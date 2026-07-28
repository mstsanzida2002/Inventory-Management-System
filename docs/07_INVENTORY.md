# 📦 Module 07 — Inventory Management
# AI-Powered Smart Inventory Management System

> **Claude Code:** This is the CORE module. All stock quantity changes flow
> through `apps/inventory/services.py`. Never update stock directly outside
> the service layer. Read this before touching any purchase, sale, or adjustment logic.

---

## Requirements Coverage
`REQ 7.1 → 7.18`

---

## Business Rules

| Rule | Detail |
|---|---|
| Stock never negative | Enforced in service layer + DB check constraint |
| Real-time updates | Inventory updated immediately after purchase receipt, sale, or approved adjustment |
| Status auto-calculation | `AVAILABLE` / `LOW_STOCK` / `OUT_OF_STOCK` updated on every stock change |
| Movement ledger | Every stock change creates an immutable `InventoryMovement` record |
| One record per product | `InventoryRecord` is a `OneToOneField` on Product |
| Valuation | `total_value = current_stock × purchase_price` |
| Low stock threshold | Based on `InventoryRecord.reorder_level` (set from product's `reorder_level`) |
| Barcode lookup | Products searchable by barcode for fast inventory operations |

---

## Inventory Service Layer

### `apps/inventory/services.py` — All Stock Operations Go Here

```python
from django.db import transaction
from django.utils import timezone
from apps.inventory.models import InventoryRecord, InventoryMovement, InventoryStatus, MovementType
from apps.notifications.services import notify_supervisors
from apps.audit.services import log_action


class InsufficientStockError(Exception):
    pass


class InventoryService:

    @classmethod
    @transaction.atomic
    def increase_stock(cls, product, quantity, movement_type, reference_type,
                       reference_id, performed_by, notes=''):
        """
        Add stock to inventory. Used by: purchase receipt, approved adjustment (increase).
        """
        record, created = InventoryRecord.objects.select_for_update().get_or_create(
            product=product,
            defaults={'reorder_level': product.reorder_level}
        )
        stock_before = record.current_stock
        record.current_stock += quantity
        record.total_value = record.current_stock * product.purchase_price
        record.update_status()
        record.save()

        InventoryMovement.objects.create(
            product=product,
            movement_type=movement_type,
            quantity_change=+quantity,
            stock_before=stock_before,
            stock_after=record.current_stock,
            reference_type=reference_type,
            reference_id=reference_id,
            performed_by=performed_by,
            notes=notes
        )
        # Sync product.current_stock
        product.current_stock = record.current_stock
        product.save(update_fields=['current_stock'])

        return record

    @classmethod
    @transaction.atomic
    def decrease_stock(cls, product, quantity, movement_type, reference_type,
                       reference_id, performed_by, notes=''):
        """
        Remove stock from inventory. Used by: sale, approved adjustment (decrease).
        Raises InsufficientStockError if not enough stock.
        """
        record = InventoryRecord.objects.select_for_update().get(product=product)

        if record.current_stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for '{product.name}'. "
                f"Available: {record.current_stock}, Requested: {quantity}"
            )

        stock_before = record.current_stock
        record.current_stock -= quantity
        record.total_value = record.current_stock * product.purchase_price
        record.update_status()
        record.save()

        InventoryMovement.objects.create(
            product=product,
            movement_type=movement_type,
            quantity_change=-quantity,
            stock_before=stock_before,
            stock_after=record.current_stock,
            reference_type=reference_type,
            reference_id=reference_id,
            performed_by=performed_by,
            notes=notes
        )
        product.current_stock = record.current_stock
        product.save(update_fields=['current_stock'])

        # Check low stock and notify
        if record.status in [InventoryStatus.LOW_STOCK, InventoryStatus.OUT_OF_STOCK]:
            cls._send_low_stock_notification(product, record)

        return record

    @classmethod
    def _send_low_stock_notification(cls, product, record):
        from apps.notifications.models import NotificationType
        if record.status == InventoryStatus.OUT_OF_STOCK:
            notify_supervisors(
                notification_type=NotificationType.OUT_OF_STOCK,
                title=f'Out of Stock: {product.name}',
                message=f'{product.name} [{product.sku}] is now out of stock.',
                link=f'/inventory/{product.id}/'
            )
        else:
            notify_supervisors(
                notification_type=NotificationType.LOW_STOCK,
                title=f'Low Stock Alert: {product.name}',
                message=f'{product.name} [{product.sku}] has {record.current_stock} units remaining (reorder level: {record.reorder_level}).',
                link=f'/inventory/{product.id}/'
            )
```

---

## Inventory Views

### `apps/inventory/views.py`

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from apps.rbac.decorators import staff_required
from apps.inventory.models import InventoryRecord, InventoryMovement
from apps.products.models import Product

@staff_required
def inventory_list_view(request):
    """All inventory records with search and status filter."""
    records = InventoryRecord.objects.select_related('product', 'product__category', 'product__supplier')
    status_filter = request.GET.get('status')
    search = request.GET.get('q')

    if status_filter:
        records = records.filter(status=status_filter)
    if search:
        records = records.filter(
            product__name__icontains=search
        ) | records.filter(
            product__sku__icontains=search
        ) | records.filter(
            product__barcode__icontains=search
        )

    context = {
        'records': records.order_by('product__name'),
        'total_value': records.aggregate(total=Sum('total_value'))['total'] or 0,
    }
    return render(request, 'inventory/list.html', context)

@staff_required
def inventory_detail_view(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    record = get_object_or_404(InventoryRecord, product=product)
    movements = InventoryMovement.objects.filter(product=product).order_by('-created_at')[:50]
    return render(request, 'inventory/detail.html', {
        'product': product,
        'record': record,
        'movements': movements
    })

@staff_required
def low_stock_view(request):
    from apps.inventory.models import InventoryStatus
    records = InventoryRecord.objects.filter(
        status__in=[InventoryStatus.LOW_STOCK, InventoryStatus.OUT_OF_STOCK]
    ).select_related('product')
    return render(request, 'inventory/low_stock.html', {'records': records})
```

---

## DRF API Views

```python
# apps/inventory/api_views.py
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.rbac.permissions import IsAnyStaff
from apps.inventory.models import InventoryRecord, InventoryMovement
from apps.inventory.serializers import InventoryRecordSerializer, InventoryMovementSerializer

class InventoryListAPIView(ListAPIView):
    permission_classes = [IsAnyStaff]
    serializer_class = InventoryRecordSerializer

    def get_queryset(self):
        qs = InventoryRecord.objects.select_related('product')
        status = self.request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

class InventoryDetailAPIView(RetrieveAPIView):
    permission_classes = [IsAnyStaff]
    serializer_class = InventoryRecordSerializer
    queryset = InventoryRecord.objects.select_related('product')
    lookup_field = 'product_id'

class InventoryMovementAPIView(ListAPIView):
    permission_classes = [IsAnyStaff]
    serializer_class = InventoryMovementSerializer

    def get_queryset(self):
        return InventoryMovement.objects.filter(
            product_id=self.kwargs['product_id']
        ).order_by('-created_at')

class InventoryStatsAPIView(APIView):
    """For dashboard widgets."""
    permission_classes = [IsAnyStaff]

    def get(self, request):
        from django.db.models import Sum, Count
        stats = InventoryRecord.objects.aggregate(
            total_value=Sum('total_value'),
            total_products=Count('id'),
            low_stock_count=Count('id', filter=Q(status='low_stock')),
            out_of_stock_count=Count('id', filter=Q(status='out_of_stock')),
        )
        return Response(stats)
```

---

## Serializers

```python
# apps/inventory/serializers.py
from rest_framework import serializers
from apps.inventory.models import InventoryRecord, InventoryMovement

class InventoryRecordSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku  = serializers.CharField(source='product.sku', read_only=True)
    category     = serializers.CharField(source='product.category.name', read_only=True)

    class Meta:
        model = InventoryRecord
        fields = ['id', 'product', 'product_name', 'product_sku', 'category',
                  'current_stock', 'reorder_level', 'status', 'total_value', 'updated_at']

class InventoryMovementSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source='performed_by.full_name', read_only=True)

    class Meta:
        model = InventoryMovement
        fields = ['id', 'movement_type', 'quantity_change', 'stock_before',
                  'stock_after', 'reference_type', 'reference_id',
                  'performed_by_name', 'notes', 'created_at']
```

---

## URL Configuration

```python
# apps/inventory/urls.py
from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list_view, name='list'),
    path('<int:product_id>/', views.inventory_detail_view, name='detail'),
    path('low-stock/', views.low_stock_view, name='low_stock'),
    path('movements/', views.movement_history_view, name='movements'),
]

# apps/inventory/api_urls.py
from django.urls import path
from . import api_views

urlpatterns = [
    path('', api_views.InventoryListAPIView.as_view()),
    path('<int:product_id>/', api_views.InventoryDetailAPIView.as_view()),
    path('<int:product_id>/movements/', api_views.InventoryMovementAPIView.as_view()),
    path('stats/', api_views.InventoryStatsAPIView.as_view()),
    path('low-stock/', api_views.LowStockAPIView.as_view()),
    path('out-of-stock/', api_views.OutOfStockAPIView.as_view()),
]
```

---

## Audit Actions for This Module

| Action Constant | Triggered When |
|---|---|
| `INVENTORY_VIEWED` | Inventory list accessed |
| `LOW_STOCK_ALERT_SENT` | Low stock notification triggered |
| `OUT_OF_STOCK_ALERT_SENT` | Out-of-stock notification triggered |
| `PHYSICAL_COUNT_PERFORMED` | Manual stock verification done |
