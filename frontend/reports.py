import csv
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.http import HttpResponse
from django.db.models import Count, Q, Sum
from django.utils import timezone

from frontend import pdf as pdf_lib
from frontend.classification import capital_at_risk
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
    # Assumption: end is 23:59:59 on date_to -- lte includes the whole day.
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
    """Shared date/product/type/search filter for the page and its export."""
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

    # Rule: Reason shows the cancelled or rejected reason, whichever applies.
    headers = ["PO Number", "Supplier", "Status", "Order Date", "Expected Delivery", "Total Cost", "Created By", "Reason"]
    rows = [
        [po.po_number, po.supplier.company_name, po.get_status_display(), po.order_date,
         po.expected_delivery or "—", f"{po.total_cost:.2f}", po.created_by.full_name, po.display_reason or "—"]
        for po in qs
    ]
    return "Purchase Report", headers, rows


def build_sales_report(request, category_filtered=True):
    # Rule: all statuses -- Reason needs cancelled/rejected rows too.
    qs = SaleTransaction.objects.select_related("created_by").prefetch_related("items").order_by("-transaction_date")
    start, end = _date_bounds(request)
    category_id = _category_id(request) if category_filtered else None
    if start:
        qs = qs.filter(transaction_date__gte=start.date())
    if end:
        qs = qs.filter(transaction_date__lte=end.date())
    if category_id:
        qs = qs.filter(items__product__category_id=category_id).distinct()

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
    """Transaction count and revenue per sale status, across all statuses."""
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
    """Completed-sales revenue per day, for the Sales Report chart."""
    qs = SaleTransaction.objects.filter(status=SaleStatus.COMPLETED)
    start, end = _date_bounds(request)
    if start:
        qs = qs.filter(transaction_date__gte=start.date())
    if end:
        qs = qs.filter(transaction_date__lte=end.date())
    # Assumption: no filter set -- falls back to the trailing default_days.
    if not start and not end:
        qs = qs.filter(transaction_date__gte=timezone.localdate() - timedelta(days=default_days))

    daily = qs.values("transaction_date").annotate(total=Sum("total_amount")).order_by("transaction_date")
    return {
        "labels": [row["transaction_date"].strftime("%d %b") for row in daily],
        "values": [float(row["total"]) for row in daily],
    }


def generate_sales_summary_pdf(request):
    """Sales Report PDF: a status-breakdown aggregate, not a transaction dump."""
    # Rule: CSV stays the detailed dump -- only the PDF shape is aggregate.
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

    generated_by = request.user.full_name if request.user.is_authenticated else None
    return pdf_lib.render_tabular_report(
        filename="sales_report.pdf", title="Sales Report", headers=headers, rows=rows,
        filters_summary=filters_summary, generated_by=generated_by,
    )


def build_movement_report(request):
    """Shared by the Reports page's export and Movement History's own export."""
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


def build_ai_classification_report(request):
    qs = InventoryClassification.objects.select_related("product", "product__category").order_by("-classified_at")
    category_id = _category_id(request)
    if category_id:
        qs = qs.filter(product__category_id=category_id)

    stock_by_product = dict(InventoryRecord.objects.values_list("product_id", "current_stock"))
    ranked = [(c, capital_at_risk(c, stock_by_product)) for c in qs]
    # Rule: ranked by capital at risk, not classification recency.
    ranked.sort(key=lambda pair: pair[1] if pair[1] is not None else Decimal("-1"), reverse=True)

    headers = ["Product", "Classification", "Turnover Rate", "Last Sold", "Days Since Last Sale", "Capital at Risk", "Recommendation"]
    rows = [
        [c.product.name, c.get_classification_display(), c.turnover_rate,
         # Edge: renders a dash for a null days_since_last_sale, never "None".
         c.last_sold_date or "—", c.days_since_last_sale if c.days_since_last_sale is not None else "—",
         pdf_lib.format_currency(risk) if risk is not None else "—",
         c.recommendation]
        for c, risk in ranked
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


def generate_csv_response(headers, rows, filename):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(rows)
    return response


def generate_pdf_response(title, headers, rows, filename, filters_summary=None, generated_by=None):
    """Renders a tabular report PDF; filters_summary shows what was filtered."""
    return pdf_lib.render_tabular_report(
        filename=filename, title=title, headers=headers, rows=rows, filters_summary=filters_summary,
        generated_by=generated_by,
    )


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
    # Rule: shows the approver's role -- only Adjustment stores its own policy.
    if not approved_by:
        return None
    return {
        "role": "Approved by", "name": approved_by.full_name,
        "level": level_label or approved_by.get_role_display(),
        "timestamp": pdf_lib.format_datetime(approved_at),
    }


def generate_purchase_order_pdf(po, generated_by=None):
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
        generated_by=generated_by,
    )


def generate_sale_transaction_pdf(sale, generated_by=None):
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
        generated_by=generated_by,
    )


def generate_adjustment_pdf(adjustment, generated_by=None):
    """Stock Adjustment Note; no party block -- not transacted with anyone."""
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
        generated_by=generated_by,
    )
