"""
Server-side "current filter" for every paginated list page — one function
per table, mirroring frontend/reports.py's own filter_movements() (Phase
8.99d) exactly: read GET params, apply them as real queryset conditions,
return one queryset the page (and, where an export exists, the export)
can share. filter_movements() itself predates this module and stays put
in reports.py rather than being moved for the sake of it — not worth the
churn of relocating a stable, working function; every filter added since
this pagination pass follows its shape from here instead.

paginate()/pagination_querystring() are the other half of the shared
pattern: real django.core.paginator.Paginator, get_page() so an
out-of-range ?page= clamps instead of raising a 404/500, and the
querystring helper that lets a filter/search/toggle survive a
Previous/Next click by re-attaching everything except `page` to the link
— exactly MovementHistoryListView's own inline idiom, shared here instead
of copied into eight more views.

Demand Forecasting is the one exception to "returns a queryset": its
table rows are already a derived, reduced Python list (nearest upcoming
forecast per (product, period-type), not a 1:1 queryset row — see
DemandForecastingView.get() for why) by the time any filtering happens,
so filter_forecasts() filters that list directly instead of building a
Q(). It still runs against every row, not just the current page's 10 —
the property that actually matters for REQ 14.11 — it just does it in
Python because the data was already reduced to Python upstream.
"""
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
    """Same as pagination_querystring(), plus `exclude_param` stripped —
    for a segmented-toggle link (audit log's status, slow-moving's
    classification, forecasting's period): every OTHER current filter
    survives the click, the toggle's own stale value doesn't linger next
    to the new one being set, and dropping `page` lands the click back on
    page 1, same as the approved plan for a toggle change."""
    qs = request.GET.copy()
    qs.pop("page", None)
    qs.pop(exclude_param, None)
    return qs.urlencode()


def paginate(request, queryset_or_list, page_size):
    """Paginator + get_page() in one call — get_page() clamps an
    out-of-range or non-numeric ?page= to the nearest real page instead
    of raising, same guarantee Movement History already relies on."""
    return Paginator(queryset_or_list, page_size).get_page(request.GET.get("page"))


def filter_products(request, base_qs=None):
    """Search: name/SKU. Category: id. Status: the derived label
    ProductListCreateView's own per-row loop computes in Python
    (current_stock<=0 -> "Out of stock"; reorder_level>0 and
    current_stock<=reorder_level -> "Low stock"; else "In stock") —
    expressed here as real queryset conditions, matching that branching
    exactly, so it can run before pagination instead of after."""
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
    """Search: action or the acting user's full name — plus the synthetic
    "System" label rows display for a null user (log.user_label in the
    template), matched here as "does the search term appear inside the
    literal word System", the same substring test the client-side filter
    it replaces used to run against that same computed label. Module:
    exact. Status: success/failure, via the page's segmented toggle."""
    qs = base_qs if base_qs is not None else AuditLog.objects.select_related("user")

    q = request.GET.get("q", "").strip()
    if q:
        conditions = Q(action__icontains=q) | Q(user__full_name__icontains=q)
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
    """Search: product name/SKU. Category: name (the page's own <select>
    options carry the category name as their value, not the id — matches
    that, not a pk). Classification: the page's segmented toggle."""
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
    """Filters DemandForecastingView's own already-reduced list (see this
    module's own docstring for why it's a list, not a queryset, by this
    point) — search against each row's own precomputed `search_blob`
    (product name + SKU), category against `product.category.name`
    (matches the <select>'s own name-valued options), period against the
    page's own weekly/monthly segmented toggle."""
    q = request.GET.get("q", "").strip().lower()
    category = request.GET.get("category", "")
    # No "All periods" option exists on this page's toggle (Weekly/Monthly
    # only, unlike audit log's All/Success/Failure) — the client-side
    # filter it replaces defaulted to weekly (segmentDefault: "weekly") via
    # its is-active markup, so an absent ?period= must resolve to "weekly"
    # here too rather than showing both periods mixed together.
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
