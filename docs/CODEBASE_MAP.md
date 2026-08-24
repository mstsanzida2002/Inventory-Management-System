# Codebase Map

A navigation guide for this project — where things live, not what's wrong with
them. For history, decisions, and disclosed gaps, read `docs/project_memory.md`
first; this file is the "where do I go" companion to that "why is it like this"
record. Everything below was confirmed by reading the actual files, not guessed
from names — current as of this writing (Phase 14).

---

## 1. Orientation

Stockwell is a Django inventory management system — purchases, sales, stock
adjustments, an approval-authority workflow, AI demand forecasting, dead-stock
classification, PDF documents, and reporting, all served from **one single
Django app called `frontend`** (`config/` is only the project package: settings,
root URLs, WSGI/ASGI). There is no `apps/` split, no `models/` package, no
`services/` package — every backend concern is its own top-level module directly
inside `frontend/` (`models.py`, `services.py`, `views.py`, `approvals.py`,
`pdf.py`, and so on), and every one of those modules is a single flat file, some
of them large (`views.py` is ~2,600 lines, `tests.py` ~6,000). **The one thing
most worth knowing before touching stock**: `frontend/services.py` is the *only*
code path allowed to mutate `InventoryRecord.current_stock` / `Product.current_stock`
or write an `InventoryMovement` row — no view, form, or management command
touches stock directly.

---

## 2. Where to go for what

| I want to... | Go to |
|---|---|
| Change what a model stores | `frontend/models.py` |
| Change how stock actually moves (purchase receipt, sale approval, adjustment) | `frontend/services.py` (`InventoryService`/`PurchaseService`/`SaleService`/`AdjustmentService`) |
| Change a page's HTTP behaviour (GET/POST handling, what gets rendered) | `frontend/views.py` — organised in the same order as `frontend/urls.py`, one class (or a few related classes) per feature |
| Add or change a URL | `frontend/urls.py` (page/action routes) or `frontend/api_urls.py` (the one DRF slice) |
| Change form validation / what fields a create-or-edit form accepts | `frontend/forms.py` |
| Change who is allowed to do something | `frontend/mixins.py` (class-based views) / `frontend/decorators.py` (function-based views) for role gates; `frontend/approvals.py` for the value/reason/variance-based approval-policy engine (who may *approve a specific transaction*, not just who may reach the page) |
| Change a page's markup | `frontend/templates/<feature>/<feature>.html` — see §6 for the full list |
| Change a page's client-side behaviour | `frontend/static/js/<feature>-form.js` or similarly named file — see §5 for which script loads where |
| Change visual styling / design tokens | `frontend/static/css/tokens.css` (colours, spacing, type scale — the source of truth) then `base.css`/`components.css`/`dashboard.css`/`landing.css`/`auth.css` depending on scope, see §4 |
| Change a PDF document's look (header, footer, table style, totals) | `frontend/pdf.py` — every PDF in the system renders through it |
| Change what a specific PDF document contains | `frontend/reports.py` (per-record documents: `generate_purchase_order_pdf`/`generate_sale_transaction_pdf`/`generate_adjustment_pdf`; report-table exports: the `REPORT_BUILDERS` dict and `build_*_report` functions) |
| Change company/admin-configurable settings (name, logo, thresholds, session timeout) | `frontend/models.py`'s `SystemSettings` + `frontend/forms.py`'s `SystemSettingsForm` + `frontend/templates/settings/settings.html` |
| Change audit logging (what gets recorded, the constants) | `frontend/audit.py` |
| Change email/in-app notifications | `frontend/notifications.py` |
| Change the AI demand forecast model or pipeline | `frontend/forecasting.py` |
| Change the slow-moving/dead-stock classification logic | `frontend/classification.py` |
| Change the read-only API (`/api/v1/...`) | `frontend/api_views.py` + `frontend/serializers.py` + `frontend/permissions.py` |
| Seed or reset local dev data | `frontend/management/commands/seed_dev_data.py` (full realistic dataset) / `seed_test_users.py` (the 3 standing verify_admin/verify_super/verify_user accounts) |
| Add a test | `frontend/tests.py` — one file, organised roughly in the order features were built; grep for the class covering the area you're touching before adding a new one |
| Understand *why* something is built the way it is, or what's disclosed-incomplete | `docs/project_memory.md` (history/decisions) and `docs/bugsfound.md` (every bug found, fixed or not) |

