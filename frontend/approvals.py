"""
Phase 12 — Approval Authority Matrix. Generalises the old static
"is this user a supervisor?" role check into a policy engine: the admin
defines which transactions a supervisor is permitted to approve, per
transaction type/value/reason — not just per role. No `apps/approvals/`
app created (single-app architecture, see docs/project_memory.md §13,
same as every other module).

Read this alongside frontend/models.py's "14. Approval Policy" section
(ApprovalTxType/ApprovalOutcome/ApprovalPolicy) and
docs/project_memory.md §13 for the full disclosure of two premise gaps
this phase's own brief had, found during discovery rather than guessed
past:

1. There was no pre-existing purchase-order approval value ceiling
   anywhere in this codebase (no SystemSettings field, no service-layer
   check) to migrate byte-identically from — confirmed by reading
   SystemSettings' full field list and PurchaseService.approve(). The
   seed migration (frontend/migrations/000X_seed_approval_policies.py)
   writes the two purchase-order rows directly instead.
2. InventoryAdjustment has no stored currency value or "variance" concept
   at all (only quantity + adjustment_type). Both are computed here, at
   resolution time, not stored:
   - value = quantity * product.purchase_price
   - variance_pct = |quantity| / current_stock * 100 (None when
     current_stock is 0 — an undefined variance against a zero base,
     deliberately excluded from matching rather than treated as infinite
     or zero, so it falls through to a catch-all/Supervisor rule instead
     of accidentally satisfying an AUTO threshold on a technicality).

ApprovalPolicy.max_variance_pct's comparison direction depends on the
policy's own required_level, disclosed here since the model spec alone
doesn't fix it: for an ADMIN-outcome policy it's a floor the transaction's
variance must EXCEED to match (escalate when variance is unusually high);
for AUTO/SUPERVISOR-outcome policies it's a ceiling the variance must stay
AT OR BELOW to match (only automate/keep-at-supervisor when variance is
routine). Both directions are named "max_variance_pct" in the model
because both express "the most variance this policy tolerates before its
own outcome no longer applies" — which side of that boundary counts as a
match flips with what the policy is granting vs. withholding.

Phase 12.1 — hardening pass. Two fail-open defaults closed (a third,
ABC-related one from this same pass was later reversed — see Phase 12.2
below), each disclosed inline at its fix site rather than silently
changed: §5a `variance_pct is None` (zero current_stock) now matches an
ADMIN-outcome variance condition instead of skipping it — undefined
variance against a zero base is treated as exceeding every threshold,
not as absence of a signal. §4 a cumulative window/cap on AUTO-outcome
adjustment policies (resolve_adjustment_with_cumulative_cap()) closes a
real salami-slicing hole: N consecutive just-under-threshold adjustments
on the same product previously moved unbounded stock with zero human
approval events.

Also discovery-only, Phase 12.1: asked to harden a "record unlock"
system (re-resolve approval authority when a terminal PO/adjustment is
edited via an unlock). No such system exists anywhere in this codebase —
confirmed by an exhaustive grep (models, services, views, all migrations)
and a full read of every §15 timeline entry. Not built here; see
docs/project_memory.md §13 for the full discovery writeup. Nothing in
this module references it.

Phase 12.2 — ABC class removed as an approval-routing input entirely
(the matching condition, the seeded "Class-A product, high variance"
policy, Phase 12.1 §5b's unclassified-resolves-as-'A' fallback, the
rule simulator and cumulative-usage-panel UI that surfaced it here): too
much complexity for the value it added. `ABCClass`/
`recompute_abc_classes()` themselves are untouched — ABC remains a real,
useful field on `InventoryClassification` for inventory analysis and
dead-stock work, just no longer consulted anywhere in this module's own
resolution logic.
"""
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta

from frontend.models import (
    ABCClass,
    ApprovalOutcome,
    ApprovalPolicy,
    ApprovalTxType,
    InventoryAdjustment,
    InventoryClassification,
    InventoryRecord,
    Product,
    PurchaseOrder,
    SaleItem,
    SaleStatus,
    SaleTransaction,
    SystemSettings,
)

