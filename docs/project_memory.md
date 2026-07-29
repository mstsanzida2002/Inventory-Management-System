# Stockwell — Project Memory

> **Read this file first, before any other document, before writing any code.**
> This file is the permanent engineering memory of the project. It reflects the
> **actual current state of the repository** as of 2026-07-29, updated after
> two work sessions on top of the original snapshot: (1) fixing four
> frontend routing/consistency bugs, and (2) **Backend Phase 1** —
> implementing the full Django ORM schema (16 models + an abstract base)
> matching `docs/SCHEMA.md` field-for-field. Everything else — migrations,
> auth wiring, admin registration, views, API, business logic, AI — is
> still not built; see §2 and §12.
>
> If anything in this file conflicts with the other `docs/*.md` files, **this
> file wins for "what exists today."** The other docs win for "what the
> intended design is" — they are the specification; this file is the as-built
> reality check.

---

## 1. Project Overview

**Purpose.** Stockwell is a planned AI-powered smart inventory management
system: product/category/supplier catalog, purchase order and sales
workflows, real-time inventory tracking with an immutable movement ledger,
supervisor-approved adjustments, role-based access control, audit logging,
and two AI features (demand forecasting via scikit-learn, and rule-based
slow-moving/dead-stock detection). The full design targets three roles
(System Administrator, Inventory Supervisor, Inventory Staff) operating
against a Django REST Framework API consumed by server-rendered templates.

**Current development stage: front-end mock / UI prototype, plus a Phase 1
database schema layer.** The Django ORM models now exist
(`frontend/models.py` — 16 concrete models + a `TimeStampedModel` abstract
base, matching `docs/SCHEMA.md` field-for-field, verified programmatically
— see §6) and `python manage.py check` passes clean. But there are still
**zero migrations**, so no application tables exist in the database,
nothing reads or writes through these models yet, there is no
authentication, no API, no business logic, and no AI implementation.
Everything else is the same complete, polished, static-data Django
template + vanilla-JS/CSS front end as before — every "Add X" button opens
a real modal with real client-side validation, but nothing persists and
nothing computes. Treat this repo as a high-fidelity clickable prototype
sitting on top of an as-yet-unmigrated schema, not a working back end.

**Technology stack — documented (intended) vs. actual (installed):**

| Layer | Documented in `TECH_STACK.md` | Actually in `requirements.txt` / `settings.py` |
|---|---|---|
| Framework | Django 5.x | **Django 6.0.7** (newer than documented) |
| API | DRF 3.15+ | Not installed |
| Database | PostgreSQL 15+ | **SQLite** (`db.sqlite3`, Django default) — schema now exists in code (§6), but **not migrated** |
| Cache/queue | Redis 7+, Celery 5.x | Not installed |
| ML | Scikit-learn 1.4+, Pandas, NumPy | Not installed |
| Auth hashing | `django[argon2]` | Not installed (default PBKDF2 hasher in use) |
| Image handling | (implied by `ImageField`, not separately listed) | **Pillow 12.3.0** — installed in Phase 1; hard-required by `Product.image`, `User.profile_image`, `SystemSettings.company_logo` |
| Static/deploy | WhiteNoise, Gunicorn | Not installed |
| PDF/CSV | ReportLab/WeasyPrint | Not installed |
| Frontend | Bootstrap 5.3, Chart.js 4.x | **No Bootstrap** — hand-built custom CSS design system (`tokens.css`/`base.css`/`components.css`/`dashboard.css`). Chart.js 4.4.4 loaded via CDN, matches doc. |
| Env config | python-decouple | `python-dotenv` (different package, same purpose) |

Installed apps are just the Django defaults plus the single `frontend` app —
none of the 14 apps described in `PROJECT_STRUCTURE.md` (`apps.products`,
`apps.purchases`, `apps.ai.forecasting`, etc.) exist. The 16 models from
`SCHEMA.md` all live in `frontend/models.py` instead (see §6).

**Architecture philosophy actually in force:**
- One Django app (`frontend`) holds everything, models included; views are
  still one-liners: `render(request, "<template>", {"active_nav": "<name>"})`
  and do not yet touch the ORM at all.
- Two independent template roots: `base.html` (public/marketing + auth) and
  `dashboard_base.html` (authenticated app shell) — `dashboard_base.html`
  does **not** extend `base.html` (see §4).
- Strict reuse discipline for the modal/form layer: every "Add X" flow reuses
  the same 4 shared JS modules (`modal.js`, `form-validation.js`,
  `dom-utils.js`, `modal-form.js`) plus a thin per-entity file. This pattern
  was deliberately established and enforced across every module built this
  way (Product, Category, Supplier, Purchase, Sale, Adjustment) — **do not
  break it** (see §18).
- Design tokens (`tokens.css`) are the single source of truth for color,
  spacing, type, radius, shadow, motion — components consume tokens, never
  hardcode raw values.
- For the schema layer: implement documented model code **exactly as
  written**, adapting only what the single-app structure forces (cross-app
  string FK references like `'suppliers.Supplier'` become direct class
  references), and verify field-for-field programmatically rather than by
  eyeballing a diff (see §14/§18).

---

## 2. Current Progress

What is actually built and working:

- ✅ **Database schema (Backend Phase 1)** — all 16 concrete models +
  `TimeStampedModel` abstract base implemented in `frontend/models.py`,
  matching `docs/SCHEMA.md` exactly: every field, relationship, `on_delete`
  behavior, unique constraint, index, and `Meta` option verified
  programmatically via Django shell introspection. `manage.py check` passes
  clean. **Not yet migrated** — zero tables exist for `frontend`, nothing
  reads or writes through these models yet (see §6).
- ✅ **Landing page** (`landing/index.html`) — full marketing page, hero,
  fabricated metrics, animated ticker, features grid, AI teaser section.
  Now uses the shared icon sprite for its feature icons (fixed — see §15).
- ✅ **Login page UI** (`accounts/login.html`) — styled split-panel form,
  password-visibility toggle, now posts to the correct `frontend:login`
  route consistently (routing bug fixed — see §15). ⚠️ Still no real
  Django auth behind it — no migrations, no auth wiring (see §12).
- ✅ **Dashboard shell** (`dashboard_base.html` + `sidebar.html` +
  `topbar_actions.html`) — sidebar nav, topbar search/notifications/user
  menu, all shared across every authenticated page. 5 sidebar links now
  render as disabled (not live-404) — fixed, see §15.
- ✅ **Dashboard page** (`dashboard/dashboard.html`) — KPI cards, Chart.js
  sales/inventory charts, static preview panels.
- ✅ **Product module** — list page + working "Add Product" modal (the
  first one built; the template all later modals copy).
- ✅ **Category module** — grid-card list + working "Add Category" modal.
- ✅ **Supplier module** — list page + working "Add Supplier" modal.
- ✅ **Purchase module** — list page + working "Add Purchase" modal with
  repeatable line-items editor.
- ✅ **Sale module** — list page + working "Add Sale" modal with repeatable
  line-items editor.
- ✅ **Adjustment module** — list page + working "Add Adjustment" modal.
- ✅ **Inventory module (read-only)** — list page only, deliberately **no**
  add/create modal (see §7/§18 — documented as API-driven only, never
  user-created directly).
- ✅ **Demand Forecasting page** (`intelligence/forecasting.html`) — KPI
  cards, trend chart, prediction table with filters, "AI insights" copy,
  reorder-priority panel. All static/mocked; "Run forecast" button just
  plays a loading-spinner animation.
- ✅ **Slow-Moving & Dead Stock page** (`intelligence/slow_moving.html`) —
  KPI cards, classification doughnut chart, filterable table, recommendation
  copy adapted from the documented classifier logic.
- ✅ **Shared modal system** (`modal.js` + `modal-form.js` + CSS) — the
  reusable architecture every "Add X" flow is built on.
- ✅ **Design system** (`tokens.css` + `base.css` + `components.css`) —
  colors, type, spacing, buttons, forms, cards, badges, tables, modals,
  empty states, all token-driven.
- ✅ **Reusable component JS library** — `dom-utils.js`, `form-validation.js`,
  `mock-catalog.js`, `line-items.js`, `table-filter.js`,
  `async-run-button.js`, `chart-colors.js`.

Not built at all (0%):
- ❌ Migrations — no migration files generated yet, so the schema in
  `frontend/models.py` has never touched the database (deliberate — see §16).
