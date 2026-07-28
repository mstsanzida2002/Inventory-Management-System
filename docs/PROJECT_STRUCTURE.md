# 🏗️ Project Structure
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when scaffolding the project, creating new apps,
> or understanding where any file should live.

---

## Full Directory Layout

```
ai-inventory-system/
│
├── config/                             # Django project config (not an app)
│   ├── __init__.py                     # imports celery app
│   ├── celery.py                       # Celery app initialization
│   ├── urls.py                         # Root URL conf
│   ├── wsgi.py
│   └── settings/
│       ├── __init__.py
│       ├── base.py                     # Shared settings
│       ├── development.py              # Dev overrides (DEBUG=True, console email)
│       └── production.py              # Prod overrides (WhiteNoise, secure cookies)
│
├── apps/                               # All Django applications live here
│   │
│   ├── authentication/                 # Login, logout, password reset, sessions
│   │   ├── __init__.py
│   │   ├── views.py                    # LoginView, LogoutView, PasswordResetView
│   │   ├── forms.py                    # LoginForm, PasswordResetForm
│   │   ├── urls.py
│   │   └── tests.py
│   │
│   ├── users/                          # Custom User model + user management
│   │   ├── __init__.py
│   │   ├── models.py                   # User model (extends AbstractBaseUser)
│   │   ├── serializers.py
│   │   ├── views.py                    # CRUD for users (admin only)
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── tests.py
│   │
│   ├── rbac/                           # Permission logic (no models needed)
│   │   ├── __init__.py
│   │   ├── permissions.py              # Custom DRF permission classes
│   │   ├── decorators.py              # @require_role() view decorators
│   │   └── mixins.py                   # RoleRequiredMixin for class-based views
│   │
│   ├── products/                       # Products + Categories
│   │   ├── __init__.py
│   │   ├── models.py                   # Product, Category
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── tests.py
│   │
│   ├── suppliers/
│   │   ├── __init__.py
│   │   ├── models.py                   # Supplier
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── tests.py
│   │
│   ├── purchases/
│   │   ├── __init__.py
│   │   ├── models.py                   # PurchaseOrder, PurchaseOrderItem
│   │   ├── serializers.py
│   │   ├── views.py                    # Includes approve/reject/receive actions
│   │   ├── urls.py
│   │   ├── signals.py                  # Post-receive → trigger inventory update
│   │   └── tests.py
│   │
│   ├── sales/
│   │   ├── __init__.py
│   │   ├── models.py                   # SaleTransaction, SaleItem
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── signals.py                  # Post-sale → trigger inventory deduction
│   │   └── tests.py
│   │
│   ├── inventory/
│   │   ├── __init__.py
│   │   ├── models.py                   # InventoryRecord, InventoryMovement
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── services.py                 # Core inventory logic (update_stock, check_levels)
│   │   └── tests.py
│   │
│   ├── adjustments/
│   │   ├── __init__.py
│   │   ├── models.py                   # InventoryAdjustment
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── tests.py
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── forecasting/
│   │   │   ├── __init__.py
│   │   │   ├── models.py               # DemandForecast (DB results storage)
│   │   │   ├── pipeline.py             # Scikit-learn training + prediction logic
│   │   │   ├── tasks.py                # Celery tasks: run_forecast, retrain_model
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   └── tests.py
│   │   └── classification/
│   │       ├── __init__.py
│   │       ├── models.py               # InventoryClassification
│   │       ├── classifier.py           # Classification logic + business rules
│   │       ├── tasks.py                # Celery tasks: run_classification
│   │       ├── serializers.py
│   │       ├── views.py
│   │       └── tests.py
│   │
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── views.py                    # Role-specific dashboard views
│   │   ├── urls.py
│   │   └── api_views.py               # DRF views for chart data endpoints
│   │
│   ├── reports/
│   │   ├── __init__.py
│   │   ├── views.py                    # 9 report views + export handlers
│   │   ├── urls.py
│   │   ├── generators/
│   │   │   ├── pdf.py                  # PDF generation with WeasyPrint
│   │   │   └── csv_export.py           # CSV generation
│   │   └── tests.py
│   │
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── models.py                   # Notification
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── services.py                 # notify_user(), send_email_notification()
│   │   └── tasks.py                    # Celery async email tasks
│   │
│   ├── audit/
│   │   ├── __init__.py
│   │   ├── models.py                   # AuditLog (read-only)
│   │   ├── serializers.py
│   │   ├── views.py                    # Read-only list view (admin only)
│   │   ├── urls.py
│   │   └── services.py                 # log_action() utility function
│   │
│   └── settings_manager/
│       ├── __init__.py
│       ├── models.py                   # SystemSettings (singleton)
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       └── tests.py
│
├── templates/                          # All Django HTML templates
│   ├── base.html                       # Master layout (Bootstrap 5 navbar, sidebar)
│   ├── partials/
│   │   ├── _sidebar.html
│   │   ├── _navbar.html
│   │   ├── _notifications_dropdown.html
│   │   └── _messages.html
│   ├── auth/
│   │   ├── login.html
│   │   ├── password_reset.html
│   │   └── password_reset_confirm.html
│   ├── dashboard/
│   │   ├── admin_dashboard.html
│   │   ├── supervisor_dashboard.html
│   │   └── staff_dashboard.html
│   ├── products/
│   │   ├── list.html
│   │   ├── detail.html
│   │   └── form.html
│   ├── purchases/
│   │   ├── list.html
│   │   ├── detail.html
│   │   ├── form.html
│   │   └── receive.html
│   ├── sales/
│   │   ├── list.html
│   │   ├── detail.html
│   │   ├── form.html
│   │   └── invoice.html
│   ├── inventory/
│   │   ├── list.html
│   │   ├── movement_history.html
│   │   └── low_stock.html
│   ├── reports/
│   │   └── [report_type].html
│   ├── notifications/
│   │   └── list.html
│   └── audit/
│       └── list.html
│
├── static/
│   ├── css/
│   │   └── custom.css
│   ├── js/
│   │   ├── dashboard_charts.js         # Chart.js initialization
│   │   ├── barcode_scanner.js
│   │   └── notifications.js            # Polling for new notifications
│   └── images/
│       └── logo.png
│
├── media/                              # User uploads (product images, company logo)
│   └── products/
│
├── staticfiles/                        # collectstatic output (gitignored)
│
├── tests/                              # Project-level test utilities
│   ├── factories.py                    # factory_boy factories for all models
│   └── fixtures/
│       └── initial_settings.json
│
├── .env                                # Secret config (gitignored)
├── .env.example                        # Template for .env
├── .gitignore
├── manage.py
├── requirements.txt
├── Procfile                            # Render deployment
└── README.md
```

