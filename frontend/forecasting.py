import os

import joblib
import numpy as np
import pandas as pd
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from frontend.models import (
    DemandForecast,
    ForecastPeriod,
    InventoryMovement,
    InventoryRecord,
    Product,
    SaleItem,
    SaleStatus,
    SystemSettings,
)

MODELS_DIR = os.path.join(settings.BASE_DIR, 'ai_models')
os.makedirs(MODELS_DIR, exist_ok=True)

FEATURE_COLUMNS = [
    'lag_1', 'lag_2', 'lag_3', 'lag_4',
    'rolling_avg_4', 'rolling_std_4', 'period_num',
    'category_id', 'stockout_flag',
]
TARGET_COLUMN = 'demand'
CATEGORICAL_FEATURE_INDICES = [FEATURE_COLUMNS.index('category_id')]

_PERIOD_CHOICE = {'W': ForecastPeriod.WEEKLY, 'M': ForecastPeriod.MONTHLY}

# Workaround: pandas 3.0 dropped bare 'M'; resample uses 'ME' internally.
_RESAMPLE_ALIAS = {'W': 'W', 'M': 'ME'}


def get_sales_dataframe(product_id=None):
    """Pulls COMPLETED sales into a DataFrame for feature-building."""
    # Rule: COMPLETED only -- draft/pending/rejected sales aren't real demand.
    qs = SaleItem.objects.filter(transaction__status=SaleStatus.COMPLETED).values(
        'product_id',
        'transaction__transaction_date',
        'product__category_id',
    ).annotate(qty_sold=Sum('quantity'))

    if product_id:
        qs = qs.filter(product_id=product_id)

    df = pd.DataFrame(list(qs))
    if df.empty:
        return df

    # Workaround: rename before converting dtype -- avoids a stale object column.
    df = df.rename(columns={
        'transaction__transaction_date': 'date',
        'product__category_id': 'category_id'
    })
    df['date'] = pd.to_datetime(df['date'])
    return df


def get_stockout_flags(product_id, period='W'):
    """Returns period_start -> stockout_flag (1 if stock hit zero that period)."""
    zero_stock_events = list(
        InventoryMovement.objects.filter(product_id=product_id, stock_after=0)
        .values_list('created_at', flat=True)
    )

    if not zero_stock_events:
        return pd.DataFrame(columns=['period_start', 'stockout_flag'])

    # Assumption: converted to Asia/Dhaka dates -- tz-naive merge with sales.
    local_dates = [timezone.localtime(dt).date() for dt in zero_stock_events]
    dates = pd.to_datetime(local_dates)
    flags = pd.Series(1, index=dates).resample(_RESAMPLE_ALIAS[period]).max().fillna(0)
    # Workaround: an unnamed resample resets to columns ['index', 0].
    return flags.reset_index().rename(columns={'index': 'period_start', 0: 'stockout_flag'})


def build_features(df, period='W'):
    """Returns a DataFrame with lag features for ML training."""
    df = df.copy()
    df.set_index('date', inplace=True)

    result_frames = []
    for product_id, group in df.groupby('product_id'):
        category_id = group['category_id'].iloc[0]
        resampled = group['qty_sold'].resample(_RESAMPLE_ALIAS[period]).sum().reset_index()
        resampled['product_id'] = product_id
        resampled['category_id'] = category_id
        resampled = resampled.rename(columns={'date': 'period_start', 'qty_sold': 'demand'})

        for lag in [1, 2, 3, 4]:
            resampled[f'lag_{lag}'] = resampled['demand'].shift(lag)

        # Assumption: rolling window matches lag depth (4 periods), inherited.
        resampled['rolling_avg_4'] = resampled['demand'].rolling(4).mean()
        resampled['rolling_std_4'] = resampled['demand'].rolling(4).std().fillna(0)
        resampled['period_num'] = range(len(resampled))

        # Rule: unmarked, a stockout period reads as zero demand, not censored.
        stockout_df = get_stockout_flags(product_id, period)
        if not stockout_df.empty:
            resampled = resampled.merge(stockout_df, on='period_start', how='left')
        else:
            resampled['stockout_flag'] = 0
        resampled['stockout_flag'] = resampled['stockout_flag'].fillna(0)

        # Rule: drops rows short of 4 lag periods -- the model-selection skip tier.
        resampled.dropna(inplace=True)
        result_frames.append(resampled)

    if not result_frames:
        return pd.DataFrame()
    return pd.concat(result_frames, ignore_index=True)


