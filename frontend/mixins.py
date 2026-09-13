from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect

from frontend.models import UserRole


class RoleRequiredMixin(LoginRequiredMixin):
    required_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        # Security: denies access when the user's role isn't in required_roles.
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
