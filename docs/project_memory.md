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
> not a gap. (8) **Phase 3.9** — found `docs/bugsfound.md` was stale, not
> the code: BUG-13/20/21/22/25 were all genuinely fixed back in Phase 3.4;
> corrected the doc, plus two stale facts in this file (§3 migrations
> line, §5 route count). (9) **Backend Phase 4** — real authentication
> against `frontend.User`: login (username OR email), logout, account
> lockout (env-configured), session timeout (`SystemSettings.
> session_timeout_seconds`), Argon2 hashing, `StrongPasswordValidator`,
> a profile view (name/contact/photo/password change). RBAC mechanism
> built (`frontend/decorators.py`, `frontend/mixins.py`) and proven
> against throwaway views — **not yet applied to any real module view**
> (Products/Purchases/Sales/etc. stay open to any authenticated-or-not
> visitor until Phase 5/6/7 wires it in, see §12). 75 tests passing. See
> §12 for 4 documentation inconsistencies found and resolved this phase.
> Still not built: real views/forms wiring the rest of the Phase 3
> services to the UI (Phase 3.6 pages are still static mocks), API,
> password reset, AI. (10) **Backend Phase 5** — Products is the first
> fully real module: `ProductForm` (server-side unique SKU/barcode,
> non-negative price/qty, active-only Category/Supplier, file-type/size
> image validation), a real `ProductListCreateView` (GET lists the real
> queryset, POST creates), `AnyStaffMixin` applied to both GET and POST
> (any logged-in role; logged-out redirects to login). `MEDIA_ROOT`/
> `MEDIA_URL` configured and dev-served; product images now actually
> upload and are servable (BUG-10, Phase 1, only ever installed Pillow —
> never wired this up). Every other view (Categories, Suppliers,
> Purchases, Sales, ...) is still the original one-line `render()`,
> unguarded — Products is the pattern Phase 6/7 will copy. **(11) Phase
> 5.5 correction**: Phase 5's product creation originally called
> `InventoryService.increase_stock()`, writing a real `InventoryMovement`
> row for every new product — violating this file's own §13 architecture
> decision that movements only ever happen as a purchase-receive/sale/
> adjustment-approval side effect, never via a direct user form. Fixed:
> product creation now calls the new `InventoryService.
> initialize_for_product()`, creating the `InventoryRecord` at
> `current_stock=0` with **no** movement row — still closing the original
> gap (every product has an `InventoryRecord` the moment it exists, so
> `SaleService` never hits a missing-record error), just without
> fabricating a cause for a movement that didn't happen. The "Initial
> stock" field was removed from the Add Product modal entirely; a
> product's first real stock now only ever arrives via a received
> Purchase Order, like every other module. Also: `modal-form.js` gained a
> documented Promise-returning `onSubmit` contract, and `product-form.js`
> moved off its synchronous-XHR workaround onto `fetch()` — see §5. 4 new
> findings across both phases — `docs/bugsfound.md` BUG-31 through
> BUG-34 — see §12. **(12) Post-Phase-5.5 check**: confirmed BUG-33 itself
> (`extraValidate()` always running, even after standard validation
> already failed) is still present in `modal-form.js` — Phase 5.5 only
> moved Products' real work out of `extraValidate` into `onSubmit`, it
> never touched the shared control flow. Purchase/Sale's `extraValidate`
> (line-items check) is unaffected today since it's synchronous, but will
> hit the same problem the moment Phase 7 gives it any server-side work —
> flagged for whoever wires those modules next (see §12). Also added the
> regression test that didn't exist for the Phase 5.5 fix itself — 80
> tests passing (was 75). **(13) Phase 5.6**: fixed BUG-33 for real, in
> `modal-form.js` itself — `extraValidate()` is now short-circuited behind
> `isStandardValid`, so it never runs once a required/non-negative field
> has already failed, for every module, not just Products. Verified live
> with a call-counting wrapper around `LineItems.validate()`: Purchase's
> empty-Supplier submit now calls it 0 times (was 1); filling Supplier in
> brings it back to 1, confirming normal operation is unchanged. Sale has
> no `requiredFieldIds` configured at all, so this fix is a no-op for it
> today (nothing to gate against) — confirmed no regression either way.
> Products was already unaffected (doesn't use `extraValidate` since
> Phase 5.5). Scope was `modal-form.js` only, per this task's own
> instruction — no per-entity file changed. 80/80 tests still passing.
> **(14) Backend Phase 6** — Categories and Suppliers are real now too,
> mechanically repeating Phase 5's pattern: `CategoryForm`/`SupplierForm`,
> `CategoryListCreateView`/`SupplierListCreateView` (`AnyStaffMixin` on
> GET+POST, `fetch()`-based `onSubmit` from the start — no sync-XHR
> workaround needed this time, since `modal-form.js`'s Promise contract
> already existed). Same BUG-31-style mismatch found again, bigger this
> time: the mock `categories.html`/`suppliers.html` modals had fields
> with no schema backing at all (category parent/code; supplier code/
> city/country/postal_code/website/tax_id/notes) and mislabeled most of
> Supplier's genuinely-required fields optional — fixed by trimming the
> unbacked fields and correcting the required labels, not by inventing
> new model columns (`docs/bugsfound.md` BUG-35). No approval workflow,
> no InventoryService involvement — neither module touches stock. Same
> live-verification approach as Phase 5 (no new automated tests this
> phase either): logged-out blocked, empty submit blocked, duplicate
> name/email rejected, Active/Inactive status confirmed mapping to
> `is_active` correctly, persistence confirmed after reload, for both
> modules. 80 tests still passing (none added or broken).
> **(15) Backend Phase 7** — Purchases, Sales, and Adjustments are real
> now, including their full approval workflows, not just create+list:
> `PurchaseOrderForm`/`SaleTransactionForm`/`AdjustmentForm`/`ReasonForm`,
> a `parse_line_items()` helper shared by Purchase/Sale, and 12 new views
> covering every documented state-machine transition (submit/approve/
> reject/receive/cancel for Purchases; create/cancel for Sales; create/
> approve/reject for Adjustments) — see §5. `AnyStaffMixin` on create/
> submit/receive, `SupervisorRequiredMixin` on approve/reject/cancel,
> confirmed live and by test that `SupervisorRequiredMixin` really is a
> hierarchy (`[ADMIN, SUPERVISOR]`) — an Admin can approve, not just a
> Supervisor. Unlike Phase 5/6, checking the mock modals against
> `SCHEMA.md` found **no** BUG-31/35-style mismatch this time — all three
> were already field-correct (each one's own template comment already
> cited the exact model fields it was built from). The real gap was
> `mock-catalog.js` keying products/suppliers by *name string*; retired
> in favor of real, server-rendered `<option value="{{ pk }}">`, with
> `line-items.js` itself untouched (it only ever cared about whatever
> HTML it was handed). Added a real "Submit for approval" action to
> Purchases' Draft rows — the mock had no way to move Draft → Pending at
> all, a workflow gap rather than a field one — and a real Cancel action
> now that `PurchaseService.cancel()` exists (Phase 3.4, BUG-25). Every
> stock mutation routes through `InventoryService`/`PurchaseService`/
> `SaleService`/`AdjustmentService` — never a raw model save. 20 new
> tests, one per documented transition (submit→approve→receive, partial
> receive, submit→reject, cancel from every cancellable state including
> "partial-received stock isn't reversed", Sale create/insufficient-
> stock/cancel, Adjustment approve-increase/approve-decrease/reject),
> written alongside the views per this phase's explicit instruction, not
> after the fact — 100 tests passing (was 80). Also found and fixed
> BUG-36: a multi-line `{# #}` comment (BUG-03's exact root cause,
> recurring) leaked text containing a literal `<template>` substring,
> which the browser parsed as a real tag and swallowed the entire rest of
> the page — worth remembering harder than BUG-03 alone implied.
> See `docs/frontend_work.md` for a frontend-only summary.
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

