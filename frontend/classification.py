"""
docs/DEAD_STOCK_DETECTION.md, translated into the single `frontend` app —
no `apps/ai/classification/` app created (see docs/project_memory.md §13:
this project deliberately stays single-app at this stage). Matches the
existing small-dedicated-module pattern (frontend/audit.py,
frontend/notifications.py, frontend/reports.py).

No ML model this phase, no Celery — run_full_classification() is called
synchronously, either from a real approve_sale()/cancel_sale() event
(single product, see frontend/services.py) or from the manual "Run
classification now" button (SlowMovingDeadStockView.post()). No scheduler
exists anywhere in this project — see docs/DEAD_STOCK_DETECTION.md's own
header for the honest statement of what that means for staleness between
triggers.

Three further translations made here, each disclosed in
docs/project_memory.md §13 rather than copied silently:
1. calculate_average_stock()'s start-of-window fallback — the doc's
   `stock_at_start = before[-1]['stock_after'] if before else
   current_stock` reaches for *today's* current_stock whenever there's no
   movement strictly before period_start, even when movements exist
   *during* the window — exactly backwards for the case this function
   exists to handle. Fixed: fall back to the first in-window movement's
   own stock_before when one exists; current_stock only when the product
   has no movement history at all in or before the window.
2. classify_product()'s `today = timezone.now().date()` (UTC calendar
   date) → `timezone.localdate()` (Asia/Dhaka) — same class of bug as
   BUG-47 (PurchaseOrder/SaleTransaction date generation): using the UTC
   date would misclassify by a day for roughly 6 hours around Dhaka
   midnight on a UTC production server.
3. The doc's `transaction__status='completed'` string literal → the real
   terminal-success constant, SaleStatus.COMPLETED (same string value,
   read from the enum this codebase actually uses everywhere else rather
   than a bare string that would silently stop matching if the constant's
   value ever changed).

Prompt 2 (2026-08-24) — upgraded from the single-factor recency branch to
a multi-criteria weighted expert system (Recency/Turnover/Coverage/
Frequency -> a 0-100 stagnation_index via admin-configurable weights).
ABC classification was removed in the same pass: never part of any
documented requirement (confirmed by a full grep of docs/*.md).

PROMPT_1B (2026-08-24) — the first live run against real shaped seed data
produced ZERO dead-stock classifications on data known to contain dead
stock (docs/bugsfound.md has the full incident). Root cause, in two
parts:

1. THE GATE. insufficient_data was gated on
   `stock_age_days < min_observation_days OR sale_event_count <
   min_sale_events`. The second condition is the bug: `sale_event_count`
   is windowed to the same trailing 90 days as demand, so a product that
   sold steadily for a year and then went quiet 200+ days ago has
   *zero* events in that window — indistinguishable, to the old gate,
   from a product that has never had the chance to sell at all. Of a
   real dev run's 10 insufficient_data products, 9 were long-established
   (age 90-300 days) products with real stock sitting idle, diverted
   away from the index before it ever saw them. Fixed: the gate is now
   AGE ONLY. `min_sale_events` still exists (SystemSettings) but now
   only feeds `confidence` (fewer events -> lower confidence) — what it
   should have been doing from the start.
2. TWO OF THE FOUR FACTORS COULD NOT VARY. Because the old gate required
   `sale_event_count >= min_sale_events` to reach the scored branch at
   all, `frequency_score = max(0, 1 - events/min_sale_events)` was
   mathematically pinned at exactly 0 for 100% of the scored population
   — dead weight, not a factor. `coverage_score`, clamped at 1.00 the
   moment `days_of_cover` crossed `target_days_of_cover`, saturated for
   30 of 33 scored products in the same run. With two of four factors
   constant, the index reproduced its own mean (~44) regardless of the
   product, compressed into a ~27-point band nowhere near
   `dead_index_threshold`. Averaging didn't cause this on its own —
   averaging *constants* did. Fixed: Frequency now counts distinct
   weekly buckets with a sale (see _distinct_sale_buckets()), completely
   independent of any gate; Coverage now ramps linearly between
   `target_days_of_cover` (0.00) and the new `extreme_coverage_days`
   (1.00) instead of clamping at the low end.

TWO-LAYER CLASSIFICATION. Override rules run FIRST, before the
insufficient_data gate, before the weighted index — see
classify_product()'s own docstring for the full precedence and why
overrides-before-gate is safe (the DEAD overrides require
`stock_age_days`/`days_since_last_sale >= dead_stock_threshold_days`,
which a genuinely new product cannot satisfy). The four Force-DEAD/
Force-SLOW/Force-FAST rules preserve the old day-threshold rule as a
floor: anything the old 180-day rule called dead is still dead, no
matter what the index would have said. See docs/DEAD_STOCK_DETECTION.md
for the full two-layer design and docs/bugsfound.md for the incident
this fixes.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Max, Sum
from django.utils import timezone

from frontend.models import (
    InventoryClassification,
    InventoryMovement,
    InventoryRecord,
    Product,
    SaleItem,
    SaleStatus,
    StockClassification,
    SystemSettings,
)

# The one window every demand-derived number in this module shares —
# avg_daily_demand, turnover_rate's total_sold, and the frequency
# factor's bucket window all read from this, never a second window
# invented for one of them alone.
_DEMAND_WINDOW_DAYS = 90

# FIX 2 (PROMPT_1B) — weekly, not monthly: 3 monthly buckets over a
# 90-day window gives almost no resolution (a single bulk sale and a
# twice-a-month seller would look nearly identical). 7-day buckets give
# 12 buckets, enough to tell "steady weekly seller" (hits in most/all of
# them) apart from "one bulk sale" (hits in exactly one).
_FREQUENCY_BUCKET_DAYS = 7
_FREQUENCY_TOTAL_BUCKETS = _DEMAND_WINDOW_DAYS // _FREQUENCY_BUCKET_DAYS  # 12

# Force-FAST override (see classify_product()): "sold very recently" —
# not specified as an exact number in the brief, chosen as a disclosed
# default rather than left ambiguous. 14 days ("within the last two
# weeks") rather than a tighter window: a 3-7 day window would exclude
# genuinely fast-moving products that happen to sell on a ~10-day cycle,
# which is exactly the shape this override exists to catch.
_FORCE_FAST_RECENT_SALE_DAYS = 14

# Precedence when a product matches more than one rule (e.g. old enough
# for Force-DEAD and also carrying extreme coverage): DEAD is checked and
# returned first in _evaluate_hard_overrides(), unconditionally, before
# the Force-SLOW candidate is even evaluated — see classify_product()'s
# own docstring for the full precedence chain. DEAD always wins.


def calculate_average_stock(product, period_start, period_end):
    """
    Time-weighted average stock over [period_start, period_end],
    reconstructed from the InventoryMovement ledger's stock_after values —
    not a single point-in-time InventoryRecord.current_stock snapshot. A
    product that held 500 units for most of the window and only sold down
    near the end would otherwise be judged entirely on whichever stock
    level happened to be true the moment this function ran (Design Notes
    revision #1, docs/DEAD_STOCK_DETECTION.md).
    """
    try:
        current_stock = InventoryRecord.objects.get(product=product).current_stock
    except InventoryRecord.DoesNotExist:
        return 0.0

    movements = list(
        InventoryMovement.objects.filter(product=product, created_at__lte=period_end)
        .order_by('created_at')
        .values('created_at', 'stock_before', 'stock_after')
    )

    before = [m for m in movements if m['created_at'] < period_start]
    during = [m for m in movements if m['created_at'] >= period_start]

    # Design Notes revision #3 (docs/DEAD_STOCK_DETECTION.md): a movement
    # before period_start fixes the stock level at the window's edge, as
    # before. But with none before and some during, the level *entering*
    # the window is the first in-window movement's own stock_before — not
    # current_stock, which is today's level and includes everything that
    # happened during and after the window too. current_stock is only a
    # sane fallback when the product has no ledger activity at all here.
    if before:
        stock_at_start = before[-1]['stock_after']
    elif during:
        stock_at_start = during[0]['stock_before']
    else:
        stock_at_start = current_stock

    checkpoints = [(period_start, stock_at_start)]
    checkpoints += [(m['created_at'], m['stock_after']) for m in during]
    checkpoints.append((period_end, current_stock))

    total_seconds = (period_end - period_start).total_seconds()
    if total_seconds <= 0:
        return float(stock_at_start)

    weighted_sum = 0.0
    for (t_start, stock), (t_end, _) in zip(checkpoints, checkpoints[1:]):
        weighted_sum += stock * (t_end - t_start).total_seconds()

    return weighted_sum / total_seconds


def _total_sold(product, days=_DEMAND_WINDOW_DAYS):
    """Total COMPLETED SaleItem quantity in the trailing `days` window.
    The one place this query is written — calculate_turnover_rate()'s
    total_sold and classify_product()'s avg_daily_demand both call this,
    so "same window" is structural, not just documented."""
    period_start = timezone.now() - timedelta(days=days)
    return SaleItem.objects.filter(
        product=product,
        transaction__transaction_date__gte=period_start.date(),
        transaction__status=SaleStatus.COMPLETED,
    ).aggregate(total=Sum('quantity'))['total'] or 0


def _sale_event_count(product, days=_DEMAND_WINDOW_DAYS):
    """Count of COMPLETED SaleItem rows (not units) in the same trailing
    window as _total_sold()/avg_daily_demand. PROMPT_1B — no longer part
    of the insufficient_data gate (see module docstring); feeds
    `confidence` only now."""
    period_start = timezone.now() - timedelta(days=days)
    return SaleItem.objects.filter(
        product=product,
        transaction__transaction_date__gte=period_start.date(),
        transaction__status=SaleStatus.COMPLETED,
    ).count()


def _distinct_sale_buckets(product, days=_DEMAND_WINDOW_DAYS, bucket_days=_FREQUENCY_BUCKET_DAYS):
    """FIX 2 (PROMPT_1B) — the Frequency factor's real input: how many of
    the trailing window's weekly buckets contain at least one COMPLETED
    sale, out of the total bucket count. A steady weekly seller hits
    most/all buckets; a single bulk sale hits exactly one — the two are
    now distinguishable, unlike the old formula (see module docstring),
    which was mathematically incapable of producing anything but 0 once
    past the old event-count gate. Independent of that gate entirely:
    this just counts real sale activity, with no threshold comparison
    baked in.

    Returns (buckets_with_sale, total_buckets).
    """
    total_buckets = max(days // bucket_days, 1)
    today_ref = timezone.now().date()
    sale_dates = SaleItem.objects.filter(
        product=product,
        transaction__transaction_date__gte=today_ref - timedelta(days=days),
        transaction__status=SaleStatus.COMPLETED,
    ).values_list('transaction__transaction_date', flat=True)

    hit_buckets = set()
    for d in sale_dates:
        age_days = (today_ref - d).days
        if age_days < 0:
            continue
        bucket = min(age_days // bucket_days, total_buckets - 1)
        hit_buckets.add(bucket)

    return len(hit_buckets), total_buckets


def _stock_age_days(product):
    """How long this product has actually been observable. Anchor: the
    first InventoryMovement.created_at (when stock activity genuinely
    began), falling back to Product.created_at for a product that has
    never had a single movement yet (freshly created, nothing
    received)."""
    first_movement_at = (
        InventoryMovement.objects.filter(product=product)
        .order_by('created_at')
        .values_list('created_at', flat=True)
        .first()
    )
    anchor = first_movement_at or product.created_at
    return max((timezone.now() - anchor).days, 0)


def calculate_turnover_rate(product, days=_DEMAND_WINDOW_DAYS):
    """
    Turnover rate = total units sold in period / time-weighted average
    stock held over the period. Returns float (higher = faster moving).
    Still informational on its own (never a classification gate by
    itself) — folded into the Turnover factor of the weighted stagnation
    index instead of using it raw.
    """
    period_end = timezone.now()
    period_start = period_end - timedelta(days=days)

    total_sold = _total_sold(product, days=days)
    avg_stock = calculate_average_stock(product, period_start, period_end)

    if avg_stock <= 0:
        return 0.0
    # Phase 10 finding, not in the doc: a product whose entire stock
    # history (received, then sold) happens within a tiny slice of the
    # 90-day window — a brand-new product stocked and sold through the
    # same day, or (found by a test exercising exactly this shape) any
    # sale approved moments after its own initial stock receipt — makes
    # avg_stock approach zero, and total_sold / avg_stock explode into the
    # billions. InventoryClassification.turnover_rate is DecimalField
    # (max_digits=8, decimal_places=4, ceiling 9999.9999); an uncapped
    # value overflows it outright (a real crash, not a display quirk).
    # Capped at that ceiling — "extremely fast" doesn't need unbounded
    # precision, and turnover is informational only, never a
    # classification gate on its own, so capping it changes no
    # classification outcome by itself.
    return min(round(total_sold / avg_stock, 4), 9999.9999)


def get_last_sold_date(product):
    """Return the most recent COMPLETED sale date for a product, or None.
    Pending/rejected/cancelled sales never count — a sale that hasn't
    actually happened (stock hasn't moved) isn't a sale for this purpose."""
    result = SaleItem.objects.filter(
        product=product,
        transaction__status=SaleStatus.COMPLETED,
    ).aggregate(last_date=Max('transaction__transaction_date'))
    return result['last_date']


def _dominant_factor(weighted_scores):
    """weighted_scores: [(name, weight * score), ...]. Returns the name
    with the largest weighted contribution — what classify_product()'s
    recommendation text names on the ordinary index path, instead of
    always blaming recency."""
    return max(weighted_scores, key=lambda pair: pair[1])[0]


def _evaluate_hard_overrides(*, days_since, stock_age_days, current_stock, days_of_cover,
                              dead_threshold, target_days_of_cover):
    """PROMPT_1B Phase 3 — Layer 1a. Force-DEAD and Force-FAST: decided on
    raw signals alone, no index required, so they can run BEFORE both the
    insufficient_data gate and the weighted index (see
    classify_product()'s own docstring for why that's safe). Returns
    (classification, rule_text), or (None, '') if neither matches.

    DEAD checked first and returned immediately — structurally, DEAD and
    FAST can never both match the same product (FAST requires a sale
    within the last _FORCE_FAST_RECENT_SALE_DAYS; DEAD requires either no
    sale in at least dead_threshold days, or no sale ever from a
    long-established product — mutually exclusive), so there is no
    severity tie to break here. The two Force-DEAD conditions together
    preserve the old recency-only rule as a floor: anything the old rule
    called dead (days_since_last_sale >= dead_stock_threshold_days, or
    never sold and old enough) is still dead here, regardless of what the
    four-factor index would say — this is what guarantees no detection
    regression.

    Force-SLOW (extreme coverage) is deliberately NOT here — see
    classify_product()'s own docstring for why it has to wait until the
    index is computed.
    """
    if days_since is not None and days_since >= dead_threshold and current_stock > 0:
        return StockClassification.DEAD, f"No sales in {days_since} days"

    if days_since is None and stock_age_days >= dead_threshold and current_stock > 0:
        return StockClassification.DEAD, f"Never sold, {stock_age_days} days in stock"

    if (days_since is not None and days_since <= _FORCE_FAST_RECENT_SALE_DAYS
            and days_of_cover is not None and days_of_cover <= target_days_of_cover):
        return StockClassification.FAST, f"Sold {days_since} day(s) ago, {round(days_of_cover)} days of cover"

    return None, ''


def classify_product(product, settings_obj=None):
    """
    Classify a single product and upsert its InventoryClassification
    record. Returns the classification string: StockClassification.FAST/
    SLOW/DEAD/INSUFFICIENT_DATA.

    PRECEDENCE (PROMPT_1B Phase 3, revised after a design review of the
    first version — see docs/bugsfound.md) — evaluated strictly in this
    order; each layer can be short-circuited by the one before it:

    1. HARD OVERRIDES (_evaluate_hard_overrides) — Force-DEAD and
       Force-FAST, decided on raw signals alone (days_since_last_sale,
       stock age, current_stock, days of cover). Bypass both the gate
       below and the index entirely. These exist specifically so a
       product the old day-threshold rule would have caught can never be
       hidden by the newer, more nuanced machinery — see that function's
       own docstring for why DEAD and FAST can never both match the same
       product. When one fires, `flagged_by_rule` is set to a
       human-readable reason ("No sales in 210 days") instead of being
       decided by an opaque index number.
    2. INSUFFICIENT_DATA gate — stock_age_days < min_observation_days,
       AGE ONLY (sale-event count no longer gates this — see module
       docstring for why that was wrong). Only reached when no hard
       override matched.
    3. WEIGHTED INDEX — four factors, each 0.00-1.00 (1.00 = maximally
       stagnant), combined via SystemSettings.weight_* into a 0-100
       stagnation_index. Always computed once past the gate, even when a
       hard override already decided the classification (a supervisor
       must still see why, not just what):

       - Recency:   days_since_last_sale / dead_stock_threshold_days,
                    capped at 1.00. Never sold -> 1.00.
       - Turnover:  1 / (1 + turnover_rate) — self-normalising.
       - Coverage:  current_stock == 0 -> 0.00. current_stock > 0 and
                    avg_daily_demand == 0 -> 1.00 (real stock, zero
                    demand — the core dead-stock signal). Otherwise a
                    LINEAR ramp from target_days_of_cover (0.00) to
                    extreme_coverage_days (1.00) — linear rather than
                    log because the Force-SLOW check below already
                    absorbs the truly extreme tail, so this ramp only
                    has to discriminate the middle band between the two
                    settings, where a straight line is both adequate
                    and easier for an admin to reason about than a log
                    curve.
       - Frequency: 1 - (distinct weekly buckets with a sale / total
                    buckets) over the trailing 90 days — see
                    _distinct_sale_buckets(). Independent of any gate;
                    a steady weekly seller scores near 0, a single bulk
                    sale scores near 1.
    4. FORCE-SLOW (extreme coverage), evaluated AFTER the index, only
       when no hard override already fired: `days_of_cover >=
       extreme_coverage_days` AND `stagnation_index < dead_index_threshold`.
       The second condition is deliberate, added after reviewing what it
       downgraded on real data: a product the index independently scores
       >= dead_index_threshold is broadly stagnant on more than just
       coverage (verified case: recency 0.42, turnover 0.96, coverage
       1.00, frequency 0.92 — every factor high, not just coverage), and
       DEAD is the more useful label for a supervisor than a coverage-only
       SLOW that quietly overrides an independently-dead-flagged product.
       Force-SLOW is a FLOOR for extreme overstock the index might
       otherwise call fast-ish (recency low, other factors not yet
       stagnant) — never a CEILING on a product the index already flags
       as dead on its own merits.
    5. INDEX-DERIVED classification — reached only when nothing above
       fired: stagnation_index >= dead_index_threshold -> DEAD;
       >= slow_index_threshold -> SLOW; else -> FAST.

    `confidence` (0.00-1.00, always persisted, including for
    INSUFFICIENT_DATA and override-fired rows — it's most informative
    exactly when data is thin) is the average of (observed days /
    min_observation_days) and (sale events / min_sale_events), each
    capped at 1.00.
    """
    if settings_obj is None:
        settings_obj = SystemSettings.get_settings()

    today = timezone.localdate()
    last_sold = get_last_sold_date(product)
    turnover = calculate_turnover_rate(product)
    days_since = None if last_sold is None else (today - last_sold).days

    stock_age_days = _stock_age_days(product)
    sale_event_count = _sale_event_count(product)
    min_observation_days = settings_obj.min_observation_days
    min_sale_events = settings_obj.min_sale_events

    try:
        current_stock = InventoryRecord.objects.get(product=product).current_stock
    except InventoryRecord.DoesNotExist:
        current_stock = 0

    dead_threshold = settings_obj.dead_stock_threshold_days or 1
    target_days_of_cover = settings_obj.target_days_of_cover or 1
    extreme_coverage_days = settings_obj.extreme_coverage_days or 1

    avg_daily_demand = _total_sold(product) / float(_DEMAND_WINDOW_DAYS)
    days_of_cover = (
        current_stock / avg_daily_demand
        if current_stock > 0 and avg_daily_demand > 0 else None
    )

    # ---- Layer 1: hard overrides (Force-DEAD / Force-FAST) ----
    hard_classification, hard_rule = _evaluate_hard_overrides(
        days_since=days_since, stock_age_days=stock_age_days, current_stock=current_stock,
        days_of_cover=days_of_cover, dead_threshold=dead_threshold,
        target_days_of_cover=target_days_of_cover,
    )

    # ---- Layer 2: insufficient_data gate (age only; skipped if a hard override already fired) ----
    insufficient = hard_classification is None and stock_age_days < min_observation_days

    if insufficient:
        classification = StockClassification.INSUFFICIENT_DATA
        flagged_by_rule = ''
        recommendation = (
            f"'{product.name}' has been observed for {stock_age_days} day(s) — below "
            f"the configured minimum ({min_observation_days} days) to classify with "
            f"confidence. Revisit once the product has been in stock longer."
        )
        recency_score = turnover_score = coverage_score = frequency_score = None
        stagnation_index = None
    else:
        # ---- Layer 3: weighted index (always computed once past the gate, even if a hard override already decided) ----
        if days_since is None:
            recency_score = Decimal('1.0000')
        else:
            recency_score = Decimal(str(min(days_since / dead_threshold, 1.0))).quantize(Decimal('0.0001'))

        turnover_score = Decimal(str(1.0 / (1.0 + float(turnover)))).quantize(Decimal('0.0001'))

        if current_stock == 0:
            coverage_score = Decimal('0.0000')
        elif avg_daily_demand == 0:
            coverage_score = Decimal('1.0000')
        elif days_of_cover <= target_days_of_cover:
            coverage_score = Decimal('0.0000')
        elif days_of_cover >= extreme_coverage_days:
            coverage_score = Decimal('1.0000')
        else:
            span = extreme_coverage_days - target_days_of_cover
            ramped = (days_of_cover - target_days_of_cover) / span
            coverage_score = Decimal(str(min(max(ramped, 0.0), 1.0))).quantize(Decimal('0.0001'))

        buckets_with_sale, total_buckets = _distinct_sale_buckets(product)
        frequency_score = Decimal(str(1.0 - (buckets_with_sale / total_buckets))).quantize(Decimal('0.0001'))

        weighted_scores = [
            ('recency', settings_obj.weight_recency * recency_score),
            ('turnover', settings_obj.weight_turnover * turnover_score),
            ('coverage', settings_obj.weight_coverage * coverage_score),
            ('frequency', settings_obj.weight_frequency * frequency_score),
        ]
        weighted_sum = sum(score for _, score in weighted_scores)
        stagnation_index = max(0, min(100, round(weighted_sum * 100)))
        dominant = _dominant_factor(weighted_scores)

        # ---- Layer 4: Force-SLOW (extreme coverage), only if no hard override fired ----
        # PROMPT_1B design review — this is a FLOOR (catches extreme
        # overstock the index might still call fast-ish), never a
        # CEILING: only applies when the index hasn't already
        # independently decided this product is broadly stagnant enough
        # to be DEAD on its own merits (verified case: a product with
        # extreme coverage AND high recency/turnover/frequency scores —
        # every factor stagnant, not just coverage — stays DEAD, not
        # downgraded to SLOW).
        slow_override_candidate = days_of_cover is not None and days_of_cover >= extreme_coverage_days
        force_slow = (
            hard_classification is None and slow_override_candidate
            and stagnation_index < settings_obj.dead_index_threshold
        )

        if hard_classification is not None:
            classification = hard_classification
            flagged_by_rule = hard_rule
        elif force_slow:
            classification = StockClassification.SLOW
            flagged_by_rule = f"{round(days_of_cover)} days of stock on hand"
        else:
            classification = None  # decided by the index below
            flagged_by_rule = ''

        if flagged_by_rule:
            if classification == StockClassification.DEAD:
                recommendation = (
                    f"'{product.name}' is dead stock — flagged by rule: {flagged_by_rule}. "
                    f"Consider clearance sale, write-off, or return to supplier. "
                    f"Suspend further purchasing."
                )
            elif classification == StockClassification.SLOW:
                recommendation = (
                    f"'{product.name}' is slow-moving — flagged by rule: {flagged_by_rule}. "
                    f"Consider promotional pricing, bundling, or reorder suspension."
                )
            else:
                recommendation = f"'{product.name}' is moving well — flagged by rule: {flagged_by_rule}."
        else:
            # ---- Layer 5: index-derived classification ----
            if stagnation_index >= settings_obj.dead_index_threshold:
                classification = StockClassification.DEAD
                if last_sold is None:
                    recommendation = (
                        f"'{product.name}' has no recorded sales (dominant factor: {dominant}). "
                        f"Consider clearance sale, write-off, or return to supplier. "
                        f"Suspend further purchasing."
                    )
                else:
                    recommendation = (
                        f"'{product.name}' has not been sold in {days_since} days "
                        f"(dominant factor: {dominant}). Consider clearance sale, write-off, "
                        f"or return to supplier. Suspend further purchasing."
                    )
            elif stagnation_index >= settings_obj.slow_index_threshold:
                classification = StockClassification.SLOW
                recommendation = (
                    f"'{product.name}' is slow-moving (dominant factor: {dominant}). "
                    f"Consider promotional pricing, bundling, or reorder suspension."
                )
            else:
                classification = StockClassification.FAST
                recommendation = f"'{product.name}' is moving well. Turnover rate: {turnover}."

    age_ratio = (
        Decimal(min(stock_age_days, min_observation_days)) / min_observation_days
        if min_observation_days else Decimal('1.00')
    )
    event_ratio = (
        Decimal(min(sale_event_count, min_sale_events)) / min_sale_events
        if min_sale_events else Decimal('1.00')
    )
    confidence = min(Decimal('1.00'), (age_ratio + event_ratio) / 2).quantize(Decimal('0.01'))

    InventoryClassification.objects.update_or_create(
        product=product,
        defaults={
            'classification': classification,
            'turnover_rate': turnover,
            'last_sold_date': last_sold,
            # BUG-72 (docs/bugsfound.md) — never store a numeric
            # days_since_last_sale when last_sold_date is None.
            'days_since_last_sale': days_since,
            'recommendation': recommendation,
            'flagged_by_rule': flagged_by_rule,
            'stagnation_index': stagnation_index,
            'confidence': confidence,
            'recency_score': recency_score,
            'turnover_score': turnover_score,
            'coverage_score': coverage_score,
            'frequency_score': frequency_score,
        }
    )
    return classification


def run_full_classification():
    """Classify all active products. Returns
    {'fast': n, 'slow': n, 'dead': n, 'insufficient_data': n}."""
    settings_obj = SystemSettings.get_settings()
    products = Product.objects.filter(is_active=True)
    results = {
        StockClassification.FAST: 0,
        StockClassification.SLOW: 0,
        StockClassification.DEAD: 0,
        StockClassification.INSUFFICIENT_DATA: 0,
    }

    for product in products:
        cls = classify_product(product, settings_obj)
        results[cls] += 1

    return results
