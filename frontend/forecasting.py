"""
docs/DEMAND_FORECASTING.md, translated into the single `frontend` app — no
`apps/ai/forecasting/` app created (see docs/project_memory.md §13).
Matches the existing small-dedicated-module pattern (frontend/audit.py,
frontend/notifications.py, frontend/reports.py, frontend/classification.py).

Implements the doc's CURRENT pipeline — the one after its own "Design
Notes — Revisions From the Original Spec" (7 changes: HistGradientBoosting
over RandomForest, chronological split, two-tier model selection,
category_id/stockout_flag features, the corrected lag-shift in
predict_demand(), backtest-residual confidence, backfill_actual_demand()).
Not the original 3-tier pipeline described anywhere else.

No Celery (not installed, docs/project_memory.md §1) — everything here
runs synchronously, either from the manual "Run forecast now" POST
(DemandForecastingView.post()) or directly (predict_demand()'s own
auto-train-if-missing fallback, exercised for real whenever ai_models/ is
empty — an ephemeral production disk after a redeploy, see §13).

One further translation beyond the doc's own 7, disclosed rather than
copied silently: get_sales_dataframe()'s reference code has no
`status='completed'` filter at all — a documented bug found while
building Phase 9.5's seed data (that phase deliberately seeded pending/
rejected/cancelled sales specifically so this would be immediately
testable here). Fixed: filters on SaleStatus.COMPLETED, matching
docs/DEAD_STOCK_DETECTION.md's equivalent queries, which already filter
correctly. Without this, every forecast would be inflated by demand from
sales that never actually happened.
"""
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

# A third pandas-3.0 break found empirically (not documented anywhere —
# pandas deprecated the bare 'M' resample alias in 2.2 and removed it in
# 3.0.5, the version installed here: "'M' is no longer supported for
# offsets. Please use 'ME' instead."). The public API of every function
# below still speaks 'W'/'M' — that's ForecastPeriod's own vocabulary and
# the doc's — only the internal call into pandas' .resample() needs the
# translation. predict_demand()'s freq='MS' (Month Start, a different,
# still-valid alias used for stepping period_start forward) is unaffected.
_RESAMPLE_ALIAS = {'W': 'W', 'M': 'ME'}


def get_sales_dataframe(product_id=None):
    """Pull sales data from DB into a pandas DataFrame. COMPLETED sales
    only — see this module's own docstring for the Phase 9.5 finding this
    fixes: pending/rejected/cancelled sales have real SaleItem rows too
    (SaleService.create_sale() writes them at draft time, before any
    approval), so without this filter every forecast would train on
    demand that never actually happened."""
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

    # Real bug in the documented reference code, found empirically (not a
    # pandas-version quirk — see this module's docstring): it assigns the
    # *converted* datetime into a new 'transaction_date' column, then
    # renames the *original, still-object-dtype* 'transaction__
    # transaction_date' column to 'date' — the column build_features()
    # actually indexes on. The conversion was silently discarded; 'date'
    # stayed object-dtype the whole time. Harmless-looking until
    # build_features()'s df.set_index('date') + .resample() call, which
    # requires a genuine DatetimeIndex and raises TypeError otherwise —
    # pandas 3.0.5 (installed here) raises loudly; whether an older
    # pandas tolerated it silently was never checked, since it doesn't
    # matter — this is fixed regardless of version. Rename first, then
    # convert the correctly-named column in place; no second column.
    df = df.rename(columns={
        'transaction__transaction_date': 'date',
        'product__category_id': 'category_id'
    })
    df['date'] = pd.to_datetime(df['date'])
    return df


