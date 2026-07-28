# 🔐 Module 01 — Authentication
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when implementing login, logout, registration,
> password reset, session management, or account lockout logic.

---

## Requirements Coverage
`REQ 1.1 → 1.15` | `REQ 15.1 → 15.15`

---

## Business Rules

| Rule | Detail |
|---|---|
| Login identifier | Username OR email address (both accepted) |
| Password hashing | Argon2 — configured in `PASSWORD_HASHERS` |
| Session timeout | Configurable via `SystemSettings.session_timeout_seconds` (default 3600s) |
| Account lockout | Temporary lock after N consecutive failed logins (configurable, default 5) |
| Lockout duration | Configurable (default 300 seconds) |
| Password policy | Min 8 chars, uppercase, lowercase, number, special character |
| Post-login redirect | Redirect to role-specific dashboard |
| Password reset | Via registered email only |
| Session cookie | HttpOnly + Secure + SameSite=Lax |
| Failed login logging | Every failed attempt recorded in AuditLog |

---

## Views

### `apps/authentication/views.py`

```python
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib import messages
from datetime import timedelta
from apps.users.models import User
from apps.audit.services import log_action
from apps.settings_manager.models import SystemSettings

def login_view(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    if request.method == 'POST':
        identifier = request.POST.get('identifier', '').strip()
        password = request.POST.get('password', '')

        # Find user by username or email
        try:
            user_obj = User.objects.get(
                username=identifier
            ) if '@' not in identifier else User.objects.get(email=identifier)
        except User.DoesNotExist:
            messages.error(request, 'Invalid credentials.')
            log_action(None, 'LOGIN_FAILED', 'authentication', status='failure',
                       details={'identifier': identifier}, request=request)
            return render(request, 'auth/login.html')

        # Check lockout
        if user_obj.locked_until and user_obj.locked_until > timezone.now():
            messages.error(request, f'Account locked. Try again after {user_obj.locked_until.strftime("%H:%M:%S")}.')
            return render(request, 'auth/login.html')

        user = authenticate(request, username=user_obj.username, password=password)

        if user is None:
            # Increment failed attempts
            user_obj.failed_login_attempts += 1
            max_attempts = 5  # or from SystemSettings
            if user_obj.failed_login_attempts >= max_attempts:
                user_obj.locked_until = timezone.now() + timedelta(seconds=300)
                user_obj.failed_login_attempts = 0
                messages.error(request, 'Account locked due to too many failed attempts.')
            else:
                messages.error(request, f'Invalid credentials. {max_attempts - user_obj.failed_login_attempts} attempts remaining.')
            user_obj.save(update_fields=['failed_login_attempts', 'locked_until'])
            log_action(user_obj, 'LOGIN_FAILED', 'authentication', status='failure', request=request)
            return render(request, 'auth/login.html')

        if not user.is_active:
            messages.error(request, 'Your account is inactive. Contact administrator.')
            return render(request, 'auth/login.html')

        # Successful login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=['failed_login_attempts', 'locked_until'])
        login(request, user)
        log_action(user, 'LOGIN_SUCCESS', 'authentication', status='success', request=request)

        # Apply session timeout from settings
        settings_obj = SystemSettings.get_settings()
        request.session.set_expiry(settings_obj.session_timeout_seconds)

        return redirect_by_role(user)

    return render(request, 'auth/login.html')


def redirect_by_role(user):
    from django.shortcuts import redirect
    if user.is_admin:
        return redirect('dashboard:admin')
    elif user.is_supervisor:
        return redirect('dashboard:supervisor')
    return redirect('dashboard:staff')


@login_required
def logout_view(request):
    log_action(request.user, 'LOGOUT', 'authentication', status='success', request=request)
    logout(request)
    return redirect('auth:login')
```

---

## Password Reset Flow

```python
# Uses Django's built-in password reset with custom templates

# apps/authentication/urls.py
from django.contrib.auth import views as auth_views
from django.urls import path

urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='auth/password_reset.html',
             email_template_name='auth/emails/password_reset_email.html',
             subject_template_name='auth/emails/password_reset_subject.txt',
         ),
         name='password_reset'),
    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(template_name='auth/password_reset_done.html'),
         name='password_reset_done'),
    path('password-reset/confirm/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(template_name='auth/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('password-reset/complete/',
         auth_views.PasswordResetCompleteView.as_view(template_name='auth/password_reset_complete.html'),
         name='password_reset_complete'),
]
```

---

## Profile Update View

```python
@login_required
def profile_update_view(request):
    if request.method == 'POST':
        user = request.user
        user.full_name = request.POST.get('full_name', user.full_name)
        user.contact_number = request.POST.get('contact_number', user.contact_number)
        if 'profile_image' in request.FILES:
            user.profile_image = request.FILES['profile_image']
        user.save()
        # Handle password change separately
        new_password = request.POST.get('new_password')
        if new_password:
            user.set_password(new_password)
            user.save()
            # Re-login to keep session alive after password change
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)
            # Notify user
            from apps.notifications.services import notify_user
            notify_user(user, 'password_changed', 'Password Changed',
                        'Your password was successfully updated.')
        messages.success(request, 'Profile updated successfully.')
        log_action(user, 'PROFILE_UPDATED', 'authentication', status='success', request=request)
    return render(request, 'auth/profile.html')
```

---

## DRF Authentication Endpoints

```python
# apps/authentication/api_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny

class APILoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        identifier = request.data.get('identifier')
        password = request.data.get('password')
        # Same lockout logic as view above
        # Returns: { "message": "Login successful", "role": "admin" }
        ...

class APILogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.contrib.auth import logout
        logout(request)
        return Response({'message': 'Logged out successfully.'})
```

---

## Security Middleware: Unauthenticated Access

Django's `login_required` decorator and `LoginRequiredMixin` handle this.
For DRF: `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]` in settings ensures all API endpoints require login by default.

---

## Template: `templates/auth/login.html`

```html
{% extends 'base_auth.html' %}
{% block content %}
<div class="container d-flex justify-content-center align-items-center min-vh-100">
  <div class="card shadow p-4" style="width: 400px;">
    <h4 class="text-center mb-4">Inventory System Login</h4>
    {% if messages %}
      {% for message in messages %}
        <div class="alert alert-{{ message.tags }}">{{ message }}</div>
      {% endfor %}
    {% endif %}
    <form method="post">
      {% csrf_token %}
      <div class="mb-3">
        <label class="form-label">Username or Email</label>
        <input type="text" name="identifier" class="form-control" required autofocus>
      </div>
      <div class="mb-3">
        <label class="form-label">Password</label>
        <input type="password" name="password" class="form-control" required>
      </div>
      <button type="submit" class="btn btn-primary w-100">Login</button>
      <a href="{% url 'auth:password_reset' %}" class="d-block text-center mt-3 small">Forgot password?</a>
    </form>
  </div>
</div>
{% endblock %}
```

---

## Audit Actions for This Module

| Action Constant | Triggered When |
|---|---|
| `LOGIN_SUCCESS` | Successful login |
| `LOGIN_FAILED` | Failed login attempt |
| `LOGOUT` | User logs out |
| `PROFILE_UPDATED` | User updates profile |
| `PASSWORD_CHANGED` | User changes password |
| `ACCOUNT_LOCKED` | Account locked after max attempts |
| `PASSWORD_RESET_REQUESTED` | Password reset email sent |
| `PASSWORD_RESET_COMPLETED` | New password set via reset link |
