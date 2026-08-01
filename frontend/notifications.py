"""
docs/11_NOTIFICATIONS.md, translated into the single `frontend` app — no
`apps/notifications/` app created (see docs/project_memory.md §13).

notify_user()/notify_supervisors() are the ONLY code path allowed to
create Notification rows — per 11_NOTIFICATIONS.md's own instruction
("Never create Notification objects directly in other modules").

One deliberate, disclosed simplification vs. the documented design: email
is sent SYNCHRONOUSLY via Django's send_mail(), not via a Celery task's
.delay(). Celery isn't installed and isn't being added until it's
explicitly needed (see docs/project_memory.md §1) — this trades away
background execution, not correctness. Swap _maybe_send_email()'s body
for a .delay() call once a Celery task exists; nothing else in this
module needs to change.

Phase 4 decision: notify_supervisors()'s `role__in=[...]` query used to
have an `is_staff=True OR is_superuser=True` fallback for the pre-Phase-3.7
window when `role` didn't exist on the active AUTH_USER_MODEL. Removed
outright (not kept as defense-in-depth) now that RBAC is being built for
real — `role` is a required field on frontend.User, the only user model
this project will ever run against, so the fallback branch was
unreachable dead code, not a meaningful safety net.
"""
from django.conf import settings as django_settings
from django.core.mail import send_mail

from frontend.models import Notification, SystemSettings, User, UserRole


def notify_user(user, notification_type, title, message, link='', is_critical=False):
    """Create an in-system notification for a specific user."""
    notification = Notification.objects.create(
        recipient=user,
        type=notification_type,
        title=title,
        message=message,
        link=link,
        is_critical=is_critical,
    )
    _maybe_send_email(user, title, message)
    return notification


def notify_supervisors(notification_type, title, message, link='', is_critical=False):
    """Notify all active supervisors and admins."""
    recipients = list(User.objects.filter(
        role__in=[UserRole.ADMIN, UserRole.SUPERVISOR], is_active=True,
    ))

    notifications = []
    for user in recipients:
        n = Notification.objects.create(
            recipient=user,
            type=notification_type,
            title=title,
            message=message,
            link=link,
            is_critical=is_critical,
        )
        notifications.append(n)
        _maybe_send_email(user, title, message)
    return notifications


def _maybe_send_email(user, subject, message):
    """Send email if the recipient has one and system email is enabled.
    Synchronous send_mail() call — see module docstring point 1."""
    settings_obj = SystemSettings.get_settings()
    if settings_obj.email_notifications_enabled and user.email:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Email send failed to {user.email}: {e}")
