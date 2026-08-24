# 🤖 AI — Demand Forecasting
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when building the forecasting pipeline, training
> the Scikit-learn model, or exposing forecast results
> through API/dashboard endpoints.
>
> **Corrected (docs/bugsfound.md):** no Celery exists anywhere in this
> project — the Celery task and Celery Beat Schedule sections below are
> reference material only. Forecasting runs synchronously: on demand via
> the "Run forecast now" button (`DemandForecastingView.post()`), never
> on a periodic schedule. REQ 9.7 (and REQ 17.4, periodic retraining) are
> consequently PHANTOM, not implemented — disclosed here rather than left
> implied by the reference code below.

---

## Requirements Coverage
`REQ 9.1 → 9.15`

---

## Overview

The demand forecasting module analyzes historical sales data to predict future product demand and recommend optimal reorder quantities. It runs as a background Celery task on a configurable schedule and stores results in the `DemandForecast` model.

---

## Design Notes — Revisions From the Original Spec (disclosed)

This version changes several things from the original reference pipeline. Each is disclosed here with its reasoning rather than silently changed:

1. **`RandomForestRegressor` → `HistGradientBoostingRegressor`.** Tree ensembles generally can't extrapolate past the range of values seen in training — for a demand series with an upward trend, that means systematic *under*-forecasting on exactly the products where under-forecasting hurts most (stockouts on growing SKUs). `HistGradientBoostingRegressor` (still `sklearn.ensemble`, no new dependency) typically outperforms `RandomForestRegressor` on tabular regression at this data scale, trains faster, and — used here — supports native categorical features, which the original pipeline imported `LabelEncoder` for but never actually used.
2. **Random train/test split → chronological split.** The original `train_test_split(X, y, test_size=0.2, random_state=42)` shuffles rows, which lets the model train on periods that come *after* the ones it's evaluated on — something that never happens at real prediction time, and which makes the reported MAE optimistic. The split is now done by sorting on `period_start` and holding out the most recent ~20% of rows.
3. **Three-tier model selection (skip / `LinearRegression` / `RandomForest`) → two-tier (skip / pooled model).** The original middle tier (4–12 weeks → `LinearRegression` on 4 lag features) is fragile in practice: a noisy early spike in a 5-period series produces a wild slope that then gets extrapolated forward uncorrected. Rather than add a second bespoke model just for short-history products, this version relies on the fact that **one model is already trained on every product's history pooled together** — a short-history product still benefits from the pooled model's cross-product patterns (especially via `category_id`, point 4 below) without needing its own, less stable, separately-trained model. The only remaining gate is the original bottom tier: skip a product with under ~4 weeks of history entirely (still enforced implicitly by `build_features()`'s `dropna()`, since `lag_4` requires 4 prior periods before any row survives it).
4. **`category_id` and a `stockout_flag` added to the feature set.** The original "Data Pipeline" diagram already promised "category encoding" as a step, but the reference code never implemented it — the `LabelEncoder` import was unused. `category_id` is now a real, native-categorical feature, which is exactly what lets a new or short-history product borrow signal from others in the same category. `stockout_flag` is new: without it, a period where the product was simply out of stock reads to the model as "zero demand," which can suppress future reorder recommendations and compound the stockout it should be correcting.
5. **Fixed a lag-shifting bug in `predict_demand()`.** The original multi-step-ahead loop called `np.roll(last_row, 1)` on the *entire* feature vector, which also rotates `rolling_std_4`/`period_num`/(now) `category_id`/`stockout_flag` into the wrong slots after the first step-ahead prediction. Only the `lag_1..lag_4` block should shift — corrected to do that by index instead.
6. **Confidence score now comes from the model's own backtest residuals, not a last-row heuristic.** The original `confidence = min(0.95, max(0.50, 1 - (last_row[5] / (pred + 1))))` derived "confidence" from one row's rolling standard deviation, which has no real connection to how accurate the model has actually been. `train_model()` now persists the held-out backtest's residual standard deviation alongside the model, and `predict_demand()` uses that instead.
7. **Added a task to actually populate `DemandForecast.actual_demand`.** REQ 9.9 ("compare forecasted demand with actual sales") has a field for this in the schema, but nothing in the original spec ever wrote to it. `backfill_actual_demand` (new, in Celery Tasks below) closes that gap.

None of the above changes any other module's contract, the `DemandForecast` schema, the API response shapes, or the existing Celery task names/signatures — `retrain_forecast_model()` and `run_demand_forecasts()` still call `train_model()` / `predict_demand()` exactly as before.

### Further findings — a dedicated bug-fixing pass (disclosed)

A later pass audited this pipeline specifically for bugs, verifying every candidate against the actual running code and real dev data rather than trusting either this doc or a reading of the source alone. Two real, fixed bugs; one deliberate design decision made explicit; one design limitation logged but not fixed; one gap found in a downstream consumer, also not fixed (not in this pass's approved scope). Full detail, root cause, and fix for every item in `docs/bugsfound.md` (BUG-61 through BUG-64).

8. **`period_num` was frozen across `predict_demand()`'s multi-step loop — now advances by 1 per step (BUG-61).** The loop above (point 5) rotates only the `lag_1..lag_4` block and recomputes `rolling_avg_4`, but never touched `period_num` at all — every step of a multi-step forecast fed the model the exact same, last-observed `period_num`, telling it every future period was the same point in time. Present in this doc's own reference code too, and never addressed by revision #5, which fixed a different problem (the value landing in the wrong array slot after a full-vector rotation) — not this one (the value staying unchanged in the *right* slot). Confirmed empirically before fixing: instrumented the real loop against a real trained model and real dev data, and `period_num` fed to the model was identical across all 4 steps of a 4-step forecast. Fixed by incrementing `last_row`'s `period_num` once per iteration, before that step's `features` are captured — verified with a test that spies on the model's own `.predict()` calls and asserts `period_num` increases by exactly 1 each step.
9. **`forecast_period_weeks` was applied unconverted to the monthly run too — now converted (BUG-62).** `run_full_forecast()` passes `periods_ahead=settings_obj.forecast_period_weeks` to `predict_demand()` for both periods. The setting is weeks-denominated (its own name, and the only horizon control exposed anywhere — form, template, serializer). With the seeded default of 4, the weekly run correctly forecast 4 weeks ahead; the monthly run silently forecast 4 *months* ahead. Present in this doc's own reference code too. Fixed without adding a second `forecast_period_months` setting (deliberately — the weeks setting stays the one horizon knob an admin sees): `periods_ahead = max(1, round(weeks / 4))` for the monthly run only, floored at 1 so a horizon under 2 weeks never produces a zero-length monthly forecast.
10. **`rolling_std_4` stays frozen across the same loop where `rolling_avg_4` is recomputed — a deliberate decision, made explicit.** Point 5's own fix only guarantees `rolling_std_4` isn't *scrambled into the wrong slot*; it never claimed the value itself should track the synthetic future the way `rolling_avg_4` does, and until this pass that was left ambiguous rather than decided. The call made here: leave it frozen at the last real observed value. `rolling_avg_4` is a level signal — it's standard recursive-forecasting practice for a level feature to track the loop's own synthetic future. `rolling_std_4` is a volatility signal; recomputing it from 4 increasingly model-generated (and typically smoother than real demand) values would make it measure "how noisy is my own prediction sequence" rather than real historical volatility, likely decaying toward artificially low numbers the further out the horizon runs. Freezing it anchors the model to real observed volatility instead of a self-reinforcing synthetic drift that has nothing to do with the actual product.
11. **`DemandForecast` rows accumulate across repeated runs by design — and one downstream reader doesn't account for that (reviewed, one gap found).** `run_full_forecast()` uses `.create()`, not `update_or_create()`, and the model carries no unique constraint on `(product, forecast_period, period_start)` — repeated "Run forecast now" clicks genuinely produce duplicate rows for the same future period. This is intentional: REQ 9.9 needs past forecasts kept around to compare against `actual_demand` once `backfill_actual_demand()` fills it in, and `backfill_actual_demand()` computes that figure independently per row from real sales in that row's own date range — duplicate rows each correctly receive the same real actual demand, which is exactly what comparing "the forecast made 2 days out vs. 5 days out" accuracy requires, not corruption. The HTML dashboard (`DemandForecastingView.get()`) already accounts for this: `_latest_batch()` dedupes to the most recently created row per `(product, forecast_period, period_start)` for *display*, without touching what's stored. But that dedup logic lives only there. `ForecastSummaryAPIView` (the read-only API's dashboard-widget-style summary) aggregates across every row unconditionally — `count()`, `avg(confidence_score)`, distinct product count — with no equivalent latest-batch filter, so its numbers skew toward whichever products happened to get re-run most. Two runs 5 minutes apart share a `model_version` at day resolution, so there's no field in that endpoint's own output to distinguish or filter on after the fact. No accuracy metric (MAE/MAPE comparing `forecasted_demand` to `actual_demand`) exists anywhere in this codebase — nothing aggregates *that* comparison, so it can't be corrupted by duplicates in the way originally suspected — but the summary-count skew above is real. Logged as BUG-64, not fixed: out of this pass's approved scope, which covered points 8-9 above only.
12. **The final resample bin can be a partial period — biases the very first forecast step downward (logged, not fixed).** `build_features()` resamples by calendar boundary regardless of whether the most recent week/month has actually finished — if training runs mid-week, that bin holds only the sales seen so far, not a complete period's worth. That artificially-low bin becomes `lag_1` for the first forecast step, biasing it downward (every step after the first uses the model's own prior prediction as `lag_1` instead, so the effect doesn't compound). A real fix — dropping the trailing partial bin, or scaling it to a full-period-equivalent — changes what `build_features()` returns and what `train_model()` trains on, which this pass's own scope explicitly excluded (model, features, and pipeline shape stay exactly as they are). Logged as BUG-63 so it's discoverable rather than silently left for the next person to rediscover.

---

## Data Pipeline

```
SaleTransaction + SaleItem (DB)              InventoryMovement (DB)
        │                                            │
        ▼                                            ▼
  pandas DataFrame                          stockout_flag per period
  (aggregated by product + period)          (stock_after == 0 at any
        │                                    point during the period)
        └───────────────────┬───────────────────────┘
                             ▼
                  Feature Engineering
       (lag_1..lag_4, rolling avg/std, period_num,
              category_id, stockout_flag)
                             │
                             ▼
        Pooled Scikit-learn Model (HistGradientBoostingRegressor,
           trained once across ALL products' history together)
                             │
                             ▼
       Forecasted demand + residual-based confidence score
                             │
                             ▼
        DemandForecast (DB) + Notification if stock insufficient
                             │
                             ▼ (once the period elapses)
              backfill_actual_demand → DemandForecast.actual_demand
```

---

## Feature Engineering

```python
# apps/ai/forecasting/pipeline.py
import pandas as pd
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
import joblib
import os
from django.conf import settings

MODELS_DIR = os.path.join(settings.BASE_DIR, 'ai_models')
os.makedirs(MODELS_DIR, exist_ok=True)

def get_sales_dataframe(product_id=None):
    """Pull sales data from DB into a pandas DataFrame."""
    from apps.sales.models import SaleItem
    from django.db.models import Sum

    qs = SaleItem.objects.values(
        'product_id',
        'transaction__transaction_date',
        'product__category_id',
    ).annotate(qty_sold=Sum('quantity'))

    if product_id:
        qs = qs.filter(product_id=product_id)

    df = pd.DataFrame(list(qs))
    if df.empty:
        return df

    df['transaction_date'] = pd.to_datetime(df['transaction__transaction_date'])
    df = df.rename(columns={
        'transaction__transaction_date': 'date',
        'product__category_id': 'category_id'
    })
    return df


def get_stockout_flags(product_id, period='W'):
    """
    Returns a small DataFrame of period_start -> stockout_flag (1 if the
    InventoryMovement ledger shows stock_after == 0 at any point during
    that period, else 0). Joined into build_features() so a demand-less
    period caused by being out of stock isn't fed to the model as a true
    zero-demand signal — left unmarked, a stockout gets learned as "this
    product doesn't sell," which suppresses future reorder recommendations
    and can compound the stockout instead of correcting it.
    """
    from apps.inventory.models import InventoryMovement

    zero_stock_events = list(
        InventoryMovement.objects.filter(product_id=product_id, stock_after=0)
        .values_list('created_at', flat=True)
    )

    if not zero_stock_events:
        return pd.DataFrame(columns=['period_start', 'stockout_flag'])

    dates = pd.to_datetime(zero_stock_events)
    flags = pd.Series(1, index=dates).resample(period).max().fillna(0)
    return flags.reset_index().rename(columns={'index': 'period_start', 0: 'stockout_flag'})


def build_features(df, period='W'):
    """
    Aggregate sales by product and period (W=weekly, M=monthly).
    Returns a DataFrame with lag features for ML training.
    """
    df = df.copy()
    df.set_index('date', inplace=True)

    result_frames = []
    for product_id, group in df.groupby('product_id'):
        category_id = group['category_id'].iloc[0]
        resampled = group['qty_sold'].resample(period).sum().reset_index()
        resampled['product_id'] = product_id
        resampled['category_id'] = category_id
        resampled = resampled.rename(columns={'date': 'period_start', 'qty_sold': 'demand'})

        # Lag features
        for lag in [1, 2, 3, 4]:
            resampled[f'lag_{lag}'] = resampled['demand'].shift(lag)

        # Rolling average
        resampled['rolling_avg_4'] = resampled['demand'].rolling(4).mean()
        resampled['rolling_std_4'] = resampled['demand'].rolling(4).std().fillna(0)

        # Period features
        resampled['period_num'] = range(len(resampled))

        # Stockout awareness — see get_stockout_flags() docstring
        stockout_df = get_stockout_flags(product_id, period)
        if not stockout_df.empty:
            resampled = resampled.merge(stockout_df, on='period_start', how='left')
        else:
            resampled['stockout_flag'] = 0
        resampled['stockout_flag'] = resampled['stockout_flag'].fillna(0)

        resampled.dropna(inplace=True)
        result_frames.append(resampled)

    if not result_frames:
        return pd.DataFrame()
    return pd.concat(result_frames, ignore_index=True)


FEATURE_COLUMNS = [
    'lag_1', 'lag_2', 'lag_3', 'lag_4',
    'rolling_avg_4', 'rolling_std_4', 'period_num',
    'category_id', 'stockout_flag',
]
TARGET_COLUMN = 'demand'
CATEGORICAL_FEATURE_INDICES = [FEATURE_COLUMNS.index('category_id')]


def train_model(period='W'):
    """
    Train one HistGradientBoostingRegressor pooled across ALL products'
    sales data — not one model per product. Pooling lets a product with a
    short history still borrow signal from other products (especially
    within the same category) rather than needing its own, less stable,
    separately-trained model.
    """
    df_raw = get_sales_dataframe()
    if df_raw.empty:
        raise ValueError("No sales data available for training.")

    df_features = build_features(df_raw, period=period)
    if df_features.empty or len(df_features) < 10:
        raise ValueError("Insufficient data for model training.")

    # Chronological split, not random: sorting by period_start and holding
    # out the most recent rows keeps the backtest honest — a random split
    # would let the model train on periods after the ones it's tested on,
    # which never happens at real prediction time.
    df_sorted = df_features.sort_values('period_start').reset_index(drop=True)
    split_idx = int(len(df_sorted) * 0.8)
    split_idx = min(max(split_idx, 1), len(df_sorted) - 1)
    train_df = df_sorted.iloc[:split_idx]
    test_df = df_sorted.iloc[split_idx:]

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df[TARGET_COLUMN]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df[TARGET_COLUMN]

    model = HistGradientBoostingRegressor(
        random_state=42,
        categorical_features=CATEGORICAL_FEATURE_INDICES,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    residual_std = float(np.std(y_test.values - y_pred)) if len(y_test) > 1 else float(mae)

    # Bundle the model with its own backtest error so predict_demand() can
    # derive a real confidence interval instead of an ad hoc heuristic.
    model_path = os.path.join(MODELS_DIR, f'forecast_model_{period}.joblib')
    joblib.dump({'model': model, 'residual_std': residual_std, 'mae': mae}, model_path)
    print(f"Model trained. MAE: {mae:.2f}. Saved to {model_path}")
    return model, mae


def load_model(period='W'):
    """Returns the (model, residual_std) pair saved by train_model()."""
    model_path = os.path.join(MODELS_DIR, f'forecast_model_{period}.joblib')
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"No trained model found at {model_path}. Run training first.")
    bundle = joblib.load(model_path)
    return bundle['model'], bundle['residual_std']


def predict_demand(product_id, period='W', periods_ahead=4):
    """
    Generate demand forecast for a specific product.
    Returns list of {period_start, period_end, forecasted_demand, confidence_score}
    """
    df_raw = get_sales_dataframe(product_id=product_id)
    if df_raw.empty:
        return []

    df_features = build_features(df_raw, period=period)
    if df_features.empty:
        return []

    try:
        model, residual_std = load_model(period)
    except FileNotFoundError:
        train_model(period)
        model, residual_std = load_model(period)

    last_row = df_features.tail(1)[FEATURE_COLUMNS].values[0]
    predictions = []

    last_period = df_features['period_start'].max()
    freq = 'W' if period == 'W' else 'MS'

    lag_indices = [FEATURE_COLUMNS.index(f'lag_{i}') for i in (1, 2, 3, 4)]
    rolling_avg_idx = FEATURE_COLUMNS.index('rolling_avg_4')

    for i in range(1, periods_ahead + 1):
        features = last_row.copy()
        pred = max(0, model.predict([features])[0])

        # Shift only the lag_1..lag_4 block for the next step-ahead
        # prediction — rotating the whole feature vector (as the original
        # np.roll(last_row, 1) did) also scrambles rolling_std_4/
        # period_num/category_id/stockout_flag into the wrong slots.
        for j in range(len(lag_indices) - 1, 0, -1):
            last_row[lag_indices[j]] = last_row[lag_indices[j - 1]]
        last_row[lag_indices[0]] = pred
        last_row[rolling_avg_idx] = np.mean([last_row[idx] for idx in lag_indices])

        period_start = last_period + pd.tseries.frequencies.to_offset(freq) * i
        period_end = period_start + pd.tseries.frequencies.to_offset(freq) - pd.Timedelta(days=1)

        # Confidence from the model's own backtest residual spread, scaled
        # against the size of this prediction (a 5-unit residual means
        # something different for a slow product than a high-volume one).
        relative_error = residual_std / (pred + 1)
        confidence = min(0.95, max(0.50, 1 - relative_error))

        predictions.append({
            'period_start': period_start.date(),
            'period_end': period_end.date(),
            'forecasted_demand': round(pred, 2),
            'confidence_score': round(confidence, 2),
        })

    return predictions
```

---

## Celery Tasks

```python
# apps/ai/forecasting/tasks.py
from celery import shared_task
from django.utils import timezone

@shared_task(name='ai.retrain_forecast_model')
def retrain_forecast_model():
    """Retrain the ML model with latest sales data. Runs on schedule."""
    from apps.ai.forecasting.pipeline import train_model
    from apps.audit.services import log_action
    try:
        for period in ['W', 'M']:
            model, mae = train_model(period=period)
        log_action(None, 'AI_MODEL_RETRAINED', 'ai_forecasting', status='success',
                   details={'mae_weekly': mae, 'timestamp': str(timezone.now())})
    except Exception as e:
        log_action(None, 'AI_MODEL_RETRAIN_FAILED', 'ai_forecasting', status='failure',
                   details={'error': str(e)})
        raise


@shared_task(name='ai.run_demand_forecasts')
def run_demand_forecasts():
    """Generate forecasts for all active products. Runs on schedule."""
    from apps.products.models import Product
    from apps.ai.forecasting.pipeline import predict_demand
    from apps.ai.forecasting.models import DemandForecast, ForecastPeriod
    from apps.inventory.models import InventoryRecord
    from apps.notifications.services import notify_supervisors
    from apps.settings_manager.models import SystemSettings

    settings_obj = SystemSettings.get_settings()
    products = Product.objects.filter(is_active=True)
    model_version = f"hgb_{timezone.now().strftime('%Y%m%d')}"

    for product in products:
        for period, period_choice in [('W', ForecastPeriod.WEEKLY), ('M', ForecastPeriod.MONTHLY)]:
            predictions = predict_demand(product.id, period=period, periods_ahead=settings_obj.forecast_period_weeks)

            for pred in predictions:
                # Calculate recommended reorder qty
                try:
                    inv = InventoryRecord.objects.get(product=product)
                    current_stock = inv.current_stock
                except InventoryRecord.DoesNotExist:
                    current_stock = 0

                recommended_qty = max(0, int(pred['forecasted_demand']) - current_stock)

                DemandForecast.objects.create(
                    product=product,
                    forecast_period=period_choice,
                    period_start=pred['period_start'],
                    period_end=pred['period_end'],
                    forecasted_demand=pred['forecasted_demand'],
                    recommended_reorder_qty=recommended_qty,
                    confidence_score=pred['confidence_score'],
                    model_version=model_version,
                )

                # Notify if forecasted demand exceeds current stock
                if pred['forecasted_demand'] > current_stock and period_choice == ForecastPeriod.WEEKLY:
                    notify_supervisors(
                        'ai_replenish',
                        f'AI: Replenish {product.name}',
                        f'Forecasted demand ({pred["forecasted_demand"]} units) exceeds current stock ({current_stock} units). Recommended order: {recommended_qty} units.',
                        link=f'/ai/forecasts/{product.id}/'
                    )

    log_action(None, 'AI_FORECASTS_GENERATED', 'ai_forecasting', status='success',
               details={'product_count': products.count(), 'timestamp': str(timezone.now())})


@shared_task(name='ai.backfill_actual_demand')
def backfill_actual_demand():
    """
    For every DemandForecast whose period has fully elapsed but whose
    actual_demand is still unset, sum real SaleItem quantities for that
    product over the same period and store it. This is what makes REQ 9.9
    ("compare forecasted demand with actual sales") real rather than just
    a schema field nothing ever writes to.
    """
    from apps.ai.forecasting.models import DemandForecast
    from apps.sales.models import SaleItem
    from apps.audit.services import log_action
    from django.db.models import Sum

    today = timezone.now().date()
    pending = DemandForecast.objects.filter(
        actual_demand__isnull=True,
        period_end__lt=today,
    )

    updated = 0
    for forecast in pending:
        actual = SaleItem.objects.filter(
            product=forecast.product,
            transaction__transaction_date__gte=forecast.period_start,
            transaction__transaction_date__lte=forecast.period_end,
            transaction__status='completed',
        ).aggregate(total=Sum('quantity'))['total'] or 0

        forecast.actual_demand = actual
        forecast.save(update_fields=['actual_demand', 'updated_at'])
        updated += 1

    log_action(None, 'AI_ACTUAL_DEMAND_BACKFILLED', 'ai_forecasting', status='success',
               details={'forecasts_updated': updated, 'timestamp': str(timezone.now())})
```

---

## Celery Beat Schedule — REMOVED (docs/bugsfound.md)

This section used to show a `CELERY_BEAT_SCHEDULE` dict wiring 5 periodic
tasks (weekly retrain, weekly forecast run, daily backfill, daily
classification, 6-hourly low-stock alerts). No Celery, no Celery Beat,
and no scheduler of any kind exists anywhere in this project — none of
these five jobs run periodically. Real triggers instead: forecasting and
classification both run on demand via their own "Run now" buttons, or
synchronously as a side effect of a real event (a sale approval
reclassifies the products it touched); low-stock/out-of-stock alerts
fire synchronously inside `InventoryService.decrease_stock()`. REQ 9.7
and REQ 17.4 (periodic retraining specifically) are PHANTOM — disclosed,
not built.

---

## API Views

```python
# apps/ai/forecasting/views.py
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.rbac.permissions import IsSupervisorOrAbove

class ForecastListAPIView(ListAPIView):
    permission_classes = [IsSupervisorOrAbove]
    serializer_class = DemandForecastSerializer

    def get_queryset(self):
        return DemandForecast.objects.select_related('product').order_by('-period_start')[:200]

class ProductForecastAPIView(ListAPIView):
    permission_classes = [IsSupervisorOrAbove]
    serializer_class = DemandForecastSerializer

    def get_queryset(self):
        return DemandForecast.objects.filter(
            product_id=self.kwargs['product_id']
        ).order_by('-period_start')

class RunForecastAPIView(APIView):
    """Manually trigger forecast run (admin only)."""
    permission_classes = [IsSupervisorOrAbove]

    def post(self, request):
        from apps.ai.forecasting.tasks import run_demand_forecasts
        run_demand_forecasts.delay()
        return Response({'message': 'Forecast task queued.'})
```

---

## Minimum Data Requirements

| Condition | Behavior |
|---|---|
| Product has < 4 weeks of sales data | Skip forecasting — insufficient data. Enforced implicitly by `build_features()`'s `dropna()`: `lag_4` needs 4 prior periods before any row survives, so a product without at least ~5 periods of history simply never produces a feature row. |
| Product has ≥ 4 weeks of data | Use the pooled `HistGradientBoostingRegressor` — trained once across every product's history together, not per-product. See Design Notes above for why the original 4–12-week `LinearRegression` tier was removed. |
| No model file on disk | Auto-train before predicting |

---

## Audit Actions

| Action Constant | Triggered When |
|---|---|
| `AI_MODEL_RETRAINED` | Forecasting model retrained successfully |
| `AI_MODEL_RETRAIN_FAILED` | Training failed (logged with error details) |
| `AI_FORECASTS_GENERATED` | Full forecast run completed |
| `AI_ACTUAL_DEMAND_BACKFILLED` | Actual demand backfilled for elapsed forecast periods |
| `AI_FORECAST_REPORT_EXPORTED` | Forecast report exported |
