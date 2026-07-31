# Stockwell — Project Memory

> **Read this file first, before any other document, before writing any code.**
> This file is the permanent engineering memory of the project. It reflects the
> **actual current state of the repository** as of 2026-07-31, updated after:
> (1) four frontend routing/consistency bug fixes, (2) **Backend Phase 1** —
> full Django ORM schema (16 models), (3) **Backend Phase 2** — all 16
> registered in Django admin, (4) **Backend Phase 3/3.4/3.5** —
> `frontend/services.py` (Inventory/Purchase/Sale/Adjustment services, the
> ONLY code path allowed to mutate stock), a model/service bug-fix pass
> (5 items, see `docs/bugsfound.md`), and `frontend/audit.py` +
> `frontend/notifications.py` (log_action/notify_user/notify_supervisors,
> retrofitted into every service method). 53 tests passing. (5) **Phase
> 3.6** — built mock frontend pages for the 5 previously-disabled sidebar
> links (Reports, Notifications, Users & Roles, Audit Log, Settings) and
> re-enabled them; all 15 sidebar links now go somewhere real. (5)
> **Phase 3.65** — regression check on Phase 3.6, no bugs found. (6)
> **Phase 3.7** — `AUTH_USER_MODEL` switched to `frontend.User`; the 3
> `frontend` migrations were regenerated from a clean slate and **are now
> applied** to `db.sqlite3` (was empty, safe to reset). Every
> `created_by`/`approved_by`/`performed_by`/`recipient` FK now really
> resolves to `frontend.User`. 53 tests passing (fixed 2 fallout issues —
> see §12/§15). (7) **Phase 3.8** — switched the DB engine from SQLite to
> PostgreSQL 18 (local, matching `TECH_STACK.md`). `db.sqlite3` is no
> longer used at all. New `stockwell_dev` Postgres role/database created
> locally; connection settings read from `.env` (`DB_NAME`/`DB_USER`/
> `DB_PASSWORD`/`DB_HOST`/`DB_PORT`), never hardcoded. Existing migrations
> replayed with zero changes needed. 53 tests still passing. Confirmed
> `InventoryService`'s `select_for_update()` usage (07_INVENTORY.md's
> requirement) is real and correctly wrapped in `@transaction.atomic` —
> not a gap. Still not built: real views/forms wiring the Phase 3 services
> to the UI (Phase 3.6 pages are static mocks, not wired to
> `frontend/services.py`), API, RBAC, AI. See `docs/frontend_work.md` for
> a frontend-only summary.
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

**Current development stage: front-end mock / UI prototype, sitting on top
of a real, migrated database schema, admin layer, and service layer —
none of which any view calls yet.** The Django ORM models
(`frontend/models.py` — 16 concrete models + a `TimeStampedModel` abstract
base, matching `docs/SCHEMA.md` field-for-field — see §6) are migrated
into PostgreSQL (Phase 3.8, see §6), `AUTH_USER_MODEL = 'frontend.User'`
(Phase 3.7, see §5), and all 16 models are registered and browsable in
`frontend/admin.py` (see §5). But there is still no real authentication
view logic, no API, and no AI implementation, and — critically — no view
in `frontend/views.py` calls the ORM or the service layer at all.
Everything user-facing is the same complete, polished, static-data Django
template + vanilla-JS/CSS front end as before — every "Add X" button opens
a real modal with real client-side validation, but nothing persists and
nothing computes. Treat this repo as a high-fidelity clickable prototype
with a working, tested backend sitting unconnected beside it, not a
wired-up application.

**Technology stack — documented (intended) vs. actual (installed):**

| Layer | Documented in `TECH_STACK.md` | Actually in `requirements.txt` / `settings.py` |
|---|---|---|
| Framework | Django 5.x | **Django 6.0.7** (newer than documented) |
| API | DRF 3.15+ | Not installed |
| Database | PostgreSQL 15+ | **PostgreSQL 18** (local, Phase 3.8) — matches the documented engine. `db.sqlite3` no longer used (§6) |
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
- ✅ **Django admin registration (Backend Phase 2)** — all 16 models
  registered in `frontend/admin.py` with per-model `list_display`,
  `search_fields`, `list_filter`, `ordering`, and `list_select_related`
  where useful. `AuditLog`/`InventoryMovement` have change/delete disabled
  in admin (matching their documented immutability), `User.password` is
  read-only (prevents a cleartext-overwrite footgun on a bare
  `AbstractBaseUser` admin form), `SystemSettings` blocks adding a second
  row. Verified live: the `/admin/` index page renders cleanly and lists
  all 16 models, and (Phase 3.7) every model's list view now actually
  works — migrations applied, see §5/§6/§12.
