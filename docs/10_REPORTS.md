# 📑 Module 10 — Report Generation
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when building any of the 9 report types,
> PDF export with WeasyPrint, or CSV export. All report access is Supervisor+ only
> and must be audit-logged.

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

---

## Common Filter Parameters

All reports accept:
- `date_from` / `date_to` — date range
- `category` — category ID
- `supplier` — supplier ID
- `format` — `pdf` or `csv` (default: HTML preview)

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
| `REPORT_GENERATED` | Any report viewed in browser |
| `REPORT_EXPORTED_PDF` | PDF export downloaded |
| `REPORT_EXPORTED_CSV` | CSV export downloaded |
