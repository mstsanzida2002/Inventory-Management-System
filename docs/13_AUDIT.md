# 🗂️ Module 13 — Audit Log Management
# AI-Powered Smart Inventory Management System

> **Claude Code:** Use `log_action()` from `apps/audit/services.py` to record
> every significant operation. Audit records are IMMUTABLE — the model prevents
> updates and deletes at the ORM level.

---

## Requirements Coverage
`REQ 16.1 → 16.12`

---

## Rules

- Audit logs are **read-only** — no update, no delete (enforced in model)
- Only System Administrator can view the full audit log
- Every record includes: user, timestamp, action, module, affected_id, status, details (JSON)
- Logs remain permanently available unless archived by admin

---

## The `log_action()` Service

```python
# apps/audit/services.py
from apps.audit.models import AuditLog

def log_action(user, action, module, affected_id=None, status='success', details=None, request=None):
    """
    Call this everywhere a significant operation happens.

    Args:
        user: User instance or None (for system/Celery tasks)
        action: string constant e.g. 'LOGIN_SUCCESS', 'PO_APPROVED'
        module: string e.g. 'authentication', 'purchases'
        affected_id: PK of the affected record (optional)
        status: 'success' or 'failure'
        details: dict of extra context (optional)
        request: Django request object for IP extraction (optional)
    """
    ip = None
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')

    AuditLog.objects.create(
        user=user,
        action=action,
        module=module,
        affected_id=affected_id,
        status=status,
        details=details or {},
        ip_address=ip,
    )
```

---

## All Action Constants

Group them in `apps/audit/constants.py`:

```python
# Authentication
LOGIN_SUCCESS           = 'LOGIN_SUCCESS'
LOGIN_FAILED            = 'LOGIN_FAILED'
LOGOUT                  = 'LOGOUT'
PROFILE_UPDATED         = 'PROFILE_UPDATED'
PASSWORD_CHANGED        = 'PASSWORD_CHANGED'
ACCOUNT_LOCKED          = 'ACCOUNT_LOCKED'
PASSWORD_RESET_REQUESTED= 'PASSWORD_RESET_REQUESTED'
PASSWORD_RESET_COMPLETED= 'PASSWORD_RESET_COMPLETED'

# User Management
USER_CREATED            = 'USER_CREATED'
USER_UPDATED            = 'USER_UPDATED'
USER_DEACTIVATED        = 'USER_DEACTIVATED'
USER_REACTIVATED        = 'USER_REACTIVATED'
USER_ROLE_CHANGED       = 'USER_ROLE_CHANGED'

# Products
PRODUCT_CREATED         = 'PRODUCT_CREATED'
PRODUCT_UPDATED         = 'PRODUCT_UPDATED'
PRODUCT_DEACTIVATED     = 'PRODUCT_DEACTIVATED'
CATEGORY_CREATED        = 'CATEGORY_CREATED'
CATEGORY_UPDATED        = 'CATEGORY_UPDATED'

# Suppliers
SUPPLIER_CREATED        = 'SUPPLIER_CREATED'
SUPPLIER_UPDATED        = 'SUPPLIER_UPDATED'
SUPPLIER_DEACTIVATED    = 'SUPPLIER_DEACTIVATED'

# Purchases
PO_CREATED              = 'PO_CREATED'
PO_SUBMITTED            = 'PO_SUBMITTED'
PO_APPROVED             = 'PO_APPROVED'
PO_REJECTED             = 'PO_REJECTED'
PO_RECEIVED             = 'PO_RECEIVED'
PO_CANCELLED            = 'PO_CANCELLED'

# Sales
SALE_CREATED            = 'SALE_CREATED'
SALE_CANCELLED          = 'SALE_CANCELLED'
SALE_INVOICE_PRINTED    = 'SALE_INVOICE_PRINTED'

# Inventory
INVENTORY_VIEWED        = 'INVENTORY_VIEWED'
LOW_STOCK_ALERT_SENT    = 'LOW_STOCK_ALERT_SENT'
OUT_OF_STOCK_ALERT_SENT = 'OUT_OF_STOCK_ALERT_SENT'
PHYSICAL_COUNT_PERFORMED= 'PHYSICAL_COUNT_PERFORMED'

# Adjustments
ADJUSTMENT_REQUESTED    = 'ADJUSTMENT_REQUESTED'
ADJUSTMENT_APPROVED     = 'ADJUSTMENT_APPROVED'
ADJUSTMENT_REJECTED     = 'ADJUSTMENT_REJECTED'

# Reports
REPORT_GENERATED        = 'REPORT_GENERATED'
REPORT_EXPORTED_PDF     = 'REPORT_EXPORTED_PDF'
REPORT_EXPORTED_CSV     = 'REPORT_EXPORTED_CSV'

# AI
AI_MODEL_RETRAINED          = 'AI_MODEL_RETRAINED'
AI_MODEL_RETRAIN_FAILED     = 'AI_MODEL_RETRAIN_FAILED'
AI_FORECASTS_GENERATED      = 'AI_FORECASTS_GENERATED'
AI_CLASSIFICATION_RUN       = 'AI_CLASSIFICATION_RUN'
AI_CLASSIFICATION_FAILED    = 'AI_CLASSIFICATION_FAILED'

# Settings
SETTINGS_UPDATED        = 'SETTINGS_UPDATED'
```

---

## Views (Admin Only)

```python
# apps/audit/views.py
from django.shortcuts import render
from apps.rbac.decorators import admin_required
from apps.audit.models import AuditLog

@admin_required
def audit_log_list_view(request):
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')

    # Filters
    module = request.GET.get('module')
    action = request.GET.get('action')
    user_id = request.GET.get('user')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if module:
        logs = logs.filter(module=module)
    if action:
        logs = logs.filter(action=action)
    if user_id:
        logs = logs.filter(user_id=user_id)
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)

    return render(request, 'audit/list.html', {
        'logs': logs[:500],
        'modules': AuditLog.objects.values_list('module', flat=True).distinct(),
    })
```

---

## Serializer

```python
# apps/audit/serializers.py
from rest_framework import serializers
from apps.audit.models import AuditLog

class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True, default='System')

    class Meta:
        model = AuditLog
        fields = ['id', 'user_name', 'action', 'module', 'affected_id',
                  'status', 'details', 'ip_address', 'timestamp']
        read_only_fields = fields   # Fully read-only
```

---

## Usage Examples

```python
# In a view
from apps.audit.services import log_action

# Simple action
log_action(request.user, 'PO_APPROVED', 'purchases', affected_id=po.pk, status='success', request=request)

# With extra details
log_action(request.user, 'ADJUSTMENT_APPROVED', 'adjustments', affected_id=adj.pk,
           status='success', details={'quantity': adj.quantity, 'type': adj.adjustment_type}, request=request)

# System/Celery task (no user)
log_action(None, 'AI_FORECASTS_GENERATED', 'ai_forecasting', status='success',
           details={'product_count': 45, 'timestamp': str(timezone.now())})

# Failed operation
try:
    do_something()
except Exception as e:
    log_action(request.user, 'PO_APPROVED', 'purchases', affected_id=po.pk,
               status='failure', details={'error': str(e)}, request=request)
    raise
```
