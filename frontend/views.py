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
from django.shortcuts import redirect, render
from django.utils import timezone

from frontend import audit
from frontend.models import NotificationType, SystemSettings, User
from frontend.notifications import notify_user


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

def products(request):
    return render(request, "products/products.html", {"active_nav": "products"})

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
