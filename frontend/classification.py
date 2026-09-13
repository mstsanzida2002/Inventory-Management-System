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

# Rule: one shared window -- every demand-derived figure here reads it.
_DEMAND_WINDOW_DAYS = 90

# Rule: 7-day buckets distinguish a steady weekly seller from one bulk sale.
_FREQUENCY_BUCKET_DAYS = 7
_FREQUENCY_TOTAL_BUCKETS = _DEMAND_WINDOW_DAYS // _FREQUENCY_BUCKET_DAYS

# Rule: 14 days -- wide enough to include a ~10-day sale cycle as "fast".
_FORCE_FAST_RECENT_SALE_DAYS = 14


def calculate_average_stock(product, period_start, period_end):
    """Time-weighted average stock over the window, from the movement ledger."""
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

    # Rule: entering stock is the first in-window movement, not today's level.
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
    period_start = timezone.now() - timedelta(days=days)
    return SaleItem.objects.filter(
        product=product,
        transaction__transaction_date__gte=period_start.date(),
        transaction__status=SaleStatus.COMPLETED,
    ).aggregate(total=Sum('quantity'))['total'] or 0


def _sale_event_count(product, days=_DEMAND_WINDOW_DAYS):
    # Rule: feeds confidence only -- does not gate insufficient_data.
    period_start = timezone.now() - timedelta(days=days)
    return SaleItem.objects.filter(
        product=product,
        transaction__transaction_date__gte=period_start.date(),
        transaction__status=SaleStatus.COMPLETED,
    ).count()


def _distinct_sale_buckets(product, days=_DEMAND_WINDOW_DAYS, bucket_days=_FREQUENCY_BUCKET_DAYS):
    # Rule: counts weekly buckets with a sale -- independent of any gate.
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
    # Assumption: anchored to the first movement, or creation if never moved.
    first_movement_at = (
        InventoryMovement.objects.filter(product=product)
        .order_by('created_at')
        .values_list('created_at', flat=True)
        .first()
    )
    anchor = first_movement_at or product.created_at
    return max((timezone.now() - anchor).days, 0)


def calculate_turnover_rate(product, days=_DEMAND_WINDOW_DAYS):
    """Units sold / time-weighted average stock; informational, never a gate."""
    period_end = timezone.now()
    period_start = period_end - timedelta(days=days)

    total_sold = _total_sold(product, days=days)
    avg_stock = calculate_average_stock(product, period_start, period_end)

    if avg_stock <= 0:
        return 0.0
    # Edge: capped at the DecimalField's ceiling -- avoids an overflow crash.
    return min(round(total_sold / avg_stock, 4), 9999.9999)


def get_last_sold_date(product):
    """Most recent COMPLETED sale date for a product, or None."""
    result = SaleItem.objects.filter(
        product=product,
        transaction__status=SaleStatus.COMPLETED,
    ).aggregate(last_date=Max('transaction__transaction_date'))
    return result['last_date']


def _dominant_factor(weighted_scores):
    return max(weighted_scores, key=lambda pair: pair[1])[0]


def _evaluate_hard_overrides(*, days_since, stock_age_days, current_stock, days_of_cover,
                              dead_threshold, target_days_of_cover):
    # Rule: DEAD checked before FAST -- the two conditions are mutually exclusive.
    if days_since is not None and days_since >= dead_threshold and current_stock > 0:
        return StockClassification.DEAD, f"No sales in {days_since} days"

    # Rule: never-sold long-established stock is DEAD, same floor as recency.
    if days_since is None and stock_age_days >= dead_threshold and current_stock > 0:
        return StockClassification.DEAD, f"Never sold, {stock_age_days} days in stock"

    if (days_since is not None and days_since <= _FORCE_FAST_RECENT_SALE_DAYS
            and days_of_cover is not None and days_of_cover <= target_days_of_cover):
        return StockClassification.FAST, f"Sold {days_since} day(s) ago, {round(days_of_cover)} days of cover"

    return None, ''


def classify_product(product, settings_obj=None):
    """Classifies one product and upserts its InventoryClassification row."""
    # Assumption: runs synchronously -- approve_sale()/cancel_sale() block on it.
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

    # Edge: a 0-valued setting would divide-by-zero or degenerate the index.
    dead_threshold = settings_obj.dead_stock_threshold_days or 1
    target_days_of_cover = settings_obj.target_days_of_cover or 1
    extreme_coverage_days = settings_obj.extreme_coverage_days or 1

    avg_daily_demand = _total_sold(product) / float(_DEMAND_WINDOW_DAYS)
    days_of_cover = (
        current_stock / avg_daily_demand
        if current_stock > 0 and avg_daily_demand > 0 else None
    )

    # Security: hard overrides bypass the gate and index -- raw signals only.
    hard_classification, hard_rule = _evaluate_hard_overrides(
        days_since=days_since, stock_age_days=stock_age_days, current_stock=current_stock,
        days_of_cover=days_of_cover, dead_threshold=dead_threshold,
        target_days_of_cover=target_days_of_cover,
    )

    # Rule: age only gates insufficient_data -- sale count no longer does.
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
        # Rule: index is always computed past the gate, even if overridden.
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
            # Rule: linear ramp -- Force-SLOW below already covers the extreme tail.
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

        # Rule: Force-SLOW is a floor for overstock, never a ceiling on DEAD.
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
            classification = None
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
            # Rule: reached only when nothing above fired -- index decides.
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

    # Rule: confidence averages age ratio and event ratio, each capped at 1.
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
            # Edge: never a numeric stand-in for "never sold" when null.
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
    """Classifies all active products; returns counts per classification."""
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


def capital_at_risk(classification, stock_by_product):
    """current_stock * purchase_price, for DEAD/SLOW products only."""
    # Edge: None (not 0) for other classifications -- sorts last, never ties.
    if classification.classification not in (StockClassification.DEAD, StockClassification.SLOW):
        return None
    current_stock = stock_by_product.get(classification.product_id, 0)
    return Decimal(current_stock) * classification.product.purchase_price
