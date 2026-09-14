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
from django.db.models import Avg, Count, F, Max, Q, Sum
from django.db.models.functions import TruncMonth, TruncWeek
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.timesince import timesince
from django.views import View

from frontend import audit
from frontend import filters
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
from frontend.classification import capital_at_risk, run_full_classification
from frontend.forecasting import backfill_actual_demand, current_forecast_window, latest_forecast_batch, needs_replenishment, run_full_forecast
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

        # Rule: locked-out account never reaches a password comparison.
        if user_obj.locked_until and user_obj.locked_until > timezone.now():
            messages.error(
                request,
                f"Account locked. Try again after "
                f"{timezone.localtime(user_obj.locked_until).strftime('%H:%M:%S')}.",
            )
            return render(request, "accounts/login.html")

        # Rule: checked before authenticate() -- gives a specific message.
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
            # Rule: reuses validate_product_image() -- generic image checks.
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
    """Shared by every path that ends in set_password(): profile, reset."""
    notify_user(
        user, NotificationType.PASSWORD_CHANGED, "Password Changed",
        "Your password was successfully updated.",
    )
    # Security: never passes the new password into notify_admins()/details=.
    notify_admins(
        NotificationType.PASSWORD_CHANGED, f"Password Changed: {user.full_name}",
        f"{user.full_name} ({user.username}) changed their account password.",
    )
    audit.log_action(user, audit.PASSWORD_CHANGED, "authentication", status="success", request=request)


@login_required
def change_password_view(request):
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
    update_session_auth_hash(request, user)  # Rule: keeps this session alive.
    _record_password_change(user, request)
    messages.success(request, "Password changed successfully.")
    return JsonResponse({"success": True})


class StockwellPasswordResetConfirmView(PasswordResetConfirmView):
    """Adds the audit/notify call Django's own form_valid() never makes."""

    def form_valid(self, form):
        response = super().form_valid(form)
        _record_password_change(form.user, self.request)
        return response


DASHBOARD_PREVIEW_ROWS = 5

_PURCHASE_ACTIVITY_STATUSES = (POStatus.APPROVED, POStatus.PARTIAL, POStatus.RECEIVED)


def _dashboard_date_buckets(unit, count):
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
    else:
        y, m = today.year, today.month
        for i in range(count - 1, -1, -1):
            total_month = (y * 12 + (m - 1)) - i
            by, bm = divmod(total_month, 12)
            buckets.append((date(by, bm + 1, 1), date(by, bm + 1, 1).strftime("%b")))
    return buckets