---

## 3. Directory structure

```
inventory 3/
├── config/                       Django project package (not an app)
│   ├── settings.py               Single file, no base/dev/prod split. AUTH_USER_MODEL='frontend.User',
│   │                             DATABASES=postgresql, TIME_ZONE='Asia/Dhaka', WhiteNoise for static files.
│   ├── urls.py                   Root URLconf: /admin/, / (frontend.urls, namespace "frontend"),
│   │                             /api/v1/ (frontend.api_urls, namespace "api")
│   └── wsgi.py / asgi.py
│
├── frontend/                     The only Django app — backend + UI both live here
│   ├── models.py                 17 models (16 + ApprovalPolicy) — see §7
│   ├── admin.py                  Django admin registration for every model
│   ├── views.py                  Every HTTP-facing view, ~2,600 lines — see §8
│   ├── forms.py                  Every ModelForm/Form — see §8
│   ├── urls.py                   All page/action routes, one `frontend` namespace
│   ├── api_urls.py / api_views.py / serializers.py / permissions.py
│   │                             The one DRF slice: read-only AI classification/forecast list+summary endpoints
│   ├── services.py               InventoryService/PurchaseService/SaleService/AdjustmentService —
│   │                             the only code path allowed to move stock
│   ├── approvals.py              The approval-policy engine: resolve_required_level()/can_approve(),
│   │                             ABC classification recompute, default-policy seeding
│   ├── pdf.py                    Shared PDF infrastructure — header/footer/style/currency/date,
│   │                             used by every generated document in the system
│   ├── reports.py                The 9 report types (CSV/PDF), Movement History's export,
│   │                             and the 3 per-record PDF documents (PO/Sale/Adjustment)
│   ├── pricing.py                calculate_line_total()/calculate_totals_breakdown() — the one place
│   │                             the unit_price×qty×(1-discount%)×(1+tax%) formula lives
│   ├── classification.py         Slow-moving/dead-stock rule-based classifier
│   ├── forecasting.py            AI demand forecasting pipeline (train/predict/backfill)
│   ├── audit.py                  log_action() + every AuditLog action-name constant
│   ├── notifications.py          notify_user()/notify_supervisors()/notify_admins(), credentials email
│   ├── mixins.py                 Class-based-view RBAC: RoleRequiredMixin/AdminRequiredMixin/
│   │                             SupervisorRequiredMixin/AnyStaffMixin
│   ├── decorators.py             Function-based-view RBAC: require_role/admin_required/
│   │                             supervisor_required/staff_required
│   ├── validators.py             StrongPasswordValidator, generate_strong_password(),
│   │                             validate_product_image(), validate_company_logo()
│   ├── apps.py                   Stock Django app config
│   ├── tests.py                  One file, ~6,000 lines, every test in the project
│   ├── migrations/                0001_initial.py through 0012 (one data migration —
│   │                              0007 — everything else is schema)
│   │
│   ├── management/commands/
│   │   ├── seed_dev_data.py      Wipes + reseeds a large, backdated, realistic dataset
│   │   └── seed_test_users.py    Recreates the 3 standing manual-verification accounts (refuses if DEBUG=False)
│   │
│   ├── templates/                See §6 for the full page list
│   │   ├── base.html             Public-site root layout (landing + login + password reset)
│   │   ├── dashboard_base.html   Authenticated-app root layout (every other page) — standalone, does NOT extend base.html
│   │   └── includes/             icons.html (SVG sprite), sidebar.html, topbar_actions.html,
│   │                             navbar.html (public nav), footer.html (public footer), auth_brand.html
│   │
│   └── static/
│       ├── css/                  tokens.css, base.css, components.css, dashboard.css, landing.css, auth.css — see §4
│       └── js/                   28 files — see §5
│
├── docs/                         Specification docs (the ORIGINAL intended design) + project_memory.md + bugsfound.md
│   └── project_memory.md         The authoritative running history — read this for "why", not this file
│
├── media/                        User-uploaded files (product images, profile photos, company logo) — MEDIA_ROOT
├── staticfiles/                  collectstatic output (WhiteNoise-served in production) — not source, don't edit here
├── ai_models/                    Trained forecasting model files (*.joblib), gitignored
├── manage.py
└── requirements.txt
```

