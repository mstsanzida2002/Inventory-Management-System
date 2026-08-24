# 🐢 AI — Slow-Moving & Dead Stock Detection
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when building the stock classification pipeline.
> Classification is a multi-criteria weighted expert system (no ML model
> needed) — a configurable knowledge base of per-factor weights and
> index thresholds in `SystemSettings`, not a single hardcoded rule (see
> Design Notes #5 and the Classification Logic table below).
>
> **There is no scheduler anywhere in this project — no Celery, no cron,
> nothing.** Reclassification is event-driven: it runs synchronously on
> sale approval/cancellation (the one real signal that changes a
> product's sales history) and on demand via the "Run classification
> now" button. This is the deliberate architecture, not a gap left by an
> unbuilt scheduler — it needs no background-worker infrastructure, and
> every classification an admin sees was computed from a real trigger,
> never a cron tick nobody can point to. Stated honestly: nothing
> recomputes when a product simply *stops* selling — no event fires for
> "time passed with no sale" — so a classification can go stale between
> triggers (a sale on some other product, or the next manual run) until
> one of those two triggers fires again.

---

## Requirements Coverage
`REQ 10.1 → 10.15`

---

## Design Notes — Revisions From the Original Spec (disclosed)

Four corrections to the original reference code, all disclosed rather than silently changed:

1. **`calculate_turnover_rate()` divided sales by a current-stock snapshot, not a period average, despite its own docstring's claim.** The original `avg_stock = InventoryRecord.objects.get(product=product).current_stock` reads today's stock level, not an average over the 90-day window the function claims to use. A product that sat at 500 units for 85 days and then sold down to 5 in the final week would score a misleadingly extreme turnover rate under the old code, purely because of when the classifier happened to run. `calculate_average_stock()` (new, below) reconstructs a genuine time-weighted average from the `InventoryMovement` ledger's `stock_after` values instead.
2. **RETIRED — NOW IMPLEMENTED (see Design Note #5).** Originally: "The Classification Logic table said `fast` requires 'turnover rate above threshold,' but `classify_product()`'s own reference code never checked it... Making turnover an actual gate would need a new configurable field — a schema change outside this file's scope, so it's flagged here as a future enhancement rather than implemented." Prompt 2 (2026-08-24) is exactly that schema change: turnover is now one of four weighted factors that genuinely gates the classification, not informational-only context. The single-factor recency branch this note was describing no longer exists.
3. **(Backend Phase 10) `calculate_average_stock()`'s start-of-window fallback reached for *today's* `current_stock` whenever no movement existed strictly before `period_start` — even when movements existed *during* the window, exactly the case this function exists to handle correctly.** `stock_at_start = before[-1]['stock_after'] if before else current_stock` silently substitutes "everything that has happened up to and including right now" for "what the stock level was entering the window" the moment `before` is empty. Fixed: fall back to the *first in-window movement's own `stock_before`* when one exists; `current_stock` is now only used when the product has no ledger activity in or before the window at all (a product with zero history).
4. **(Backend Phase 10, found while testing #3) `calculate_turnover_rate()`'s `total_sold / avg_stock` has no ceiling, and `InventoryClassification.turnover_rate` is a `DecimalField(max_digits=8, decimal_places=4)` — a hard ceiling of 9999.9999.** A product whose entire stock history (received, then sold) falls within a tiny slice of the 90-day window — a brand-new product stocked and sold through same-day, proven by a test that approves a sale moments after the product's own initial stock receipt — drives `avg_stock` toward zero and the ratio toward the billions, overflowing the field outright (a real `DataError` crash, not a display quirk). Capped at the field's own ceiling; still informational for the Turnover *factor's own normalisation* (`1 / (1 + turnover_rate)`, self-bounding regardless of the cap), so this cap protects the DB column, not a classification outcome.
5. **(Prompt 2, 2026-08-24) Upgraded from the single-factor recency branch to a multi-criteria weighted expert system with a configurable knowledge base — superseded by Design Note #6 below; see the Classification Logic table for the real, current behaviour.** In brief: four factors (Recency, Turnover, Coverage, Frequency), each normalised to 0.00–1.00, combined via admin-configurable weights into a 0–100 stagnation index. ABC classification (`ABCClass`, `InventoryClassification.abc_class`, `recompute_abc_classes()`) was removed in this same pass — never part of any documented requirement (confirmed by a full grep of `docs/*.md`), so it wasn't "downgraded," it was out of scope from the start; see `docs/project_memory.md` for the full disclosure.
6. **(PROMPT_1B, 2026-08-24) The first live run of Design Note #5's design against real shaped seed data produced ZERO dead-stock classifications on data known to contain dead stock — a detection regression against the old day-threshold rule it replaced.** Full incident in `docs/bugsfound.md`. Root cause, in two parts: (a) `insufficient_data` gated on sale-event count as well as age; since that count was windowed to the same trailing 90 days as demand, a product that sold steadily for a year and then went quiet 200+ days ago had zero events in the window — indistinguishable, to the gate, from a product that had never had the chance to sell at all. All 5 of the real dev run's genuinely dead products were diverted to `insufficient_data` before the index ever saw them. (b) Two of the four factors were mathematically incapable of varying: `frequency_score`'s old formula was pinned at exactly 0 for every product that cleared the event-count gate (a structural contradiction between the gate and the formula it fed), and `coverage_score` clamped to 1.00 the instant `days_of_cover` crossed `target_days_of_cover`, saturating 30 of 33 scored products in the same run. With two of four factors constant, the index reproduced its own mean regardless of the product (stdev 4.82). **Fixed** — see the Classification Logic table below for the resulting design: the gate is now age-only (event count feeds `confidence` instead, which is what it should always have done); Frequency counts distinct weekly buckets with a sale instead of a formula the gate had already zeroed out; Coverage ramps linearly between `target_days_of_cover` and a new `extreme_coverage_days` setting instead of clamping at the low end; and a new override layer (Force-DEAD/Force-SLOW/Force-FAST, evaluated on raw signals *before* the gate and the index) preserves the old day-threshold rule as an explicit floor, so nothing the old rule caught can be lost to the newer machinery again. Re-measured on the same seed data after the fix: index stdev rose from 4.82 to 25.30, all four factor variances went from at-or-near-zero to real spread, and the distribution matched every anti-regression and non-degeneracy check (see Classification Logic and `docs/bugsfound.md`). Only findable by running against shaped seed data and breaking the composite down by per-factor variance — code review and unit tests against synthetic single-factor fixtures had both already passed.

**Weights examined and consciously retained, not silently inherited.** After the Design Note #6 fixes, the default weights (0.40/0.30/0.20/0.10) were re-examined against the *post-fix* per-factor variance (recency 0.331, turnover 0.135, coverage 0.338, frequency 0.299 — see `docs/project_memory.md` for the full re-measurement) and deliberately kept as-is, not made variance-proportional. Reasoning: the weights encode business policy (how much each signal *should* matter to a supervisor), not a statistical fit — deriving them from one 43-product seed catalogue's variance would tune the classifier against synthetic data's shape rather than the businesses this system is meant to generalise to (a real SME with a mixed durables/perishables catalogue would show a very different variance profile; Turnover's comparatively tight spread here reflects this seed set, not Turnover's real-world relevance). The resulting class separation (fast 21-39 / slow 43-48 / dead 75-100 on the re-measured data, with both thresholds sitting cleanly in the gaps between clusters) was judged too clean to perturb for an unproven statistical gain.

Everything else in this document — the Celery task, the post-sale signal, the API views, the serializer, and the dashboard chart reference code blocks below — is kept as historical reference code (this project's translation lives in `frontend/classification.py`/`frontend/views.py`/`frontend/api_views.py`/`frontend/serializers.py`/`frontend/static/js/slow-moving.js`, not this file); Design Note #6 above and the Classification Logic table are the authoritative description of what those files actually do today.

**Possible future enhancement (not implemented here):** a single global `slow_moving_threshold_days`/`dead_stock_threshold_days` pair may not fit every category well (perishables and durable goods naturally turn over at very different rates) — a per-`Category` override would need its own schema addition and is worth considering once real sales data across categories exists to validate against.

---

## Classification Logic

Real behaviour as of PROMPT_1B (2026-08-24) — see Design Note #6. **Two
layers, evaluated strictly in this order; each can be short-circuited by
the one before it.** This precedence exists specifically because the
first version of Layer 2 (the weighted index alone) lost real dead stock
to `insufficient_data` before ever scoring it — see Design Note #6.

### Layer 1 — override rules (raw signals, checked before anything else)

| Rule | Condition | Result |
|---|---|---|
| Force dead | `days_since_last_sale >= dead_stock_threshold_days` AND `current_stock > 0` | `dead` |
| Force dead | Never sold AND `stock_age_days >= dead_stock_threshold_days` AND `current_stock > 0` | `dead` |
| Force slow | `days_of_cover >= extreme_coverage_days` **AND** `stagnation_index < dead_index_threshold` (Layer 2's own index, computed first — see below) | `slow` |
| Force fast | Sold within the last 14 days **AND** `days_of_cover <= target_days_of_cover` | `fast` |

The two Force-dead rules together are what preserve the old day-threshold
rule as a floor: anything the old rule called dead is still dead here,
regardless of what the index would otherwise say — this is the
non-regression guarantee. DEAD and FAST can never both match the same
product (mutually exclusive conditions); DEAD is checked first. Force-slow
is the one rule with a second precondition, added after a design review:
without it, Force-slow would act as a *ceiling*, quietly downgrading a
product the index had already independently flagged dead on more than
just coverage (a real case: recency 0.42, turnover 0.96, coverage 1.00,
frequency 0.92 — every factor high, not just coverage) back down to
`slow`. Force-slow is meant as a *floor* for extreme overstock the index
might still call fast-ish, never a ceiling on a product already flagged
dead on its own merits — so it only applies when the index agrees the
product isn't there yet. `flagged_by_rule` on `InventoryClassification`
records which rule fired, in plain language ("No sales in 210 days"),
for any Layer-1 decision — worth more to a supervisor than an opaque
index number.

### Layer 2 — not old enough to score

| Class | Criteria |
|---|---|
| `insufficient_data` | `stock_age_days < min_observation_days`, **and no Layer 1 rule fired.** AGE ONLY — sale-event count does not gate this (Design Note #6). Not a problem state: never counted in `total_flagged`, never notified. |

### Layer 3 — weighted stagnation index (only reached if nothing above decided it)

| Class | Criteria |
|---|---|
| `fast` | `stagnation_index < slow_index_threshold` |
| `slow` | `slow_index_threshold <= stagnation_index < dead_index_threshold` |
| `dead` | `stagnation_index >= dead_index_threshold` |

`stagnation_index` (0–100) is `round(100 * (weight_recency * recency_score + weight_turnover * turnover_score + weight_coverage * coverage_score + weight_frequency * frequency_score))`, and is always computed once a product is past Layer 2 — even when a Layer-1 rule already decided the classification, so a supervisor can still see the underlying factor scores, not just the rule text. Each factor is normalised to 0.00–1.00 (1.00 = maximally stagnant):

| Factor | Normalisation |
|---|---|
| Recency | `min(days_since_last_sale / dead_stock_threshold_days, 1.00)`. Never sold (but past the `insufficient_data` gate) -> 1.00. |
| Turnover | `1 / (1 + turnover_rate)` — self-normalising, no separate setting. `turnover_rate` 0 -> 1.00; higher turnover asymptotically -> 0. |
| Coverage | `current_stock == 0` -> 0.00 (nothing tied up, nothing at risk, regardless of demand). `current_stock > 0` and `avg_daily_demand == 0` -> 1.00 (real stock, zero demand — the core dead-stock signal). Otherwise a **linear ramp**: `days_of_cover <= target_days_of_cover` -> 0.00; `days_of_cover >= extreme_coverage_days` -> 1.00; between the two, `(days_of_cover - target_days_of_cover) / (extreme_coverage_days - target_days_of_cover)`. Linear rather than log: Layer 1's Force-slow rule already absorbs the truly extreme tail, so this ramp only has to discriminate the middle band between the two settings, where a straight line is both adequate and easier for an admin to reason about. |
| Frequency | `1 - (distinct weekly buckets with a sale / total buckets)` over the trailing 90 days, in 7-day buckets (12 buckets total) — **not** a formula keyed to `min_sale_events` (Design Note #6: that coupling is exactly what pinned this factor at 0). A steady weekly seller scores near 0; a single bulk sale scores near 1 — independent of any gate. |

`avg_daily_demand`, `days_of_cover`, and the Frequency factor's bucket
window all read the same trailing 90-day window `calculate_turnover_rate()`
already uses — never a second window.

Default weights/thresholds (all configurable in `SystemSettings` — the
classifier's "knowledge base"; the four weights must sum to exactly
1.00, rejected on save otherwise; **examined against post-fix per-factor
variance and consciously retained, not carried forward blind — see
Design Note #6 for the full reasoning**):
- `weight_recency = 0.40`, `weight_turnover = 0.30`, `weight_coverage = 0.20`, `weight_frequency = 0.10`
- `slow_index_threshold = 40`, `dead_index_threshold = 70`
- `target_days_of_cover = 90`, `extreme_coverage_days = 730`
- `min_observation_days = 30`
- `min_sale_events = 2` — no longer part of any gate; feeds `confidence` only
- `slow_moving_threshold_days = 60`, `dead_stock_threshold_days = 180` — `dead_stock_threshold_days` is both the Recency factor's normalisation input AND the Force-dead override's own threshold; `slow_moving_threshold_days` is currently unused by the classifier itself (kept for any UI copy still referencing it)

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
