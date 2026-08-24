"""
docs/10_REPORTS.md's 9 report types + PDF/CSV export, translated into the
single `frontend` app the same way frontend/audit.py and
frontend/notifications.py already are — no `apps/reports/` app created
(see docs/project_memory.md §13).

PDF library: ReportLab, not WeasyPrint, even though 10_REPORTS.md's own
example code uses WeasyPrint. TECH_STACK.md documents both as acceptable
("ReportLab or WeasyPrint") — WeasyPrint needs GTK/Pango/Cairo native
libraries that aren't a pip install on Windows (this project's dev
environment, see docs/project_memory.md's environment notes), while
ReportLab is pure Python and installed cleanly with zero native
dependencies. A disclosed choice within the doc's own stated options, not
a deviation from it.

Every report builder below returns (title, headers, rows) — rows already
display-ready strings/numbers, not raw querysets — so generate_pdf_response/
generate_csv_response can stay completely generic instead of the
getattr-chain approach 10_REPORTS.md's own generate_csv() reference code
uses (that approach doesn't reach across joins or computed values cleanly,
e.g. a movement row's product name or a sale's item count).

Phase 13 — every PDF export below (generate_pdf_response, and the 3
per-record documents further down) now renders through frontend/pdf.py's
shared header/footer/style infrastructure instead of building its own
ReportLab document from scratch; see that module's own docstring for the
two disclosed ReportLab-only constraints (no ৳ glyph, no SVG logo
rasterization) this inherits.
"""
import csv
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.http import HttpResponse
from django.db.models import Count, Q, Sum
from django.utils import timezone

from frontend import pdf as pdf_lib
from frontend.models import (
    AdjustmentStatus,
    DemandForecast,
    InventoryAdjustment,
    InventoryClassification,
    InventoryMovement,
    InventoryRecord,
    InventoryStatus,
    MovementType,
    POStatus,
    PurchaseOrder,
    SaleStatus,
    SaleTransaction,
)
from frontend.pricing import calculate_totals_breakdown


def _date_bounds(request):
    """Common `date_from`/`date_to` GET params (10_REPORTS.md) as
    (start, end) datetimes, or (None, None) if not given. end is set to
    23:59:59 on date_to so `lte` includes the whole day, not just midnight.

    Phase 8.98: made timezone-aware (`timezone.make_aware()`, in the
    active TIME_ZONE = 'Asia/Dhaka') — a genuine, if latent, pre-existing
    bug surfaced by this phase's own new date-filtered export test (no
    earlier test ever exercised this function with date_from/date_to
    actually set). A naive datetime compared against `created_at`
    (`DateTimeField`, `USE_TZ=True`) made Django coerce it into the active
    timezone anyway with a loud `RuntimeWarning` — same end result, just
    noisy. This makes the intent explicit instead of relying on that
    implicit coercion."""
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    start = timezone.make_aware(datetime.strptime(date_from, "%Y-%m-%d")) if date_from else None
    end = timezone.make_aware(datetime.combine(datetime.strptime(date_to, "%Y-%m-%d"), time.max)) if date_to else None
    return start, end


def _category_id(request):
    value = request.GET.get("category")
    return int(value) if value and value.isdigit() else None


def _supplier_id(request):
    value = request.GET.get("supplier")
    return int(value) if value and value.isdigit() else None


def _product_id(request):
    value = request.GET.get("product")
    return int(value) if value and value.isdigit() else None


