# 🧾 Module 06 — Sales Management
# AI-Powered Smart Inventory Management System

> **Claude Code:** Stock verification MUST happen before confirming any sale.
> Cancellation MUST restore stock. Invoice numbers are auto-generated.
> Sales history is preserved permanently for AI demand forecasting.

---

## Requirements Coverage
`REQ 6.1 → 6.15`

---

## Business Rules

| Rule | Detail |
|---|---|
| Invoice number | Auto-generated: `INV-YYYYMMDD-XXXX` |
| Stock check | Verify availability BEFORE confirming — raise error if insufficient |
| Stock deduction | Immediate on sale confirmation |
| Cancellation | Restores stock via `InventoryService.increase_stock()` |
| Customer info | Optional — not required for B2B or anonymous sales |
| Multi-product | Single transaction supports multiple line items |
| History | Never deleted — preserved for AI forecasting |
| Inactive product | Cannot be added to a sale |

---

## Service Layer

```python
# apps/sales/services.py
from django.db import transaction
from apps.inventory.services import InventoryService, InsufficientStockError
from apps.inventory.models import MovementType
from apps.audit.services import log_action
from apps.products.models import Product

class SaleService:

    @classmethod
    @transaction.atomic
    def create_sale(cls, sale_data, items_data, created_by):
        """
        sale_data: {customer_name, notes}
        items_data: [{product_id, quantity, unit_price, discount, tax}, ...]
        """
        from apps.sales.models import SaleTransaction, SaleItem

        # 1. Pre-validate all stock before touching anything
        for item in items_data:
            product = Product.objects.get(pk=item['product_id'])
            if not product.is_active:
                raise ValueError(f"Product '{product.name}' is inactive and cannot be sold.")
            from apps.inventory.models import InventoryRecord
            try:
                record = InventoryRecord.objects.get(product=product)
                if record.current_stock < item['quantity']:
                    raise InsufficientStockError(
                        f"Insufficient stock for '{product.name}'. "
                        f"Available: {record.current_stock}, Requested: {item['quantity']}"
                    )
            except InventoryRecord.DoesNotExist:
                raise InsufficientStockError(f"No inventory record for '{product.name}'.")

        # 2. Create transaction header
        sale = SaleTransaction.objects.create(
            created_by=created_by,
            customer_name=sale_data.get('customer_name', ''),
            notes=sale_data.get('notes', ''),
        )

        total = 0
        # 3. Create line items + deduct stock
        for item in items_data:
            product = Product.objects.get(pk=item['product_id'])
            line_total = (item['unit_price'] * item['quantity']) \
                         * (1 - item.get('discount', 0) / 100) \
                         * (1 + item.get('tax', 0) / 100)
            total += line_total

            SaleItem.objects.create(
                transaction=sale,
                product=product,
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                discount=item.get('discount', 0),
                tax=item.get('tax', 0),
                line_total=line_total
            )
            InventoryService.decrease_stock(
                product=product,
                quantity=item['quantity'],
                movement_type=MovementType.SALE,
                reference_type='SaleTransaction',
                reference_id=sale.pk,
                performed_by=created_by,
                notes=f'Sale {sale.invoice_number}'
            )

        sale.total_amount = total
        sale.save(update_fields=['total_amount'])
        log_action(created_by, 'SALE_CREATED', 'sales', affected_id=sale.pk, status='success')
        return sale

    @classmethod
    @transaction.atomic
    def cancel_sale(cls, sale, cancelled_by):
        if sale.status == 'cancelled':
            raise ValueError("Sale is already cancelled.")

        # Restore stock for each item
        for item in sale.items.all():
            InventoryService.increase_stock(
                product=item.product,
                quantity=item.quantity,
                movement_type=MovementType.RETURN,
                reference_type='SaleTransaction',
                reference_id=sale.pk,
                performed_by=cancelled_by,
                notes=f'Cancellation of {sale.invoice_number}'
            )

        sale.status = 'cancelled'
        sale.save(update_fields=['status', 'updated_at'])
        log_action(cancelled_by, 'SALE_CANCELLED', 'sales', affected_id=sale.pk, status='success')
        return sale
```

---

## Views

```python
# apps/sales/views.py
from django.shortcuts import render, redirect, get_object_or_404
from apps.rbac.decorators import staff_required, supervisor_required
from apps.sales.models import SaleTransaction
from apps.sales.services import SaleService
from apps.inventory.services import InsufficientStockError

@staff_required
def sale_list_view(request):
    sales = SaleTransaction.objects.select_related('created_by').order_by('-created_at')
    return render(request, 'sales/list.html', {'sales': sales})

@staff_required
def sale_create_view(request):
    if request.method == 'POST':
        try:
            sale_data = {
                'customer_name': request.POST.get('customer_name', ''),
                'notes': request.POST.get('notes', ''),
            }
            items_data = []  # Parse from POST (product_id, quantity, unit_price, discount, tax)
            sale = SaleService.create_sale(sale_data, items_data, request.user)
            return redirect('sales:detail', pk=sale.pk)
        except InsufficientStockError as e:
            from django.contrib import messages
            messages.error(request, str(e))
    return render(request, 'sales/form.html')

@staff_required
def sale_detail_view(request, pk):
    sale = get_object_or_404(SaleTransaction, pk=pk)
    return render(request, 'sales/detail.html', {'sale': sale})

@supervisor_required
def sale_cancel_view(request, pk):
    sale = get_object_or_404(SaleTransaction, pk=pk)
    if request.method == 'POST':
        SaleService.cancel_sale(sale, request.user)
        return redirect('sales:detail', pk=pk)
    return render(request, 'sales/cancel_confirm.html', {'sale': sale})

@staff_required
def sale_invoice_view(request, pk):
    """Printable invoice view."""
    sale = get_object_or_404(SaleTransaction, pk=pk)
    return render(request, 'sales/invoice.html', {'sale': sale})
```

---

## DRF API Serializers

```python
# apps/sales/serializers.py
from rest_framework import serializers
from apps.sales.models import SaleTransaction, SaleItem

class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = SaleItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_price',
                  'discount', 'tax', 'line_total']

class SaleItemCreateSerializer(serializers.Serializer):
    product_id  = serializers.IntegerField()
    quantity    = serializers.IntegerField(min_value=1)
    unit_price  = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount    = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax         = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)

class SaleTransactionSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)

    class Meta:
        model = SaleTransaction
        fields = ['id', 'invoice_number', 'customer_name', 'transaction_date',
                  'status', 'total_amount', 'created_by_name', 'items', 'notes', 'created_at']

class SaleCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(required=False, allow_blank=True)
    notes         = serializers.CharField(required=False, allow_blank=True)
    items         = SaleItemCreateSerializer(many=True, min_length=1)
```

---

## Audit Actions

| Action Constant | Triggered When |
|---|---|
| `SALE_CREATED` | New sale transaction confirmed |
| `SALE_CANCELLED` | Sale transaction cancelled and stock restored |
| `SALE_INVOICE_PRINTED` | Invoice viewed/downloaded |
