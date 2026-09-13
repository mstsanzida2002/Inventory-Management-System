from rest_framework.permissions import BasePermission

from frontend.models import UserRole


class IsSupervisorOrAbove(BasePermission):
    """Grants access to authenticated Admin or Supervisor users only."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in [UserRole.ADMIN, UserRole.SUPERVISOR]
        )
