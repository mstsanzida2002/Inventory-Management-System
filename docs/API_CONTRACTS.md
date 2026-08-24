# 🔌 API Contracts
# AI-Powered Smart Inventory Management System

> **Claude Code:** This project is server-rendered Django templates, not a
> REST-API-driven frontend. There is a single, small, deliberately
> read-only DRF slice covering AI classification/forecast data
> (`frontend/api_urls.py`, `frontend/api_views.py`) — that is the entire
> API surface. Everything else in the product (products, purchases,
> sales, inventory, adjustments, reports, notifications, users, dashboard)
> is a server-rendered view with its own POST-based mutation endpoints,
> not a REST resource — see `docs/CODEBASE_MAP.md` for those routes.
>
> An earlier version of this file documented a ~30-endpoint REST surface
> across every module. That surface was never built; the entries below
> are the only DRF routes that exist. A hand-built, server-rendered app
> with a small, honest read-only API slice is a defensible architecture —
> a fictional REST surface documented as if it existed is not. See
> `docs/bugsfound.md` BUG-68 for the full history of this correction.

---

## AI Endpoints (the entire API surface)

All four require authentication and `IsSupervisorOrAbove`
(`frontend/permissions.py` — Supervisor or Admin role; a Staff or
anonymous request gets 403/401). Prefixed `/api/v1/`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/ai/classifications/` | Paginated list of `InventoryClassification` rows |
| GET | `/api/v1/ai/classifications/summary/` | `{classification_value: count}` — dashboard-widget shape |
| GET | `/api/v1/ai/forecasts/` | Paginated list of `DemandForecast` rows (newest `period_start` first, capped at 200) |
| GET | `/api/v1/ai/forecasts/summary/` | `{total_forecasts, products_forecasted, avg_confidence, latest_model_version}` |

**`/ai/classifications/` query param:** `?filter=fast|slow|dead|insufficient_data`

**`InventoryClassificationSerializer` fields** (`frontend/serializers.py`):
`id, product, product_name, product_sku, classification, turnover_rate,
last_sold_date, days_since_last_sale, recommendation, classified_at,
stagnation_index, confidence, recency_score, turnover_score,
coverage_score, frequency_score`

**`DemandForecastSerializer` fields**:
`id, product, product_name, product_sku, forecast_period, period_start,
period_end, forecasted_demand, recommended_reorder_qty, confidence_score,
actual_demand, model_version, created_at`

**List response shape** (standard DRF `ListAPIView` pagination — applies
to `/ai/classifications/` and `/ai/forecasts/`):
```json
{
  "count": 43,
  "next": "http://domain/api/v1/ai/classifications/?page=2",
  "previous": null,
  "results": [...]
}
```

Not built, and not planned without a scheduler: `RunClassificationAPIView`/
`RunForecastAPIView` (both would `.delay()` a Celery task — no Celery
exists in this project, see `docs/DEAD_STOCK_DETECTION.md`/
`docs/DEMAND_FORECASTING.md`) and the per-product detail routes
(`/ai/classifications/{id}/`, `/ai/forecasts/{product_id}/` — nothing
consumes them).