- ✅ **Service layer (Backend Phase 3/3.4/3.5)** — `frontend/services.py`:
  `InventoryService` (increase/decrease_stock, stock-never-negative,
  writes `InventoryMovement`), `PurchaseService` (submit/approve/reject/
  receive/cancel, stock only moves on receive), `SaleService`
  (atomic pre-validate-then-deduct, cancel restores stock),
  `AdjustmentService` (approve/reject, mirrors Purchase). Plus
  `frontend/audit.py` (`log_action()`) and `frontend/notifications.py`
  (`notify_user`/`notify_supervisors`, sync email via `send_mail()`, no
  Celery yet) wired into every service method. 5 model/service bugs fixed
  along the way (immutability, singleton enforcement, redundant indexes,
  a `Decimal`/`float` crash bug inherited from `SCHEMA.md`'s own reference
  code — full list in `docs/bugsfound.md`). 53 tests passing, migrations
  applied to PostgreSQL (Phase 3.8, see §5/§6). Still nothing calls any of
  this from a view — no views/forms exist yet (see §5).
- ✅ **`select_for_update()` concurrency safety (verified Phase 3.8)** —
  `InventoryService.increase_stock`/`decrease_stock` are both
  `@transaction.atomic` and lock the `InventoryRecord` row before
  reading, exactly as `07_INVENTORY.md` specifies. Confirmed no other
  code path mutates `current_stock` unlocked — `PurchaseService`/
  `AdjustmentService` both delegate to these two methods rather than
  touching stock directly. SQLite silently no-ops `select_for_update()`;
  Postgres actually enforces it, so this was worth confirming for real,
  not just reading the code — it holds.
- ✅ **Landing page** (`landing/index.html`) — full marketing page, hero,
  fabricated metrics, animated ticker, features grid, AI teaser section.
  Now uses the shared icon sprite for its feature icons (fixed — see §15).
- ✅ **Login page UI** (`accounts/login.html`) — styled split-panel form,
  password-visibility toggle, now posts to the correct `frontend:login`
  route consistently (routing bug fixed — see §15). ⚠️ Still no real
  Django auth view logic behind it (Phase 4) — the data layer it needs
  (`AUTH_USER_MODEL`, migrations) is ready as of Phase 3.7 (see §12).
- ✅ **Dashboard shell** (`dashboard_base.html` + `sidebar.html` +
  `topbar_actions.html`) — sidebar nav (all 15 links now live, none
  disabled — Phase 3.6, see §15), topbar search/user menu, and a working
  notification-bell dropdown (`.dropdown` component, `dashboard.js`).
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
- ✅ **Reports page** (`reports/reports.html`) — 9 report-type cards +
  Sales Report / Low Stock Report preview panels, `table-filter.js` wired.
  Static mock data only, no backend query.
- ✅ **Notifications page** (`notifications/notifications.html`) — 8 mock
  rows (read/unread states), plus the topbar dropdown (above). Static mock,
  decorative mark-as-read.
- ✅ **Users & Roles page** (`users/users.html`) — user list + stat strip +
  working "Add User" modal (fields exactly match `SCHEMA.md`'s `User`
  model: full_name, username, employee_id, email, role). Static mock, no
  RBAC, no persistence.
- ✅ **Audit Log page** (`audit/audit_log.html`) — 8 mock log rows,
  search/module/status filtering via `table-filter.js`. Static mock, not
  reading real `AuditLog` rows.
- ✅ **Settings page** (`settings/settings.html`) — single form, all 13
  `SystemSettings` fields, decorative Save button. Static mock, no
  persistence.
- Verified regression-free (Phase 3.65): no leaked `{# #}` comment text, no
  `[hidden]`/`display` cascade bugs, no console errors across all 5 pages —
  see §15.
