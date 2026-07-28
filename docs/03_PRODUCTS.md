# 📦 Module 03 — Products & Categories
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when implementing product CRUD, SKU/barcode generation,
> category management, product image handling, or reorder level monitoring.

---

## Requirements Coverage
`REQ 3.1 → 3.15`

---

## Business Rules

| Rule | Detail |
|---|---|
| SKU | Unique, auto-generated if not provided: `PRD-YYYYMMDD-XXXX` |
| Barcode | Unique, optional, supports EAN-13/QR |
| Inactive products | Hidden from purchase and sales forms |
| Soft-delete | Never hard-delete a product — use `is_active = False` |
| Category | Required, must be active |
| Supplier | Required, must be active |
| Reorder level | When `current_stock <= reorder_level`, status = LOW_STOCK |
| History | All purchase/sale records remain even after product deactivation |
| Image | Optional upload, validated for type and size |

---

## Key Views

```python
# apps/products/views.py
from django.shortcuts import render, redirect, get_object_or_404
from apps.rbac.decorators import staff_required, supervisor_required
from apps.products.models import Product, Category
from apps.audit.services import log_action

@staff_required
def product_list_view(request):
    products = Product.objects.select_related('category', 'supplier').filter(is_active=True)
    # Search
    q = request.GET.get('q')
    if q:
        products = products.filter(
            name__icontains=q
        ) | products.filter(sku__icontains=q) | products.filter(barcode__icontains=q)
    # Filter
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)
    return render(request, 'products/list.html', {
        'products': products,
        'categories': Category.objects.filter(is_active=True)
    })

@staff_required
def product_create_view(request):
    if request.method == 'POST':
        # Validate + create product
        # Create InventoryRecord for the new product
        from apps.inventory.models import InventoryRecord
        product = Product.objects.create(...)
        InventoryRecord.objects.create(product=product, reorder_level=product.reorder_level)
        log_action(request.user, 'PRODUCT_CREATED', 'products', affected_id=product.pk, status='success', request=request)
        return redirect('products:detail', pk=product.pk)
    return render(request, 'products/form.html')

@supervisor_required
def product_deactivate_view(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.is_active = False
    product.save(update_fields=['is_active'])
    log_action(request.user, 'PRODUCT_DEACTIVATED', 'products', affected_id=product.pk, status='success', request=request)
    return redirect('products:list')
```

---

## SKU Auto-Generation

```python
# apps/products/models.py
def generate_sku():
    from django.utils import timezone
    import random
    return f"PRD-{timezone.now().strftime('%Y%m%d')}-{random.randint(1000,9999)}"

class Product(TimeStampedModel):
    sku = models.CharField(max_length=50, unique=True, default=generate_sku)
    ...
```

---

## Serializer

```python
# apps/products/serializers.py
from rest_framework import serializers
from apps.products.models import Product

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.company_name', read_only=True)
    inventory_status = serializers.CharField(source='inventory.status', read_only=True)
    current_stock = serializers.IntegerField(source='inventory.current_stock', read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'sku', 'barcode', 'name', 'brand', 'category', 'category_name',
                  'supplier', 'supplier_name', 'purchase_price', 'selling_price',
                  'reorder_level', 'current_stock', 'inventory_status', 'unit', 'is_active']
```

---

## Audit Actions

| Action | Triggered When |
|---|---|
| `PRODUCT_CREATED` | New product added |
| `PRODUCT_UPDATED` | Product info edited |
| `PRODUCT_DEACTIVATED` | Product deactivated |
| `CATEGORY_CREATED` | New category added |
| `CATEGORY_UPDATED` | Category edited |
