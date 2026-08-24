"""
docs/DEAD_STOCK_DETECTION.md, translated into the single `frontend` app —
no `apps/ai/classification/` app created (see docs/project_memory.md §13:
this project deliberately stays single-app at this stage). Matches the
existing small-dedicated-module pattern (frontend/audit.py,
frontend/notifications.py, frontend/reports.py).

Rule-based classification (recency-based; turnover is computed and stored
for context but is not itself a classification gate — see the doc's own
"Design Notes — Revisions From the Original Spec", which already corrects
two things in the original reference code before this file even starts).
No ML model this phase, no Celery — run_full_classification() is called
synchronously, either from a real approve_sale()/cancel_sale() event
(single product, see frontend/services.py) or from the manual "Run
classification now" button (SlowMovingDeadStockView.post()).

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
"""
from datetime import timedelta

from django.db.models import Max, Sum
from django.utils import timezone

from frontend.approvals import recompute_abc_classes
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


def calculate_turnover_rate(product, days=90):
    """
    Turnover rate = total units sold in period / time-weighted average
    stock held over the period. Returns float (higher = faster moving).
    Informational only — see classify_product()'s own docstring for why
    this never gates the classification itself.
    """
    period_end = timezone.now()
    period_start = period_end - timedelta(days=days)

    total_sold = SaleItem.objects.filter(
        product=product,
        transaction__transaction_date__gte=period_start.date(),
        transaction__status=SaleStatus.COMPLETED,
    ).aggregate(total=Sum('quantity'))['total'] or 0

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
    # classification gate (see classify_product()'s own docstring), so
    # capping it changes no classification outcome.
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


def classify_product(product, settings_obj=None):
    """
    Classify a single product and upsert its InventoryClassification
    record. Returns the classification string: StockClassification.FAST/
    SLOW/DEAD.
    """
    if settings_obj is None:
        settings_obj = SystemSettings.get_settings()

    slow_threshold = settings_obj.slow_moving_threshold_days
    dead_threshold = settings_obj.dead_stock_threshold_days
    today = timezone.localdate()

    last_sold = get_last_sold_date(product)
    turnover = calculate_turnover_rate(product)

    if last_sold is None:
        days_since = 9999
    else:
        days_since = (today - last_sold).days

    # Classification logic — recency-based; turnover is informational
    # (see docs/DEAD_STOCK_DETECTION.md's Design Notes revision #2 — the
    # doc's own reference code never actually gated on turnover despite an
    # earlier version of the Classification Logic table claiming it did;
    # the table's since been corrected to match the code, and this
    # implementation matches both).
    if days_since >= dead_threshold:
        classification = StockClassification.DEAD
        # Phase 10 — the never-sold sentinel (days_since == 9999) must
        # never reach user-facing copy. Same established precedent this
        # project already applied to slow_moving.html's mock text
        # (docs/project_memory.md §13): "9999" reads as a leaked
        # implementation detail, not real information, to anyone viewing
        # this recommendation.
        if last_sold is None:
            recommendation = (
                f"'{product.name}' has no recorded sales. "
                f"Consider clearance sale, write-off, or return to supplier. "
                f"Suspend further purchasing."
            )
        else:
            recommendation = (
                f"'{product.name}' has not been sold in {days_since} days. "
                f"Consider clearance sale, write-off, or return to supplier. "
                f"Suspend further purchasing."
            )
    elif days_since >= slow_threshold:
        classification = StockClassification.SLOW
        recommendation = (
            f"'{product.name}' is slow-moving (last sold {days_since} days ago). "
            f"Consider promotional pricing, bundling, or reorder suspension."
        )
    else:
        classification = StockClassification.FAST
        recommendation = f"'{product.name}' is moving well. Turnover rate: {turnover}."

    InventoryClassification.objects.update_or_create(
        product=product,
        defaults={
            'classification': classification,
            'turnover_rate': turnover,
            'last_sold_date': last_sold,
            'days_since_last_sale': days_since if days_since < 9999 else 0,
            'recommendation': recommendation,
        }
    )
    return classification


def run_full_classification():
    """Classify all active products. Returns {'fast': n, 'slow': n, 'dead': n}."""
    settings_obj = SystemSettings.get_settings()
    products = Product.objects.filter(is_active=True)
    results = {StockClassification.FAST: 0, StockClassification.SLOW: 0, StockClassification.DEAD: 0}

    for product in products:
        cls = classify_product(product, settings_obj)
        results[cls] += 1

    # Phase 12 — recompute_abc_classes() folded in here rather than its
    # own scheduled task (no Celery exists in this project, see that
    # function's own docstring in frontend/approvals.py): every product
    # above just got a fresh classify_product() row, so this always has
    # somewhere real to write abc_class onto, and every manual "Run
    # classification now" click keeps ABC ranking current too.
    recompute_abc_classes()

    return results
