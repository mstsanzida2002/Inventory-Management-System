"""
docs/01_AUTH.md's `apps/authentication/views.py`, translated into the
single `frontend` app — no `apps/authentication/` app created (see
docs/project_memory.md §13). `apps.users.models.User` -> `frontend.models.User`;
`apps.audit.services.log_action` -> `frontend.audit.log_action`;
`apps.settings_manager.models.SystemSettings` -> `frontend.models.SystemSettings`;
`apps.notifications.services.notify_user` -> `frontend.notifications.notify_user`.

`redirect_by_role()` is intentionally NOT implemented as documented: the
reference code assumes three distinct routes (`dashboard:admin`/
`dashboard:supervisor`/`dashboard:staff`), but only one `/dashboard/`
route exists in this project (no dedicated Dashboard module doc — see
docs/project_memory.md §12/§17 gap list). Everyone redirects to the one
real `frontend:dashboard` route; role-conditional content inside that
template (02_RBAC.md's own template example shows exactly this pattern)
is the right fix, not inventing new routes.

`auth:login`/`auth:logout` -> `frontend:login`/`frontend:logout` — this
project's login route lives in the `frontend` namespace (see
docs/project_memory.md §12 bug #1: an earlier bug fix moved *away* from
django.contrib.auth's built-in `accounts:` namespace).
"""
import json
from datetime import date, timedelta

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login as auth_login,
    logout as auth_logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.views import PasswordResetConfirmView
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth, TruncWeek
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from frontend import audit
from frontend import reports as report_lib
from frontend.forms import (
    AdjustmentForm,
    ApprovalPolicyForm,
    CategoryForm,
    ProductForm,
    PurchaseOrderForm,
    ReasonForm,
    SaleTransactionForm,
    SupplierForm,
    SystemSettingsForm,
    UserForm,
    parse_line_items,
)
from frontend.mixins import AdminRequiredMixin, AnyStaffMixin, SupervisorRequiredMixin
from frontend.approvals import can_approve, resolve_for_transaction
from frontend.classification import run_full_classification
from frontend.forecasting import backfill_actual_demand, latest_forecast_batch, needs_replenishment, run_full_forecast
from frontend.models import (
    AdjustmentReason,
    AdjustmentStatus,
    ApprovalOutcome,
    ApprovalPolicy,
    ApprovalTxType,
    AuditLog,
    Category,
    DemandForecast,
    ForecastPeriod,
    InventoryAdjustment,
    InventoryClassification,
    InventoryMovement,
    InventoryRecord,
    InventoryStatus,
    MovementType,
    Notification,
    NotificationType,
    POStatus,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SaleItem,
    SaleStatus,
    SaleTransaction,
    StockClassification,
    Supplier,
    SystemSettings,
    UnitOfMeasurement,
    User,
    UserRole,
)
from frontend.notifications import (
    notify_admins,
    notify_supervisors,
    notify_user,
    send_new_user_credentials_email,
)
from frontend.validators import generate_strong_password, validate_product_image
from frontend.services import (
    AdjustmentService,
    ApprovalAuthorityError,
    InsufficientStockError,
    InventoryService,
    PurchaseService,
    SaleService,
)


def landing(request):
    return render(request, "landing/index.html")


def login(request):
    if request.user.is_authenticated:
        return redirect("frontend:dashboard")

    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        try:
            user_obj = User.objects.get(email=identifier) if "@" in identifier else User.objects.get(username=identifier)
        except User.DoesNotExist:
            messages.error(request, "Invalid credentials.")
            audit.log_action(
                None, audit.LOGIN_FAILED, "authentication", status="failure",
                details={"identifier": identifier}, request=request,
            )
            return render(request, "accounts/login.html")

        # Lockout check happens before authenticate() — a locked-out
        # account never even reaches a password comparison.
        if user_obj.locked_until and user_obj.locked_until > timezone.now():
            messages.error(
                request,
                f"Account locked. Try again after "
                f"{timezone.localtime(user_obj.locked_until).strftime('%H:%M:%S')}.",
            )
            return render(request, "accounts/login.html")

        # is_active check also happens before authenticate() — not after,
        # unlike 01_AUTH.md's own reference code. Django's default
        # ModelBackend already refuses to authenticate an inactive user
        # (returns None), which makes an `if not user.is_active` check
        # placed AFTER a successful authenticate() call unreachable dead
        # code as originally written. Checking first gives a correct,
        # specific message without also bumping the failed-attempt
        # counter for a deactivated account whose password was actually
        # correct — that's not a failed *login attempt* by the user.
        if not user_obj.is_active:
            messages.error(request, "Your account is inactive. Contact administrator.")
            return render(request, "accounts/login.html")

        user = authenticate(request, username=user_obj.username, password=password)

        if user is None:
            user_obj.failed_login_attempts += 1
            max_attempts = django_settings.MAX_LOGIN_ATTEMPTS
            just_locked = False
            if user_obj.failed_login_attempts >= max_attempts:
                user_obj.locked_until = timezone.now() + timedelta(seconds=django_settings.LOCKOUT_DURATION)
                user_obj.failed_login_attempts = 0
                just_locked = True
                messages.error(request, "Account locked due to too many failed attempts.")
            else:
                remaining = max_attempts - user_obj.failed_login_attempts
                messages.error(request, f"Invalid credentials. {remaining} attempts remaining.")
            user_obj.save(update_fields=["failed_login_attempts", "locked_until"])
            audit.log_action(user_obj, audit.LOGIN_FAILED, "authentication", status="failure", request=request)
            if just_locked:
                audit.log_action(user_obj, audit.ACCOUNT_LOCKED, "authentication", status="failure", request=request)
            return render(request, "accounts/login.html")

        # Successful login.
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_attempts", "locked_until"])
        auth_login(request, user)
        audit.log_action(user, audit.LOGIN_SUCCESS, "authentication", status="success", request=request)

        settings_obj = SystemSettings.get_settings()
        request.session.set_expiry(settings_obj.session_timeout_seconds)

        return redirect("frontend:dashboard")

    return render(request, "accounts/login.html")


@login_required
def logout_view(request):
    audit.log_action(request.user, audit.LOGOUT, "authentication", status="success", request=request)
    auth_logout(request)
    return redirect("frontend:login")


@login_required
def profile_view(request):
    user = request.user
    if request.method == "POST":
        user.full_name = request.POST.get("full_name", user.full_name).strip() or user.full_name
        user.contact_number = request.POST.get("contact_number", user.contact_number).strip()
        if "profile_image" in request.FILES:
            image = request.FILES["profile_image"]
            # Phase 8.98e: profile_image (SCHEMA.md's own field, already on
            # the model since Phase 1) had no validation at all before this
            # — any file of any type/size would silently become the user's
            # avatar. Reuses validate_product_image() unchanged: its check
            # (extension + size) is generic image validation with nothing
            # product-specific in it. Phase 13's SystemSettings.company_logo
            # gets its own validate_company_logo() instead (SVG support, a
            # profile photo doesn't need) — same precedent, different
            # validator once the two fields' real requirements diverged.
            try:
                validate_product_image(image)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("frontend:profile")
            user.profile_image = image
        user.save()

        messages.success(request, "Profile updated successfully.")
        audit.log_action(user, audit.PROFILE_UPDATED, "authentication", status="success", request=request)
        return redirect("frontend:profile")

    return render(request, "accounts/profile.html")


def _record_password_change(user, request):
    """Phase 8.99a — extracted out of change_password_view so
    StockwellPasswordResetConfirmView (below) can fire the exact same
    audit/notify sequence, not a second hand-copied one. Every path that
    ends in a successful set_password() — the profile modal, and now the
    emailed reset link — must be equally visible to the audit log and
    every Admin; before this, only the modal's path was. Never receives
    the new password itself: nothing here takes one as an argument, so
    there's nothing to leak into `notify_user`/`notify_admins`' stored
    Notification rows or `audit.log_action`'s `details`."""
    notify_user(
        user, NotificationType.PASSWORD_CHANGED, "Password Changed",
        "Your password was successfully updated.",
    )
    # Every admin is told a password changed — reusing the same documented
    # PASSWORD_CHANGED type for a second recipient set
    # (frontend.notifications.notify_admins()), never the new password.
    notify_admins(
        NotificationType.PASSWORD_CHANGED, f"Password Changed: {user.full_name}",
        f"{user.full_name} ({user.username}) changed their account password.",
    )
    audit.log_action(user, audit.PASSWORD_CHANGED, "authentication", status="success", request=request)


@login_required
def change_password_view(request):
    """Phase 8.98a — split out of profile_view's old inline "new password"
    field (which had no current-password check and no confirm field, both
    real gaps for a self-service password change). This is the only
    server-side path that ever calls set_password() for the logged-in
    user's own account now — validate_password() (the same
    AUTH_PASSWORD_VALIDATORS chain, StrongPasswordValidator included) is
    still the actual enforcement point, same as before. Returns JSON,
    matching modal-form.js's fetch()-based onSubmit contract — a real
    page redirect (like profile_view's own POST) isn't right for a modal."""

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed."}, status=405)

    user = request.user
    current_password = request.POST.get("current_password", "")
    new_password = request.POST.get("new_password", "")
    confirm_password = request.POST.get("confirm_password", "")

    errors = {}
    if not user.check_password(current_password):
        errors["current_password"] = [{"message": "Current password is incorrect.", "code": "invalid"}]
    if new_password != confirm_password:
        errors["confirm_password"] = [{"message": "Passwords do not match.", "code": "invalid"}]
    try:
        validate_password(new_password, user)
    except ValidationError as exc:
        errors["new_password"] = [{"message": msg, "code": "invalid"} for msg in exc.messages]

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    user.set_password(new_password)
    user.save()
    update_session_auth_hash(request, user)  # keep this session alive post-change
    _record_password_change(user, request)
    messages.success(request, "Password changed successfully.")
    return JsonResponse({"success": True})


class StockwellPasswordResetConfirmView(PasswordResetConfirmView):
    """Phase 8.99a — Django's own PasswordResetConfirmView.form_valid()
    calls form.save() (SetPasswordForm, which itself already runs
    validate_password()/StrongPasswordValidator via
    UserModel.clean_new_password2() — no re-validation needed here) and
    redirects; it never goes through change_password_view, so without
    this override a password reset via the emailed link would be
    invisible to both the audit log and every Admin, while the identical
    change made through the profile modal is fully recorded — a genuine
    compliance-record inconsistency, confirmed by reading Django's own
    form_valid() source before writing this, not assumed.

    Only adds the missing audit/notify call — form.save()'s actual
    password-setting logic is untouched, reused via super().form_valid(),
    not reimplemented. form.user (set by SetPasswordForm.__init__, not by
    save()) is the target user the password was just changed for; the new
    password itself is never read here, so there is nothing for
    _record_password_change() to leak."""

    def form_valid(self, form):
        response = super().form_valid(form)
        _record_password_change(form.user, self.request)
        return response


# -------------------------------------------------------------- Dashboard
# Phase 8.96 — docs/09_DASHBOARD.md (originated + approved Phase 8.95/
# 8.95.1). Every number below traces to a row in that spec's decision
# table; nothing here is a number invented to fill a gap — where the spec
# says an element can't be real yet (AI Insights) it's simply absent, not
# faked or shown as an empty state.

DASHBOARD_PREVIEW_ROWS = 5  # 09_DASHBOARD.md Decision 3 — the one place this is defined.

_PURCHASE_ACTIVITY_STATUSES = (POStatus.APPROVED, POStatus.PARTIAL, POStatus.RECEIVED)  # Decision 2b


def _dashboard_date_buckets(unit, count):
    """(bucket_start, label) tuples, oldest first, ending at the current
    bucket. 'day'/'week'/'month' per 09_DASHBOARD.md's chart windows —
    Decision 2a. Week buckets start Monday (matches Django's TruncWeek);
    month buckets start on the 1st (matches TruncMonth)."""
    today = timezone.localdate()
    buckets = []
    if unit == "day":
        for i in range(count - 1, -1, -1):
            d = today - timedelta(days=i)
            buckets.append((d, d.strftime("%a")))
    elif unit == "week":
        week_start = today - timedelta(days=today.weekday())
        for i in range(count - 1, -1, -1):
            d = week_start - timedelta(weeks=i)
            buckets.append((d, d.strftime("%b %d")))
    else:  # month
        y, m = today.year, today.month
        for i in range(count - 1, -1, -1):
            total_month = (y * 12 + (m - 1)) - i
            by, bm = divmod(total_month, 12)
            buckets.append((date(by, bm + 1, 1), date(by, bm + 1, 1).strftime("%b")))
    return buckets


def _sales_purchases_series(unit, count):
    """09_DASHBOARD.md §3a — Sales = completed SaleTransactions by
    transaction_date; Purchases = APPROVED/PARTIAL/RECEIVED PurchaseOrders
    by order_date (Decision 2b). Both DB-aggregated (Sum + annotate), zero-
    filled per bucket in Python rather than pulling raw rows."""
    buckets = _dashboard_date_buckets(unit, count)
    start = buckets[0][0]
    trunc = {"day": None, "week": TruncWeek, "month": TruncMonth}[unit]

    sales_qs = SaleTransaction.objects.filter(status=SaleStatus.COMPLETED, transaction_date__gte=start)
    purchase_qs = PurchaseOrder.objects.filter(status__in=_PURCHASE_ACTIVITY_STATUSES, order_date__gte=start)

    if unit == "day":
        sales_rows = sales_qs.values("transaction_date").annotate(total=Sum("total_amount"))
        sales_totals = {r["transaction_date"]: r["total"] or 0 for r in sales_rows}
        purchase_rows = purchase_qs.values("order_date").annotate(total=Sum("total_cost"))
        purchase_totals = {r["order_date"]: r["total"] or 0 for r in purchase_rows}
    else:
        sales_rows = sales_qs.annotate(bucket=trunc("transaction_date")).values("bucket").annotate(total=Sum("total_amount"))
        sales_totals = {r["bucket"]: r["total"] or 0 for r in sales_rows}
        purchase_rows = purchase_qs.annotate(bucket=trunc("order_date")).values("bucket").annotate(total=Sum("total_cost"))
        purchase_totals = {r["bucket"]: r["total"] or 0 for r in purchase_rows}

    return {
        "labels": [label for _, label in buckets],
        "sales": [float(sales_totals.get(bstart, 0)) for bstart, _ in buckets],
        "purchases": [float(purchase_totals.get(bstart, 0)) for bstart, _ in buckets],
    }


