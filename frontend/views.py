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
from datetime import timedelta

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login as auth_login,
    logout as auth_logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from frontend import audit
from frontend.forms import (
    AdjustmentForm,
    CategoryForm,
    ProductForm,
    PurchaseOrderForm,
    ReasonForm,
    SaleTransactionForm,
    SupplierForm,
    parse_line_items,
)
from frontend.mixins import AnyStaffMixin, SupervisorRequiredMixin
from frontend.models import (
    AdjustmentStatus,
    Category,
    InventoryAdjustment,
    NotificationType,
    POStatus,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SaleStatus,
    SaleTransaction,
    Supplier,
    SystemSettings,
    UnitOfMeasurement,
    User,
)
from frontend.notifications import notify_supervisors, notify_user
from frontend.services import (
    AdjustmentService,
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
            user.profile_image = request.FILES["profile_image"]
        user.save()

        # Password change handled separately, matching 01_AUTH.md — but
        # with validate_password() actually enforced first, unlike the
        # doc's own reference code (which calls set_password() directly,
        # skipping AUTH_PASSWORD_VALIDATORS entirely for this path — a
        # real gap given SECURITY.md's own password-policy requirement).
        new_password = request.POST.get("new_password", "").strip()
        if new_password:
            try:
                validate_password(new_password, user)
            except ValidationError as exc:
                for msg in exc.messages:
                    messages.error(request, msg)
                return render(request, "accounts/profile.html")
            user.set_password(new_password)
            user.save()
            update_session_auth_hash(request, user)  # keep session alive post-change
            notify_user(
                user, NotificationType.PASSWORD_CHANGED, "Password Changed",
                "Your password was successfully updated.",
            )
            audit.log_action(user, audit.PASSWORD_CHANGED, "authentication", status="success", request=request)

        messages.success(request, "Profile updated successfully.")
        audit.log_action(user, audit.PROFILE_UPDATED, "authentication", status="success", request=request)
        return redirect("frontend:profile")

    return render(request, "accounts/profile.html")


def dashboard(request):
    return render(request, "dashboard/dashboard.html")

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
        for product in products:
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
        for category in categories:
            category.product_count = category.products.count()
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


class SupplierListCreateView(AnyStaffMixin, View):
    """Phase 6 — same shape as Phase 5's ProductListCreateView."""

    def get(self, request):
        suppliers = list(Supplier.objects.order_by("company_name"))
        counts = {"total": 0, "active": 0, "inactive": 0}
        for supplier in suppliers:
            supplier.product_count = supplier.products.count()
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
            po.cancellable = po.status in (POStatus.DRAFT, POStatus.PENDING, POStatus.APPROVED, POStatus.PARTIAL)
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
    """05_PURCHASES.md: "Who approves | Supervisor or Admin only"."""

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            PurchaseService.approve(po, request.user)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
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
    """05_PURCHASES.md state machine: "Any state -> CANCELLED (cancel by
    admin/supervisor)". The mock's approve/reject buttons already existed
    without a working backend (project_memory.md §10); Cancel gets the
    same real-endpoint treatment now that PurchaseService.cancel() exists
    (Phase 3.4, BUG-25)."""

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            PurchaseService.cancel(po, request.user)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        return JsonResponse({"success": True})


# ----------------------------------------------------------------- Sales
# Phase 7 — docs/06_SALES.md. SaleService (Phase 3) is the ONLY code path
# allowed to touch stock here.

class SaleListCreateView(AnyStaffMixin, View):

    def get(self, request):
        sales = list(
            SaleTransaction.objects.select_related("created_by")
            .prefetch_related("items").order_by("-created_at")
        )
        counts = {"revenue_today": 0, "transactions_today": 0, "cancelled_30d": 0, "avg_order_30d": 0}
        today = timezone.now().date()
        cutoff = today - timedelta(days=30)
        completed_30d_total, completed_30d_count = 0, 0
        for sale in sales:
            sale.item_count = sale.items.count()
            sale.is_cancelled = sale.status == SaleStatus.CANCELLED
            if sale.transaction_date == today:
                counts["transactions_today"] += 1
                if not sale.is_cancelled:
                    counts["revenue_today"] += sale.total_amount
            if sale.is_cancelled and sale.transaction_date >= cutoff:
                counts["cancelled_30d"] += 1
            if not sale.is_cancelled and sale.transaction_date >= cutoff:
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
        # 06_SALES.md: "Stock check | Verify availability BEFORE
        # confirming" — SaleService.create_sale() does this pre-validation
        # itself (and the InsufficientStockError below is how it surfaces),
        # not duplicated here.
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
        except InsufficientStockError as e:
            return JsonResponse(
                {"success": False, "errors": {"items": [{"message": str(e), "code": "insufficient_stock"}]}},
                status=400,
            )
        except ValueError as e:
            return JsonResponse(
                {"success": False, "errors": {"items": [{"message": str(e), "code": "invalid"}]}}, status=400,
            )

        return JsonResponse({"success": True})


class SaleCancelView(SupervisorRequiredMixin, View):
    """06_SALES.md's own sale_cancel_view uses @supervisor_required."""

    def post(self, request, pk):
        sale = get_object_or_404(SaleTransaction, pk=pk)
        try:
            SaleService.cancel_sale(sale, request.user)
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        return JsonResponse({"success": True})


def inventory(request):
    return render(request, "inventory/inventory.html", {"active_nav": "inventory"})


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
        }
        return render(request, "adjustments/adjustments.html", context)

    def post(self, request):
        form = AdjustmentForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors.get_json_data()}, status=400)

        adjustment = form.save(commit=False)
        adjustment.requested_by = request.user
        adjustment.save()
        audit.log_action(
            request.user, audit.ADJUSTMENT_REQUESTED, "adjustments",
            affected_id=adjustment.pk, status="success", request=request,
        )
        # Mirrors PurchaseService.submit_for_approval()'s notify_supervisors()
        # call — same "a request now needs a supervisor's attention" shape.
        notify_supervisors(
            NotificationType.ADJ_PENDING, f"Adjustment Pending Approval: {adjustment.product.name}",
            f"{request.user.full_name} requested a "
            f"{adjustment.get_adjustment_type_display().lower()} adjustment for "
            f"{adjustment.product.name}.",
            link="/adjustments/",
        )
        return JsonResponse({"success": True})


class AdjustmentApproveView(SupervisorRequiredMixin, View):

    def post(self, request, pk):
        adjustment = get_object_or_404(InventoryAdjustment, pk=pk)
        try:
            AdjustmentService.approve(adjustment, request.user)
        except (ValueError, InsufficientStockError) as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
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
        return JsonResponse({"success": True})

def demand_forecasting(request):
    return render(request, "intelligence/forecasting.html", {"active_nav": "forecasting"})

def slow_moving_dead_stock(request):
    return render(request, "intelligence/slow_moving.html", {"active_nav": "slow-moving"})

def reports(request):
    return render(request, "reports/reports.html", {"active_nav": "reports"})

def notifications(request):
    return render(request, "notifications/notifications.html", {"active_nav": "notifications"})

def users(request):
    return render(request, "users/users.html", {"active_nav": "users"})

def audit_log(request):
    return render(request, "audit/audit_log.html", {"active_nav": "audit-log"})

def settings(request):
    return render(request, "settings/settings.html", {"active_nav": "settings"})