- ❌ `AUTH_USER_MODEL` switch — the custom `User` model exists in code but
  Django is still using its own default `auth.User`; nothing is actually
  authenticated through the new model yet (see §5/§12).
- ❌ Admin registration — `frontend/admin.py` is still empty; none of the
  16 models are registered.
- ❌ RBAC enforcement, session logic, real login view
- ❌ Any DRF/API layer
- ❌ Reports module (no page, no route)
- ❌ Notifications module (no page, no route — topbar bell is decorative)
- ❌ Audit log module (no page, no route)
- ❌ Settings module (no page, no route)
- ❌ Users & Roles admin page (no page, no route)
- ❌ Celery/Redis/background jobs
- ❌ Real scikit-learn forecasting model, real classification job
- ❌ Any persistence — every "submit" button either does nothing or
  builds a DOM row client-side; nothing survives a page reload. The models
  existing does not change this yet — nothing calls them.

---

## 3. Folder Structure

```
inventory 3/
├── config/                    Django project package
│   ├── settings.py            Single-file settings (no base/dev/prod split, unlike TECH_STACK.md's documented pattern). AUTH_USER_MODEL still default (not switched — see §5/§12).
│   ├── urls.py                Root URLconf: /admin/, /accounts/ (django.contrib.auth.urls), / (frontend app)
│   ├── wsgi.py / asgi.py
├── frontend/                  The ONLY Django app. Holds both the backend schema and the entire UI.
│   ├── models.py              16 concrete models + TimeStampedModel abstract base (Backend Phase 1), matching docs/SCHEMA.md exactly. NOT yet migrated.
│   ├── admin.py                Still empty — none of the 16 models registered yet
│   ├── views.py               One-line render() functions per page, no business logic, no ORM usage yet
│   ├── urls.py                app_name="frontend"; 12 registered routes (see §5)
│   ├── apps.py / tests.py     Stock Django scaffolding, tests.py unused
│   ├── migrations/             Only __init__.py — models exist but have never been migrated (deliberately deferred to Phase 1b, see §16)
│   ├── templates/
│   │   ├── base.html                  Public-site root layout (landing + login)
│   │   ├── dashboard_base.html        Authenticated-app root layout (all other pages)
│   │   ├── includes/                  Shared partials: icons.html (SVG sprite), sidebar.html, topbar_actions.html, navbar.html (public nav), footer.html (public footer)
│   │   ├── landing/index.html
│   │   ├── accounts/login.html
│   │   ├── dashboard/dashboard.html
│   │   ├── products/products.html
│   │   ├── categories/categories.html
│   │   ├── suppliers/suppliers.html
│   │   ├── purchases/purchases.html
│   │   ├── sales/sales.html
│   │   ├── inventory/inventory.html
│   │   ├── adjustments/adjustments.html
│   │   └── intelligence/forecasting.html, slow_moving.html
│   └── static/
│       ├── css/    tokens.css, base.css, components.css, dashboard.css, landing.css, auth.css
│       └── js/     19 files — see §4/§8 for the full module map
├── docs/                       Specification documents (the INTENDED design — see §12 for gaps/mismatches)
│   ├── INDEX.md, SCHEMA.md, API_CONTRACTS.md, SECURITY.md, TESTING.md,
│   │   TECH_STACK.md, PROJECT_STRUCTURE.md, ENVIRONMENT.md, DEPLOYMENT.md,
│   │   01_AUTH.md, 02_RBAC.md, 03_PRODUCTS.md, 05_PURCHASES.md, 06_SALES.md,
│   │   07_INVENTORY.md, 10_REPORTS.md, 11_NOTIFICATIONS.md, 13_AUDIT.md,
│   │   DEMAND_FORECASTING.md, DEAD_STOCK_DETECTION.md
│   └── project_memory.md       ← this file
├── manage.py
├── requirements.txt             6 packages total — see §1 table (Pillow added in Backend Phase 1)
├── db.sqlite3                   Django's own built-in tables (auth, admin, sessions, contenttypes) are already migrated from initial `startproject` — but zero `frontend` tables (no migrations generated for the new models yet)
├── .env / .env.example
└── .venv/
```

Note the flat `docs/` folder: `INDEX.md` links to files as if they lived in
subfolders (`modules/`, `database/`, `api/`, `security/`, `setup/`, `ai/`,
`testing/`, `deployment/`) — those subfolders **do not exist**. See §12.

---

## 4. Frontend Architecture

**Two independent layout roots — not one shared shell with variants:**

```
base.html                              dashboard_base.html
├── blocks: title, meta_description,   ├── blocks: browser_title, extra_css,
│   extra_css, body_class, content,    │   page_eyebrow, page_title, content,
│   extra_js                          │   extra_js
├── loads: tokens.css, base.css,       ├── loads: tokens.css, base.css,
│   components.css, main.js (defer)   │   components.css, dashboard.css
│                                      ├── includes: icons.html, sidebar.html,
├── landing/index.html                 │   topbar_actions.html
└── accounts/login.html                ├── loads (end of body): Chart.js CDN,
                                        │   chart-colors.js, dashboard.js
                                        └── extended by all 10 authenticated
                                            pages (dashboard, products,
                                            categories, suppliers, purchases,
                                            sales, inventory, adjustments,
                                            forecasting, slow_moving)
```

Every `dashboard_base.html` child page loads Chart.js + `chart-colors.js` +
`dashboard.js` unconditionally, even pages with no charts — `dashboard.js`'s
chart-init functions early-return via `if (!canvas) return`, so this is
inert-but-wasteful on non-chart pages, not broken.

**Reusable includes:**
- `includes/icons.html` — one hidden inline `<svg><defs>` sprite (~35
  `<symbol id="icon-*">`), included by `dashboard_base.html`,
  `accounts/login.html`, and now also `landing/index.html` (fixed — it
  previously inlined its own raw SVGs; see §15). Add new icons here, never
  inline raw SVG markup on a page.
- `includes/sidebar.html` — left nav, present on all 10 dashboard pages.
  Reads `active_nav` context var (default `"dashboard"`). Nav hrefs are
  hardcoded strings, not `{% url %}` tags (the file's own comment
  acknowledges this is a placeholder to fix later). 5 of 15 links
  (Reports, Notifications, Users & Roles, Audit Log, Settings) point to
  routes that don't exist yet; they now render as disabled, non-navigable
  `<span class="nav-item nav-item-disabled">` elements (`aria-disabled`,
  `tabindex="-1"`, `title="Coming soon"`, no `href`) instead of live-404ing
  links — fixed, see §15.