def _inventory_movement_series():
    """09_DASHBOARD.md §3b — Received/Dispatched by InventoryMovement's
    own quantity_change sign, last 6 months (the mock's own given window,
    not a decision). created_at is a DateTimeField, so TruncMonth returns
    an aware datetime — .date() normalizes it to match the bucket keys."""
    buckets = _dashboard_date_buckets("month", 6)
    start = buckets[0][0]
    qs = InventoryMovement.objects.filter(created_at__date__gte=start)

    received_rows = (
        qs.filter(quantity_change__gt=0).annotate(bucket=TruncMonth("created_at"))
        .values("bucket").annotate(total=Sum("quantity_change"))
    )
    received_totals = {r["bucket"].date(): r["total"] or 0 for r in received_rows}

    dispatched_rows = (
        qs.filter(quantity_change__lt=0).annotate(bucket=TruncMonth("created_at"))
        .values("bucket").annotate(total=Sum("quantity_change"))
    )
    dispatched_totals = {r["bucket"].date(): abs(r["total"] or 0) for r in dispatched_rows}

    return {
        "labels": [label for _, label in buckets],
        "received": [float(received_totals.get(bstart, 0)) for bstart, _ in buckets],
        "dispatched": [float(dispatched_totals.get(bstart, 0)) for bstart, _ in buckets],
    }


class DashboardView(AnyStaffMixin, View):
    """Phase 8.97 (Part A) — previously a bare function view with no auth
    check at all, a real risk once Phase 8.96 made this page compute
    genuine business aggregates (inventory value, stock levels, real
    headcounts) instead of fabricated numbers. `AnyStaffMixin` matches
    every other real view's convention and `09_DASHBOARD.md`'s own
    "Any role, same content" decision — not gated to a single role, just
    to "logged in at all" (all 3 roles satisfy `AnyStaffMixin`)."""

    def get(self, request):
        # BUG-37 fix (Phase 8.6): greeting tracks time of day in Bangladesh
        # time, the same clock every other timestamp in the app renders in
        # (TIME_ZONE = 'Asia/Dhaka', see config/settings.py).
        now_local = timezone.localtime()
        hour = now_local.hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        thirty_days_ago = timezone.now() - timedelta(days=30)

        # ---- KPI cards (Decision 1: "+N new in the last 30 days", all 4) ----
        kpis = {
            "total_products": Product.objects.count(),
            "new_products_30d": Product.objects.filter(created_at__gte=thirty_days_ago).count(),
            "total_categories": Category.objects.count(),
            "new_categories_30d": Category.objects.filter(created_at__gte=thirty_days_ago).count(),
            # "Active suppliers", not raw total — Decision 7.
            "active_suppliers": Supplier.objects.filter(is_active=True).count(),
            "new_active_suppliers_30d": Supplier.objects.filter(
                is_active=True, created_at__gte=thirty_days_ago
            ).count(),
            # Not in API_CONTRACTS.md's documented stats payload — Decision 6.
            "total_users": User.objects.count(),
            "new_users_30d": User.objects.filter(created_at__gte=thirty_days_ago).count(),
        }

        # ---- Compact stat strip ----
        inv_agg = InventoryRecord.objects.aggregate(value=Sum("total_value"), units=Sum("current_stock"))
        stats = {
            "inventory_value": inv_agg["value"] or 0,
            "stock_units": inv_agg["units"] or 0,  # Decision 6.
            "low_stock_count": InventoryRecord.objects.filter(status=InventoryStatus.LOW_STOCK).count(),
            "out_of_stock_count": InventoryRecord.objects.filter(status=InventoryStatus.OUT_OF_STOCK).count(),
        }

        # ---- Stock Alerts widget (§4a) ----
        stock_alerts = list(
            InventoryRecord.objects.filter(status__in=[InventoryStatus.LOW_STOCK, InventoryStatus.OUT_OF_STOCK])
            .select_related("product").order_by("current_stock")[:DASHBOARD_PREVIEW_ROWS]
        )
        for record in stock_alerts:
            # Reused from InventoryListView (Phase 8.9) — same badge convention,
            # not redefined. Looked up lazily (method body, not module level)
            # since _INVENTORY_STATUS_BADGE is defined later in this file.
            record.status_badge = _INVENTORY_STATUS_BADGE.get(record.status, "badge-indigo")

        # ---- Pending Approvals widget (§4b) — read-only, no action buttons ----
        pending_po_count = PurchaseOrder.objects.filter(status=POStatus.PENDING).count()
        pending_adjustment_count = InventoryAdjustment.objects.filter(status=AdjustmentStatus.PENDING).count()

        pending_items = []
        for po in (
            PurchaseOrder.objects.filter(status=POStatus.PENDING)
            .select_related("supplier").order_by("-created_at")[:DASHBOARD_PREVIEW_ROWS]
        ):
            pending_items.append({
                "kind": "purchase", "title": po.po_number,
                "meta": f"{po.supplier.company_name} · ${po.total_cost:.2f}",
                "created_at": po.created_at,
            })
        for adjustment in (
            InventoryAdjustment.objects.filter(status=AdjustmentStatus.PENDING)
            .select_related("product").order_by("-created_at")[:DASHBOARD_PREVIEW_ROWS]
        ):
            sign = "+" if adjustment.adjustment_type == "increase" else "−"
            pending_items.append({
                "kind": "adjustment", "title": f"Adjustment #AJ-{adjustment.pk:04d}",
                "meta": f"{adjustment.product.name} · {sign}{adjustment.quantity} units",
                "created_at": adjustment.created_at,
            })
        pending_items.sort(key=lambda item: item["created_at"], reverse=True)
        pending_items = pending_items[:DASHBOARD_PREVIEW_ROWS]

        # ---- Recent Activity widget (§4c) — Decision 5: admin/supervisor only ----
        # `AnyStaffMixin` now guarantees an authenticated user with a role
        # reaches this point at all, so `is_authenticated` here is
        # belt-and-suspenders, not load-bearing — kept anyway since it's
        # harmless and keeps this check correct in isolation if the mixin
        # is ever changed.
        recent_activity = None
        if request.user.is_authenticated and request.user.role in (UserRole.ADMIN, UserRole.SUPERVISOR):
            recent_activity = list(
                AuditLog.objects.exclude(module="authentication")
                .select_related("user").order_by("-timestamp")[:DASHBOARD_PREVIEW_ROWS]
            )
            for log in recent_activity:
                log.user_label = log.user.full_name if log.user else "System"

        # ---- AI Insights: Stock Classification (§4d, REQ 11.9/11.10, PROMPT_C_STEP_3) ----
        # 09_DASHBOARD.md §4d's own query shape ("most recently classified
        # 4 rows") was written when neither AI table had any rows at all
        # and was never re-verified once they did (docs/bugsfound.md
        # BUG-76) — "most recently classified" is meaningless once
        # run_full_classification() updates every active product's
        # classified_at in the same batch (ties, arbitrary order), and
        # says nothing about priority. Replaced here with what the page
        # actually needs: real counts across all four states (matching
        # SlowMovingDeadStockView's own counting, so this widget can
        # never silently disagree with /ai/slow-moving/ — the exact
        # failure mode BUG-64 was for forecasts) and the highest-priority
        # dead/slow products by stagnation_index, the same composite
        # score /ai/slow-moving/ itself sorts and displays by. Same
        # Supervisor+ role gate as the page these link to
        # (SlowMovingDeadStockView is SupervisorRequiredMixin) — showing
        # this widget to a Staff user who can't open the linked page
        # would be a dead end, not an insight.
        classification_insights = None
        if request.user.is_authenticated and request.user.role in (UserRole.ADMIN, UserRole.SUPERVISOR):
            classification_counts = {choice: 0 for choice in StockClassification.values}
            for row in InventoryClassification.objects.values('classification').annotate(count=Count('id')):
                classification_counts[row['classification']] = row['count']

            # PROMPT_C_STEP_3 — priority is stagnation_index today. Step 4
            # adds capital-at-risk ranking (current_stock * purchase_price
            # for dead/slow products) — this stays a plain list of rows
            # with one sort key, so swapping the key (or blending it with
            # stagnation_index) is a one-line change here, not a
            # restructure of the widget or its template.
            priority_products = list(
                InventoryClassification.objects.filter(
                    classification__in=[StockClassification.DEAD, StockClassification.SLOW],
                )
                .select_related('product', 'product__category')
                .order_by('-stagnation_index')[:DASHBOARD_PREVIEW_ROWS]
            )
            for c in priority_products:
                c.badge = SlowMovingDeadStockView._BADGE.get(c.classification, "badge-neutral")

            classification_insights = {
                "counts": classification_counts,
                "total_flagged": classification_counts[StockClassification.SLOW] + classification_counts[StockClassification.DEAD],
                "priority_products": priority_products,
            }

        # ---- AI Insights: Forecast Replenishment (§4d, REQ 11.9, PROMPT_C_STEP_3) ----
        # Deliberately NOT ForecastSummaryAPIView — that endpoint has a
        # known, still-open aggregation defect (docs/bugsfound.md BUG-64:
        # it aggregates every DemandForecast row ever created, no dedup
        # by latest run, so repeated "Run forecast now" clicks skew its
        # counts toward whichever products got re-run most). Uses
        # frontend.forecasting.latest_forecast_batch() instead — the same
        # dedup-by-latest-created-per-(product, period, period_start)
        # DemandForecastingView's own HTML page uses, extracted specifically
        # so this widget can't define a second, divergent "current
        # forecast." "Needs replenishment" = forecasted_demand exceeds
        # current_stock, the identical condition run_full_forecast()'s own
        # replenish_alerts uses; "urgency" = the size of that shortfall.
        forecast_insights = None
        if request.user.is_authenticated and request.user.role in (UserRole.ADMIN, UserRole.SUPERVISOR):
            forecasts, forecast_last_run = latest_forecast_batch()
            stock_by_product = dict(InventoryRecord.objects.values_list('product_id', 'current_stock'))

            # needs_replenishment() (frontend/forecasting.py) is the same
            # function run_full_forecast()'s own replenish_alerts calls —
            # written once so tuning this threshold can't happen in one
            # call site and silently drift from the other.
            replenishment_needed = []
            for f in forecasts:
                current_stock = stock_by_product.get(f.product_id, 0)
                if needs_replenishment(f.forecast_period, f.forecasted_demand, current_stock):
                    f.current_stock_display = current_stock
                    f.deficit = float(f.forecasted_demand) - current_stock
                    f.confidence_pct = round(float(f.confidence_score) * 100)
                    replenishment_needed.append(f)
            replenishment_needed.sort(key=lambda f: -f.deficit)

            forecast_insights = {
                "last_run": forecast_last_run,
                # Same computation ForecastSummaryAPIView and
                # DemandForecastingView both use against the same
                # latest_forecast_batch() rows — BUG-64 was exactly this
                # figure disagreeing across surfaces, so it's exposed
                # here too rather than only implied by the widget's list.
                "products_forecasted": len({f.product_id for f in forecasts}),
                "replenishment_count": len(replenishment_needed),
                "replenishment_products": replenishment_needed[:DASHBOARD_PREVIEW_ROWS],
            }

        # ---- Charts (§3) ----
        chart_data = {
            "sales_purchases": {
                "daily": _sales_purchases_series("day", 7),
                "weekly": _sales_purchases_series("week", 8),
                "monthly": _sales_purchases_series("month", 6),
            },
            "inventory_movement": _inventory_movement_series(),
        }

        context = {
            "active_nav": "dashboard",
            "greeting": greeting,
            "today": now_local.date(),
            "kpis": kpis,
            "stats": stats,
            "stock_alerts": stock_alerts,
            "pending_items": pending_items,
            "pending_po_count": pending_po_count,
            "pending_adjustment_count": pending_adjustment_count,
            "recent_activity": recent_activity,
            "classification_insights": classification_insights,
            "forecast_insights": forecast_insights,
            "chart_data": chart_data,
        }
        return render(request, "dashboard/dashboard.html", context)


def _product_ids_with_history():
    """Phase 8.99i — mirrors `_user_ids_with_history()`'s own reasoning
    (Phase 8.99f-2) for Products: `Product` is referenced by `PROTECT` FKs
    from `PurchaseOrderItem`/`SaleItem`/`InventoryMovement`/
    `InventoryAdjustment` — a genuine hard-delete must refuse all of
    those. `InventoryRecord.product` (a `OneToOneField`, also `PROTECT`)
    is deliberately NOT included here: every product gets exactly one at
    creation (`InventoryService.initialize_for_product()`) regardless of
    whether it's ever actually used, so it's current-state bookkeeping,
    not history — `ProductDeleteView` deletes it explicitly as part of a
    genuinely safe delete, the one place this project ever removes an
    `InventoryRecord`. `DemandForecast`/`InventoryClassification` are
    `CASCADE` (disposable, AI-generated) and need no check at all."""
    ids = set()
    ids |= set(PurchaseOrderItem.objects.values_list("product_id", flat=True))
    ids |= set(SaleItem.objects.values_list("product_id", flat=True))
    ids |= set(InventoryMovement.objects.values_list("product_id", flat=True))
    ids |= set(InventoryAdjustment.objects.values_list("product_id", flat=True))
    return ids


