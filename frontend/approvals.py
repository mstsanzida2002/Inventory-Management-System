from decimal import Decimal

from django.utils import timezone
from datetime import timedelta

from frontend.models import (
    ApprovalOutcome,
    ApprovalPolicy,
    ApprovalTxType,
    InventoryAdjustment,
    InventoryRecord,
    PurchaseOrder,
    SaleTransaction,
)

# Rule: migrations carry their own copy of this list; never import it.
DEFAULT_APPROVAL_POLICIES = [
    {
        "name": "Unexplained shrinkage — any value", "transaction_type": ApprovalTxType.ADJUSTMENT,
        "reason_code": "shrinkage_unknown", "required_level": ApprovalOutcome.ADMIN, "priority": 10,
        "notes": "The single most common fraud vector this phase exists to close: "
                 "shrinkage laundered through a self-approved adjustment.",
    },
    {
        "name": "Damage adjustment up to ৳5,000", "transaction_type": ApprovalTxType.ADJUSTMENT,
        "reason_code": "damage", "max_value": Decimal("5000.00"), "required_level": ApprovalOutcome.SUPERVISOR, "priority": 30,
    },
    {
        "name": "Expiry adjustment up to ৳5,000", "transaction_type": ApprovalTxType.ADJUSTMENT,
        "reason_code": "expiry", "max_value": Decimal("5000.00"), "required_level": ApprovalOutcome.SUPERVISOR, "priority": 31,
    },
    {
        "name": "Small, low-variance adjustment", "transaction_type": ApprovalTxType.ADJUSTMENT,
        "max_value": Decimal("500.00"), "max_variance_pct": Decimal("2.00"),
        "required_level": ApprovalOutcome.AUTO, "priority": 40,
        # Rule: caps AUTO value at ৳2,000 per product per 30 days.
        "cumulative_window_days": 30, "cumulative_value_cap": Decimal("2000.00"),
        "notes": "The lever that makes this a policy engine, not just a permission "
                 "wall: routine, low-value, low-variance adjustments post immediately, no human approval. "
                 "Capped at ৳2,000 per product per 30 days (Phase 12.1 §4) so this can't be salami-sliced.",
    },
    {
        "name": "All other adjustments", "transaction_type": ApprovalTxType.ADJUSTMENT,
        "required_level": ApprovalOutcome.SUPERVISOR, "priority": 50,
        "notes": "Catch-all — anything not matched by a more specific rule above.",
    },
    {
        "name": "Purchase order up to ৳50,000", "transaction_type": ApprovalTxType.PURCHASE_ORDER,
        "max_value": Decimal("50000.00"), "required_level": ApprovalOutcome.SUPERVISOR, "priority": 60,
    },
    {
        "name": "Purchase order above ৳50,000", "transaction_type": ApprovalTxType.PURCHASE_ORDER,
        "required_level": ApprovalOutcome.ADMIN, "priority": 70,
    },
    {
        "name": "Sale cancellation up to ৳10,000", "transaction_type": ApprovalTxType.SALE_CANCEL,
        "max_value": Decimal("10000.00"), "required_level": ApprovalOutcome.SUPERVISOR, "priority": 80,
    },
    {
        "name": "Sale cancellation above ৳10,000", "transaction_type": ApprovalTxType.SALE_CANCEL,
        "required_level": ApprovalOutcome.ADMIN, "priority": 90,
    },
]


def ensure_default_policies():
    """Idempotent; fills in missing seed rows without touching admin edits."""
    created = 0
    for entry in DEFAULT_APPROVAL_POLICIES:
        _, was_created = ApprovalPolicy.objects.get_or_create(
            transaction_type=entry["transaction_type"], priority=entry["priority"],
            defaults={
                "name": entry["name"],
                "reason_code": entry.get("reason_code", ""),
                "min_value": entry.get("min_value", Decimal("0")),
                "max_value": entry.get("max_value"),
                "max_variance_pct": entry.get("max_variance_pct"),
                "cumulative_window_days": entry.get("cumulative_window_days"),
                "cumulative_value_cap": entry.get("cumulative_value_cap"),
                "required_level": entry["required_level"],
                "block_self_approval": entry.get("block_self_approval", True),
                "is_active": True,
                "notes": entry.get("notes", ""),
            },
        )
        if was_created:
            created += 1
    return created