---

## App Creation Commands

```bash
# Run from project root
python manage.py startapp authentication apps/authentication
python manage.py startapp users apps/users
python manage.py startapp products apps/products
python manage.py startapp suppliers apps/suppliers
python manage.py startapp purchases apps/purchases
python manage.py startapp sales apps/sales
python manage.py startapp inventory apps/inventory
python manage.py startapp adjustments apps/adjustments
python manage.py startapp dashboard apps/dashboard
python manage.py startapp reports apps/reports
python manage.py startapp notifications apps/notifications
python manage.py startapp audit apps/audit
python manage.py startapp settings_manager apps/settings_manager

# AI sub-apps (create manually, no startapp needed)
mkdir -p apps/ai/forecasting apps/ai/classification
touch apps/ai/__init__.py apps/ai/forecasting/__init__.py apps/ai/classification/__init__.py
```

## App Config Pattern

Each app needs an `AppConfig` pointing to its correct path:

```python
# apps/products/apps.py
from django.apps import AppConfig

class ProductsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.products'             # IMPORTANT: full dotted path
    label = 'products'
```

Each app's `__init__.py`:
```python
default_app_config = 'apps.products.apps.ProductsConfig'
```

---

## URL Registration Pattern

**`config/urls.py`:**

```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.authentication.urls')),
    path('dashboard/', include('apps.dashboard.urls')),
    path('products/', include('apps.products.urls')),
    path('suppliers/', include('apps.suppliers.urls')),
    path('purchases/', include('apps.purchases.urls')),
    path('sales/', include('apps.sales.urls')),
    path('inventory/', include('apps.inventory.urls')),
    path('adjustments/', include('apps.adjustments.urls')),
    path('reports/', include('apps.reports.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('audit/', include('apps.audit.urls')),
    path('settings/', include('apps.settings_manager.urls')),
    # DRF API
    path('api/v1/', include([
        path('auth/', include('apps.authentication.api_urls')),
        path('users/', include('apps.users.urls')),
        path('products/', include('apps.products.api_urls')),
        path('suppliers/', include('apps.suppliers.api_urls')),
        path('purchases/', include('apps.purchases.api_urls')),
        path('sales/', include('apps.sales.api_urls')),
        path('inventory/', include('apps.inventory.api_urls')),
        path('adjustments/', include('apps.adjustments.api_urls')),
        path('ai/', include('apps.ai.forecasting.urls')),
        path('ai/', include('apps.ai.classification.urls')),
        path('dashboard/', include('apps.dashboard.api_urls')),
        path('reports/', include('apps.reports.api_urls')),
        path('notifications/', include('apps.notifications.api_urls')),
        path('audit/', include('apps.audit.api_urls')),
        path('settings/', include('apps.settings_manager.api_urls')),
    ])),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```
