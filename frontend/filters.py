from django.core.paginator import Paginator
from django.db.models import F, Q

from frontend.models import (
    AuditLog,
    InventoryClassification,
    InventoryRecord,
    InventoryStatus,
    POStatus,
    Product,
    PurchaseOrder,
    SaleStatus,
    SaleTransaction,
    StockClassification,
)


def pagination_querystring(request):
    """Current GET params with `page` stripped, urlencoded."""
    qs = request.GET.copy()
    qs.pop("page", None)
    return qs.urlencode()


def toggle_querystring(request, exclude_param):
    """Like pagination_querystring(), plus `exclude_param` stripped."""
    qs = request.GET.copy()
    qs.pop("page", None)
    qs.pop(exclude_param, None)
    return qs.urlencode()


def paginate(request, queryset_or_list, page_size):
    """get_page() clamps an out-of-range or non-numeric ?page= instead of raising."""
    return Paginator(queryset_or_list, page_size).get_page(request.GET.get("page"))


def filter_products(request, base_qs=None):
    """Search: name/SKU. Category: id. Status: Out of stock/Low stock/In stock."""
    qs = base_qs if base_qs is not None else Product.objects.select_related("category", "supplier")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))

    category_id = request.GET.get("category", "")
    if category_id.isdigit():
        qs = qs.filter(category_id=category_id)

    status = request.GET.get("status", "")
    if status == "Out of stock":
        qs = qs.filter(current_stock__lte=0)
    elif status == "Low stock":
        qs = qs.filter(current_stock__gt=0, reorder_level__gt=0, current_stock__lte=F("reorder_level"))
    elif status == "In stock":
        qs = qs.filter(current_stock__gt=0).filter(Q(reorder_level=0) | Q(current_stock__gt=F("reorder_level")))

    return qs


def filter_purchases(request, base_qs=None):
    """Search: PO number/supplier company name. Status: POStatus value."""
    qs = base_qs if base_qs is not None else PurchaseOrder.objects.select_related("supplier", "created_by").prefetch_related("items__product")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(po_number__icontains=q) | Q(supplier__company_name__icontains=q))

    status = request.GET.get("status", "")
    if status in POStatus.values:
        qs = qs.filter(status=status)

    return qs


def filter_sales(request, base_qs=None):
    """Search: invoice number/customer name. Status: SaleStatus value."""
    qs = base_qs if base_qs is not None else SaleTransaction.objects.select_related("created_by").prefetch_related("items")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(invoice_number__icontains=q) | Q(customer_name__icontains=q))

    status = request.GET.get("status", "")
    if status in SaleStatus.values:
        qs = qs.filter(status=status)

    return qs


def filter_inventory(request, base_qs=None):
    """Search: product name/SKU/barcode. Status: InventoryStatus value."""
    qs = base_qs if base_qs is not None else InventoryRecord.objects.select_related("product", "product__category", "product__supplier")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(product__sku__icontains=q) | Q(product__barcode__icontains=q))

    status = request.GET.get("status", "")
    if status in InventoryStatus.values:
        qs = qs.filter(status=status)

    return qs


def filter_audit_log(request, base_qs=None):
    """Search: action or user's full name. Module: exact. Status: success/failure."""
    qs = base_qs if base_qs is not None else AuditLog.objects.select_related("user")

    q = request.GET.get("q", "").strip()
    if q:
        conditions = Q(action__icontains=q) | Q(user__full_name__icontains=q)
        # Rule: a null user displays as "System" -- matched as a substring too.
        if q.lower() in "system":
            conditions |= Q(user__isnull=True)
        qs = qs.filter(conditions)

    module = request.GET.get("module", "")
    if module:
        qs = qs.filter(module=module)

    status = request.GET.get("status", "")
    if status in ("success", "failure"):
        qs = qs.filter(status=status)

    return qs


def filter_classifications(request, base_qs=None):
    """Search: product name/SKU. Category: matched by name, not id."""
    qs = base_qs if base_qs is not None else InventoryClassification.objects.select_related("product", "product__category")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(product__sku__icontains=q))

    category = request.GET.get("category", "")
    if category:
        qs = qs.filter(product__category__name=category)

    classification = request.GET.get("classification", "")
    if classification in StockClassification.values:
        qs = qs.filter(classification=classification)

    return qs


def filter_forecasts(rows, request):
    """Filters an already-reduced list of rows, not a queryset."""
    q = request.GET.get("q", "").strip().lower()
    category = request.GET.get("category", "")
    # Assumption: no "All periods" toggle option -- an absent ?period= means weekly.
    period = request.GET.get("period", "") or "weekly"

    def matches(row):
        if q and q not in row.search_blob:
            return False
        if category and row.product.category.name != category:
            return False
        if row.period_type != period:
            return False
        return True

    return [row for row in rows if matches(row)]
