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
"""
import csv
from datetime import datetime, time
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from django.db.models import Count, Q, Sum
from django.utils import timezone

from frontend.models import (
    DemandForecast,
    InventoryAdjustment,
    InventoryClassification,
    InventoryMovement,
    InventoryRecord,
    InventoryStatus,
    MovementType,
    PurchaseOrder,
    SaleStatus,
    SaleTransaction,
)


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


def _styled_data_table(data, repeat_rows=1):
    """The exact Table/TableStyle `generate_pdf_response()` always built
    inline, pulled out so Phase 8.98d's per-record PDFs (below) can reuse
    the same look — same reportlab objects, not a second styling scheme."""
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(data, repeatRows=repeat_rows)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def generate_pdf_response(title, headers, rows, filename, filters_summary=None):
    """`filters_summary` (Phase 8.99d): an optional list of "Label: value"
    strings rendered under the title, above the table — a report of a
    filtered subset that doesn't say what it was filtered by isn't a
    usable record (Movement History's own PDF export is the first user of
    this; the 9 REPORT_BUILDERS callers via ReportExportView don't pass
    it, so their output is byte-for-byte unchanged)."""
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), title=title, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    if filters_summary:
        elements.append(Paragraph("Filters: " + "; ".join(filters_summary), styles["Normal"]))
        elements.append(Spacer(1, 12))

    table_data = [headers] + [[str(cell) for cell in row] for row in rows]
    if not rows:
        table_data.append(["No data available for the selected filters."] + [""] * (len(headers) - 1))

    elements.append(_styled_data_table(table_data))
    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ------------------------------------------------- Per-record PDFs (Phase 8.98d)
# Individual Purchase Order / Sale Transaction downloads — distinct from the
# 9 whole-report exports above (Reports module, untouched by this phase).
# Reuses the exact same reportlab setup: SimpleDocTemplate + getSampleStyleSheet
# + _styled_data_table() (just above) for the line-items grid — no new PDF
# library or rendering mechanism.

def generate_purchase_order_pdf(po):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title=f"Purchase Order {po.po_number}",
                             topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = [Paragraph(f"Purchase Order {po.po_number}", styles["Title"]), Spacer(1, 12)]

    meta_data = [
        ["Field", "Value"],
        ["Supplier", po.supplier.company_name],
        ["Status", po.get_status_display()],
        ["Order Date", str(po.order_date)],
        ["Expected Delivery", str(po.expected_delivery) if po.expected_delivery else "—"],
        ["Created By", po.created_by.full_name],
        # Phase 8.99c — same conditional "—"-fallback pattern the Sale PDF
        # already uses for Approved By/Approved At, just below. Reason
        # covers rejected_reason too (display_reason), not just
        # cancellation, per this phase's Objective #3.
        ["Cancelled By", po.cancelled_by.full_name if po.cancelled_by else "—"],
        ["Cancelled At", str(po.cancelled_at) if po.cancelled_at else "—"],
        ["Reason", po.display_reason or "—"],
    ]
    elements += [_styled_data_table(meta_data), Spacer(1, 16)]

    items = po.items.select_related("product").all()
    headers = ["Product", "SKU", "Ordered Qty", "Received Qty", "Unit Price", "Discount %", "Tax %", "Line Total"]
    rows = [
        [item.product.name, item.product.sku, item.ordered_qty, item.received_qty,
         f"{item.unit_price:.2f}", f"{item.discount:.2f}", f"{item.tax:.2f}", f"{item.line_total:.2f}"]
        for item in items
    ]
    elements.append(_styled_data_table([headers] + rows))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Total Cost: {po.total_cost:.2f}", styles["Heading3"]))

    doc.build(elements)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{po.po_number}.pdf"'
    return response


def generate_sale_transaction_pdf(sale):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title=f"Sale {sale.invoice_number}",
                             topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = [Paragraph(f"Sale {sale.invoice_number}", styles["Title"]), Spacer(1, 12)]

    meta_data = [
        ["Field", "Value"],
        ["Customer", sale.customer_name or "—"],
        ["Status", sale.get_status_display()],
        ["Transaction Date", str(sale.transaction_date)],
        ["Created By", sale.created_by.full_name],
        # Phase 8.99b — a sale now goes through the same approval gate a
        # PO does; not every sale reaches it (draft/pending/rejected/
        # cancelled never set these), so both are conditional, same
        # blank-vs-set pattern the purchases table itself already uses
        # for expected_delivery.
        ["Approved By", sale.approved_by.full_name if sale.approved_by else "—"],
        ["Approved At", str(sale.approved_at) if sale.approved_at else "—"],
        # Phase 8.99c — mirrors the PO PDF's own new rows, just above.
        ["Cancelled By", sale.cancelled_by.full_name if sale.cancelled_by else "—"],
        ["Cancelled At", str(sale.cancelled_at) if sale.cancelled_at else "—"],
        ["Reason", sale.display_reason or "—"],
    ]
    elements += [_styled_data_table(meta_data), Spacer(1, 16)]

    items = sale.items.select_related("product").all()
    headers = ["Product", "SKU", "Quantity", "Unit Price", "Discount %", "Tax %", "Line Total"]
    rows = [
        [item.product.name, item.product.sku, item.quantity,
         f"{item.unit_price:.2f}", f"{item.discount:.2f}", f"{item.tax:.2f}", f"{item.line_total:.2f}"]
        for item in items
    ]
    elements.append(_styled_data_table([headers] + rows))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Total Amount: {sale.total_amount:.2f}", styles["Heading3"]))

    doc.build(elements)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{sale.invoice_number}.pdf"'
    return response
