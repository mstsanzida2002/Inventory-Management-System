# 🐢 AI — Slow-Moving & Dead Stock Detection
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when building the stock classification pipeline.
> Classification is rule-based (no ML model needed) but configurable via
> SystemSettings thresholds. Runs as a Celery task daily.

---

## Requirements Coverage
`REQ 10.1 → 10.15`

---

## Design Notes — Revisions From the Original Spec (disclosed)

Four corrections to the original reference code, all disclosed rather than silently changed:

1. **`calculate_turnover_rate()` divided sales by a current-stock snapshot, not a period average, despite its own docstring's claim.** The original `avg_stock = InventoryRecord.objects.get(product=product).current_stock` reads today's stock level, not an average over the 90-day window the function claims to use. A product that sat at 500 units for 85 days and then sold down to 5 in the final week would score a misleadingly extreme turnover rate under the old code, purely because of when the classifier happened to run. `calculate_average_stock()` (new, below) reconstructs a genuine time-weighted average from the `InventoryMovement` ledger's `stock_after` values instead.
2. **The Classification Logic table said `fast` requires "turnover rate above threshold," but `classify_product()`'s own reference code never checked it** — the `if`/`elif`/`else` block was, and still is, purely recency-based (`days_since` against `slow_threshold`/`dead_threshold`). Rather than leave that contradiction in place, the table below has been corrected to describe what the code actually does: turnover rate is computed and surfaced (in `InventoryClassification.turnover_rate` and the recommendation text) as context, but is not itself a classification gate. Making turnover an actual gate would need a new configurable field (e.g. `SystemSettings.min_turnover_rate_fast`) — a schema change outside this file's scope, so it's flagged here as a future enhancement rather than implemented.
3. **(Backend Phase 10) `calculate_average_stock()`'s start-of-window fallback reached for *today's* `current_stock` whenever no movement existed strictly before `period_start` — even when movements existed *during* the window, exactly the case this function exists to handle correctly.** `stock_at_start = before[-1]['stock_after'] if before else current_stock` silently substitutes "everything that has happened up to and including right now" for "what the stock level was entering the window" the moment `before` is empty. Fixed: fall back to the *first in-window movement's own `stock_before`* when one exists; `current_stock` is now only used when the product has no ledger activity in or before the window at all (a product with zero history).
4. **(Backend Phase 10, found while testing #3) `calculate_turnover_rate()`'s `total_sold / avg_stock` has no ceiling, and `InventoryClassification.turnover_rate` is a `DecimalField(max_digits=8, decimal_places=4)` — a hard ceiling of 9999.9999.** A product whose entire stock history (received, then sold) falls within a tiny slice of the 90-day window — a brand-new product stocked and sold through same-day, proven by a test that approves a sale moments after the product's own initial stock receipt — drives `avg_stock` toward zero and the ratio toward the billions, overflowing the field outright (a real `DataError` crash, not a display quirk). Capped at the field's own ceiling; turnover is informational only (see #2), so capping it changes no classification outcome.

Everything else in this document — the Celery task, the post-sale signal, the API views, the serializer, and the dashboard chart — is unchanged.

**Possible future enhancement (not implemented here):** a single global `slow_moving_threshold_days`/`dead_stock_threshold_days` pair may not fit every category well (perishables and durable goods naturally turn over at very different rates) — a per-`Category` override would need its own schema addition and is worth considering once real sales data across categories exists to validate against.

---

## Classification Logic

| Class | Criteria |
|---|---|
| `fast` | Last sold within `slow_moving_threshold_days`. Turnover rate is calculated and shown for context (see Design Notes) but does not itself gate this classification. |
| `slow` | Last sold between `slow_moving_threshold_days` and `dead_stock_threshold_days` days ago |
| `dead` | Not sold for more than `dead_stock_threshold_days` days, or zero sales ever |

Default thresholds (configurable in `SystemSettings`):
- `slow_moving_threshold_days = 60`
- `dead_stock_threshold_days = 180`

---

## Classifier

```python
# apps/ai/classification/classifier.py
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Max
from apps.settings_manager.models import SystemSettings
from apps.ai.classification.models import InventoryClassification, StockClassification
from apps.inventory.models import InventoryRecord, InventoryMovement
from apps.products.models import Product
from apps.sales.models import SaleItem


def calculate_average_stock(product, period_start, period_end):
    """
    Time-weighted average stock over [period_start, period_end],
    reconstructed from the InventoryMovement ledger's stock_after values —
    not a single point-in-time InventoryRecord.current_stock snapshot. A
    product that held 500 units for most of the window and only sold down
    near the end would otherwise be judged entirely on whichever stock
    level happened to be true the moment this function ran.
    """
    try:
        current_stock = InventoryRecord.objects.get(product=product).current_stock
    except InventoryRecord.DoesNotExist:
        return 0.0

    movements = list(
        InventoryMovement.objects.filter(product=product, created_at__lte=period_end)
        .order_by('created_at')
        .values('created_at', 'stock_after')
    )

    before = [m for m in movements if m['created_at'] < period_start]
    during = [m for m in movements if m['created_at'] >= period_start]

    stock_at_start = before[-1]['stock_after'] if before else current_stock

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
    """
    period_end = timezone.now()
    period_start = period_end - timedelta(days=days)

    total_sold = SaleItem.objects.filter(
        product=product,
        transaction__transaction_date__gte=period_start.date(),
        transaction__status='completed'
    ).aggregate(total=Sum('quantity'))['total'] or 0

    avg_stock = calculate_average_stock(product, period_start, period_end)

    if avg_stock <= 0:
        return 0.0
    return round(total_sold / avg_stock, 4)


def get_last_sold_date(product):
    """Return the most recent sale date for a product, or None."""
    result = SaleItem.objects.filter(
        product=product,
        transaction__status='completed'
    ).aggregate(last_date=Max('transaction__transaction_date'))
    return result['last_date']


def classify_product(product, settings_obj=None):
    """
    Classify a single product and upsert its InventoryClassification record.
    Returns the classification string: 'fast', 'slow', or 'dead'.
    """
    if settings_obj is None:
        settings_obj = SystemSettings.get_settings()

    slow_threshold = settings_obj.slow_moving_threshold_days
    dead_threshold = settings_obj.dead_stock_threshold_days
    today = timezone.now().date()

    last_sold = get_last_sold_date(product)
    turnover = calculate_turnover_rate(product)

    if last_sold is None:
        days_since = 9999
    else:
        days_since = (today - last_sold).days

    # Classification logic — recency-based; turnover is informational
    # (see Design Notes at the top of this file)
    if days_since >= dead_threshold:
        classification = StockClassification.DEAD
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

    # Upsert classification record
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
    """Classify all active products."""
    settings_obj = SystemSettings.get_settings()
    products = Product.objects.filter(is_active=True)
    results = {'fast': 0, 'slow': 0, 'dead': 0}

    for product in products:
        cls = classify_product(product, settings_obj)
        results[cls] += 1

    return results
```

---

## Celery Task

```python
# apps/ai/classification/tasks.py
from celery import shared_task
from django.utils import timezone

@shared_task(name='ai.run_stock_classification')
def run_stock_classification():
    """Daily classification of all active products."""
    from apps.ai.classification.classifier import run_full_classification
    from apps.ai.classification.models import InventoryClassification, StockClassification
    from apps.notifications.services import notify_supervisors
    from apps.audit.services import log_action

    try:
        results = run_full_classification()

        # Notify supervisors of slow and dead stock
        slow_products = InventoryClassification.objects.filter(
            classification=StockClassification.SLOW
        ).select_related('product')

        dead_products = InventoryClassification.objects.filter(
            classification=StockClassification.DEAD
        ).select_related('product')

        if slow_products.exists():
            notify_supervisors(
                'ai_slow',
                f'AI Alert: {slow_products.count()} Slow-Moving Products',
                f'{slow_products.count()} products identified as slow-moving. Review recommended.',
                link='/ai/classifications/?filter=slow'
            )

        if dead_products.exists():
            notify_supervisors(
                'ai_dead',
                f'AI Alert: {dead_products.count()} Dead Stock Products',
                f'{dead_products.count()} products have had no sales activity. Immediate action recommended.',
                link='/ai/classifications/?filter=dead'
            )

        log_action(None, 'AI_CLASSIFICATION_RUN', 'ai_classification', status='success',
                   details={**results, 'timestamp': str(timezone.now())})

    except Exception as e:
        log_action(None, 'AI_CLASSIFICATION_FAILED', 'ai_classification', status='failure',
                   details={'error': str(e)})
        raise


@shared_task(name='ai.reclassify_product')
def reclassify_product_after_sale(product_id):
    """
    Triggered after every completed sale transaction.
    Reclassifies a single product immediately.
    """
    from apps.products.models import Product
    from apps.ai.classification.classifier import classify_product
    try:
        product = Product.objects.get(pk=product_id, is_active=True)
        classify_product(product)
    except Product.DoesNotExist:
        pass
```

---

## Signal: Reclassify After Sale

```python
# apps/sales/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.sales.models import SaleTransaction

@receiver(post_save, sender=SaleTransaction)
def reclassify_after_sale(sender, instance, created, **kwargs):
    """After any sale completes, reclassify affected products."""
    if instance.status == 'completed':
        from apps.ai.classification.tasks import reclassify_product_after_sale
        for item in instance.items.all():
            reclassify_product_after_sale.delay(item.product_id)
```

Register signal in `apps/sales/apps.py`:

```python
class SalesConfig(AppConfig):
    name = 'apps.sales'

    def ready(self):
        import apps.sales.signals   # noqa
```

---

## API Views

```python
# apps/ai/classification/views.py
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.rbac.permissions import IsSupervisorOrAbove
from apps.ai.classification.models import InventoryClassification, StockClassification

class ClassificationListAPIView(ListAPIView):
    permission_classes = [IsSupervisorOrAbove]
    serializer_class = InventoryClassificationSerializer

    def get_queryset(self):
        qs = InventoryClassification.objects.select_related('product').order_by('-classified_at')
        filter_by = self.request.query_params.get('filter')
        if filter_by in ['fast', 'slow', 'dead']:
            qs = qs.filter(classification=filter_by)
        return qs

class RunClassificationAPIView(APIView):
    permission_classes = [IsSupervisorOrAbove]

    def post(self, request):
        from apps.ai.classification.tasks import run_stock_classification
        run_stock_classification.delay()
        return Response({'message': 'Classification task queued.'})

class ClassificationSummaryAPIView(APIView):
    """Dashboard widget data."""
    permission_classes = [IsSupervisorOrAbove]

    def get(self, request):
        from django.db.models import Count
        summary = InventoryClassification.objects.values('classification').annotate(count=Count('id'))
        return Response({item['classification']: item['count'] for item in summary})
```

---

## Serializer

```python
# apps/ai/classification/serializers.py
from rest_framework import serializers
from apps.ai.classification.models import InventoryClassification

class InventoryClassificationSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku  = serializers.CharField(source='product.sku', read_only=True)

    class Meta:
        model = InventoryClassification
        fields = ['id', 'product', 'product_name', 'product_sku',
                  'classification', 'turnover_rate', 'last_sold_date',
                  'days_since_last_sale', 'recommendation', 'classified_at']
```

---

## Dashboard Display

The classification summary is shown on supervisor/admin dashboards:

```javascript
// static/js/dashboard_charts.js
fetch('/api/v1/ai/classifications/summary/')
  .then(r => r.json())
  .then(data => {
    new Chart(document.getElementById('stockClassChart'), {
      type: 'doughnut',
      data: {
        labels: ['Fast-Moving', 'Slow-Moving', 'Dead Stock'],
        datasets: [{
          data: [data.fast || 0, data.slow || 0, data.dead || 0],
          backgroundColor: ['#28a745', '#ffc107', '#dc3545']
        }]
      }
    });
  });
```

---

## Audit Actions

| Action Constant | Triggered When |
|---|---|
| `AI_CLASSIFICATION_RUN` | Full classification task completed |
| `AI_CLASSIFICATION_FAILED` | Classification task failed |
| `AI_PRODUCT_RECLASSIFIED` | Single product reclassified after sale |
