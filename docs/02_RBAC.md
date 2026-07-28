# 👥 Module 02 — Role-Based Access Control (RBAC)
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when adding permission checks to any view,
> API endpoint, or template. Every protected operation must go through these patterns.

---

## Requirements Coverage
`REQ 2.1 → 2.12`

---

## Roles

| Role Constant | Label | Access Level |
|---|---|---|
| `admin` | System Administrator | Full unrestricted access |
| `supervisor` | Inventory Supervisor | Operational + approval access |
| `staff` | Inventory Staff | Day-to-day operations only |

---

## Permission Matrix (Complete)

| Operation | Admin | Supervisor | Staff |
|---|:---:|:---:|:---:|
| Manage users (create/edit/deactivate) | ✅ | ❌ | ❌ |
| Configure system settings | ✅ | ❌ | ❌ |
| Configure AI parameters | ✅ | ❌ | ❌ |
| View audit logs | ✅ | ❌ | ❌ |
| Create/edit products | ✅ | ✅ | ✅ |
| Deactivate products | ✅ | ✅ | ❌ |
| Create/edit categories | ✅ | ✅ | ❌ |
| Manage suppliers | ✅ | ✅ | ❌ |
| Create purchase orders | ✅ | ✅ | ✅ |
| **Approve/reject purchase orders** | ✅ | ✅ | ❌ |
| Receive purchase orders | ✅ | ✅ | ✅ |
| Create sales transactions | ✅ | ✅ | ✅ |
| Cancel sales transactions | ✅ | ✅ | ❌ |
| Create inventory adjustment requests | ✅ | ✅ | ✅ |
| **Approve/reject inventory adjustments** | ✅ | ✅ | ❌ |
| View AI recommendations | ✅ | ✅ | ❌ |
| Generate/export reports | ✅ | ✅ | ❌ |
| View dashboard (role-scoped) | ✅ | ✅ | ✅ |
| View inventory | ✅ | ✅ | ✅ |

---

## Implementation

### `apps/rbac/permissions.py` — DRF Permission Classes

```python
from rest_framework.permissions import BasePermission
from apps.users.models import UserRole

class IsAdmin(BasePermission):
    """Only System Administrators."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == UserRole.ADMIN

class IsSupervisorOrAbove(BasePermission):
    """Supervisors and Admins."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in [
            UserRole.ADMIN, UserRole.SUPERVISOR
        ]

class IsAnyStaff(BasePermission):
    """All authenticated roles (any staff member)."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in [
            UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.STAFF
        ]

class IsOwnerOrAdmin(BasePermission):
    """For profile/personal resource access."""
    def has_object_permission(self, request, view, obj):
        return request.user.role == UserRole.ADMIN or obj == request.user
```

---

### `apps/rbac/decorators.py` — View Decorators

```python
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from apps.users.models import UserRole

def require_role(*roles):
    """
    Usage:
        @require_role('admin')
        @require_role('admin', 'supervisor')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('auth:login')
            if request.user.role not in roles:
                messages.error(request, 'Access denied. You do not have permission to perform this action.')
                return redirect('dashboard:home')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

# Convenience decorators
def admin_required(view_func):
    return require_role(UserRole.ADMIN)(view_func)

def supervisor_required(view_func):
    return require_role(UserRole.ADMIN, UserRole.SUPERVISOR)(view_func)

def staff_required(view_func):
    return require_role(UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.STAFF)(view_func)
```

---

### `apps/rbac/mixins.py` — Class-Based View Mixins

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.contrib import messages
from apps.users.models import UserRole

class RoleRequiredMixin(LoginRequiredMixin):
    required_roles = []   # Override in subclass

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.required_roles and request.user.role not in self.required_roles:
            messages.error(request, 'Access denied.')
            return redirect('dashboard:home')
        return super().dispatch(request, *args, **kwargs)

class AdminRequiredMixin(RoleRequiredMixin):
    required_roles = [UserRole.ADMIN]

class SupervisorRequiredMixin(RoleRequiredMixin):
    required_roles = [UserRole.ADMIN, UserRole.SUPERVISOR]

class AnyStaffMixin(RoleRequiredMixin):
    required_roles = [UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.STAFF]
```

---

## Usage Examples

### Function-Based Views

```python
from apps.rbac.decorators import admin_required, supervisor_required, staff_required

# Admin only
@admin_required
def user_management_view(request):
    ...

# Supervisor and above
@supervisor_required
def approve_purchase_view(request, pk):
    ...

# Any authenticated staff
@staff_required
def create_sale_view(request):
    ...
```

### Class-Based Views

```python
from apps.rbac.mixins import SupervisorRequiredMixin, AdminRequiredMixin

class ApprovePurchaseView(SupervisorRequiredMixin, View):
    def post(self, request, pk):
        ...

class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = 'users/list.html'
```

### DRF API Views

```python
from apps.rbac.permissions import IsAdmin, IsSupervisorOrAbove, IsAnyStaff
from rest_framework.views import APIView

class UserManagementAPIView(APIView):
    permission_classes = [IsAdmin]
    ...

class ApprovePurchaseAPIView(APIView):
    permission_classes = [IsSupervisorOrAbove]
    ...

class CreateSaleAPIView(APIView):
    permission_classes = [IsAnyStaff]
    ...
```

### Template Conditional Rendering

```html
{% if request.user.role == 'admin' %}
  <a href="{% url 'users:list' %}" class="nav-link">User Management</a>
{% endif %}

{% if request.user.role in 'admin,supervisor' %}
  <button class="btn btn-success" id="approve-btn">Approve</button>
{% endif %}
```

---

## Enforcing at API Level — Global Default

In `config/settings/base.py`, all API views require authentication by default:

```python
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

Every API view that needs role checking adds its class-level `permission_classes`:

```python
class AuditLogListView(ListAPIView):
    permission_classes = [IsAdmin]      # Overrides global default
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.all().order_by('-timestamp')
```

---

## Access-Denied Response

- **Template views:** Redirect to dashboard with `messages.error()`
- **API views:** Return `HTTP 403 Forbidden` with `{"detail": "You do not have permission to perform this action."}`
