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
# BUG-65 (docs/bugsfound.md) — DRIFTED, not dead: a password reset via
# the emailed link genuinely is audited
# (StockwellPasswordResetConfirmView.form_valid() -> _record_password_
# change()), just consolidated under the more general PASSWORD_CHANGED
# below rather than these two dedicated constants. Left defined-but-
# unused deliberately rather than removed: 13_AUDIT.md still names them,
# and consolidating under PASSWORD_CHANGED is a disclosed decision, not
# an oversight — see docs/project_memory.md for the write-up.
PASSWORD_RESET_REQUESTED = 'PASSWORD_RESET_REQUESTED'
PASSWORD_RESET_COMPLETED = 'PASSWORD_RESET_COMPLETED'

# User Management
USER_CREATED = 'USER_CREATED'
# BUG-65 — PHANTOM, not just unused: no view exists anywhere to edit an
# existing user's fields or change their role after creation
# (frontend/urls.py's users/ routes are List/Create/Deactivate/
# Reactivate/Delete/Resend-credentials only). Not building that view for
# this pass (out of scope) — these two constants stay defined, genuinely
# unreachable, and disclosed as such (docs/13_AUDIT.md REQ 16.3 is
# PARTIAL, not fully closed, until/unless that view exists).
USER_UPDATED = 'USER_UPDATED'
USER_DEACTIVATED = 'USER_DEACTIVATED'
USER_REACTIVATED = 'USER_REACTIVATED'
USER_ROLE_CHANGED = 'USER_ROLE_CHANGED'
USER_DELETED = 'USER_DELETED'
# Phase 8.99f-7 — same disclosure as USER_DELETED above: not in
# 13_AUDIT.md, added because a resend with no audit trail at all would be
# a worse gap than the one it closes (a real SMTP failure is now routine
# enough, per Phase 8.99f-5's own live one, that "resend" is a real
# operational action worth recording who triggered it and when).
USER_CREDENTIALS_RESENT = 'USER_CREDENTIALS_RESENT'

# Products
PRODUCT_CREATED = 'PRODUCT_CREATED'
PRODUCT_UPDATED = 'PRODUCT_UPDATED'
PRODUCT_DEACTIVATED = 'PRODUCT_DEACTIVATED'
# Phase 8.99i — Reactivate/Delete have no 13_AUDIT.md entry (that doc only
# lists CREATED/UPDATED/DEACTIVATED for all three of Products/Categories/
# Suppliers). Same disclosed-addition treatment as USER_DELETED/USER_
# CREDENTIALS_RESENT (§13): an action with no audit trail is a worse gap
# than an undocumented constant.
PRODUCT_REACTIVATED = 'PRODUCT_REACTIVATED'
PRODUCT_DELETED = 'PRODUCT_DELETED'
CATEGORY_CREATED = 'CATEGORY_CREATED'
CATEGORY_UPDATED = 'CATEGORY_UPDATED'
# Phase 8.99i — CATEGORY_DEACTIVATED isn't in 13_AUDIT.md either (only
# CATEGORY_CREATED/UPDATED are) even though Categories always had a
# deactivate concept (is_active on the model, a "status" field on the Add
# form) — the view to actually flip it just never existed before this
# phase. Disclosed the same way as PRODUCT_REACTIVATED/DELETED above.
CATEGORY_DEACTIVATED = 'CATEGORY_DEACTIVATED'
CATEGORY_REACTIVATED = 'CATEGORY_REACTIVATED'
CATEGORY_DELETED = 'CATEGORY_DELETED'

# Suppliers
SUPPLIER_CREATED = 'SUPPLIER_CREATED'
SUPPLIER_UPDATED = 'SUPPLIER_UPDATED'
SUPPLIER_DEACTIVATED = 'SUPPLIER_DEACTIVATED'
SUPPLIER_REACTIVATED = 'SUPPLIER_REACTIVATED'
SUPPLIER_DELETED = 'SUPPLIER_DELETED'

# Purchases
PO_CREATED = 'PO_CREATED'
PO_SUBMITTED = 'PO_SUBMITTED'
PO_APPROVED = 'PO_APPROVED'
PO_REJECTED = 'PO_REJECTED'
PO_RECEIVED = 'PO_RECEIVED'
PO_CANCELLED = 'PO_CANCELLED'

# Sales
SALE_CREATED = 'SALE_CREATED'
# Phase 8.99b — new, following 13_AUDIT.md's own PO_SUBMITTED/PO_APPROVED/
# PO_REJECTED naming exactly, for the same 3 new transitions on the
# now-mirrored Sale approval workflow.
SALE_SUBMITTED = 'SALE_SUBMITTED'
SALE_APPROVED = 'SALE_APPROVED'
SALE_REJECTED = 'SALE_REJECTED'
SALE_CANCELLED = 'SALE_CANCELLED'
# BUG-65 (docs/bugsfound.md) — now fired (SaleTransactionPDFView.get()).
SALE_INVOICE_PRINTED = 'SALE_INVOICE_PRINTED'

