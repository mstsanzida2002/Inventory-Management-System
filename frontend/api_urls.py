"""
Phase 10/11 — the only DRF routes in this project (docs/project_memory.md
§13). API_CONTRACTS.md documents detail/run routes for both AI features
too (`/ai/classifications/{id}/`, `/ai/forecasts/{product_id}/`, both
`run/` endpoints); only the `run/` routes are explicitly out of scope
(Celery). The detail routes aren't built either — nothing consumes them
and neither phase's own verification needs them, so they stay unbuilt
rather than added speculatively.
"""
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