def filter_movements(request, base_qs=None):
    """Phase 8.99d — single source of truth for what "the current Movement
    History filter" means: date_from/date_to (via `_date_bounds()`,
    already timezone-aware — BUG-46), product, movement_type, and a
    server-side search (q, product name/SKU icontains).

    Used by BOTH `MovementHistoryListView` (the page) and
    `build_movement_report()` (its CSV/PDF export), so the two can never
    silently disagree again — before this phase, the page filtered dates
    with `created_at__date__gte` while the export used this file's own
    `_date_bounds()`-based `created_at__gte`, and the export had no
    product/type/search filtering at all. One function, two callers.

    `q` matches what used to be table-filter.js's client-side-only search
    (product name/SKU). Made server-side here rather than kept
    client-side-with-a-caveat: the exact "grows unbounded, so client-side
    only ever sees one page" argument BUG-45 originally used to justify
    server-side dates applies identically to search — a client-side-only
    search could never be reflected in an export anyway (this phase's own
    goal), and disclosing "search isn't exported" as a permanent UI
    caveat is worse than just making it real. `table-filter.js` is no
    longer loaded on this page as a result (still used by Forecasting/
    Slow-Moving, untouched)."""
    qs = base_qs if base_qs is not None else InventoryMovement.objects.select_related("product", "performed_by")

    start, end = _date_bounds(request)
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)

    product_id = _product_id(request)
    if product_id:
        qs = qs.filter(product_id=product_id)

    movement_type = request.GET.get("movement_type")
    if movement_type in MovementType.values:
        qs = qs.filter(movement_type=movement_type)

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(product__sku__icontains=q))

    return qs


# --------------------------------------------------------------- 1. Inventory

def build_inventory_report(request):
    qs = InventoryRecord.objects.select_related("product", "product__category", "product__supplier").order_by("product__name")
    category_id, supplier_id = _category_id(request), _supplier_id(request)
    if category_id:
        qs = qs.filter(product__category_id=category_id)
    if supplier_id:
        qs = qs.filter(product__supplier_id=supplier_id)

    headers = ["SKU", "Product", "Category", "Supplier", "Current Stock", "Reorder Level", "Status", "Total Value"]
    rows = [
        [r.product.sku, r.product.name, r.product.category.name, r.product.supplier.company_name,
         r.current_stock, r.reorder_level, r.get_status_display(), f"{r.total_value:.2f}"]
        for r in qs
    ]
    return "Inventory Report", headers, rows


# --------------------------------------------------------------- 2. Purchases

def build_purchase_report(request):
    qs = PurchaseOrder.objects.select_related("supplier", "created_by").order_by("-order_date")
    start, end = _date_bounds(request)
    supplier_id = _supplier_id(request)
    if start:
        qs = qs.filter(order_date__gte=start.date())
    if end:
        qs = qs.filter(order_date__lte=end.date())
    if supplier_id:
        qs = qs.filter(supplier_id=supplier_id)

    # Phase 8.99c — added "Reason" (PurchaseOrder.display_reason: cancelled_
    # reason or rejected_reason, whichever applies), per this phase's
    # Objective #3 ("visible wherever that record is reported or
    # exported"). Extending an existing report type's columns rather than
    # adding a 10th type — 10_REPORTS.md documents 9 fixed report types;
    # this is the smaller, disclosed deviation (see project_memory.md §13).
    headers = ["PO Number", "Supplier", "Status", "Order Date", "Expected Delivery", "Total Cost", "Created By", "Reason"]
    rows = [
        [po.po_number, po.supplier.company_name, po.get_status_display(), po.order_date,
         po.expected_delivery or "—", f"{po.total_cost:.2f}", po.created_by.full_name, po.display_reason or "—"]
        for po in qs
    ]
    return "Purchase Report", headers, rows


# ------------------------------------------------------------------ 3. Sales

