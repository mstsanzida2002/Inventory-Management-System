"""docs/02_RBAC.md's `apps/rbac/mixins.py`, translated into this single
`frontend` app -- no separate `apps/rbac/` app exists; same route
translations as frontend/decorators.py.

Security: the actual RBAC gate on every role-restricted view in this
project -- AdminRequiredMixin/SupervisorRequiredMixin/AnyStaffMixin are
applied across frontend/views.py (BUG-93, docs/bugsfound.md -- this
docstring previously claimed the opposite)."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect

from frontend.models import UserRole


class RoleRequiredMixin(LoginRequiredMixin):
    required_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.required_roles and request.user.role not in self.required_roles:
            messages.error(request, 'Access denied.')
            return redirect('frontend:dashboard')
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    required_roles = [UserRole.ADMIN]


class SupervisorRequiredMixin(RoleRequiredMixin):
    required_roles = [UserRole.ADMIN, UserRole.SUPERVISOR]


class AnyStaffMixin(RoleRequiredMixin):
    required_roles = [UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.STAFF]