- `includes/topbar_actions.html` — search box (non-functional), notification
  bell (decorative), user menu. Deliberately has no `{% block %}` tags
  (blocks don't resolve through nested includes). Always shows the
  `request.user...|default:"Amara Tenzin"` fallback since there's no real
  auth.
- `includes/navbar.html` / `includes/footer.html` — public marketing
  nav/footer, used only by `landing/index.html`. Both now consistently link
  to `{% url 'frontend:login' %}` (fixed — footer previously pointed to
  `accounts:login`; see §15).

**Modal architecture (the core reusable pattern — read before adding any
new "Add X" flow):**
- `modal.js` → `window.InventoryModal`: generic controller. Handles
  open/close, ESC key, overlay-click-to-close, scroll lock, focus return.
  Dispatches `CustomEvent("modal:open"/"modal:close", {detail:{id}})` on
  `document` so other scripts can react without tight coupling.
- `form-validation.js` → `window.FormValidation`: `getField`,
  `setFieldError`, `clearFieldError`, `validateRequired(field, label)`,
  `validateNonNegative(field, label)`, `focusFirstInvalid(container)`.
- `modal-form.js` → `window.ModalForm.init(config)`: the central controller
  gluing a `<form>` inside a modal to validation + submit/reset handling.
  Config keys: `formId`, `modalId`, `fieldLabels`, `requiredFieldIds`,
  `nonNegativeFieldIds`, `resettableFieldIds`, `onSubmit`, `onReset`,
  `onInit`, `extraValidate` (hook used by Purchase/Sale to also validate
  their line-items editor before allowing submit).
- `dom-utils.js` → `window.DomUtils.buildActionButton(label, iconId)`:
  shared `.pill-btn` builder used when a new table row is appended
  client-side.
- Every entity's "Add X" trigger button carries `data-modal-open="<id>"`;
  the modal markup, the target `<tbody>`/grid container id, and an
  `extra_js` block loading the shared 4 scripts + one thin per-entity file
  (`product-form.js`, `category-form.js`, `supplier-form.js`,
  `purchase-form.js`, `sale-form.js`, `adjustment-form.js`) is the fixed
  recipe. **Follow this recipe exactly for any new create-modal — do not
  invent a new pattern.**
- Purchase and Sale additionally load `mock-catalog.js` (canonical
  product/supplier option lists) and `line-items.js` (repeatable
  product/qty/price/discount/tax row editor,
  `line_total = unitPrice * qty * (1 - discount/100) * (1 + tax/100)`)
  before their own per-entity file.

**Intelligence-page JS (no modal, different pattern):**
- `chart-colors.js` → `window.ChartColors`: hex palette mirroring the CSS
  tokens (Canvas can't read CSS custom properties directly). Extracted from
  what used to be an inline object in `dashboard.js` — reuse this, never
  redefine a local color object in a new page's JS.
- `table-filter.js` → `window.TableFilter.init(config)`: generic
  search+select+segmented-control row filtering against `data-*` attributes
  on `<tr>` elements, toggles an empty-state element via the native
  `hidden` attribute.
- `async-run-button.js` → `window.AsyncRunButton.init(config)`: simulates a
  queued-task loading state (spinner → "done" → revert) for "Run
  forecast"/"Run classification" buttons.
- `forecasting.js` / `slow-moving.js`: thin per-page files wiring the above
  three shared modules plus a Chart.js instance (bar+line combo for
  forecasting trend, doughnut for classification breakdown).

**CSS architecture** (load order: `tokens.css → base.css → components.css →
{page-specific}`):
- `tokens.css` — all design tokens (colors, type, spacing, radius, shadow,
  motion). No breakpoint tokens exist — breakpoints are hardcoded per-file
  raw px values (960/860/720/640/480/900/1180). No z-index scale token —
  z-index is hardcoded per component (modal-overlay 100, site-header 50,
  sidebar 40, topbar 30).
- `base.css` — reset, typography defaults, layout utility classes
  (`.container`, `.flex*`, `.grid*`, `.gap-*`, `.text-*`, `.sr-only`).
- `components.css` — the shared component library: buttons, cards, badges,
  form fields, form grid, modal, line-items grid, empty state, spinner, nav,
  footer. This is the file every new UI element should extend first.
- `dashboard.css` — authenticated shell only: sidebar, topbar, KPI cards,
  panels, widgets, tables, AI-insight sections, plus `.nav-item-disabled`
  (added — dimmed, `cursor: not-allowed`, `pointer-events: none`, for the 5
  not-yet-built sidebar destinations). Declares `--sidebar-w`/`--topbar-h`
  (deliberately not in tokens.css — see inline comment in tokens.css
  warning future authors not to redeclare them there).
- `landing.css` / `auth.css` — page-specific, not reused elsewhere.

---

## 5. Backend Architecture

The schema layer now exists (§6), but nothing else in the backend does —
this section documents what's wired up vs. what's still just Python classes
nothing calls.

- **Apps**: one Django app, `frontend` (`INSTALLED_APPS` also has the
  standard `django.contrib.*` set — admin/auth/contenttypes/sessions/
  messages/staticfiles). None of the 14 apps in `PROJECT_STRUCTURE.md`
  (`apps.products`, `apps.purchases`, `apps.inventory`, `apps.ai.*`, etc.)
  have been created; all 16 SCHEMA.md models live in `frontend/models.py`
  instead, with cross-model references changed from SCHEMA.md's app-label
  strings (`'suppliers.Supplier'`) to direct class references since
  there's only one app.
- **Models**: `frontend/models.py` implements `TimeStampedModel` (abstract)
  plus 16 concrete models — `User`, `Category`, `Supplier`, `Product`,
  `PurchaseOrder`, `PurchaseOrderItem`, `SaleTransaction`, `SaleItem`,
  `InventoryRecord`, `InventoryMovement`, `InventoryAdjustment`,
  `DemandForecast`, `InventoryClassification`, `Notification`, `AuditLog`,
  `SystemSettings` — matching `docs/SCHEMA.md` field-for-field (see §6 for
  the full verification). Included per-model methods that SCHEMA.md writes
  directly inside each class body (custom `UserManager`, `save()` overrides
  for PO/invoice-number generation and line-total calculation, `AuditLog`'s
  immutability enforcement, `SystemSettings.get_settings()`) — see §13 for
  why this reading of "models only" was chosen. **`AUTH_USER_MODEL` in
  `config/settings.py` is still Django's default (`auth.User`)** — the new
  custom `User` model is not yet the active auth model. Switching requires
  resetting `db.sqlite3` first, since `auth`/`admin` migrations are already
  applied against the default user model (confirmed via
  `manage.py showmigrations`); this is a deliberate Phase 1b decision, not
  an oversight (see §12/§16). Because every cross-model FK to a user uses
  `settings.AUTH_USER_MODEL` (exactly as SCHEMA.md specifies) rather than a
  hardcoded string, the switch will resolve correctly with zero model-code
  changes once it happens.
- **Migrations**: none generated yet. `python manage.py showmigrations
  frontend` → `(no migrations)`. Deliberately deferred (task scoping called
  this "Phase 1b").
- **URLs**: `config/urls.py` registers 3 top-level patterns: `/admin/`,
  `/accounts/` (Django's built-in `django.contrib.auth.urls`, namespaced
  `accounts`), and `/` (includes `frontend.urls`, namespaced `frontend`).
  `frontend/urls.py` registers 12 routes, all GET-rendered templates:
  `""` (landing), `login/`, `dashboard/`, `products/`, `categories/`,
  `suppliers/`, `purchases/`, `sales/`, `inventory/`, `adjustments/`,
  `ai/forecasting/`, `ai/slow-moving/`.
- **Views**: every view in `frontend/views.py` is still a one-line
  `render(request, "<template>", {"active_nav": "<name>"})` — no forms, no
  querysets, no auth checks, no POST handling, no ORM usage at all. Models
  existing does not change this; nothing calls them yet.
- **Forms**: no Django Form/ModelForm classes exist. `accounts/login.html`'s
  dead `{% if form.* %}` template conditionals (referencing a `form` object
  the view never passed) were removed — see §15 — since there's still no
  real form/auth wiring to justify keeping them.
- **Services / API**: none exist. `docs/API_CONTRACTS.md` documents 60
  intended DRF endpoints across 11 groups; none are implemented. DRF is not
  even installed.
- **Admin**: `frontend/admin.py` is still empty — none of the 16 new models
  are registered (explicitly out of scope for Backend Phase 1; needed
  before the schema is practically inspectable/seedable — see §16).

---

## 6. Database

- **Actual state**: `db.sqlite3` has Django's own built-in tables (`auth`,
  `admin`, `sessions`, `contenttypes`) already migrated from the initial
  `startproject`. **Zero `frontend` tables exist** — the 16 models in
  `frontend/models.py` have never been migrated (`manage.py showmigrations
  frontend` → `(no migrations)`).
- **Schema implementation status**: **all 16 models implemented in code**,
  verified programmatically (Django shell introspection of
  `model._meta.get_fields()`, `_meta.indexes`, `_meta.db_table`, and each
  FK's `field.remote_field.on_delete`) to match `docs/SCHEMA.md` exactly —
  zero mismatches found on field names, field counts, `db_table` values,
  index counts, or `on_delete` behavior across all 16 models. `manage.py
  check` passes clean.

  | Model | Key fields | Relationships |
  |---|---|---|
  | `User` | username, email, employee_id (all unique), role (admin/supervisor/staff), lockout fields | base for all `created_by`/`performed_by`/`requested_by`/`approved_by` FKs (via `settings.AUTH_USER_MODEL` — not yet the active auth model, see §5) |
  | `Category` | name (unique), is_active | Product FK (PROTECT) |
  | `Supplier` | supplier_name, company_name, email (unique), is_active | Product FK, PurchaseOrder FK (both PROTECT) |
  | `Product` | sku (unique), barcode (unique, nullable), purchase_price, selling_price, reorder_level, current_stock, unit | FK→Category, FK→Supplier (PROTECT) |
  | `PurchaseOrder` | po_number (unique, auto), status (draft/pending/approved/rejected/partial/received/cancelled), total_cost | FK→Supplier, FK→User×2 (created_by/approved_by) |
  | `PurchaseOrderItem` | ordered_qty, received_qty, unit_price, discount, tax, line_total (auto-calc) | FK→PurchaseOrder (CASCADE), FK→Product (PROTECT) |
  | `SaleTransaction` | invoice_number (unique, auto), status (completed/cancelled), total_amount | FK→User (created_by) |
  | `SaleItem` | quantity, unit_price, discount, tax, line_total | FK→SaleTransaction (CASCADE), FK→Product (PROTECT) |
  | `InventoryRecord` | current_stock, reorder_level, status (available/low_stock/out_of_stock), total_value | OneToOne→Product (PROTECT) |
  | `InventoryMovement` | movement_type (purchase/sale/adjustment/return), quantity_change, stock_before/after, reference_type/id — **immutable ledger** | FK→Product, FK→User (performed_by) |
  | `InventoryAdjustment` | adjustment_type (increase/decrease), quantity, reason (required), status (pending/approved/rejected) | FK→Product, FK→User×2 |
  | `DemandForecast` | forecast_period (weekly/monthly), forecasted_demand, recommended_reorder_qty, confidence_score, model_version | FK→Product (CASCADE) |
  | `InventoryClassification` | classification (fast/slow/dead), turnover_rate, days_since_last_sale, recommendation | OneToOne→Product (CASCADE) |
  | `Notification` | type (12 choices), title, message, is_read, is_critical | FK→User (recipient, CASCADE) |
  | `AuditLog` | action, module, affected_id, status, details (JSON), ip_address — **immutable, save()/delete() raise `PermissionError` on update/delete attempts**. Note: does **not** inherit `TimeStampedModel` — it's a plain `models.Model` with its own `timestamp` field instead of `created_at`/`updated_at`, exactly as SCHEMA.md writes it. | FK→User (SET_NULL) |
  | `SystemSettings` | singleton (`get_settings()` → `get_or_create(pk=1)`); default_reorder_level, forecast config, threshold days, session_timeout_seconds, notification toggles | none |

  Documented migration order (per-app, not yet actionable since everything
  is one app now): users → products → suppliers → purchases → sales →
  inventory → adjustments → notifications → audit → settings_manager →
  ai_forecasting → ai_classification. In the current single-app structure
  this collapses to one `makemigrations frontend` (see §16).

- **Redundancies found in SCHEMA.md itself** (implemented literally, not
  fixed — not this session's call to resolve, flagged for whoever owns the
  schema design):
  - `Product.current_stock`/`reorder_level` duplicate
    `InventoryRecord.current_stock`/`reorder_level` with no documented
    relationship between the two (is one a denormalized cache of the
    other? Not explained).
  - Several `unique=True` fields (`User.email`, `Product.sku`,
    `Product.barcode`) also carry a separate `models.Index` on the same
    field — redundant, since a unique constraint already indexes the
    column.
  - `Product.category` and `Product.supplier` both use
    `related_name='products'` — harmless (different reverse-accessor
    hosts, `Category.products` vs `Supplier.products`), but reads like an
    unintentional copy-paste.
  - `InventoryClassification.classified_at` (`auto_now=True`) duplicates
    the inherited `updated_at` from `TimeStampedModel`.
- **Environment fix required to implement as documented**: `User.groups`/
  `user_permissions` (inherited from `PermissionsMixin`) needed explicit
  `related_name` overrides — not in SCHEMA.md's literal text, but required
  because `PermissionsMixin` hardcodes `related_name="user_set"`, which
  clashed with Django's own still-present default `auth.User` (`fields.E304`
  on `manage.py check`). Standard, well-known Django fix; doesn't change
  the DB schema shape (see §13/§18).
- **Pending**: migrations, the `AUTH_USER_MODEL` switch, admin
  registration, seed/fixture data, and all business logic/services layered
  on top (see §16/§17).

---

## 7. AI Features

Both AI pages are polished front-end mocks with **no real model, no real
job, no real data pipeline** behind them. `DemandForecast` and
`InventoryClassification` now exist as Django models in code (§6), but
they're unmigrated and completely unused — the pages below remain 100%
static mocks with no connection to these models yet.

**Demand Forecasting** (`docs/DEMAND_FORECASTING.md`, page at
`/ai/forecasting/`):
- Documented pipeline: `SaleTransaction`+`SaleItem` → pandas DataFrame →
  feature engineering (lag_1..lag_4, rolling avg/std, period_num) →
  scikit-learn model → `DemandForecast` row + low-stock notification.
  Model selection rule: <4 weeks of data → skip; 4–12 weeks →
  `LinearRegression`; >12 weeks → `RandomForestRegressor`. Auto-trains via
  `joblib` if no persisted model file found. Celery Beat: retrain weekly
  (Mon 2am), forecast weekly (Mon 3am).
- Actual implementation: `forecasting.html` shows a static `TREND_DATA`
  object (hardcoded weekly/monthly labels + demand + reorder arrays) driving
  a Chart.js combo chart, a hardcoded 16-row prediction table (8 products ×
  weekly/monthly), and a `#runForecastBtn` that only plays a spinner
  animation via `async-run-button.js` — no computation happens.
- The page's "How this forecast works" panel accurately reproduces the
  documented minimum-data-requirements table as user-facing copy — this is
  the one place the mock explicitly explains, to the viewer, that it's
  describing an unbuilt pipeline.

**Slow-Moving & Dead Stock Detection** (`docs/DEAD_STOCK_DETECTION.md`,
page at `/ai/slow-moving/`):
- Documented logic: rule-based, no ML. `fast` = sold recently + turnover
  above threshold; `slow` = last sold between `slow_moving_threshold_days`
  (default 60) and `dead_stock_threshold_days` (default 180) days ago;
  `dead` = beyond 180 days or never sold. Runs daily via Celery, plus
  reactively after every completed sale via a `post_save` signal.
- Actual implementation: `slow_moving.html` shows a hardcoded 11-row table
  with `data-classification` attributes, a Chart.js doughnut
  (`[1142, 118, 24]` fast/slow/dead), and recommendation text **adapted
  from the actual sentence templates in the documented `classifier.py`**
  (not invented copy) — except the never-sold case, where the doc's
  `days_since = 9999` sentinel is deliberately **not** reproduced verbatim
  ("No recorded sales..." is shown instead of "...9999 days...") since
  leaking an internal sentinel value would look like a bug in a production
  UI. This is a recorded, deliberate deviation — not an oversight.
- A pre-existing inconsistency was found and only partially fixed: the
  older `dashboard/dashboard.html` mock preview table mislabels some items
  against the documented 60/180-day thresholds (e.g., a 142-day-old item
  shown as "Dead stock" when the docs say that's "Slow-moving"). The new
  `slow_moving.html` page uses corrected labels for the same product
  names/day-values; `dashboard.html` itself was left as-is (out of scope
  at the time, still a latent inconsistency — see §12).

**Pending (100% of the real AI work)**: actual model training code, actual
Celery tasks, actually persisting to the now-existing `DemandForecast`/
`InventoryClassification` models (which requires migrations first), actual
signal-based reclassification, everything.

---

## 8. Reusable Components

| Component | File(s) | Used by | Reuse for |
|---|---|---|---|
| Modal controller | `modal.js` | Every "Add X" flow (6 modules) | Any new create/edit modal |
| Form validation | `form-validation.js` | Every "Add X" flow | Any new form needing required/non-negative field checks |
| Modal+form glue | `modal-form.js` | Every "Add X" flow | Any new modal-hosted form (has `extraValidate` hook for custom pre-submit checks) |
| Action-button builder | `dom-utils.js` | Every "Add X" flow (for appending new table rows) | Any client-side row/card insertion |
| Product/supplier catalog | `mock-catalog.js` | Purchase, Sale forms | Any future form needing a product or supplier picker |
| Repeatable line-items editor | `line-items.js` | Purchase, Sale forms | Any future multi-line-item form |
| Chart color palette | `chart-colors.js` | dashboard.js, forecasting.js, slow-moving.js (loaded globally by `dashboard_base.html`) | Any new Chart.js instance — never hardcode chart colors again |
| Generic table filter | `table-filter.js` | Forecasting, Slow-Moving pages | Any future filterable/searchable table with an empty state |
| Async loading-state button | `async-run-button.js` | Forecasting, Slow-Moving "Run" buttons | Any future simulated-async action button |
| SVG icon sprite | `includes/icons.html` | All dashboard-shell pages, login, and now landing (fixed — see §15) | Any new icon — add a `<symbol>` here, don't inline new raw SVGs |
| Sidebar nav | `includes/sidebar.html` | All 10 dashboard pages | N/A — single shared instance, extend its route table when adding a new page |
| Topbar actions | `includes/topbar_actions.html` | All 10 dashboard pages | N/A — single shared instance |
| Design tokens | `tokens.css` | Every stylesheet | Every new color/spacing/type/radius/shadow/motion value |
| Component CSS library | `components.css` | Every page | Buttons, cards, badges, forms, modals, tables, empty states, spinners — extend here before writing page-specific CSS |

**Known duplication not yet refactored**: the line-item `line_total`
formula (`unitPrice * qty * (1 - discount/100) * (1 + tax/100)`) is
implemented three times — once inside `line-items.js`'s internal
recalculation, and once each in `purchase-form.js`/`sale-form.js`'s own
`computeTotal()` display helpers. A future task should extract this into a
single exported `LineItems` calculation helper. (Note: the identical
formula also now exists a fourth time, server-side, in
`PurchaseOrderItem.save()`/`SaleItem` per SCHEMA.md — worth reconciling
once the service layer is built, so client and server never disagree.)

---

## 9. Design System

**Colors** (from `tokens.css`):
- Brand: `--c-ink #10162B`, `--c-ink-soft #232A44`, `--c-indigo #3D4FE0`
  (primary), `--c-indigo-deep #2734A6` (hover), `--c-indigo-tint #EEF0FD`,
  `--c-amber #F2A93B` (AI/insight accent), `--c-amber-tint #FDF1DD`,
  `--c-mist #F5F6FA` (page bg), `--c-white`, `--c-slate #64708A`
  (secondary text), `--c-slate-200 #2d3c66` (borders), `--c-slate-100 #EEF0F5`.
- Status: `--c-success #1FA97A`, `--c-warning #F2A93B` (identical to
  `--c-amber` — same hex, two names), `--c-danger #E14B4B`, plus a
  `-tint` pale variant of each for badge backgrounds.

**Typography**: `--font-display` (Archivo), `--font-body` (Inter),
`--font-mono` (IBM Plex Mono). Size scale `--fs-xs` (12px) through
`--fs-4xl` (60px), 9 steps. Line-heights: tight/snug/normal.

**Spacing**: `--sp-1` (0.25rem) through `--sp-16` (8rem), 10 steps.

**Radius**: sm 8px, md 14px, lg 22px, pill 999px.

**Shadow**: sm/md/lg + a special `--shadow-indigo` for primary-button glow.

**Motion**: `--ease-out`, durations fast/base/slow (150/250/600ms), all
zeroed under `prefers-reduced-motion: reduce`.

**No token exists for breakpoints or z-index** — both are hardcoded
per-file. Worth tokenizing if the design system grows further.

**Component classes** (in `components.css`): buttons (`.btn`,
`.btn-primary`, `.btn-secondary`, `.btn-ghost`, `.btn-block`, `.btn-lg`),
cards (`.card` — **defined but never used anywhere**, `.card-flat` — the
one actually used), badges (`.badge-success/-warning/-danger/-indigo`),
form fields (`.field`, `.input`, `.input.has-error`, `.field-error`,
`.form-label`, `.select-wrap`, `.file-drop*`), form grid (`.form-grid`,
`.field-full`), modal (`.modal-overlay`, `.modal`, `.modal-lg`,
`.modal-header/-body/-footer`), line-items grid, empty state
(`.empty-state*`), spinner (`.spin`), nav item states (`.nav-item`,
`.nav-item.is-active`, `.nav-item-disabled`).

**Known CSS-cascade trap** (fix pattern must be repeated for any new
`[hidden]`-toggled element): any class that sets `display` on an element
(e.g. `.empty-state { display: flex }`, `.file-drop-preview { display:
block }` via the `img,svg{display:block}` base rule) silently beats the
browser's native `[hidden]{display:none}` User-Agent rule, because author
CSS always wins over UA CSS regardless of specificity. **Every class that
might coexist with a `hidden` attribute toggle must have an explicit
`.class[hidden] { display: none; }` override.** This has bitten the project
twice already (`.file-drop-preview`, `.empty-state`) — check for it
whenever adding a new element whose visibility is toggled via `hidden`.

---

## 10. Current Features

**Fully completed (UI + client-side validation, no persistence):**
Landing page, login page UI, dashboard shell + charts, Product/Category/
Supplier/Purchase/Sale/Adjustment "Add" modals, Inventory list (read-only
by design), Demand Forecasting page, Slow-Moving & Dead Stock page.

**Fully completed (schema layer):** all 16 documented models, matching
SCHEMA.md exactly — see §6. Not yet migrated or wired to anything.

**Partially completed:**
- Search/filter controls exist visually on most list pages (Products,
  Suppliers, Purchases, Sales, Inventory, Adjustments) but are **not
  wired** to actually filter the static table rows — only the Intelligence
  pages' filters (`table-filter.js`) actually work.
- Pagination controls exist on several list pages but are non-functional
  (Previous disabled, Next does nothing).
- Approve/reject buttons exist on Purchase/Adjustment pending rows but
  have no click handlers.
- Login form renders and validates client-side, posts to the correct route
  now (`frontend:login`, fixed — see §15), but there's still no real
  Django auth behind it — no migrations, no `AUTH_USER_MODEL` switch, no
  auth view logic.

**Missing entirely**: Reports, Notifications, Audit Log, Users & Roles,
Settings — no pages, no routes, no templates exist for any of these five
modules despite being documented and linked from the sidebar (their
sidebar links are now disabled rather than live-404s — see §15).

---

## 11. Current UI Pages

- ✅ Landing
- ✅ Login (UI only, not functionally wired — see §12)
- ✅ Dashboard
- ✅ Products (list + Add modal)
- ✅ Categories (list + Add modal)
- ✅ Suppliers (list + Add modal)
- ✅ Purchases (list + Add modal, line-items)
- ✅ Sales (list + Add modal, line-items)
- ✅ Inventory (list only, read-only by design)
- ✅ Adjustments (list + Add modal)
- ✅ Demand Forecasting (`/ai/forecasting/`)
- ✅ Slow-Moving & Dead Stock (`/ai/slow-moving/`)
- ⬜ Reports (sidebar link disabled, no route registered)
- ⬜ Notifications (sidebar link disabled, no route registered)
- ⬜ Users & Roles (sidebar link disabled, no route registered)
- ⬜ Audit Log (sidebar link disabled, no route registered)
- ⬜ Settings (sidebar link disabled, no route registered)

---

## 12. Current Problems

**Bugs fixed this cycle** (kept here for traceability, not because they're
still open):
1. ~~Login form posted to the wrong URL namespace~~ — **FIXED.**
   `accounts/login.html`'s form now posts to `{% url 'frontend:login' %}`;
   `includes/footer.html`'s login link was also changed from
   `accounts:login` to `frontend:login` for consistency with `navbar.html`.
2. ~~`accounts/login.html` referenced an undefined `form` object~~ —
   **FIXED.** The dead `{% if form.* %}` conditionals were removed rather
   than fabricating a fake form context, since there's still no real form
   object passed by the view.
3. ~~5 sidebar links 404'd~~ — **FIXED.** Reports, Notifications, Users &
   Roles, Audit Log, Settings now render as disabled `<span>` elements
   (`aria-disabled`, `tabindex="-1"`, no `href`) instead of live dead
   links.
4. ~~`landing/index.html` inlined raw SVGs~~ — **FIXED.** Converted to the
   shared icon sprite (`includes/icons.html`), which the page now also
   includes (it didn't before).

**Open items from Backend Phase 1** (not bugs — `manage.py check` passes
clean — but real decisions/gaps to track):
- **`AUTH_USER_MODEL` still points to Django's default `auth.User`.** The
  new custom `frontend.User` model exists and matches SCHEMA.md, but
  nothing is actually authenticated through it. Switching requires
  resetting `db.sqlite3` first, since `auth`/`admin` migrations are already
  applied against the default user model — deliberately deferred to Phase
  1b (see §16), not forgotten.
- **No migrations generated yet** — `frontend` has zero tables; the schema
  exists only in Python.
- **`frontend/admin.py` still empty** — none of the 16 new models are
  registered, so there's no way to inspect/seed data yet even after
  migrating.

**Technical debt:**
- `line_total` calculation logic duplicated in 3 places on the frontend
  (see §8), and a 4th time server-side in the new `PurchaseOrderItem`/
  `SaleItem` models — worth reconciling once a real service layer exists.
- `.card` CSS class defined in `components.css` but completely unused
  (every real card uses `.card-flat` or a more specific variant instead).
- `MockCatalog.products`/`.suppliers` raw arrays exported but unused
  (only the derived `*OptionsHtml` strings are consumed).
- `LineItems.create()`'s returned `recalculate()` handle is never called
  externally; `TableFilter.init()`'s returned `refresh` handle is never
  captured by either caller; `TableFilter`'s `onFilter` hook is never used.
- `--c-warning` and `--c-amber` tokens are identical hex values under two
  names — consider consolidating.
- No breakpoint or z-index design tokens — both hardcoded ad hoc per file.
- `Product.current_stock`/`reorder_level` duplicate `InventoryRecord`'s
  same-named fields with no documented relationship (see §6).
- Redundant `models.Index` on already-`unique=True` fields (`User.email`,
  `Product.sku`, `Product.barcode`) — implemented literally per SCHEMA.md,
  not fixed (see §6).
- `InventoryClassification.classified_at` duplicates the inherited
  `updated_at` (see §6).

**Unfinished pages**: Reports, Notifications, Audit Log, Users & Roles,
Settings — not started.

**Missing backend**: no migrations (models exist in code only, see §6), no
`AUTH_USER_MODEL` switch, no admin registration, no API, no auth wiring, no
services, no Celery, no AI execution.

**Temporary/mock implementations**: every table on every list page is
hardcoded static HTML rows, not server-rendered from a queryset. "Run
forecast"/"Run classification" buttons only play a fake loading animation.
Search/filter/pagination controls on most pages are decorative.

**Documentation defects** (in `docs/*.md`, not in the app itself):
- `INDEX.md`'s entire "File Map" table links to paths inside subfolders
  (`setup/`, `database/`, `modules/`, `ai/`, `api/`, `security/`,
  `testing/`, `deployment/`) that don't exist — `docs/` is completely flat.
  Every link in that table is broken as written.
- 8 files `INDEX.md` references do not exist on disk at all:
  `MIGRATIONS.md`, `04_SUPPLIERS.md`, `08_ADJUSTMENTS.md`,
  `09_DASHBOARD.md`, `12_SEARCH.md`, `14_SETTINGS.md`, `SERIALIZERS.md`,
  `PERMISSIONS.md`. Any task touching Suppliers, Adjustments, Dashboard,
  Search, Settings, serializer patterns, or DRF permission classes has no
  dedicated spec to read — cross-reference `SCHEMA.md` and
  `API_CONTRACTS.md` instead, and flag the gap rather than inventing rules.
- `dashboard/dashboard.html`'s mock stock-status preview mislabels some
  items against the documented 60/180-day slow/dead thresholds (see §7) —
  never corrected in that file, only in the newer `slow_moving.html`.
- `SCHEMA.md` itself has the field-duplication and redundant-index
  quirks noted in §6 — minor, but worth a pass if the schema doc is ever
  revised.

---

## 13. Architecture Decisions

- **Single `frontend` app instead of the documented 14-app split** — for
  templates originally, now also for models. Because no other backend
  layers exist yet, splitting into `apps.products`, `apps.purchases`, etc.
  now would be premature — there's nothing to separate. Decision: keep one
  app until real services/API are added, then split per
  `PROJECT_STRUCTURE.md` at that point, not before. SCHEMA.md's app-label
  string FK references (`'suppliers.Supplier'`) were changed to direct
  class references to match this single-app reality.
- **Two independent template roots (`base.html` / `dashboard_base.html`)
  instead of one shared shell.** The public marketing/auth pages and the
  authenticated app have genuinely different chrome (no sidebar/topbar on
  landing/login) — forcing them through one base with heavy conditional
  blocks was judged worse than two small, clear roots. Trade-off: some
  duplication of the `<head>` CSS-loading block between the two roots.
- **Vanilla JS, no framework, no bundler.** Matches the "front-end mock,
  no build step" nature of the project and the documented CDN-only
  frontend approach (`TECH_STACK.md` lists CDN Bootstrap/Chart.js, no
  webpack/vite). Script order in `extra_js` blocks is the only dependency
  mechanism — deliberate, not accidental; keep new pages consistent with
  this (see §14).
- **Custom hand-built CSS design system instead of the documented
  Bootstrap 5.3.** The actual visual language (indigo/amber/ink palette,
  custom card/modal/badge styles) diverges significantly from stock
  Bootstrap; building a small token-driven system gave tighter control
  over the "enterprise analytics" look the Intelligence pages needed.
  This is a deliberate, accepted deviation from `TECH_STACK.md` — not an
  oversight, but `TECH_STACK.md` itself was never updated to reflect it.
- **No "Add Inventory Transaction" modal**, unlike every other module.
  Verified against `07_INVENTORY.md` and `API_CONTRACTS.md`: every
  inventory endpoint is documented as GET-only, and `InventoryMovement`
  rows are explicitly described as created only as an internal side effect
  of purchase-receive/sale/adjustment-approval — never via a direct user
  form. Building a create form here would have invented an undocumented
  workflow, so it was deliberately skipped and reported rather than guessed.
- **9999-day sentinel not reproduced verbatim in Slow-Moving UI copy.**
  The documented classifier uses `days_since = 9999` internally for
  never-sold products; showing that number to a user reads as a leaked
  implementation bug in an "enterprise analytics" UI, so
  `slow_moving.html` shows "No recorded sales..." instead. Deliberate,
  disclosed deviation from literal doc-generated text (see §7).
- **Single shared period toggle on the Forecasting page** instead of two
  separate weekly/monthly toggles (one for the chart, one for the table).
  Consolidated into one `#forecastPeriodToggle` driving both, to avoid
  presenting the user with two controls that do the same conceptual thing.
- **Disabled the 5 not-yet-built sidebar links instead of building
  placeholder "Coming soon" pages for them.** Registering 5 real routes
  with fabricated content would have meant inventing UI for undocumented
  pages beyond the fix's scope; a non-navigable, visually dimmed nav item
  honestly represents "this doesn't exist yet" without pretending otherwise.
- **`settings.AUTH_USER_MODEL` used in every FK, without switching it.**
  Written exactly as SCHEMA.md specifies. This keeps the model code
  forward-compatible: once a later phase resets the DB and flips
  `AUTH_USER_MODEL = 'frontend.User'`, every FK resolves to the custom
  model correctly with zero model-code changes needed.
- **Added `related_name` overrides on `User.groups`/`user_permissions`** —
  not in SCHEMA.md's literal text, but required because `PermissionsMixin`
  hardcodes `related_name="user_set"`, which clashes with Django's own
  `auth.User` (still present/loaded since `django.contrib.auth` is a
  required built-in app). This is the standard, well-known Django fix for
  a custom user model coexisting with the default one — it only renames a
  reverse accessor, it does not change the DB schema shape SCHEMA.md
  documents.
- **Included model-level methods that SCHEMA.md writes directly inside
  each model class** (custom `UserManager`, `save()` overrides for
  PO/invoice-number generation and line-total calculation, `AuditLog`'s
  immutability enforcement, `SystemSettings.get_settings()`) even though a
  "models only, exclude business logic/services" scoping was given.
  Interpreted "business logic/services" as referring to the separate
  workflow-service classes described in the other module docs
  (`PurchaseService`, `SaleService`, `InventoryService` — none of which
  live in SCHEMA.md), not the methods SCHEMA.md writes directly inside
  each model. Flagged explicitly in case a stricter, fields-only reading
  was actually intended.
- **Installed Pillow and added it to `requirements.txt`.** `ImageField`
  (used by 3 already-documented fields: `Product.image`,
  `User.profile_image`, `SystemSettings.company_logo`) hard-requires it —
  `manage.py check` fails outright without it (`fields.E210`), it's not an
  optional nice-to-have.

---

## 14. Coding Standards

**Naming conventions:**
- JS shared/reusable modules: `window.PascalCaseNamespace` (e.g.
  `InventoryModal`, `FormValidation`, `ModalForm`, `DomUtils`,
  `MockCatalog`, `LineItems`, `ChartColors`, `TableFilter`,
  `AsyncRunButton`). Thin per-entity JS files (`product-form.js`, etc.)
  expose **no** global — they're self-contained IIFEs that call the shared
  modules' `.init()`.
- Template files: lowercase, matching the URL segment (`products.html` at
  `/products/`).
- CSS custom properties: `--c-*` (color), `--fs-*` (font size), `--sp-*`
  (spacing), `--radius-*`, `--shadow-*`, `--dur-*`/`--ease-*` (motion).
- Python/Django models: `PascalCase` model names, `snake_case` fields,
  `TextChoices` classes named `<Concept>` (e.g. `POStatus`, `UserRole`)
  living directly above the model that uses them, matching SCHEMA.md's
  own layout.

**Folder conventions:** one subfolder per module under both
`templates/<module>/` and (implicitly) grouped JS filenames
`<module>-form.js`; shared/cross-module code lives at the top level of
`static/js/` and `static/css/`, never inside a module's own folder (there
are no per-module JS/CSS folders — everything is flat under `static/js/`
and `static/css/`). Models similarly all live flat in `frontend/models.py`
until/unless the project splits into the documented per-module apps.

**Component rules**: extend `components.css` classes before writing new
page-specific CSS; never redefine a component that already exists there
(e.g. don't create a second modal implementation — extend `.modal`/
`.modal-lg`).

**Reuse rules** (established and enforced across every task this project
has gone through): reuse existing JS/CSS/HTML before writing new; if
duplicate logic is found while adding a feature, refactor it into a shared
module *first*, then build the new feature on top (this is exactly how
`chart-colors.js` and `table-filter.js` came to exist — extracted before
the Intelligence pages were built, not after).

**Modal rules**: every new "Add X" flow must follow the fixed 5-script
recipe (`modal.js → form-validation.js → dom-utils.js → modal-form.js →
<entity>-form.js`, plus `mock-catalog.js`+`line-items.js` if it needs a
product picker or repeatable line items). Never hand-roll a new modal open/
close mechanism.

**JavaScript rules**: IIFE pattern (`(function(){ "use strict"; ... })()`)
for anything not meant to be a shared module; only shared/reusable modules
get a `window.X` export; script load order in `extra_js` blocks is the
only dependency-resolution mechanism (no imports/bundler) — order matters
and must match the dependency table in §4/§8.

**CSS rules**: never hardcode a color/spacing/radius/shadow value that has
a token in `tokens.css`; any element toggled via the `hidden` attribute
must have an explicit `.class[hidden] { display: none; }` rule if its base
class sets `display` (see §9's cascade trap).

**Model verification rule**: when implementing against a documented schema,
verify field names, `on_delete` behavior, `db_table`, and index counts
*programmatically* — via `manage.py shell -c` scripts using
`model._meta.get_fields()`, `_meta.indexes`, `_meta.db_table`, and
`field.remote_field.on_delete` — rather than eyeballing a diff against the
doc. This is how all 16 Backend Phase 1 models were confirmed to match
`docs/SCHEMA.md` exactly, and it's the only way to be confident across
that many models without re-reading the source doc line-by-line every time.

---

## 15. Development Timeline

Git history is uninformative here — the repository has a single commit
("Initial commit: Inventory Management System (Django)") containing the
original snapshot; the actual build order below is reconstructed from
session history, not `git log`:

1. **Product module first** — the "Add Product" modal was built first and
   established the entire reusable modal/validation/JS architecture
   (`modal.js`, `form-validation.js`, `dom-utils.js`, `modal-form.js`)
   that every later module copies.
2. **Modal regression debugged** — an early bug where the modal rendered
   inline below the table instead of as a popup overlay was root-caused
   (a fragile `inset: 0` CSS shorthand) and hardened with explicit
   `top/right/bottom/left` offsets.
3. **Category & Supplier modals** — built by reusing the Product modal
   architecture exactly, no new patterns introduced.
4. **Purchase, Sale, Adjustment forms** — built strictly from
   `SCHEMA.md`/`API_CONTRACTS.md`/module docs; introduced `mock-catalog.js`
   and `line-items.js` as new shared modules (needed by Purchase and Sale
   for their line-item editors); explicitly declined to build an "Add
   Inventory Transaction" form after verifying the docs describe it as
   API-only.
5. **Intelligence module (Demand Forecasting + Slow-Moving & Dead Stock)**
   — Extracted `chart-colors.js` out of `dashboard.js` before writing new
   chart code (dedup-first discipline); built `table-filter.js` and
   `async-run-button.js` as new shared modules; fixed three latent bugs
   found during live verification (multi-line Django `{# #}` comments
   leaking as page text across 4 templates, the `.empty-state[hidden]`
   cascade bug, and `.topbar-title` mobile overflow).
6. **`docs/project_memory.md` created** — the first version of this
   document, capturing the state after the Intelligence module landed
   (frontend-only, zero backend).
7. **Four frontend bugs fixed**: the login form's URL-namespace mismatch
   (now posts to `frontend:login` consistently across the form action,
   navbar, and footer), the dead `form.*` template conditionals in
   `accounts/login.html` (removed), the 5 sidebar links that 404'd (now
   disabled `<span>` elements instead of live dead links), and
   `landing/index.html`'s raw inline SVGs (converted to the shared icon
   sprite, which the page now also includes). Each verified live via
   Playwright against the dev server.
8. **Backend Phase 1: Database Models** — implemented all 16 concrete
   models + the `TimeStampedModel` abstract base in `frontend/models.py`,
   matching `docs/SCHEMA.md` field-for-field, verified programmatically.
   Installed Pillow (required by `ImageField`) and added `related_name`
   overrides on `User.groups`/`user_permissions` to resolve a clash with
   Django's still-present default `auth.User`. Deliberately did not touch
   `AUTH_USER_MODEL`, migrations, admin registration, or any business
   logic — all explicitly out of scope for this phase. `manage.py check`
   passes clean; zero migrations generated (by design).
9. **This document updated** — to reflect both the bug-fix session and
   Backend Phase 1.

---

## 16. Next Priorities

Highest priority first:

1. **Decide and execute the `AUTH_USER_MODEL` switch.** Reset
   `db.sqlite3` (safe — it holds no business data, only Django's own
   default tables) and set `AUTH_USER_MODEL = 'frontend.User'` in
   `config/settings.py` *before* generating any migrations. This must
   happen first: `auth`/`admin` migrations are already applied against
   the default user model and can't be changed after the fact without
   significant pain.
2. **Generate and run migrations (Phase 1b)** for the `frontend` app now
   that the models exist — conceptually one `makemigrations frontend` +
   `migrate` in the current single-app structure (SCHEMA.md's documented
   per-app migration order no longer applies literally).
3. **Register all 16 models in `frontend/admin.py`** so the schema is
   inspectable/seedable through Django admin during backend development.
4. **Reconcile `INDEX.md`'s broken links** — either flatten its paths to
   match the real flat `docs/` layout, or physically move files into the
   subfolders it references. Either is fine; leaving it broken is not.
5. **Write the missing module docs** (`04_SUPPLIERS.md`,
   `08_ADJUSTMENTS.md`, `09_DASHBOARD.md`, `12_SEARCH.md`,
   `14_SETTINGS.md`) or consolidate their content into existing files —
   currently any AI session working on those modules has no dedicated spec.
6. **Wire list pages to real querysets** once migrations exist, replacing
   the static hardcoded `<tr>`/card rows module by module (Products first,
   since its modal architecture is the reference implementation).
7. **Implement the service layer** (`InventoryService`, `PurchaseService`,
   `SaleService`) per the documented business rules before any create-modal
   is allowed to actually persist data — the stock-never-negative and
   approval-workflow invariants must live here, not in views.
8. **Then** real auth views (login/logout wired to the switched
   `AUTH_USER_MODEL`), DRF API layer, RBAC enforcement, Celery/Redis, and
   finally the real AI pipelines (forecasting, classification) — in that
   order, since each layer depends on the one before it.

---

## 17. Future Work

Grouped by module, per the documentation:

- **Database schema**: ✅ **done** (Backend Phase 1, §6) — all 16 models
  implemented matching SCHEMA.md. Still pending: migrations, the
  `AUTH_USER_MODEL` switch, seed data, admin registration (see §16).
- **Auth**: the custom `User` model now exists in code (Phase 1) but isn't
  wired as the active auth model yet. Still needed: `AUTH_USER_MODEL`
  switch + migrations + real login/logout view logic, session timeout,
  account lockout (5 attempts/300s), password reset via email, Argon2
  hashing, profile update.
- **RBAC**: permission classes/decorators/mixins per the 3-role matrix in
  `02_RBAC.md`; template-level role conditionals.
- **Products/Categories**: real CRUD, SKU auto-generation (already coded
  as a `save()` pattern for PO/invoice numbers; Product's SKU generation
  isn't in SCHEMA.md's `Product.save()` — only PO/invoice auto-numbering
  is documented that way, so Product SKU generation would need its own
  documented rule before implementing), soft-delete, image upload
  validation.
- **Suppliers**: real CRUD (no dedicated doc exists — see §12; work from
  `SCHEMA.md` + the existing `suppliers.html` UI).
- **Purchases**: `PurchaseService` (submit/approve/reject/receive), partial
  delivery, stock-increase-only-on-receive invariant.
- **Sales**: `SaleService` (atomic stock pre-check, stock deduction,
  cancellation restoring stock).
- **Inventory**: `InventoryService` as the single choke point for all
  stock mutations, movement ledger, auto status recalculation.
- **Adjustments**: approval workflow mirroring Purchases (no dedicated doc
  — work from `SCHEMA.md` + existing `adjustments.html` UI).
- **Dashboard**: real KPI/stat aggregation replacing hardcoded numbers (no
  dedicated doc — infer from the existing `dashboard.html` mock + general
  patterns in other module docs).
- **Reports**: all 9 report types (Inventory, Purchase, Sales, Movement,
  Adjustment, Low Stock, Out of Stock, AI Forecast, AI Slow-Moving), PDF
  (WeasyPrint) + CSV export, Supervisor+ only.
- **Notifications**: `notify_user()`/`notify_supervisors()` service, 12
  notification types (the `Notification` model already exists — §6),
  email gating via `SystemSettings` (model already exists), 30s frontend
  polling.
- **Search** (no dedicated doc — see §12): global search, filters, AI
  classification filter per `INDEX.md`'s one-line description.
- **Audit**: `log_action()` service (the immutable `AuditLog` model already
  exists — §6), ~40 action constants, admin-only viewer.
- **Settings** (no dedicated doc — see §12): company info, thresholds, AI
  config admin UI, backed by the already-existing `SystemSettings`
  singleton model.
- **AI — Demand Forecasting**: real pandas/scikit-learn pipeline, model
  persistence, Celery Beat schedule, confidence scoring, reorder
  recommendations — writing into the already-existing `DemandForecast`
  model.
- **AI — Dead Stock Detection**: real rule-based classifier,
  post-sale-signal reclassification, daily Celery job — writing into the
  already-existing `InventoryClassification` model.
- **Deployment**: Render.com setup (5 services: web, celery-worker,
  celery-beat, PostgreSQL, Redis), WhiteNoise static files, persistent
  storage for AI model files.

---

## 18. AI Development Memory

Rules future AI assistants working on this repo must follow, distilled
from decisions made and corrections applied during development:

- **Read `docs/INDEX.md` first**, then the specific module doc for the
  task — but remember `INDEX.md`'s links are broken (flat-vs-subfolder
  mismatch, see §12) and 8 referenced files don't exist. Don't let a
  missing/broken link stop you; fall back to `SCHEMA.md` +
  `API_CONTRACTS.md`, and **report the gap explicitly rather than
  inventing rules to fill it.**