def _sales_purchases_series(unit, count):
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
    buckets = _dashboard_date_buckets("month", 6)
    start = buckets[0][0]
    qs = InventoryMovement.objects.filter(created_at__date__gte=start)

    received_rows = (
        qs.filter(quantity_change__gt=0).annotate(bucket=TruncMonth("created_at"))
        .values("bucket").annotate(total=Sum("quantity_change"))
    )
    # Workaround: TruncMonth returns an aware datetime; .date() matches buckets.
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

    def get(self, request):
        # Assumption: Asia/Dhaka clock -- matches every other rendered timestamp.
        now_local = timezone.localtime()
        hour = now_local.hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        thirty_days_ago = timezone.now() - timedelta(days=30)

        kpis = {
            "total_products": Product.objects.count(),
            "new_products_30d": Product.objects.filter(created_at__gte=thirty_days_ago).count(),
            "total_categories": Category.objects.count(),
            "new_categories_30d": Category.objects.filter(created_at__gte=thirty_days_ago).count(),
            "active_suppliers": Supplier.objects.filter(is_active=True).count(),
            "new_active_suppliers_30d": Supplier.objects.filter(
                is_active=True, created_at__gte=thirty_days_ago
            ).count(),
            "total_users": User.objects.count(),
            "new_users_30d": User.objects.filter(created_at__gte=thirty_days_ago).count(),
        }

        inv_agg = InventoryRecord.objects.aggregate(value=Sum("total_value"), units=Sum("current_stock"))
        stats = {
            "inventory_value": inv_agg["value"] or 0,
            "stock_units": inv_agg["units"] or 0,
            "low_stock_count": InventoryRecord.objects.filter(status=InventoryStatus.LOW_STOCK).count(),
            "out_of_stock_count": InventoryRecord.objects.filter(status=InventoryStatus.OUT_OF_STOCK).count(),
        }

        stock_alerts = list(
            InventoryRecord.objects.filter(status__in=[InventoryStatus.LOW_STOCK, InventoryStatus.OUT_OF_STOCK])
            .select_related("product").order_by("current_stock")[:DASHBOARD_PREVIEW_ROWS]
        )
        for record in stock_alerts:
            record.status_badge = _INVENTORY_STATUS_BADGE.get(record.status, "badge-indigo")

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

        # Security: 3 widgets below are Admin/Supervisor only, above the mixin floor.
        recent_activity = None
        if request.user.is_authenticated and request.user.role in (UserRole.ADMIN, UserRole.SUPERVISOR):
            recent_activity = list(
                AuditLog.objects.exclude(module="authentication")
                .select_related("user").order_by("-timestamp")[:DASHBOARD_PREVIEW_ROWS]
            )
            for log in recent_activity:
                log.user_label = log.user.full_name if log.user else "System"

        # Rule: counts must match SlowMovingDeadStockView's own -- one truth.
        classification_insights = None
        if request.user.is_authenticated and request.user.role in (UserRole.ADMIN, UserRole.SUPERVISOR):
            classification_counts = {choice: 0 for choice in StockClassification.values}
            for row in InventoryClassification.objects.values('classification').annotate(count=Count('id')):
                classification_counts[row['classification']] = row['count']

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

        # Rule: latest_forecast_batch() -- same dedup as DemandForecastingView.
        forecast_insights = None
        if request.user.is_authenticated and request.user.role in (UserRole.ADMIN, UserRole.SUPERVISOR):
            forecasts, forecast_last_run = latest_forecast_batch()
            stock_by_product = dict(InventoryRecord.objects.values_list('product_id', 'current_stock'))

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
                "products_forecasted": len({f.product_id for f in forecasts}),
                "replenishment_count": len(replenishment_needed),
                "replenishment_products": replenishment_needed[:DASHBOARD_PREVIEW_ROWS],
            }

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
    # Rule: InventoryRecord excluded -- current-state, not history.
    ids = set()
    ids |= set(PurchaseOrderItem.objects.values_list("product_id", flat=True))
    ids |= set(SaleItem.objects.values_list("product_id", flat=True))
    ids |= set(InventoryMovement.objects.values_list("product_id", flat=True))
    ids |= set(InventoryAdjustment.objects.values_list("product_id", flat=True))
    return ids


class ProductListCreateView(AnyStaffMixin, View):

    def get(self, request):
        # Perf: whole-table aggregate -- counts ignore the filter/pagination below.
        counts = Product.objects.aggregate(
            total=Count("id"),
            out_of_stock=Count("id", filter=Q(current_stock__lte=0)),
            low_stock=Count("id", filter=Q(current_stock__gt=0, reorder_level__gt=0, current_stock__lte=F("reorder_level"))),
        )
        counts["in_stock"] = counts["total"] - counts["out_of_stock"] - counts["low_stock"]

        qs = filters.filter_products(
            request, Product.objects.select_related("category", "supplier").order_by("-created_at")
        )
        page = filters.paginate(request, qs, 10)

        history_ids = _product_ids_with_history()
        for product in page.object_list:
            product.deletable = product.pk not in history_ids
            # Assumption: reads Product's own fields -- a legacy row may have none.
            if product.current_stock <= 0:
                product.stock_label, product.stock_badge = "Out of stock", "badge-danger"
            elif product.reorder_level and product.current_stock <= product.reorder_level:
                product.stock_label, product.stock_badge = "Low stock", "badge-warning"
            else:
                product.stock_label, product.stock_badge = "In stock", "badge-success"
            product.edit_json = json.dumps({
                "name": product.name, "sku": product.sku, "barcode": product.barcode or "",
                "category": product.category_id, "supplier": product.supplier_id,
                "brand": product.brand, "unit": product.unit,
                "purchase_price": str(product.purchase_price), "selling_price": str(product.selling_price),
                "tax_rate": str(product.tax_rate), "reorder_level": product.reorder_level,
            })

        context = {
            "active_nav": "products",
            "page": page,
            "counts": counts,
            "categories": Category.objects.filter(is_active=True).order_by("name"),
            "suppliers": Supplier.objects.filter(is_active=True).order_by("company_name"),
            "unit_choices": UnitOfMeasurement.choices,
            "q": request.GET.get("q", ""),
            "category_id": request.GET.get("category", ""),
            "status": request.GET.get("status", ""),
            "querystring": filters.pagination_querystring(request),
        }
        return render(request, "products/products.html", context)

    def post(self, request):
        form = ProductForm(request.POST, request.FILES)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        with transaction.atomic():
            product = form.save(commit=False)
            product.save()
            # Rule: no InventoryMovement yet -- stock moves only once a PO is received.
            InventoryService.initialize_for_product(product)
            audit.log_action(
                request.user, audit.PRODUCT_CREATED, "products",
                affected_id=product.pk, status="success", request=request,
            )

        return JsonResponse({"success": True})