# Inventory
# BUG-65 (docs/bugsfound.md) — INVENTORY_VIEWED/LOW_STOCK_ALERT_SENT/
# OUT_OF_STOCK_ALERT_SENT are now fired (InventoryListView.get() and
# InventoryService._send_low_stock_notification(), respectively).
INVENTORY_VIEWED = 'INVENTORY_VIEWED'
LOW_STOCK_ALERT_SENT = 'LOW_STOCK_ALERT_SENT'
OUT_OF_STOCK_ALERT_SENT = 'OUT_OF_STOCK_ALERT_SENT'
# BUG-65 — DRIFTED, not dead: physical counts are real, handled through
# InventoryAdjustment's COUNT_CORRECTION reason code and logged under
# ADJUSTMENT_REQUESTED/ADJUSTMENT_APPROVED instead of this dedicated
# constant, because the feature was folded into the general adjustment
# workflow rather than built as its own flow. Left defined-but-unused
# deliberately — see docs/project_memory.md for the write-up.
PHYSICAL_COUNT_PERFORMED = 'PHYSICAL_COUNT_PERFORMED'

# Adjustments
ADJUSTMENT_REQUESTED = 'ADJUSTMENT_REQUESTED'
ADJUSTMENT_APPROVED = 'ADJUSTMENT_APPROVED'
ADJUSTMENT_REJECTED = 'ADJUSTMENT_REJECTED'
# Phase 12 — a single audit entry for the AUTO-outcome create path
# (AdjustmentService.create()), distinct from ADJUSTMENT_APPROVED: no
# human approved this, a policy authorised it automatically, and that
# distinction matters when reading the trail back later.
ADJUSTMENT_AUTO_POSTED = 'ADJUSTMENT_AUTO_POSTED'
# Phase 12.1 §4 — fires when the cumulative cap deflects what would
# otherwise have been an AUTO match; "the trail that makes the control
# provable" (§4's own words) against salami-slicing.
ADJUSTMENT_AUTO_DEFLECTED = 'ADJUSTMENT_AUTO_DEFLECTED'

# Phase 12 — Approval Policy (§4's own instruction: "the policy table
# must be at least as auditable as the transactions it governs" — an
# admin who can silently raise the supervisor ceiling has defeated the
# entire control).
APPROVAL_POLICY_CREATED = 'APPROVAL_POLICY_CREATED'
APPROVAL_POLICY_UPDATED = 'APPROVAL_POLICY_UPDATED'
APPROVAL_POLICY_DEACTIVATED = 'APPROVAL_POLICY_DEACTIVATED'
APPROVAL_POLICY_REACTIVATED = 'APPROVAL_POLICY_REACTIVATED'

# Reports
REPORT_GENERATED = 'REPORT_GENERATED'
REPORT_EXPORTED_PDF = 'REPORT_EXPORTED_PDF'
REPORT_EXPORTED_CSV = 'REPORT_EXPORTED_CSV'

# AI
AI_MODEL_RETRAINED = 'AI_MODEL_RETRAINED'
AI_MODEL_RETRAIN_FAILED = 'AI_MODEL_RETRAIN_FAILED'
AI_FORECASTS_GENERATED = 'AI_FORECASTS_GENERATED'
# BUG-82 (docs/bugsfound.md) — fires whenever an admin changes
# any of the stagnation-index knowledge-base fields on SystemSettings
# (the four factor weights, both index thresholds, target_days_of_cover,
# extreme_coverage_days, min_observation_days, min_sale_events). Separate
# from the generic SETTINGS_UPDATED below because these specific fields
# directly change what SLOW/DEAD means for every product in the system —
# worth being able to find without scanning every settings change.
AI_CLASSIFIER_WEIGHTS_CHANGED = 'AI_CLASSIFIER_WEIGHTS_CHANGED'
AI_CLASSIFICATION_RUN = 'AI_CLASSIFICATION_RUN'
AI_CLASSIFICATION_FAILED = 'AI_CLASSIFICATION_FAILED'
# Phase 10 — DEAD_STOCK_DETECTION.md's own Audit Actions table names this
# alongside the two above but it was never added when they were; added now.
AI_PRODUCT_RECLASSIFIED = 'AI_PRODUCT_RECLASSIFIED'
# Phase 11 — DEMAND_FORECASTING.md's own Audit Actions table.
# AI_FORECAST_REPORT_EXPORTED (also in that table) isn't added: the
# generic REPORT_EXPORTED_PDF/REPORT_EXPORTED_CSV below already fire for
# every report type ReportExportView serves, ai-forecasts included —
# confirmed by reading that view before deciding a forecast-specific
# constant would just be dead code next to the one already covering it.
AI_ACTUAL_DEMAND_BACKFILLED = 'AI_ACTUAL_DEMAND_BACKFILLED'

# Settings
SETTINGS_UPDATED = 'SETTINGS_UPDATED'