def build_sales_report(request, category_filtered=True):
    # Phase 8.99c — was `.filter(status=SaleStatus.COMPLETED)`, matching
    # 10_REPORTS.md's own reference `sales_report_view` filter exactly.
    # Disclosed deviation: this phase's Objective #3 requires cancellation/
    # rejection reasons to be visible in every report a sale appears in: a
    # completed-only queryset can never contain either, since neither
    # status is reachable once a sale is COMPLETED. Broadened to all
    # statuses so the new "Reason" column below is meaningful instead of
    # permanently "—". The completed-only revenue KPI on the Reports page
    # (ReportsView.get()'s own separate `sales_summary` query) is untouched
    # by this — it never called build_sales_report() for that number, so
    # "Total revenue"/"Total transactions" still mean realized revenue only.
    qs = SaleTransaction.objects.select_related("created_by").prefetch_related("items").order_by("-transaction_date")
    start, end = _date_bounds(request)
    category_id = _category_id(request) if category_filtered else None
    if start:
        qs = qs.filter(transaction_date__gte=start.date())
    if end:
        qs = qs.filter(transaction_date__lte=end.date())
    if category_id:
        qs = qs.filter(items__product__category_id=category_id).distinct()

    # "Reason" added alongside "Status" for the same reason (and same §13
    # disclosure) as build_purchase_report()'s own new column, just above.
    headers = ["Invoice", "Date", "Customer", "Items", "Total", "Status", "Reason"]
    rows = [
        [sale.invoice_number, sale.transaction_date, sale.customer_name or "—",
         sale.items.count(), f"{sale.total_amount:.2f}", sale.get_status_display(), sale.display_reason or "—"]
        for sale in qs
    ]
    return "Sales Report", headers, rows


def sales_report_summary(sales_qs):
    agg = sales_qs.aggregate(total_revenue=Sum("total_amount"), total_transactions=Count("id"))
    return {
        "total_revenue": agg["total_revenue"] or Decimal("0"),
        "total_transactions": agg["total_transactions"] or 0,
    }


def sales_status_breakdown(request):
    """Phase 13 Task 4 — replaces the Sales Report panel's raw per-
    transaction table with an aggregate: count + revenue per status,
    across every status (not completed-only, same broadened scope
    build_sales_report() already uses — see that function's own Phase
    8.99c comment), same date_from/date_to filter."""
    qs = SaleTransaction.objects.all()
    start, end = _date_bounds(request)
    if start:
        qs = qs.filter(transaction_date__gte=start.date())
    if end:
        qs = qs.filter(transaction_date__lte=end.date())
    rows = []
    for value, label in SaleStatus.choices:
        agg = qs.filter(status=value).aggregate(count=Count("id"), total=Sum("total_amount"))
        rows.append({"status": value, "label": label, "count": agg["count"] or 0, "total": agg["total"] or Decimal("0")})
    return rows


def sales_daily_revenue(request, default_days=30):
    """Completed-sales revenue per day, for the Sales Report panel's
    chart — same shape dashboard.js's own sales/purchases Chart.js setup
    already reads (labels/values), reused rather than a new chart
    convention. Falls back to the trailing `default_days` days when no
    date filter is set, matching this page's own KPI panel's existing
    "no filter = everything/recent" convention."""
    qs = SaleTransaction.objects.filter(status=SaleStatus.COMPLETED)
    start, end = _date_bounds(request)
    if start:
        qs = qs.filter(transaction_date__gte=start.date())
    if end:
        qs = qs.filter(transaction_date__lte=end.date())
    if not start and not end:
        qs = qs.filter(transaction_date__gte=timezone.localdate() - timedelta(days=default_days))

    daily = qs.values("transaction_date").annotate(total=Sum("total_amount")).order_by("transaction_date")
    return {
        "labels": [row["transaction_date"].strftime("%d %b") for row in daily],
        "values": [float(row["total"]) for row in daily],
    }


