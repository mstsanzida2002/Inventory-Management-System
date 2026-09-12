"""Only one DRF BasePermission class exists by design -- `IsAdmin`/
`IsAnyStaff`/`IsOwnerOrAdmin` (docs/02_RBAC.md) are deliberately not
built; nothing in this project's DRF surface needs them yet."""
from rest_framework.permissions import BasePermission

from frontend.models import UserRole


class IsSupervisorOrAbove(BasePermission):
    """Security: matches SupervisorRequiredMixin's gate on the same page --
    two parallel authorization mechanisms for one role check, accepted
    deliberately for this single class, not a general DRF layer."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in [UserRole.ADMIN, UserRole.SUPERVISOR]
        )