class ProductUpdateView(AnyStaffMixin, View):

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        data = request.POST.copy()
        # Rule: sku is read-only on edit -- overwritten before the form sees it.
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

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        if product.pk in _product_ids_with_history():
            return JsonResponse({
                "success": False,
                "error": "This product has purchase, sale, or adjustment history and can't be deleted; deactivate instead.",
            }, status=400)
        name = product.name
        with transaction.atomic():
            # Rule: InventoryRecord deleted explicitly -- excluded from the check above.
            InventoryRecord.objects.filter(product=product).delete()
            product.delete()
        audit.log_action(
            request.user, audit.PRODUCT_DELETED, "products",
            affected_id=pk, status="success", request=request,
            details={"deleted_product_name": name},
        )
        return JsonResponse({"success": True})


class ProductExportView(AnyStaffMixin, View):

    def get(self, request):
        # Rule: filter_products() -- whole matching set, never just the current page.
        products = filters.filter_products(
            request, Product.objects.select_related("category", "supplier").order_by("name")
        )
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
    return set(Product.objects.values_list("category_id", flat=True))


def _supplier_ids_with_history():
    ids = set(Product.objects.values_list("supplier_id", flat=True))
    ids |= set(PurchaseOrder.objects.values_list("supplier_id", flat=True))
    return ids


class CategoryListCreateView(AnyStaffMixin, View):

    def get(self, request):
        categories = list(Category.objects.order_by("name"))
        history_ids = _category_ids_with_products()
        for category in categories:
            category.product_count = category.products.count()
            category.deletable = category.pk not in history_ids
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

    def get(self, request):
        suppliers = Supplier.objects.order_by("company_name")
        headers = ["Company Name", "Supplier Name", "Contact Person", "Email", "Phone", "Address", "Active"]
        rows = [
            [s.company_name, s.supplier_name, s.contact_person, s.email, s.phone, s.address, "Yes" if s.is_active else "No"]
            for s in suppliers
        ]
        return report_lib.generate_csv_response(headers, rows, "suppliers.csv")

# Rule: PurchaseService is the only code path allowed to touch stock here.