def train_model(period='W'):
    """Trains one pooled HistGradientBoostingRegressor across all products."""
    df_raw = get_sales_dataframe()
    if df_raw.empty:
        raise ValueError("No sales data available for training.")

    df_features = build_features(df_raw, period=period)
    # Edge: <10 pooled rows raises rather than train on too little data.
    if df_features.empty or len(df_features) < 10:
        raise ValueError("Insufficient data for model training.")

    # Rule: chronological split -- prevents leakage from future data.
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error

    df_sorted = df_features.sort_values('period_start').reset_index(drop=True)
    # Assumption: 80/20 split, matching the original reference pipeline's ratio.
    split_idx = int(len(df_sorted) * 0.8)
    split_idx = min(max(split_idx, 1), len(df_sorted) - 1)
    train_df = df_sorted.iloc[:split_idx]
    test_df = df_sorted.iloc[split_idx:]

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df[TARGET_COLUMN]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df[TARGET_COLUMN]

    # Assumption: fixed seed for reproducible training runs.
    # Rule: category_id is native-categorical -- short-history SKUs borrow signal.
    model = HistGradientBoostingRegressor(
        random_state=42,
        categorical_features=CATEGORICAL_FEATURE_INDICES,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    residual_std = float(np.std(y_test.values - y_pred)) if len(y_test) > 1 else float(mae)

    model_path = os.path.join(MODELS_DIR, f'forecast_model_{period}.joblib')
    joblib.dump({'model': model, 'residual_std': residual_std, 'mae': mae}, model_path)
    return model, mae


def load_model(period='W'):
    """Returns the (model, residual_std) pair saved by train_model()."""
    model_path = os.path.join(MODELS_DIR, f'forecast_model_{period}.joblib')
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"No trained model found at {model_path}. Run training first.")
    bundle = joblib.load(model_path)
    return bundle['model'], bundle['residual_std']


def predict_demand(product_id, period='W', periods_ahead=4):
    """Forecasts demand; auto-trains if no saved model file is found."""
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
    period_num_idx = FEATURE_COLUMNS.index('period_num')

    for i in range(1, periods_ahead + 1):
        # Rule: period_num advances each step -- each is a distinct future period.
        last_row[period_num_idx] += 1
        features = last_row.copy()
        # Workaround: predict via a named DataFrame -- avoids an sklearn warning.
        pred = max(0, model.predict(pd.DataFrame([features], columns=FEATURE_COLUMNS))[0])

        # Rule: shifts only the lag block -- a full-vector rotate scrambles slots.
        for j in range(len(lag_indices) - 1, 0, -1):
            last_row[lag_indices[j]] = last_row[lag_indices[j - 1]]
        last_row[lag_indices[0]] = pred
        last_row[rolling_avg_idx] = np.mean([last_row[idx] for idx in lag_indices])
        # Rule: rolling_std_4 stays frozen -- avoids drift from synthetic values.

        period_start = last_period + pd.tseries.frequencies.to_offset(freq) * i
        period_end = period_start + pd.tseries.frequencies.to_offset(freq) - pd.Timedelta(days=1)

        relative_error = residual_std / (pred + 1)
        # Assumption: confidence clamped to 50-95%, per the original reference formula.
        confidence = min(0.95, max(0.50, 1 - relative_error))

        predictions.append({
            'period_start': period_start.date(),
            'period_end': period_end.date(),
            'forecasted_demand': round(pred, 2),
            'confidence_score': round(confidence, 2),
        })

    return predictions