**Current development stage: real authentication, sitting in front of an
otherwise still-mostly-mock front-end / UI prototype.** The Django ORM
models (`frontend/models.py` — 16 concrete models + a `TimeStampedModel`
abstract base, matching `docs/SCHEMA.md` field-for-field — see §6) are
migrated into PostgreSQL (Phase 3.8, see §6), `AUTH_USER_MODEL =
'frontend.User'` (Phase 3.7, see §5), and all 16 models are registered
and browsable in `frontend/admin.py` (see §5). **Phase 4 made login real**
— `frontend/views.py`'s `login`/`logout_view`/`profile_view` genuinely
call the ORM (`User.objects.get`, lockout fields, `set_password`) and the
service-layer-adjacent modules (`frontend/audit.py`, `frontend/
notifications.py`). But there is still no API, no AI implementation, and
— critically — every *other* view in `frontend/views.py` (Products,
Purchases, Sales, ...) is still a one-line `render()` that doesn't touch
the ORM, the Phase 3 service layer, or the new RBAC decorator/mixin at
all. Everything past the login page is still the same complete, polished,
static-data Django template + vanilla-JS/CSS front end as before — every
"Add X" button opens a real modal with real client-side validation, but
nothing persists and nothing computes. Treat this repo as a real,
working front door (login/logout/lockout/RBAC-mechanism) opening onto a
high-fidelity clickable prototype with a working, tested backend still
sitting unconnected behind it — closer to wired-up than before Phase 4,
but not there yet.

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
- ✅ **Real authentication (Phase 4)** — `accounts/login.html` now posts to
  a real `login` view: username OR email, Argon2 hashing, account lockout
  (`MAX_LOGIN_ATTEMPTS`/`LOCKOUT_DURATION` env vars), session timeout from
  `SystemSettings.session_timeout_seconds`, `StrongPasswordValidator`.
  Real `logout` (POST, topbar dropdown) and `profile` view (name/contact/
  photo/password change, `validate_password()` enforced). `LOGIN_SUCCESS`/
  `LOGIN_FAILED`/`ACCOUNT_LOCKED`/`LOGOUT`/`PROFILE_UPDATED`/
  `PASSWORD_CHANGED` all write real `AuditLog` rows; password change also
  fires a real `Notification` + email. Verified live against the real
  Postgres dev DB, not just the test suite — see §12/§15.
- ✅ **RBAC mechanism (Phase 4)** — `frontend/decorators.py`
  (`require_role`/`admin_required`/`supervisor_required`/`staff_required`)
  and `frontend/mixins.py` (`RoleRequiredMixin`/`AdminRequiredMixin`/
  `SupervisorRequiredMixin`/`AnyStaffMixin`), both proven against
  throwaway views in `frontend/tests.py`. **Not applied to any real view
  yet** — every other page (Products, Purchases, Sales, ...) stays open
  to anyone, authenticated or not, until Phase 5/6/7 wires it in per
  module (see §12).
- ✅ **Dashboard shell** (`dashboard_base.html` + `sidebar.html` +
  `topbar_actions.html`) — sidebar nav (all 15 links now live, none
  disabled — Phase 3.6, see §15), topbar search, a working
  notification-bell dropdown, and (Phase 4) a working user-menu dropdown
  showing the real logged-in user's name/role/initials (`My Profile`,
  `Log out`) — no longer hardcoded to "Amara Tenzin".
- ✅ **Dashboard page** (`dashboard/dashboard.html`) — KPI cards, Chart.js
  sales/inventory charts, static preview panels.
- ✅ **Product module (real, Phase 5)** — list page renders the real
  `Product` queryset (with real Category/Supplier FK display, computed
  stock-status badge); "Add Product" modal posts to a real
  `ProductListCreateView` guarded by `AnyStaffMixin`, with server-side
  `ProductForm` validation (unique SKU/barcode, non-negative price/qty,
  active-only Category/Supplier, image type/size) and a real
  `InventoryRecord` created via `InventoryService` on every product. The
  template/JS pattern (modal.js/form-validation.js/dom-utils.js/
  modal-form.js + product-form.js) this module established is still the
  one every later module copies — see §5/§12/§15.
- ✅ **Category module (real, Phase 6)** — grid-card list renders the real
  `Category` queryset (real product counts via `category.products.count()`);
  "Add Category" modal posts to a real `CategoryListCreateView` guarded by
  `AnyStaffMixin`, `CategoryForm` enforcing unique name server-side. No
  parent/hierarchy or category-code fields — the mock had them, `SCHEMA.md`
  doesn't (see §12 BUG-35).
- ✅ **Supplier module (real, Phase 6)** — list page renders the real
  `Supplier` queryset (real product counts, real Active/Inactive stat
  strip); "Add Supplier" modal posts to a real `SupplierListCreateView`
  guarded by `AnyStaffMixin`, `SupplierForm` enforcing unique email and
  every genuinely-required field server-side. Mock fields with no schema
  backing (code/city/country/postal_code/website/tax_id/notes) removed;
  gained a "Company name" field the mock was missing (see §12 BUG-35).
- ✅ **Purchase module (real, Phase 7)** — list page renders the real
  `PurchaseOrder` queryset; "New purchase order" modal creates a real
  Draft PO with real line items via `PurchaseOrderForm` +
  `parse_line_items()`. Full state machine wired: Submit (`AnyStaffMixin`),
  Approve/Reject (`SupervisorRequiredMixin`), Receive — full or partial
  (`AnyStaffMixin`), Cancel from any cancellable state
  (`SupervisorRequiredMixin`). Every transition calls `PurchaseService`,
  never a raw model save.
