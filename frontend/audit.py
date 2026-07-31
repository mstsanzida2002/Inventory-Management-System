"""
docs/13_AUDIT.md, translated into the single `frontend` app — no
`apps/audit/` app created (see docs/project_memory.md §13: this project
deliberately stays single-app at this stage).

log_action() is the ONLY code path allowed to create AuditLog rows — per
13_AUDIT.md's own instruction ("Use log_action() ... to record every
significant operation").
"""
from frontend.models import AuditLog


def log_action(user, action, module, affected_id=None, status='success', details=None, request=None):
    """
    Call this everywhere a significant operation happens.

    Args:
        user: User instance or None (for system tasks)
        action: string constant e.g. 'LOGIN_SUCCESS', 'PO_APPROVED' — see the
            constants below
        module: string e.g. 'authentication', 'purchases'
        affected_id: PK of the affected record (optional)
        status: 'success' or 'failure'
        details: dict of extra context (optional)
        request: Django request object for IP extraction (optional) — no
            views exist yet to pass one, so this is always None for now
    """
    ip = None
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')

    return AuditLog.objects.create(
        user=user,
        action=action,
        module=module,
        affected_id=affected_id,
        status=status,
        details=details or {},
        ip_address=ip,
    )


# All Action Constants — 13_AUDIT.md "All Action Constants" (originally
# `apps/audit/constants.py`), flat module-level constants exactly as
# documented, just consolidated into this single-app module.

# Authentication
LOGIN_SUCCESS = 'LOGIN_SUCCESS'
LOGIN_FAILED = 'LOGIN_FAILED'
LOGOUT = 'LOGOUT'
PROFILE_UPDATED = 'PROFILE_UPDATED'
PASSWORD_CHANGED = 'PASSWORD_CHANGED'
ACCOUNT_LOCKED = 'ACCOUNT_LOCKED'
PASSWORD_RESET_REQUESTED = 'PASSWORD_RESET_REQUESTED'
PASSWORD_RESET_COMPLETED = 'PASSWORD_RESET_COMPLETED'

# User Management
USER_CREATED = 'USER_CREATED'
USER_UPDATED = 'USER_UPDATED'
USER_DEACTIVATED = 'USER_DEACTIVATED'
USER_REACTIVATED = 'USER_REACTIVATED'
USER_ROLE_CHANGED = 'USER_ROLE_CHANGED'

# Products
PRODUCT_CREATED = 'PRODUCT_CREATED'
PRODUCT_UPDATED = 'PRODUCT_UPDATED'
PRODUCT_DEACTIVATED = 'PRODUCT_DEACTIVATED'
CATEGORY_CREATED = 'CATEGORY_CREATED'
CATEGORY_UPDATED = 'CATEGORY_UPDATED'

# Suppliers
SUPPLIER_CREATED = 'SUPPLIER_CREATED'
SUPPLIER_UPDATED = 'SUPPLIER_UPDATED'
SUPPLIER_DEACTIVATED = 'SUPPLIER_DEACTIVATED'

# Purchases
PO_CREATED = 'PO_CREATED'
PO_SUBMITTED = 'PO_SUBMITTED'
PO_APPROVED = 'PO_APPROVED'
PO_REJECTED = 'PO_REJECTED'
PO_RECEIVED = 'PO_RECEIVED'
PO_CANCELLED = 'PO_CANCELLED'

# Sales
SALE_CREATED = 'SALE_CREATED'
SALE_CANCELLED = 'SALE_CANCELLED'
SALE_INVOICE_PRINTED = 'SALE_INVOICE_PRINTED'

# Inventory
INVENTORY_VIEWED = 'INVENTORY_VIEWED'
LOW_STOCK_ALERT_SENT = 'LOW_STOCK_ALERT_SENT'
OUT_OF_STOCK_ALERT_SENT = 'OUT_OF_STOCK_ALERT_SENT'
PHYSICAL_COUNT_PERFORMED = 'PHYSICAL_COUNT_PERFORMED'

# Adjustments
ADJUSTMENT_REQUESTED = 'ADJUSTMENT_REQUESTED'
ADJUSTMENT_APPROVED = 'ADJUSTMENT_APPROVED'
ADJUSTMENT_REJECTED = 'ADJUSTMENT_REJECTED'

# Reports
REPORT_GENERATED = 'REPORT_GENERATED'
REPORT_EXPORTED_PDF = 'REPORT_EXPORTED_PDF'
REPORT_EXPORTED_CSV = 'REPORT_EXPORTED_CSV'

# AI
AI_MODEL_RETRAINED = 'AI_MODEL_RETRAINED'
AI_MODEL_RETRAIN_FAILED = 'AI_MODEL_RETRAIN_FAILED'
AI_FORECASTS_GENERATED = 'AI_FORECASTS_GENERATED'
AI_CLASSIFICATION_RUN = 'AI_CLASSIFICATION_RUN'
AI_CLASSIFICATION_FAILED = 'AI_CLASSIFICATION_FAILED'

# Settings
SETTINGS_UPDATED = 'SETTINGS_UPDATED'