class PurchaseListCreateView(AnyStaffMixin, View):

    _STATUS_BADGE = {
        POStatus.DRAFT: "badge-indigo", POStatus.PENDING: "badge-warning",
        POStatus.APPROVED: "badge-success", POStatus.PARTIAL: "badge-warning",
        POStatus.RECEIVED: "badge-success", POStatus.REJECTED: "badge-danger",
        POStatus.CANCELLED: "badge-danger",
    }

    def get(self, request):
        # Perf: whole-table aggregate -- counts ignore the filter/pagination below.
        now = timezone.now()
        counts = PurchaseOrder.objects.aggregate(
            open=Count("id", filter=~Q(status__in=[POStatus.RECEIVED, POStatus.REJECTED, POStatus.CANCELLED])),
            pending=Count("id", filter=Q(status=POStatus.PENDING)),
            received_month=Count("id", filter=Q(
                status__in=[POStatus.RECEIVED, POStatus.PARTIAL],
                created_at__year=now.year, created_at__month=now.month,
            )),
            value_month=Sum("total_cost", filter=Q(created_at__year=now.year, created_at__month=now.month)),
        )
        counts["value_month"] = counts["value_month"] or 0

        qs = filters.filter_purchases(
            request,
            PurchaseOrder.objects.select_related("supplier", "created_by").prefetch_related("items__product").order_by("-created_at"),
        )
        page = filters.paginate(request, qs, 10)

        for po in page.object_list:
            po.item_count = po.items.count()
            po.status_badge = self._STATUS_BADGE.get(po.status, "badge-indigo")
            # Rule: hiding the button here is UX only -- cancel() is the real gate.
            po.cancellable = po.status in (POStatus.DRAFT, POStatus.PENDING)
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

        context = {
            "active_nav": "purchases",
            "page": page,
            "counts": counts,
            "suppliers": Supplier.objects.filter(is_active=True).order_by("company_name"),
            "products": Product.objects.filter(is_active=True).order_by("name"),
            # Assumption: Asia/Dhaka "today" -- matches PurchaseOrderForm's own check.
            "today": timezone.localdate(),
            "q": request.GET.get("q", ""),
            "status": request.GET.get("status", ""),
            "querystring": filters.pagination_querystring(request),
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
            # Rule: total_cost has no auto-compute -- summed from each item's line_total.
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

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            PurchaseService.submit_for_approval(po, request.user)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        return JsonResponse({"success": True})


# Security: this mixin is a floor -- ApprovalPolicy can narrow it to Admin-only.
class PurchaseApproveView(SupervisorRequiredMixin, View):

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
    """receive_json: [{item_id, received_qty}, ...]."""

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

    def get(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        return report_lib.generate_purchase_order_pdf(po, generated_by=request.user.full_name)


# Rule: SaleService is the only code path allowed to touch stock here.

class SaleListCreateView(AnyStaffMixin, View):

    _STATUS_BADGE = {
        SaleStatus.DRAFT: "badge-indigo", SaleStatus.PENDING: "badge-warning",
        SaleStatus.COMPLETED: "badge-success", SaleStatus.REJECTED: "badge-danger",
        SaleStatus.CANCELLED: "badge-danger",
    }

    def get(self, request):
        # Perf: whole-table aggregate -- counts ignore the filter/pagination below.
        today = timezone.now().date()
        cutoff = today - timedelta(days=30)
        counts = SaleTransaction.objects.aggregate(
            pending=Count("id", filter=Q(status=SaleStatus.PENDING)),
            transactions_today=Count("id", filter=Q(transaction_date=today)),
            revenue_today=Sum("total_amount", filter=Q(status=SaleStatus.COMPLETED, transaction_date=today)),
            cancelled_30d=Count("id", filter=Q(status=SaleStatus.CANCELLED, transaction_date__gte=cutoff)),
            avg_order_30d=Avg("total_amount", filter=Q(status=SaleStatus.COMPLETED, transaction_date__gte=cutoff)),
        )
        counts["revenue_today"] = counts["revenue_today"] or 0
        counts["avg_order_30d"] = counts["avg_order_30d"] or 0

        qs = filters.filter_sales(
            request, SaleTransaction.objects.select_related("created_by").prefetch_related("items").order_by("-created_at")
        )
        page = filters.paginate(request, qs, 10)

        for sale in page.object_list:
            sale.item_count = sale.items.count()
            sale.status_badge = self._STATUS_BADGE.get(sale.status, "badge-indigo")
            sale.cancellable = sale.status in (SaleStatus.DRAFT, SaleStatus.PENDING)
            if sale.cancellable:
                _, sale.required_level, _ = resolve_for_transaction(sale)
                sale.can_cancel, sale.cancel_denied_reason = can_approve(request.user, sale)
            else:
                sale.required_level = ""
                sale.can_cancel = False
                sale.cancel_denied_reason = ""

        context = {
            "active_nav": "sales",
            "page": page,
            "counts": counts,
            "products": Product.objects.filter(is_active=True).order_by("name"),
            "q": request.GET.get("q", ""),
            "status": request.GET.get("status", ""),
            "querystring": filters.pagination_querystring(request),
        }
        return render(request, "sales/sales.html", context)

    def post(self, request):
        form = SaleTransactionForm(request.POST)
        # Rule: no stock check here -- re-checked for real at approve_sale() time.
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

    def post(self, request, pk):
        sale = get_object_or_404(SaleTransaction, pk=pk)
        try:
            SaleService.submit_for_approval(sale, request.user)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        return JsonResponse({"success": True})


class SaleApproveView(SupervisorRequiredMixin, View):

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

    def get(self, request, pk):
        sale = get_object_or_404(SaleTransaction, pk=pk)
        audit.log_action(
            request.user, audit.SALE_INVOICE_PRINTED, "sales",
            affected_id=sale.pk, status="success", request=request,
        )
        return report_lib.generate_sale_transaction_pdf(sale, generated_by=request.user.full_name)


# Rule: status is read straight off InventoryRecord, never recomputed here.
_INVENTORY_STATUS_BADGE = {
    InventoryStatus.AVAILABLE: "badge-success",
    InventoryStatus.LOW_STOCK: "badge-warning",
    InventoryStatus.OUT_OF_STOCK: "badge-danger",
}


class InventoryListView(AnyStaffMixin, View):

    def get(self, request):
        # Perf: whole-table aggregate -- counts ignore the filter/pagination below.
        counts = InventoryRecord.objects.aggregate(
            total_skus=Count("id"),
            total_value=Sum("total_value"),
            low_stock=Count("id", filter=Q(status=InventoryStatus.LOW_STOCK)),
            out_of_stock=Count("id", filter=Q(status=InventoryStatus.OUT_OF_STOCK)),
        )
        counts["total_value"] = counts["total_value"] or 0

        qs = filters.filter_inventory(
            request,
            InventoryRecord.objects.select_related("product", "product__category", "product__supplier").order_by("product__name"),
        )
        page = filters.paginate(request, qs, 10)

        for record in page.object_list:
            record.status_badge = _INVENTORY_STATUS_BADGE.get(record.status, "badge-indigo")
            latest_movement = record.product.movements.order_by("-created_at").first()
            record.last_movement_at = latest_movement.created_at if latest_movement else None

        audit.log_action(request.user, audit.INVENTORY_VIEWED, "inventory", status="success", request=request)

        context = {
            "active_nav": "inventory",
            "page": page,
            "counts": counts,
            "q": request.GET.get("q", ""),
            "status": request.GET.get("status", ""),
            "querystring": filters.pagination_querystring(request),
        }
        return render(request, "inventory/inventory.html", context)


class MovementHistoryListView(AnyStaffMixin, View):

    PAGE_SIZE = 50

    def get(self, request):
        movements = InventoryMovement.objects.select_related("product", "performed_by").order_by("-created_at")
        # Rule: filter_movements() is shared with the export -- can't disagree.
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
            # Rule: RETURN excluded -- no code path ever creates that movement type.
            "movement_types": [c for c in MovementType.choices if c[0] != MovementType.RETURN],
            "export_querystring": querystring.urlencode(),
        }
        return render(request, "inventory/movement_history.html", context)


class MovementHistoryExportView(AnyStaffMixin, View):
    """`?format=csv` (default) or `?format=pdf`; same querystring as the page."""

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


# Rule: AdjustmentService is the only code path allowed to touch stock here.

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
            "products": Product.objects.order_by("name"),
            "reason_codes": AdjustmentReason.choices,
        }
        return render(request, "adjustments/adjustments.html", context)

    def post(self, request):
        form = AdjustmentForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        # Rule: AdjustmentService.create() decides AUTO-post vs PENDING-save.
        adjustment = form.save(commit=False)
        try:
            AdjustmentService.create(adjustment, request.user)
        except InsufficientStockError as e:
            # Edge: only an AUTO-outcome DECREASE reaches this -- PENDING never does.
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        return JsonResponse({"success": True})


