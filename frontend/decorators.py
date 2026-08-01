"""
docs/02_RBAC.md's `apps/rbac/decorators.py`, translated into the single
`frontend` app — no `apps/rbac/` app created (see docs/project_memory.md
§13). `apps.users.models.UserRole` -> `frontend.models.UserRole`;
`dashboard:home` -> `frontend:dashboard` (only one dashboard route exists,
see docs/project_memory.md §17 gap list — no per-role dashboard routes);
`auth:login` -> `frontend:login` (this project's login route lives in the
`frontend` namespace, not a separate `auth`/`accounts` one — see
docs/project_memory.md §12 bug #1).

Not yet applied to any real view — Phase 5/6/7 wire this into
Products/Purchases/Sales/etc. as each module's views are built. Proven
working here only against a throwaway view in frontend/tests.py.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from frontend.models import UserRole


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
                return redirect('frontend:login')
            if request.user.role not in roles:
                messages.error(request, 'Access denied. You do not have permission to perform this action.')
                return redirect('frontend:dashboard')
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