class ProductListCreateView(AnyStaffMixin, View):
    """docs/03_PRODUCTS.md's product_list_view/product_create_view,
    combined into one view against the one existing /products/ route (this
    project has no separate products:list/products:create URL split, and
    the Add Product modal already posts back to the same page). AnyStaffMixin
    (frontend/mixins.py, Phase 4) mirrors 03_PRODUCTS.md's own
    @staff_required on both — the doc guards read and write the same way,
    so both are guarded here too, not just create.

    GET renders the real product list (§2 of this phase); POST is the
    Add Product modal's real endpoint, called via fetch() from
    product-form.js's onSubmit (Phase 5.5 — modal-form.js now natively
    supports a Promise-returning onSubmit, see that file's header)."""

    def get(self, request):
        products = list(
            Product.objects.select_related("category", "supplier").order_by("-created_at")
        )
        counts = {"total": 0, "in_stock": 0, "low_stock": 0, "out_of_stock": 0}
        history_ids = _product_ids_with_history()
        for product in products:
            # Phase 8.99i — same "compute once, reuse for both the row's
            # own display and the delete endpoint's own enforcement" split
            # as _user_ids_with_history() (Phase 8.99f-2).
            product.deletable = product.pk not in history_ids
            # Mirrors product-form.js's old client-side deriveStatus() and
            # InventoryRecord.update_status()'s thresholds — read from
            # Product.current_stock/reorder_level (kept in sync by
            # InventoryService, the only code path allowed to write them)
            # rather than joining InventoryRecord, since legacy rows
            # created before this phase (e.g. via /admin/) may have no
            # InventoryRecord at all.
            if product.current_stock <= 0:
                product.stock_label, product.stock_badge = "Out of stock", "badge-danger"
                counts["out_of_stock"] += 1
            elif product.reorder_level and product.current_stock <= product.reorder_level:
                product.stock_label, product.stock_badge = "Low stock", "badge-warning"
                counts["low_stock"] += 1
            else:
                product.stock_label, product.stock_badge = "In stock", "badge-success"
                counts["in_stock"] += 1
            counts["total"] += 1
            # Phase 8.99e — same "compute once server-side, read via a
            # data-* attribute" pattern PurchaseOrder.receive_items_json
            # already uses for the Receive modal: lets the Edit modal be
            # pre-filled with zero extra network round-trips, reusing the
            # existing embed-JSON-on-the-row mechanism rather than adding
            # a new fetch helper.
            product.edit_json = json.dumps({
                "name": product.name, "sku": product.sku, "barcode": product.barcode or "",
                "category": product.category_id, "supplier": product.supplier_id,
                "brand": product.brand, "unit": product.unit,
                "purchase_price": str(product.purchase_price), "selling_price": str(product.selling_price),
                "tax_rate": str(product.tax_rate), "reorder_level": product.reorder_level,
                "description": product.description, "image_url": product.image.url if product.image else "",
            })

        context = {
            "active_nav": "products",
            "products": products,
            "counts": counts,
            "categories": Category.objects.filter(is_active=True).order_by("name"),
            "suppliers": Supplier.objects.filter(is_active=True).order_by("company_name"),
            "unit_choices": UnitOfMeasurement.choices,
        }
        return render(request, "products/products.html", context)

    def post(self, request):
        form = ProductForm(request.POST, request.FILES)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        with transaction.atomic():
            product = form.save(commit=False)
            product.save()
            # Phase 5.5 correction: creating a product means a catalog entry
            # now exists, not that stock arrived — no InventoryMovement is
            # written here. See InventoryService.initialize_for_product()'s
            # docstring and docs/bugsfound.md's Phase 5.5 entry. Stock only
            # moves for real once a Purchase Order is received.
            InventoryService.initialize_for_product(product)
            audit.log_action(
                request.user, audit.PRODUCT_CREATED, "products",
                affected_id=product.pk, status="success", request=request,
            )

        return JsonResponse({"success": True})


class ProductUpdateView(AnyStaffMixin, View):
    """Phase 8.99e — this project's first per-entity update route (see
    docs/project_memory.md §13: no per-entity detail/update route existed
    anywhere before this phase, by deliberate decision — every module had
    list+create only). 02_RBAC.md: "Create/edit products" is ✅ for all 3
    roles, same as create — `AnyStaffMixin`, not `SupervisorRequiredMixin`
    (that gate is reserved for `ProductDeactivateView` below; 02_RBAC.md's
    "Deactivate products" row is Admin/Supervisor only — a real asymmetry
    between these two buttons in the same table row, not a copy-paste of
    the same gate twice).

    Reuses `ProductForm` completely unchanged via `instance=` — the exact
    same server-side validation (unique SKU/barcode, non-negative prices,
    active-only Category/Supplier, tax_rate, image type/size) applies to
    an edit exactly as it does to a create, per this phase's own explicit
    instruction not to fork the form. 03_PRODUCTS.md documents no
    `product_update_view` reference code at all (only list/create/
    deactivate) — this view's shape (reuse the create form via `instance=`,
    log `PRODUCT_UPDATED`) follows `PurchaseOrderForm`/`SaleTransactionForm`
    not needing a separate edit form either, and the doc's own Audit
    Actions table, which does list `PRODUCT_UPDATED`.

    SKU is read-only on edit (disclosed decision — no doc gives a reason
    it should be changeable after creation, and it's an identifier a
    product is referenced by across the app: POs, sales, reports, already-
    issued PDFs). Enforced server-side, not just by disabling the input
    client-side: the posted `sku` is always overwritten with the
    instance's current value before `ProductForm` ever sees it. This also
    sidesteps a real gotcha — `ProductForm.clean_sku()`'s "blank ->
    auto-generate a new one" branch exists for *create*; if a disabled
    client-side SKU input simply omitted the field (which browsers do),
    an edit would silently issue the product a brand-new SKU on every
    save without this override.

    Does not touch `InventoryService`/the ledger beyond
    `sync_reorder_level()` — editing a catalogue entry never moves stock
    (the §13 rule BUG-34 established for create applies identically to
    edit); reorder_level is a config value, not a stock quantity, so
    syncing it to InventoryRecord writes no InventoryMovement row."""

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        data = request.POST.copy()
        data["sku"] = product.sku
        form = ProductForm(data, request.FILES, instance=product)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        with transaction.atomic():
            product = form.save()
            InventoryService.sync_reorder_level(product)
            audit.log_action(
                request.user, audit.PRODUCT_UPDATED, "products",
                affected_id=product.pk, status="success", request=request,
            )

        return JsonResponse({"success": True})