class AdjustmentApproveView(SupervisorRequiredMixin, View):

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

    def get(self, request, pk):
        adjustment = get_object_or_404(InventoryAdjustment, pk=pk)
        return report_lib.generate_adjustment_pdf(adjustment, generated_by=request.user.full_name)


class DemandForecastingView(SupervisorRequiredMixin, View):

    _PERIOD_LABEL = {ForecastPeriod.WEEKLY: 'weekly', ForecastPeriod.MONTHLY: 'monthly'}

    def _build_chart_data(self, period_choice):
        # Rule: current_forecast_window() already caps at 4 upcoming periods.
        window = current_forecast_window(period_choice, horizon=4)
        buckets = {}
        for f in window:
            buckets.setdefault(f.period_start, {'demand': 0.0, 'reorder': 0})
            buckets[f.period_start]['demand'] += float(f.forecasted_demand)
            buckets[f.period_start]['reorder'] += f.recommended_reorder_qty
        keys = sorted(buckets.keys())
        return {
            'labels': [k.strftime('%d %b') for k in keys],
            'demand': [round(buckets[k]['demand'], 1) for k in keys],
            'reorder': [buckets[k]['reorder'] for k in keys],
        }

    def get(self, request):
        _, last_run = latest_forecast_batch()
        stock_by_product = dict(InventoryRecord.objects.values_list('product_id', 'current_stock'))

        # Rule: one row per (product, period-type) -- the soonest upcoming only.
        upcoming = (
            current_forecast_window(ForecastPeriod.WEEKLY, horizon=None)
            + current_forecast_window(ForecastPeriod.MONTHLY, horizon=None)
        )
        nearest = {}
        for f in upcoming:
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

        filtered_rows = filters.filter_forecasts(table_rows, request)
        page = filters.paginate(request, filtered_rows, 10)

        context = {
            "active_nav": "forecasting",
            "page": page,
            "q": request.GET.get("q", ""),
            "category_name": request.GET.get("category", ""),
            "period": request.GET.get("period", "") or "weekly",
            "querystring": filters.pagination_querystring(request),
            "period_toggle_querystring": filters.toggle_querystring(request, "period"),
            "categories": Category.objects.filter(is_active=True).order_by("name"),
            "products_forecasted": len({f.product_id for f in table_rows}),
            "avg_confidence_pct": avg_confidence_pct,
            "flagged_count": flagged_count,
            "last_run": last_run,
            "reorder_priorities": reorder_priorities,
            "chart_data": {
                "weekly": self._build_chart_data(ForecastPeriod.WEEKLY),
                "monthly": self._build_chart_data(ForecastPeriod.MONTHLY),
            },
        }
        return render(request, "intelligence/forecasting.html", context)

    def post(self, request):
        # Assumption: runs synchronously -- blocks for a full retrain-and-forecast.
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

    _BADGE = {
        StockClassification.FAST: "badge-success",
        StockClassification.SLOW: "badge-warning",
        StockClassification.DEAD: "badge-danger",
        # Rule: insufficient_data gets its own neutral badge -- not a problem state.
        StockClassification.INSUFFICIENT_DATA: "badge-neutral",
    }

    def get(self, request):
        settings_obj = SystemSettings.get_settings()

        # Perf: whole-table aggregate -- counts ignore the filter/pagination below.
        counts_agg = InventoryClassification.objects.aggregate(
            fast=Count("id", filter=Q(classification=StockClassification.FAST)),
            slow=Count("id", filter=Q(classification=StockClassification.SLOW)),
            dead=Count("id", filter=Q(classification=StockClassification.DEAD)),
            insufficient_data=Count("id", filter=Q(classification=StockClassification.INSUFFICIENT_DATA)),
        )
        counts = {
            StockClassification.FAST: counts_agg["fast"],
            StockClassification.SLOW: counts_agg["slow"],
            StockClassification.DEAD: counts_agg["dead"],
            StockClassification.INSUFFICIENT_DATA: counts_agg["insufficient_data"],
        }

        # Assumption: a None days_since_last_sale ranks as 0 -- last, never first.
        dead_and_slow = list(
            InventoryClassification.objects.filter(classification__in=[StockClassification.DEAD, StockClassification.SLOW])
            .select_related("product")
        )
        dead_watch = sorted(
            (c for c in dead_and_slow if c.classification == StockClassification.DEAD),
            key=lambda c: -(c.days_since_last_sale or 0),
        )[:2]
        slow_watch = sorted(
            (c for c in dead_and_slow if c.classification == StockClassification.SLOW),
            key=lambda c: -(c.days_since_last_sale or 0),
        )[:1]
        for c in slow_watch:
            c.days_to_dead = max(settings_obj.dead_stock_threshold_days - (c.days_since_last_sale or 0), 0)

        # Rule: capital_at_risk() -- shared with the classification report's export.
        stock_by_product = dict(InventoryRecord.objects.values_list("product_id", "current_stock"))
        dead_value_at_risk = sum(
            (capital_at_risk(c, stock_by_product) or 0)
            for c in dead_and_slow if c.classification == StockClassification.DEAD
        )
        last_classified_at = InventoryClassification.objects.aggregate(Max("classified_at"))["classified_at__max"]

        qs = filters.filter_classifications(
            request,
            InventoryClassification.objects.select_related("product", "product__category").order_by("product__name"),
        )
        page = filters.paginate(request, qs, 10)

        for c in page.object_list:
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

        context = {
            "active_nav": "slow-moving",
            "page": page,
            "counts": counts,
            "total_flagged": counts[StockClassification.SLOW] + counts[StockClassification.DEAD],
            "total_classified": sum(counts.values()),
            "dead_value_at_risk": dead_value_at_risk,
            "last_classified_at": last_classified_at,
            "categories": Category.objects.filter(is_active=True).order_by("name"),
            "dead_watch": dead_watch,
            "slow_watch": slow_watch,
            "slow_threshold": settings_obj.slow_moving_threshold_days,
            "dead_threshold": settings_obj.dead_stock_threshold_days,
            "min_sale_events": settings_obj.min_sale_events,
            "chart_data": {
                "fast": counts[StockClassification.FAST],
                "slow": counts[StockClassification.SLOW],
                "dead": counts[StockClassification.DEAD],
                "insufficient_data": counts[StockClassification.INSUFFICIENT_DATA],
            },
            "q": request.GET.get("q", ""),
            "category_name": request.GET.get("category", ""),
            "classification": request.GET.get("classification", ""),
            "querystring": filters.pagination_querystring(request),
            "classification_toggle_querystring": filters.toggle_querystring(request, "classification"),
        }
        return render(request, "intelligence/slow_moving.html", context)

    def post(self, request):
        # Assumption: runs synchronously -- blocks for a full classification run.
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