def generate_sales_summary_pdf(request):
    """Phase 13 Task 4 — the Sales Report's own PDF export, rebuilt
    around the same aggregate shape the on-page panel now shows (status
    breakdown + the 2 KPIs), replacing what used to be a straight dump
    of build_sales_report()'s per-transaction rows. build_sales_report()
    itself is untouched and still backs the CSV export — Task 4 only
    asked to remove the *detailed* on-page table and its PDF twin, not
    the underlying per-transaction data CSV analysis would still want."""
    summary_qs = SaleTransaction.objects.filter(status=SaleStatus.COMPLETED)
    start, end = _date_bounds(request)
    if start:
        summary_qs = summary_qs.filter(transaction_date__gte=start.date())
    if end:
        summary_qs = summary_qs.filter(transaction_date__lte=end.date())
    summary = sales_report_summary(summary_qs)
    breakdown = sales_status_breakdown(request)

    headers = ["Status", "Transactions", "Total Value"]
    rows = [[b["label"], b["count"], pdf_lib.format_currency(b["total"])] for b in breakdown]

    filters_summary = [
        f"Total revenue (completed): {pdf_lib.format_currency(summary['total_revenue'])}",
        f"Total transactions (completed): {summary['total_transactions']}",
    ]
    date_from, date_to = request.GET.get("date_from"), request.GET.get("date_to")
    if date_from or date_to:
        filters_summary.append(f"Date: {date_from or 'any'} to {date_to or 'any'}")

    return pdf_lib.render_tabular_report(
        filename="sales_report.pdf", title="Sales Report", headers=headers, rows=rows,
        filters_summary=filters_summary,
    )


# -------------------------------------------------------------- 4. Movements

def build_movement_report(request):
    """Reports page's own "Movements" report type (category-filterable,
    via the 9 REPORT_BUILDERS/ReportExportView) AND Movement History's
    dedicated export (MovementHistoryExportView) both call this — the
    former only ever sets `category`, the latter only ever sets
    date_from/date_to/product/movement_type/q (Phase 8.99d), so sharing
    one function is safe: each caller's querystring only carries the
    params it actually uses. `filter_movements()` is the shared date/
    product/type/search logic; `category` stays this function's own,
    since Movement History's own page has no category filter."""
    qs = InventoryMovement.objects.select_related("product", "product__category", "performed_by").order_by("-created_at")
    qs = filter_movements(request, base_qs=qs)
    category_id = _category_id(request)
    if category_id:
        qs = qs.filter(product__category_id=category_id)

    headers = ["Date", "Product", "Type", "Qty Change", "Stock Before", "Stock After", "Reference", "Performed By"]
    rows = [
        [m.created_at.strftime("%Y-%m-%d %H:%M"), m.product.name, m.get_movement_type_display(),
         m.quantity_change, m.stock_before, m.stock_after, f"{m.reference_type} #{m.reference_id}", m.performed_by.full_name]
        for m in qs
    ]
    return "Inventory Movement Report", headers, rows


# ------------------------------------------------------------ 5. Adjustments

def build_adjustment_report(request):
    qs = InventoryAdjustment.objects.select_related("product", "product__category", "requested_by").order_by("-created_at")
    start, end = _date_bounds(request)
    category_id = _category_id(request)
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    if category_id:
        qs = qs.filter(product__category_id=category_id)

    headers = ["Date", "Product", "Type", "Quantity", "Status", "Requested By", "Reason"]
    rows = [
        [a.created_at.strftime("%Y-%m-%d %H:%M"), a.product.name, a.get_adjustment_type_display(),
         a.quantity, a.get_status_display(), a.requested_by.full_name, a.reason]
        for a in qs
    ]
    return "Inventory Adjustment Report", headers, rows


# -------------------------------------------------------- 6/7. Low/Out Stock

def _stock_status_report(request, status, title):
    qs = InventoryRecord.objects.filter(status=status).select_related("product", "product__category", "product__supplier").order_by("product__name")
    category_id = _category_id(request)
    if category_id:
        qs = qs.filter(product__category_id=category_id)

    headers = ["Product", "Category", "Current Stock", "Reorder Level", "Supplier"]
    rows = [
        [r.product.name, r.product.category.name, r.current_stock, r.reorder_level, r.product.supplier.company_name]
        for r in qs
    ]
    return title, headers, rows


def build_low_stock_report(request):
    return _stock_status_report(request, InventoryStatus.LOW_STOCK, "Low Stock Report")


def build_out_of_stock_report(request):
    return _stock_status_report(request, InventoryStatus.OUT_OF_STOCK, "Out of Stock Report")


# -------------------------------------------------------- 8. AI Forecasts

