"""
Phase 10/11 — the two DRF slices Phase 9 pre-committed (docs/
project_memory.md §13): read-only classification and forecast data,
nothing else. Deliberately NOT built (see the doc's own reference code for
both): `RunClassificationAPIView`/`RunForecastAPIView` — both `.delay()` a
Celery task and Celery isn't installed; the manual "Run ... now" POSTs
(SlowMovingDeadStockView.post()/DemandForecastingView.post()) are the only
triggers. `ProductForecastAPIView` (per-product detail) isn't built either
— nothing consumes it and it's not needed for this phase's own
verification. No other AI/Report/etc. endpoint from API_CONTRACTS.md's
remaining ~50 routes is built here — both slices are additive and scoped
to exactly what their phase's data supports.
"""
from django.db.models import Count
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from frontend.forecasting import latest_forecast_batch
from frontend.models import DemandForecast, InventoryClassification
from frontend.permissions import IsSupervisorOrAbove
from frontend.serializers import DemandForecastSerializer, InventoryClassificationSerializer


class ClassificationListAPIView(ListAPIView):
    permission_classes = [IsSupervisorOrAbove]
    serializer_class = InventoryClassificationSerializer

    def get_queryset(self):
        qs = InventoryClassification.objects.select_related('product').order_by('-classified_at')
        filter_by = self.request.query_params.get('filter')
        if filter_by in ['fast', 'slow', 'dead', 'insufficient_data']:
            qs = qs.filter(classification=filter_by)
        return qs


class ClassificationSummaryAPIView(APIView):
    """Dashboard-widget-shaped summary: {"fast": n, "slow": n, "dead": n}."""
    permission_classes = [IsSupervisorOrAbove]

    def get(self, request):
        summary = InventoryClassification.objects.values('classification').annotate(count=Count('id'))
        return Response({item['classification']: item['count'] for item in summary})


class ForecastListAPIView(ListAPIView):
    """docs/DEMAND_FORECASTING.md's ForecastListAPIView, used verbatim
    (select_related + order by -period_start, capped at 200 rows)."""
    permission_classes = [IsSupervisorOrAbove]
    serializer_class = DemandForecastSerializer

    def get_queryset(self):
        return DemandForecast.objects.select_related('product').order_by('-period_start')[:200]


class ForecastSummaryAPIView(APIView):
    """Not separately specified in the doc (only ForecastListAPIView/
    ProductForecastAPIView/RunForecastAPIView are) — shaped the same way
    as ClassificationSummaryAPIView above for a consistent, small
    dashboard-widget-style read.

    BUG-64 (docs/bugsfound.md), fixed: this used to aggregate
    unconditionally across every DemandForecast row ever created
    (`DemandForecast.objects.all()`, no dedup by run) while the HTML
    dashboard/forecasting page both showed only the latest batch — after
    two runs this endpoint would report roughly double what the two real
    UI surfaces agreed on. Now consumes
    frontend.forecasting.latest_forecast_batch(), the same dedup-by-
    latest-created-per-(product, period, period_start) definition
    DemandForecastingView and the Dashboard's forecast widget already
    share — one definition of "current forecast," three surfaces, not a
    second divergent one here. DemandForecast.objects.create() and the
    intentional cross-run row accumulation (REQ 9.9 needs forecast
    history to compare against actual_demand once backfilled) are both
    untouched — this only changes what gets *read* for a summary, never
    what gets written."""
    permission_classes = [IsSupervisorOrAbove]

    def get(self, request):
        forecasts, last_run = latest_forecast_batch()
        products_forecasted = len({f.product_id for f in forecasts})
        avg_confidence = (
            sum(float(f.confidence_score) for f in forecasts) / len(forecasts)
            if forecasts else None
        )
        return Response({
            'total_forecasts': len(forecasts),
            'products_forecasted': products_forecasted,
            'avg_confidence': avg_confidence,
            'latest_model_version': last_run.model_version if last_run else None,
        })