def get_stockout_flags(product_id, period='W'):
    """
    Returns a small DataFrame of period_start -> stockout_flag (1 if the
    InventoryMovement ledger shows stock_after == 0 at any point during
    that period, else 0). Joined into build_features() so a demand-less
    period caused by being out of stock isn't fed to the model as a true
    zero-demand signal.

    Queries InventoryMovement directly, not frontend.reports.
    filter_movements() — that helper takes an HTTP request and is scoped
    to page/export filtering, not this pipeline's needs.

    The reset_index().rename({'index': ..., 0: ...}) column names were
    verified empirically against the installed pandas (3.0.5) before
    relying on them here — an unnamed Series with an unnamed
    DatetimeIndex resets to columns ['index', 0], exactly as this
    function assumes. Not something to take on faith with a pandas
    version this new (a 2.x-to-3.0 major bump can rename defaults).

    A second, real bug found the same way: InventoryMovement.created_at
    is a DateTimeField (timezone-aware, USE_TZ=True) while
    SaleTransaction.transaction_date is a plain DateField — feeding the
    former straight into pd.to_datetime() produces a tz-*aware*
    (datetime64[us, UTC]) index, while build_features()'s sales-side
    period_start is tz-*naive*. merge()-ing the two raises a ValueError
    on pandas 3.0 (ValueError: You are trying to merge on datetime64[s]
    and datetime64[us, UTC] columns), not a silent misjoin — still fixed
    here rather than left to surface as a crash on the first product with
    a real stockout. Converted to Asia/Dhaka calendar dates first (same
    timezone.localtime()-before-comparing discipline as BUG-47 and
    everywhere else in this project that compares against a day, not an
    instant) — tz-naive on both sides, and the right calendar day besides."""
    zero_stock_events = list(
        InventoryMovement.objects.filter(product_id=product_id, stock_after=0)
        .values_list('created_at', flat=True)
    )

    if not zero_stock_events:
        return pd.DataFrame(columns=['period_start', 'stockout_flag'])

    local_dates = [timezone.localtime(dt).date() for dt in zero_stock_events]
    dates = pd.to_datetime(local_dates)
    flags = pd.Series(1, index=dates).resample(_RESAMPLE_ALIAS[period]).max().fillna(0)
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
        resampled = group['qty_sold'].resample(_RESAMPLE_ALIAS[period]).sum().reset_index()
        resampled['product_id'] = product_id
        resampled['category_id'] = category_id
        resampled = resampled.rename(columns={'date': 'period_start', 'qty_sold': 'demand'})

        for lag in [1, 2, 3, 4]:
            resampled[f'lag_{lag}'] = resampled['demand'].shift(lag)

        resampled['rolling_avg_4'] = resampled['demand'].rolling(4).mean()
        resampled['rolling_std_4'] = resampled['demand'].rolling(4).std().fillna(0)
        resampled['period_num'] = range(len(resampled))

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