- ✅ **Sale module (real, Phase 7)** — list page renders the real
  `SaleTransaction` queryset; "New sale" modal creates a real sale with
  real line items via `SaleTransactionForm` + `parse_line_items()`,
  routed through `SaleService.create_sale()` (pre-validates stock, deducts
  on success). Cancel (`SupervisorRequiredMixin`) restores stock via
  `SaleService.cancel_sale()`.
- ✅ **Adjustment module (real, Phase 7)** — list page renders the real
  `InventoryAdjustment` queryset; "New adjustment" modal creates a real
  pending request via `AdjustmentForm` (`AnyStaffMixin`). Approve/Reject
  (`SupervisorRequiredMixin`) route through `AdjustmentService`.
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
│   ├── views.py               login/logout_view/profile_view real (Phase 4); ProductListCreateView (Phase 5), CategoryListCreateView/SupplierListCreateView (Phase 6) real; Purchases/Sales/Inventory/Adjustments still one-line render() — see §5
│   ├── forms.py                Phase 5 — ProductForm; Phase 6 — CategoryForm/SupplierForm
│   ├── urls.py                app_name="frontend"; 19 registered routes (products/, categories/, suppliers/ point at their List/CreateView.as_view(), see §5)
│   ├── decorators.py          Phase 4 — require_role/admin_required/supervisor_required/staff_required (RBAC, function-based views)
│   ├── mixins.py               Phase 4 — RoleRequiredMixin/AdminRequiredMixin/SupervisorRequiredMixin/AnyStaffMixin (RBAC, class-based views); AnyStaffMixin's first real use is Phase 5's ProductListCreateView
│   ├── validators.py          Phase 4 — StrongPasswordValidator; Phase 5 — validate_product_image (AUTH_PASSWORD_VALIDATORS / ProductForm.image)
│   ├── apps.py                Stock Django scaffolding
│   ├── tests.py                80 tests (Phase 3/3.4/3.5/4/5.5), all passing — see §2/§15. Phase 5 itself added none (verified live instead); Phase 5.5 added 5 — InventoryServiceTests.test_initialize_for_product_creates_zero_stock_record_with_no_movement + ProductCreateViewTests (new class, first real /products/ view test)
│   ├── migrations/             0001_initial.py, applied to PostgreSQL (Phase 3.7 switch, Phase 3.8 engine — see §5/§6)
│   ├── templates/
│   │   ├── base.html                  Public-site root layout (landing + login)
│   │   ├── dashboard_base.html        Authenticated-app root layout (all other pages)
│   │   ├── includes/                  Shared partials: icons.html (SVG sprite), sidebar.html, topbar_actions.html, navbar.html (public nav), footer.html (public footer)
│   │   ├── landing/index.html
│   │   ├── accounts/login.html, profile.html (profile.html is new, Phase 4)
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
├── requirements.txt             9 packages total — see §1 table (Pillow added Phase 1, psycopg+psycopg-binary added Phase 3.8, argon2-cffi added Phase 4)
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
- `includes/sidebar.html` — left nav, present on all 17 dashboard-shell
  pages. Reads `active_nav` context var (default `"dashboard"`). Nav
  hrefs are hardcoded strings, not `{% url %}` tags (the file's own
  comment acknowledges this is a placeholder to fix later). All 15
  sidebar links are live routes as of Phase 3.6 — none disabled anymore
  (see §15).
- `includes/topbar_actions.html` — search box (non-functional, still),
  notification bell (decorative, still). User menu (Phase 4) is a real
  dropdown showing `request.user.get_full_name`/`get_initials`/
  `get_role_display` (falls back to "Amara Tenzin" only for a genuinely
  anonymous visitor on a not-yet-login-gated page — see §12), with
  working `My Profile`/`Log out` links.
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
  their line-items editor before allowing submit). **Phase 5.5**:
  `onSubmit` now has a documented Promise contract — if it returns a
  value with a `.then` (i.e. it used `fetch()`/`async`), the modal stays
  open and unreset until that promise settles, closing only if the
  resolved value isn't `false`/`{success:false}`; a plain (non-Promise)
  return keeps the exact old behavior (always closes immediately). Added
  because Phase 5's Product modal needed a real async round-trip and the
  only way to keep the modal open on a server-side validation failure
  (e.g. duplicate SKU) was a page-freezing synchronous XHR inside
  `extraValidate` — see `docs/bugsfound.md`'s Phase 5.5 entry. Every
  future "Add X" module (Phase 6/7/8) should use this contract for real
  submits rather than reinventing a workaround.
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
  `frontend/urls.py` registers 19 routes: the 17 GET-rendered template
  routes (`""` landing, `dashboard/`, `products/`, `categories/`,
  `suppliers/`, `purchases/`, `sales/`, `inventory/`, `adjustments/`,
  `ai/forecasting/`, `ai/slow-moving/`, the 5 Phase 3.6 routes —
  `reports/`, `notifications/`, `users/`, `audit-log/`, `settings/` —
  plus `login/`) and 2 new real ones (Phase 4): `logout/`, `profile/`.