class ProductDeactivateView(SupervisorRequiredMixin, View):
    """02_RBAC.md: "Deactivate products" is Admin/Supervisor only — Staff
    can edit a product (ProductUpdateView, AnyStaffMixin above) but not
    deactivate one; two different gates on two buttons in the same row.
    03_PRODUCTS.md: "Never hard-delete a product — use is_active = False"
    — this is that soft-delete, matching its own `product_deactivate_view`
    reference shape (pure status flip, no InventoryService/ledger
    involvement — deactivating a catalogue entry doesn't move stock,
    same reasoning as create/edit above). Idempotent, matching
    `UserDeactivateView`'s own precedent: no special-cased error for
    deactivating an already-inactive product, just re-confirms the flag
    and logs it."""

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
        audit.log_action(
            request.user, audit.PRODUCT_DEACTIVATED, "products",
            affected_id=product.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class ProductReactivateView(SupervisorRequiredMixin, View):
    """Phase 8.99i — same gate as ProductDeactivateView (its own natural
    counterpart); Products had no reactivate path at all before this
    phase (Phase 8.99e scoped it out as optional). Idempotent, same
    precedent as UserReactivateView/ProductDeactivateView above."""

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        product.is_active = True
        product.save(update_fields=["is_active", "updated_at"])
        audit.log_action(
            request.user, audit.PRODUCT_REACTIVATED, "products",
            affected_id=product.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class ProductDeleteView(SupervisorRequiredMixin, View):
    """Phase 8.99i — true delete, mirroring UserDeleteView's own shape
    (Phase 8.99f-2) exactly: only ever succeeds for a product referenced
    by none of the 4 PROTECT FKs in _product_ids_with_history(). Every
    other product — meaning any product actually used anywhere — can only
    be deactivated (ProductDeactivateView); hard-deleting it would raise
    ProtectedError. Same SupervisorRequiredMixin gate as Deactivate (its
    own sibling action in the same row), not AnyStaffMixin.

    Explicitly deletes the product's own InventoryRecord first — the one
    PROTECT relation _product_ids_with_history() deliberately excludes,
    since every product has exactly one regardless of use (current-state
    bookkeeping, not history) and it would otherwise block this delete
    even for a genuinely unused product. InventoryClassification/
    DemandForecast are CASCADE and need no explicit handling."""

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        if product.pk in _product_ids_with_history():
            return JsonResponse({
                "success": False,
                "error": "This product has purchase, sale, or adjustment history and can't be deleted; deactivate instead.",
            }, status=400)
        name = product.name
        with transaction.atomic():
            InventoryRecord.objects.filter(product=product).delete()
            product.delete()
        audit.log_action(
            request.user, audit.PRODUCT_DELETED, "products",
            affected_id=pk, status="success", request=request,
            details={"deleted_product_name": name},
        )
        return JsonResponse({"success": True})


class ProductExportView(AnyStaffMixin, View):
    """Phase 8.98 (BUG-44) — Products' "Export" button was decorative.
    Real CSV now, via `frontend/reports.py`'s shared `generate_csv_response()`
    (the same CSV-writing utility every export in this app uses) rather
    than a new export mechanism. Exports the full product list, not the
    current `table-filter.js` selection — that filter is client-side only
    (Phase 8.7), with no server-side equivalent to read yet; stated here
    rather than silently only exporting whatever happened to be visible."""

    def get(self, request):
        products = Product.objects.select_related("category", "supplier").order_by("name")
        headers = [
            "SKU", "Name", "Category", "Supplier", "Brand",
            "Current Stock", "Reorder Level", "Unit", "Purchase Price", "Selling Price", "Active",
        ]
        rows = [
            [
                p.sku, p.name, p.category.name, p.supplier.company_name, p.brand,
                p.current_stock, p.reorder_level, p.get_unit_display(),
                f"{p.purchase_price:.2f}", f"{p.selling_price:.2f}", "Yes" if p.is_active else "No",
            ]
            for p in products
        ]
        return report_lib.generate_csv_response(headers, rows, "products.csv")

def _category_ids_with_products():
    """Phase 8.99i — Category's only PROTECT reference is Product.category
    (related_name='products'); a category is safe to hard-delete only if
    it has zero products, ever."""
    return set(Product.objects.values_list("category_id", flat=True))


def _supplier_ids_with_history():
    """Phase 8.99i — Supplier is referenced by two PROTECT FKs:
    Product.supplier and PurchaseOrder.supplier — safe to hard-delete
    only if zero of both."""
    ids = set(Product.objects.values_list("supplier_id", flat=True))
    ids |= set(PurchaseOrder.objects.values_list("supplier_id", flat=True))
    return ids


class CategoryListCreateView(AnyStaffMixin, View):
    """Phase 6 — same shape as Phase 5's ProductListCreateView. GET
    renders the real Category queryset (with each category's real product
    count); POST creates via CategoryForm, called from category-form.js's
    onSubmit using the Phase 5.5 fetch()/Promise contract directly (no
    sync-XHR-in-extraValidate workaround needed this time — that
    workaround only ever existed because modal-form.js didn't support
    async onSubmit yet when Phase 5 shipped; it does now)."""

    def get(self, request):
        categories = list(Category.objects.order_by("name"))
        history_ids = _category_ids_with_products()
        for category in categories:
            category.product_count = category.products.count()
            category.deletable = category.pk not in history_ids
            # Phase 8.99i — same embed-JSON-on-the-row pattern
            # ProductListCreateView.get() already uses for its own Edit
            # modal pre-fill (Phase 8.99e) — no new mechanism.
            category.edit_json = json.dumps({
                "name": category.name, "description": category.description,
            })
        context = {"active_nav": "categories", "categories": categories}
        return render(request, "categories/categories.html", context)

    def post(self, request):
        form = CategoryForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        category = form.save(commit=False)
        category.is_active = form.cleaned_data["status"] != "Inactive"
        category.save()
        audit.log_action(
            request.user, audit.CATEGORY_CREATED, "products",
            affected_id=category.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class CategoryUpdateView(AnyStaffMixin, View):
    """Phase 8.99i — mirrors ProductUpdateView's own shape: reuses
    CategoryForm unchanged via instance=, same AnyStaffMixin gate as
    create (02_RBAC.md draws no edit/deactivate distinction for
    Categories, unlike Products — there's no documented rule requiring
    one, so this stays a single gate for both, matching the doc rather
    than inventing an asymmetry it doesn't call for).

    Deliberately does NOT process CategoryForm's own `status` field on
    edit, even though CategoryForm.Meta doesn't include is_active anyway
    (status is a synthetic, non-model ChoiceField the create view
    interprets manually) — is_active only ever changes through
    CategoryDeactivateView/CategoryReactivateView below, the same "one
    way to change active status" rule Products already established, kept
    consistent here rather than giving Categories a second path to the
    same flag."""

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        form = CategoryForm(request.POST, instance=category)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        category = form.save(commit=False)
        category.save(update_fields=["name", "description", "updated_at"])
        audit.log_action(
            request.user, audit.CATEGORY_UPDATED, "products",
            affected_id=category.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class CategoryDeactivateView(SupervisorRequiredMixin, View):
    """Phase 8.99i — same SupervisorRequiredMixin gate as
    ProductDeactivateView/SupplierDeactivateView, for consistency across
    all three modules (02_RBAC.md's "Deactivate products"/"Deactivate
    suppliers" rows are both Admin/Supervisor only; Categories has no
    documented rule of its own, so it follows its two siblings rather
    than inventing a third gating rule)."""

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        category.is_active = False
        category.save(update_fields=["is_active", "updated_at"])
        audit.log_action(
            request.user, audit.CATEGORY_DEACTIVATED, "products",
            affected_id=category.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class CategoryReactivateView(SupervisorRequiredMixin, View):

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        category.is_active = True
        category.save(update_fields=["is_active", "updated_at"])
        audit.log_action(
            request.user, audit.CATEGORY_REACTIVATED, "products",
            affected_id=category.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class CategoryDeleteView(SupervisorRequiredMixin, View):
    """Phase 8.99i — true delete, only for a category with zero products
    ever assigned to it (_category_ids_with_products()). Everyone else
    refuses cleanly, matching ProductDeleteView/UserDeleteView's shape."""

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        if category.pk in _category_ids_with_products():
            return JsonResponse({
                "success": False,
                "error": "This category has products assigned to it and can't be deleted; deactivate instead.",
            }, status=400)
        name = category.name
        category.delete()
        audit.log_action(
            request.user, audit.CATEGORY_DELETED, "products",
            affected_id=pk, status="success", request=request,
            details={"deleted_category_name": name},
        )
        return JsonResponse({"success": True})


class SupplierListCreateView(AnyStaffMixin, View):
    """Phase 6 — same shape as Phase 5's ProductListCreateView."""

    def get(self, request):
        suppliers = list(Supplier.objects.order_by("company_name"))
        counts = {"total": 0, "active": 0, "inactive": 0}
        history_ids = _supplier_ids_with_history()
        for supplier in suppliers:
            supplier.product_count = supplier.products.count()
            supplier.deletable = supplier.pk not in history_ids
            supplier.edit_json = json.dumps({
                "supplier_name": supplier.supplier_name, "company_name": supplier.company_name,
                "contact_person": supplier.contact_person, "email": supplier.email,
                "phone": supplier.phone, "address": supplier.address,
            })
            counts["total"] += 1
            counts["active" if supplier.is_active else "inactive"] += 1
        context = {"active_nav": "suppliers", "suppliers": suppliers, "counts": counts}
        return render(request, "suppliers/suppliers.html", context)

    def post(self, request):
        form = SupplierForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        supplier = form.save(commit=False)
        supplier.is_active = form.cleaned_data["status"] != "Inactive"
        supplier.save()
        audit.log_action(
            request.user, audit.SUPPLIER_CREATED, "suppliers",
            affected_id=supplier.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class SupplierUpdateView(AnyStaffMixin, View):
    """Phase 8.99i — mirrors CategoryUpdateView exactly: reuses
    SupplierForm via instance=, same AnyStaffMixin gate as create, and
    deliberately doesn't touch is_active on edit (SupplierDeactivateView/
    SupplierReactivateView own that, consistent with the other two
    modules)."""

    def post(self, request, pk):
        supplier = get_object_or_404(Supplier, pk=pk)
        form = SupplierForm(request.POST, instance=supplier)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        supplier = form.save(commit=False)
        supplier.save(update_fields=[
            "supplier_name", "company_name", "contact_person", "email", "phone", "address", "updated_at",
        ])
        audit.log_action(
            request.user, audit.SUPPLIER_UPDATED, "suppliers",
            affected_id=supplier.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class SupplierDeactivateView(SupervisorRequiredMixin, View):
    """02_RBAC.md: "Deactivate suppliers" is Admin/Supervisor only —
    same asymmetry as Products (Staff can edit, not deactivate)."""

    def post(self, request, pk):
        supplier = get_object_or_404(Supplier, pk=pk)
        supplier.is_active = False
        supplier.save(update_fields=["is_active", "updated_at"])
        audit.log_action(
            request.user, audit.SUPPLIER_DEACTIVATED, "suppliers",
            affected_id=supplier.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class SupplierReactivateView(SupervisorRequiredMixin, View):

    def post(self, request, pk):
        supplier = get_object_or_404(Supplier, pk=pk)
        supplier.is_active = True
        supplier.save(update_fields=["is_active", "updated_at"])
        audit.log_action(
            request.user, audit.SUPPLIER_REACTIVATED, "suppliers",
            affected_id=supplier.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class SupplierDeleteView(SupervisorRequiredMixin, View):
    """Phase 8.99i — true delete, only for a supplier with zero products
    AND zero purchase orders ever (_supplier_ids_with_history())."""

    def post(self, request, pk):
        supplier = get_object_or_404(Supplier, pk=pk)
        if supplier.pk in _supplier_ids_with_history():
            return JsonResponse({
                "success": False,
                "error": "This supplier has products or purchase orders and can't be deleted; deactivate instead.",
            }, status=400)
        name = supplier.company_name
        supplier.delete()
        audit.log_action(
            request.user, audit.SUPPLIER_DELETED, "suppliers",
            affected_id=pk, status="success", request=request,
            details={"deleted_supplier_name": name},
        )
        return JsonResponse({"success": True})


class SupplierExportView(AnyStaffMixin, View):
    """Phase 8.98 (BUG-44) — same treatment as ProductExportView: real CSV
    via the shared `generate_csv_response()`, full dataset (client-side
    filter has no server-side equivalent yet)."""

    def get(self, request):
        suppliers = Supplier.objects.order_by("company_name")
        headers = ["Company Name", "Supplier Name", "Contact Person", "Email", "Phone", "Address", "Active"]
        rows = [
            [s.company_name, s.supplier_name, s.contact_person, s.email, s.phone, s.address, "Yes" if s.is_active else "No"]
            for s in suppliers
        ]
        return report_lib.generate_csv_response(headers, rows, "suppliers.csv")

# ------------------------------------------------------------- Purchases
# Phase 7 — docs/05_PURCHASES.md. PurchaseService (frontend/services.py,
# Phase 3) is the ONLY code path allowed to touch stock here; every view
# below either delegates to it or (PurchaseListCreateView.post(), PO
# *creation*) stays out of stock entirely, per PurchaseService's own
# docstring ("PO creation isn't part of this service"). Never call
# InventoryMovement.save() on an existing row anywhere here — Phase 3.4
# (BUG-20) made that raise PermissionError by design.

class PurchaseListCreateView(AnyStaffMixin, View):
    """GET lists the real PurchaseOrder queryset; POST creates a new PO
    as DRAFT (matching the modal's own "Saved as a draft" copy) with its
    line items via PurchaseOrderForm + parse_line_items()."""

    _STATUS_BADGE = {
        POStatus.DRAFT: "badge-indigo", POStatus.PENDING: "badge-warning",
        POStatus.APPROVED: "badge-success", POStatus.PARTIAL: "badge-warning",
        POStatus.RECEIVED: "badge-success", POStatus.REJECTED: "badge-danger",
        POStatus.CANCELLED: "badge-danger",
    }

    def get(self, request):
        orders = list(
            PurchaseOrder.objects.select_related("supplier", "created_by")
            .prefetch_related("items__product").order_by("-created_at")
        )
        counts = {"open": 0, "pending": 0, "received_month": 0, "value_month": 0}
        now = timezone.now()
        for po in orders:
            po.item_count = po.items.count()
            po.status_badge = self._STATUS_BADGE.get(po.status, "badge-indigo")
            # Phase 8.99c — mirrors PurchaseService._CANCELLABLE_STATUSES
            # exactly (narrowed from also including APPROVED/PARTIAL);
            # hiding the button here is UX only, cancel() itself is the
            # real enforcement (Phase 8.5 pattern).
            po.cancellable = po.status in (POStatus.DRAFT, POStatus.PENDING)
            # Phase 12 — §8b: shown-but-disabled-with-reason, not hidden,
            # when the current user can't act on this specific PO's
            # resolved policy (SupervisorRequiredMixin is only the floor).
            if po.status == POStatus.PENDING:
                _, po.required_level, _ = resolve_for_transaction(po)
                po.can_approve, po.approve_denied_reason = can_approve(request.user, po)
            else:
                po.required_level = ""
                po.can_approve = False
                po.approve_denied_reason = ""
            po.receive_items_json = json.dumps([
                {
                    "item_id": item.pk, "product_name": item.product.name,
                    "ordered_qty": item.ordered_qty, "received_qty": item.received_qty,
                    "remaining": item.ordered_qty - item.received_qty,
                }
                for item in po.items.all()
            ])
            if po.status not in (POStatus.RECEIVED, POStatus.REJECTED, POStatus.CANCELLED):
                counts["open"] += 1
            if po.status == POStatus.PENDING:
                counts["pending"] += 1
            if po.created_at.year == now.year and po.created_at.month == now.month:
                if po.status in (POStatus.RECEIVED, POStatus.PARTIAL):
                    counts["received_month"] += 1
                counts["value_month"] += po.total_cost

        context = {
            "active_nav": "purchases",
            "orders": orders,
            "counts": counts,
            "suppliers": Supplier.objects.filter(is_active=True).order_by("company_name"),
            "products": Product.objects.filter(is_active=True).order_by("name"),
            # Phase 8.98b — Asia/Dhaka "today" (not the OS clock), server-
            # computed so the Expected Delivery date input's real min=
            # attribute agrees with PurchaseOrderForm's own validation.
            "today": timezone.localdate(),
        }
        return render(request, "purchases/purchases.html", context)

    def post(self, request):
        form = PurchaseOrderForm(request.POST)
        items, item_errors = parse_line_items(request.POST.get("items_json"))

        if not form.is_valid() or item_errors:
            errors = form.errors.get_json_data()
            if item_errors:
                errors["items"] = [{"message": msg, "code": "invalid"} for msg in item_errors]
            return JsonResponse({"success": False, "errors": errors}, status=400)

        with transaction.atomic():
            po = form.save(commit=False)
            po.created_by = request.user
            po.save()
            # PurchaseOrder.total_cost has no auto-compute anywhere in
            # SCHEMA.md/PurchaseService (unlike PurchaseOrderItem.line_total,
            # which computes itself in save()) — a pre-existing doc gap, not
            # invented here; summing the items' own computed line_total is
            # the obvious, disclosed way to fill it.
            total_cost = 0
            for item in items:
                po_item = PurchaseOrderItem.objects.create(
                    purchase_order=po, product=item["product"], ordered_qty=item["quantity"],
                    unit_price=item["unit_price"], discount=item["discount"], tax=item["tax"],
                )
                total_cost += po_item.line_total
            po.total_cost = total_cost
            po.save(update_fields=["total_cost"])
            audit.log_action(
                request.user, audit.PO_CREATED, "purchases",
                affected_id=po.pk, status="success", request=request,
            )

        return JsonResponse({"success": True})


class PurchaseSubmitView(AnyStaffMixin, View):
    """No dedicated doc URL exists for this in this project's flat routing
    style, but the state machine (05_PURCHASES.md) requires SOME way to
    move DRAFT -> PENDING, and the mock's own Draft-row actions (Edit/
    Delete only) had no path to do it — a real gap in the mock, not a
    field mismatch, fixed by adding a real Submit action. Same role as
    create (any staff), matching 05_PURCHASES.md's "who creates" rule."""

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            PurchaseService.submit_for_approval(po, request.user)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        return JsonResponse({"success": True})


class PurchaseApproveView(SupervisorRequiredMixin, View):
    """05_PURCHASES.md: "Who approves | Supervisor or Admin only" — that's
    still the floor (SupervisorRequiredMixin). Phase 12's ApprovalPolicy
    engine, enforced inside PurchaseService.approve() itself, can narrow
    it further to Admin-only for a specific PO's own resolved value."""

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            PurchaseService.approve(po, request.user)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except ApprovalAuthorityError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=403)
        return JsonResponse({"success": True})


class PurchaseRejectView(SupervisorRequiredMixin, View):

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        form = ReasonForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)
        try:
            PurchaseService.reject(po, request.user, form.cleaned_data["reason"])
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except ApprovalAuthorityError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=403)
        return JsonResponse({"success": True})


class PurchaseReceiveView(AnyStaffMixin, View):
    """05_PURCHASES.md's own purchase_receive_view uses @staff_required,
    not @supervisor_required — receiving a shipment is an operational
    task, not an approval decision. receive_json: [{item_id, received_qty}]."""

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            raw_entries = json.loads(request.POST.get("receive_json") or "[]")
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "Could not read receive data."}, status=400)

        if not isinstance(raw_entries, list) or not raw_entries:
            return JsonResponse({"success": False, "error": "Enter a quantity for at least one item."}, status=400)

        receive_data = []
        for entry in raw_entries:
            try:
                item_id = int(entry.get("item_id"))
                received_qty = int(entry.get("received_qty"))
            except (TypeError, ValueError, AttributeError):
                return JsonResponse({"success": False, "error": "Invalid receive data."}, status=400)
            if received_qty > 0:
                receive_data.append({"item_id": item_id, "received_qty": received_qty})

        if not receive_data:
            return JsonResponse({"success": False, "error": "Enter a quantity greater than zero for at least one item."}, status=400)

        try:
            PurchaseService.receive_items(po, receive_data, request.user)
        except (ValueError, PurchaseOrderItem.DoesNotExist) as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        return JsonResponse({"success": True})


class PurchaseCancelView(SupervisorRequiredMixin, View):
    """Phase 8.99c: cancel is now draft/pending-only (see §13, overriding
    05_PURCHASES.md's original "any state -> CANCELLED") and requires a
    reason — same ReasonForm PurchaseRejectView already uses."""

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        form = ReasonForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)
        try:
            PurchaseService.cancel(po, request.user, form.cleaned_data["reason"])
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except ApprovalAuthorityError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=403)
        return JsonResponse({"success": True})


class PurchaseOrderPDFView(AnyStaffMixin, View):
    """Phase 8.98d — a single PO's own PDF, not one of Reports' 9 whole-
    report exports (frontend/reports.py's REPORT_BUILDERS/ReportExportView,
    untouched by this phase). Same `AnyStaffMixin` gate as
    PurchaseListCreateView.get() above, since this is just another way of
    viewing a PO already on that page — no stricter/looser access than
    seeing the record itself. Reuses reports.py's
    generate_purchase_order_pdf(), which itself reuses generate_pdf_response()'s
    own Table/TableStyle via the shared _styled_data_table() helper — no new
    PDF mechanism."""

    def get(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        return report_lib.generate_purchase_order_pdf(po, generated_by=request.user.full_name)


# ----------------------------------------------------------------- Sales
# Phase 7 — docs/06_SALES.md. SaleService (Phase 3) is the ONLY code path
# allowed to touch stock here.

class SaleListCreateView(AnyStaffMixin, View):
    """Phase 8.99b: GET lists the real SaleTransaction queryset; POST
    creates a new sale as DRAFT (mirrors PurchaseListCreateView's own
    "Saved as a draft" behavior exactly — see SaleService.create_sale())."""

    _STATUS_BADGE = {
        SaleStatus.DRAFT: "badge-indigo", SaleStatus.PENDING: "badge-warning",
        SaleStatus.COMPLETED: "badge-success", SaleStatus.REJECTED: "badge-danger",
        SaleStatus.CANCELLED: "badge-danger",
    }

    def get(self, request):
        sales = list(
            SaleTransaction.objects.select_related("created_by")
            .prefetch_related("items").order_by("-created_at")
        )
        counts = {"pending": 0, "revenue_today": 0, "transactions_today": 0, "cancelled_30d": 0, "avg_order_30d": 0}
        today = timezone.now().date()
        cutoff = today - timedelta(days=30)
        completed_30d_total, completed_30d_count = 0, 0
        for sale in sales:
            sale.item_count = sale.items.count()
            sale.is_cancelled = sale.status == SaleStatus.CANCELLED
            sale.status_badge = self._STATUS_BADGE.get(sale.status, "badge-indigo")
            sale.cancellable = sale.status in (SaleStatus.DRAFT, SaleStatus.PENDING)
            # Phase 12 — §8b: same shown-but-disabled-with-reason pattern
            # as Purchases/Adjustments, for ApprovalTxType.SALE_CANCEL.
            if sale.cancellable:
                _, sale.required_level, _ = resolve_for_transaction(sale)
                sale.can_cancel, sale.cancel_denied_reason = can_approve(request.user, sale)
            else:
                sale.required_level = ""
                sale.can_cancel = False
                sale.cancel_denied_reason = ""
            if sale.status == SaleStatus.PENDING:
                counts["pending"] += 1
            if sale.transaction_date == today:
                counts["transactions_today"] += 1
                # Phase 8.99b: "revenue" now means realized revenue —
                # only a COMPLETED sale has actually moved stock/money.
                # Counting draft/pending/rejected sales here would
                # overstate today's revenue with sales that may never
                # actually go through.
                if sale.status == SaleStatus.COMPLETED:
                    counts["revenue_today"] += sale.total_amount
            if sale.is_cancelled and sale.transaction_date >= cutoff:
                counts["cancelled_30d"] += 1
            if sale.status == SaleStatus.COMPLETED and sale.transaction_date >= cutoff:
                completed_30d_total += sale.total_amount
                completed_30d_count += 1
        if completed_30d_count:
            counts["avg_order_30d"] = completed_30d_total / completed_30d_count
        context = {
            "active_nav": "sales",
            "sales": sales,
            "counts": counts,
            "products": Product.objects.filter(is_active=True).order_by("name"),
        }
        return render(request, "sales/sales.html", context)

    def post(self, request):
        form = SaleTransactionForm(request.POST)
        # Phase 8.99b: no stock check happens here anymore — creating a
        # sale no longer touches InventoryService at all (draft, per
        # SaleService.create_sale()'s own docstring). Availability is
        # re-checked for real at approve_sale() time instead.
        items, item_errors = parse_line_items(request.POST.get("items_json"), min_quantity=1)

        if not form.is_valid() or item_errors:
            errors = form.errors.get_json_data()
            if item_errors:
                errors["items"] = [{"message": msg, "code": "invalid"} for msg in item_errors]
            return JsonResponse({"success": False, "errors": errors}, status=400)

        sale_data = {
            "customer_name": form.cleaned_data["customer_name"],
            "notes": form.cleaned_data["notes"],
        }
        items_data = [
            {
                "product_id": item["product"].pk, "quantity": item["quantity"],
                "unit_price": item["unit_price"], "discount": item["discount"], "tax": item["tax"],
            }
            for item in items
        ]

        try:
            SaleService.create_sale(sale_data, items_data, request.user)
        except ValueError as e:
            return JsonResponse(
                {"success": False, "errors": {"items": [{"message": str(e), "code": "invalid"}]}}, status=400,
            )

        return JsonResponse({"success": True})


class SaleSubmitView(AnyStaffMixin, View):
    """Phase 8.99b — mirrors PurchaseSubmitView exactly: same role as
    create (any staff), moves DRAFT -> PENDING."""

    def post(self, request, pk):
        sale = get_object_or_404(SaleTransaction, pk=pk)
        try:
            SaleService.submit_for_approval(sale, request.user)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        return JsonResponse({"success": True})


class SaleApproveView(SupervisorRequiredMixin, View):
    """Phase 8.99b — mirrors PurchaseApproveView: Supervisor or Admin
    only (the same confirmed hierarchy, Phase 7). No creator≠approver
    restriction, deliberately matching how Purchases already works —
    disclosed, not silent, see docs/project_memory.md §13."""

    def post(self, request, pk):
        sale = get_object_or_404(SaleTransaction, pk=pk)
        try:
            SaleService.approve_sale(sale, request.user)
        except InsufficientStockError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except ApprovalAuthorityError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=403)
        return JsonResponse({"success": True})


class SaleRejectView(SupervisorRequiredMixin, View):
    """Phase 8.99b — mirrors PurchaseRejectView, same ReasonForm."""

    def post(self, request, pk):
        sale = get_object_or_404(SaleTransaction, pk=pk)
        form = ReasonForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)
        try:
            SaleService.reject_sale(sale, request.user, form.cleaned_data["reason"])
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except ApprovalAuthorityError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=403)
        return JsonResponse({"success": True})


class SaleCancelView(SupervisorRequiredMixin, View):
    """06_SALES.md's own sale_cancel_view uses @supervisor_required.
    Phase 8.99b: SaleService.cancel_sale() refuses anything past DRAFT/
    PENDING — a completed sale can no longer reach this at all, server-
    side, regardless of what the UI shows. Phase 8.99c: now requires a
    reason — same ReasonForm SaleRejectView already uses."""

    def post(self, request, pk):
        sale = get_object_or_404(SaleTransaction, pk=pk)
        form = ReasonForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)
        try:
            SaleService.cancel_sale(sale, request.user, form.cleaned_data["reason"])
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except ApprovalAuthorityError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=403)
        return JsonResponse({"success": True})