# The starting ruleset (§9), also frozen as a snapshot inside
# frontend/migrations/0007_seed_approval_policies.py — deliberately
# duplicated, not imported from there: a migration must stay
# self-contained against the schema it was written for, so it carries
# its own copy rather than importing this evolving module (importing
# live app code from a migration is the real anti-pattern — a future
# edit here would silently change what an old migration replays).
# This copy is what seed_dev_data.py calls, via ensure_default_policies()
# below, to restore the table after its own call_command("flush", ...) —
# flush truncates every table, including one a data migration seeded only
# once; found empirically (seed_dev_data.py's first post-Phase-12 run
# failed every PurchaseService.approve() call with "no matching policy"),
# not assumed.
#
# Phase 12.2 — the "Class-A product, high variance" row (priority 20)
# is gone; ABC is no longer a matching condition anywhere in this list.
# Coverage re-checked after removing it: shrinkage_unknown (10) and the
# damage/expiry rows (30/31) still resolve their specific cases, the
# catch-all (50) still resolves everything else for ADJUSTMENT, and
# resolve_required_level()'s own "no match -> None -> caller fails
# closed to ADMIN" guarantee is a resolver-level property that never
# depended on which specific rows exist — removing one row can never
# weaken it.
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
        # Phase 12.1 §4 — the cumulative cap: without it, N consecutive
        # sub-threshold adjustments on the same product move unbounded
        # stock with zero human approval events. 30 days / ৳2,000 per
        # product; once exceeded, resolution continues to the next
        # priority (here, row 50 — Supervisor) instead of hard-coding an
        # escalation target.
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
    """Idempotent: get_or_create per (transaction_type, priority), same
    keying as the migration. Safe to call after a flush (dev seed) or any
    time the table is found empty — never overwrites an admin's own
    edits to an existing row, only fills in rows that are missing."""
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


# Trailing window for cumulative-revenue ABC ranking. Matches
# frontend.classification.calculate_turnover_rate()'s own 90-day default —
# same "recent, not lifetime" horizon, same reasoning: a product's
# revenue-contribution class should track its recent behaviour, not
# something it did a year ago.
ABC_WINDOW_DAYS = 90


def resolve_required_level(*, transaction_type, value, reason_code='',
                            variance_pct=None, exclude_policy_ids=None):
    """Returns the first matching active ApprovalPolicy for this
    transaction_type, ordered by priority (lower wins), or None.
    None means NO POLICY MATCHED -> the caller (can_approve()) fails
    closed to ADMIN — never to SUPERVISOR, never to AUTO. A transaction
    the ruleset can't classify is, by definition, the kind that needs the
    most senior signature.

    exclude_policy_ids (Phase 12.1 §4): pks to skip during this
    resolution, letting the cumulative-cap check
    (resolve_adjustment_with_cumulative_cap()) re-resolve "as if this
    AUTO policy didn't exist" without hard-coding what the fallback
    outcome should be — the ruleset decides, same as every other
    resolution."""
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
            # Phase 12.1 §5a: variance_pct is None only for an
            # adjustment against zero current_stock — an undefined
            # variance against a zero base, not an absent one. Treated
            # as EXCEEDING every threshold (infinite variance: the
            # "phantom stock"/"found in overflow storage" case), never
            # as "no variance to report." For an ADMIN-outcome policy
            # (match = exceeds) that means None now MATCHES, escalating
            # — the fail-closed-consistent fix. For AUTO/SUPERVISOR
            # (match = at-or-below) None still fails to match, unchanged
            # from before — it was already correctly excluded there.
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
    """Returns (transaction_type, value, reason_code, variance_pct,
    created_by) for any of the three transaction kinds this phase's
    policy engine governs. Purchase-order approval and sale-cancellation
    have no reason-code concept of their own (only adjustments do) — both
    pass through blank/None for it, which only ever matches policies that
    also leave that condition blank (a deliberate, not accidental,
    exclusion — see §9's own seed table: rows 60/70/80/90 never set
    reason_code)."""
    if isinstance(tx, PurchaseOrder):
        return ApprovalTxType.PURCHASE_ORDER, tx.total_cost, '', None, tx.created_by
    if isinstance(tx, InventoryAdjustment):
        return _adjustment_context(tx)
    if isinstance(tx, SaleTransaction):
        return ApprovalTxType.SALE_CANCEL, tx.total_amount, '', None, tx.created_by
    raise TypeError(f"No approval context defined for {type(tx)!r}")