---

## 4. CSS — what loads where, in what order

Two independent base layouts, each pulling the same design-token foundation
but diverging after that:

**`base.html`** (landing page, login, password-reset flow):
`tokens.css` → `base.css` → `components.css` → page's own `{% block extra_css %}`
(only `auth.css`, loaded by the 5 auth-flow templates; the landing page adds
nothing here — `landing.css` is loaded by `landing/index.html`'s own
`extra_css` block).

**`dashboard_base.html`** (every authenticated page — does *not* extend
`base.html`, it's a separate full document):
`tokens.css` → `base.css` → `components.css` → `dashboard.css` → page's own
`{% block extra_css %}`.

So `tokens.css`/`base.css`/`components.css` are the shared foundation on *every*
page in the system; `dashboard.css` is authenticated-app-only; `landing.css`
and `auth.css` are each scoped to their one context (public marketing page,
auth flow) and loaded nowhere else.

---

## 5. JavaScript — global vs page-specific

**Loaded on every authenticated page** (from `dashboard_base.html` itself, in
this order): Chart.js (CDN) → `chart-colors.js` → `dashboard.js` →
`row-actions.js` → `notifications.js`.

**Loaded on every public page** (from `base.html`): `main.js` only.

**Everything else is page-specific**, added via that page's own
`{% block extra_js %}`. Confirmed per template:

| Page | Extra scripts it loads |
|---|---|
| `accounts/profile.html` | `modal.js`, `modal-form.js`, `dom-utils.js`, `form-validation.js`, `change-password-form.js` |
| `adjustments/adjustments.html` | `modal.js`, `modal-form.js`, `dom-utils.js`, `form-validation.js`, `adjustment-form.js`, `table-filter.js` |
| `audit/audit_log.html` | `table-filter.js`, `audit-log.js` |
| `categories/categories.html` | `modal.js`, `modal-form.js`, `dom-utils.js`, `form-validation.js`, `category-form.js` |
| `intelligence/forecasting.html` | `row-actions.js`, `table-filter.js`, `async-run-button.js`, `forecasting.js` |
| `intelligence/slow_moving.html` | `row-actions.js`, `table-filter.js`, `async-run-button.js`, `slow-moving.js` |
| `inventory/inventory.html` | `table-filter.js`, `inventory.js` |
| `inventory/movement_history.html` | *(none — global set only)* |
| `products/products.html` | `modal.js`, `modal-form.js`, `dom-utils.js`, `form-validation.js`, `table-filter.js`, `product-form.js` |
| `purchases/purchases.html` | `modal.js`, `modal-form.js`, `dom-utils.js`, `form-validation.js`, `table-filter.js`, `line-items.js`, `purchase-form.js` |
| `sales/sales.html` | `modal.js`, `modal-form.js`, `dom-utils.js`, `form-validation.js`, `table-filter.js`, `line-items.js`, `sale-form.js` |
| `suppliers/suppliers.html` | `modal.js`, `modal-form.js`, `dom-utils.js`, `form-validation.js`, `table-filter.js`, `supplier-form.js` |
| `users/users.html` | `modal.js`, `modal-form.js`, `dom-utils.js`, `form-validation.js`, `table-filter.js`, `user-form.js` |
| `settings/settings.html` | `form-validation.js`, `settings-form.js` |
| `settings/approval_policies.html` | `modal.js`, `modal-form.js`, `dom-utils.js`, `form-validation.js`, `row-actions.js`, `approval-policy-form.js` |
| `reports/reports.html` | `table-filter.js`, `reports.js` |
| `dashboard/dashboard.html`, `notifications/notifications.html` | *(none — global set only)* |
| `landing/index.html` | *(none — `main.js` only, from `base.html`)* |

Shared helper scripts worth knowing: `modal.js` (open/close mechanics)
+ `modal-form.js` (wires a form inside a modal to validation + a submit
handler) are the pair every add/edit modal on the site uses — never a
one-off modal implementation. `dom-utils.js` and `form-validation.js` are
small shared primitives those and other scripts build on. `table-filter.js`
is the shared client-side list-filtering helper used by most list pages.
`row-actions.js` is the shared "POST an action, then reload/report result"
helper for pill-button row actions (approve/reject/deactivate/etc.).

---

## 6. Templates, by feature area

| Feature | Template(s) |
|---|---|
| Public landing page | `landing/index.html` |
| Auth | `accounts/login.html`, `accounts/profile.html`, `registration/password_reset_*.html` (4 templates + 1 email) |
| Dashboard | `dashboard/dashboard.html` |
| Products / Categories / Suppliers | `products/products.html`, `categories/categories.html`, `suppliers/suppliers.html` |
| Purchases / Sales | `purchases/purchases.html`, `sales/sales.html` |
| Inventory | `inventory/inventory.html`, `inventory/movement_history.html` |
| Adjustments | `adjustments/adjustments.html` |
| AI features | `intelligence/forecasting.html`, `intelligence/slow_moving.html` |
| Reports | `reports/reports.html` |
| Notifications | `notifications/notifications.html` |
| Users & Roles | `users/users.html` |
| Audit Log | `audit/audit_log.html` |
| Settings | `settings/settings.html`, `settings/approval_policies.html` (+ its shared field partial `settings/_approval_policy_fields.html`) |
| Shared partials | `includes/icons.html` (the SVG icon sprite — every icon in the app is a `<symbol>` here, referenced via `<use href="#icon-name">`), `includes/sidebar.html`, `includes/topbar_actions.html`, `includes/navbar.html` (public-site nav), `includes/footer.html` (public-site footer), `includes/auth_brand.html` |

---

## 7. Models (`frontend/models.py`)

`TimeStampedModel` is the abstract base (`created_at`/`updated_at`) every
concrete model except `AuditLog` inherits from (`AuditLog` is deliberately
plain — it has its own `timestamp` field and overrides `save()`/`delete()` to
refuse updates/deletes, since an audit trail must be append-only).

17 concrete models: `User`, `Category`, `Supplier`, `Product`, `PurchaseOrder`,
`PurchaseOrderItem`, `SaleTransaction`, `SaleItem`, `InventoryRecord`,
`InventoryMovement`, `InventoryAdjustment`, `DemandForecast`,
`InventoryClassification`, `Notification`, `AuditLog`, `SystemSettings`,
`ApprovalPolicy`.

---

## 8. Views and forms — organisation

`frontend/views.py` is laid out in the same order as `frontend/urls.py` —
auth/profile first, then dashboard, then one section per feature (Products →
Categories → Suppliers → Purchases → Sales → Inventory/Movements →
Adjustments → AI forecasting/classification → Reports → Notifications →
Users → Audit Log → Settings → Approval Policies), each as one or a small
cluster of `View` subclasses (list+create combined, then separate
update/deactivate/reactivate/delete/export/pdf classes per feature, where
those actions exist for it). A handful of module-level helper functions
(prefixed `_`, e.g. `_dashboard_date_buckets`, `_product_ids_with_history`)
sit just above the view class(es) that use them.

`frontend/forms.py` has one `ModelForm` (or plain `Form`) per feature that
needs one: `ProductForm`, `CategoryForm`, `SupplierForm`, `PurchaseOrderForm`,
`SaleTransactionForm`, `AdjustmentForm`, `UserForm`, `SystemSettingsForm`,
`ApprovalPolicyForm`, plus the small shared `ReasonForm` (reject/cancel
reason text, reused across Purchases/Sales/Adjustments).

---

## 9. A file whose purpose wasn't obvious from its name alone

`frontend/pricing.py` — despite the generic name, it holds exactly two
functions: `calculate_line_total()` (the shared discount/tax formula every
purchase/sale line item uses) and `calculate_totals_breakdown()` (reconstructs
a Subtotal/Discount/Tax/Grand-Total split for PDF totals blocks, since the
item models only ever persist the final `line_total`, never the breakdown).
Confirmed by reading it, not assumed from the name.