class SaleTransactionPDFView(AnyStaffMixin, View):
    """Phase 8.98d — same treatment as PurchaseOrderPDFView above: a
    single sale's own PDF, same `AnyStaffMixin` gate as
    SaleListCreateView.get(), reuses reports.py's
    generate_sale_transaction_pdf()."""

    def get(self, request, pk):
        sale = get_object_or_404(SaleTransaction, pk=pk)
        # BUG-65 (docs/bugsfound.md) — SALE_INVOICE_PRINTED was defined
        # but never fired anywhere; this is the one real trigger.
        audit.log_action(
            request.user, audit.SALE_INVOICE_PRINTED, "sales",
            affected_id=sale.pk, status="success", request=request,
        )
        return report_lib.generate_sale_transaction_pdf(sale, generated_by=request.user.full_name)


# ------------------------------------------------------------- Inventory
# Phase 8.9 — docs/07_INVENTORY.md's inventory_list_view. GET-only, no
# create/edit form anywhere: InventoryRecord rows only ever come into
# existence via InventoryService.initialize_for_product() (Phase 5.5) and
# only ever mutate via InventoryService.increase_stock()/decrease_stock()
# (Phase 3), both called exclusively from Purchase/Sale/Adjustment's
# service-layer methods — never from this view or any form. `status` is
# read straight off InventoryRecord, not recomputed here: InventoryService
# already calls record.update_status() and saves before any view ever
# reads it, so re-deriving it in the view would just be a second,
# potentially-drifting copy of the same logic. 07_INVENTORY.md's own
# reference view uses `@staff_required`, which in this project's RBAC
# (frontend/decorators.py) means "any authenticated role" (admin,
# supervisor, and staff are all listed) — the same as AnyStaffMixin,
# used here for consistency with every other real list view.

_INVENTORY_STATUS_BADGE = {
    InventoryStatus.AVAILABLE: "badge-success",
    InventoryStatus.LOW_STOCK: "badge-warning",
    InventoryStatus.OUT_OF_STOCK: "badge-danger",
}


class InventoryListView(AnyStaffMixin, View):

    def get(self, request):
        records = list(
            InventoryRecord.objects.select_related("product", "product__category", "product__supplier")
            .order_by("product__name")
        )
        counts = {"total_value": 0, "total_skus": 0, "low_stock": 0, "out_of_stock": 0}
        for record in records:
            record.status_badge = _INVENTORY_STATUS_BADGE.get(record.status, "badge-indigo")
            latest_movement = record.product.movements.order_by("-created_at").first()
            record.last_movement_at = latest_movement.created_at if latest_movement else None

            counts["total_skus"] += 1
            counts["total_value"] += record.total_value
            if record.status == InventoryStatus.LOW_STOCK:
                counts["low_stock"] += 1
            elif record.status == InventoryStatus.OUT_OF_STOCK:
                counts["out_of_stock"] += 1

        # BUG-65 (docs/bugsfound.md) — INVENTORY_VIEWED was defined in
        # 13_AUDIT.md's constant list but never fired anywhere; this is
        # that page. Same "view = auditable" precedent ReportsView's own
        # REPORT_GENERATED calls already establish in this codebase.
        audit.log_action(request.user, audit.INVENTORY_VIEWED, "inventory", status="success", request=request)

        context = {"active_nav": "inventory", "records": records, "counts": counts}
        return render(request, "inventory/inventory.html", context)


class MovementHistoryListView(AnyStaffMixin, View):
    """Phase 8.98 — the "Movement history" button on Inventory used to do
    nothing; this is the real page it now opens. `InventoryMovement` is
    the immutable stock ledger (Phase 3, `save()`/`delete()` raise on any
    mutation attempt per BUG-20) — nothing new is created here, this only
    ever reads what already exists.

    Phase 8.99d — every filter (date_from/date_to, product, movement_type,
    and search) is now server-side, all applied via
    `frontend/reports.py`'s `filter_movements()` — the exact same function
    `MovementHistoryExportView` calls, so the CSV/PDF export can never
    silently disagree with what's on screen again. Previously only date
    range was server-side (via a *different* date comparison than the
    export used — `created_at__date__gte` here vs. `build_movement_report()`'s
    own `_date_bounds()`-based range — a latent mismatch this phase closed
    by sharing one function) and search/type were client-side
    (`table-filter.js`), which meant an export honored the date range but
    silently ignored type, and could never reflect what was typed into
    search at all. Real `Paginator`-backed pagination (page size 50) on
    top, since the ledger is append-only and grows forever — narrowing
    happens in the query, not by hiding rows client-side.

    The `?product=<id>` deep-link from Inventory's per-row links now
    lands in the same filter form as every other field (a real `<select>`,
    pre-selected) rather than being a separate hidden-input-only
    mechanism.
    """

    PAGE_SIZE = 50

    def get(self, request):
        movements = InventoryMovement.objects.select_related("product", "performed_by").order_by("-created_at")
        movements = report_lib.filter_movements(request, base_qs=movements)

        date_from = request.GET.get("date_from", "")
        date_to = request.GET.get("date_to", "")
        product_id = request.GET.get("product", "")
        movement_type = request.GET.get("movement_type", "")
        search = request.GET.get("q", "")

        paginator = Paginator(movements, self.PAGE_SIZE)
        page = paginator.get_page(request.GET.get("page"))

        for movement in page.object_list:
            movement.reference_label = f"{movement.reference_type} #{movement.reference_id}"

        # Preserves every filter param across pagination links and feeds
        # both export buttons, so exporting honors exactly what's on screen.
        querystring = request.GET.copy()
        querystring.pop("page", None)

        context = {
            "active_nav": "inventory",
            "page": page,
            "total_count": paginator.count,
            "date_from": date_from,
            "date_to": date_to,
            "product_id": product_id,
            "movement_type": movement_type,
            "search": search,
            "filtered_product": Product.objects.filter(pk=product_id).first() if product_id else None,
            "products": Product.objects.order_by("name"),
            # RETURN dropped (Phase 8.99d) — confirmed via grep that no
            # code path anywhere ever creates a MovementType.RETURN
            # movement; a filter value that can never match is left on
            # the model (SCHEMA.md's) but no longer offered as a choice.
            "movement_types": [c for c in MovementType.choices if c[0] != MovementType.RETURN],
            "export_querystring": querystring.urlencode(),
        }
        return render(request, "inventory/movement_history.html", context)


class MovementHistoryExportView(AnyStaffMixin, View):
    """CSV/PDF export for Movement History — reuses `frontend/reports.py`'s
    `build_movement_report()` (which itself now calls the shared
    `filter_movements()`) and `generate_csv_response()`/
    `generate_pdf_response()` verbatim, just gated with `AnyStaffMixin`
    here instead of Reports' `SupervisorRequiredMixin`, matching this
    page's own access level — not a new export mechanism, and no second
    PDF library (Phase 8.99d, mirrors Phase 8.98d's per-record PDFs).
    `?format=csv` (default, unchanged link) or `?format=pdf`; both take
    the exact same querystring as the page, so what's exported is
    precisely what was filtered."""

    def get(self, request):
        title, headers, rows = report_lib.build_movement_report(request)

        if request.GET.get("format") == "pdf":
            filters_summary = []
            date_from, date_to = request.GET.get("date_from"), request.GET.get("date_to")
            if date_from or date_to:
                filters_summary.append(f"Date: {date_from or 'any'} to {date_to or 'any'}")
            product_id = request.GET.get("product")
            if product_id:
                product = Product.objects.filter(pk=product_id).first()
                filters_summary.append(f"Product: {product.name if product else product_id}")
            movement_type = request.GET.get("movement_type")
            if movement_type in MovementType.values:
                filters_summary.append(f"Type: {MovementType(movement_type).label}")
            search = request.GET.get("q", "").strip()
            if search:
                filters_summary.append(f"Search: \"{search}\"")
            if not filters_summary:
                filters_summary.append("None — full ledger")
            return report_lib.generate_pdf_response(
                title, headers, rows, "movement_history.pdf", filters_summary=filters_summary,
                generated_by=request.user.full_name,
            )

        return report_lib.generate_csv_response(headers, rows, "movement_history.csv")


# --------------------------------------------------------- Adjustments
# Phase 7 — no dedicated doc (project_memory.md §12/§17); built from
# SCHEMA.md's InventoryAdjustment + the existing adjustments.html mock,
# mirroring Purchase/Adjustment's approve/reject shape. AdjustmentService
# (Phase 3) is the ONLY code path allowed to touch stock here.

