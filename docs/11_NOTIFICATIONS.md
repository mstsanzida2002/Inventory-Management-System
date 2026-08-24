# 🔔 Module 11 — Notification Management
# AI-Powered Smart Inventory Management System

> **Claude Code:** Use `notify_user()` and `notify_supervisors()` from
> `apps/notifications/services.py` everywhere you need to send a notification.
> Never create Notification objects directly in other modules.
>
> **Corrected (docs/bugsfound.md):** this file's `@shared_task(name=
> 'notifications.send_email')` reference code below is unbuilt — no
> Celery exists anywhere in this project. Email sends run synchronously,
> in the same request, from `frontend/notifications.py`'s own
> `_maybe_send_email()`, not as a queued background task.

---

## Requirements Coverage
`REQ 13.1 → 13.15`

---

## Notification Types

| Type Constant | Trigger |
|---|---|
| `low_stock` | Inventory drops to/below reorder level |
| `out_of_stock` | Inventory reaches zero |
| `po_pending` | PO submitted, awaiting supervisor approval |
| `po_approved` | PO approved — notify creator |
| `po_rejected` | PO rejected — notify creator |
| `adj_pending` | Adjustment request awaiting approval |
| `adj_approved` | Adjustment approved |
| `ai_replenish` | AI forecasting recommends replenishment |
| `ai_slow` | AI classifies product as slow-moving |
| `ai_dead` | AI classifies product as dead stock |
| `password_changed` | User changed password |
| `sale_completed` | Sale transaction confirmed |

---

## Notification Service

```python
# apps/notifications/services.py
from apps.notifications.models import Notification, NotificationType
from django.contrib.auth import get_user_model

User = get_user_model()


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
    # Also send email if enabled
    _maybe_send_email(user, title, message)
    return notification


def notify_supervisors(notification_type, title, message, link='', is_critical=False):
    """Notify all active supervisors and admins."""
    from apps.users.models import UserRole
    recipients = User.objects.filter(
        role__in=[UserRole.ADMIN, UserRole.SUPERVISOR],
        is_active=True
    )
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


def notify_all_staff(notification_type, title, message, link=''):
    """Notify all active users."""
    for user in User.objects.filter(is_active=True):
        notify_user(user, notification_type, title, message, link)


def _maybe_send_email(user, subject, message):
    """Send email notification if user has email and system email is enabled."""
    from apps.settings_manager.models import SystemSettings
    settings_obj = SystemSettings.get_settings()
    if settings_obj.email_notifications_enabled and user.email:
        from apps.notifications.tasks import send_email_notification_task
        send_email_notification_task.delay(
            to_email=user.email,
            subject=subject,
            message=message
        )
```

---

## Celery Email Task

```python
# apps/notifications/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

@shared_task(name='notifications.send_email')
def send_email_notification_task(to_email, subject, message):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"Email send failed to {to_email}: {e}")
```

---

## Views

```python
# apps/notifications/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from apps.notifications.models import Notification

@login_required
def notification_list_view(request):
    notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')
    return render(request, 'notifications/list.html', {'notifications': notifications})

@login_required
def mark_read_view(request, pk):
    Notification.objects.filter(pk=pk, recipient=request.user).update(is_read=True)
    return JsonResponse({'status': 'ok'})

@login_required
def mark_all_read_view(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok'})

@login_required
def unread_count_view(request):
    """For navbar badge polling."""
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'unread_count': count})
```

---

## DRF API

```python
# apps/notifications/api_views.py
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer

class NotificationListAPIView(ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')

class MarkReadAPIView(APIView):
    def patch(self, request, pk):
        Notification.objects.filter(pk=pk, recipient=request.user).update(is_read=True)
        return Response({'status': 'read'})

class MarkAllReadAPIView(APIView):
    def patch(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'all read'})
```

---

## Frontend: Notification Polling

```javascript
// static/js/notifications.js
function pollNotifications() {
  fetch('/notifications/unread-count/')
    .then(r => r.json())
    .then(data => {
      const badge = document.getElementById('notif-badge');
      if (data.unread_count > 0) {
        badge.textContent = data.unread_count;
        badge.style.display = 'inline';
      } else {
        badge.style.display = 'none';
      }
    });
}
// Poll every 30 seconds
setInterval(pollNotifications, 30000);
pollNotifications();
```

---

## Navbar Notification Dropdown (Partial Template)

```html
<!-- templates/partials/_notifications_dropdown.html -->
<li class="nav-item dropdown">
  <a class="nav-link position-relative" href="#" data-bs-toggle="dropdown">
    <i class="bi bi-bell"></i>
    <span id="notif-badge" class="badge bg-danger rounded-pill position-absolute top-0 start-100"
          style="display:none;"></span>
  </a>
  <ul class="dropdown-menu dropdown-menu-end" style="min-width: 320px;">
    {% for notif in recent_notifications %}
      <li class="dropdown-item {% if not notif.is_read %}fw-bold{% endif %}">
        <small class="text-muted">{{ notif.created_at|timesince }} ago</small>
        <div>{{ notif.title }}</div>
        <small>{{ notif.message|truncatechars:80 }}</small>
      </li>
    {% empty %}
      <li class="dropdown-item text-muted">No notifications</li>
    {% endfor %}
    <li><hr class="dropdown-divider"></li>
    <li><a class="dropdown-item text-center" href="{% url 'notifications:list' %}">View all</a></li>
  </ul>
</li>
```
