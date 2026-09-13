from django.conf import settings as django_settings
from django.core.mail import send_mail

from frontend.models import Notification, SystemSettings, User, UserRole


# Rule: the notify_* helpers are the only path that creates Notification rows.
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
    # Assumption: role is required on User; no is_staff fallback needed.
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
    """Notifies every active Admin only, not supervisors."""
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
    """Emails a new user's password directly; creates no Notification row."""
    # Security: password must never enter a Notification row or audit log.
    # Rule: ignores email_notifications_enabled -- this is the only delivery path.
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
        # Security: logs only the exception, never the message body.
        print(f"Credentials email send failed to {user.email}: {e}")
        return False


def _maybe_send_email(user, subject, message):
    # Assumption: send_mail() runs synchronously in-request; no retry.
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