- **Never duplicate the modal/form architecture.** Every new "Add X" flow
  must reuse `modal.js` + `form-validation.js` + `dom-utils.js` +
  `modal-form.js`, following the exact recipe in §4/§14. If you're about
  to write a new modal-open function or a new validation helper, stop —
  it almost certainly already exists.
- **Never hardcode colors, spacing, or type values** — every one of those
  has a token in `tokens.css`. If a value you need doesn't have a token,
  add one to `tokens.css` rather than hardcoding it inline.
- **Refactor duplicate logic into a shared module before adding new
  code**, not after. This is how `chart-colors.js` and `table-filter.js`
  came to exist — both were extracted/created before the Intelligence
  pages were built, specifically to avoid a third copy of the same logic.
- **Do not invent fields or business rules.** Every field on every form
  and every model field implemented so far was traced to an explicit
  source in `SCHEMA.md` or `API_CONTRACTS.md`. When documentation was
  missing or ambiguous (e.g. "Add Inventory Transaction"), the correct
  move was to investigate, conclude it shouldn't exist as a direct-create
  form, and **report that conclusion** rather than build something
  undocumented.
- **Check `[hidden]` + `display` interactions carefully.** A class that
  sets `display` on an element will silently override the browser's
  native `[hidden]{display:none}` default regardless of specificity
  (cascade *origin* rule, not specificity). This has caused two real bugs
  in this project already. When toggling visibility via `hidden`, verify
  with `getComputedStyle(el).display`, not just the DOM `.hidden`
  property — a Playwright test checking only the property passed while
  the element was still visually showing.
