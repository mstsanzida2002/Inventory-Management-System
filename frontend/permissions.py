"""
docs/02_RBAC.md's DRF `BasePermission` classes — only one built. Phase 9
decided against a general DRF layer but pre-committed one small, read-only
AI slice to Phase 10 (see docs/project_memory.md §13); this is that
slice's only permission class. `IsAdmin`/`IsAnyStaff`/`IsOwnerOrAdmin`
(also documented in 02_RBAC.md) are deliberately not built — nothing in
this project's DRF surface needs them yet, and adding unused permission
classes ahead of a real caller is exactly the kind of speculative
scaffolding Phase 9 rejected in the first place.
"""
from rest_framework.permissions import BasePermission

from frontend.models import UserRole


class IsSupervisorOrAbove(BasePermission):
    """Supervisors and Admins — matches SupervisorRequiredMixin, the same
    gate Phase 8.99j already put on the Slow-Moving & Dead Stock page
    these endpoints serve. Two independent authorization mechanisms
    (this one and the mixin) now exist for the exact same role check —
    the parallel-RBAC-paths cost Phase 9 flagged for a *general* DRF
    layer, accepted here deliberately for one class covering one page,
    not the ~40-endpoint version that was rejected."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in [UserRole.ADMIN, UserRole.SUPERVISOR]
        )
