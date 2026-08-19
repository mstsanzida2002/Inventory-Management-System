"""
docs/DEAD_STOCK_DETECTION.md's serializer, used verbatim — every field it
lists exists on frontend.models.InventoryClassification/Product exactly as
named, so no adjustment was needed. Phase 9 pre-committed this one
read-only slice to Phase 10 (see docs/project_memory.md §13).

DemandForecastSerializer (Phase 11) — docs/DEMAND_FORECASTING.md
references this class by name in its API Views section but never defines
its fields anywhere (unlike InventoryClassificationSerializer's full
"## Serializer" section) — built here following that same
product_name/product_sku-plus-real-fields shape, since nothing about
DemandForecast's own fields suggested a different one.
"""
from rest_framework import serializers

from frontend.models import DemandForecast, InventoryClassification


class InventoryClassificationSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)

    class Meta:
        model = InventoryClassification
        fields = ['id', 'product', 'product_name', 'product_sku',
                  'classification', 'turnover_rate', 'last_sold_date',
                  'days_since_last_sale', 'recommendation', 'classified_at']


class DemandForecastSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)

    class Meta:
        model = DemandForecast
        fields = ['id', 'product', 'product_name', 'product_sku', 'forecast_period',
                  'period_start', 'period_end', 'forecasted_demand',
                  'recommended_reorder_qty', 'confidence_score', 'actual_demand',
                  'model_version', 'created_at']
