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


def notify_admins(notification_type, title, message, link='', is_critical=False):
    """Notify every active Admin — Phase 8.98e, for the "Admin is told a
    password changed" requirement. Same shape as notify_supervisors()
    (which already includes admins) but Admin-only, since this alert is
    specifically about administrative awareness, not the broader
    supervisor-approval audience. Reuses the already-documented
    NotificationType.PASSWORD_CHANGED (11_NOTIFICATIONS.md) for a second
    recipient set rather than inventing a new type — same real-world
    event, different audience, matching notify_user()'s own call for the
    acting user."""
    recipients = list(User.objects.filter(role=UserRole.ADMIN, is_active=True))

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


def send_new_user_credentials_email(user, password):
    """Phase 8.98e — a brand-new, admin-created user's only way to ever
    learn their own password: the Admin who created the account never
    chooses or sees it (UserListCreateView.post(), frontend/views.py).

    Deliberately NOT built on notify_user(): that function stores its
    exact message text in a Notification row, and this phase's explicit,
    hard security rule is that the generated password must never appear
    in a notification or audit log — not even the new user's own (a
    Notification row is regular application data, readable by anything
    with DB access, unlike a transactional email that exists once and
    isn't persisted by this app at all). So this sends a real,
    credentials-only email directly via send_mail() — the exact same
    primitive _maybe_send_email() below already uses — and creates no
    Notification row at all. 11_NOTIFICATIONS.md has no documented type
    for "account created" either way, matching this project's existing
    precedent of not inventing an undocumented notification type (see
    PurchaseService.cancel()/reject()'s own "logs but doesn't notify"
    reasoning, project_memory.md §12).

    Sent unconditionally — deliberately ignoring
    SystemSettings.email_notifications_enabled, unlike every other email
    in this module. That flag is a discretionary alert-noise preference;
    this is the sole delivery channel for a credential nobody (not even
    an Admin) can retrieve or resend afterward, so it can't be silently
    skipped by a system-wide toggle. Disclosed decision, see
    project_memory.md §13."""
    if not user.email:
        return False
    subject = "Your Stockwell Account Has Been Created"
    message = (
        f"Hello {user.full_name},\n\n"
        f"An administrator has created a Stockwell account for you.\n\n"
        f"Username: {user.username}\n"
        f"Temporary password: {password}\n\n"
        f"Please log in and change this password from your Profile page as "
        f"soon as possible.\n\n— Stockwell"
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        # Same fail-open shape as _maybe_send_email() below — logs the
        # exception (a connection/auth failure message), never the
        # message body, so this can't become a password-leak vector.
        print(f"Credentials email send failed to {user.email}: {e}")
        return False


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