def resolve_required_level(*, transaction_type, value, reason_code='',
                            variance_pct=None, exclude_policy_ids=None):
    """Returns the first matching active policy by priority, or None."""
    # Security: None means fail closed to ADMIN, never SUPERVISOR/AUTO.
    # Assumption: exclude_policy_ids lets a caller re-resolve without it.
    policies = ApprovalPolicy.objects.filter(
        transaction_type=transaction_type, is_active=True,
    ).order_by('priority')
    if exclude_policy_ids:
        policies = policies.exclude(pk__in=exclude_policy_ids)

    for policy in policies:
        if policy.reason_code and policy.reason_code != reason_code:
            continue
        if value < policy.min_value:
            continue
        if policy.max_value is not None and value > policy.max_value:
            continue
        if policy.max_variance_pct is not None:
            # Edge: null variance (zero stock) escalates for ADMIN, else excludes.
            if policy.required_level == ApprovalOutcome.ADMIN:
                if variance_pct is not None and not (variance_pct > policy.max_variance_pct):
                    continue
            else:
                if variance_pct is None or not (variance_pct <= policy.max_variance_pct):
                    continue
        return policy

    return None


def _adjustment_context(adjustment):
    value = Decimal(adjustment.quantity) * adjustment.product.purchase_price

    try:
        current_stock = InventoryRecord.objects.get(product=adjustment.product).current_stock
    except InventoryRecord.DoesNotExist:
        current_stock = 0
    variance_pct = (Decimal(adjustment.quantity) / current_stock * 100) if current_stock else None

    return ApprovalTxType.ADJUSTMENT, value, adjustment.reason_code, variance_pct, adjustment.requested_by


def _tx_context(tx):
    # Assumption: PO/Sale have no reason_code; only Adjustments do.
    if isinstance(tx, PurchaseOrder):
        return ApprovalTxType.PURCHASE_ORDER, tx.total_cost, '', None, tx.created_by
    if isinstance(tx, InventoryAdjustment):
        return _adjustment_context(tx)
    if isinstance(tx, SaleTransaction):
        return ApprovalTxType.SALE_CANCEL, tx.total_amount, '', None, tx.created_by
    raise TypeError(f"No approval context defined for {type(tx)!r}")


def resolve_for_transaction(tx):
    """Resolves (policy, required_level, creator) for a live transaction."""
    tx_type, value, reason_code, variance_pct, created_by = _tx_context(tx)
    policy = resolve_required_level(
        transaction_type=tx_type, value=value, reason_code=reason_code,
        variance_pct=variance_pct,
    )
    required_level = policy.required_level if policy else ApprovalOutcome.ADMIN
    return policy, required_level, created_by


def _cumulative_auto_total(product, policy):
    # Assumption: uses current purchase_price; no historical value stored.
    cutoff = timezone.now() - timedelta(days=policy.cumulative_window_days)
    rows = InventoryAdjustment.objects.filter(
        product=product, resolved_policy=policy, was_auto_posted=True,
        created_at__gte=cutoff,
    ).values_list('quantity', flat=True)
    return sum((Decimal(q) for q in rows), Decimal('0')) * product.purchase_price


def resolve_adjustment_with_cumulative_cap(adjustment):
    """Deflects an AUTO match that would exceed its cumulative cap."""
    tx_type, value, reason_code, variance_pct, _created_by = _adjustment_context(adjustment)
    policy = resolve_required_level(
        transaction_type=tx_type, value=value, reason_code=reason_code,
        variance_pct=variance_pct,
    )

    if (policy and policy.required_level == ApprovalOutcome.AUTO
            and policy.cumulative_window_days and policy.cumulative_value_cap is not None):
        existing_total = _cumulative_auto_total(adjustment.product, policy)
        if existing_total + value > policy.cumulative_value_cap:
            deflected_from = policy
            policy = resolve_required_level(
                transaction_type=tx_type, value=value, reason_code=reason_code,
                variance_pct=variance_pct,
                exclude_policy_ids={deflected_from.pk},
            )
            required_level = policy.required_level if policy else ApprovalOutcome.ADMIN
            return policy, required_level, deflected_from, existing_total

    required_level = policy.required_level if policy else ApprovalOutcome.ADMIN
    return policy, required_level, None, None


def can_approve(user, tx):
    """Returns (allowed, reason) -- reason is empty when allowed."""
    policy, required_level, created_by = resolve_for_transaction(tx)

    if required_level == ApprovalOutcome.AUTO:
        return True, ''

    if required_level == ApprovalOutcome.ADMIN and not user.is_admin:
        label = policy.name if policy else 'unclassified transaction (no matching policy)'
        return False, f'Requires administrator approval — {label}.'

    if required_level == ApprovalOutcome.SUPERVISOR and not (user.is_admin or user.is_supervisor):
        return False, 'Requires supervisor or administrator approval.'

    block_self = policy.block_self_approval if policy else True
    # Security: blocks self-approval unless the approver is admin.
    if block_self and created_by_id_equals(created_by, user) and not user.is_admin:
        return False, 'You cannot approve your own request — a different supervisor or an administrator must review it.'

    return True, ''


def created_by_id_equals(created_by, user):
    return created_by is not None and user is not None and created_by.pk == user.pk