class ReportsView(SupervisorRequiredMixin, View):
    """9 report cards, each a direct PDF/CSV link to ReportExportView."""

    def get(self, request):
        context = {"active_nav": "reports"}
        return render(request, "reports/reports.html", context)


class ReportExportView(SupervisorRequiredMixin, View):
    """GET .../reports/export/<report_type>/?format=pdf|csv"""

    def get(self, request, report_type):
        builder = report_lib.REPORT_BUILDERS.get(report_type)
        if builder is None:
            return JsonResponse({"success": False, "error": "Unknown report type."}, status=404)

        export_format = request.GET.get("format")
        filename_base = report_type.replace("-", "_")

        # Rule: sales PDF is the aggregate summary shape; CSV keeps detailed rows.
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

# Security: recipient=request.user row-filtering is the real gate below.

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
        qs = Notification.objects.filter(recipient=request.user).order_by("-created_at")
        page = filters.paginate(request, qs, 10)
        for notif in page.object_list:
            notif.icon_name, notif.icon_style = _NOTIF_ICON.get(notif.type, _NOTIF_ICON_DEFAULT)
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        context = {
            "active_nav": "notifications",
            "page": page,
            "querystring": filters.pagination_querystring(request),
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


class NotificationRecentView(LoginRequiredMixin, View):

    def get(self, request):
        qs = Notification.objects.filter(recipient=request.user).order_by("-created_at")
        recent = qs[:DASHBOARD_PREVIEW_ROWS]
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        notifications = []
        for notif in recent:
            icon_name, icon_style = _NOTIF_ICON.get(notif.type, _NOTIF_ICON_DEFAULT)
            notifications.append({
                "id": notif.pk,
                "title": notif.title,
                "message": notif.message,
                "created_at": f"{timesince(notif.created_at)} ago",
                "is_read": notif.is_read,
                "is_critical": notif.is_critical,
                "icon_name": icon_name,
                "icon_style": icon_style,
            })
        return JsonResponse({"unread_count": unread_count, "notifications": notifications})

_ROLE_BADGE = {UserRole.ADMIN: "badge-indigo", UserRole.SUPERVISOR: "badge-warning", UserRole.STAFF: "badge-success"}


def _user_ids_with_history():
    # Rule: AuditLog.user (SET_NULL) counts too -- would orphan an audited action.
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
    email_sent = send_new_user_credentials_email(user, password)
    # Rule: console backend "sends" by printing -- not a real delivery.
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
            # Rule: resendable until the user's first real login -- no separate flag.
            user.resendable = user.is_active and user.last_login is None
            counts["total"] += 1
            counts[user.role] += 1
        context = {"active_nav": "users", "users": users, "counts": counts}
        return render(request, "users/users.html", context)

    def post(self, request):
        form = UserForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        # Security: a strong random password -- never returned, logged, or notified.
        password = generate_strong_password()
        user = form.save(commit=False)
        user.set_password(password)
        user.save()
        audit.log_action(
            request.user, audit.USER_CREATED, "users",
            affected_id=user.pk, status="success", request=request,
        )
        response = {"success": True}
        # Rule: created even if the credentials email fails -- recoverable via resend.
        response.update(_credentials_email_feedback(user, password))
        return JsonResponse(response)


class UserResendCredentialsView(AdminRequiredMixin, View):

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

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        # Rule: an admin cannot deactivate or delete their own account.
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
        # Assumption: affected_id is now a deleted row -- username kept in details=.
        audit.log_action(
            request.user, audit.USER_DELETED, "users",
            affected_id=pk, status="success", request=request,
            details={"deleted_username": username},
        )
        return JsonResponse({"success": True})

def _format_audit_details(details):
    if not details:
        return None
    parts = []
    for field, change in details.items():
        if isinstance(change, dict) and "old" in change and "new" in change:
            parts.append(f"{field}: {change['old']} → {change['new']}")
        else:
            parts.append(f"{field}: {change}")
    return "; ".join(parts)


class AuditLogListView(AdminRequiredMixin, View):

    def get(self, request):
        qs = filters.filter_audit_log(request, AuditLog.objects.select_related("user").order_by("-timestamp"))
        page = filters.paginate(request, qs, 10)

        for log in page.object_list:
            log.user_label = log.user.full_name if log.user else "System"
            log.details_display = _format_audit_details(log.details)

        context = {
            "active_nav": "audit-log",
            "page": page,
            "modules": sorted(AuditLog.objects.values_list("module", flat=True).distinct()),
            "q": request.GET.get("q", ""),
            "module_filter": request.GET.get("module", ""),
            "status": request.GET.get("status", ""),
            "querystring": filters.pagination_querystring(request),
            "status_toggle_querystring": filters.toggle_querystring(request, "status"),
        }
        return render(request, "audit/audit_log.html", context)


# Rule: filter_audit_log() -- full matching set, never just the current page.
class AuditLogExportView(AdminRequiredMixin, View):

    def get(self, request):
        logs = filters.filter_audit_log(request, AuditLog.objects.select_related("user").order_by("-timestamp"))
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
        # Assumption: read before is_valid() -- full_clean() mutates form.instance.
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


_POLICY_AUDIT_FIELDS = [
    "name", "transaction_type", "reason_code", "min_value",
    "max_value", "max_variance_pct", "required_level",
    "block_self_approval", "priority", "is_active", "notes",
]


# Security: policy changes must be as auditable as the transactions they govern.
def _policy_snapshot(policy):
    return {f: (None if getattr(policy, f) is None else str(getattr(policy, f))) for f in _POLICY_AUDIT_FIELDS}


class ApprovalPolicyListCreateView(AdminRequiredMixin, View):
    """GET: every policy grouped by transaction_type. POST: creates one."""

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

        # Workaround: templates can't do dict[var] lookup -- pre-grouped to a list.
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
