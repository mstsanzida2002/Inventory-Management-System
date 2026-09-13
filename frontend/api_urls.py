from django.urls import path

from frontend.api_views import (
    ClassificationListAPIView,
    ClassificationSummaryAPIView,
    ForecastListAPIView,
    ForecastSummaryAPIView,
)

urlpatterns = [
    path("ai/classifications/", ClassificationListAPIView.as_view(), name="ai_classifications_list"),
    path("ai/classifications/summary/", ClassificationSummaryAPIView.as_view(), name="ai_classifications_summary"),
    path("ai/forecasts/", ForecastListAPIView.as_view(), name="ai_forecasts_list"),
    path("ai/forecasts/summary/", ForecastSummaryAPIView.as_view(), name="ai_forecasts_summary"),
]
