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
from django.db.models import Count, Sum

from frontend.models import (
    DemandForecast,
    InventoryAdjustment,
    InventoryClassification,
    InventoryMovement,
    InventoryRecord,
    InventoryStatus,
    PurchaseOrder,
    SaleStatus,
    SaleTransaction,
)


def _date_bounds(request):
    """Common `date_from`/`date_to` GET params (10_REPORTS.md) as
    (start, end) datetimes, or (None, None) if not given. end is set to
    23:59:59 on date_to so `lte` includes the whole day, not just midnight."""
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    start = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    end = datetime.combine(datetime.strptime(date_to, "%Y-%m-%d"), time.max) if date_to else None
    return start, end


def _category_id(request):
    value = request.GET.get("category")
    return int(value) if value and value.isdigit() else None


def _supplier_id(request):
    value = request.GET.get("supplier")
    return int(value) if value and value.isdigit() else None


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

    headers = ["PO Number", "Supplier", "Status", "Order Date", "Expected Delivery", "Total Cost", "Created By"]
    rows = [
        [po.po_number, po.supplier.company_name, po.get_status_display(), po.order_date,
         po.expected_delivery or "—", f"{po.total_cost:.2f}", po.created_by.full_name]
        for po in qs
    ]
    return "Purchase Report", headers, rows


# ------------------------------------------------------------------ 3. Sales

def build_sales_report(request, category_filtered=True):
    qs = SaleTransaction.objects.filter(status=SaleStatus.COMPLETED).select_related("created_by").prefetch_related("items").order_by("-transaction_date")
    start, end = _date_bounds(request)
    category_id = _category_id(request) if category_filtered else None
    if start:
        qs = qs.filter(transaction_date__gte=start.date())
    if end:
        qs = qs.filter(transaction_date__lte=end.date())
    if category_id:
        qs = qs.filter(items__product__category_id=category_id).distinct()

    headers = ["Invoice", "Date", "Customer", "Items", "Total", "Status"]
    rows = [
        [sale.invoice_number, sale.transaction_date, sale.customer_name or "—",
         sale.items.count(), f"{sale.total_amount:.2f}", sale.get_status_display()]
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
    qs = InventoryMovement.objects.select_related("product", "product__category", "performed_by").order_by("-created_at")
    start, end = _date_bounds(request)
    category_id = _category_id(request)
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
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


def generate_pdf_response(title, headers, rows, filename):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), title=title, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

    table_data = [headers] + [[str(cell) for cell in row] for row in rows]
    if not rows:
        table_data.append(["No data available for the selected filters."] + [""] * (len(headers) - 1))

    table = Table(table_data, repeatRows=1)
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
    elements.append(table)
    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