class AdjustmentListCreateView(AnyStaffMixin, View):

    _STATUS_BADGE = {
        AdjustmentStatus.PENDING: "badge-warning", AdjustmentStatus.APPROVED: "badge-success",
        AdjustmentStatus.REJECTED: "badge-danger",
    }

    def get(self, request):
        adjustments = list(
            InventoryAdjustment.objects.select_related("product", "requested_by").order_by("-created_at")
        )
        counts = {"pending": 0, "approved_month": 0, "rejected_month": 0, "total_30d": 0}
        now = timezone.now()
        cutoff = now - timedelta(days=30)
        for adjustment in adjustments:
            adjustment.status_badge = self._STATUS_BADGE.get(adjustment.status, "badge-indigo")
            # Phase 12 — §8b: the approve control is shown-but-disabled
            # with a reason when the current user isn't the one who can
            # act on it, never hidden. Only meaningful for PENDING rows —
            # everything else has no approve action to gate at all.
            if adjustment.status == AdjustmentStatus.PENDING:
                _, adjustment.required_level, _ = resolve_for_transaction(adjustment)
                adjustment.can_approve, adjustment.approve_denied_reason = can_approve(request.user, adjustment)
            else:
                adjustment.required_level = ""
                adjustment.can_approve = False
                adjustment.approve_denied_reason = ""
            if adjustment.status == AdjustmentStatus.PENDING:
                counts["pending"] += 1
            if adjustment.created_at.year == now.year and adjustment.created_at.month == now.month:
                if adjustment.status == AdjustmentStatus.APPROVED:
                    counts["approved_month"] += 1
                elif adjustment.status == AdjustmentStatus.REJECTED:
                    counts["rejected_month"] += 1
            if adjustment.created_at >= cutoff:
                counts["total_30d"] += 1
        context = {
            "active_nav": "adjustments",
            "adjustments": adjustments,
            "counts": counts,
            # Not filtered to is_active — see AdjustmentForm's docstring.
            "products": Product.objects.order_by("name"),
            "reason_codes": AdjustmentReason.choices,
        }
        return render(request, "adjustments/adjustments.html", context)

    def post(self, request):
        form = AdjustmentForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        # Phase 12 — AdjustmentService.create() now owns the whole
        # request-time decision (AUTO posts immediately, SUPERVISOR/ADMIN
        # saves PENDING and notifies the right audience) — moved out of
        # this view so the service layer is the boundary that must hold
        # regardless of caller, matching approve()'s own gate.
        adjustment = form.save(commit=False)
        try:
            AdjustmentService.create(adjustment, request.user)
        except InsufficientStockError as e:
            # Only reachable for an AUTO-outcome DECREASE adjustment
            # against insufficient stock — a PENDING one never touches
            # stock at creation time.
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        return JsonResponse({"success": True})


class AdjustmentApproveView(SupervisorRequiredMixin, View):
    """SupervisorRequiredMixin is the floor (any supervisor/admin may
    reach this URL) — AdjustmentService.approve()'s own can_approve()
    call (Phase 12) is the finer-grained gate that can still refuse a
    genuine supervisor when the resolved policy requires ADMIN."""

    def post(self, request, pk):
        adjustment = get_object_or_404(InventoryAdjustment, pk=pk)
        try:
            AdjustmentService.approve(adjustment, request.user)
        except (ValueError, InsufficientStockError) as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except ApprovalAuthorityError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=403)
        return JsonResponse({"success": True})


class AdjustmentRejectView(SupervisorRequiredMixin, View):

    def post(self, request, pk):
        adjustment = get_object_or_404(InventoryAdjustment, pk=pk)
        form = ReasonForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)
        try:
            AdjustmentService.reject(adjustment, request.user, form.cleaned_data["reason"])
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except ApprovalAuthorityError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=403)
        return JsonResponse({"success": True})


class AdjustmentPDFView(AnyStaffMixin, View):
    """Phase 13 — new: no per-adjustment PDF existed before this (only
    the whole-Adjustments report table did). Same treatment as
    PurchaseOrderPDFView/SaleTransactionPDFView above: AnyStaffMixin,
    since this is just another way of viewing a record already visible
    on the Adjustments list page, not a stricter/looser access level."""

    def get(self, request, pk):
        adjustment = get_object_or_404(InventoryAdjustment, pk=pk)
        return report_lib.generate_adjustment_pdf(adjustment, generated_by=request.user.full_name)

# Phase 8.99j — closes BUG-43: both views had zero auth requirement at
# all (reachable by anyone, logged in or not), found in Phase 8.97's
# audit and deliberately left unfixed for its own scoped phase. BUG-43's
# own text suggested AnyStaffMixin (matching BUG-42's fix on the
# Dashboard) — this phase's actual, more specific requirement ("staff
# can't see the AI models") is narrower, so SupervisorRequiredMixin is
# used instead, a disclosed deviation from BUG-43's own suggestion, not
# an oversight. Converted from bare function views to CBVs to match this
# app's dominant convention (every other real, RBAC-gated view in this
# file is a class with a mixin, not a decorated function).

class DemandForecastingView(SupervisorRequiredMixin, View):
    """Phase 11 — real DemandForecast data (was a static TREND_DATA/table
    mock). SupervisorRequiredMixin is unchanged from Phase 8.99j/BUG-43 —
    not re-added, not modified; both GET and POST inherit the same gate.

    DemandForecast rows accumulate real history by design (REQ 9.9 needs
    past forecasts kept around to compare against actual_demand once
    backfilled) — run_full_forecast() never deletes old rows, matching
    the doc's own reference code (a plain .create(), no update_or_create;
    unlike InventoryClassification, DemandForecast has no OneToOneField
    forcing one-row-per-product). Repeated "Run forecast now" clicks are
    therefore expected to accumulate rows over time — this view's own GET
    query keeps the *display* sane by showing only the most recent batch
    (deduped by (product, period, period_start), keyed off created_at),
    not by changing what gets written. That dedup now lives in
    frontend.forecasting.latest_forecast_batch() (extracted so the
    Dashboard's AI Insights widget, REQ 11.9, shares the exact same
    definition of "current forecast" rather than risking a second,
    divergent one)."""

    _PERIOD_LABEL = {ForecastPeriod.WEEKLY: 'weekly', ForecastPeriod.MONTHLY: 'monthly'}

    def _build_chart_data(self, forecasts, period_choice):
        buckets = {}
        for f in forecasts:
            if f.forecast_period != period_choice:
                continue
            buckets.setdefault(f.period_start, {'demand': 0.0, 'reorder': 0})
            buckets[f.period_start]['demand'] += float(f.forecasted_demand)
            buckets[f.period_start]['reorder'] += f.recommended_reorder_qty
        keys = sorted(buckets.keys())[:4]
        return {
            'labels': [k.strftime('%d %b') for k in keys],
            'demand': [round(buckets[k]['demand'], 1) for k in keys],
            'reorder': [buckets[k]['reorder'] for k in keys],
        }

    def get(self, request):
        forecasts, last_run = latest_forecast_batch()
        stock_by_product = dict(InventoryRecord.objects.values_list('product_id', 'current_stock'))

        # One table row per (product, period-type): the nearest upcoming
        # forecast only — matches the page's own shape (a row is "this
        # product's next weekly/monthly forecast", not every future step).
        nearest = {}
        for f in forecasts:
            key = (f.product_id, f.forecast_period)
            if key not in nearest or f.period_start < nearest[key].period_start:
                nearest[key] = f
        table_rows = sorted(nearest.values(), key=lambda f: (f.product.name, f.forecast_period))
        for f in table_rows:
            f.search_blob = f"{f.product.name} {f.product.sku}".lower()
            f.period_type = self._PERIOD_LABEL[f.forecast_period]
            f.current_stock_display = stock_by_product.get(f.product_id, 0)
            f.confidence_pct = round(float(f.confidence_score) * 100)

        flagged_count = sum(1 for f in table_rows if f.recommended_reorder_qty > 0)
        confidences = [float(f.confidence_score) for f in table_rows]
        avg_confidence_pct = round(sum(confidences) / len(confidences) * 100) if confidences else 0

        reorder_priorities = sorted(
            (f for f in table_rows if f.recommended_reorder_qty > 0),
            key=lambda f: -f.recommended_reorder_qty,
        )[:4]

        context = {
            "active_nav": "forecasting",
            "forecasts": table_rows,
            "categories": Category.objects.filter(is_active=True).order_by("name"),
            "products_forecasted": len({f.product_id for f in table_rows}),
            "avg_confidence_pct": avg_confidence_pct,
            "flagged_count": flagged_count,
            "last_run": last_run,
            "reorder_priorities": reorder_priorities,
            "chart_data": {
                "weekly": self._build_chart_data(forecasts, ForecastPeriod.WEEKLY),
                "monthly": self._build_chart_data(forecasts, ForecastPeriod.MONTHLY),
            },
        }
        return render(request, "intelligence/forecasting.html", context)

    def post(self, request):
        """Manual "Run forecast now" — synchronous (no Celery). Backfills
        elapsed forecasts first, then retrains both period models with
        the latest data and generates fresh forecasts for every active
        product. The doc's slow/dead-equivalent here is notify_supervisors
        for 'ai_replenish' — documented as living inside the same un-built
        Celery task; fired from this view instead, per replenish_alerts
        run_full_forecast() returns (that function stays notify-free,
        matching frontend/classification.py's run_full_classification())."""
        backfilled = backfill_actual_demand()
        audit.log_action(
            request.user, audit.AI_ACTUAL_DEMAND_BACKFILLED, "ai_forecasting",
            status="success", details={"forecasts_updated": backfilled},
        )

        try:
            result = run_full_forecast()
        except Exception as e:
            audit.log_action(
                request.user, audit.AI_MODEL_RETRAIN_FAILED, "ai_forecasting",
                status="failure", details={"error": str(e)},
            )
            return JsonResponse({"success": False, "error": "Forecast run failed."}, status=500)

        audit.log_action(
            request.user, audit.AI_MODEL_RETRAINED, "ai_forecasting",
            status="success", details={"mae": result["mae"]},
        )
        audit.log_action(
            request.user, audit.AI_FORECASTS_GENERATED, "ai_forecasting",
            status="success", details={
                "products_considered": result["products_considered"],
                "forecasts_created": result["forecasts_created"],
            },
        )

        for alert in result["replenish_alerts"]:
            notify_supervisors(
                NotificationType.AI_REPLENISH, f'AI: Replenish {alert["product"].name}',
                f'Forecasted demand ({alert["forecasted_demand"]} units) exceeds current '
                f'stock ({alert["current_stock"]} units). Recommended order: '
                f'{alert["recommended_qty"]} units.',
                link="/ai/forecasting/",
            )

        return JsonResponse({
            "success": True,
            "forecasts_created": result["forecasts_created"],
            "replenish_alerts": len(result["replenish_alerts"]),
        })


class SlowMovingDeadStockView(SupervisorRequiredMixin, View):
    """Phase 10 — real InventoryClassification data (was a static mock
    table). SupervisorRequiredMixin is unchanged from Phase 8.99j/BUG-43 —
    not re-added, not modified; both GET and POST inherit the same gate
    from the class, so the manual "Run classification now" action is
    guarded identically to the page itself."""

    _BADGE = {
        StockClassification.FAST: "badge-success",
        StockClassification.SLOW: "badge-warning",
        StockClassification.DEAD: "badge-danger",
        # Prompt 2 (2026-08-24) — deliberately not badge-indigo (the
        # generic/AI-accent fallback): insufficient_data isn't a problem
        # state, so it gets its own neutral/muted badge, not one that
        # reads as "some other kind of alert."
        StockClassification.INSUFFICIENT_DATA: "badge-neutral",
    }

    def get(self, request):
        settings_obj = SystemSettings.get_settings()
        classifications = list(
            InventoryClassification.objects.select_related("product", "product__category")
            .order_by("product__name")
        )
        counts = {
            StockClassification.FAST: 0,
            StockClassification.SLOW: 0,
            StockClassification.DEAD: 0,
            StockClassification.INSUFFICIENT_DATA: 0,
        }
        for c in classifications:
            counts[c.classification] = counts.get(c.classification, 0) + 1
            c.badge = self._BADGE.get(c.classification, "badge-neutral")
            c.search_blob = f"{c.product.name} {c.product.sku}".lower()
            if c.last_sold_date is None:
                c.last_sold_label = "Never sold"
            elif c.days_since_last_sale == 0:
                c.last_sold_label = "Today"
            elif c.days_since_last_sale == 1:
                c.last_sold_label = "1 day ago"
            else:
                c.last_sold_label = f"{c.days_since_last_sale} days ago"

        # Prompt 2 — days_since_last_sale is now genuinely nullable (BUG
        # fix, docs/bugsfound.md); the DEAD/SLOW branches below only ever
        # see rows with a real integer here (INSUFFICIENT_DATA rows have
        # no meaningful days_since_last_sale to rank by and are excluded
        # from both watch lists — they're not a problem state to flag).
        dead_watch = sorted(
            (c for c in classifications if c.classification == StockClassification.DEAD),
            key=lambda c: -(c.days_since_last_sale or 0),
        )[:2]
        slow_watch = sorted(
            (c for c in classifications if c.classification == StockClassification.SLOW),
            key=lambda c: -(c.days_since_last_sale or 0),
        )[:1]
        for c in slow_watch:
            c.days_to_dead = max(settings_obj.dead_stock_threshold_days - (c.days_since_last_sale or 0), 0)

        context = {
            "active_nav": "slow-moving",
            "classifications": classifications,
            "counts": counts,
            "total_flagged": counts[StockClassification.SLOW] + counts[StockClassification.DEAD],
            "categories": Category.objects.filter(is_active=True).order_by("name"),
            "dead_watch": dead_watch,
            "slow_watch": slow_watch,
            "slow_threshold": settings_obj.slow_moving_threshold_days,
            "dead_threshold": settings_obj.dead_stock_threshold_days,
            "slow_index_threshold": settings_obj.slow_index_threshold,
            "dead_index_threshold": settings_obj.dead_index_threshold,
            "min_observation_days": settings_obj.min_observation_days,
            "min_sale_events": settings_obj.min_sale_events,
            "target_days_of_cover": settings_obj.target_days_of_cover,
            "extreme_coverage_days": settings_obj.extreme_coverage_days,
            "chart_data": {
                "fast": counts[StockClassification.FAST],
                "slow": counts[StockClassification.SLOW],
                "dead": counts[StockClassification.DEAD],
                "insufficient_data": counts[StockClassification.INSUFFICIENT_DATA],
            },
        }
        return render(request, "intelligence/slow_moving.html", context)

    def post(self, request):
        """Manual "Run classification now" — synchronous (no Celery, see
        docs/project_memory.md §13). The doc hosts the slow/dead
        supervisor notification inside a Celery task this project isn't
        building; fired here instead, from the one real trigger that
        exists, so the REQ-covered behavior isn't lost to an un-built
        host."""
        try:
            results = run_full_classification()
        except Exception as e:
            audit.log_action(
                request.user, audit.AI_CLASSIFICATION_FAILED, "ai_classification",
                status="failure", details={"error": str(e)},
            )
            return JsonResponse({"success": False, "error": "Classification run failed."}, status=500)

        audit.log_action(
            request.user, audit.AI_CLASSIFICATION_RUN, "ai_classification",
            status="success", details=results,
        )

        slow_count = results.get(StockClassification.SLOW, 0)
        dead_count = results.get(StockClassification.DEAD, 0)
        if slow_count:
            notify_supervisors(
                NotificationType.AI_SLOW_STOCK, f"AI Alert: {slow_count} Slow-Moving Products",
                f"{slow_count} products identified as slow-moving. Review recommended.",
                link="/ai/slow-moving/",
            )
        if dead_count:
            notify_supervisors(
                NotificationType.AI_DEAD_STOCK, f"AI Alert: {dead_count} Dead Stock Products",
                f"{dead_count} products have had no sales activity. Immediate action recommended.",
                link="/ai/slow-moving/",
            )

        return JsonResponse({"success": True, "results": results})

