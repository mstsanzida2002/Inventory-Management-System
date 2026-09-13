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
    permission_classes = [IsSupervisorOrAbove]
    serializer_class = DemandForecastSerializer

    def get_queryset(self):
        # Perf: capped at 200 -- no pagination on this endpoint.
        return DemandForecast.objects.select_related('product').order_by('-period_start')[:200]


class ForecastSummaryAPIView(APIView):
    permission_classes = [IsSupervisorOrAbove]

    def get(self, request):
        # Rule: reads latest_forecast_batch() -- must match the dashboard's own count.
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
