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

## Data Pipeline

```
SaleTransaction + SaleItem (DB)
        │
        ▼
  pandas DataFrame (aggregated by product + period)
        │
        ▼
  Feature Engineering
  (rolling avg, lag features, stock level, category encoding)
        │
        ▼
  Scikit-learn Model (RandomForestRegressor or LinearRegression)
        │
        ▼
  Forecasted demand + confidence interval
        │
        ▼
  DemandForecast (DB) + Notification if stock insufficient
```

---

## Feature Engineering

```python
# apps/ai/forecasting/pipeline.py
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import LabelEncoder
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


def build_features(df, period='W'):
    """
    Aggregate sales by product and period (W=weekly, M=monthly).
    Returns a DataFrame with lag features for ML training.
    """
    df = df.copy()
    df.set_index('date', inplace=True)

    result_frames = []
    for product_id, group in df.groupby('product_id'):
        resampled = group['qty_sold'].resample(period).sum().reset_index()
        resampled['product_id'] = product_id
        resampled = resampled.rename(columns={'date': 'period_start', 'qty_sold': 'demand'})

        # Lag features
        for lag in [1, 2, 3, 4]:
            resampled[f'lag_{lag}'] = resampled['demand'].shift(lag)

        # Rolling average
        resampled['rolling_avg_4'] = resampled['demand'].rolling(4).mean()
        resampled['rolling_std_4'] = resampled['demand'].rolling(4).std().fillna(0)

        # Period features
        resampled['period_num'] = range(len(resampled))
        resampled.dropna(inplace=True)
        result_frames.append(resampled)

    if not result_frames:
        return pd.DataFrame()
    return pd.concat(result_frames, ignore_index=True)


FEATURE_COLUMNS = ['lag_1', 'lag_2', 'lag_3', 'lag_4', 'rolling_avg_4', 'rolling_std_4', 'period_num']
TARGET_COLUMN = 'demand'


def train_model(period='W'):
    """Train a RandomForestRegressor on all product sales data."""
    df_raw = get_sales_dataframe()
    if df_raw.empty:
        raise ValueError("No sales data available for training.")

    df_features = build_features(df_raw, period=period)
    if df_features.empty or len(df_features) < 10:
        raise ValueError("Insufficient data for model training.")

    X = df_features[FEATURE_COLUMNS]
    y = df_features[TARGET_COLUMN]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)

    # Save model
    model_path = os.path.join(MODELS_DIR, f'forecast_model_{period}.joblib')
    joblib.dump(model, model_path)
    print(f"Model trained. MAE: {mae:.2f}. Saved to {model_path}")
    return model, mae


def load_model(period='W'):
    model_path = os.path.join(MODELS_DIR, f'forecast_model_{period}.joblib')
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"No trained model found at {model_path}. Run training first.")
    return joblib.load(model_path)


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
        model = load_model(period)
    except FileNotFoundError:
        model, _ = train_model(period)

    # Use last known features to predict ahead
    last_row = df_features.tail(1)[FEATURE_COLUMNS].values[0]
    predictions = []

    import pandas as pd
    last_period = df_features['period_start'].max()
    freq = 'W' if period == 'W' else 'MS'

    for i in range(1, periods_ahead + 1):
        features = last_row.copy()
        pred = max(0, model.predict([features])[0])

        # Shift lag features for next prediction
        last_row = np.roll(last_row, 1)
        last_row[0] = pred  # lag_1 becomes this prediction
        last_row[4] = (last_row[1:5].mean())  # rolling avg (approx)

        period_start = last_period + pd.tseries.frequencies.to_offset(freq) * i
        period_end = period_start + pd.tseries.frequencies.to_offset(freq) - pd.Timedelta(days=1)

        # Confidence: rough heuristic based on variance
        confidence = min(0.95, max(0.50, 1 - (last_row[5] / (pred + 1))))

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
    model_version = f"rf_{timezone.now().strftime('%Y%m%d')}"

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
| Product has < 4 weeks of sales data | Skip forecasting — insufficient data |
| Product has 4–12 weeks of data | Use linear regression (simpler model) |
| Product has > 12 weeks of data | Use RandomForestRegressor |
| No model file on disk | Auto-train before predicting |

---

## Audit Actions

| Action Constant | Triggered When |
|---|---|
| `AI_MODEL_RETRAINED` | Forecasting model retrained successfully |
| `AI_MODEL_RETRAIN_FAILED` | Training failed (logged with error details) |
| `AI_FORECASTS_GENERATED` | Full forecast run completed |
| `AI_FORECAST_REPORT_EXPORTED` | Forecast report exported |
