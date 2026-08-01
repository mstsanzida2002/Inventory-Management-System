"""
docs/02_RBAC.md's `apps/rbac/mixins.py`, translated into the single
`frontend` app — no `apps/rbac/` app created (see docs/project_memory.md
§13). Same app-path/route translations as frontend/decorators.py.

Not yet applied to any real class-based view — Phase 5/6/7 wire this into
Products/Purchases/Sales/etc. as each module's views are built. Proven
working here only against a throwaway CBV in frontend/tests.py.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect

from frontend.models import UserRole


class RoleRequiredMixin(LoginRequiredMixin):
    required_roles = []   # Override in subclass

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
