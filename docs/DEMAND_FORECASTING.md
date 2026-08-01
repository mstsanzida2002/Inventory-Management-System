# 🤖 AI — Demand Forecasting
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when building the forecasting pipeline, training
> the Scikit-learn model, writing Celery tasks, or exposing forecast results
> through API/dashboard endpoints.

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

## Celery Beat Schedule

Add to `config/settings/base.py`:

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'retrain-forecast-model': {
        'task': 'ai.retrain_forecast_model',
        'schedule': crontab(hour=2, minute=0, day_of_week=1),   # Every Monday 2am
    },
    'run-demand-forecasts': {
        'task': 'ai.run_demand_forecasts',
        'schedule': crontab(hour=3, minute=0, day_of_week=1),   # Every Monday 3am
    },
    'backfill-actual-demand': {
        'task': 'ai.backfill_actual_demand',
        'schedule': crontab(hour=5, minute=0),                  # Every day 5am
    },
    'run-stock-classification': {
        'task': 'ai.run_stock_classification',
        'schedule': crontab(hour=4, minute=0),                   # Every day 4am
    },
    'send-low-stock-alerts': {
        'task': 'inventory.send_low_stock_alerts',
        'schedule': crontab(minute=0, hour='*/6'),              # Every 6 hours
    },
}
```

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