def build_ai_forecast_report(request):
    qs = DemandForecast.objects.select_related("product", "product__category").order_by("-period_start")
    start, end = _date_bounds(request)
    category_id = _category_id(request)
    if start:
        qs = qs.filter(period_start__gte=start.date())
    if end:
        qs = qs.filter(period_start__lte=end.date())
    if category_id:
        qs = qs.filter(product__category_id=category_id)

    headers = ["Product", "Period", "Start", "End", "Forecasted Demand", "Recommended Reorder Qty", "Confidence", "Model Version"]
    rows = [
        [f.product.name, f.get_forecast_period_display(), f.period_start, f.period_end,
         f.forecasted_demand, f.recommended_reorder_qty, f.confidence_score, f.model_version]
        for f in qs
    ]
    return "AI Demand Forecast Report", headers, rows


# ------------------------------------------------- 9. AI Slow-Moving/Dead Stock

def build_ai_classification_report(request):
    qs = InventoryClassification.objects.select_related("product", "product__category").order_by("-classified_at")
    category_id = _category_id(request)
    if category_id:
        qs = qs.filter(product__category_id=category_id)

    headers = ["Product", "Classification", "Turnover Rate", "Last Sold", "Days Since Last Sale", "Recommendation"]
    rows = [
        [c.product.name, c.get_classification_display(), c.turnover_rate,
         c.last_sold_date or "—", c.days_since_last_sale, c.recommendation]
        for c in qs
    ]
    return "AI Slow-Moving & Dead Stock Report", headers, rows


REPORT_BUILDERS = {
    "inventory": build_inventory_report,
    "purchases": build_purchase_report,
    "sales": build_sales_report,
    "movements": build_movement_report,
    "adjustments": build_adjustment_report,
    "low-stock": build_low_stock_report,
    "out-of-stock": build_out_of_stock_report,
    "ai-forecasts": build_ai_forecast_report,
    "ai-classifications": build_ai_classification_report,
}


# ------------------------------------------------------------------ Exporters

def generate_csv_response(headers, rows, filename):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(rows)
    return response


def generate_pdf_response(title, headers, rows, filename, filters_summary=None):
    """`filters_summary` (Phase 8.99d): an optional list of "Label: value"
    strings rendered under the title, above the table — a report of a
    filtered subset that doesn't say what it was filtered by isn't a
    usable record (Movement History's own PDF export is the first user of
    this; the 9 REPORT_BUILDERS callers via ReportExportView don't pass
    it, so their output is byte-for-byte unchanged).

    Phase 13 — delegates to frontend.pdf.render_tabular_report() for the
    actual document (shared header/footer/style with every other PDF in
    the system now, plus real "Page N of M" and a repeating table
    header); this function's own signature is unchanged so every caller
    (ReportExportView, MovementHistoryExportView) needed no changes."""
    return pdf_lib.render_tabular_report(
        filename=filename, title=title, headers=headers, rows=rows, filters_summary=filters_summary,
    )


# ------------------------------------------------- Per-record PDFs (Phase 8.98d,
# rebuilt Phase 13 on frontend/pdf.py's shared document structure)
# Individual Purchase Order / Sale Transaction / Stock Adjustment downloads
# — distinct from the 9 whole-report exports above (untouched by this
# section). generate_adjustment_pdf is new in Phase 13: no per-adjustment
# document existed before (only the whole-Adjustments report table did).

_PO_STATUS_VARIANT = {
    POStatus.DRAFT: "slate", POStatus.PENDING: "warning", POStatus.APPROVED: "success",
    POStatus.PARTIAL: "warning", POStatus.RECEIVED: "success",
    POStatus.REJECTED: "danger", POStatus.CANCELLED: "danger",
}
_SALE_STATUS_VARIANT = {
    SaleStatus.DRAFT: "slate", SaleStatus.PENDING: "warning", SaleStatus.COMPLETED: "success",
    SaleStatus.REJECTED: "danger", SaleStatus.CANCELLED: "danger",
}
_ADJUSTMENT_STATUS_VARIANT = {
    AdjustmentStatus.PENDING: "warning", AdjustmentStatus.APPROVED: "success", AdjustmentStatus.REJECTED: "danger",
}
_WATERMARK_STATUSES = {POStatus.REJECTED, POStatus.CANCELLED, SaleStatus.REJECTED, SaleStatus.CANCELLED, AdjustmentStatus.REJECTED}