def train_model(period='W'):
    """
    Train one HistGradientBoostingRegressor pooled across ALL products'
    sales data — not one model per product (Design Notes revision #3: the
    original 4-12-week LinearRegression tier was dropped in favor of
    letting every product, short-history included, borrow signal from the
    pooled model via category_id).
    """
    df_raw = get_sales_dataframe()
    if df_raw.empty:
        raise ValueError("No sales data available for training.")

    df_features = build_features(df_raw, period=period)
    if df_features.empty or len(df_features) < 10:
        raise ValueError("Insufficient data for model training.")

    # Chronological split, not random (Design Notes revision #2): a
    # random split would let the model train on periods after the ones
    # it's evaluated on, which never happens at real prediction time and
    # makes the reported MAE optimistic.
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error

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
    # derive a real confidence interval (Design Notes revision #6) instead
    # of the original last-row heuristic.
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
    """
    Generate demand forecast for a specific product.
    Returns list of {period_start, period_end, forecasted_demand, confidence_score}

    Auto-trains if no model file is found — the only thing standing
    between an empty ai_models/ directory (a fresh deploy on an ephemeral
    disk, or simply the first forecast ever requested) and a 500. See
    docs/project_memory.md §13 for the disclosure of what this fallback
    does and does not cover.
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
    period_num_idx = FEATURE_COLUMNS.index('period_num')

    for i in range(1, periods_ahead + 1):
        # BUG found and fixed this pass — period_num previously stayed
        # frozen at the last real observed value for every step of this
        # loop (verified empirically: instrumented the loop against real
        # trained-model data, period_num fed to the model was identical
        # on all 4 steps). That told the model every future period was
        # the same point in time it had already seen, rather than 1/2/3/4
        # periods further out. Advanced here, once per step, before
        # `features` is captured, so step i's period_num is genuinely
        # last-observed + i.
        last_row[period_num_idx] += 1
        features = last_row.copy()
        # Predict from a DataFrame with the same column names train_model()
        # fit on, not a bare array (model.predict([features])) — the model
        # still predicts correctly either way, but a raw array triggers a
        # real sklearn UserWarning ("X does not have valid feature names,
        # but OrdinalEncoder was fitted with feature names") on every
        # single forecast, which would spam production logs for no
        # behavioral difference.
        pred = max(0, model.predict(pd.DataFrame([features], columns=FEATURE_COLUMNS))[0])

        # Shift only the lag_1..lag_4 block for the next step-ahead
        # prediction (Design Notes revision #5) — rotating the whole
        # feature vector (the original np.roll(last_row, 1)) also
        # scrambles rolling_std_4/period_num/category_id/stockout_flag
        # into the wrong slots after the first step.
        for j in range(len(lag_indices) - 1, 0, -1):
            last_row[lag_indices[j]] = last_row[lag_indices[j - 1]]
        last_row[lag_indices[0]] = pred
        last_row[rolling_avg_idx] = np.mean([last_row[idx] for idx in lag_indices])
        # rolling_std_4 (index 5) is deliberately left untouched here,
        # unlike rolling_avg_4 just above — an explicit decision made
        # this pass, not an oversight Design Note #5 left ambiguous.
        # rolling_avg_4 is a level signal: it's standard recursive-
        # forecasting practice for a level feature to track the synthetic
        # future the loop is building. rolling_std_4 is a volatility
        # signal — recomputing it from 4 increasingly model-generated (and
        # typically smoother than real demand) values would make it
        # measure "how noisy is my own prediction sequence" rather than
        # real historical volatility, likely decaying toward artificially
        # low numbers the further out the horizon runs. Freezing it
        # anchors the model to the last real observed volatility instead
        # of a self-reinforcing synthetic drift.

        period_start = last_period + pd.tseries.frequencies.to_offset(freq) * i
        period_end = period_start + pd.tseries.frequencies.to_offset(freq) - pd.Timedelta(days=1)

        relative_error = residual_std / (pred + 1)
        confidence = min(0.95, max(0.50, 1 - relative_error))

        predictions.append({
            'period_start': period_start.date(),
            'period_end': period_end.date(),
            'forecasted_demand': round(pred, 2),
            'confidence_score': round(confidence, 2),
        })

    return predictions


def backfill_actual_demand():
    """
    For every DemandForecast whose period has fully elapsed but whose
    actual_demand is still unset, sum real COMPLETED SaleItem quantities
    for that product over the same period and store it (Design Notes
    revision #7 — REQ 9.9 had a schema field nothing ever wrote to).
    Asia/Dhaka "today" (timezone.localdate()), same BUG-47-class reasoning
    as everywhere else in this project that compares against a calendar
    day. Returns the count of forecasts updated."""
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
    """
    Retrains both period models with the latest data, then forecasts
    every active product for both periods, creating real DemandForecast
    rows. Returns a summary the caller (the view) uses for audit logging
    and notify_supervisors() — this function stays free of both, matching
    frontend/classification.py's run_full_classification(): a pure
    orchestration function, not itself responsible for who gets told.

    Each period's training is independent — found by testing, not
    documented: a system with real weekly history but not yet enough
    monthly history (train_model()'s own >=10-pooled-feature-row guard is
    far harder to satisfy for 'M' than 'W' — a product needs ~14 months
    of history, pooled across products, before monthly rows survive
    build_features()'s dropna() at all) shouldn't lose its perfectly
    valid weekly forecasts just because monthly can't train yet. Only
    raises if *neither* period can train — nothing at all could be
    forecast, which is a real failure worth surfacing to the caller.
    """
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

    # BUG found and fixed this pass — forecast_period_weeks is a
    # weeks-denominated horizon setting (its own name says so), but was
    # previously passed straight through as periods_ahead for BOTH
    # periods: with the seeded default of 4, the weekly run correctly
    # forecast 4 weeks ahead, but the monthly run forecast 4 *months*
    # ahead — a materially longer horizon than the setting promises.
    # Converted here rather than adding a second forecast_period_months
    # setting (out of scope for this pass — forecast_period_weeks stays
    # the one horizon knob an admin sees, matching every existing
    # caller/serializer/template that already names it that way).
    # Rounded to the nearest month, floored at 1 so a horizon shorter
    # than half a month never produces a zero-length monthly run.
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
    """The one comparison that defines "this forecast means reorder now":
    weekly forecasts only (a monthly forecast exceeding current stock is
    a routine, healthy pattern for anything restocked more than once a
    month, not a signal) AND forecasted demand exceeding what's on hand.

    Shared by run_full_forecast()'s replenish_alerts (fires the real
    ai_replenish notification supervisors see) and the Dashboard's
    forecast-replenishment widget (REQ 11.9) — written once specifically
    so tuning this threshold later (a buffer margin, a different
    comparison, lead-time awareness) can't happen in one call site and
    silently drift from the other, which would leave the dashboard
    disagreeing with the notification it's supposed to summarise.
    """
    return forecast_period == ForecastPeriod.WEEKLY and float(forecasted_demand) > float(current_stock)


def latest_forecast_batch():
    """One row per (product_id, forecast_period, period_start) — the most
    recently created one, discarding older re-run duplicates from the
    *display* only (the DB keeps every row on purpose — REQ 9.9 needs
    historical forecasts kept around to compare against actual_demand
    once backfilled; run_full_forecast() never deletes old rows).

    Extracted from DemandForecastingView._latest_batch() (Phase 11) so
    the Dashboard's AI Insights widget (REQ 11.9) can show "the current
    forecast" without a second, potentially-divergent definition of what
    that means — this dedup-by-latest-created-per-key is exactly the
    shape ForecastSummaryAPIView's own BUG-64 defect used to get wrong, by
    aggregating every row ever created instead of deduping like this.
    ForecastSummaryAPIView (frontend/api_views.py) now calls this function
    too, so all three surfaces — API, dashboard widget, forecasting page —
    share one definition of "current forecast."

    Returns (list_of_forecasts, most_recent_forecast_or_None).
    """
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
    """BUG-89 (docs/bugsfound.md) — latest_forecast_batch() above is left
    exactly as it is: it deliberately returns every period ever forecast,
    deduped only per (product, forecast_period, period_start), because
    REQ 9.9 needs that full history retained to compare against
    actual_demand once backfilled. But "every period ever forecast" is a
    different question from "what should a user see right now" — as
    forecasts accumulate across repeated runs, most of that pool
    describes periods that have already come and gone.

    Two consumers (the forecasting page's trend chart and its table's
    per-product row) used to answer "what's current" by sorting
    latest_forecast_batch()'s full pool chronologically and taking
    either the earliest N periods or the single earliest period per
    product — which, once enough runs accumulate, always picks the
    OLDEST period ever forecast, not the soonest upcoming one. Monthly
    only ever looked correct by coincidence: with just 3 distinct months
    on record, `[:4]` happened to include all of them.

    This is the one shared, correct answer to "what's current" for a
    given period type: every forecast whose period_start is today or
    later, restricted to the earliest `horizon` distinct period_start
    values (pass horizon=None for no cap — the per-product table
    selection needs every future period available, not just the
    chart's fixed 4 bars). Returns a flat list, empty if nothing has
    been forecast for today or later — a genuinely empty chart/table
    cell is honest; falling back to old data is not.
    """
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
