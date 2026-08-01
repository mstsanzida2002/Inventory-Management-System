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
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from frontend import audit
from frontend.forms import ProductForm
from frontend.mixins import AnyStaffMixin
from frontend.models import (
    Category,
    NotificationType,
    Product,
    Supplier,
    SystemSettings,
    UnitOfMeasurement,
    User,
)
from frontend.notifications import notify_user
from frontend.services import InventoryService


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

def categories(request):
    return render(request, "categories/categories.html", {"active_nav": "categories"})

def suppliers(request):
    return render(request, "suppliers/suppliers.html", {"active_nav": "suppliers"})

def purchases(request):
    return render(request, "purchases/purchases.html", {"active_nav": "purchases"})

def sales(request):
    return render(request, "sales/sales.html", {"active_nav": "sales"})

def inventory(request):
    return render(request, "inventory/inventory.html", {"active_nav": "inventory"})

def adjustments(request):
    return render(request, "adjustments/adjustments.html", {"active_nav": "adjustments"})

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