# ------------------------------------------------------------------ Reports
# Phase 8 — docs/10_REPORTS.md: "All report access is Supervisor+ only and
# must be audit-logged." SupervisorRequiredMixin (Phase 7, confirmed there
# to mean Admin-or-Supervisor via the RBAC hierarchy, not an exact-role
# match) is the same mixin that guards Purchase/Adjustment approve/reject.
# frontend/reports.py holds the 9 report builders + PDF/CSV generators —
# kept out of this file the same way frontend/audit.py and
# frontend/notifications.py already are.

class ReportsView(SupervisorRequiredMixin, View):
    """GET renders the reports page itself: 9 report cards (each linking
    straight to ReportExportView for PDF/CSV — this page has no per-card
    HTML preview), plus the two live preview panels the Phase 3.6 mock
    already had (Sales, Low Stock) with real data. Viewing either preview
    counts as 10_REPORTS.md's "REPORT_GENERATED | Any report viewed in
    browser" — logged once per panel on this GET, not once per report
    type (the other 7 only ever get logged if actually exported, since
    they're never rendered to the browser)."""

    def get(self, request):
        # Phase 13 Task 4 — build_sales_report()'s per-transaction rows
        # are no longer used on this page at all (the panel dropped its
        # detailed table for an aggregate/chart shape, matching the other
        # report panels); build_sales_report() itself is untouched and
        # still backs the Sales Report's CSV export.
        sales_qs = SaleTransaction.objects.filter(status=SaleStatus.COMPLETED)
        sales_summary = report_lib.sales_report_summary(sales_qs)
        sales_breakdown = report_lib.sales_status_breakdown(request)
        sales_chart_data = report_lib.sales_daily_revenue(request)
        low_stock_title, low_stock_headers, low_stock_rows = report_lib.build_low_stock_report(request)

        audit.log_action(request.user, audit.REPORT_GENERATED, "reports", status="success",
                          details={"report": "sales"}, request=request)
        audit.log_action(request.user, audit.REPORT_GENERATED, "reports", status="success",
                          details={"report": "low_stock"}, request=request)

        context = {
            "active_nav": "reports",
            "categories": Category.objects.filter(is_active=True).order_by("name"),
            "sales_summary": sales_summary,
            "sales_breakdown": sales_breakdown,
            "sales_chart_data": sales_chart_data,
            "low_stock_headers": low_stock_headers,
            "low_stock_rows": low_stock_rows,
        }
        return render(request, "reports/reports.html", context)


class ReportExportView(SupervisorRequiredMixin, View):
    """GET .../reports/export/<report_type>/?format=pdf|csv — a plain GET
    download link, not a fetch()-based endpoint (10_REPORTS.md's own
    format param is a query string on a GET, not a POST body)."""

    def get(self, request, report_type):
        builder = report_lib.REPORT_BUILDERS.get(report_type)
        if builder is None:
            return JsonResponse({"success": False, "error": "Unknown report type."}, status=404)

        export_format = request.GET.get("format")
        filename_base = report_type.replace("-", "_")

        # Phase 13 Task 4 — the Sales Report's PDF is now the same
        # aggregate/summary shape its on-page panel shows, not
        # build_sales_report()'s per-transaction rows; CSV is untouched
        # (still the detailed export), so this only short-circuits the
        # pdf branch, before build_sales_report() ever runs.
        if report_type == "sales" and export_format == "pdf":
            audit.log_action(request.user, audit.REPORT_EXPORTED_PDF, "reports", status="success",
                              details={"report": report_type}, request=request)
            return report_lib.generate_sales_summary_pdf(request)

        title, headers, rows = builder(request)

        if export_format == "pdf":
            audit.log_action(request.user, audit.REPORT_EXPORTED_PDF, "reports", status="success",
                              details={"report": report_type}, request=request)
            return report_lib.generate_pdf_response(
                title, headers, rows, f"{filename_base}_report.pdf", generated_by=request.user.full_name,
            )
        elif export_format == "csv":
            audit.log_action(request.user, audit.REPORT_EXPORTED_CSV, "reports", status="success",
                              details={"report": report_type}, request=request)
            return report_lib.generate_csv_response(headers, rows, f"{filename_base}_report.csv")

        return JsonResponse({"success": False, "error": "format must be 'pdf' or 'csv'."}, status=400)

# --------------------------------------------------------- Notifications
# Phase 8 — docs/11_NOTIFICATIONS.md's list/mark-read/mark-all-read/
# unread-count views. notify_user()/notify_supervisors() (Phase 3.5,
# frontend/notifications.py) already write the Notification rows this
# phase only ever reads/updates is_read on — never creates one directly,
# matching that module's own "Never create Notification objects directly
# in other modules" rule. Any authenticated user sees their own
# notifications (no role gate — 11_NOTIFICATIONS.md's views use
# @login_required only, not a role-restricted decorator).

# icon id + inline tint style per NotificationType, matching the exact
# icon/color choices the Phase 3.6 mock already used per notification
# type (see notifications.html's original mock rows) — kept as a style
# string (not new CSS classes) since every value here already exists as
# a design-token CSS var, just applied inline like the mock did.
_NOTIF_ICON = {
    NotificationType.LOW_STOCK: ("icon-alert-triangle", "background:var(--c-warning-tint); color:#9C6B12;"),
    NotificationType.OUT_OF_STOCK: ("icon-alert-circle", "background:var(--c-danger-tint); color:var(--c-danger);"),
    NotificationType.PO_PENDING: ("icon-clock", "background:var(--c-warning-tint); color:#9C6B12;"),
    NotificationType.PO_APPROVED: ("icon-check-circle", "background:var(--c-success-tint); color:var(--c-success);"),
    NotificationType.PO_REJECTED: ("icon-alert-circle", "background:var(--c-danger-tint); color:var(--c-danger);"),
    NotificationType.ADJ_PENDING: ("icon-clock", "background:var(--c-warning-tint); color:#9C6B12;"),
    NotificationType.ADJ_APPROVED: ("icon-check-circle", "background:var(--c-success-tint); color:var(--c-success);"),
    NotificationType.AI_REPLENISH: ("icon-cpu", "background:var(--c-amber-tint); color:#9C6B12;"),
    NotificationType.AI_SLOW_STOCK: ("icon-trending-down", "background:var(--c-danger-tint); color:var(--c-danger);"),
    NotificationType.AI_DEAD_STOCK: ("icon-trending-down", "background:var(--c-danger-tint); color:var(--c-danger);"),
    NotificationType.PASSWORD_CHANGED: ("icon-shield", "background:var(--c-slate-100); color:var(--c-slate);"),
    NotificationType.SALE_COMPLETED: ("icon-receipt", "background:var(--c-success-tint); color:var(--c-success);"),
}
_NOTIF_ICON_DEFAULT = ("icon-bell", "background:var(--c-slate-100); color:var(--c-slate);")


class NotificationListView(LoginRequiredMixin, View):

    def get(self, request):
        notifications = list(
            Notification.objects.filter(recipient=request.user).order_by("-created_at")[:100]
        )
        for notif in notifications:
            notif.icon_name, notif.icon_style = _NOTIF_ICON.get(notif.type, _NOTIF_ICON_DEFAULT)
        unread_count = sum(1 for n in notifications if not n.is_read)
        context = {
            "active_nav": "notifications",
            "notifications": notifications,
            "unread_count": unread_count,
        }
        return render(request, "notifications/notifications.html", context)


class NotificationMarkReadView(LoginRequiredMixin, View):

    def post(self, request, pk):
        updated = Notification.objects.filter(pk=pk, recipient=request.user).update(is_read=True)
        if not updated:
            return JsonResponse({"success": False, "error": "Notification not found."}, status=404)
        return JsonResponse({"success": True})


class NotificationMarkAllReadView(LoginRequiredMixin, View):

    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return JsonResponse({"success": True})


class NotificationUnreadCountView(LoginRequiredMixin, View):

    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return JsonResponse({"unread_count": count})

# ------------------------------------------------------------- Users & Roles
# Phase 8 — no dedicated doc (project_memory.md §12/§17); built from
# SCHEMA.md's User model + API_CONTRACTS.md's User Management Endpoints
# table (list/create/deactivate/reactivate, all Admin-only) plus the
# existing users.html mock. See UserForm's own docstring (frontend/forms.py)
# for the one disclosed field-list deviation: a required password field,
# which the mock explicitly didn't have.

_ROLE_BADGE = {UserRole.ADMIN: "badge-indigo", UserRole.SUPERVISOR: "badge-warning", UserRole.STAFF: "badge-success"}


def _user_ids_with_history():
    """Phase 8.99f-2 — every User FK in this project is either PROTECT
    (PurchaseOrder.created_by/approved_by/cancelled_by, SaleTransaction.
    created_by/approved_by/cancelled_by, InventoryMovement.performed_by,
    InventoryAdjustment.requested_by/approved_by) or SET_NULL
    (AuditLog.user) — never CASCADE except Notification.recipient (a
    user's own in-app notifications, harmless to lose). Hard-deleting a
    user referenced by any PROTECT FK raises ProtectedError (a 500, not a
    clean refusal); hard-deleting one referenced only via AuditLog.user
    would silently null out who performed real, audited actions. Neither
    is acceptable, so UserDeleteView only ever allows deleting a user
    who appears in none of these — one shared computation (10 queries,
    each a cheap `.values_list(...flat=True)`), used both to decide which
    rows get a real "Delete" pill (UserListCreateView.get()) and to
    enforce the same rule server-side (UserDeleteView) — one source of
    truth, not two, matching this phase's own "server check is the real
    gate, hiding is UX" convention (Phase 8.5)."""
    ids = set()
    ids |= set(PurchaseOrder.objects.values_list("created_by_id", flat=True))
    ids |= set(PurchaseOrder.objects.exclude(approved_by=None).values_list("approved_by_id", flat=True))
    ids |= set(PurchaseOrder.objects.exclude(cancelled_by=None).values_list("cancelled_by_id", flat=True))
    ids |= set(SaleTransaction.objects.values_list("created_by_id", flat=True))
    ids |= set(SaleTransaction.objects.exclude(approved_by=None).values_list("approved_by_id", flat=True))
    ids |= set(SaleTransaction.objects.exclude(cancelled_by=None).values_list("cancelled_by_id", flat=True))
    ids |= set(InventoryMovement.objects.values_list("performed_by_id", flat=True))
    ids |= set(InventoryAdjustment.objects.values_list("requested_by_id", flat=True))
    ids |= set(InventoryAdjustment.objects.exclude(approved_by=None).values_list("approved_by_id", flat=True))
    ids |= set(AuditLog.objects.exclude(user=None).values_list("user_id", flat=True))
    return ids


def _credentials_email_feedback(user, password, is_resend=False):
    """The 3-way outcome `UserListCreateView.post()` built up across
    Phase 8.99f-3/f-4/f-5 — factored out (Phase 8.99f-7) so
    `UserResendCredentialsView` doesn't duplicate it (§18: consolidate
    duplicate logic before adding new code). Why 3 outcomes, not 2:
    `send_new_user_credentials_email()` fails open (catches its own
    exception, returns False) rather than raising, so a genuine failure
    (f-3) is surfaced as `warning`, never a silent identical success. But
    `email_sent=True` alone still isn't "a real email reached this
    address" (f-5) — Django's console backend never raises either, it
    "sends" by printing to whichever terminal runs the process, so a
    console-backend send and a real SMTP send used to produce the exact
    "credentials emailed to X" text either way. `message` is now split:
    a real send says so plainly, a console send says so plainly too,
    distinct from both. Returns a dict with exactly one of
    `message`/`warning`, meant to be merged into the caller's own
    {"success": True} response."""
    email_sent = send_new_user_credentials_email(user, password)
    console_dev_mode = email_sent and django_settings.EMAIL_BACKEND.endswith("console.EmailBackend")

    if console_dev_mode:
        action = "Credentials resent" if is_resend else "User created"
        return {"message": (
            f"{action}. The server is using the local console email backend (dev "
            f"mode) — no real email was sent to {user.email}; the credentials printed "
            f"to the server's own terminal instead. Configure real SMTP "
            f"(EMAIL_BACKEND in .env) to actually deliver this email."
        )}
    if email_sent:
        action = "Credentials resent" if is_resend else "User created"
        return {"message": f"{action} — credentials emailed to {user.email}."}

    if is_resend:
        return {"warning": (
            f"Resending credentials to {user.full_name} failed — the email could not "
            f"be sent to {user.email}. Check the server's email configuration, then "
            f"try Resend again."
        )}
    return {"warning": (
        f"{user.full_name}'s account was created, but the credentials email "
        f"could not be sent to {user.email}. They won't be able to log in until "
        f"someone gets them access another way — check the server's email "
        f"configuration, then resend or set a password manually."
    )}