def resolve_for_transaction(tx):
    """Returns (policy_or_None, required_level, created_by) for a live
    PurchaseOrder/InventoryAdjustment/SaleTransaction instance. Shared by
    can_approve() and the service layer's own audit-detail logging, so
    both agree on exactly what was resolved and why."""
    tx_type, value, reason_code, variance_pct, created_by = _tx_context(tx)
    policy = resolve_required_level(
        transaction_type=tx_type, value=value, reason_code=reason_code,
        variance_pct=variance_pct,
    )
    required_level = policy.required_level if policy else ApprovalOutcome.ADMIN
    return policy, required_level, created_by


def _cumulative_auto_total(product, policy):
    """Sum of AUTO-posted-under-this-exact-policy adjustment values for
    `product` within `policy.cumulative_window_days` (Phase 12.1 §4).
    Scoped per-policy, not per-product-globally: each AUTO policy tracks
    its own window/cap independently, matching where the fields live
    (on the policy, not the product). Uses each row's own quantity times
    the product's CURRENT purchase_price, not a historical snapshot —
    InventoryAdjustment doesn't store a value at all (see this module's
    own docstring, gap 2), so there is no historical price to recover;
    disclosed simplification, not silently assumed."""
    cutoff = timezone.now() - timedelta(days=policy.cumulative_window_days)
    rows = InventoryAdjustment.objects.filter(
        product=product, resolved_policy=policy, was_auto_posted=True,
        created_at__gte=cutoff,
    ).values_list('quantity', flat=True)
    return sum((Decimal(q) for q in rows), Decimal('0')) * product.purchase_price


def resolve_adjustment_with_cumulative_cap(adjustment):
    """Phase 12.1 §4 — like resolve_for_transaction(), but for
    InventoryAdjustment only: if the first-matched policy would resolve
    to AUTO and carries a cumulative cap, checks whether posting this
    adjustment would push the trailing-window total for this product
    over that cap. If so, the policy does NOT apply — re-resolves with
    it excluded and lets the ruleset's own next-priority rule decide
    (the seeded set lands on the Supervisor catch-all, but this function
    doesn't hard-code that).

    Returns (policy_or_None, required_level, deflected_from_policy_or_None,
    cumulative_total_or_None). deflected_from is only set when a cap
    genuinely deflected a match — the caller uses it to decide whether to
    write the ADJUSTMENT_AUTO_DEFLECTED audit entry (§4's own instruction:
    "this is the trail that makes the control provable"). Still enforced
    exactly as built in Phase 12.1 — Phase 12.2 only removed ABC from the
    UI/matching, not this."""
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
    """Returns (allowed: bool, reason: str) — reason is a human-readable
    denial explanation (empty string when allowed), for both the JSON
    error the view surfaces and the disabled-button label the template
    renders (§8b — the control is shown-but-disabled, never hidden).

    Rule order (§5):
    1. No matching policy -> ADMIN (fail closed).
    2. AUTO -> no human approval needed at all.
    3. SUPERVISOR -> admin or supervisor may approve.
    4. ADMIN -> admin only.
    5. Self-approval: creator == approver is blocked when the matched
       policy's block_self_approval is True -- UNLESS the approver is
       admin. Admin may self-approve; supervisor may not. Deliberate
       (§5), and a reversal of the previously-disclosed "no creator≠
       approver restriction" decision for Purchases/Sales (Phase 7/
       8.99b, docs/project_memory.md §13) -- flagged there, not silent.
    """
    policy, required_level, created_by = resolve_for_transaction(tx)

    if required_level == ApprovalOutcome.AUTO:
        return True, ''

    if required_level == ApprovalOutcome.ADMIN and not user.is_admin:
        label = policy.name if policy else 'unclassified transaction (no matching policy)'
        return False, f'Requires administrator approval — {label}.'

    if required_level == ApprovalOutcome.SUPERVISOR and not (user.is_admin or user.is_supervisor):
        return False, 'Requires supervisor or administrator approval.'

    block_self = policy.block_self_approval if policy else True
    if block_self and created_by_id_equals(created_by, user) and not user.is_admin:
        return False, 'You cannot approve your own request — a different supervisor or an administrator must review it.'

    return True, ''