- **Django's `{# #}` comment tag does not support multi-line content.**
  If the closing `#}` isn't on the same line as `{#`, the entire block
  renders as literal visible page text instead of being stripped. Always
  use `{% comment %}...{% endcomment %}` for anything spanning more than
  one line. This bug shipped into 4 templates before being caught by
  actually looking at a full-page screenshot — DOM/text assertions alone
  didn't catch it either, since the leaked text was visually present but
  easy to miss without a visual check.
- **Verify UI changes live**, not just by reading the diff. This project's
  established verification method: run the dev server, drive it with
  Playwright (screenshots + console-error capture + computed-style
  checks + DOM interaction), across every affected page, not just the one
  you changed — several real bugs here were only caught by checking
  pages *adjacent* to the one being worked on.
- **Verify a documented schema programmatically, not by eyeballing.** Use
  `model._meta.get_fields()`, `_meta.indexes`, `_meta.db_table`, and
  `field.remote_field.on_delete` in a `manage.py shell -c` script to
  confirm every field/index/`on_delete` matches the doc — this is the only
  way to be confident across many models without re-reading the source doc
  line-by-line for each one.
- **`PermissionsMixin` hardcodes `related_name="user_set"`** for `groups`/
  `user_permissions` — it is not parametrized by app or class name. If a
  project defines a custom user model *and* still has `django.contrib.auth`
  installed (true almost everywhere, since it's a default app), both
  fields need explicit, distinct `related_name` overrides on the custom
  model or `manage.py check` fails with `fields.E304`. This is a standard,
  well-known Django gotcha, not a project-specific bug — don't skip it
  when adding a custom `AbstractBaseUser` model.
- **`ImageField` hard-requires Pillow.** Django's `check` framework catches
  this immediately (`fields.E210`) rather than failing silently at
  runtime — install Pillow the moment any model uses `ImageField`.
- **Changing `AUTH_USER_MODEL` after `auth`/`admin` migrations are already
  applied is a landmine.** Always run `manage.py showmigrations` before
  touching it. If `auth`/`admin` show applied migrations, a full DB reset
  is needed before flipping `AUTH_USER_MODEL` — it can't be done as a
  simple settings.py edit once those migrations exist. In this project
  that reset is safe (no business data in `db.sqlite3` yet), but always
  confirm that before resetting anything.
- **When a task says "models only, exclude business logic/services,"**
  model-level code the source doc writes directly inside a model class
  (managers, `save()` overrides, simple properties/classmethods) is
  reasonably in-scope even under a strict reading — "business logic/
  services" more naturally refers to separate workflow-service classes
  described elsewhere (e.g. `PurchaseService`, `SaleService`). State this
  interpretation explicitly rather than silently picking one, so it can be
  corrected if a narrower reading was actually intended.
- **This project has no working backend yet, even with models in place.**
  Before implementing any feature that seems to need persistence, confirm
  whether you're meant to be building real Django wiring (migrations,
  views, services — a genuinely new phase of work) or another
  front-end-only mock page following the existing static-data pattern.
  Don't assume — the distinction changes the entire approach.
- **`TECH_STACK.md` describes Bootstrap 5.3**; the actual project uses a
  custom hand-built design system instead. This was a deliberate choice,
  not a mistake — don't "fix" it by pulling in Bootstrap, and don't be
  surprised the two disagree.
- **`requirements.txt` has 6 packages, not the ~15 in `TECH_STACK.md`.**
  DRF, Celery, Redis, scikit-learn, Argon2, WhiteNoise, Gunicorn, WeasyPrint
  are all documented but **not installed** (Pillow was added in Backend
  Phase 1 for `ImageField` support — that's the one addition so far). Any
  task assuming a documented dependency is available should check
  `requirements.txt` first rather than assuming.