class UserListCreateView(AdminRequiredMixin, View):

    def get(self, request):
        users = list(User.objects.order_by("full_name"))
        history_ids = _user_ids_with_history()
        counts = {"total": 0, "admin": 0, "supervisor": 0, "staff": 0}
        for user in users:
            user.role_badge = _ROLE_BADGE.get(user.role, "badge-indigo")
            user.deletable = user.pk not in history_ids and user.pk != request.user.pk
            # Phase 8.99f-7 — "Resend credentials" is offered for anyone
            # who has never successfully logged in yet (a real signal,
            # last_login is Django's own field, not a new one): if the
            # original credentials email genuinely reached them, they'd
            # have used it by now. Disappears naturally on their first
            # real login, no separate "did the email fail" flag needed.
            user.resendable = user.is_active and user.last_login is None
            counts["total"] += 1
            counts[user.role] += 1
        context = {"active_nav": "users", "users": users, "counts": counts}
        return render(request, "users/users.html", context)

    def post(self, request):
        """Phase 8.98e: the Admin no longer supplies a password at all —
        UserForm has none (see its own docstring). A strong random one is
        generated here, set directly via set_password(), and never placed
        anywhere this view's own response, the audit log, or a
        Notification row could surface it back to the Admin — `details=`
        below deliberately carries no password field, matching every
        other audit.log_action() call in this view.

        The account is still created even if the credentials email fails
        to send (Phase 8.99f-3) — deliberately, not an oversight: rolling
        it back would throw away real, valid admin work (username/
        employee_id/role already chosen and validated) over what's
        usually a transient delivery problem, and there's now a real
        recovery path (`UserResendCredentialsView`, Phase 8.99f-7) for
        exactly this case. What the response says about the send itself —
        real delivery / console dev-mode / genuine failure — is
        `_credentials_email_feedback()`'s own job (above); see that
        function's docstring for the full Phase 8.99f-3/f-4/f-5 history
        of why those 3 distinct outcomes exist."""
        form = UserForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        password = generate_strong_password()
        user = form.save(commit=False)
        user.set_password(password)
        user.save()
        audit.log_action(
            request.user, audit.USER_CREATED, "users",
            affected_id=user.pk, status="success", request=request,
        )
        response = {"success": True}
        response.update(_credentials_email_feedback(user, password))
        return JsonResponse(response)


class UserResendCredentialsView(AdminRequiredMixin, View):
    """Phase 8.99f-7 — the missing piece that makes real SMTP delivery
    operationally safe: without this, one transient send failure (or a
    user who genuinely never saw the original email) means an account
    that can never be accessed, since the Admin never sees the password
    either. Generates a fresh strong password via the exact same
    generate_strong_password() UserListCreateView.post() uses (the Admin
    still never sees it), sets it, and re-sends through the exact same
    send_new_user_credentials_email() — no new password-generation or
    email-sending mechanism. Logs `USER_CREDENTIALS_RESENT` with no
    password in `details=`, same discipline as USER_CREATED."""

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        password = generate_strong_password()
        target.set_password(password)
        target.save(update_fields=["password"])
        audit.log_action(
            request.user, audit.USER_CREDENTIALS_RESENT, "users",
            affected_id=target.pk, status="success", request=request,
        )
        response = {"success": True}
        response.update(_credentials_email_feedback(target, password, is_resend=True))
        return JsonResponse(response)


class UserDeactivateView(AdminRequiredMixin, View):
    """API_CONTRACTS.md: `PATCH /api/v1/users/{id}/deactivate/`, Admin
    only — POST here to match every other action endpoint in this project
    (approve/reject/cancel are all POST, not PATCH; see Phase 7)."""

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target.pk == request.user.pk:
            return JsonResponse({"success": False, "error": "You cannot deactivate your own account."}, status=400)
        target.is_active = False
        target.save(update_fields=["is_active"])
        audit.log_action(
            request.user, audit.USER_DEACTIVATED, "users",
            affected_id=target.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class UserReactivateView(AdminRequiredMixin, View):

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        target.is_active = True
        target.save(update_fields=["is_active"])
        audit.log_action(
            request.user, audit.USER_REACTIVATED, "users",
            affected_id=target.pk, status="success", request=request,
        )
        return JsonResponse({"success": True})


class UserDeleteView(AdminRequiredMixin, View):
    """Phase 8.99f-2 — true delete, deliberately narrow: only a user with
    zero referential history anywhere (_user_ids_with_history(), above)
    can ever be hard-deleted. Every other user — meaning anyone who has
    actually done anything in the system — can only be deactivated
    (UserDeactivateView): hard-deleting them would either raise
    ProtectedError (a 500) or silently null their identity off real
    audit rows. Same self-action guard as deactivate."""

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target.pk == request.user.pk:
            return JsonResponse({"success": False, "error": "You cannot delete your own account."}, status=400)
        if target.pk in _user_ids_with_history():
            return JsonResponse({
                "success": False,
                "error": "This user has activity history and can't be deleted; deactivate instead.",
            }, status=400)
        username = target.username
        target.delete()
        # affected_id below points at an id that no longer exists (this
        # is the one User action where that's unavoidable — every other
        # audited user action leaves the row in place) — details= carries
        # the username so the log entry still means something on its own.
        audit.log_action(
            request.user, audit.USER_DELETED, "users",
            affected_id=pk, status="success", request=request,
            details={"deleted_username": username},
        )
        return JsonResponse({"success": True})

# ------------------------------------------------------------- Audit Log
# Phase 8 — docs/13_AUDIT.md: "Only System Administrator can view the full
# audit log" and "read-only — no update, no delete (enforced in model)".
# AuditLog.save()/delete() already raise PermissionError on any attempt to
# mutate an existing row (Phase 1) — this view only ever reads.

class AuditLogListView(AdminRequiredMixin, View):

    def get(self, request):
        logs = list(
            AuditLog.objects.select_related("user").order_by("-timestamp")[:500]
        )
        for log in logs:
            log.user_label = log.user.full_name if log.user else "System"
        context = {
            "active_nav": "audit-log",
            "logs": logs,
            "total_count": AuditLog.objects.count(),
            "modules": sorted(AuditLog.objects.values_list("module", flat=True).distinct()),
        }
        return render(request, "audit/audit_log.html", context)


class AuditLogExportView(AdminRequiredMixin, View):
    """Phase 8.98 (BUG-44) — same `AdminRequiredMixin` as AuditLogListView
    itself, per 13_AUDIT.md's "Admin only" rule — the export must never be
    a way around that gate. Reuses the shared `generate_csv_response()`.
    Exports the full log, not just the on-screen page's 500-row cap."""

    def get(self, request):
        logs = AuditLog.objects.select_related("user").order_by("-timestamp")
        headers = ["Timestamp", "User", "Action", "Module", "Affected ID", "Status", "IP Address"]
        rows = [
            [
                timezone.localtime(log.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                log.user.full_name if log.user else "System",
                log.action, log.module, log.affected_id or "", log.status, log.ip_address or "",
            ]
            for log in logs
        ]
        return report_lib.generate_csv_response(headers, rows, "audit_log.csv")

# --------------------------------------------------------------- Settings
# Phase 8 — SystemSettings (SCHEMA.md §13) is a documented singleton,
# already enforced at the model level (SystemSettings.save() forces
# pk=1 — Phase 3.4, BUG-21). This is the one and only place that form is
# ever rendered/saved from.

# REQ 17.10 (docs/13_AUDIT.md) follow-up, alongside AI_CLASSIFIER_WEIGHTS_CHANGED
# above — SETTINGS_UPDATED used to fire with no details= payload at all, so an
# admin could see *that* something changed but never *what*. _settings_snapshot()
# is taken before and after form.save() (before is captured pre-bind: a
# ModelForm's own is_valid()/full_clean() already mutates form.instance —
# the same settings_obj — to the new values, so "before" must be read first)
# and diffed field-by-field, same shape as _policy_snapshot()/_POLICY_AUDIT_FIELDS
# below for ApprovalPolicy. AI_CLASSIFIER_WEIGHTS_CHANGED reuses this diff,
# filtered to just the classifier-parameter subset, rather than computing its
# own separate snapshot.
_SETTINGS_AUDIT_FIELDS = SystemSettingsForm.Meta.fields
_CLASSIFIER_AUDIT_FIELDS = [
    "weight_recency", "weight_turnover", "weight_coverage", "weight_frequency",
    "slow_index_threshold", "dead_index_threshold", "target_days_of_cover",
    "extreme_coverage_days", "min_observation_days", "min_sale_events",
]


def _settings_snapshot(settings_obj):
    return {f: (None if getattr(settings_obj, f) is None else str(getattr(settings_obj, f))) for f in _SETTINGS_AUDIT_FIELDS}


class SettingsView(AdminRequiredMixin, View):

    def get(self, request):
        settings_obj = SystemSettings.get_settings()
        context = {"active_nav": "settings", "settings": settings_obj}
        return render(request, "settings/settings.html", context)

    def post(self, request):
        settings_obj = SystemSettings.get_settings()
        before = _settings_snapshot(settings_obj)

        form = SystemSettingsForm(request.POST, request.FILES, instance=settings_obj)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        form.save()
        after = _settings_snapshot(settings_obj)
        diff = {f: {"old": before[f], "new": after[f]} for f in _SETTINGS_AUDIT_FIELDS if before[f] != after[f]}

        classifier_diff = {f: v for f, v in diff.items() if f in _CLASSIFIER_AUDIT_FIELDS}
        if classifier_diff:
            audit.log_action(
                request.user, audit.AI_CLASSIFIER_WEIGHTS_CHANGED, "settings",
                status="success", details=classifier_diff, request=request,
            )
        audit.log_action(
            request.user, audit.SETTINGS_UPDATED, "settings",
            status="success", details=diff, request=request,
        )
        return JsonResponse({"success": True})


# ------------------------------------------------- Approval Policy (Phase 12)
# §8a — admin-only: the admin defines which transactions a supervisor is
# permitted to approve, and a supervisor must never even reach the page
# where that boundary is set (§2's own framing) — AdminRequiredMixin
# throughout, same gate as Settings/Users/Audit Log.
#
# Phase 12.2 — simplified back down to "list the policies that exist,
# let an admin add one": the rule simulator, the unreachable-rule
# warning, the cumulative-usage panel, and ABC as a display/matching
# concept are all removed from this screen (ApprovalPolicySimulateView
# deleted outright). cumulative_window_days/cumulative_value_cap and
# their enforcement in frontend.approvals are untouched — only the
# analysis-oriented UI around them is gone; the condition column still
# shows the cap when one is set.

_POLICY_AUDIT_FIELDS = [
    "name", "transaction_type", "reason_code", "min_value",
    "max_value", "max_variance_pct", "required_level",
    "block_self_approval", "priority", "is_active", "notes",
]


def _policy_snapshot(policy):
    """Plain-dict before/after snapshot for AuditLog.details — §4's own
    instruction: "the policy table must be at least as auditable as the
    transactions it governs." An admin who can silently raise the
    supervisor ceiling has defeated the entire control."""
    return {f: (None if getattr(policy, f) is None else str(getattr(policy, f))) for f in _POLICY_AUDIT_FIELDS}


class ApprovalPolicyListCreateView(AdminRequiredMixin, View):
    """GET renders every policy grouped by transaction_type, ordered by
    priority (matching ApprovalPolicy.Meta.ordering); POST creates one."""

    def get(self, request):
        policies = list(ApprovalPolicy.objects.order_by("transaction_type", "priority"))
        by_type = {}
        for policy in policies:
            policy.edit_json = json.dumps({
                "name": policy.name, "transaction_type": policy.transaction_type,
                "reason_code": policy.reason_code,
                "min_value": str(policy.min_value),
                "max_value": str(policy.max_value) if policy.max_value is not None else "",
                "max_variance_pct": str(policy.max_variance_pct) if policy.max_variance_pct is not None else "",
                "cumulative_window_days": policy.cumulative_window_days or "",
                "cumulative_value_cap": str(policy.cumulative_value_cap) if policy.cumulative_value_cap is not None else "",
                "required_level": policy.required_level,
                "block_self_approval": policy.block_self_approval,
                "priority": policy.priority, "notes": policy.notes,
            })
            by_type.setdefault(policy.transaction_type, []).append(policy)

        # Template needs an ordered list, not a dict keyed by variable
        # value (Django templates can't do `dict[var]` lookup without a
        # custom filter) — one group per ApprovalTxType, including empty
        # ones, in the enum's own declared order.
        grouped_policies = [
            {"value": value, "label": label, "policies": by_type.get(value, [])}
            for value, label in ApprovalTxType.choices
        ]

        context = {
            "active_nav": "settings",
            "grouped_policies": grouped_policies,
            "tx_types": ApprovalTxType.choices,
            "outcomes": ApprovalOutcome.choices,
            "reason_codes": AdjustmentReason.choices,
        }
        return render(request, "settings/approval_policies.html", context)

    def post(self, request):
        form = ApprovalPolicyForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)
        policy = form.save()
        audit.log_action(
            request.user, audit.APPROVAL_POLICY_CREATED, "settings", affected_id=policy.pk,
            status="success", details={"after": _policy_snapshot(policy)}, request=request,
        )
        return JsonResponse({"success": True})


class ApprovalPolicyUpdateView(AdminRequiredMixin, View):

    def post(self, request, pk):
        policy = get_object_or_404(ApprovalPolicy, pk=pk)
        before = _policy_snapshot(policy)
        form = ApprovalPolicyForm(request.POST, instance=policy)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)
        policy = form.save()
        audit.log_action(
            request.user, audit.APPROVAL_POLICY_UPDATED, "settings", affected_id=policy.pk,
            status="success", details={"before": before, "after": _policy_snapshot(policy)}, request=request,
        )
        return JsonResponse({"success": True})


class ApprovalPolicyDeactivateView(AdminRequiredMixin, View):

    def post(self, request, pk):
        policy = get_object_or_404(ApprovalPolicy, pk=pk)
        before = _policy_snapshot(policy)
        policy.is_active = False
        policy.save(update_fields=["is_active", "updated_at"])
        audit.log_action(
            request.user, audit.APPROVAL_POLICY_DEACTIVATED, "settings", affected_id=policy.pk,
            status="success", details={"before": before, "after": _policy_snapshot(policy)}, request=request,
        )
        return JsonResponse({"success": True})


class ApprovalPolicyReactivateView(AdminRequiredMixin, View):

    def post(self, request, pk):
        policy = get_object_or_404(ApprovalPolicy, pk=pk)
        before = _policy_snapshot(policy)
        policy.is_active = True
        conflict = ApprovalPolicy.objects.filter(
            transaction_type=policy.transaction_type, priority=policy.priority, is_active=True,
        ).exclude(pk=policy.pk).exists()
        if conflict:
            return JsonResponse({
                "success": False,
                "error": "Another active policy already uses this priority for this transaction type.",
            }, status=400)
        policy.save(update_fields=["is_active", "updated_at"])
        audit.log_action(
            request.user, audit.APPROVAL_POLICY_REACTIVATED, "settings", affected_id=policy.pk,
            status="success", details={"before": before, "after": _policy_snapshot(policy)}, request=request,
        )
        return JsonResponse({"success": True})