def created_by_id_equals(created_by, user):
    return created_by is not None and user is not None and created_by.pk == user.pk


def recompute_abc_classes():
    """Batch pass — cumulative revenue contribution over the trailing
    ABC_WINDOW_DAYS, split 80/15/5 into A/B/C. Called from
    frontend.classification.run_full_classification()'s own closing step:
    no Celery task exists anywhere in this project to schedule this
    alongside the existing AI tasks (requirements.txt has no celery
    dependency; frontend/forecasting.py's own docstring already discloses
    the same absence) — every AI/analytics pass here is a manual
    synchronous run, so this follows that established pattern rather than
    inventing background-task infrastructure.

    Phase 12.2 note: ABC is no longer consulted by the approval resolver
    (see this module's own docstring) — this function is unchanged and
    still runs, purely for inventory analysis/dead-stock work.

    Only UPDATEs existing InventoryClassification rows (never creates
    one) — a product that has never been through classify_product() yet
    has no row to update, and stays at whatever the model's own blank
    default implies ("never computed") until its row is eventually
    created; recompute_abc_classes() folding into run_full_classification()
    (which classifies every active product first) means that gap only
    matters for products with literally zero sales history. Returns the
    count of rows updated."""
    cutoff = timezone.localdate() - timedelta(days=ABC_WINDOW_DAYS)
    revenue_by_product = dict(
        SaleItem.objects.filter(
            transaction__status=SaleStatus.COMPLETED,
            transaction__transaction_date__gte=cutoff,
        ).values('product_id').annotate(revenue=Sum('line_total')).values_list('product_id', 'revenue')
    )

    active_product_ids = list(Product.objects.filter(is_active=True).values_list('id', flat=True))
    total_revenue = sum(revenue_by_product.values()) if revenue_by_product else Decimal('0')

    ranked = sorted(
        active_product_ids,
        key=lambda pid: revenue_by_product.get(pid, Decimal('0')),
        reverse=True,
    )

    cumulative = Decimal('0')
    updated = 0
    for pid in ranked:
        revenue = revenue_by_product.get(pid, Decimal('0'))
        if revenue <= 0 or total_revenue <= 0:
            cls = ABCClass.C
        else:
            cumulative += revenue
            pct = cumulative / total_revenue * 100
            if pct <= 80:
                cls = ABCClass.A
            elif pct <= 95:
                cls = ABCClass.B
            else:
                cls = ABCClass.C
        rows = InventoryClassification.objects.filter(product_id=pid).update(abc_class=cls)
        updated += rows

    # A bulk queryset .update() (above) bypasses TimeStampedModel's
    # auto_now updated_at entirely (.update() never calls save()), so
    # without this, ABC's own recompute time would be silently
    # unobservable — still tracked for analysts, even though (Phase
    # 12.2) it no longer gates any approval.
    settings_obj = SystemSettings.get_settings()
    settings_obj.abc_last_recomputed_at = timezone.now()
    settings_obj.save(update_fields=['abc_last_recomputed_at', 'updated_at'])

    return updated


# "Warning when it exceeds ~30 days" — still relevant on the Slow-Moving
# & Dead Stock page (Phase 12.2 kept ABC for analytics there), no longer
# surfaced on the Approval Policies page.
ABC_STALENESS_WARNING_DAYS = 30


def abc_staleness_info():
    """Returns (last_recomputed_at_or_None, is_stale). is_stale is True
    both when it's never been run at all and when it's older than
    ABC_STALENESS_WARNING_DAYS — an analyst reading ABC-based inventory
    recommendations off stale or never-computed data is the risk this
    guards against."""
    last = SystemSettings.get_settings().abc_last_recomputed_at
    if last is None:
        return None, True
    is_stale = (timezone.now() - last) > timedelta(days=ABC_STALENESS_WARNING_DAYS)
    return last, is_stale
