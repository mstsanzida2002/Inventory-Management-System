# 📑 Module 10 — Report Generation
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when building any of the 9 report types,
> PDF export, or CSV export. All report access is Supervisor+ only
> and must be audit-logged.

> **⚠️ STALE DOC WARNING (2026-09-12, BUG-92 cleanup pass):** this file
> predates the real implementation and describes an app layout
> (`apps/reports/`) and PDF library (WeasyPrint) that were never built —
> the real code lives in `frontend/reports.py` (the 9 `REPORT_BUILDERS`),
> `frontend/pdf.py` (`render_tabular_report()`, built on **reportlab**,
> not WeasyPrint), and `frontend/views.py`'s `ReportsView`/
> `ReportExportView`. Only the **Report Types table**, **Common Filter
> Parameters**, and **Audit Actions** sections below have been corrected
> to match reality as part of this pass. The **Base Report View
> Pattern**, **PDF Generator (WeasyPrint)**, **CSV Generator**, and **URL
> Configuration** code blocks below are all fabricated/aspirational and
> were out of scope for this pass — do not copy them; read the real
> files instead.

---

## Requirements Coverage
`REQ 12.1 → 12.15`

---

## Report Types

| # | Report | Model Source |
|---|---|---|
| 1 | Inventory Report | `InventoryRecord` + `Product` |
| 2 | Purchase Report | `PurchaseOrder` + `PurchaseOrderItem` |
| 3 | Sales Report | `SaleTransaction` + `SaleItem` |
| 4 | Inventory Movement Report | `InventoryMovement` |
| 5 | Inventory Adjustment Report | `InventoryAdjustment` |
| 6 | Low Stock Report | `InventoryRecord` (status=low_stock) |
| 7 | Out of Stock Report | `InventoryRecord` (status=out_of_stock) |
| 8 | AI Demand Forecast Report | `DemandForecast` |
| 9 | AI Slow-Moving & Dead Stock Report | `InventoryClassification` |

**Sales Report note:** PDF and CSV intentionally differ in shape — CSV
is the detailed per-transaction dump (`build_sales_report()`), PDF is a
status-breakdown aggregate (`generate_sales_summary_pdf()`), a disclosed
decision (see `docs/bugsfound.md`), not a bug.

**Reports page note (BUG-92, 2026-09-12):** the Reports page
(`frontend/templates/reports/reports.html`) renders all 9 reports as
plain PDF/CSV download cards, all nine structurally identical (icon,
heading, one-line description, PDF + CSV anchor links) — there is no
per-report HTML preview on this page, for any report, and (as of
2026-09-12) no per-card filter UI either. Sales and Low Stock briefly
carried their own filter inputs (date range + category for Sales,
category for Low Stock) directly on the card; removed the same day for
visual consistency with the other 7 cards — see the gap noted under
**Common Filter Parameters** below.

---

## Common Filter Parameters

Not all reports accept all of these — this list is the union across
all 9 builders, not a guarantee for any one of them:
- `date_from` / `date_to` — date range (accepted by Sales; Low Stock
  and Out of Stock are point-in-time snapshots and don't take a date
  range)
- `category` — category ID (accepted by Sales, Low Stock)
- `supplier` — supplier ID
- `format` — `pdf` or `csv` (required; there is no HTML-preview mode —
  every report is a direct file download)

**Known gap, deliberate, not a bug:** none of the 9 cards on the
Reports page expose any filter UI — `build_inventory_report()` and
`build_purchase_report()` accept `category`/`supplier`, and
`build_sales_report()`/`build_low_stock_report()` accept
`date_from`/`date_to`/`category` (per above), all in `frontend/reports.py`,
but no card lets a user set any of them. Sales and Low Stock briefly
(2026-09-12) exposed their own filter inputs directly on the card;
removed the same day because a filtered card was visibly wider/taller
than its neighbours, breaking the uniform grid — visual consistency
won over in-card filtering. Every param above still works for a direct
URL request (`?date_from=...&category=...`); this is a deliberate UI
choice, not a rediscoverable gap. See `docs/project_memory.md`.

---

## Base Report View Pattern

```python
# apps/reports/views.py
from django.shortcuts import render
from django.http import HttpResponse
from apps.rbac.decorators import supervisor_required
from apps.audit.services import log_action

@supervisor_required
def sales_report_view(request):
    from apps.sales.models import SaleTransaction
    from django.db.models import Sum, Count

    qs = SaleTransaction.objects.filter(status='completed').select_related('created_by')

    date_from = request.GET.get('date_from')
    date_to   = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(transaction_date__gte=date_from)
    if date_to:
        qs = qs.filter(transaction_date__lte=date_to)

    summary = qs.aggregate(
        total_revenue=Sum('total_amount'),
        total_transactions=Count('id'),
    )

    export_format = request.GET.get('format')
    context = {'sales': qs, 'summary': summary, 'date_from': date_from, 'date_to': date_to}

    log_action(request.user, 'REPORT_GENERATED', 'reports',
               details={'report': 'sales', 'format': export_format or 'html'}, status='success', request=request)

    if export_format == 'pdf':
        return generate_pdf('reports/sales_report.html', context, filename='sales_report.pdf')
    elif export_format == 'csv':
        return generate_csv(qs, fields=['invoice_number', 'transaction_date', 'total_amount'],
                            filename='sales_report.csv')
    return render(request, 'reports/sales_report.html', context)
```

---

## PDF Generator (WeasyPrint)

```python
# apps/reports/generators/pdf.py
from django.template.loader import render_to_string
from django.http import HttpResponse
import weasyprint

def generate_pdf(template_name, context, filename='report.pdf'):
    html_string = render_to_string(template_name, context)
    pdf = weasyprint.HTML(string=html_string).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
```

---

## CSV Generator

```python
# apps/reports/generators/csv_export.py
import csv
from django.http import HttpResponse

def generate_csv(queryset, fields, filename='report.csv'):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([f.replace('_', ' ').title() for f in fields])
    for obj in queryset:
        row = []
        for field in fields:
            value = obj
            for part in field.split('__'):
                value = getattr(value, part, '')
            row.append(value)
        writer.writerow(row)
    return response
```

---

## URL Configuration

```python
# apps/reports/urls.py
from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('inventory/', views.inventory_report_view, name='inventory'),
    path('purchases/', views.purchase_report_view, name='purchases'),
    path('sales/', views.sales_report_view, name='sales'),
    path('movements/', views.movement_report_view, name='movements'),
    path('adjustments/', views.adjustment_report_view, name='adjustments'),
    path('low-stock/', views.low_stock_report_view, name='low_stock'),
    path('out-of-stock/', views.out_of_stock_report_view, name='out_of_stock'),
    path('ai-forecasts/', views.ai_forecast_report_view, name='ai_forecasts'),
    path('ai-classifications/', views.ai_classification_report_view, name='ai_classifications'),
]
```

---

## Audit Actions

| Action | Triggered When |
|---|---|
| `REPORT_GENERATED` | **Removed, permanently unreachable (BUG-92, 2026-09-12).** Used to fire unconditionally on every GET of the Reports page for the Sales/Low Stock preview panels, regardless of whether anyone exported anything — false data, not just noise. Those panels are gone; nothing calls this action anymore. See `docs/bugsfound.md`. |
| `REPORT_EXPORTED_PDF` | A PDF is actually downloaded via `ReportExportView` |
| `REPORT_EXPORTED_CSV` | A CSV is actually downloaded via `ReportExportView` |