def _approver_signature(approved_by, approved_at, level_label=None):
    """§ Task 3's own instruction: "a document approved under an
    admin-only policy should show the admin as approver." Neither
    PurchaseOrder nor SaleTransaction stores which policy/level resolved
    their approval (only InventoryAdjustment does, via resolved_policy)
    — the approver's own role is always available and is exactly the
    signal that matters here: whoever is shown as "Approved by" already
    passed can_approve() for whatever level this transaction required."""
    if not approved_by:
        return None
    return {
        "role": "Approved by", "name": approved_by.full_name,
        "level": level_label or approved_by.get_role_display(),
        "timestamp": pdf_lib.format_datetime(approved_at),
    }


def generate_purchase_order_pdf(po):
    items = list(po.items.select_related("product").all())
    subtotal, discount_total, tax_total, grand_total = calculate_totals_breakdown(items)

    totals = [("Subtotal", pdf_lib.format_currency(subtotal), False)]
    if discount_total:
        totals.append(("Discount", f"-{pdf_lib.format_currency(discount_total)}", False))
    if tax_total:
        totals.append(("Tax", pdf_lib.format_currency(tax_total), False))
    totals.append(("Grand Total", pdf_lib.format_currency(grand_total), True))

    meta_extra = []
    if po.expected_delivery:
        meta_extra.append(("Expected delivery", pdf_lib.format_date(po.expected_delivery)))
    if po.status in (POStatus.CANCELLED, POStatus.REJECTED) and po.display_reason:
        meta_extra.append(("Reason", po.display_reason))

    signatures = [{
        "role": "Prepared by", "name": po.created_by.full_name,
        "timestamp": pdf_lib.format_date(po.order_date), "level": None,
    }]
    approver_sig = _approver_signature(po.approved_by, po.approved_at)
    if approver_sig:
        signatures.append(approver_sig)

    return pdf_lib.render_document(
        filename=f"{po.po_number}.pdf",
        doc_type_label="Purchase Order", doc_number=po.po_number, issue_date=po.order_date,
        status_label=po.get_status_display(), status_variant=_PO_STATUS_VARIANT.get(po.status, "slate"),
        table_headers=["Product", "SKU", "Ordered", "Received", "Unit Price", "Discount %", "Tax %", "Line Total"],
        table_rows=[
            [item.product.name, item.product.sku, str(item.ordered_qty), str(item.received_qty),
             pdf_lib.format_currency(item.unit_price), f"{item.discount:.1f}%", f"{item.tax:.1f}%",
             pdf_lib.format_currency(item.line_total)]
            for item in items
        ],
        col_widths=[130, 60, 45, 45, 65, 55, 45, 70], col_aligns=["L", "L", "C", "C", "R", "R", "R", "R"],
        party=("Supplier", [
            po.supplier.company_name, po.supplier.contact_person,
            po.supplier.email, po.supplier.phone, po.supplier.address,
        ]),
        meta_extra=meta_extra, totals=totals, signatures=signatures,
        watermark_text=po.get_status_display().upper() if po.status in _WATERMARK_STATUSES else None,
    )