- **Views (Phase 4 auth + Phase 5/6/7 real modules)**: `frontend/views.py`'s
  `login`/`logout_view`/`profile_view` (Phase 4); `ProductListCreateView`
  (Phase 5 — GET renders the real `Product` queryset, POST validates via
  `ProductForm` and, in one transaction, creates the product and calls
  `InventoryService.initialize_for_product()` — see §6's Phase 5.5 note);
  `CategoryListCreateView`/`SupplierListCreateView` (Phase 6, identical
  shape — no `InventoryService` involvement, neither module touches
  stock). Phase 7 adds 12 more views for the first time modules with real
  *workflows*, not just CRUD, go live: `PurchaseListCreateView` +
  `PurchaseSubmitView`/`PurchaseApproveView`/`PurchaseRejectView`/
  `PurchaseReceiveView`/`PurchaseCancelView`; `SaleListCreateView` +
  `SaleCancelView`; `AdjustmentListCreateView` +
  `AdjustmentApproveView`/`AdjustmentRejectView`. Every stock-touching
  transition delegates to `PurchaseService`/`SaleService`/
  `AdjustmentService` (Phase 3) — creation views themselves never call
  `InventoryService` directly except via those services (Purchase/
  Adjustment *creation* stays out of stock entirely, matching
  `PurchaseService`'s own docstring: "PO creation isn't part of this
  service"). All action views return JSON for `fetch()`-based row actions
  (confirm()/prompt() dialogs on the client, no bespoke confirmation
  modals built beyond the one genuinely new UI needed — Purchase's
  Receive modal, since partial receiving needs real per-line input).
  Every *other* view (Inventory, Users & Roles, Settings, ...) is still
  the original one-line `render()` — no forms, no querysets, no auth
  checks, no ORM usage.
- **RBAC (Phase 4 mechanism, real since Phase 5)**: `frontend/decorators.py`
  (`require_role`/`admin_required`/`supervisor_required`/`staff_required`)
  and `frontend/mixins.py` (`RoleRequiredMixin`/`AdminRequiredMixin`/
  `SupervisorRequiredMixin`/`AnyStaffMixin`) — translated from
  `02_RBAC.md`'s `apps/rbac/decorators.py`/`apps/rbac/mixins.py`. Phase 4
  proved it only against throwaway views; `AnyStaffMixin` guards
  `ProductListCreateView` (Phase 5), `CategoryListCreateView`/
  `SupplierListCreateView` (Phase 6), and now (Phase 7) create/submit/
  receive across Purchases/Sales/Adjustments; `SupervisorRequiredMixin`
  gets its first real use ever on approve/reject/cancel across the same
  three. **Confirmed live and by test (Phase 7) that `SupervisorRequiredMixin`
  is genuinely a hierarchy** — `required_roles = [UserRole.ADMIN,
  UserRole.SUPERVISOR]` — not an exact-role check that would incorrectly
  lock out Admins; nothing needed fixing here. Inventory/Users & Roles/
  Settings/etc. remain unguarded (see §12/§16). DRF's `BasePermission`
  classes (`IsAdmin` etc.) from the same doc were explicitly out of
  scope — DRF isn't installed.
- **Forms (Phase 5/6/7 — real ModelForms)**: `frontend/forms.py`'s
  `ProductForm` (Phase 5) — server-side enforcement of what the JS modal
  previously only checked client-side (unique SKU/barcode via Django's
  automatic `ModelForm` uniqueness check, non-negative purchase/selling
  price), restricts Category/Supplier choices to `is_active=True`, validates
  uploaded images via `frontend/validators.py`'s new
  `validate_product_image` (`SECURITY.md`'s allowed-extensions/max-size
  rule). Also reconciled two required/optional mismatches between
  `SCHEMA.md` and the Phase 3 mock UI — see `docs/bugsfound.md` BUG-31.
  `CategoryForm`/`SupplierForm` (Phase 6) — same treatment, bigger mismatch:
  the mock modals had fields with no schema backing at all (removed, not
  invented as new columns) and mislabeled most of `Supplier`'s genuinely-
  required fields optional (relabeled) — see BUG-35. Both forms also carry
  a form-only `status` `ChoiceField` (Active/Inactive text, matching the
  existing template `<select>`) that the view maps to `is_active`, the
  same pattern as `ProductForm.initial_stock` being a form-only field
  consumed by the view.
  `PurchaseOrderForm`/`SaleTransactionForm`/`AdjustmentForm`/`ReasonForm`
  (Phase 7) — header-only forms; line items arrive as a JSON-encoded
  `items_json` POST field, parsed by the new shared `parse_line_items()`
  helper (also form-only-field territory: line items aren't a Django
  formset here). Unlike Phase 5/6, checking these three against
  `SCHEMA.md` found no mismatch to fix — see §15's Phase 7 entry.
  `ReasonForm` is shared by `PurchaseOrder.reject`/`InventoryAdjustment.reject`,
  the first form in this project reused across two unrelated models.
- **Validators (Phase 4)**: `frontend/validators.py`'s
  `StrongPasswordValidator` — translated from `SECURITY.md`'s
  `apps/authentication/validators.py`, registered in
  `AUTH_PASSWORD_VALIDATORS` alongside Django's 4 built-in validators.
- Phase 4's auth views (`login`/`profile_view`) still use raw
  `request.POST.get(...)`, matching `01_AUTH.md`'s own reference code —
  `ProductForm` (above) is the first real `ModelForm` in the project, not
  a retrofit onto auth. `accounts/login.html`'s dead `{% if form.* %}`
  template conditionals (referencing a `form` object the view never
  passed) were removed earlier — see §15.
- **Services / API**: `frontend/services.py` (Phase 3) is the only
  service-layer code; nothing in Phase 4 calls it (auth isn't part of the
  stock-mutation service layer). `docs/API_CONTRACTS.md` documents 60
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

  **`User.role` DB constraint (checked Phase 4.5)**: `\d+ users` on the
  real Postgres table confirms the column is `NOT NULL` with **no
  SQL-level default** — `default=UserRole.STAFF` in `models.py` is
  Python/ORM-only (applied when Django constructs a model instance, e.g.
  `.objects.create()`), not a `DEFAULT` clause in the schema. Every user
  created through the ORM always gets a role — safe. The one scenario
  this doesn't cover: a raw-SQL insert or an external bulk-import path
  that bypasses the ORM entirely and forgets `role` would hit the `NOT
  NULL` constraint and fail loudly, not silently create a row with an
  unset/wrong role. Worth re-checking if a future phase ever bulk-creates
  or imports users outside the ORM — not a bug today, nothing to fix.

  **Product creation → `InventoryRecord` (corrected Phase 5.5)**: every
  `Product` gets a matching `InventoryRecord` the moment it's created,
  via the new `InventoryService.initialize_for_product()`
  (`frontend/services.py`) — `current_stock=0`, `reorder_level` copied
  from the product, `status` computed by the existing
  `InventoryRecord.update_status()` (→ `out_of_stock` for zero stock).
  Unlike `increase_stock()`/`decrease_stock()`, this method writes **no**
  `InventoryMovement` row — Phase 5 originally called `increase_stock()`
  here instead, which forced a real movement into the immutable ledger
  with no true cause (see `docs/bugsfound.md`'s Phase 5.5 entry); a
  product's first real stock now only ever arrives via a received
  Purchase Order (`PurchaseService.receive_items()` → `increase_stock()`),
  same as every other module.

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

**Fully completed and real (Phase 4):** login, logout, account lockout,
session timeout, profile update/password change — see §2/§12.

**Fully completed (UI + client-side validation, no persistence):**
Landing page, dashboard shell + charts, Product/Category/Supplier/
Purchase/Sale/Adjustment "Add" modals, Inventory list (read-only by
design), Demand Forecasting page, Slow-Moving & Dead Stock page.

**Fully completed (schema + admin layer):** all 16 documented models,
matching SCHEMA.md exactly — see §6, migrated to PostgreSQL since
Phase 3.7/3.8. All 16 registered and browsable in Django admin — see §5.

**Partially completed:**
- Search/filter controls exist visually on most list pages (Products,
  Suppliers, Purchases, Sales, Inventory, Adjustments) but are **not
  wired** to actually filter the static table rows — only the Intelligence
  pages' filters (`table-filter.js`) actually work.
- Pagination controls exist on several list pages but are non-functional
  (Previous disabled, Next does nothing).
- Approve/reject buttons exist on Purchase/Adjustment pending rows but
  have no click handlers.

**No longer missing**: Reports, Notifications, Audit Log, Users & Roles,
Settings all got real mock pages in Phase 3.6 (§11) — sidebar links
re-enabled, nothing left disabled.

---

## 11. Current UI Pages

- ✅ Landing
- ✅ Login (real, Phase 4 — username/email, lockout, session timeout)
- ✅ Profile (`/profile/`, Phase 4 — new page, not in the sidebar; reached
  via the topbar user-menu dropdown only)
- ✅ Dashboard
- ✅ Products (real, Phase 5 — list + Add modal against the live DB, RBAC-guarded)
- ✅ Categories (real, Phase 6 — list + Add modal against the live DB, RBAC-guarded)
- ✅ Suppliers (real, Phase 6 — list + Add modal against the live DB, RBAC-guarded)
- ✅ Purchases (real, Phase 7 — list + Add modal against the live DB, full submit/approve/reject/receive/cancel workflow, RBAC-guarded)
- ✅ Sales (real, Phase 7 — list + Add modal against the live DB, cancel restores stock, RBAC-guarded)
- ✅ Inventory (list only, read-only by design)
- ✅ Adjustments (real, Phase 7 — list + Add modal against the live DB, approve/reject workflow, RBAC-guarded)
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

**Open items from Backend Phase 4** (real, verified, but with real gaps —
kept together here rather than scattered, since they were all found in
the same phase):

- **RBAC mechanism now applied to 6 real modules — Products (Phase 5),
  Categories, Suppliers (Phase 6), Purchases, Sales, Adjustments (Phase 7).**
  `AnyStaffMixin` guards every create/list/submit/receive view;
  `SupervisorRequiredMixin` (first real use, Phase 7) guards every
  approve/reject/cancel view; logged-out requests redirect to login,
  confirmed live and by test across all six. Every *other* page view
  (Inventory, Users & Roles, Settings, Reports, Notifications, Audit Log)
  is still a bare `render()` with no `@login_required` and no role
  check — open to anyone, logged in or not, until those modules get
  wired in the same way. This remains a real, current security gap for
  every module except the six above.
- **Phase 5 verification surfaced two pre-existing quirks in the shared
  modal architecture** (`modal-form.js`/`form-validation.js`), neither
  introduced this phase — see `docs/bugsfound.md` BUG-32/33 for full
  detail: (1) a field that's both required and non-negative can show a
  blank error on blur even while its value is still negative (cosmetic —
  submit-time re-validation still blocks it, confirmed live); (2)
  `extraValidate()` runs unconditionally even when standard validation
  already failed, which only became costly once Product's `extraValidate`
  started doing real server work — worked around locally in
  `product-form.js` (skip the request if a `.has-error` field already
  exists), not by changing the shared files.
- **4 documentation inconsistencies found and resolved, source disclosed
  rather than silently picked:**
  1. `MAX_LOGIN_ATTEMPTS`/`LOCKOUT_DURATION`: `01_AUTH.md`'s business
     rules table calls these "configurable" but `SCHEMA.md`'s
     `SystemSettings` has no matching fields — only `ENVIRONMENT.md`
     documents them, as env vars. Used as env vars (`MAX_LOGIN_ATTEMPTS`/
     `LOCKOUT_DURATION` in `.env`, read in `config/settings.py`); no
     `SystemSettings` fields added to work around the gap, per this
     phase's explicit instruction.
  2. `01_AUTH.md`'s own `login_view` reference code checks
     `if not user.is_active` *after* a successful `authenticate()` call —
     but Django's default `ModelBackend` already refuses to authenticate
     an inactive user (returns `None`), making that branch unreachable
     dead code as written. Fixed: the `is_active` check now happens
     *before* `authenticate()`, giving a correct "inactive" message
     without also incrementing the failed-attempt counter for a
     deactivated account's otherwise-correct password.
  3. `01_AUTH.md`'s Audit Actions table lists `ACCOUNT_LOCKED` and
     `PASSWORD_CHANGED`, but neither is actually called anywhere in the
     module's own reference code (`login_view` only logs
     `LOGIN_FAILED` even on the attempt that triggers a lock;
     `profile_update_view` never logs a password change at all). Both are
     now actually called — `ACCOUNT_LOCKED` when a lockout triggers,
     `PASSWORD_CHANGED` when a password change succeeds — matching the
     documented action table over the doc's own incomplete example code.
  4. `01_AUTH.md`'s `profile_update_view` reference code calls
     `user.set_password(new_password)` directly, never calling
     `validate_password()` — skipping `AUTH_PASSWORD_VALIDATORS`
     (including the new `StrongPasswordValidator`) entirely for this one
     path. Fixed: `validate_password()` is now called first; a weak
     password is rejected with the same messages the validators would
     give anywhere else, before `set_password()` ever runs.
- **Two fallbacks explicitly deferred to this phase (project_memory.md
  §13/§17) are now removed, not kept as defense-in-depth**: `frontend/
  notifications.py`'s `notify_supervisors()` `is_staff`/`is_superuser`
  fallback, and `frontend/services.py`'s `_user_display_name()` helper
  (deleted entirely, call site now reads `submitted_by.full_name`
  directly). Both existed only to cover the pre-Phase-3.7 window where
  `role`/`full_name` didn't exist on the active `AUTH_USER_MODEL` — now
  permanently resolved, since `frontend.User` (with both fields required,
  non-blank) is the only user model this project will ever run against.
  Kept as "dead code defense-in-depth" would have meant carrying
  unreachable branches with no realistic failure mode they still guard
  against.
- **RESOLVED Phase 4.5**: `accounts/login.html`'s "Forgot password?" was a
  live link to `accounts:password_reset` (`django.contrib.auth.urls`).
  **Correcting this document's own earlier claim that it 500'd**: verified
  live and it does not — `django.contrib.admin`'s bundled `registration/
  password_reset_*.html` templates are found via `APP_DIRS=True` (a
  lesser-known Django convenience: the admin app ships fallback templates
  for the whole default reset flow, not just its own `/admin/` pages), so
  all of `password_reset/`, `password_reset/done/`, and `reset/done/`
  actually render `200` — just with Django-admin styling, not Stockwell's,
  and full email-send behavior was never verified (out of scope). Either
  way, a real reset flow — styled or not — is still explicitly deferred,
  so the link was disabled the same way BUG-08 disabled the 5 sidebar
  links: `<span aria-disabled="true" tabindex="-1" title="Coming soon">`,
  no `href`. `config/urls.py`'s `django.contrib.auth.urls` include is now
  fully unreferenced by any template (nothing left points at the
  `accounts:` namespace) but was deliberately left in place — dead but
  harmless, and removing it was outside this cleanup's explicit scope.

**Missing backend**: no API, no AI execution, no Celery. RBAC not wired
into any real module view yet (above). Migrations + `AUTH_USER_MODEL`
resolved Phase 3.7 (§15); the service layer (§5) exists and login/logout/
profile now call the ORM directly, but every other view still doesn't.

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
  **Phase 5 briefly violated this decision without noticing** — the new
  Add Product modal's "Initial stock" field was wired to a real
  `InventoryMovement` via `InventoryService.increase_stock()`, a direct
  user-form-triggered movement this exact bullet had already ruled out.
  **Corrected Phase 5.5**: the field was removed; product creation now
  only ever produces a zero-stock `InventoryRecord` with no movement — see
  §5/§6 and `docs/bugsfound.md`'s Phase 5.5 entry for the full story.
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
- **SKU auto-generation format (`PRD-YYYYMMDD-XXXX`) has no source in any
  doc — disclosed, not silently invented (Phase 5, disclosure added
  Phase 5.5).** `03_PRODUCTS.md` documents this exact format
  (`generate_sku()`) and the mock UI's own "SKU (optional)" label/
  placeholder (`SKU-00000`) already implied auto-generation before any
  backend existed — so the *feature* (auto-generate when blank) traces to
  both; the specific *format* traces only to `03_PRODUCTS.md`'s reference
  code, reused verbatim in `ProductForm._generate_sku()`
  (`frontend/forms.py`) rather than inventing a different one. Flagged
  here per this project's standing practice (§17 had already listed this
  exact gap) of giving every deliberate doc deviation its own explicit
  entry rather than leaving it to only exist in chat/session history —
  same treatment as the 9999-day sentinel and the single period toggle
  above. No retry-on-collision loop, matching `PurchaseOrder`/
  `SaleTransaction`'s identical random-suffix pattern (§6).
- **`InventoryService.initialize_for_product()` added as its own method
  (Phase 5.5) rather than reusing `increase_stock()` with `quantity=0`.**
  `increase_stock()`'s whole contract is "log a real movement with a real
  cause" — every call site writes an `InventoryMovement` row unconditionally.
  Product creation has no real cause (no stock physically moved), so
  reusing it — even at `quantity=0` — would still write a movement row
  describing an event that didn't happen. A distinctly-named method that
  writes no movement at all keeps the ledger honest and keeps
  `InventoryService` as the single place `InventoryRecord` rows are
  created or mutated either way (see §5/§6).

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
21. **Phase 3.9: reconcile docs against code** — found `docs/bugsfound.md`
    was stale, not the code: BUG-13/20/21/22/25 were all genuinely fixed
    back in Phase 3.4 (confirmed by reading `frontend/models.py`/
    `services.py` directly, not by trusting either doc), but
    `bugsfound.md`'s status column was never updated to match — this
    document's own timeline (item 13 above) had it right the whole time.
    Root cause: Phase 3.4's doc-sync step only touched `project_memory.md`
    (per the standing update-after-every-change rule), and `bugsfound.md`
    was never in that rule's scope, so it silently drifted. Also fixed two
    unrelated stale spots: §3's migrations line and §5's route count
    (12 → 17, missing the 5 Phase 3.6 routes). No code changes — all 5
    fixes were already real. 53/53 tests still passing.
22. **Backend Phase 4: Authentication & RBAC** — real `login`/
    `logout_view`/`profile_view` against `frontend.User`: username-or-email
    identifier, Argon2 hashing (`django[argon2]`), `StrongPasswordValidator`
    (`frontend/validators.py`), account lockout and session timeout, both
    verified live against the real Postgres dev DB (not just tests) —
    lockout blocked a subsequently-*correct* password, session expiry
    matched a changed `SystemSettings.session_timeout_seconds` exactly.
    RBAC mechanism built (`frontend/decorators.py`, `frontend/mixins.py`,
    translated from `02_RBAC.md`) and proven against throwaway views —
    explicitly not wired into any real module view yet (see §12, next
    priority). Found and fixed 4 doc/reference-code inconsistencies in
    `01_AUTH.md` (env-var lockout config vs. `SystemSettings`, an
    unreachable `is_active` check, `ACCOUNT_LOCKED`/`PASSWORD_CHANGED`
    action-table entries never actually called, `set_password()` bypassing
    `validate_password()`) — see §12 for the full list and what changed.
    Closed 2 fallbacks explicitly deferred to this phase since Phase 3.5/
    3.7 (`notify_supervisors()`'s `is_staff`/`is_superuser` branch,
    `_user_display_name()`'s `get_full_name()` chain) — both removed
    outright, not kept as defense-in-depth, since they guarded a state
    (`AUTH_USER_MODEL` ≠ `frontend.User`) that can no longer occur. Added
    `User.get_full_name()`/`get_short_name()`/`get_initials()` (methods
    only, no migration) so the Phase 3.6 topbar's existing template calls
    resolve to the real user instead of always falling back to mock data;
    wired the topbar user-menu into a working dropdown (`My Profile`/
    `Log out`). 75 tests passing (was 53).
23. **Phase 4.5: pre-Phase-5 safety check** — confirmed `User.role` is
    `NOT NULL` with no DB-level default (§6) — safe via the ORM, a
    documented risk only for a hypothetical raw-SQL bulk-import path.
    Confirmed the weak-password regression test for BUG-30 already
    existed and passes. Fixed the "Forgot password?" link on the login
    page — disabled it the same way BUG-08 disabled the sidebar links
    (`aria-disabled`, no `href`, "Coming soon"), and **corrected this
    document's own earlier claim** that the route it pointed to 500'd:
    verified live, it doesn't — `django.contrib.admin`'s bundled
    `registration/` templates render the whole default reset flow with
    admin styling, not a `TemplateDoesNotExist` crash. Disabled anyway,
    since a real (Stockwell-styled) reset flow is still deferred either
    way. No code logic changed — CSS/template + doc corrections only.
24. **Backend Phase 5: Products, end to end** — `ProductForm`, a real
    `ProductListCreateView` (`AnyStaffMixin`-guarded GET+POST), and
    `products/products.html` wired to the real DB, keeping the existing
    modal.js/form-validation.js/dom-utils.js/modal-form.js architecture
    untouched — only `product-form.js`'s `extraValidate`/`onSubmit` point
    at the real endpoint now (a synchronous XHR inside `extraValidate`,
    not `fetch` in `onSubmit`, since `modal-form.js` closes/resets the
    modal unconditionally right after `onSubmit()` runs — see
    `product-form.js`'s file header). Every created product gets a real
    `InventoryRecord` via `InventoryService.increase_stock()` in the same
    transaction as the product save. `MEDIA_ROOT`/`MEDIA_URL` configured
    and dev-served (BUG-10 never finished this in Phase 1). Verified live
    with Playwright end to end: logged-out `/products/` redirects to
    login; empty submit shows inline required-field errors and keeps the
    modal open; a negative price is blocked at submit time (client-side
    display of that block has a cosmetic pre-existing gap — BUG-32);
    duplicate SKU is rejected server-side with a visible inline error,
    modal stays open; a valid submit creates the product, reloads, the
    row persists after a fresh reload; ESC and overlay-click still close
    the modal; reopening shows a clean form; an uploaded image saves to
    `media/products/` and is servable at `/media/products/<name>`; the
    product's `InventoryRecord`/`InventoryMovement`/`AuditLog` rows all
    exist afterward. Found 3 new issues — 2 pre-existing in the shared
    modal architecture (not fixed, kept out of scope), 1 in the Phase 3
    mock UI's required/optional labels (fixed) — see `docs/bugsfound.md`
    BUG-31/32/33. **Corrected in Phase 5.5 (item 25 below)**: the
    `InventoryService.increase_stock()` call this item describes turned
    out to violate this document's own §13 architecture decision — see
    item 25 and `docs/bugsfound.md`'s Phase 5.5 entry (BUG-34).
25. **Phase 5.5: correct the inventory business rule + fix
    `modal-form.js`'s async gap.** Two fixes, one dev-DB cleanup, one
    disclosure:
    - **Inventory rule**: Phase 5's `increase_stock()` call (item 24)
      wrote a real `InventoryMovement` for every new product with no true
      cause — none of the 4 documented `movement_type`s describe "a
      product was catalogued." The Add Product modal's "Initial stock"
      field (a Phase 3 mock-UI holdover) was the actual source of the
      quantity being passed — flagged as a real decision rather than
      silently resolved; chose (per explicit direction) to remove the
      field entirely rather than invent a 5th documented movement type.
      Added `InventoryService.initialize_for_product()` (§5/§6): creates
      the `InventoryRecord` at `current_stock=0`, correct `out_of_stock`
      status, zero `InventoryMovement` rows. Matches `03_PRODUCTS.md`'s
      own reference code and this file's pre-existing §13 decision
      exactly. Deleted the 3 Phase 5 test products that had gone through
      the old, incorrect path (with their now-inconsistent
      `InventoryMovement`/`AuditLog` rows) rather than leaving mislabeled
      ledger entries sitting in the dev DB.
    - **`modal-form.js` async gap**: added a documented Promise contract
      to `onSubmit` (§4) — an async `onSubmit` now keeps the modal open
      until it settles, closing only on success — so `product-form.js`
      could drop its synchronous-XHR-inside-`extraValidate` workaround
      for a real `fetch()`. Every future "Add X" module gets this for
      free once it's wired to a real endpoint. Confirmed live: the POST
      to `/products/` now shows as a `fetch` request, and the page
      remains fully interactive (JS keeps running, the DOM stays
      scriptable) while a request is in flight — throttled the request to
      1.5s via CDP and confirmed the page didn't hang for that window.
    - **SKU auto-generation disclosure** (§13, §17): no code change —
      gave the `PRD-YYYYMMDD-XXXX` format its own explicit architecture-
      decision entry, closing the exact gap §17 had already flagged.
    - Re-verified live end to end after both fixes: empty submit, valid
      submit, duplicate SKU, ESC/overlay-click all still behave exactly
      as Phase 5 verified — this was a correctness/architecture fix, not
      a UX change. 75/75 tests still passing throughout.
26. **Post-Phase-5.5 check: was BUG-33 actually fixed, and was the
    inventory-rule fix covered by a test?** Two direct questions, answered
    by reading code rather than restating the item-25 summary:
    - **BUG-33**: confirmed still present in `modal-form.js` —
      `extraValidate()` is called unconditionally either way (see the
      submit handler's two unconditional statements, `isStandardValid`
      and `isExtraValid`). Item 25's "moot for Products" claim holds only
      for Products (its real work moved to `onSubmit`, which *is* gated);
      Purchase/Sale's `extraValidate` is unaffected today only because
      it's still synchronous — it will reproduce the same problem the
      moment either gets server-side work inside `extraValidate` instead
      of `onSubmit`. Not fixed at the source; flagged for Phase 7.
    - **Test coverage**: none existed for the item-25 fix. Added
      `InventoryServiceTests.test_initialize_for_product_creates_zero_stock_record_with_no_movement`
      (service-level) and a new `ProductCreateViewTests` class (4 tests,
      real HTTP round-trip through `/products/` — the original bug was in
      the *view*, not the service, so a service-only test wouldn't have
      caught it). Verified the new test actually guards the regression by
      temporarily reverting `views.py` to call `increase_stock()` again —
      it failed loudly (`1 != 0`) — then restored the fix. 80/80 tests
      passing.
27. **Phase 5.6: fix BUG-33 at its source, in `modal-form.js`.** Item 26
    confirmed it was still live in the shared file; this phase fixed the
    actual control flow rather than continuing to work around it per
    module. One-line change to the submit handler:
    `isExtraValid = isStandardValid && (config.extraValidate ? config.extraValidate() : true)`
    — `extraValidate()` is now short-circuited, never called once
    `validateAll()` has already failed. Scope was `modal-form.js` only
    (per this task's explicit instruction) — `product-form.js`/
    `purchase-form.js`/`sale-form.js` were not touched, since the shared
    file's contract becoming correct is exactly the point: every module
    inherits it automatically, including ones that don't exist yet.
    Verified live (not just by reading the code) with a call-counting
    wrapper injected around `LineItems.validate()`: Purchase's
    required-Supplier-empty submit dropped from 1 call to 0; filling
    Supplier in restored the call, proving normal validation is
    unaffected. Sale has no `requiredFieldIds` at all, so nothing changed
    for it either way (no required field exists to short-circuit
    against) — confirmed, not just assumed. Header comment updated with
    the new ordering guarantee, alongside the existing Phase 5.5
    `onSubmit` Promise-contract note. 80/80 tests passing (no test
    exercises this JS path directly — coverage here is the live
    verification above, matching how `modal.js`/`modal-form.js` have
    always been verified, see §15 items throughout).
28. **Backend Phase 6: Categories & Suppliers.** Mechanical repetition of
    Phase 5's pattern, as instructed — `CategoryForm`/`SupplierForm`,
    `CategoryListCreateView`/`SupplierListCreateView` (`AnyStaffMixin` on
    GET+POST), real queryset rendering, `fetch()`-based `onSubmit` used
    from the start (no sync-XHR workaround needed — `modal-form.js`'s
    Promise contract already existed by this phase). Neither module has
    an approval workflow or touches `InventoryService`. Found the same
    class of mock-UI/schema mismatch as BUG-31, bigger this time:
    `categories.html`'s mock had a "Parent category" hierarchy and
    "Category code" with no schema backing at all; `suppliers.html`'s
    mock had `code`/`city`/`country`/`postal_code`/`website`/`tax_id`/
    `notes` fields with no schema backing, and mislabeled nearly every
    genuinely-required `Supplier` field as optional. Fixed by trimming
    the unbacked fields from both templates and correcting the required
    labels — not by inventing new model columns, per this phase's
    explicit instruction (`docs/bugsfound.md` BUG-35). Supplier's single
    mock "name" field also couldn't cover both of the model's two
    required name fields (`supplier_name`/`company_name`) — mapped the
    existing field to `supplier_name` by literal name match and added a
    new "Company name" field for `company_name`, disclosed as a judgment
    call rather than picked silently. Verified live end to end for both
    modules: logged-out blocked, empty submit blocked with inline errors,
    duplicate name (Category)/duplicate email (Supplier) rejected with a
    visible error and the modal staying open, Active/Inactive status
    confirmed mapping to `is_active` correctly in the DB, valid submit
    persists after a fresh reload, ESC/overlay-click/clean-reopen all
    still work. No new automated tests this phase either, matching
    Phase 5's own precedent — verified live instead. 80/80 tests still
    passing (none broken).

---

## 16. Next Priorities

Highest priority first:

1. **Wire the RBAC decorator/mixin (§5, Phase 4) and the service layer
   into real module views, together, module by module** — Products
   (Phase 5), Categories, Suppliers (Phase 6), Purchases, Sales,
   Adjustments (Phase 7) are done, see §2/§5/§12/§15. Inventory is next —
   it's documented as read-only/API-driven only (§6/§13), so "wiring it
   in" means a real list view, not a create form. After that, the
   backlog is the 5 Phase 3.6 mock pages (Reports, Notifications, Users &
   Roles, Audit Log, Settings, §11) — none of which involve
   `InventoryService` or an approval workflow, closer to Categories/
   Suppliers' shape than Purchase/Sale/Adjustment's. Until this happens,
   every page except login/logout/profile and the 6 Phase 5/6/7 modules
   remains open to anyone (§12) — treat this as a security gap, not just
   an incompleteness note.
2. **Reconcile `INDEX.md`'s broken links**; write the missing module docs
   (`04_SUPPLIERS.md`, `08_ADJUSTMENTS.md`, `09_DASHBOARD.md`,
   `12_SEARCH.md`, `14_SETTINGS.md`).
3. **Then** password reset (deferred from Phase 4), DRF API layer + its
   `BasePermission` classes (`02_RBAC.md`, deferred from Phase 4 — DRF
   still isn't installed), Celery (needed for the notification email
   `.delay()` upgrade — see §2), and the real AI pipelines — in that
   order.

---

## 17. Future Work

Grouped by module, per the documentation:

- **Database schema**: ✅ **done** (Backend Phase 1, §6) — all 16 models
  implemented matching SCHEMA.md.
- **Admin registration**: ✅ **done** (Backend Phase 2, §5) — all 16
  models registered, and now actually usable for data-browsing (migrations
  applied Phase 3.7, see §12). Still pending: seed data.
- **Auth**: ✅ **done** (Backend Phase 4, §2/§5) — real login (username or
  email)/logout/profile update against `frontend.User`, session timeout,
  account lockout, Argon2 hashing, `StrongPasswordValidator`. Still
  needed: password reset via email (explicitly deferred).
- **RBAC**: ✅ **mechanism done** (Backend Phase 4, §5) —
  decorators/mixins per the 3-role matrix in `02_RBAC.md`, proven against
  throwaway views. Still needed: applying it to every real module view
  (§16 top priority — this is the actual enforcement, not yet real
  anywhere), template-level role conditionals (`{% if
  request.user.role == ... %}` — trivial once views pass real `request.user`
  context, not attempted yet), DRF `BasePermission` classes (needs DRF).
- **Products**: real CRUD — ✅ **create + list done** (Phase 5, §2/§5),
  SKU auto-generation implemented per `03_PRODUCTS.md`'s own documented
  format and disclosed as its own architecture decision (§13, Phase 5.5 —
  this bullet's "needs its own documented rule" gap is resolved), image
  upload validation done (§5). Still pending: edit/deactivate views,
  soft-delete (`is_active = False`, per `03_PRODUCTS.md`'s business
  rules — no deactivate view exists yet, only create/list).
- **Categories**: real CRUD — ✅ **create + list done** (Phase 6, §2/§5).
  Still pending: edit/deactivate views.
- **Suppliers**: real CRUD — ✅ **create + list done** (Phase 6, §2/§5; no
  dedicated doc exists — see §12; built from `SCHEMA.md` + the existing
  `suppliers.html` UI, reconciled per BUG-35). Still pending: edit/
  deactivate views.
- **Purchases/Sales/Adjustments services**: ✅ **done** (Backend Phase
  3/3.4, §2) — `PurchaseService`, `SaleService`, `AdjustmentService`, all
  with audit/notification hooks (Phase 3.5). ✅ **Now wired to real
  views/forms too** (Phase 7, §2/§5/§15) — full create + approval-workflow
  UI for all three, every stock mutation routed through the service
  layer. Still pending: edit views, PO/sale detail pages (this project
  has no per-entity detail routes anywhere yet, by design — see §13).
- **Inventory service**: ✅ **done** (Backend Phase 3/3.8, §2) —
  `InventoryService`, `select_for_update()`-safe. Still just a read-only
  list page (§6/§13 — documented as API-driven only, deliberately no
  create form) — "wiring it in" (§16 #1) means RBAC + a real queryset on
  the existing list view, not a new create flow.
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
- **`requirements.txt` has 9 packages, not the ~15 in `TECH_STACK.md`.**
  DRF, Celery, Redis, scikit-learn, WhiteNoise, Gunicorn, WeasyPrint are
  all documented but **not installed**. Pillow (Phase 1),
  psycopg+psycopg-binary (Phase 3.8, the Postgres switch), and
  argon2-cffi (Phase 4, `PASSWORD_HASHERS`) are the only additions beyond
  Django's own base install so far. Any task assuming a
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
