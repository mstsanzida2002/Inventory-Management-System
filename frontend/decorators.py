from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from frontend.models import UserRole


def require_role(*roles):
    """Restricts a view to users whose role is in `roles`."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('frontend:login')
            # Security: denies access when the user's role isn't in roles.
            if request.user.role not in roles:
                messages.error(request, 'Access denied. You do not have permission to perform this action.')
                return redirect('frontend:dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def admin_required(view_func):
    return require_role(UserRole.ADMIN)(view_func)


def supervisor_required(view_func):
    return require_role(UserRole.ADMIN, UserRole.SUPERVISOR)(view_func)


def staff_required(view_func):
    return require_role(UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.STAFF)(view_func)