def generate_sale_transaction_pdf(sale):
    items = list(sale.items.select_related("product").all())
    subtotal, discount_total, tax_total, grand_total = calculate_totals_breakdown(items)

    totals = [("Subtotal", pdf_lib.format_currency(subtotal), False)]
    if discount_total:
        totals.append(("Discount", f"-{pdf_lib.format_currency(discount_total)}", False))
    if tax_total:
        totals.append(("Tax", pdf_lib.format_currency(tax_total), False))
    totals.append(("Grand Total", pdf_lib.format_currency(grand_total), True))

    meta_extra = []
    if sale.status in (SaleStatus.CANCELLED, SaleStatus.REJECTED) and sale.display_reason:
        meta_extra.append(("Reason", sale.display_reason))

    signatures = [{
        "role": "Prepared by", "name": sale.created_by.full_name,
        "timestamp": pdf_lib.format_date(sale.transaction_date), "level": None,
    }]
    approver_sig = _approver_signature(sale.approved_by, sale.approved_at)
    if approver_sig:
        signatures.append(approver_sig)

    return pdf_lib.render_document(
        filename=f"{sale.invoice_number}.pdf",
        doc_type_label="Sales Invoice", doc_number=sale.invoice_number, issue_date=sale.transaction_date,
        status_label=sale.get_status_display(), status_variant=_SALE_STATUS_VARIANT.get(sale.status, "slate"),
        table_headers=["Product", "SKU", "Qty", "Unit Price", "Discount %", "Tax %", "Line Total"],
        table_rows=[
            [item.product.name, item.product.sku, str(item.quantity),
             pdf_lib.format_currency(item.unit_price), f"{item.discount:.1f}%", f"{item.tax:.1f}%",
             pdf_lib.format_currency(item.line_total)]
            for item in items
        ],
        col_widths=[150, 65, 40, 65, 55, 45, 75], col_aligns=["L", "L", "C", "R", "R", "R", "R"],
        party=("Bill To", [sale.customer_name or "Walk-in customer"]),
        meta_extra=meta_extra, totals=totals, signatures=signatures,
        watermark_text=sale.get_status_display().upper() if sale.status in _WATERMARK_STATUSES else None,
    )


def generate_adjustment_pdf(adjustment):
    """Phase 13 — new: no per-adjustment document existed before this
    (only the whole-Adjustments report table did). No party block —
    an adjustment isn't transacted with a supplier or customer; this
    project also has no location/warehouse concept anywhere in its
    schema (single-location throughout, confirmed via InventoryRecord
    having no location breakdown), so a fabricated "Location: Main
    Warehouse" line was left out rather than invented. The product and
    reason code stand in its place — what a Stock Adjustment Note
    actually needs to justify is which product moved and why."""
    level_label = None
    if adjustment.resolved_policy:
        level_label = adjustment.resolved_policy.get_required_level_display()

    signatures = [{
        "role": "Requested by", "name": adjustment.requested_by.full_name,
        "timestamp": pdf_lib.format_datetime(adjustment.created_at), "level": None,
    }]
    if adjustment.approved_by:
        signatures.append(_approver_signature(adjustment.approved_by, adjustment.approved_at, level_label))

    meta_extra = [("Reason code", adjustment.get_reason_code_display())]
    if adjustment.status == AdjustmentStatus.REJECTED and adjustment.rejected_reason:
        meta_extra.append(("Rejection reason", adjustment.rejected_reason))

    sign = "+" if adjustment.adjustment_type == "increase" else "-"
    return pdf_lib.render_document(
        filename=f"adjustment_{adjustment.pk}.pdf",
        doc_type_label="Stock Adjustment Note", doc_number=f"ADJ-{adjustment.pk:06d}",
        issue_date=adjustment.created_at, status_label=adjustment.get_status_display(),
        status_variant=_ADJUSTMENT_STATUS_VARIANT.get(adjustment.status, "slate"),
        table_headers=["Product", "SKU", "Type", "Quantity", "Notes"],
        table_rows=[[
            adjustment.product.name, adjustment.product.sku, adjustment.get_adjustment_type_display(),
            f"{sign}{adjustment.quantity}", adjustment.reason,
        ]],
        col_widths=[130, 70, 70, 60, 145], col_aligns=["L", "L", "L", "C", "L"],
        party=None, meta_extra=meta_extra, totals=None, signatures=signatures,
        watermark_text="REJECTED" if adjustment.status == AdjustmentStatus.REJECTED else None,
    )