def backfill_actual_demand():
    """Fills actual_demand for every elapsed forecast; returns the count updated."""
    # Assumption: Asia/Dhaka "today" -- matches every calendar-day comparison.
    today = timezone.localdate()
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
            transaction__status=SaleStatus.COMPLETED,
        ).aggregate(total=Sum('quantity'))['total'] or 0

        forecast.actual_demand = actual
        forecast.save(update_fields=['actual_demand', 'updated_at'])
        updated += 1

    return updated


def run_full_forecast():
    """Retrains both period models, then forecasts every active product."""
    # Assumption: runs synchronously in-request; the manual retrain POST blocks.
    # Rule: each period trains independently -- one failing doesn't block the other.
    mae_by_period = {}
    trained_periods = []
    training_errors = {}
    for period in ('W', 'M'):
        try:
            _, mae = train_model(period)
            mae_by_period[period] = mae
            trained_periods.append(period)
        except ValueError as e:
            training_errors[period] = str(e)

    if not trained_periods:
        raise ValueError(f"No forecast period could be trained: {training_errors}")

    settings_obj = SystemSettings.get_settings()
    products = Product.objects.filter(is_active=True)
    model_version = f"hgb_{timezone.localdate().strftime('%Y%m%d')}"

    # Rule: forecast_period_weeks is weeks; converted for the monthly run.
    # Edge: rounded and floored at 1 -- a short horizon never yields zero months.
    periods_ahead_by_period = {
        'W': settings_obj.forecast_period_weeks,
        'M': max(1, round(settings_obj.forecast_period_weeks / 4)),
    }

    forecasts_created = 0
    replenish_alerts = []

    for product in products:
        for period, period_choice in (('W', ForecastPeriod.WEEKLY), ('M', ForecastPeriod.MONTHLY)):
            if period not in trained_periods:
                continue
            predictions = predict_demand(product.id, period=period, periods_ahead=periods_ahead_by_period[period])

            for pred in predictions:
                try:
                    current_stock = InventoryRecord.objects.get(product=product).current_stock
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
                forecasts_created += 1

                if needs_replenishment(period_choice, pred['forecasted_demand'], current_stock):
                    replenish_alerts.append({
                        'product': product,
                        'forecasted_demand': pred['forecasted_demand'],
                        'current_stock': current_stock,
                        'recommended_qty': recommended_qty,
                    })

    return {
        'products_considered': products.count(),
        'forecasts_created': forecasts_created,
        'mae': mae_by_period,
        'periods_trained': trained_periods,
        'training_errors': training_errors,
        'replenish_alerts': replenish_alerts,
    }


def needs_replenishment(forecast_period, forecasted_demand, current_stock):
    """Weekly-only: forecasted demand exceeding current stock means reorder now."""
    return forecast_period == ForecastPeriod.WEEKLY and float(forecasted_demand) > float(current_stock)


def latest_forecast_batch():
    """Dedupes to the most-recently-created row per (product, period, start)."""
    # Assumption: every row is kept in the DB; only this display copy dedupes.
    all_forecasts = list(
        DemandForecast.objects.select_related('product', 'product__category')
        .order_by('-created_at')
    )
    latest = {}
    for f in all_forecasts:
        key = (f.product_id, f.forecast_period, f.period_start)
        if key not in latest:
            latest[key] = f
    return list(latest.values()), (all_forecasts[0] if all_forecasts else None)


def current_forecast_window(forecast_period, horizon=4):
    """Forecasts from today onward, capped to the earliest `horizon` periods."""
    # Edge: empty if nothing is forecast for today or later -- never stale data.
    today = timezone.localdate()
    all_forecasts, _ = latest_forecast_batch()
    candidates = [
        f for f in all_forecasts
        if f.forecast_period == forecast_period and f.period_start >= today
    ]
    upcoming_starts = sorted({f.period_start for f in candidates})
    if horizon is not None:
        upcoming_starts = upcoming_starts[:horizon]
    allowed = set(upcoming_starts)
    return [f for f in candidates if f.period_start in allowed]