- ✅ **`AUTH_USER_MODEL` switch + migrations applied (Phase 3.7)** —
  `AUTH_USER_MODEL = 'frontend.User'`, `db.sqlite3` reset and migrated
  fresh, every user-pointing FK confirmed resolving to `frontend.User` at
  runtime, `createsuperuser` creates a real `frontend.User` row. Admin
  list pages (Phase 2) now actually render — verified live. See §15.

Not built at all (0%):
- ❌ RBAC enforcement, session logic, real login view
- ❌ Any DRF/API layer, any views/forms calling the new services at all
- ❌ Persistence/backend wiring for Reports, Notifications, Users & Roles,
  Audit Log, Settings — all 5 have real frontend mock pages (above) but
  none reads from `frontend/services.py` or the database yet.
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
│   ├── settings.py            Single-file settings (no base/dev/prod split, unlike TECH_STACK.md's documented pattern). AUTH_USER_MODEL = 'frontend.User' (Phase 3.7, see §5).
│   ├── urls.py                Root URLconf: /admin/, /accounts/ (django.contrib.auth.urls), / (frontend app)
│   ├── wsgi.py / asgi.py
├── frontend/                  The ONLY Django app. Holds both the backend schema and the entire UI.
│   ├── models.py              16 concrete models + TimeStampedModel abstract base (Backend Phase 1), matching docs/SCHEMA.md exactly. Migrated (Phase 3.7).
│   ├── admin.py                All 16 models registered (Backend Phase 2) — list_display/search_fields/list_filter/ordering configured. Data-browsing works (Phase 3.7, see §5).
│   ├── views.py               One-line render() functions per page, no business logic, no ORM usage yet
│   ├── urls.py                app_name="frontend"; 17 registered routes (12 + 5 from Phase 3.6, see §5)
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
├── requirements.txt             8 packages total — see §1 table (Pillow added Phase 1, psycopg+psycopg-binary added Phase 3.8)
├── db.sqlite3                   Stale/unused since Phase 3.8 (engine is now PostgreSQL) — gitignored, safe to delete
├── .env / .env.example          Now also carries DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT (Phase 3.8)
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
  why this reading of "models only" was chosen. **`AUTH_USER_MODEL =
  'frontend.User'` (Phase 3.7)** — switched by resetting `db.sqlite3`
  (confirmed empty first) and regenerating migrations fresh. Confirmed live:
  `PurchaseOrder.created_by` resolves to `frontend.models.User`, not
  `auth.User`.
- **Migrations**: `frontend/migrations/0001_initial.py`, generated fresh
  in Phase 3.7 with `AUTH_USER_MODEL` already correct, applied to
  `db.sqlite3` (`showmigrations` shows all `[X]`).
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
- **Admin (Backend Phase 2 — done)**: all 16 models registered in
  `frontend/admin.py` with `list_display`/`search_fields`/`list_filter`/
  `ordering`/`list_select_related` configured per model. Three
  admin-layer-only design choices, none touching `models.py`:
  - `User.password` is `readonly_fields` — a bare `ModelAdmin` on an
    `AbstractBaseUser` model renders `password` as an editable plain-text
    field with no hashing, which would silently break login if edited.
  - `InventoryMovement` and `AuditLog` have `has_change_permission`/
    `has_delete_permission` overridden to `False` — both are documented as
    immutable ledgers, and `AuditLog.save()`/`delete()` raise a bare
    `PermissionError` on mutation (not a Django-recognized exception),
    which would otherwise surface as an unhandled 500 the moment someone
    clicked "Save" on an existing row.
  - `SystemSettings.has_add_permission` blocks creating a second row once
    one exists (the model is documented as a singleton but nothing in
    `models.py` enforces that — see §12).
  **Verified live**: `/admin/` index renders cleanly and lists all 16
  models correctly. **Phase 3.7 update**: list views no longer 500 —
  `/admin/frontend/user/` and `/admin/frontend/purchaseorder/` both
  confirmed `200` via a real login flow, now that migrations are applied
  (see §6/§12/§15). Creating and deleting a `frontend.User` also confirmed
  crash-free.
- **Services (Backend Phase 3/3.4/3.5 — done)**: `frontend/services.py`,
  `frontend/audit.py`, `frontend/notifications.py` — see §2 for what they
  do. Still no views/forms call any of them. 53 tests passing (against
  Django's throwaway test database, as always) — Phase 3.7 fixed 2 fallout
  issues from the `AUTH_USER_MODEL` switch: test fixtures needed unique
  `employee_id`s, and `notify_supervisors()`'s test fixtures needed a real
  `role` set now that its role-based query actually runs (see §15).

---

## 6. Database

- **Actual state (Phase 3.8)**: engine is PostgreSQL 18, local
  `stockwell_dev` role/database, connection settings read from `.env`
  (`DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`). All migrations
  — `auth`/`admin`/`contenttypes`/`sessions` plus `frontend.0001_initial`
  (unchanged, no regeneration needed) — applied via `manage.py migrate`
  against a fresh database. `manage.py showmigrations` shows all `[X]`.
  `db.sqlite3` (used through Phase 3.7) is no longer read by the app at
  all — the file is still on disk (gitignored, harmless) but stale;
  safe to delete whenever convenient.
- **Schema implementation status**: **all 16 models implemented in code**,
  verified programmatically (Django shell introspection of
  `model._meta.get_fields()`, `_meta.indexes`, `_meta.db_table`, and each
  FK's `field.remote_field.on_delete`) to match `docs/SCHEMA.md` exactly —
  zero mismatches found on field names, field counts, `db_table` values,
  index counts, or `on_delete` behavior across all 16 models. `manage.py
  check` passes clean.

  | Model | Key fields | Relationships |
  |---|---|---|
  | `User` | username, email, employee_id (all unique), role (admin/supervisor/staff), lockout fields | base for all `created_by`/`performed_by`/`requested_by`/`approved_by` FKs (via `settings.AUTH_USER_MODEL` — the active auth model since Phase 3.7, see §5) |
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

  Documented migration order (per-app) collapses to one
  `makemigrations frontend` in the current single-app structure — this is
  what Phase 3.7 actually ran, producing one `0001_initial.py`.

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
  - `InventoryMovement`'s docstring says "Immutable ledger — never update
    or delete," but unlike `AuditLog`, that's **not enforced in code** —
    no `save()`/`delete()` override exists on `InventoryMovement`, so
    nothing stops a direct mutation outside admin. Surfaced while building
    admin (Phase 2) — the admin layer enforces it there, but the model
    itself doesn't.
  - `SystemSettings` is documented as a singleton (`get_settings()` →
    `get_or_create(pk=1)`), but that's a **convention, not a constraint** —
    no override prevents `SystemSettings.objects.create(...)` from making
    a second row. Also surfaced while building admin (Phase 2); admin
    mitigates this at the UI layer only (see §5).
- **Environment fix required to implement as documented**: `User.groups`/
  `user_permissions` (inherited from `PermissionsMixin`) needed explicit
  `related_name` overrides — not in SCHEMA.md's literal text, but required
  because `PermissionsMixin` hardcodes `related_name="user_set"`, which
  clashed with Django's own still-present default `auth.User` (`fields.E304`
  on `manage.py check`). Standard, well-known Django fix; doesn't change
  the DB schema shape (see §13/§18).
- **Pending**: seed/fixture data, real views/forms calling the service
  layer, RBAC/auth wiring (Phase 4). Migrations + `AUTH_USER_MODEL`
  resolved Phase 3.7 (§15).

---

## 7. AI Features

Both AI pages are polished front-end mocks with **no real model, no real
job, no real data pipeline** behind them. `DemandForecast` and
`InventoryClassification` exist as migrated Django models (§6) but are
completely unused — the pages below remain 100% static mocks with no
connection to these models yet.

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

**Fully completed (schema + admin layer):** all 16 documented models,
matching SCHEMA.md exactly — see §6. All 16 registered in Django admin
with sensible list/search/filter config — see §5. Neither layer is
migrated yet, so nothing in either is actually usable for browsing real
data (admin list views 500; see §12).

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
  Django auth behind it — no auth view logic (Phase 4). Migrations +
  `AUTH_USER_MODEL` are resolved (§15), so the data layer this needs is
  ready; nothing in the login view uses it yet.

**No longer missing**: Reports, Notifications, Audit Log, Users & Roles,
Settings all got real mock pages in Phase 3.6 (§11) — sidebar links
re-enabled, nothing left disabled.

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
- ✅ Reports (`/reports/`, Phase 3.6 — 9 report types listed, 2 with mock tables)
- ✅ Notifications (`/notifications/`, Phase 3.6 — list page + topbar dropdown)
- ✅ Users & Roles (`/users/`, Phase 3.6 — list + Add User modal)
- ✅ Audit Log (`/audit-log/`, Phase 3.6 — filterable mock log)
- ✅ Settings (`/settings/`, Phase 3.6 — single form, all SystemSettings fields)

All 15 sidebar links now resolve to a real page. All 5 above are static
mocks like every pre-Phase-3.6 page — nothing here reads from
`frontend/services.py` or the database yet (see §16).

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

**Open items from Backend Phase 1 — RESOLVED Phase 3.7:**
`AUTH_USER_MODEL` is now `frontend.User`, migrations are generated and
applied to `db.sqlite3` (reset first — it had zero real rows). See §15.

**Open items from Backend Phase 2 — RESOLVED Phase 3.7:**
- Admin list views no longer 500 — verified live for `User` and
  `PurchaseOrder`, both render `200`.
- Deleting a user no longer crashes — cascade-delete collector now walks
  real, migrated tables. Re-verified: create + delete a throwaway
  `frontend.User`, no error.
- **A bug was found and fixed in `SystemSettingsAdmin` itself during this
  phase**: `has_add_permission` originally queried `SystemSettings.objects
  .exists()` directly. Django calls `has_add_permission` for *every*
  registered model on *every* admin page load (to decide whether to show
  "Add" links in the sidebar/index), not just on that model's add view —
  so this took down the entire `/admin/` index with a 500, not just the
  SystemSettings page. Fixed by wrapping the query in
  `try/except DatabaseError`, failing open. Worth remembering for any
  future permission-method override that queries the DB (see §18).
- **RESOLVED Phase 3.7**: Django no longer auto-registers `auth.User` in
  admin once `AUTH_USER_MODEL` is swapped — confirmed live via
  `admin.site._registry`, only `frontend.User` (+ `auth.Group`) show up.
  The old side-by-side duplicate-Users confusion is gone.
- **Cosmetic**: `SystemSettings` has no `verbose_name`/`verbose_name_plural`
  set, so Django's default auto-pluralization renders "System settingss"
  (double s) in the admin index. Harmless, visible, not fixed (models.py
  out of scope for Phase 2).

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

**Missing backend**: no API, no real auth views/RBAC (Phase 4), no Celery,
no AI execution. Migrations + `AUTH_USER_MODEL` resolved Phase 3.7 (§15);
the service layer (§5) exists but nothing calls it from a view yet.

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

**Full bug catalog**: `docs/bugsfound.md` now tracks every bug found
project-wide, each traced to its source doc where applicable — check there
instead of this section for exhaustive detail going forward.
`notify_supervisors()`'s `role`-based filter is now live for real (Phase
3.7) — the `is_staff`/`is_superuser` fallback in `frontend/notifications.py`
is dead in practice but deliberately left in place (Phase 4/RBAC decision,
not this phase's scope). `PurchaseService`'s `user.full_name` path is also
now live; `_user_display_name()`'s `get_full_name()` fallback is similarly
inert but undeleted for the same reason.

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
  model correctly with zero model-code changes needed. **Confirmed
  correct, Phase 3.7**: the switch happened exactly as predicted here,
  zero changes needed to any FK declaration in `models.py`.
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
- **Made `User.password` read-only in admin instead of leaving it
  editable.** A bare `ModelAdmin` on an `AbstractBaseUser` subclass renders
  `password` as a plain editable text field with no hashing (Django's
  `UserAdmin`/`ReadOnlyPasswordHashField` machinery isn't wired up since
  `AUTH_USER_MODEL` wasn't switched at the time) — editing it would
  silently bypass `set_password()` and break login. Admin-config-only,
  doesn't touch `models.py`. Still applies post-Phase-3.7: this admin
  customization was never removed and remains correct.
- **Disabled change/delete permissions in admin for `InventoryMovement`
  and `AuditLog`** instead of leaving them as plain editable models.
  `AuditLog.save()`/`delete()` already raise `PermissionError` on mutation
  in the model itself, which would surface as an unhandled 500 in the
  admin change form rather than a clean permission message — disabling it
  at the admin layer avoids that. `InventoryMovement` has the same
  documented invariant but no code enforcement (see §6) — the admin
  override is currently the *only* place this invariant is actually kept.
- **Guarded `SystemSettings`'s "Add" button in admin (`has_add_permission`
  blocks a second row) rather than leaving it unrestricted**, since the
  model itself has no singleton constraint (see §6). This is a UI-layer
  mitigation only — direct ORM code can still create a second row; flagged,
  not fixed, since `models.py` was out of scope for Phase 2.
- **Wrapped that same `has_add_permission` check in `try/except
  DatabaseError`** after discovering it broke the *entire* admin index
  (not just the SystemSettings page) — Django calls `has_add_permission`
  for every registered model on every admin page load, so a DB query
  there needs to fail open, not just be "probably fine." Found and fixed
  within this same phase, before it could ship as a latent landmine (see
  §12/§18).

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
10. **Backend Phase 2: Django Admin** — registered all 16 models in
    `frontend/admin.py` with `list_display`/`search_fields`/`list_filter`/
    `ordering` configured per model; disabled change/delete for the two
    documented-immutable models (`AuditLog`, `InventoryMovement`); made
    `User.password` read-only; guarded `SystemSettings` against a second
    row. Verified live with a throwaway superuser (created, then removed
    via raw SQL after the ORM delete path turned out to be broken — see
    below): the `/admin/` index renders and lists all 16 models correctly,
    but every one of their list views 500s (`OperationalError: no such
    table`) since there are still zero migrations. Found and fixed a
    self-introduced bug (`SystemSettingsAdmin.has_add_permission` querying
    the DB on every admin page load, not just its own page) within the
    same phase. Also discovered that deleting any `auth.User` now crashes
    too, since Django's delete-cascade collector walks every reverse FK to
    `settings.AUTH_USER_MODEL` including the new, unmigrated models.
11. **This document updated again** — to reflect Backend Phase 2.
12. **Backend Phase 3: Service Layer** — `frontend/services.py`:
    `InventoryService`, `PurchaseService`, `SaleService`,
    `AdjustmentService`. Generated migrations `0001`–`0003` (needed to run
    tests at all — Django's test DB can't build tables without them; not
    applied to the real DB). Found and fixed a `Decimal`/`float` crash in
    both `06_SALES.md`'s and `SCHEMA.md`'s own reference code. 27 tests.
13. **Backend Phase 3.4: bug-fix pass** — added `PurchaseService.cancel()`,
    made `InventoryMovement`/`SystemSettings` enforce their documented
    invariants in code (not just docstrings), removed 3 redundant indexes.
    39 tests. Full detail: `docs/bugsfound.md`.
14. **Backend Phase 3.5: audit + notifications** — `frontend/audit.py`
    (`log_action`), `frontend/notifications.py` (`notify_user`/
    `notify_supervisors`, sync email), retrofitted into every Phase 3/3.4
    service method. Found the `role`/`full_name` gap (only exist on the
    still-inert `frontend.User`) and added disclosed fallbacks. 53 tests.
15. **This document updated (concise pass)** — Phases 3/3.4/3.5 folded in
    briefly rather than with the earlier phases' full essay-per-decision
    treatment, per explicit instruction to keep future updates short.
16. **Phase 3.6: Insights & Administration mock pages** — Reports,
    Notifications, Users & Roles, Audit Log, Settings all built as static
    mocks (same pattern as every pre-existing page), sidebar re-enabled
    (undoes BUG-08's disabled-span treatment). New reusable piece: a
    `.dropdown` component in `dashboard.css` + toggle logic in
    `dashboard.js` for the topbar notification bell (first dropdown
    pattern in the app). `docs/frontend_work.md` added as a concise
    frontend-only work log.
17. **This document updated again (concise)**.
18. **Phase 3.65: Phase 3.6 regression check** — re-verified the 5 new
    pages + notification dropdown against the two bug patterns that have
    each shipped twice before (`[hidden]`/`display` cascade trap, §12;
    multi-line `{# #}` leaking as text). Neither reappeared — dropdown
    uses `display:none`/`.is-open` (not `[hidden]`) by design, the 3 new
    `hidden`-toggled elements are already covered by existing
    `.empty-state[hidden]`/`.file-drop-preview[hidden]` CSS, and every
    `{# #}` in the 5 templates closes on its own line. Confirmed live via
    Playwright (screenshots + console + `getComputedStyle`): Add User
    modal validates/submits/appends a row correctly, dropdown opens/closes
    on outside-click, Audit Log's search+status filters work including the
    empty state. Add User modal fields and Settings form fields both
    verified to match `SCHEMA.md` exactly, nothing invented.
19. **Phase 3.7: `AUTH_USER_MODEL` switch** — confirmed BUG-11's writeup
    was still accurate (not stale): `AUTH_USER_MODEL` was never set, every
    cross-model FK resolved to `auth.User`. Confirmed `db.sqlite3` had 0
    real rows, so reset it and the 3 `frontend` migrations, set
    `AUTH_USER_MODEL = 'frontend.User'`, regenerated one fresh
    `0001_initial.py`, migrated. Verified live: FK resolution, a real
    `createsuperuser`-created `frontend.User` with `role`/`employee_id`
    populated, admin list pages rendering `200`, create+delete of a user
    not crashing (BUG-19 closed). Fixed 2 test-suite fallout issues
    (`employee_id` uniqueness, `notify_supervisors()`'s now-real
    `role`-based query) — 53/53 tests passing. `docs/bugsfound.md` updated
    (BUG-19 closed, BUG-11 given a follow-up note).
20. **Phase 3.8: switch to PostgreSQL** — confirmed a local Postgres 18
    server was actually installed and running (not just assumed from
    pgAdmin's presence), created a dedicated `stockwell_dev` role +
    database, added `psycopg[binary]` to `requirements.txt`, and switched
    `DATABASES` in `settings.py` to read `DB_NAME`/`DB_USER`/
    `DB_PASSWORD`/`DB_HOST`/`DB_PORT` from `.env` (no hardcoded
    credentials). Existing migrations replayed against a fresh database
    with zero regeneration needed. Re-verified BUG-19 (create+delete a
    user) doesn't reoccur. 53/53 tests passing on Postgres. Confirmed
    `InventoryService`'s `select_for_update()` usage (§2) is real,
    correctly wrapped in `@transaction.atomic`, and the only path that
    mutates stock — not a gap SQLite was silently hiding.

---

## 16. Next Priorities

Highest priority first:

1. **Wire real views/forms to the now-complete service layer** (§2) —
   the data layer (`AUTH_USER_MODEL`, migrations, both resolved Phase 3.7,
   §15) is finally ready for this. Replace static hardcoded rows module by
   module (Products first). The 5 Phase 3.6 pages (§11) join this same
   backlog — they're mocks like everything else.
2. **Reconcile `INDEX.md`'s broken links**; write the missing module docs
   (`04_SUPPLIERS.md`, `08_ADJUSTMENTS.md`, `09_DASHBOARD.md`,
   `12_SEARCH.md`, `14_SETTINGS.md`).
3. **Then** real auth views, DRF API layer, RBAC enforcement, Celery
   (needed for the notification email `.delay()` upgrade — see §2), and
   the real AI pipelines — in that order.

---

## 17. Future Work

Grouped by module, per the documentation:

- **Database schema**: ✅ **done** (Backend Phase 1, §6) — all 16 models
  implemented matching SCHEMA.md.
- **Admin registration**: ✅ **done** (Backend Phase 2, §5) — all 16
  models registered, and now actually usable for data-browsing (migrations
  applied Phase 3.7, see §12). Still pending: seed data.
- **Auth**: the custom `User` model is now the active `AUTH_USER_MODEL`
  (Phase 3.7). Still needed: real login/logout view logic, session
  timeout, account lockout (5 attempts/300s), password reset via email,
  Argon2 hashing, profile update.
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
- **Purchases/Sales/Inventory/Adjustments services**: ✅ **done**
  (Backend Phase 3/3.4, §2) — `PurchaseService`, `SaleService`,
  `InventoryService`, `AdjustmentService`, all with audit/notification
  hooks (Phase 3.5). Not yet callable from any view/form (see §16 #3).
- **Dashboard**: real KPI/stat aggregation replacing hardcoded numbers (no
  dedicated doc — infer from the existing `dashboard.html` mock + general
  patterns in other module docs).
- **Reports**: all 9 report types (Inventory, Purchase, Sales, Movement,
  Adjustment, Low Stock, Out of Stock, AI Forecast, AI Slow-Moving), PDF
  (WeasyPrint) + CSV export, Supervisor+ only.
- **Notifications**: ✅ service **done** (`notify_user`/`notify_supervisors`,
  Phase 3.5, §2), sync email not Celery. Still missing: list page,
  mark-read, 30s polling badge (topbar bell still decorative).
- **Search** (no dedicated doc — see §12): global search, filters, AI
  classification filter per `INDEX.md`'s one-line description.
- **Audit**: ✅ service **done** (`log_action()`, Phase 3.5, §2), called
  from every Purchase/Sale/Adjustment service method. Still missing:
  admin-only viewer page.
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
- **Data layer (models/migrations/`AUTH_USER_MODEL`/admin) being real
  doesn't mean views are wired to it.** Even post-Phase-3.7, every view is
  still a one-line `render()` with no ORM usage. Before implementing any
  feature that seems to need persistence, confirm whether you're meant to
  be wiring a real view to the service layer (a genuinely new phase of
  work) or building another front-end-only mock page following the
  existing static-data pattern. Don't assume — the distinction changes the
  entire approach.
- **`TECH_STACK.md` describes Bootstrap 5.3**; the actual project uses a
  custom hand-built design system instead. This was a deliberate choice,
  not a mistake — don't "fix" it by pulling in Bootstrap, and don't be
  surprised the two disagree.
- **`requirements.txt` has 8 packages, not the ~15 in `TECH_STACK.md`.**
  DRF, Celery, Redis, scikit-learn, Argon2, WhiteNoise, Gunicorn, WeasyPrint
  are all documented but **not installed**. Pillow (Phase 1) and
  psycopg+psycopg-binary (Phase 3.8, the Postgres switch) are the only
  additions beyond Django's own base install so far. Any task assuming a
  documented dependency is available should check `requirements.txt`
  first rather than assuming.
- **Django admin permission methods (`has_add_permission`,
  `has_change_permission`, etc.) are called on every admin page load for
  every registered model — not lazily, only when that model's own page is
  visited.** A DB query inside one of these (e.g. `Model.objects.exists()`
  to enforce a singleton) can take down the *entire* admin site, not just
  that model's page, if the query fails. Wrap any such check in
  `try/except DatabaseError` and fail open. Found and fixed live in this
  project (`SystemSettingsAdmin.has_add_permission`) — it initially broke
  `/admin/`'s index page entirely.
- **Django's delete-cascade collector walks every reverse FK before
  allowing a delete, including FKs from models whose tables don't exist
  yet.** Deleting a user crashed in this project throughout the
  no-migrations period, even though the delete had nothing to do with the
  new schema, because the collector checked `PurchaseOrder`/
  `SaleTransaction`/etc. (all FK'd to `settings.AUTH_USER_MODEL`) for
  related rows and hit `OperationalError: no such table`. Resolved
  Phase 3.7 once migrations were applied — general lesson stands for any
  project in a similar half-migrated state: a raw SQL delete (bypassing
  the ORM collector) is a reasonable, safe escape hatch for throwaway test
  data in that window, not something to reach for on real data.
- **A docstring claiming a model is "immutable" or "singleton" is not the
  same as that being enforced in code.** `AuditLog` enforces immutability
  via `save()`/`delete()` overrides that raise `PermissionError` — that's
  real. `InventoryMovement`'s "never update or delete" is a docstring
  only, with no code backing it. `SystemSettings`'s "singleton" is a
  `get_settings()` convention, not a constraint — nothing stops a second
  row. Don't assume a documented invariant is code-enforced without
  checking; when building anything downstream (admin, services, tests),
  verify it directly against the model source, not the comment.
