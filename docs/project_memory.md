# Stockwell — Project Memory

> **Read this file first, before any other document, before writing any code.**
> This file is the permanent engineering memory of the project. It reflects the
> **actual current state of the repository** as of 2026-08-15, updated after:
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
> **(16) Backend Phase 8** — the last 5 mock pages (Reports, Notifications,
> Users & Roles, Audit Log, Settings) are all real now: real querysets/
> forms, real RBAC (`AdminRequiredMixin` on Audit Log/Users/Settings,
> `SupervisorRequiredMixin` on Reports, plain `LoginRequiredMixin` on
> Notifications), no mock data left anywhere in the app except Inventory's
> deliberately-unwired read-only list. Reports exports real PDF (ReportLab,
> chosen over `10_REPORTS.md`'s own WeasyPrint example for zero native
> deps — disclosed choice within the doc's own stated options, see §15)
> and CSV for all 9 documented types. Notifications' topbar badge actually
> polls now. Users & Roles required one disclosed field-list deviation —
> a required password field the mock didn't have, since a `User` without
> one can never log in. 125 tests passing (was 100). See §15 for the full
> writeup. **(17) Phase 8.6 — 4 live-usage bug fixes** (BUG-37 through
> BUG-40, see `docs/bugsfound.md`): Users & Roles' filter was silently
> dead (missing `table-filter.js` `<script>` tag); `TIME_ZONE` was `'UTC'`
> — changed to `'Asia/Dhaka'` (`USE_TZ` stays `True`; storage was always
> correct UTC, this was display-only, confirmed against a real AuditLog
> row); the dashboard greeting was hardcoded "Good morning" regardless of
> time (now computed server-side from `timezone.localtime().hour`); and it
> showed "Amara" for every user (`dashboard.html` referenced a
> `first_name` field `frontend.User` doesn't have — now uses the existing
> `get_short_name()`). Cross-role Playwright sweep (Purchases/Adjustments/
> Sales/Users action buttons, all 3 roles) found no other visible-but-dead
> or wired-but-misgated buttons — see §15. 131 tests passing (was 125).
> **(18) Phase 8.7 — wired table filtering** on Products/Suppliers/
> Purchases/Sales/Adjustments (BUG-37 case (c)): missing `table-filter.js`
> script tags, missing control `id`s, missing `data-*` row hooks, and
> missing `value=` attributes on status/type `<select>` options (defaulted
> to display text instead of the model's real choice value) — all fixed,
> `table-filter.js` reused unchanged. Categories has no filter controls to
> wire; **Inventory's page turned out to still be 100% mock** —
> `inventory()` is a one-line `render()` with no queryset, previously
> mislabeled ✅ in this file (now corrected, see §2/§11/§16) — its real
> build-out is still outstanding, separate from filter-wiring. 131 tests
> still passing. **(19) Phase 8.8 — documentation-integrity audit**, no
> code changes: read every real view in `frontend/views.py` against every
> ✅ claim in this file. Found one more mislabeled page beyond Inventory —
> **the Dashboard**: only its greeting/user name are real (Phase 8.6);
> every KPI card, both Chart.js charts, and all 4 widgets (Stock Alerts,
> Pending Approvals — inert Approve/Reject buttons included, Recent
> Activity, AI Insights) are hardcoded, and `dashboard()` passes no
> queryset context at all — corrected here (see §2/§11/§16). Everything
> else marked ✅ checked out genuinely real, including all 9 Reports
> builders (`frontend/reports.py`) — no hardcoded rows anywhere, though 2
> of the 9 (AI Forecast/Classification) are real queries against tables
> nothing populates yet until AI is built (Phase 10/11), an honest gap,
> not a fake one. Demand Forecasting/Slow-Moving were already correctly
> disclosed as "All static/mocked" and needed no correction. Root cause
> across all three misses (this one, Phase 3.9, Phase 4.5): a page whose
> mock template renders cleanly gives no visual signal that its data is
> fake — verifying the view's actual context, not how the page looks, is
> the only reliable check; worth making a standing habit for any future
> ✅ claim in this file, not just at these three checkpoints.
> **(20) Phase 8.9 — built the real Inventory list view**, closing
> BUG-37's Inventory portion. `InventoryListView` (`AnyStaffMixin`,
> matching `07_INVENTORY.md`'s own `@staff_required` = all 3 roles in this
> project's RBAC) replaces the one-line `render()` with a genuine
> `InventoryRecord` queryset — status read straight off the model, not
> recomputed. Real rows, real KPI/stat-strip aggregates, real "last
> movement" column, filters wired to `table-filter.js`. Confirmed strictly
> read-only: no `<form>` anywhere, no mutation call in the view, live
> `POST /inventory/` → `405`. 5 new tests — 136/136 passing (was 131).
> Every module now has a real view; only the Dashboard (Phase 8.8 finding)
> remains mock. **(21) Phase 8.95/8.95.1 — `docs/09_DASHBOARD.md` written
> and approved**: no `REQ` range or spec ever existed for the Dashboard
> (`INDEX.md` linked to a file that didn't exist, BUG-17), so every KPI/
> chart/widget was defined from scratch against `API_CONTRACTS.md` +
> `SCHEMA.md` before any code was written — 8 disclosed decisions (30-day
> KPI trends, chart windows, a single `DASHBOARD_PREVIEW_ROWS` constant,
> Pending Approvals read-only not live-action, Recent Activity
> admin/supervisor-only per `13_AUDIT.md`'s "Admin only" rule, 3 fields
> kept beyond `API_CONTRACTS.md`'s documented payload, "Active suppliers"
> over raw total, "Any role" as the page-wide default) — all approved,
> none left open. **(22) Phase 8.96 — built it for real**, closing BUG-41.
> `dashboard()` now computes every value from real `Sum`/`Count`/
> `annotate` queries, zero `|default:"..."` fabrication remains (the one
> exception — the greeting-name fallback — predates this and isn't a
> fabrication, see BUG-40). AI Insights deleted outright, not shown as an
> empty state. Pending Approvals has no Approve/Reject buttons anywhere.
> Recent Activity confirmed absent from the *rendered HTML* for staff, not
> just hidden. Live-verified against real Postgres, all 3 roles: every
> KPI/stat matched a direct manual DB query exactly. 8 new tests —
> 144/144 passing. **Every page in the app is now genuinely real** — the
> mock-but-marked-done list Phase 8.8 opened is empty; the one open item
> is `dashboard()` still having no RBAC/login gate at all (§12).
> **(23) Phase 8.97 — closed the dashboard auth gap + a full-app wiring
> audit.** Part A (BUG-42, fixed): `dashboard()` converted to
> `DashboardView(AnyStaffMixin, View)` — anonymous access now `302`s to
> login; all 3 roles unaffected; Recent Activity's existing
> `is_authenticated` check is now belt-and-suspenders. Part B: audited
> every one of the app's 31 routes against actual code (not prior ✅
> claims — this file's claims have been wrong 3 times before: Phase 3.9,
> 4.5, and Inventory/Dashboard in 8.7/8.8) for real-vs-mock views, correct
> auth/RBAC, dead controls, and every `|default:`/hardcoded-row/hardcoded-
> stat tell. Found two more real gaps, both reported, neither fixed this
> session per the task's explicit scope: `demand_forecasting`/
> `slow_moving_dead_stock` also have no auth requirement (BUG-43, lower
> severity — both pages are still honestly-disclosed mock, no real data to
> expose); "Export"/"Export CSV" buttons on Products/Suppliers/Audit Log
> are decorative, never individually named before (BUG-44). Everything
> else checked out: every other view is genuinely real with the correct
> mixin, no orphaned fabricated `<tr>` rows or hardcoded stats anywhere,
> and every remaining `|default:"..."` hit is a legitimate per-field null
> fallback or the one already-reviewed anonymous-identity fallback — not a
> new fabrication. 1 test updated + 1 added — 145/145 passing.
> **(24) Phase 8.98 — made every button real.** Built the Movement History
> page (BUG-45): `/inventory/movements/` (`MovementHistoryListView`,
> `AnyStaffMixin`) over the real, already-complete `InventoryMovement`
> ledger — server-side date-range filtering + real `Paginator` pagination
> (the ledger grows unbounded forever, so client-side-only filtering would
> only ever see one page), client-side search/type filtering on top of
> that, an optional `?product=<id>` narrowing used by each Inventory row's
> own link. Wired real CSV export on Products/Suppliers/Audit Log
> (BUG-44) and Movement History, all reusing `frontend/reports.py`'s
> existing `generate_csv_response()` — no new export mechanism — with
> auth matching each source page exactly. Removed the global topbar
> search box (present on every page, including the Dashboard) — it never
> had any JS behind it at all. Found and fixed two small things while
> building: a latent `RuntimeWarning` in `reports.py`'s `_date_bounds()`
> (naive datetime against a tz-aware field — BUG-46, silently correct via
> Django's coercion, now explicit via `timezone.make_aware()`) and a
> flaky pre-existing test (`NotificationViewTests` asserting on a bare
> `'T3'` substring against a page containing a random CSRF token). 21 new
> tests — 156/156 passing (was 145). One known gap remains, unrelated to
> this phase and already tracked: `demand_forecasting`/
> `slow_moving_dead_stock` still have no auth requirement (BUG-43).
> **Closed, Phase 8.99j** — `SupervisorRequiredMixin`, both server-side
> and nav-link gating.
> **(25) Phase 8.98a — topbar spacing investigation + real Change
> Password modal.** Part 1: investigated a reported topbar-badge
> left-shift regression exhaustively (9 viewport widths 480–1440px,
> Dashboard/Products/Profile, sidebar open/closed, all 3 roles) and
> **could not reproduce it** — `.topbar-actions`'s `margin-left: auto`
> (Phase 8.98) sits correctly flush-right in every configuration tested,
> confirmed via `getBoundingClientRect()`, not just visual inspection. No
> code change made; likely explanation was a stale browser cache of
> `dashboard.css` from mid-edit (this dev setup has no cache-busting on
> static URLs) — **confirmed correct**: a hard refresh (Ctrl+Shift+R)
> resolved it for the user. No residual code issue.
> Part 2: password change moved off `profile_view`'s old inline "new
> password" field (which had no current-password check and no confirm
> field — real gaps) into a real modal + dedicated
> `change_password_view`/`/profile/change-password/` endpoint, reusing
> the existing modal.js/modal-form.js recipe and the same
> `validate_password()`/`StrongPasswordValidator` chain, not rewritten.
> Verified live: wrong current password rejected, weak new password
> rejected (with the real validator message), mismatched confirmation
> rejected, a valid change succeeds and the user can immediately log in
> with the new password; `PASSWORD_CHANGED` audit log + notification still
> fire (same `frontend/audit.py`/`frontend/notifications.py` calls,
> unchanged). 3 old tests migrated to the new endpoint + 4 new — 160/160
> passing (was 156).
> **(26) Phase 8.98b — Purchases Expected Delivery + date guard.**
> `expected_delivery` already existed on `PurchaseOrder` and in
> `PurchaseOrderForm` (SCHEMA.md's own field) — no migration needed,
> confirmed via `makemigrations --check`. The real gaps were display (no
> table column) and validation (no past-date guard), both closed: a real
> "Expected delivery" column in the purchases table, and a real,
> server-side `clean_expected_delivery()` rejecting a past date, computed
> against Asia/Dhaka's current date (`timezone.localdate()`) rather than
> the OS clock — verified by POSTing a past date directly, bypassing the
> client entirely (`400`, real field error, no PO created). `order_date`
> stays `auto_now_add=True` (unchanged, matches SCHEMA.md) — never user-
> submitted, always exactly "today" at save time, so "not before
> order_date" collapses into the same past-date check, not a second rule
> — explicitly reported rather than building a redundant check against a
> value that can't exist yet at form-validation time. Client-side, the
> date input's `min=` is the same server-computed Asia/Dhaka date passed
> into the template, not the browser's local clock guessing. 5 new tests
> — 165/165 passing (was 160).
> **(27) Phase 8.98c — moved tax onto Product, auto-calculated on every
> transaction.** `Product.tax_rate` (`DecimalField`, default 0%) is new —
> undocumented in `SCHEMA.md`/`API_CONTRACTS.md` (both still describe `tax`
> only as a per-line `PurchaseOrderItem`/`SaleItem` field), a disclosed
> architecture decision (see §13), same treatment as the SKU-format
> decision. The tax input was removed from the Purchase/Sale line-items
> editor (`line-items.js`) entirely — it's now a read-only per-line display
> sourced from the selected product's own `data-tax-rate` option attribute;
> Adjustment never had a tax field to begin with (confirmed, not a code
> change). `frontend.forms.parse_line_items()` — the one shared chokepoint
> both Purchase and Sale line items already passed through — now always
> sets `tax = product.tax_rate`, ignoring any client-submitted value even
> if one is present; `SaleService.create_sale()` independently re-derives
> it from the product too, as defense in depth, satisfying the task's
> literal "never from a form field" instruction at both layers. The
> previously-duplicated `line_total` formula (flagged as frontend/tech
> debt in §12 since Phase 3) is now one function,
> `frontend.pricing.calculate_line_total()` — a new dependency-free module
> (avoids a circular import: `models.py` can't import `services.py`, which
> already imports `models.py`) — used by both `PurchaseOrderItem.save()`
> and `SaleService.create_sale()`. `tax` stays a real stored column on
> `PurchaseOrderItem`/`SaleItem` (not derived at read-time) so it's a
> historical snapshot — confirmed live: changing a product's `tax_rate`
> after a transaction leaves that transaction's stored `tax`/`line_total`
> untouched, but a new transaction created afterward picks up the new
> rate. Stock/ledger logic was never touched — confirmed by reading every
> line changed against `InventoryService`/`InventoryMovement` (BUG-20's
> immutability), no entanglement found, matching the task's own "stop and
> flag if this touches stock" scope guard. Dev DB wiped and reseeded (new
> `seed_dev_data` management command, DEBUG-only like `seed_test_users`) —
> 4 categories, 3 suppliers, 10 products with varied `tax_rate` (0%, 5%,
> 7.5%, 10%, 12.5%, 15%), 12 purchase orders (10 received, 1 draft, 1
> pending — real stock via the real service layer, not fabricated), 4
> sales, 2 adjustments. Live-verified against the real running dev server
> (not just the test suite): created a live PO and sale for a 15%-tax
> product, hand-checked the math (`18.00 x 4 x 1.15 = 82.80`,
> `32.00 x 2 x 1.15 = 73.60`) against the actual stored `line_total` —
> exact match both times; then bumped that product's `tax_rate` to 25% and
> confirmed a new sale used 25% while the two earlier lines stayed at 15%.
> 8 new tests (`ProductTaxRateTests`, `TaxAutoCalculationTests`) —
> 173/173 passing (was 165).
> **(28) Phase 8.98d — per-record Purchase/Sale PDF download.** A single
> PO's/sale's own PDF, distinct from Reports' 9 whole-report exports
> (`frontend/reports.py`'s `REPORT_BUILDERS`/`ReportExportView`,
> `reports/reports.html` — none touched this phase). Reused the exact
> existing ReportLab machinery: `generate_pdf_response()`'s inline
> `Table`/`TableStyle` was pulled out into `_styled_data_table()` (a pure
> refactor, same visual output for every existing report PDF) so the two
> new builders — `generate_purchase_order_pdf()`/
> `generate_sale_transaction_pdf()` — could reuse it for both a small
> metadata table (supplier/customer, status, dates, created by) and the
> real line-items table (product, qty, unit price, discount, the Phase
> 8.98c auto-calculated tax, line total), plus a `Total Cost`/`Total
> Amount` line — no new PDF library. `PurchaseOrderPDFView`/
> `SaleTransactionPDFView` (`purchases/<pk>/pdf/`, `sales/<pk>/pdf/`) use
> the same `AnyStaffMixin` gate as `PurchaseListCreateView`/
> `SaleListCreateView` themselves — viewing a record's PDF needs the same
> access as viewing the record on its list page, no stricter or looser.
> A "Download PDF" pill-button (`icon-receipt`, a plain `<a href>` GET
> link like Reports' own export links, not a fetch-based control) added
> to every row on both pages. Live-verified against the real reseeded dev
> DB: downloaded a real PO PDF and a real sale PDF, decompressed each
> PDF's content stream by hand (ASCII85+Flate) to confirm the actual
> rendered text, not just headers — both matched the DB exactly, tax and
> totals included (`8.50 × 100 × 1.10 = 935.00`, `15.00 × 3 × 1.10 =
> 49.50`); confirmed anonymous requests to both PDF URLs `302` to login,
> matching the list pages' own gate. 6 new tests
> (`PerRecordPDFViewTests`) — 179/179 passing (was 173).
> **(29) Phase 8.98e — admin user creation with emailed credentials,
> password-change admin alerts, validated profile images.** Email
> backend: `EMAIL_BACKEND` is `django.core.mail.backends.console.
> EmailBackend` (config/settings.py, env-overridable) — dev/test only;
> real delivery needs a real SMTP backend (`ENVIRONMENT.md`'s Gmail
> setup, or Render's email config at deployment) — this phase wires the
> flow correctly against the console backend and does not pretend real
> email is configured. **Part 1**: `UserForm` (Phase 8's own disclosed
> decision) had the Admin type a password directly — reversed here,
> disclosed a second time (§13): the form has no password field at all
> now. `UserListCreateView.post()` generates one via
> `frontend.validators.generate_strong_password()` (`secrets`-based,
> guaranteed to pass every validator in `AUTH_PASSWORD_VALIDATORS` by
> construction), calls `set_password()`, and emails it directly via a new
> `frontend.notifications.send_new_user_credentials_email()` —
> deliberately NOT built on `notify_user()`, since that function stores
> its exact message in a `Notification` row and this phase's hard rule is
> that the password must never appear in a notification or audit log,
> not even the new user's own; sent unconditionally, ignoring
> `SystemSettings.email_notifications_enabled` (disclosed — that flag is
> a discretionary alert preference, not a valid reason to strand a new
> user with no way to ever learn their password). No new
> `NotificationType` invented for "account created" (11_NOTIFICATIONS.md
> has none), matching this project's existing precedent of not inventing
> undocumented types. `change_password_view` now also calls a new
> `notify_admins()` (same shape as `notify_supervisors()`, Admin-only),
> reusing the documented `PASSWORD_CHANGED` type for a second recipient —
> every Admin is told *who* changed their password, never what it was.
> **Part 2**: `User.profile_image` already existed (SCHEMA.md's own
> field, Phase 1) with zero validation — `profile_view()` now runs it
> through `validate_product_image()` (frontend/validators.py), reused
> unchanged from Product.image/SystemSettings.company_logo, not
> duplicated. Displays for real now too: `.avatar` (topbar user menu,
> sidebar, profile page) shows the actual photo when set, falling back to
> initials exactly as before when not. Same Render-ephemeral-disk caveat
> as Phase 5/deployment (`DEPLOYMENT.md` line ~179) — flagged, not
> re-solved here. Live-verified end-to-end against the real dev DB and
> the real console backend (not just the test suite): an Admin created a
> new user through the real view; the console backend printed a real
> credentials email with a real generated password; the DB's hashed
> password matched what was emailed; the new user logged in with it for
> real (`302` to `/dashboard/`); confirmed zero rows in `Notification`
> or `AuditLog` contain that password anywhere, and no in-app
> `Notification` was created for the new user at all (email-only, by
> design); the new user then changed their password, and the Admin
> received a real notification naming who changed it with the new
> password absent from both the title and message; a profile image
> upload was rejected for a bad extension, accepted for a valid one, and
> then rendered as a real `<img>` on both the profile page and the
> dashboard topbar. 9 new tests (`PasswordGeneratorTests`,
> `ProfileImageValidationTests`, plus additions to
> `ChangePasswordViewTests`/`UserManagementViewTests`) — 188/188 passing
> (was 179).
> **(30) Phase 8.99 — production deployment configuration + the
> auto_now_add/OS-clock pre-deploy fix (BUG-47).** Closed the gap
> flagged, not fixed, in Phase 8.6/BUG-38: `PurchaseOrder.order_date`/
> `SaleTransaction.transaction_date` (`DateField(auto_now_add=True)`) and
> their PO/invoice-number generation
> (`timezone.now().strftime('%Y%m%d')`) both silently ignored
> `TIME_ZONE`, reading the OS clock's raw date / raw UTC respectively —
> invisible on this project's Dhaka-clocked dev machine, would have
> produced wrong dates **and wrong identifiers** on a UTC production
> server near Dhaka midnight. Fixed by setting both fields explicitly via
> `timezone.localdate()` in each model's `save()` (migration `0003`,
> `AlterField` only, no DB-level change) and switching both number
> generators to the same call. Existing dev records checked directly, not
> assumed: all agreed with each other, consistent with the dev machine's
> OS clock already being set to Bangladesh time, not evidence the bug was
> ever harmless. New `TimezoneAwareDateGenerationTests` mocks
> `timezone.now()` to a UTC instant on a different Dhaka calendar day and
> asserts the stored date and the number's date segment land on the
> Dhaka day — a regression back to either old mechanism fails it
> immediately, since it doesn't touch the real OS clock at all. Full
> writeup: `docs/bugsfound.md` BUG-47.
> Configuration: `DEBUG`/`SECRET_KEY`/`ALLOWED_HOSTS`/`DATABASES` were
> **already** fully env-driven with safe fail-closed defaults (confirmed,
> not re-implemented) — this project never had the hardcoded-dev-key/
> `DEBUG=True` mistake to begin with. Added: WhiteNoise
> (`CompressedManifestStaticFilesStorage` via Django 6's `STORAGES` dict —
> the old `STATICFILES_STORAGE` setting no longer exists in this Django
> version), verified locally by running with `DEBUG=False` +
> `collectstatic` end to end (163 files, gzip + content-hashed filenames,
> confirmed serving with correct headers); `SECURE_PROXY_SSL_HEADER` for
> Render's TLS-terminates-at-the-edge proxy shape (undocumented in
> `SECURITY.md`/`DEPLOYMENT.md` but required — without it
> `SECURE_SSL_REDIRECT` would infinite-loop-redirect every request behind
> Render's proxy); `SECURE_SSL_REDIRECT`/HSTS tied to `not DEBUG`, the
> same established pattern `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`
> already used; `EMAIL_HOST`/`PORT`/`USE_TLS`/`HOST_USER`/`HOST_PASSWORD`
> newly wired from env (`ENVIRONMENT.md` documented them, but nothing
> read them before this phase — setting only `EMAIL_BACKEND=...smtp...`
> without them would have silently fallen back to Django's own
> `localhost:25` no-auth default). `SECURE_BROWSER_XSS_FILTER`
> (`SECURITY.md`'s list) deliberately omitted — removed from Django
> itself in 4.0, inert under this project's Django 6.0.7.
> Media: `SERVE_MEDIA_IN_PRODUCTION` (new, default `False`) added rather
> than silently extending dev's DEBUG-gated media serving into
> production — Render's default disk is ephemeral, so serving media
> there at all only makes sense once a persistent disk is actually
> mounted at `MEDIA_ROOT`, a deliberate deploy decision the operator
> makes once, not a side effect of flipping `DEBUG`. Recommendation
> stated, not built: Render persistent disk for this app's actual scale;
> `django-storages` + S3/Cloudinary as the better long-term answer once
> multi-instance/high-traffic needs justify a new dependency and real
> cloud credentials, neither available to verify in this phase.
> First production admin: `createsuperuser` (already correctly
> Render-listed in `DEPLOYMENT.md`'s own checklist) — verified live
> end-to-end against this project's actual custom `User`
> model/`UserManager`, both via `--noinput` (env vars) and confirmed the
> resulting account has `role='admin'`/`is_staff`/`is_superuser` all
> correctly set and a working password; recommend running it
> **interactively** for the real first admin specifically, since
> `--noinput` mode skips `AUTH_PASSWORD_VALIDATORS` entirely (a Django
> limitation, not a project bug) while interactive mode enforces
> `StrongPasswordValidator` like everywhere else. `seed_test_users`/
> `seed_dev_data` reconfirmed DEBUG-guarded — correctly refuse to run in
> production, not a viable substitute.
> **The 3 "faked in dev" gate — explicit verdicts, none left ambiguous:**
> (a) **Emailed new-user credentials (Phase 8.98e): ✅ PROVEN LOCALLY over
> real SMTP** (Phase 8.99f, re-confirmed 8.99f-3/f-5/f-6). Real SMTP (a
> genuine Gmail app password, owner-supplied), a real admin-creates-a-user
> test, a real credentials email confirmed received in a real inbox — not
> just "`send_mail()` didn't raise." Phase 8.99f-5 found and fixed the one
> real remaining gap (BUG-53): the console backend never raises either, so
> the success message used to overclaim "credentials emailed" even when
> nothing left the machine — the response now distinguishes a real send
> from a local-only console print. Phase 8.99f-6 closed the thread: every
> email-related bug (BUG-48/52/53) audited against actual code and
> confirmed genuinely Fixed, one further end-to-end regression pass run
> clean on real SMTP. What remains for Phase D is narrower than "first
> real send" — it's "re-confirm this same, already-proven send against
> Render's real domain/environment," since a new deploy target is exactly
> the kind of change this gate exists to catch early. **Phase 8.99f-7:
> real SMTP is now the RESTING DEFAULT for local use**, not a manual
> flip-then-revert — `.env`'s `EMAIL_BACKEND` stays pointed at real Gmail
> SMTP, proven safe for the test suite specifically (real credentials
> present in `.env` throughout a full 254/254 run; `settings.EMAIL_
> BACKEND` directly confirmed to resolve to `locmem` under `manage.py
> test`, both via Django's own `setup_test_environment()` and this
> project's own explicit `sys.argv`-based guard in `settings.py`).
> Console stays a one-line, fully-supported opt-in
> (`EMAIL_BACKEND=django.core.mail.backends.console...` in `.env`) with
> BUG-53's honesty message unchanged. A new `UserResendCredentialsView`
> (Admin-only, shown while `last_login` is still `None`) closes the
> operational gap real-SMTP-by-default opens: one transient send failure
> no longer strands an account with no recovery path. `.env.example`
> corrected (Phase 8.99f-7): `EMAIL_BACKEND`/`DEFAULT_FROM_EMAIL` must be
> *absent*, not present-and-empty, for `config/settings.py`'s own
> fallback defaults to actually apply — confirmed live, a real bug in
> 8.99f-6's own version of this file, now fixed. (b) **"Forgot password?"
> reset: ✅ PROVEN LOCALLY, same SMTP sessions as (a).** Same email
> dependency as (a) — proven together deliberately, since it's the same
> one dependency underneath both features. Already re-enabled in the UI
> since Phase 8.99a; a real reset email was sent and confirmed received
> in the same real inbox. (c) **Uploaded images (product + profile):
> still DEFERRED, ephemeral — unrelated dependency, untouched by the email
> thread (Phases 8.99f through f-7).** Uploads work within a single running instance but are lost on every redeploy
> until `SERVE_MEDIA_IN_PRODUCTION=True` + a Render persistent disk (or
> `django-storages`) is actually attached — see the media section above.
> `MAX_LOGIN_ATTEMPTS`/`LOCKOUT_DURATION` reconfirmed already env-driven
> with sensible defaults (5/300) — genuinely LIVE, just needs the values
> set in Render if a non-default is wanted. `python manage.py check
> --deploy` passes clean with zero warnings under `DEBUG=False`+a real
> `ALLOWED_HOSTS`. 2 new tests
> (`TimezoneAwareDateGenerationTests`) — 190/190 passing (was 188).
> **(31) Phase 8.99a — finished the forgot-password flow (local-only;
> deployment explicitly out of scope this session).** Closes the last
> visibly-disabled control in the app (Phase 4.5's `<span
> aria-disabled>`) and a real audit gap behind it (BUG-48). Built the 4
> real templates (`registration/password_reset_form.html`/`_done.html`/
> `_confirm.html`/`_complete.html`) plus the 2 Django needs to send a
> correctly-linked email (`password_reset_email.html`/
> `password_reset_subject.txt`) — all extend `base.html` and reuse
> `auth.css` + `components.css`'s existing `.field`/`.input`/
> `.form-alert`/`.btn-primary`, zero new CSS, `login.html`'s own
> `.auth-page`/`.auth-shell`/`.auth-card` structure duplicated exactly as
> the reference, not reinvented. `password_reset_confirm.html` branches
> on Django's own `validlink` context flag for the expired/already-used
> case, styled the same way instead of admin's fallback template.
> **The audit gap, confirmed by reading Django's source before writing
> any fix**: `PasswordResetConfirmView.form_valid()` calls `form.save()`
> and redirects — it never touches `change_password_view`, the only place
> `audit.log_action(PASSWORD_CHANGED)`/`notify_admins()` were ever called
> — so a password reset via email was a real change invisible to both the
> audit log and every Admin, unlike the identical change via the profile
> modal. Fixed by extracting the shared `notify_user()`/`notify_admins()`/
> `audit.log_action()` triplet out of `change_password_view` into a new
> `_record_password_change(user, request)` helper, and a new
> `StockwellPasswordResetConfirmView` that calls it after
> `super().form_valid(form)` — Django's own password-setting logic
> reused, not reimplemented; `form.user` (not `self.request.user`, which
> is anonymous at this point) is the target, and the new password itself
> is never read here, so there's nothing for either function to leak.
> **Namespace decision**: the whole flow (all 4 URLs) now lives under
> `frontend:`, not the pre-existing-but-dead `accounts:` django.contrib.
> auth.urls include — removed outright from `config/urls.py`, not left
> dead a second time. Matches this project's own established precedent
> (login/logout already left `accounts:` for `frontend:` — BUG-01) and
> was the only option that actually works: Django's default `success_url`s
> and the default email template's `{% url 'password_reset_confirm' %}`
> tag reverse a *bare*, non-namespaced name, which `NoReverseMatch`es the
> moment the route only exists inside a namespaced include — confirmed by
> hitting that exact error live before explicitly overriding every
> `success_url` and building a custom `email_template_name` with an
> explicit `frontend:password_reset_confirm` tag. Verified zero other
> references to `accounts:` existed first (a full-repo grep — only a
> code comment did).
> **SMTP smoke test (Part 4): explicitly skipped, not attempted.** No
> real Gmail app password exists in this environment (confirmed by
> checking `.env` for `EMAIL_HOST_USER`/`PASSWORD` — absent) — per this
> phase's own instruction, skipped and stated plainly rather than
> simulated. This flow and Phase 8.98e's emailed new-user credentials
> both remain **UNVERIFIED against a real inbox** (not "working"); the
> follow-up carries to a future deployment phase once real SMTP
> credentials exist. **Superseded, Phase 8.99f: both proven ✅ LIVE**
> against a real Gmail inbox — see §15 item 52.
> Live-verified end to end against the real seeded `verify_user` account,
> not just the test suite: real console-backend reset email sent with a
> working link; confirm page renders Stockwell-styled (not admin
> fallback); a weak new password is rejected with the real
> `StrongPasswordValidator` message and leaves no audit row; a valid
> reset succeeds, and `verify_user` logged in with the new password for
> real (`302` to `/dashboard/`); a real `AuditLog` `PASSWORD_CHANGED` row
> now exists for the reset path specifically; `verify_admin` received a
> real notification naming Talia Nakamura, with the new password absent
> from both its title and message; an invalid/tampered token shows the
> real Stockwell-styled "This link no longer works" message, not admin's.
> `verify_user`'s password restored via `seed_test_users` afterward so
> the standard dev credentials still work. 10 new tests
> (`PasswordResetFlowTests`) — 200/200 passing (was 190).
> **(32) Phase 8.99b — Sales now go through approval before completing,
> mirroring Purchases.** The highest-risk phase since 8.98c (money +
> stock-timing on the app's other core transaction type). Two design
> questions were raised to the owner before writing any code rather than
> guessed at, since both would have been expensive to redo: **(1)
> segregation of duties** — confirmed Purchases has no creator≠approver
> restriction today (read the code, not assumed), owner chose to match
> that for Sales too, not implemented any stricter without approval; **(2)
> draft state shape** — owner confirmed the full Draft→Submit→Pending
> mirror (a real `SaleSubmitView`/"Submit for approval" action, not a
> single combined create-and-submit step), matching Purchases exactly and
> making the task's own requested `SALE_SUBMITTED` audit constant a real,
> non-redundant event.
> **State decision**: no separate `APPROVED` status — `SaleStatus` gained
> `DRAFT`/`PENDING`/`REJECTED` alongside the pre-existing `COMPLETED`/
> `CANCELLED` (reusing `COMPLETED`, not renaming it, so every pre-existing
> dev row stayed valid with zero data migration). Reasoning: for a
> Purchase, approval and receipt are genuinely different moments (approval
> commits; stock moves later, on receive, possibly in parts) — for a Sale,
> approval *is* the moment stock moves, so a distinct `APPROVED` status
> would describe no second, later event of its own. Disclosed as its own
> §13 decision, same treatment as `Product.tax_rate` — explicit divergence
> from `SCHEMA.md` §6's original two-status shape.
> **Service layer split** (`frontend/services.py`): `create_sale()` now
> creates a DRAFT with **zero** `InventoryService` contact — no
> availability check, no movement row; the money math
> (`calculate_line_total()`/`Product.tax_rate`, Phase 8.98c) is completely
> untouched, confirmed by reading every line before and after. New
> `submit_for_approval()` (DRAFT→PENDING) and `approve_sale()` — the
> *only* place a sale's stock now moves, mirroring
> `PurchaseService.receive_items()` being the only place a PO's stock
> moves. New `reject_sale()` mirrors `PurchaseService.reject()` — no
> notification type exists for "sale rejected" (11_NOTIFICATIONS.md has
> none), so it logs but doesn't notify, matching `AdjustmentService.
> reject()`'s identical precedent rather than inventing a second
> undocumented type in the same phase as the one (`SALE_PENDING`) already
> disclosed as load-bearing. `cancel_sale()` restricted to `DRAFT`/
> `PENDING` only — the Objective's own explicit "once completed, a sale
> can never be cancelled" rule — and, since nothing is ever deducted
> before approval now, it no longer calls `InventoryService.
> increase_stock()` at all; `06_SALES.md`'s original "cancellation
> restores stock" rule no longer describes what this method does, also
> disclosed in §13. What happens to an already-completed sale that needs
> reversing is explicitly out of scope, named in the task itself as
> Phase 8.99c's problem to own.
> **Stock-at-approval finding, reported plainly, not silently accepted**:
> confirmed live (two drafts against the same limited stock, deliberately
> set up) that a draft/pending sale reserves nothing — the second
> approval fails with a clean, specific error
> ("Insufficient stock for 'X'. Available: N, Requested: M") and leaves
> the sale pending, stock untouched. **Customer-facing consequence**: a
> staff member can tell a customer "order placed" and have it fail at
> approval — real stock reservation at draft time was explicitly not
> built (a materially bigger feature: reservation expiry, released-on-
> reject, reserved-vs-available shown everywhere), matching the task's own
> explicit instruction not to build it. Recommended, not built: an
> indicative (non-binding) stock check at creation time so this is rare in
> practice, same "indicative client-side, authoritative server-side"
> principle already established for tax/line-total math.
> **`SALE_PENDING`** added as `NotificationType`'s 13th value — a
> deliberate, disclosed override of this project's own Phase 8.98e
> precedent (skip a notification rather than invent an undocumented type)
> because that precedent covered a merely-informational case, while this
> one is load-bearing: without a real notification a Supervisor/Admin has
> no way to learn a sale even exists, and the whole approval gate has no
> trigger. `SALE_COMPLETED` (pre-existing since Phase 1, never actually
> fired by any reference code before this) gets its first real use, on
> approval, notifying the sale's creator — mirrors `PO_APPROVED`'s
> `notify_user(po.created_by, ...)` shape exactly.
> **RBAC**: `AnyStaffMixin` on create/submit (any role), new
> `SupervisorRequiredMixin`-gated `SaleApproveView`/`SaleRejectView`
> (confirmed live: Admin can approve too, the hierarchy holds), no
> creator≠approver check per the owner's confirmed decision above.
> **UI**: `sales.html` gained real status badges + Submit/Approve/Reject/
> Cancel row actions matching `purchases.html`'s shape exactly (including
> removing a pre-existing, decorative "View invoice" button with no
> handler, found while editing this exact area); a new "Pending approval"
> stat card (mirrors Purchases' own); the status `<select>` filter's
> `value=` attributes match the real `TextChoices` (Phase 8.7's own rule);
> the "New sale" modal copy changed from "Complete sale" to "Save draft"
> so it stops claiming to do something it no longer does. `row-actions.js`
> reused unchanged for the new submit/approve/reject handlers — no sixth
> copy of the CSRF/fetch helper (§18's own standing rule). Phase 8.98d's
> per-record Sale PDF now shows Approved By/Approved At (blank-dash when
> unset, same pattern the purchases PDF already uses for
> expected_delivery) — confirmed live by decompressing a real PDF's
> content stream for both a completed and a still-pending sale, not
> assumed correct from the code alone.
> `seed_dev_data.py` updated — sales now need to be pushed through
> submit+approve to reach a realistic `COMPLETED` state (3 of 4 seeded
> sales fully approved; 1 left `PENDING` so the approval queue has a real
> row, same in-progress-state variety the PO seed already had).
> Live-verified end to end against the real reseeded dev DB, all 3 roles:
> a real draft created touching zero stock; staff blocked server-side
> from approving directly (not just button-hidden); supervisor approves —
> real stock deduction, real `InventoryMovement`, real notification to
> both admin and supervisor on submit, real notification to the creator
> on completion (actual console-backend email content captured for all of
> these, not just HTTP status codes); the deliberately-engineered
> insufficient-stock-at-approval race produced the exact clean failure
> Step 3 predicted; reject flow correctly left stock untouched with the
> reason stored; a completed sale's cancel attempt correctly `400`'d with
> stock and status both unchanged. Existing test suite swept for every
> other `SaleService`/`SaleStatus` call site (tax tests, PDF tests,
> dashboard tests) — all still pass unchanged since none of them depended
> on immediate completion; `SaleServiceTests`/`SaleWorkflowViewTests`/
> `LowStockNotificationTests` rewritten for the new flow, one test per
> documented transition per Phase 7's own precedent. 14 net new tests —
> 214/214 passing (was 200). (11) **Phase 8.99c** — cancellation
> restricted (draft/pending only, both Purchase and Sale — overrides
> `05_PURCHASES.md`'s "any state -> CANCELLED"; full disclosure, the
> named-not-solved "stranded approved PO" gap, and `InventoryAdjustment`
> as the documented post-completion correction path are all in §13) and
> a reason is now required and stored (who/when included) for every
> cancellation, surfaced in the list tables, both per-record PDFs, and
> the Purchase/Sales Report CSV+PDF exports. Full detail: §13, §15 item
> 49. 217/217 passing (was 214). (12) **Phase 8.99d** — Movement
> History's date/product/type/search filters unified into one shared,
> server-side function so the page and its export can never disagree
> again; PDF export added (reused `generate_pdf_response()`, states its
> active filters); investigated a "cancelled/rejected source" filter and
> found it's structurally unbuildable-as-useful under Phase 8.99c's own
> rules, so it was documented rather than shipped as a dead control;
> removed the unused `MovementType.RETURN` filter option. Full detail:
> §13, §15 item 50. 225/225 passing (was 217). (13) **Phase 8.99e** —
> Product Edit/Delete, this project's first per-entity update route.
> Diagnosed first: Add was confirmed genuinely working live; the report
> meant Edit/Delete, which never existed. `ProductUpdateView`
> (`AnyStaffMixin`) reuses `ProductForm` unchanged via `instance=`;
> `ProductDeactivateView` (`SupervisorRequiredMixin`) is the real
> `is_active = False` soft-delete, relabelled "Delete" -> "Deactivate"
> rather than left mislabelled — two different mixins on two buttons in
> the same row, matching 02_RBAC.md's asymmetric edit/deactivate split.
> SKU made read-only on edit, enforced server-side. Full detail: §13,
> §15 item 51. 238/238 passing (was 225). (14) **Phase 8.99f** —
> verification only, no rebuild: proved the existing Phase 8.98e/8.99a
> emailed-credentials and password-reset flows end to end. Console
> backend: no regression (real user created, real password emailed, real
> login succeeds, password confirmed absent from every `AuditLog`/
> `Notification` row). Real SMTP: the owner supplied a genuine Gmail app
> password (a real-account-password offer was caught and declined first —
> see §13/§15 item 52) — both a real credentials email and a real
> password-reset email were sent and **confirmed received in the actual
> inbox**, closing the DEFERRED verdict below to **LIVE** for both.
> Forced-password-change-on-first-login confirmed advisory-only today
> (no enforcement field/hook anywhere) and recommended, not built, per
> the task's own scope limit. `EMAIL_BACKEND` reverted to console for
> normal dev; real `EMAIL_HOST_*` values kept in `.env` (gitignored,
> never committed). No code changes — 238/238 passing, unchanged.
> (15) **Phase 8.99f-2** — three items, diagnosed first. Admin-creates-
> user email: already proven live (14), just re-confirmed, no regression.
> User delete: `UserDeactivateView`/`UserReactivateView` (Phase 8) turned
> out already complete and correctly labelled — no dead/mislabelled
> button to fix — so the real gap was that no true delete existed at
> all; built one deliberately narrow (new `UserDeleteView` + `audit.
> USER_DELETED`), succeeding only for a user referenced by none of the 9
> `User`-FK tables (8 `PROTECT`, 1 `SET_NULL`), refusing everyone else
> with a clear message rather than a `ProtectedError` 500. Sidebar
> notification badge: found the literal hardcoded "6" (Phase 3.6 mock
> era), rewired it to share the topbar bell's existing 30s poll of
> `/notifications/unread-count/` — one callback now drives both badges,
> hiding both at zero. Full detail: §13, §15 item 53. 245/245 passing
> (was 238). (16) **Phase 8.99f-3** — Add User modal audited field-by-
> field against `SCHEMA.md` §1 (clean, no changes needed); found and
> fixed a real defect where a failed credentials-email send was
> indistinguishable from a real success (`UserListCreateView.post()`
> never checked `send_new_user_credentials_email()`'s return value) —
> account creation stays either way, but the response now carries a
> `warning` naming the affected email on failure. Re-proven over real
> SMTP for both a Staff and a Supervisor creation, including the
> `email_notifications_enabled=False` override. Full detail: §15 item 54.
> 247/247 passing (was 245). (17) **Phase 8.99f-4** — BUG-51: a leaked
> multi-line `{# #}` comment (BUG-03/BUG-36's shape, a third time) above
> the Add User modal's info banner, rendering as literal text — the
> "stray lines." BUG-52: the modal's real success path had never shown a
> user-visible confirmation at all (no Add-modal in this app ever has;
> reproduced live, diagnosed as a genuine missing feature, not a create
> failure) — fixed by extending 8.99f-3's `warning` field with a
> mutually-exclusive `message` naming the emailed address on real
> success, alert()'d by the existing mechanism before the reload. Full
> detail: §15 item 55. 248/248 passing (was 247). (18) **Phase 8.99f-5**
> — BUG-53, the real cause of "works when the tool does it, not when I do
> it": `EMAIL_BACKEND` was the console backend (this session's own
> resting dev state after every prior SMTP-proving phase), which never
> raises — it "sends" by printing locally, so `email_sent=True` meant the
> same thing for a real delivery and a local-only print, and the success
> message overclaimed either way. Diagnosed via the task's own 4-cause
> checklist (config print, bare-shell isolated `send_mail()` test, live
> repro) before any code change; the SMTP config itself was already
> correct (confirmed again). Fixed by giving the console-backend case its
> own honest message distinct from both the real-send and failed-send
> ones; resting default kept on console per the owner's own choice, put
> to them directly rather than decided unilaterally. `send_new_user_
> credentials_email()` untouched — the bare-shell test proved it was
> never the problem. Full detail: §15 item 56. 249/249 passing (was 248).
> (19) **Phase 8.99f-6** — close-out audit, not a new investigation: every
> email-related bug (BUG-48/52/53) inventoried and verified genuinely
> Fixed against actual code, not just the table (all-fixed outcome, no
> drift, no stale entries to flip). One further real-SMTP regression pass
> confirmed clean; the console-branch honesty message re-verified
> unchanged. `.env.example` was missing its `EMAIL_*` keys entirely — not
> a secret leak, but a real gap — added as documented placeholders. The
> Phase 8.99 deploy gate now reads emailed credentials/password-reset as
> **PROVEN LOCALLY over real SMTP**, not DEFERRED; Phase D's remaining
> email work is "re-confirm on Render," not "first real send." **The
> email thread (8.99f through f-6) is closed.** Full detail: §15 item 57.
> 249/249 passing, unchanged. (20) **Phase 8.99f-7** — real SMTP became
> the resting default for local use (was: manual flip-then-revert every
> time). Test-suite safety proven FIRST, before the flip: real SMTP creds
> present in `.env` throughout a full 254/254 run; `settings.EMAIL_
> BACKEND` directly confirmed `locmem` under `manage.py test`, both via
> Django's own mechanism and a new explicit `settings.py` guard.
> `.env.example`'s `EMAIL_BACKEND`/`DEFAULT_FROM_EMAIL` fixed to be
> genuinely absent rather than present-and-empty (the latter shadows
> `settings.py`'s own safe fallback and crashes — a real bug in 8.99f-6's
> version, corrected). New `EMAIL_TIMEOUT` (10s default) so a hung
> connection fails fast. New `UserResendCredentialsView` — the recovery
> path real-SMTP-by-default needs, shown while `last_login` is `None`,
> live-verified against a deliberately-wrong app password (honest
> `warning`, then a real successful resend once corrected). Console stays
> a one-line opt-in, BUG-53's honesty message unchanged. Full detail:
> §13, §15 item 58. 254/254 passing (was 249). (21) **Phase 8.99f-8** —
> the "works when the tool does it, not when I do it" report traced to a
> stale `runserver` process (started before `.env`'s last edit — proven
> by comparing the process's own `CreationDate` against the file's
> `LastWriteTime`, not guessed at). Not a code bug. Fixed by a real stop/
> start, confirmed via real `curl` HTTP requests against the actual
> listening process across two independent restarts. Full detail: §15
> item 59. 254/254 passing, unchanged. (22) **Phase 8.99i** — Products'
> Edit/Deactivate already existed (Phase 8.99e); added the missing
> Reactivate + a guarded true-Delete. Categories and Suppliers had *zero*
> Edit/Delete views or JS handlers at all — built the full set for both,
> matching Products' pattern exactly (`AnyStaffMixin` edit,
> `SupervisorRequiredMixin` deactivate/reactivate/delete, delete guarded
> to referenced-vs-unreferenced, "one way to change active status" —
> edit never touches `is_active`). Found and fixed BUG-55 along the way
> (Products' Deactivate button used the same `icon-trash` the new, real
> Delete buttons use — fixed to `icon-x` on all three modules). Real
> `InventoryRecord` subtlety handled: excluded from Products' history
> check (every product has one regardless of use) but explicitly deleted
> as part of a genuinely-safe product delete, since it's `PROTECT` too.
> 27 new tests, 254/254 → 281/281 passing. Live-verified through the
> actual running server (`curl`, not just the test client) for all three
> modules' full create→edit→deactivate→reactivate→delete cycle. Full
> detail: §13, §15 item 60.
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
| API | DRF 3.15+ | **djangorestframework 3.18.0** — installed Phase 10, one read-only classification slice only (§13); the other ~55 documented endpoints remain unbuilt |
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
  **Profile images (Phase 8.98e)**: `User.profile_image` (already on the
  model since Phase 1) is now actually validated on upload
  (`validate_product_image()`, reused from Product/SystemSettings, not
  duplicated) and actually displayed — the topbar user menu, sidebar, and
  profile page all show the real photo when set, falling back to
  initials exactly as before when not. **Password changes now also alert
  every Admin** (`notify_admins()`, reusing the documented
  `PASSWORD_CHANGED` type), naming who changed it, never the new value.
  **Forgot-password reset (Phase 8.99a)**: real, Stockwell-styled 4-step
  flow under `frontend:password_reset*` (`registration/password_reset_
  *.html`), closing Phase 4.5's disabled login-page link. A password
  reset via the emailed link now writes the same `AuditLog`
  `PASSWORD_CHANGED` row and fires the same `notify_admins()` alert the
  profile-modal path already did (`StockwellPasswordResetConfirmView`,
  BUG-48) — previously it silently did neither. Delivery runs on the
  console backend in normal dev; real-inbox delivery proven ✅ LIVE
  against a real Gmail inbox (Phase 8.99f, §13/§15 item 52).
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
- ✅ **Dashboard page (real, Phase 8.96)** — genuinely built now, against
  `docs/09_DASHBOARD.md` (originated Phase 8.95, approved 8.95.1). Closes
  the gap Phase 8.8 found (this entry previously read "✅" while the view
  passed only `{"greeting": ...}` — see `docs/bugsfound.md` BUG-41). All 4
  KPI cards are real DB counts (`Product`/`Category`/`Supplier`
  (`is_active=True`)/`User`), each with a real "+N new in the last 30
  days" trend, not a fabricated percentage; the 4-item stat strip reuses
  `InventoryRecord`'s own aggregates (`Sum(total_value)`,
  `Sum(current_stock)`, `status` counts — same definitions as the real
  Inventory page, Phase 8.9); both Chart.js charts render real,
  DB-aggregated series (`Sum`/`annotate`/`TruncWeek`/`TruncMonth`, zero-
  filled per bucket) passed via `{{ chart_data|json_script:
  "dashboardChartData" }}`, not hardcoded arrays; Stock Alerts shows real
  low/out-of-stock `InventoryRecord` rows; Pending Approvals is a
  **read-only** summary of real pending `PurchaseOrder`/
  `InventoryAdjustment` rows — no Approve/Reject buttons anywhere on this
  page, a deliberate decision (Phase 8.5's action-button risk class, see
  `09_DASHBOARD.md` §4b); Recent Activity shows real `AuditLog` rows
  (business actions only, `authentication` module excluded) and renders
  **only** for admin/supervisor — genuinely absent from the rendered HTML
  for staff, confirmed by test and live Playwright check, not just CSS-
  hidden. The AI Insights section is gone entirely (not an empty state) —
  returns once Phase 10/11 populate its source tables for real.
  `DASHBOARD_PREVIEW_ROWS = 5` is defined once in `frontend/views.py` and
  reused for all 3 preview widgets. 8 new tests — 144/144 passing.
- ✅ **Product module (real, Phase 5)** — list page renders the real
  `Product` queryset (with real Category/Supplier FK display, computed
  stock-status badge); "Add Product" modal posts to a real
  `ProductListCreateView` guarded by `AnyStaffMixin`, with server-side
  `ProductForm` validation (unique SKU/barcode, non-negative price/qty,
  active-only Category/Supplier, image type/size) and a real
  `InventoryRecord` created via `InventoryService` on every product. The
  template/JS pattern (modal.js/form-validation.js/dom-utils.js/
  modal-form.js + product-form.js) this module established is still the
  one every later module copies — see §5/§12/§15. **`tax_rate` (Phase
  8.98c)**: a new, disclosed (§13) percentage field on the product itself
  — not per-transaction — non-negative-validated, optional (defaults to
  0%), feeding every Purchase/Sale line's auto-calculated tax.
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
  never a raw model save. **Expected Delivery (Phase 8.98b)**:
  `expected_delivery` already existed on the model and in
  `PurchaseOrderForm` (SCHEMA.md's own field) — the actual gap was
  display (no table column) and validation (no past-date guard), both
  closed. Now a real column in the purchases table (`—` when unset) and a
  real, server-side-enforced rule: can't be in the past, computed against
  Asia/Dhaka's current date (`timezone.localdate()`, Phase 8.6's
  convention), not the OS clock. `order_date` itself is set explicitly in
  `PurchaseOrder.save()` via `timezone.localdate()` (**Phase 8.99**: was
  `auto_now_add=True` at the time this was written — closed as BUG-47,
  see §12/§15, since a plain `DateField`'s `auto_now_add` ignores
  `TIME_ZONE` entirely and would have used the OS clock's raw date on a
  UTC production server) — never user-submitted, always exactly "today"
  (Asia/Dhaka) at save time, so a separate "not-before-order_date" check
  is still redundant with the past-date check, not a second real rule.
  Client-side, the date input's `min=` is the same server-computed
  Asia/Dhaka date (not the browser's local clock), so the two can never
  disagree. **Tax (Phase 8.98c)**: each
  line's tax is now auto-calculated server-side from the product's own
  `tax_rate`, never a form field — the line-items editor's old tax
  `<input>` is gone, replaced by a read-only display, and the order-total
  footer now reads "Total (incl. tax)". **PDF (Phase 8.98d)**: a real
  per-row "Download PDF" button (`PurchaseOrderPDFView`, same
  `AnyStaffMixin` gate as the list view) — that PO's real line items,
  tax, and total, reusing `frontend/reports.py`'s existing ReportLab
  setup, not a new export mechanism and not the Reports module.
- ✅ **Sale module (real, Phase 7; full approval workflow, Phase 8.99b)**
  — list page renders the real `SaleTransaction` queryset; "New sale"
  modal creates a real sale with real line items via
  `SaleTransactionForm` + `parse_line_items()`. **Approval workflow
  (Phase 8.99b)**: no longer create-and-complete in one step — mirrors
  Purchases' own state machine. `SaleService.create_sale()` now creates a
  `DRAFT` with zero stock effect; `AnyStaffMixin`-gated
  `SaleSubmitView` moves it to `PENDING` (fires the new `SALE_PENDING`
  notification, §13); `SupervisorRequiredMixin`-gated `SaleApproveView`/
  `SaleRejectView` are the only place a sale's stock actually moves —
  `approve_sale()` re-validates availability for real at that moment (see
  §13's stock-at-approval finding) and deducts via `InventoryService`;
  `reject_sale()` mirrors `PurchaseService.reject()`. `SaleCancelView`
  (`SupervisorRequiredMixin`) now only reaches `DRAFT`/`PENDING` sales —
  a completed sale can never be cancelled, and since nothing is deducted
  before approval, cancelling a draft/pending sale no longer restores
  stock (there's nothing to restore). Tax (Phase 8.98c) and the PDF
  export (Phase 8.98d) are both unchanged — the money math and the
  ledger were explicitly out of scope for this phase, confirmed
  untouched. Sale's PDF now additionally shows Approved By/Approved At.
- ✅ **Adjustment module (real, Phase 7)** — list page renders the real
  `InventoryAdjustment` queryset; "New adjustment" modal creates a real
  pending request via `AdjustmentForm` (`AnyStaffMixin`). Approve/Reject
  (`SupervisorRequiredMixin`) route through `AdjustmentService`.
- ✅ **Inventory module (real, Phase 8.9)** — genuinely built now, closing
  the gap Phase 8.7/8.8 found (this entry incorrectly read "✅ read-only"
  before the view actually existed; see `docs/bugsfound.md` BUG-37).
  `InventoryListView` (`AnyStaffMixin` — matches `07_INVENTORY.md`'s own
  `@staff_required`, which means all 3 roles in this project's RBAC, not a
  stricter gate) renders a real `InventoryRecord` queryset: product,
  current stock, reorder level, total value, and `status` read straight
  off the model (InventoryService already keeps it correct on every real
  mutation — not recomputed in the view). KPI/stat-strip numbers and the
  "last movement" column are real aggregates too, not hardcoded. Filter
  controls wired to `table-filter.js` the same way as Phase 8.7's 5 pages.
  Confirmed strictly read-only: no `<form>` in the template, no mutation
  call anywhere in the view, live `POST /inventory/` returns `405`.
  **Movement History added (Phase 8.98, BUG-45)** — `/inventory/movements/`
  (`MovementHistoryListView`, `AnyStaffMixin`), the real page behind the
  page's own "Movement history" button (previously dead). Real
  `InventoryMovement` ledger, real `Paginator`-backed pagination (the
  ledger is append-only and grows forever — client-side filtering would
  only ever see one page of it). Also strictly read-only, same as
  Inventory itself.
  **Phase 8.99d — every filter went server-side, and export gained a PDF
  twin of the CSV.** Date range, product, movement type, and search (`q`,
  product name/SKU) are now all query-string filters read by one shared
  `frontend/reports.py` function (`filter_movements()`), used by both this
  page and its own export view — the page and the export can no longer
  silently disagree, which they previously did (the page filtered dates
  with `created_at__date__gte`; the export used a different, timezone-
  aware range; the export had no product/type/search filtering at all).
  `table-filter.js`/`movement-history.js` (the latter deleted, now dead)
  are gone from this page — search moved server-side rather than staying
  client-side-with-a-caveat, since a client-only search could never be
  reflected in an export either, the same reasoning BUG-45 already used
  for date range. The `?product=<id>` deep-link from Inventory's per-row
  links now lands in a real, visible `<select>` in the same filter form,
  not a separate hidden-input mechanism. Export CSV unchanged in shape;
  Export PDF is new, reusing `generate_pdf_response()`/
  `_styled_data_table()` verbatim (no new PDF mechanism) with a new
  optional `filters_summary` line rendered under the title stating
  exactly what was filtered. See §13 for the full disclosure, including
  why a "cancelled/rejected source document" filter was *not* added as a
  UI control despite being buildable.
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
- ✅ **Reports module (real, Phase 8)** — `frontend/reports.py`'s 9 report
  builders (Inventory/Purchase/Sales/Movement/Adjustment/Low Stock/Out of
  Stock/AI Forecast/AI Classification), each exporting real PDF (ReportLab
  — chosen over WeasyPrint for zero native deps on this Windows dev
  environment, both documented as acceptable in `TECH_STACK.md`) and CSV;
  Sales/Low Stock keep their full HTML preview from the mock, the other 7
  export straight from their card (no preview panel existed for those in
  the mock either); every export audit-logged
  (`REPORT_GENERATED`/`REPORT_EXPORTED_PDF`/`REPORT_EXPORTED_CSV`);
  `SupervisorRequiredMixin`-gated. **Confirmed genuinely real (Phase 8.8
  audit)** — all 9 builders are real querysets, no hardcoded rows anywhere.
  One honest caveat, not a bug: AI Forecast/AI Classification query
  `DemandForecast`/`InventoryClassification`, which nothing populates yet
  (AI is Phase 10/11) — those two exports are real code against
  currently-empty tables, correctly producing an empty report, not fake
  data standing in for real data.
- ✅ **Notifications module (real, Phase 8)** — real `Notification`
  queryset for the logged-in user; mark-read/mark-all-read/unread-count
  endpoints; topbar bell badge (`#notifBadge`) polls `/notifications/
  unread-count/` every 30s and only shows when something's actually
  unread — no role gate, any authenticated user sees their own.
- ✅ **Users & Roles module (real, Phase 8; password field removed again,
  Phase 8.98e)** — real `User` queryset + role counts. Phase 8 gave "Add
  user" a required password field (a `User` saved without one gets
  `set_unusable_password()` and can never log in); Phase 8.98e removes
  that field a second time, deliberately, for the opposite reason — the
  Admin must never choose or see a new user's password at all now.
  `UserListCreateView.post()` generates a strong random one
  (`frontend.validators.generate_strong_password()`), sets it, and emails
  it directly to the new user (`frontend.notifications.
  send_new_user_credentials_email()`) — never returned in this view's own
  response, never logged, never stored in a `Notification`. Deactivate/
  Reactivate wired for real; an admin cannot deactivate their own account.
  `AdminRequiredMixin`-gated.
- ✅ **Audit Log module (real, Phase 8)** — real `AuditLog` queryset
  (latest 500), `AdminRequiredMixin`-gated; module/status filter still
  client-side (`table-filter.js`), now against real data.
- ✅ **Settings module (real, Phase 8)** — real `SystemSettings` singleton
  (`SystemSettingsForm`), `AdminRequiredMixin`-gated; every optional
  numeric/text field left blank on submit falls back to the row's own
  current value, not the model's class default — a plain fallback to the
  class default would silently blank out a real admin-configured value on
  any partial save.
- Verified regression-free (Phase 3.65): no leaked `{# #}` comment text, no
  `[hidden]`/`display` cascade bugs, no console errors across all 5 pages —
  see §15.
- ✅ **`AUTH_USER_MODEL` switch + migrations applied (Phase 3.7)** —
  `AUTH_USER_MODEL = 'frontend.User'`, `db.sqlite3` reset and migrated
  fresh, every user-pointing FK confirmed resolving to `frontend.User` at
  runtime, `createsuperuser` creates a real `frontend.User` row. Admin
  list pages (Phase 2) now actually render — verified live. See §15.

Not built at all (0%):
- ❌ Any DRF/API layer
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
│   ├── views.py               981 lines. Every view is real now (Phase 4-8.9) except Dashboard's — see §5/§16
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
  `frontend/urls.py` registers 39 routes as of Phase 8.98a (was 38 after
  Phase 8.98, 33 after Phase 8, 31 after Phase 7 — grew again via Phase
  8.9's `inventory/movements/` (+2, list and export), Phase 8.98's
  `products/export/`/`suppliers/export/`/`audit-log/export/` (+3), and
  Phase 8.98a's `profile/change-password/` (+1)): the original
  GET-rendered template routes (landing/dashboard/login/logout/profile/
  inventory/AI pages), the 12 Purchase/Sale/Adjustment workflow routes
  (Phase 7), `reports/`/`notifications/`/`users/`/`audit-log/`/`settings/`
  (all 5 already existed as routes, now pointing at real class-based
  views instead of one-line `render()` functions), and Phase 8's 6
  net-new sub-routes: `reports/export/<slug:report_type>/`,
  `notifications/<pk>/read/`, `notifications/read-all/`,
  `notifications/unread-count/`, `users/<pk>/deactivate/`,
  `users/<pk>/reactivate/`.
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
  Phase 8 replaces the remaining 5 one-line `render()` views:
  `AuditLogListView` (read-only, `AdminRequiredMixin`); `NotificationListView`
  plus `NotificationMarkReadView`/`NotificationMarkAllReadView`/
  `NotificationUnreadCountView` (`LoginRequiredMixin` only — any
  authenticated user, no role gate, since these are always scoped to
  `request.user`'s own rows); `UserListCreateView` plus
  `UserDeactivateView`/`UserReactivateView` (`AdminRequiredMixin`;
  self-deactivation blocked); `SettingsView` (`AdminRequiredMixin`, GET+POST
  against the `SystemSettings` singleton); `ReportsView` plus
  `ReportExportView` (`SupervisorRequiredMixin`, delegate to the 9 builders
  in the new `frontend/reports.py`, same small-dedicated-module pattern as
  `frontend/audit.py`/`frontend/notifications.py`). Every view in this
  project now does real work — none is still a placeholder `render()`.
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
  lock out Admins; nothing needed fixing here, and Phase 8 re-confirmed it
  by test on Reports too, not just Purchases. Phase 8 gives
  `AdminRequiredMixin` its first real (non-throwaway) use — Audit Log,
  Users & Roles, Settings — and plain Django `LoginRequiredMixin` its
  first use anywhere in this project, on Notifications (correctly
  role-less: every user's notifications are their own). **Every view in
  the app is RBAC-gated one way or another** — Inventory's real
  `InventoryListView` (Phase 8.9) closed the last gap with
  `AnyStaffMixin` (matching `07_INVENTORY.md`'s own `@staff_required`,
  which means all 3 roles in this project's RBAC — not a stricter gate;
  it still has no create/write action to gate, by design, just a real
  login/role check now instead of none at all). DRF's `BasePermission`
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
  `UserForm`/`SystemSettingsForm` (Phase 8) — `UserForm` adds a required
  `password` field the mock explicitly hadn't had (see §2's Users & Roles
  entry for why), run through the same `validate_password()`/
  `AUTH_PASSWORD_VALIDATORS` stack `profile_view` already used (Phase 4);
  `SystemSettingsForm` is the first form in this project where every
  field is optional on the form despite most having no `blank=True` on
  the model — `SystemSettings` is a singleton always edited via
  `instance=`, so a blank submission falls back to that instance's
  current value in `clean()`, not the model's class default (falling back
  to the class default would silently blank out a real admin-configured
  value on every save that happens to omit a field).
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
- **Schema implementation status**: **all 17 models implemented in code**
  (16 through Phase 11, `ApprovalPolicy` added Phase 12),
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
  | `InventoryAdjustment` | adjustment_type (increase/decrease), quantity, **reason_code (Phase 12 — structured, required, `AdjustmentReason` choices) alongside the original free-text reason (required)**, status (pending/approved/rejected) | FK→Product, FK→User×2 |
  | `DemandForecast` | forecast_period (weekly/monthly), forecasted_demand, recommended_reorder_qty, confidence_score, model_version | FK→Product (CASCADE) |
  | `InventoryClassification` | classification (fast/slow/dead), turnover_rate, days_since_last_sale, recommendation, **abc_class (Phase 12 — `ABCClass` A/B/C, blank = never computed since Phase 12.1 §5b, recomputed by `recompute_abc_classes()`, never touched by `classify_product()`; analytics-only since Phase 12.2 — see §13)** | OneToOne→Product (CASCADE) |
  | `Notification` | type (12 choices), title, message, is_read, is_critical | FK→User (recipient, CASCADE) |
  | `AuditLog` | action, module, affected_id, status, details (JSON), ip_address — **immutable, save()/delete() raise `PermissionError` on update/delete attempts**. Note: does **not** inherit `TimeStampedModel` — it's a plain `models.Model` with its own `timestamp` field instead of `created_at`/`updated_at`, exactly as SCHEMA.md writes it. | FK→User (SET_NULL) |
  | `SystemSettings` | singleton (`get_settings()` → `get_or_create(pk=1)`); default_reorder_level, forecast config, threshold days, session_timeout_seconds, notification toggles (`email_notifications_enabled`/`low_stock_email_enabled` fields still live, still read by `notifications.py`; the settings-page UI control was removed Phase 12.2 — only Django admin can change them now, see §13); company_name/address/email/phone plus **company_tax_number/company_website (Phase 13, new)**; `company_logo` is a **`FileField`, not `ImageField`, since Phase 13** — SVG has no Pillow support, so `ImageField`'s built-in validation would hard-reject it; `frontend.validators.validate_company_logo` does that checking instead (Pillow-verified for PNG/JPG, sniffed for SVG). `get_company_profile()` (classmethod, alongside `get_settings()`) is the one accessor every PDF reads through — no PDF hardcodes a company value | none |
  | `ApprovalPolicy` (Phase 12, new) | name, transaction_type (purchase_order/adjustment/sale_cancel), reason_code/min_value/max_value/max_variance_pct/cumulative_window_days/cumulative_value_cap (matching conditions, blank/null = matches anything), required_level (auto/supervisor/admin), block_self_approval, priority (lower wins, unique per active row per type), is_active, notes — **`abc_class` field removed Phase 12.2, see §13** | none — resolved against live `PurchaseOrder`/`InventoryAdjustment`/`SaleTransaction` instances by `frontend/approvals.py`, not a FK |

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

**Demand Forecasting remains a polished front-end mock — no real model, no
real job, no real data pipeline (Phase 11's territory). Slow-Moving & Dead
Stock is real as of Backend Phase 10**: `frontend/classification.py`
implements the documented rule-based classifier for real, writing real
`InventoryClassification` rows, wired into `slow_moving.html` and a small
read-only DRF slice. `DemandForecast` remains a migrated-but-unused model.

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

**Slow-Moving & Dead Stock Detection — real as of Backend Phase 10**
(`docs/DEAD_STOCK_DETECTION.md`, page at `/ai/slow-moving/`,
`frontend/classification.py`):
- Rule-based, no ML, exactly as documented: `fast` = sold recently
  (turnover is computed and shown for context but is not a gate — the
  doc's own Design Notes revision #2, matched not re-litigated); `slow` =
  last sold between `slow_moving_threshold_days` (default 60) and
  `dead_stock_threshold_days` (default 180) days ago, read from
  `SystemSettings`, never hardcoded; `dead` = beyond that or never sold.
  No Celery (not installed) — runs synchronously, either from
  `SaleService.approve_sale()`/`cancel_sale()` (one product) or the manual
  "Run classification now" button (all active products). Full rejection
  reasoning for the documented `post_save` signal, the two further
  translations (Dhaka-not-UTC "today," the real `SaleStatus.COMPLETED`
  constant), the bulk-seed reclassification-volume finding, and a real
  `turnover_rate` overflow bug found and fixed along the way — all in §13.
- `slow_moving.html` renders a real `InventoryClassification` queryset
  (was an 11-row hardcoded mock); the doughnut chart and KPI tiles read
  real fast/slow/dead counts; filters stay client-side (`table-filter.js`,
  unchanged) since the page is a bounded, non-paginated list. The
  never-sold case still shows "No recorded sales..." rather than the
  doc's internal `9999` sentinel — the same deliberate UI-copy decision
  from before Phase 10, now proven by a live test, not just carried
  forward as an assumption.
- The pre-existing `dashboard/dashboard.html` mock preview inconsistency
  noted below Phase 10 remains unchanged (still out of scope, see §12) —
  Phase 10 only touched `slow_moving.html`.
- DRF: `ClassificationListAPIView`/`ClassificationSummaryAPIView`
  (read-only, `IsSupervisorOrAbove`) — the one slice Phase 9 pre-committed
  to this phase. Full detail in §13.

**Still pending**: Demand Forecasting's actual model training code,
actual Celery tasks/Beat schedule for either AI feature, and persisting to
`DemandForecast` — all Phase 11.

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
- Search/filter controls now filter real data on every list page that has
  them: Products, Suppliers, Purchases, Sales, Adjustments (Phase 8.7),
  Inventory (Phase 8.9), Users & Roles (Phase 8.6), Forecasting/
  Slow-Moving/Audit Log/Reports (already working pre-8.6). One exception,
  confirmed intentional not overlooked (Phase 8.7): **Categories** has no
  filter controls in its template at all — nothing to wire. This bullet
  predates Phase 5-8; the "Approve/reject have no click handlers" line
  immediately below is similarly stale — see §2/§15 Phase 7/8.5.
- Pagination controls exist on several list pages but are non-functional
  (Previous disabled, Next does nothing).
- ~~Approve/reject buttons exist on Purchase/Adjustment pending rows but
  have no click handlers.~~ Stale — real since Phase 7 (Purchases/
  Adjustments) and role-gated since Phase 8.5, see §2/§15.

**No longer missing**: Reports, Notifications, Audit Log, Users & Roles,
Settings all got real mock pages in Phase 3.6 (§11) — sidebar links
re-enabled, nothing left disabled.

---

## 11. Current UI Pages

- ✅ Landing
- ✅ Login (real, Phase 4 — username/email, lockout, session timeout)
- ✅ Profile (`/profile/`, Phase 4 — new page, not in the sidebar; reached
  via the topbar user-menu dropdown only). Password change moved to its
  own real modal (Phase 8.98a) — `/profile/change-password/`, current-
  password verification + confirm-match, same `StrongPasswordValidator`
  chain reused from Phase 4.
- ✅ Dashboard (real, Phase 8.96 — real KPIs/stats/charts/widgets against
  `docs/09_DASHBOARD.md`, Recent Activity admin/supervisor-only — see §2/§16)
- ✅ Products (real, Phase 5 — list + Add modal against the live DB, RBAC-guarded; Phase 8.99e/8.99i added the full Edit/Deactivate/Reactivate/Delete lifecycle — see §13)
- ✅ Categories (real, Phase 6 — list + Add modal against the live DB, RBAC-guarded; Phase 8.99i added the full Edit/Deactivate/Reactivate/Delete lifecycle — previously unwired, see §13)
- ✅ Suppliers (real, Phase 6 — list + Add modal against the live DB, RBAC-guarded; Phase 8.99i added the full Edit/Deactivate/Reactivate/Delete lifecycle — previously unwired, see §13)
- ✅ Purchases (real, Phase 7 — list + Add modal against the live DB, full submit/approve/reject/receive/cancel workflow, RBAC-guarded; Phase 8.99c: cancel is draft/pending-only and requires a reason — see §13)
- ✅ Sales (real, Phase 7 — list + Add modal against the live DB, full submit/approve/reject/cancel workflow mirroring Purchases since Phase 8.99b, RBAC-guarded; Phase 8.99c: cancel is draft/pending-only and requires a reason, same as Purchases — see §13)
- ✅ Inventory (real, Phase 8.9 — real `InventoryRecord` list, read-only
  by design, `AnyStaffMixin`-guarded, filters wired — see §2/§16)
- ✅ Adjustments (real, Phase 7 — list + Add modal against the live DB, approve/reject workflow, RBAC-guarded)
- ✅ Demand Forecasting (`/ai/forecasting/`)
- ✅ Slow-Moving & Dead Stock (`/ai/slow-moving/`)
- ✅ Reports (`/reports/`, real, Phase 8 — 9 report types, all export real PDF/CSV; Sales/Low Stock keep a real HTML preview, RBAC-guarded Supervisor+)
- ✅ Notifications (`/notifications/`, real, Phase 8 — real per-user list, mark-read/mark-all, 30s-polling topbar badge; Phase 8.99f-2: the sidebar's own badge — previously a hardcoded "6" — now driven by the same poll/endpoint, not a second one)
- ✅ Users & Roles (`/users/`, real, Phase 8 — list + Add User against the live DB (password field removed again, Phase 8.98e — a generated password is emailed instead, see §13), Deactivate/Reactivate, RBAC-guarded Admin-only; Phase 8.99f-2: real Delete added, guarded to users with zero referential history — see §13)
- ✅ Audit Log (`/audit-log/`, real, Phase 8 — real `AuditLog` queryset, RBAC-guarded Admin-only)
- ✅ Settings (`/settings/`, real, Phase 8 — real `SystemSettings` singleton, RBAC-guarded Admin-only)

All 15 sidebar links now resolve to a real page, every one of them is
real, and (Phase 8.97 Part A) every one of them is now genuinely
RBAC-guarded too — Inventory (Phase 8.9), Dashboard content (Phase 8.96),
and Dashboard's own auth gate (Phase 8.97) closed the last gaps, see
§2/§16. Every page except Inventory runs through a real form/queryset and
a real RBAC mixin; Inventory runs through a real queryset and
`AnyStaffMixin` (no form, since it's read-only by design); Dashboard now
does the same (`DashboardView(AnyStaffMixin, View)`, Phase 8.97).

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
- ~~`line_total` calculation logic duplicated in 3 places on the frontend
  (see §8), and a 4th time server-side in the new `PurchaseOrderItem`/
  `SaleItem` models~~ — **server-side duplication RESOLVED (Phase 8.98c)**:
  `PurchaseOrderItem.save()` and `SaleService.create_sale()` both now call
  the same `frontend.pricing.calculate_line_total()`. The frontend copy in
  `line-items.js` is unchanged and still indicative-only (server is
  authoritative) — that half of the debt still stands, tax is just no
  longer part of what it duplicates as a user-editable input.
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
- ~~`dashboard()` had no `@login_required`/RBAC mixin at all~~ —
  **FIXED (Phase 8.97 Part A, BUG-42).** Converted to
  `DashboardView(AnyStaffMixin, View)`, matching every other real view's
  convention. Verified live: anonymous `GET /dashboard/` → `302` to
  `/login/?next=/dashboard/`; all 3 roles still load correctly; Recent
  Activity's `is_authenticated` guard (Phase 8.96) is now
  belt-and-suspenders, not load-bearing.
- ~~`demand_forecasting`/`slow_moving_dead_stock` (`/ai/forecasting/`,
  `/ai/slow-moving/`) also have no auth requirement at all~~ — **FIXED
  (Phase 8.99j, BUG-43).** Converted both to CBVs
  (`DemandForecastingView`/`SlowMovingDeadStockView`), gated
  `SupervisorRequiredMixin` (Admin+Supervisor only — narrower than
  `AnyStaffMixin`, since this phase's actual requirement was "staff can't
  see the AI models," a disclosed deviation from BUG-43's own original
  suggested fix). Sidebar's Intelligence nav group gated to match.
  Verified live, all 3 roles + anonymous, by direct URL. Both pages
  remain 100% disclosed mock (§10/§11) pending Phase 10/11 — only the
  access gate changed here.
- ~~"Export"/"Export CSV" buttons on Products, Suppliers, and Audit Log
  are decorative~~ — **FIXED (Phase 8.98, BUG-44).** All 3 now produce
  real CSV via `frontend/reports.py`'s existing `generate_csv_response()`
  — exactly the reuse this entry predicted. Auth matches each source
  page (`AnyStaffMixin` on Products/Suppliers, `AdminRequiredMixin` on
  Audit Log). Products/Suppliers export the full dataset, not the current
  client-side filter selection (disclosed, not silent). Movement History
  (BUG-45, same phase) got the same treatment, and — being genuinely
  server-side date-filtered already — its export actually respects the
  current filter, unlike the other three.

**Open items from Backend Phase 4** (real, verified, but with real gaps —
kept together here rather than scattered, since they were all found in
the same phase):

- **RBAC mechanism now applied to 11 real modules — Products (Phase 5),
  Categories, Suppliers (Phase 6), Purchases, Sales, Adjustments (Phase 7),
  Audit Log, Users & Roles, Settings, Reports, Notifications (Phase 8).**
  `AnyStaffMixin` guards every create/list/submit/receive view;
  `SupervisorRequiredMixin` guards every approve/reject/cancel view plus
  Reports (Phase 8, re-confirmed the Admin-or-Supervisor hierarchy holds
  there too); `AdminRequiredMixin` gets its first real use on Audit Log/
  Users & Roles/Settings; plain `LoginRequiredMixin` guards Notifications
  (correctly role-less — every user's notifications are their own);
  logged-out requests redirect to login, confirmed live and by test across
  all eleven. **Inventory is now the only view in the entire app with no
  RBAC mixin** — by design, not a gap: it's read-only with no create/write
  action to gate (see §16).
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
  **RESOLVED for real, Phase 8.99a**: the flow is now real and
  Stockwell-styled (own templates, not admin's fallback ones), the link
  is a genuine `<a href>` again, and the `accounts:` include this entry
  called "deliberately left in place" is now actually removed — its last
  reason for existing (this flow) no longer needs it. See §15.

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
- **`Product.tax_rate` added with no source in any doc — disclosed, not
  silently invented (Phase 8.98c), same treatment as the SKU-format
  decision above.** `SCHEMA.md`/`API_CONTRACTS.md` both still document
  `tax` only as a per-line `PurchaseOrderItem`/`SaleItem` field (a
  transaction-time value); this task explicitly asked to move it onto
  `Product` instead — a property of the product, not something entered
  per-transaction — and to auto-calculate every line's tax from it.
  Defaults to 0% (matches the field's own model default, and the general
  principle used elsewhere in this project of not baking in an assumed
  jurisdiction/tax regime — see `SystemSettings`, which has no tax-rate
  field of its own either). `PurchaseOrderItem.tax`/`SaleItem.tax` are
  kept as real, separately-stored columns rather than being derived at
  read-time from `product.tax_rate` — deliberately, so each transaction
  keeps a historical snapshot of what was actually charged: a later change
  to a product's `tax_rate` must only affect new transactions, never
  retroactively rewrite an already-completed one. `InventoryAdjustment`
  was left alone entirely — it has no monetary/tax field in `SCHEMA.md` and
  none was added; tax is a purchase/sale concern only.
- **`UserForm`'s password field (Phase 8's own disclosed decision) removed
  again (Phase 8.98e) — the second reversal on this exact field.** Phase 8
  added it because a `User` saved without ever calling `set_password()`
  could never log in; Phase 8.98e removes it again because this task
  requires the Admin to never choose or see a new user's password at
  all. Both states were real, working, and disclosed at the time — this
  is not a bug being fixed, it's a requirement changing. A random
  password is now generated server-side and emailed instead.
- **The new-user credentials email (Phase 8.98e) bypasses
  `SystemSettings.email_notifications_enabled`**, unlike every other
  email this app sends. That flag is framed throughout `SCHEMA.md`/
  `11_NOTIFICATIONS.md` as a discretionary alert-noise preference; the
  credentials email is the *only* channel through which a new,
  Admin-invisible password can ever reach its owner, so honoring a
  blanket "no emails" toggle here would strand that account with no way
  to log in. Disclosed rather than silently special-cased.
- **No new `NotificationType` added for "account created" (Phase
  8.98e)**, even though the new-user flow does send a real email.
  `11_NOTIFICATIONS.md`'s type table has no such entry, and this
  project's existing precedent (`PurchaseService.cancel()`/`reject()`,
  §12) is to skip the in-app `Notification` rather than invent an
  undocumented type — applied here too. There is a stronger reason on
  top of precedent this time: `notify_user()` always stores its exact
  message in a `Notification` row, and the message would have to contain
  the password to be useful, which this phase's own hard security rule
  forbids. So `send_new_user_credentials_email()` (frontend/
  notifications.py) sends the real email directly via `send_mail()` and
  creates no `Notification` row for the new user at all.
- **`SERVE_MEDIA_IN_PRODUCTION` (Phase 8.99) defaults to `False`,
  deliberately not tied to `DEBUG`.** Serving media in production is only
  correct once a persistent disk is actually mounted at `MEDIA_ROOT`
  (Render's default disk is ephemeral) — making it a bare
  `not DEBUG`-style flag like the security headers would mean the very
  first production deploy silently starts "serving" media it's about to
  lose on the next redeploy. A separate, explicit opt-in makes attaching
  real storage a deliberate step, not an accidental side effect of
  flipping `DEBUG`.
- **`SECURITY.md`'s `SECURE_BROWSER_XSS_FILTER` deliberately not added
  (Phase 8.99).** Django removed this setting in 4.0 — the
  `X-XSS-Protection` header it controlled was itself deprecated/removed
  by every major browser for being an exploitable security hole. Setting
  it under this project's Django 6.0.7 would do nothing; disclosed as an
  intentional gap against the doc rather than added as inert cargo.
- **Emailed new-user credentials and the forgot-password reset were
  reported DEFERRED, not LIVE, after Phase 8.99** even though all the
  SMTP settings existed and were wired correctly — that phase had no real
  Gmail app-password or outbound SMTP access to prove an email actually
  reaches a real inbox, and claiming "LIVE" on code-correctness alone
  would have been exactly the silent-failure mode Phase 8.99's own
  verification gate exists to catch. **Superseded, Phase 8.99f: both are
  now ✅ LIVE** — a real Gmail app password became available, both a real
  credentials email and a real password-reset email were sent and
  confirmed received in a real inbox. See §15 item 52 and the intro
  blockquote's "3 faked in dev gate" paragraph for the full verification.
- **Password reset (Phase 8.99a) lives entirely under `frontend:`, and
  the `accounts:` django.contrib.auth.urls include is now removed, not
  left dead.** Matches this project's own established precedent (login/
  logout already left `accounts:` for `frontend:`, BUG-01) and was the
  only option that actually works, not just the more consistent one:
  `PasswordResetConfirmView`/`PasswordResetView`'s own default
  `success_url`s, and Django's default `registration/
  password_reset_email.html`'s `{% url 'password_reset_confirm' %}` tag,
  all reverse a *bare*, non-namespaced name — confirmed via a live
  `NoReverseMatch` before fixing it — which cannot resolve once the route
  only exists inside a namespaced include. Every `success_url` is now
  explicitly namespaced (`frontend:password_reset_done` etc.), and a
  custom `password_reset_email.html` explicitly tags
  `{% url 'frontend:password_reset_confirm' ... %}` rather than relying
  on Django's default template's bare one. Confirmed via full-repo grep
  that nothing still referenced `accounts:` before removing the include —
  only a code comment did.
- **`SaleTransaction.status` extended to a 5-value state machine
  (Phase 8.99b), diverging from `SCHEMA.md` §6's documented two values
  (`completed`/`cancelled`).** The owner is the source of this rule, not
  the doc — same "the owner overrides the doc" treatment as
  `Product.tax_rate`. No separate `APPROVED` status was added alongside
  the pre-existing `COMPLETED`: for a Purchase, approval and receipt are
  genuinely different moments (approval commits to the order; stock only
  moves later, on receive, and can move in parts across several
  receipts) — for a Sale, approval *is* the moment stock moves, so a
  distinct `APPROVED` status would describe no second, later event of
  its own; adding one would be a state with no real meaning. `COMPLETED`
  was reused, not renamed, specifically so every pre-existing dev record
  stayed a valid row with zero data migration needed.
- **`SALE_PENDING` added as `NotificationType`'s 13th value (Phase
  8.99b), a deliberate override of this project's own Phase 8.98e
  precedent** ("skip a notification rather than invent an undocumented
  type," applied there to `PurchaseService.cancel()`/
  `AdjustmentService.reject()`-style purely-informational gaps). That
  precedent doesn't apply here: without a real notification, a
  Supervisor/Admin has no way to ever learn a sale is awaiting them, and
  the entire approval gate this phase builds has no trigger at all — a
  functional gap, not a cosmetic one. `reject_sale()`'s own missing
  notification type, by contrast, *is* the informational-gap shape the
  Phase 8.98e precedent describes, and was left un-invented, matching it
  exactly (same reasoning `AdjustmentService.reject()` already used).
- **`SaleService.cancel_sale()` no longer restores stock (Phase 8.99b)**,
  diverging from `06_SALES.md`'s documented "Cancellation | Restores
  stock via `InventoryService.increase_stock()`" rule. Not an oversight:
  cancellation is now restricted to `DRAFT`/`PENDING` sales only (a
  completed sale can never be cancelled by this method — the task's own
  explicit rule), and a draft/pending sale has had nothing deducted yet
  under the new approval-gated model (only `approve_sale()` moves
  stock), so there is nothing left to restore. What should happen to an
  already-completed sale that needs reversing is an explicitly separate,
  out-of-scope concern — named in this phase's own task spec as Phase
  8.99c's problem to own, not solved here.
- **`PurchaseService._CANCELLABLE_STATUSES` narrowed to `DRAFT`/`PENDING`
  only (Phase 8.99c), overriding `05_PURCHASES.md`'s own state machine
  ("Any state -> CANCELLED") and business-rules table.** The owner is the
  source of this rule, not the doc — same treatment as `Product.tax_rate`
  and the Sale status extension above. Reason: an approved PO is a
  commitment already made to the supplier; cancelling it after that point
  isn't a status flip, it's reneging on an order the supplier may already
  be fulfilling. `APPROVED`/`PARTIAL` were previously cancellable
  (Phase 3.4 / BUG-25's original implementation, which read the doc's
  diagram literally); `RECEIVED`/`REJECTED`/`CANCELLED` were already
  terminal and remain so.
  **Named, unsolved consequence**: an approved or partially-received PO
  the supplier will never fulfil now has no terminal state to reach. It
  stays in the pending-approvals view and the Purchases list indefinitely,
  and the Dashboard's Pending Approvals widget keeps counting it. The
  minimal fix is a future, distinct "close/abandon PO" supervisor action —
  not a new status invented to paper over it now, and not built this
  phase. Flagged here as a real gap, not quietly worked around.
- **`InventoryAdjustment` is the one, official path for post-completion
  stock corrections (Phase 8.99c)** — customer returns, mis-keyed
  quantities, damaged goods discovered after a Purchase is `RECEIVED` or a
  Sale is `COMPLETED`. Never via editing or deleting a completed
  transaction (both are effectively append-only once terminal — Purchase/
  Sale cancellation is now pre-approval-only, see above). This is a pure
  documentation decision, not new code: `InventoryAdjustment` already had
  everything a correction needs before this phase — a mandatory `reason`
  field, `requested_by`/`approved_by`, an approval workflow, and a real
  `InventoryMovement` row on approval (`AdjustmentService.approve()`).
  Restricting cancellation without naming the existing alternative would
  leave staff no documented way to fix a mistake after the fact.
- **`PurchaseOrder.cancelled_reason`/`cancelled_by`/`cancelled_at` and the
  identical trio on `SaleTransaction` added (Phase 8.99c)** — checked
  `SCHEMA.md` §5/§6 first, per this phase's own instruction: neither model
  has any cancellation-equivalent field there (only `rejected_reason`,
  itself a Phase 8.99b addition to `SaleTransaction`, undocumented in
  `SCHEMA.md` too). A new field rather than overloading `rejected_reason`
  — cancellation and rejection are different events with different
  actors, and conflating them would make `PurchaseRejectView`'s and
  `PurchaseCancelView`'s data indistinguishable on the record itself.
  `cancelled_reason` matches `rejected_reason`'s own shape (`TextField`,
  `blank=True`, no `null=True`); `cancelled_by`/`cancelled_at` mirror
  `approved_by`/`approved_at` exactly — a reason with no attributable
  author and timestamp isn't an audit record. `ReasonForm` (already shared
  by `PurchaseOrder.reject`, `InventoryAdjustment.reject`, and
  `SaleTransaction.reject`) is reused a third/fourth time for both cancel
  views rather than writing a new form. A new `display_reason` property on
  both models (cancelled_reason if `CANCELLED`, rejected_reason if
  `REJECTED`, else empty) is the one place the list tables, per-record
  PDFs, and Purchase/Sales Report all read from — single source, not
  four places computing the same conditional independently. Migration:
  `0005_purchaseorder_cancelled_at_and_more`.
- **`build_sales_report()`'s `status=SaleStatus.COMPLETED` filter removed
  (Phase 8.99c), diverging from `10_REPORTS.md`'s own reference
  `sales_report_view`, which filters identically.** This phase's own
  Objective ("every cancellation and rejection must record a reason...
  visible wherever that record is reported or exported") cannot be met
  under a completed-only filter — a completed sale can never carry a
  cancellation or rejection reason, so the new "Reason" column (below)
  would be permanently empty for every row the report could ever contain.
  Broadened to all statuses so the column is meaningful. The Reports
  page's own revenue KPI (`ReportsView.get()`'s separate `sales_summary`
  query) is untouched — it was never sourced from `build_sales_report()`
  to begin with, so "Total revenue"/"Total transactions" still mean
  realized (completed-only) revenue, unaffected by this change.
- **`build_purchase_report()`/`build_sales_report()` both gained a
  "Reason" column, in CSV and PDF export alike (Phase 8.99c)** — sourced
  from the new `display_reason` property above. Both report builders
  already had a "Status" column (this phase's task spec assumed neither
  did — confirmed otherwise by reading `reports.py` directly before
  changing it). Disclosed as extending two of `10_REPORTS.md`'s 9
  documented, fixed-column report types rather than adding a 10th type —
  the smaller, more consistent change. The two per-record PDFs
  (`generate_purchase_order_pdf`/`generate_sale_transaction_pdf`) gained
  matching "Cancelled By"/"Cancelled At"/"Reason" rows in their existing
  metadata table via the same `_styled_data_table()` helper, no new PDF
  machinery. The Reports page's live Sales preview panel
  (`reports/reports.html`) was updated to match: a 7th "Reason" column,
  and the status badge's CSS class now follows the row's actual status
  label instead of being hardcoded to `badge-success` (accurate now that
  the preview can show non-completed rows too).
- **Movement History's search moved server-side, dropping
  `table-filter.js` from this page entirely (Phase 8.99d)** — the
  explicit choice offered by the task between "keep search client-side
  and disclose it's not exported" and "make it server-side and drop the
  client layer." Took the latter: the exact "the ledger is append-only
  and grows unbounded, so client-side filtering only ever sees one page"
  reasoning BUG-45 already used to justify server-side date range applies
  identically to search, and a permanent "search isn't part of the
  export" UI caveat is a worse outcome than just making it real,
  especially given this phase's whole point is that export must match
  filter. `q` matches product name/SKU via `icontains`. `movement-
  history.js` (this page's only consumer of `table-filter.js`) is now
  dead code and was deleted rather than left unreferenced.
- **One shared `filter_movements()` function (`frontend/reports.py`,
  Phase 8.99d) is now the single source of truth for what "the current
  Movement History filter" means** — date range, product, movement type,
  and search — called by both `MovementHistoryListView` (the page) and
  `build_movement_report()` (its CSV/PDF export, and also the Reports
  page's own "Movements" report type, which additionally applies its own
  `category` filter on top — untouched, still works, confirmed live).
  Before this, the page and the export computed date filtering two
  different ways (the page: `created_at__date__gte`; the export: this
  file's own timezone-aware `_date_bounds()`) and the export had no
  product/type/search filtering at all — an export was never guaranteed
  to match what was on screen. One function, two callers, closes that gap
  structurally rather than by convention.
- **`generate_pdf_response()` gained an optional `filters_summary` param
  (Phase 8.99d) instead of a second PDF-building function.** Movement
  History's new PDF export is the first caller to pass it (a list of
  "Label: value" strings rendered as one line under the title, e.g.
  "Filters: Product: Wireless Mouse; Type: Purchase Receipt", or "Filters:
  None — full ledger" when nothing is set) — a filtered export that
  doesn't say what it was filtered by isn't a usable record. The existing
  9 `REPORT_BUILDERS` callers (via `ReportExportView`) don't pass it, so
  their PDF output is byte-for-byte unchanged; confirmed live.
- **No "filter by cancelled/rejected source document" control was added
  to Movement History's UI, even though the task explicitly asked the
  question and the honest, join-based implementation was written and
  confirmed correct (Phase 8.99d).** `InventoryMovement` records stock
  changes only — a cancelled PO or rejected adjustment never moved stock
  (BUG-25's invariant), so it has no ledger row and never will; adding
  synthetic rows for non-events would corrupt the one honest ledger this
  app has, and was never on the table. The honest alternative — filter
  movements by the *current* status of their source document, joining by
  hand through `reference_type`/`reference_id` (no real DB FK exists
  there; `django.contrib.contenttypes` isn't used in this project) — was
  built and confirmed correct against the real dev DB. It was then
  deliberately **not** wired to a UI control, because it is not merely
  empirically empty today (0 of 19 real movements match) but
  *structurally* empty: Phase 8.99c locked cancellation/rejection to
  states strictly before any stock moves, for every one of the three
  source types (`PurchaseOrder.cancel()`/`reject()`: draft/pending only;
  `SaleTransaction.cancel_sale()`: draft/pending only, `reject_sale()`:
  pending only; `InventoryAdjustment.reject()`: pending only, before
  `approve()` ever calls `InventoryService`). A movement's source
  reaching CANCELLED/REJECTED *after* that movement was recorded is
  therefore impossible under this codebase's own enforced rules, not just
  unobserved — shipping a filter option that can never match anything
  would be exactly the `MovementType.RETURN` defect this same phase
  removes elsewhere, just reintroduced under a different name. If Phase
  8.99c's own named-but-unsolved "close/abandon PO" action is ever built,
  this becomes reachable again and the filter can be wired up then — the
  underlying function (`reference_type`/`reference_id`-based lookup) is
  documented here so it doesn't need rediscovering.
- **`reference_type`/`reference_id` confirmed consistently populated
  across every real `InventoryMovement`-writing path (Phase 8.99d
  finding, feeding the decision above).** `InventoryService.increase_
  stock()`/`decrease_stock()` both require `reference_type`/
  `reference_id` as non-default positional params — no call path can
  create a movement without them. All 3 real call sites
  (`PurchaseService.receive_items()`, `SaleService.approve_sale()`,
  `AdjustmentService.approve()`) pass one of exactly `'PurchaseOrder'`/
  `'SaleTransaction'`/`'InventoryAdjustment'`, matching each model's own
  class name. Confirmed live against the dev DB: every one of 19 real
  movements has exactly one of those 3 `reference_type` values, no stray
  or blank ones.
- **`MovementType.RETURN` confirmed unused everywhere, left on the model,
  removed from both filter UIs (Phase 8.99d).** Grepped `services.py`/
  `views.py` for `MovementType.RETURN` and for every real
  `movement_type=` call site: only `PURCHASE`, `SALE`, and `ADJUSTMENT`
  are ever produced, by exactly the 3 call sites in the finding above —
  nothing creates a `RETURN` movement anywhere in this codebase. Removed
  the option from Movement History's type filter (the only place it
  existed as UI — see below) since a filter value that can never match is
  a defect, same reasoning as removing dead sidebar links (§13, earlier).
  Left `MovementType.RETURN` on the model untouched — it's `SCHEMA.md`'s,
  and removing it is a migration for no benefit; it may stay permanently
  unused, and that's fine: Phase 8.99c already documented
  `InventoryAdjustment` as the path for customer returns, so `RETURN`
  was never going to be the mechanism.
  **Correction to this phase's own task premise**: the task described
  the dead option as being on "the main Inventory page's filter." Checked
  before removing anything — `inventory.html`'s own status filter
  (`available`/`low_stock`/`out_of_stock`, `InventoryStatus` values) has
  no movement-type concept and never had a `return` option; only Movement
  History's separate type filter did. Reported rather than silently
  "fixing" a page that had nothing to fix, or inventing a `return` option
  on Inventory's filter just to have something to remove.
- **`ProductUpdateView`/`ProductDeactivateView` (Phase 8.99e) are this
  project's first per-entity detail/update routes.** Every module before
  this phase had list+create only, by deliberate decision — no dedicated
  bullet ever recorded that decision explicitly (the closest is BUG-45's
  own entry in `docs/bugsfound.md`, which references "this project's
  existing §13 architecture decision" as if one existed; it didn't, as a
  standalone bullet — it was an emergent, consistent pattern across every
  module's views, not a written-down rule until now). Recorded properly
  here: the owner asked for editable products specifically, not a general
  "add detail routes" mandate, so only Products gained one this phase —
  every other module's list+create-only shape is unchanged.
  **Does this open the door to Suppliers/Categories edit/delete too?**
  Structurally, yes, cleanly — `SupplierForm`/`CategoryForm` already
  exist and already work for create; the exact same `instance=`-reuse
  pattern `ProductUpdateView` establishes would apply with no new
  mechanism needed. The RBAC shape is *simpler* there than Products':
  02_RBAC.md gives Products an asymmetric split (edit: all 3 roles;
  deactivate: Admin/Supervisor only), but "Create/edit categories" and
  "Manage suppliers" are both flatly Admin/Supervisor-only (no Staff
  access to either verb) — so both edit and deactivate would share one
  `SupervisorRequiredMixin` gate each, not two different mixins on two
  buttons the way Products needed. **Recommendation: don't build them
  this phase** (this task's own "Products only" scope, and "one
  responsibility per phase" — Purchases/Sales' edit views and PO/sale
  detail pages are still-pending per §17 too, and also out of scope
  here) — **but do build them next**, back to back if the owner wants,
  since the pattern this phase establishes (reuse the existing form via
  `instance=`, one shared modal-JS parameterization, embed pre-fill JSON
  on the row like `purchases.html`'s own `receive_items_json`) transfers
  directly with no new design work, just repetition of a now-proven shape.
  **Superseded, Phase 8.99i: built.** Both modules got the full pattern —
  `CategoryUpdateView`/`SupplierUpdateView` (`AnyStaffMixin`) +
  Deactivate/Reactivate/Delete (`SupervisorRequiredMixin`), same shape
  predicted here, transferred with no new design work as expected.
- **SKU is read-only on `ProductUpdateView` (Phase 8.99e), a disclosed
  decision — no doc gives SKU an editable-after-creation rule either
  way.** It's an identifier the product is referenced by across the app
  (POs, sales, reports, already-issued PDFs) and changing it post-
  creation has no documented use case, so the safer default was chosen.
  Enforced server-side, not just by disabling the client-side input: the
  posted `sku` is always overwritten with the instance's current value
  before `ProductForm` ever validates it — this also sidesteps a real
  gotcha, since `ProductForm.clean_sku()`'s "blank -> auto-generate a new
  one" branch exists for *create*, and a disabled input (which browsers
  simply omit from a submission) would otherwise silently trigger it on
  every edit. Confirmed by test (`test_sku_is_immutable_on_edit_even_if_
  tampered`): a tampered POST attempting to steal another product's SKU
  succeeds (the rest of the edit is valid) while the SKU itself is left
  completely unchanged — not an error, just a no-op on that one field.
  As a consequence, this phase's own Verification ask — "test a
  duplicate SKU on edit specifically" — is structurally impossible to
  exercise as literally worded (the edit endpoint never lets a client-
  supplied SKU reach uniqueness validation at all); tested barcode's
  uniqueness constraint instead, which genuinely does re-run
  `ProductForm`'s validation end-to-end on edit and proves the same
  underlying mechanism (`ModelForm.validate_unique()`) still applies.
  Disclosed here rather than silently substituted.
- **"Delete" relabelled to "Deactivate" on the Products row action (Phase
  8.99e), not kept as "Delete" with soft-delete behavior underneath.**
  03_PRODUCTS.md is explicit: never hard-delete, only `is_active = False`
  — a button labelled "Delete" that actually deactivates is a UI lie a
  confirm() dialog doesn't fully cure (a user who skims past the confirm
  text still expects "Delete" to mean gone). The honest label was chosen
  over keeping familiar icon/copy.
- **`InventoryService.sync_reorder_level()` added (Phase 8.99e) — the
  only `InventoryService` change this phase made**, per its own explicit
  scope limit. `Product.reorder_level`/`InventoryRecord.reorder_level`
  are undocumented duplicates of each other (§6) with no prior sync path
  outside of initial creation (`initialize_for_product()`'s own
  `defaults=`, which only ever applies once, at `get_or_create` time).
  Editing a product's reorder_level needed *some* way to propagate to
  `InventoryRecord` — kept inside `InventoryService` rather than written
  directly from `ProductUpdateView`, since that class's own docstring
  already claims sole ownership of writing `InventoryRecord` fields; a
  view reaching around it to mutate `InventoryRecord` directly would be
  exactly the kind of bypass that docstring exists to prevent. Writes no
  `InventoryMovement` row — a reorder-threshold change isn't a stock
  movement, same reasoning `initialize_for_product()` already uses for
  product creation — but does call `update_status()`, since moving the
  threshold can flip `LOW_STOCK`/`AVAILABLE` on its own with
  `current_stock` unchanged.
- **Reactivate was not built for Products this phase (Phase 8.99e),
  despite Users having an exact precedent (`UserReactivateView`/
  `USER_REACTIVATED`) to mirror.** Recommended for symmetry — a
  deactivated product currently has no path back except `/admin/` — but
  the task's own request was Edit/Delete, not Edit/Delete/Reactivate, and
  this project's now-established discipline (Phase 8.99c's "stranded PO"
  gap: name the follow-up, don't build it opportunistically inside an
  unrelated phase) says the same here: flagged as a natural, low-effort
  next step (the shape is already proven by `UserReactivateView`), not
  built now. **Superseded, Phase 8.99i: built** — `ProductReactivateView`,
  same `SupervisorRequiredMixin` gate as Deactivate, plus the identical
  shape for Categories/Suppliers.
- **`InventoryModal.open()` added to `modal.js`'s public API (Phase
  8.99e)** — only `close()` existed before. A row action (Edit) needs to
  populate a modal's fields *before* it becomes visible, which a plain
  `data-modal-open` trigger can't do (it fires the open on click, with no
  hook to run code first) — exposing the controller's own existing
  `openModal()` internal function is a minimal, backward-compatible
  addition to a shared file, not a new modal mechanism; every existing
  `data-modal-open` trigger elsewhere in the app is completely unaffected.
- **`audit.USER_DELETED` added (Phase 8.99f-2), undocumented in
  `13_AUDIT.md`'s own action table.** Disclosed the same way `SALE_
  PENDING` was (Phase 8.99b): not in the doc, added anyway because it's
  load-bearing — a true user delete with zero audit trail would be a
  worse gap than the one it closes. `UserDeleteView` is deliberately
  narrow: it only ever succeeds for a user referenced by none of
  `PurchaseOrder`/`SaleTransaction`'s 6 `PROTECT` FKs
  (`created_by`/`approved_by`/`cancelled_by` on each),
  `InventoryMovement.performed_by` (`PROTECT`), `InventoryAdjustment.
  requested_by`/`approved_by` (`PROTECT`), or `AuditLog.user`
  (`SET_NULL`) — every other user gets a clean refusal ("has activity
  history... deactivate instead"), never a `ProtectedError` 500 and
  never a silently-nulled audit actor. One shared helper
  (`_user_ids_with_history()`, `frontend/views.py`) computes this once
  and is read by both `UserListCreateView.get()` (which rows get a
  "Delete" pill) and `UserDeleteView` (the actual enforcement) — the same
  "server check is the real gate, showing the button is UX" split this
  project has used since Phase 8.5, applied to a destructive action for
  the first time. `UserDeactivateView`/`UserReactivateView` (Phase 8)
  needed no changes at all — they already existed, complete, correctly
  labelled, and already wired into `users.html`; the task's prediction
  that the row pill was a mislabelled/dead "Delete" button turned out not
  to match this codebase's actual state, confirmed by reading the
  template and JS before changing anything.
- **The sidebar notification badge and the topbar bell dot now share one
  poll instead of each getting their own (Phase 8.99f-2).**
  `notifications.js`'s existing `pollUnreadCount()` (Phase 8, originally
  topbar-only) was extended to also update the sidebar's badge element
  from the same `fetch('/notifications/unread-count/')` response, rather
  than adding a context processor or a second `setInterval`. The two
  badges differ only in presentation (the topbar's is a plain dot; the
  sidebar's shows the real number) but now always agree on the
  underlying count and on hiding entirely at zero — they physically
  cannot disagree, since one callback sets both. The sidebar badge starts
  `hidden` in the server-rendered markup, same as the topbar dot always
  has, rather than showing a stale or zero value until the first poll
  resolves.
- **`config/settings.py` gained an explicit `sys.argv[1] == 'test'` guard
  pinning `EMAIL_BACKEND` to `locmem` (Phase 8.99f-7), on top of
  Django's own `setup_test_environment()` doing the identical thing
  automatically.** Confirmed-redundant, kept anyway: Django's mechanism
  was directly proven reliable (inspected `settings.EMAIL_BACKEND` after
  it ran, with real SMTP credentials genuinely present in `.env`) before
  this guard was even written, so this isn't "fixing" anything — it's
  making "tests can never send real email" a property of this project's
  own settings file, not solely of an external library's behavior this
  project has no control over if its test-running path ever changes.
- **`audit.USER_CREDENTIALS_RESENT` added (Phase 8.99f-7), same
  disclosure treatment as `USER_DELETED` (§13, Phase 8.99f-2) —
  undocumented in `13_AUDIT.md`, added because the alternative (a resend
  action with no audit trail) is a worse gap than the one it closes.**
  A real, deliberately-wrong-app-password test this same phase produced
  a genuine SMTP failure live, underscoring that "resend" is a real
  operational action now that real SMTP is the resting default, not a
  hypothetical one.
- **`EMAIL_TIMEOUT` added (Phase 8.99f-7, default 10s, env-overridable)
  — not documented in `ENVIRONMENT.md`'s original 5-var SMTP list.**
  Python's `smtplib` has no default timeout; a hung connection would
  otherwise block the whole request indefinitely rather than failing
  into the caught-exception path `send_new_user_credentials_email()`
  already has. Disclosed the same way the other 5 SMTP vars were
  (Phase 8.99): a real, deploy-relevant setting the original doc list
  didn't anticipate.
- **`.env.example`'s `EMAIL_BACKEND`/`DEFAULT_FROM_EMAIL` are omitted
  entirely rather than present-but-empty (Phase 8.99f-7, correcting
  8.99f-6's own version of this file).** Confirmed live:
  `os.environ.get(KEY, default)` only uses `config/settings.py`'s own
  safe fallback when the key is genuinely absent from the environment —
  `KEY=` (present, empty string) overrides that fallback with `''` and
  would crash on an empty backend import path / empty From address. The
  other EMAIL_* keys with empty-string-safe defaults (`EMAIL_HOST_USER`/
  `EMAIL_HOST_PASSWORD`) stay as blank lines, since blank is genuinely
  equivalent to absent for those two specifically.
- **`seed_dev_data.py` backdates its ledger via a queryset-level
  `InventoryMovement.objects.filter(...).update(created_at=...)` (Phase
  9.5) — deliberately bypassing both `auto_now_add` and BUG-20's own
  immutability guard.** This exists so Phases 10/11 (AI demand
  forecasting, slow-moving/dead-stock classification) have real data
  spanning the 60/180-day thresholds and a real `stockout_flag`-triggering
  window to be right or wrong about — the dev DB otherwise has every row
  dated "today" (every seeded sale/movement created within the same few
  real seconds). **This is DEBUG-guarded dev-fixture mutation, not a
  production code path.** `InventoryMovement.save()`'s `if self.pk: raise
  PermissionError` guard (BUG-20) is completely untouched — `.update()`
  bypasses `save()` by design (it goes straight to SQL), which is exactly
  why it's the only way to do this at all, not a workaround discovered by
  accident. No application code outside this one management command gains
  the ability to mutate a movement row. **Any future `.update()` call
  against `InventoryMovement` outside a seed command is a bug, not
  precedent set by this file** — flagged explicitly so it doesn't get
  cited as "we already do this elsewhere" later.
  Two related, smaller Phase 9.5 disclosures on the same file:
  (a) `PurchaseOrder._generate_po_number()`/`SaleTransaction.
  _generate_invoice_number()`'s 4-digit random suffix (no collision-retry
  loop, already disclosed as a known limitation alongside BUG-47) hit real
  birthday-paradox collisions at this seed's volume — every PO/sale is
  created within the same few seconds of real wall-clock time regardless
  of which historical date it's backdated to afterward, so ~200+ rows draw
  from the same "today" 9000-value number space. Fixed with a retry loop
  in the seed command only (`_new_po()`/`_new_sale()`); the real generator
  in `models.py` is untouched — this is seed-volume-specific, not a
  latent production bug (no real deployment creates hundreds of POs/sales
  in the same few seconds). (b) `SystemSettings.email_notifications_enabled`
  is force-set to `False` before any bulk purchase/sale is created (~250+
  approval-type events, each of which would otherwise fire a real
  synchronous `send_mail()` per `frontend/notifications.py`'s
  `_maybe_send_email()`) and left off after seeding; an admin can
  re-enable it from the Settings page. In-app `Notification` rows are
  unaffected, only the email side effect.
- **Part A's premise (Phase 9.5 task spec) — that `SaleTransaction.save()`/
  `PurchaseOrder.save()` needed changing from unconditional date
  assignment to "assign only if unset" — did not match the actual code,
  checked before changing anything.** Both already read `if self.
  transaction_date is None: ...` / `if self.order_date is None: ...`
  (this was already true going into Phase 9.5; BUG-47's Phase 8.99 fix
  happened to write it this way, not for backdating purposes — TIME_ZONE
  correctness was the only goal at the time). No model change was made.
  `ExplicitDateAssignmentTests` (`frontend/tests.py`) proves the
  consequence that matters — a caller that constructs the model with the
  field already populated gets that exact value, not "today" — which is
  the whole mechanism `seed_dev_data.py` relies on. Confirmed separately
  (Part A step 2) that this is a capability, not a hole: `PurchaseOrderForm`/
  `SaleTransactionForm.Meta.fields` never list `order_date`/
  `transaction_date`/`approved_at`, and every real view path only ever
  passes form `cleaned_data` into the service layer — a crafted POST
  cannot inject a date. `approved_at` (`PurchaseOrder`/`SaleTransaction`/
  `InventoryAdjustment`) is set unconditionally to `timezone.now()`
  *inside* `PurchaseService.approve()`/`SaleService.approve_sale()`/
  `AdjustmentService.approve()` — not via `save()`/`auto_now` — and was
  deliberately left that way (no service-layer date parameter added, per
  this task's own explicit instruction); the seed calls the real service
  method for its real business logic, then does an ordinary
  `.save(update_fields=['approved_at'])` afterward. This isn't a bypass of
  anything — `approved_at` carries no immutability guard the way
  `InventoryMovement`'s fields do — so unlike the ledger-backdating
  finding above, it needed no disclosure of its own.
- **`docs/DEMAND_FORECASTING.md`'s `get_sales_dataframe()` reference code
  has no `transaction__status='completed'` filter at all, unlike
  `docs/DEAD_STOCK_DETECTION.md`'s `get_last_sold_date()`/
  `calculate_turnover_rate()`, which both filter on it explicitly (Phase
  9.5 finding, while building non-completed seed records to prove "AI
  queries exclude them" per that phase's own Verification step).** Not
  fixed here — Phase 10's forecaster doesn't exist yet, and this file's
  scope is data only, not classifier/forecaster code. Flagged for whoever
  implements Phase 10: as literally documented, `get_sales_dataframe()`
  would include `SaleItem` rows from draft/pending/rejected/cancelled
  sales too (they all have real `SaleItem` rows from
  `SaleService.create_sale()` regardless of whether the sale ever gets
  approved), inflating demand. The seed's non-completed sales (3 pending,
  2 rejected, 2 cancelled) deliberately sit on cohort products that
  already have a stable, separately-measured last-sold date specifically
  so this gap is visible/testable the moment Phase 10 is built, not
  discovered later against production data.
- **Part D (Phase 9.5) — `transaction_date` (not `approved_at`) stays the
  field both AI docs key off; not changed.** A draft-to-approval gap is
  real (`transaction_date` is stamped at draft creation, `approved_at` at
  approval, and nothing in this codebase bounds how long a sale can sit
  PENDING in between) but is judged noise-level at the granularities both
  features actually use: weekly/monthly aggregation for forecasting, and
  60/180-*day* thresholds for classification. A sale drafted Sunday night
  and approved Monday can shift one unit of demand into an adjacent
  weekly bucket; it essentially never moves `days_since_last_sale` across
  a 60- or 180-day boundary. `transaction_date` is also the semantically
  right field regardless of the gap's size — it's the business's record
  of when the sale happened, not of when the internal approval paperwork
  caught up; `approved_at` reflects workflow timing, not demand timing.
  Both AI docs already specify `transaction_date` as the join key, so
  switching would mean editing two reference-code specs to fix a skew
  smaller than the noise real sales data has anyway. Revisit only if this
  system is ever extended to allow long-pending (multi-week) approval
  queues, which would be a process problem worth its own fix regardless
  of which date field forecasting reads.
- **Backend Phase 10 — the documented `post_save(SaleTransaction)`
  reclassification signal was rejected; an explicit synchronous call at
  the end of `SaleService.approve_sale()`/`cancel_sale()` was used
  instead.** Verified both of the task's suspected reasons against the
  actual code before deciding: (1) `create_sale()`'s very first
  `SaleTransaction.objects.create(...)` fires `post_save` before any
  `SaleItem` exists (they're created in the loop immediately after) —
  true, but harmless in isolation, since a naive `if instance.status ==
  'completed'` guard would already skip that save (status defaults to
  DRAFT). (2) The real problem is architectural, not timing: a signal
  fires on *every* save of the model — create, submit, approve, reject,
  cancel, roughly 3-5 saves per sale lifecycle — and correctness would
  depend entirely on an incidental status-string check getting it right,
  not on the signal genuinely being scoped to "stock just moved." It also
  can't cover `cancel_sale()` at all without a second condition (`status
  == 'completed' OR status == 'cancelled'`), silently grows every time a
  new save-triggering transition is added, and lives in a separate
  `signals.py` a reader of `services.py` — where every other real
  business event in this app is already legible — would have no reason to
  know exists (this project's established explicit-call-sites discipline:
  `notify_user()`/`notify_supervisors()` are already "the ONLY code path
  allowed to create Notification rows," not a signal either).
  **Bulk-seed volume, checked and disclosed as asked:** `seed_dev_data.py`
  calls `approve_sale()` ~180+ times per run, each one now firing a real
  `classify_product()` call against whatever the DB looks like at that
  exact moment in real execution time — which is *not yet backdated* (the
  seed's own backdating follow-up runs after each service call returns).
  Every one of those ~180 intermediate classifications is computed
  against wrong (not-yet-backdated) dates and gets silently overwritten
  by the next real event for that product; only a final
  `run_full_classification()` call, added to the very end of the seed
  command after every date in the dataset is already correct, produces
  the classification state the Phase 9.5 cohort table was built to prove.
  Confirmed live: 177 `AI_PRODUCT_RECLASSIFIED` audit rows from one seed
  run, all superseded by the closing pass. Not "thousands," but real, and
  the seed would produce a wrong final dataset without the closing call.
  **`cancel_sale()`'s reclassification is a same-result no-op by design,
  included anyway per the task's explicit instruction.** `cancel_sale()`
  only ever runs on DRAFT/PENDING sales (8.99c) — pre-approval, so no
  stock has moved and no `SaleItem` there has ever counted toward
  `get_last_sold_date()`/`calculate_turnover_rate()` (both filter
  `status=COMPLETED`); `classify_product()` will recompute the exact
  result it already has. Kept for a genuine reason, not just compliance:
  keeps `classified_at` a real "last touched" timestamp, costs one cheap
  query per line item, and needs no future code change if a
  classification signal ever does start reading non-completed sales. No
  `AI_PRODUCT_RECLASSIFIED` audit row is logged for this path specifically
  — logging a "reclassified" entry for a call that changes nothing would
  be audit-log noise, not a real event.
  **Two further translations, both disclosed:** `classify_product()`'s
  `today = timezone.now().date()` (UTC calendar date) → `timezone.
  localdate()` (Asia/Dhaka) — same class of bug as BUG-47, proven by a
  test where the classification genuinely flips (SLOW vs FAST) depending
  on which "today" is used. The doc's bare `'completed'` string literal →
  `SaleStatus.COMPLETED`, the real enum this codebase reads everywhere
  else (identical value, not a behavior change).
  **DRF slice (Phase 9's pre-commitment, built here):**
  `ClassificationListAPIView`/`ClassificationSummaryAPIView`, one new
  permission class (`IsSupervisorOrAbove`, matching the
  `SupervisorRequiredMixin` gate already on the page), `frontend/
  serializers.py`'s `InventoryClassificationSerializer` used verbatim from
  the doc — every field it names matched the real model with no
  adjustment needed. `djangorestframework==3.18.0` installed (was not
  installed before this phase — Phase 9 confirmed DRF wasn't in
  `requirements.txt`). `RunClassificationAPIView` deliberately not built
  — it `.delay()`s a Celery task and Celery isn't installed; the manual
  "Run classification now" POST (`SlowMovingDeadStockView.post()`,
  guarded by the same `SupervisorRequiredMixin` the GET already had —
  not re-added, not changed) is the only trigger. The doc's
  slow/dead supervisor notifications, documented as living inside that
  same un-built Celery task, are fired from the manual Run view instead
  via `notify_supervisors()` — the REQ-covered behavior isn't lost to a
  host that was never going to exist.
  **`AI_PRODUCT_RECLASSIFIED` added to `audit.py`** — named in
  `DEAD_STOCK_DETECTION.md`'s own Audit Actions table alongside
  `AI_CLASSIFICATION_RUN`/`AI_CLASSIFICATION_FAILED` (both of which
  already existed in `audit.py` before this phase) but never added when
  those two were.
  **A real bug found while testing the `calculate_average_stock()` fix,
  not asked for but disclosed and fixed**: `calculate_turnover_rate()`'s
  `total_sold / avg_stock` has no ceiling, and `InventoryClassification.
  turnover_rate` is `DecimalField(max_digits=8, decimal_places=4)` — a
  hard ceiling of 9999.9999. A product whose entire stock history
  (received, then sold) falls within a tiny slice of the 90-day window
  drives `avg_stock` toward zero and the ratio into the billions,
  overflowing the field outright (a real `DataError` crash, proven by a
  test that approves a sale moments after the product's own initial stock
  receipt — exactly the shape a brand-new, fast-selling product would
  produce in real usage, not just a test artifact). Capped at the field's
  own ceiling in `calculate_turnover_rate()`; turnover is informational
  only, never a classification gate, so capping it changes no
  classification outcome. Documented as the Design Notes' 4th disclosed
  revision alongside the 3rd (the `calculate_average_stock()` fix itself)
  directly in `docs/DEAD_STOCK_DETECTION.md`, matching that doc's own
  established self-correcting convention — unlike `TECH_STACK.md`/
  `API_CONTRACTS.md` (left untouched per Phase 9's finding), this doc
  explicitly hosts its own revision history inline.
- **Backend Phase 11: Demand Forecasting — real pipeline
  (`frontend/forecasting.py`), implementing `DEMAND_FORECASTING.md`'s own
  7 disclosed Design Notes revisions (HistGradientBoostingRegressor,
  chronological split, two-tier model selection, category_id/
  stockout_flag features, the lag-shift fix, backtest-residual
  confidence, `backfill_actual_demand()`) plus real bugs found while
  building against pandas 3.0.5 and this project's real seeded data —
  none of them anticipated by the doc, all found by actually running the
  code against real data rather than trusting it as written.**
  1. **`get_sales_dataframe()`'s date column was silently never
  converted.** The reference code assigns the *converted* datetime into a
  new `transaction_date` column, then renames the *original,
  still-object-dtype* `transaction__transaction_date` column to `date` —
  the column `build_features()` actually indexes on. `date` stayed
  object-dtype the whole time; harmless-looking until `df.set_index(
  'date').resample()`, which requires a genuine DatetimeIndex. pandas
  3.0.5 (installed here) raises `TypeError` loudly; this bug doesn't
  depend on that version, only its symptom's loudness does. Fixed:
  rename first, convert the correctly-named column in place, no second
  column. Pinned by `test_get_sales_dataframe_date_column_is_real_datetime`.
  2. **A tz-aware/tz-naive merge failure in `get_stockout_flags()`.**
  `InventoryMovement.created_at` is a `DateTimeField` (timezone-aware,
  `USE_TZ=True`); `SaleTransaction.transaction_date` is a plain
  `DateField`. Feeding the former straight into `pd.to_datetime()`
  produces a tz-*aware* index; `build_features()`'s sales-side
  `period_start` is tz-*naive*. `merge()`-ing the two raises
  `ValueError` on pandas 3.0 ("You are trying to merge on datetime64[s]
  and datetime64[us, UTC] columns"), not a silent misjoin. Fixed the
  same way BUG-47 fixed an unrelated date bug: `timezone.localtime(dt)
  .date()` before comparing, tz-naive on both sides and the correct
  Asia/Dhaka calendar day besides.
  3. **pandas 3.0 removed the bare `'M'` resample alias** ("'M' is no
  longer supported for offsets. Please use 'ME' instead") — a real,
  version-specific breaking change, not documented anywhere. The public
  API of every function in this module still speaks `'W'`/`'M'` (
  `ForecastPeriod`'s own vocabulary); only the internal `.resample()`
  call needed the translation (`_RESAMPLE_ALIAS = {'W': 'W', 'M': 'ME'}`).
  `predict_demand()`'s own `freq='MS'` (Month Start, a different, still-
  valid alias for stepping `period_start` forward) was unaffected.
  4. **A pandas 3.0.5 `reset_index()` column-naming assumption
  (`get_stockout_flags()`'s `rename(columns={'index': ..., 0: ...})`)
  was verified empirically before relying on it, per this phase's own
  instruction** — confirmed correct for this version (an unnamed Series
  with an unnamed DatetimeIndex resets to columns `['index', 0]`,
  exactly as the doc assumes), not taken on faith.
  5. **Phase 9.5's stockout cohort needed more pre-stockout runway —
  found here, fixed in `seed_dev_data.py`, not a pipeline bug.**
  `get_stockout_flags()` computed the right day and flag in isolation
  (proven by `test_stockout_flag_computed_correctly_in_isolation`), but
  the merge into `build_features()` silently dropped it: the stockout
  fell inside the first ~4 weekly buckets of that product's *entire*
  sales history, and `dropna()` (`lag_4` needs 4 prior periods) trims
  exactly those buckets regardless of what's in them. `_build_stockout()`
  now puts 6 sales (~7 weekly buckets) ahead of the stockout instead of
  3, so the dropna() burn-in eats only leading weeks, not the stockout
  week itself. Re-verified against the real seed: `stockout_flag == 1`
  survives into training features for both stockout-cohort products.
  6. **`run_full_forecast()` trains 'W' and 'M' independently, not
  as an all-or-nothing pair — found by testing, not documented.**
  `train_model()`'s own `len(df_features) < 10` guard is far harder to
  satisfy for monthly resampling than weekly (a product needs roughly 14
  months of history, pooled across products, before monthly rows survive
  `dropna()` at all) — a system with solid weekly history but not yet
  enough monthly history would otherwise lose its perfectly valid weekly
  forecasts too, since the original design raised on the first failing
  `train_model()` call before either period's forecasts were generated.
  Each period's training failure is now caught independently
  (`periods_trained`/`training_errors` in the returned summary); only
  raises if *neither* period can train. Real seed data (Phase 9.5) trains
  both periods successfully (MAE ≈ 3.2 weekly, ≈ 12.5 monthly) — this
  matters for a newer/smaller install, not this project's own dataset.
  7. **A cosmetic sklearn `UserWarning` ("X does not have valid feature
  names, but OrdinalEncoder was fitted with feature names") on every
  single forecast** — `train_model()` fits on a DataFrame (named
  columns), `predict_demand()` predicted from a bare array. Fixed by
  predicting from a `DataFrame` with the same `FEATURE_COLUMNS`; no
  behavioral change, just stops what would be log spam in production.
  8. **`DemandForecastSerializer` isn't defined anywhere in
  `DEMAND_FORECASTING.md`** (referenced by name in the API Views section,
  unlike `InventoryClassificationSerializer`'s full "## Serializer"
  section in the sibling doc) — built following that same
  product_name/product_sku-plus-real-fields shape, since nothing about
  `DemandForecast`'s own fields suggested a different one.
  9. **Two honest, non-bug characterizations, not overclaimed as
  clean wins.** The trending cohort's actual `predict_demand()` output
  oscillates (e.g. 6.7 → 14.27 → 7.91 → 12.72 units/week for Portable
  Power Bank) rather than rising monotonically — the lag-rotation logic
  is verified correct (Design Note 5), and the values sit well above
  that product's own early-history baseline, but tree ensembles
  (`HistGradientBoostingRegressor` included) fundamentally cannot
  extrapolate past values seen in training; Design Note 1's claim is
  that HGB generally outperforms `RandomForestRegressor` on tabular
  data and supports native categorical features, not that it solves
  non-extrapolation outright. Separately, several different products'
  *furthest*-ahead monthly forecasts converge to identical values — a
  real characteristic of a pooled model trained on sparse monthly data
  (each product has at most a few months of real history in this seed),
  not a code defect; not chased further given the seed's own modest
  scale.
  10. **Model persistence (`ai_models/`, local disk via `joblib`) makes
  an ephemeral production disk survivable, at a real cost — noted, no
  production storage decision made here.** `predict_demand()`'s
  `except FileNotFoundError: train_model(...)` fallback is proven
  end-to-end by `test_predict_demand_auto_trains_when_model_file_missing`
  (delete the file, call predict, it retrains inline and returns real
  predictions, no 500) — this means a Render-style redeploy that wipes
  `ai_models/` degrades to "the first forecast request after a redeploy
  is slow" rather than "forecasting breaks," but every subsequent
  request until the *next* redeploy still hits a cold-started model file
  with no cross-request caching benefit beyond that first request. No
  persistent volume / object storage wiring is in scope here — flagged
  for whenever production deployment (Phase D, per `ENVIRONMENT.md`) is
  addressed for real.
  11. **DRF: `ForecastListAPIView`/`ForecastSummaryAPIView` (Phase 9's
  second pre-committed slice), reusing Phase 10's one permission class
  (`IsSupervisorOrAbove`) — no new permission class added.**
  `RunForecastAPIView`/`ProductForecastAPIView` deliberately not built
  (Celery; not needed for this phase's own verification, respectively).

- **Phase 11.5 extends the Phase 9.5 seed-only ledger-backdating disclosure
  above to a much larger dataset (20 → 43 products, ~30 → ~55 weeks of
  history on every forecastable cohort) — same mechanism, same
  DEBUG-guard, same untouched `InventoryMovement.save()` guard, nothing
  new to disclose about *how* it backdates.** What's new: 5 demand-pattern
  cohorts (`trending` extended from 2→5 products; `trending_down`,
  `seasonal`, `steady`, `spiky` added, 4-7 products each), each generated
  from an explicit shape — base level + linear trend and/or a sinusoidal
  seasonal term + bounded noise (`_weekly_series()`) — not a random walk,
  so the forecaster's recovery of each shape could be checked directly
  rather than assumed. All 8 original Phase 9.5 cohorts are unchanged in
  shape and re-verified: same classification outcomes, same collision-
  retry/coherence/idempotency guarantees. A new `_stock_and_sell()` helper
  replaced the old hand-picked two-receive schedule for every
  history-heavy cohort (three receives, each sized at 55% of that
  product's own total generated demand) — a fixed schedule doesn't scale
  once a product's year-long total demand isn't known until its shaped
  series is actually generated; verified no `InsufficientStock`-class
  error occurred across a full run. Result: 40 of 43 products now forecast
  (vs. Phase 11's 17 of 20) — the 3 non-forecastable products are the same
  *kind* of gap as before (2 never-sold, 1 short-history-only), not a new
  one; every genuinely patterned product now clears `build_features()`'s
  dropna() burn-in with 45-52 training rows (vs. as few as 6-9 for the
  smaller Phase 9.5 trending pair).
- **A genuine `predict_demand()` bug, exposed by this phase's richer data,
  reported here rather than fixed (out of this phase's scope — seed data
  only).** Single-step-ahead forecasts correctly recover every cohort's
  shape (trending-up step-1 predictions land at/above each product's own
  recent average; trending-down at/below; steady stays close to its flat
  recent level; spiky comes in elevated but bounded) — the seed's signal
  is real and learnable. But `predict_demand()`'s recursive multi-step
  loop (frontend/forecasting.py, the `for i in range(1, periods_ahead+1)`
  block) only rotates `lag_1..lag_4` and recomputes `rolling_avg_4` each
  step; `period_num`, `rolling_std_4`, `category_id`, and `stockout_flag`
  are copied once from the last real row and never advance across steps
  2-4. Design Notes revision #5 (Phase 11) correctly stopped scrambling
  these into the *wrong* feature slots (the original `np.roll()` bug) but
  never added the missing advancement of `period_num` — every forecasted
  step after the first is scored with a stale temporal-position feature
  the model never saw paired with that step's lag values during training,
  which plausibly explains the non-monotonic, sometimes direction-
  reversing sequences observed in the weekly trend chart (e.g. one
  trending-down product's forecast rising from 2.46 to 4.84 units/week
  over its own 4-period horizon). Phase 11's own item 9 above attributed
  similar oscillation entirely to tree ensembles' inability to extrapolate
  past training values — that ceiling is real and unrelated to this, but
  this frozen-`period_num` gap is a separate, narrower, and fixable code
  issue this phase's wider variety of trending/seasonal cohorts made
  visible for the first time. Not patched here per this phase's explicit
  scope (seed data only); flagged for a future forecasting.py phase.

- **Phase 12: Approval Authority Matrix — the static `@supervisor_required`/
  `SupervisorRequiredMixin` role check is now a floor, not the whole
  answer.** "The supervisor approves transactions. The admin defines which
  transactions the supervisor is permitted to approve." New model
  (`ApprovalPolicy`, §6) + resolver (`frontend/approvals.py`:
  `resolve_required_level()`/`can_approve()`) govern three actions:
  `PurchaseService.approve()`, `AdjustmentService.approve()` (+ a new
  `AdjustmentService.create()` for the AUTO fast path), and
  `SaleService.cancel_sale()`. **Fail-closed is the core design
  principle**: no matching active policy → required level is `ADMIN`,
  never `SUPERVISOR`, never `AUTO` — a transaction the ruleset can't
  classify needs the most senior signature, by construction. The gate
  lives *inside* the service layer, not only the view — `SupervisorRequiredMixin`
  stays as the coarse floor (can this role ever reach this URL), `can_approve()`
  narrows further per-transaction and is called from the service methods
  themselves (§6's own instruction: the service layer is the boundary
  that must hold "regardless of caller" — proven by this phase's own
  `ApprovalAuthorityServiceLayerTests`, which call the services directly,
  bypassing views entirely).
  Two premise gaps found during discovery, reported before writing code
  rather than guessed past (this task's own explicit instruction):
  1. **No pre-existing purchase-order approval value ceiling existed
  anywhere in this codebase** — confirmed by reading `SystemSettings`'
  full field list and `PurchaseService.approve()` line by line; grepped
  the whole tree for `ceiling`/`approval_limit`/`approval_threshold` and
  found only an unrelated Phase 10 `turnover_rate` overflow cap. The
  task's own brief (§2/§3) assumed one existed and asked for a data
  migration converting it byte-identically into two seeded policy rows —
  there was nothing to convert *from*. The seed migration
  (`frontend/migrations/0007_seed_approval_policies.py`) writes the
  starting ruleset directly; the ৳50,000 purchase-order supervisor/admin
  split is a fresh value, confirmed with the user (not invented, not
  inherited).
  2. **`InventoryAdjustment` has no stored currency value or "variance"
  concept at all** — only `quantity` + `adjustment_type`. Both are
  computed at resolution time, not stored: `value = quantity *
  product.purchase_price`; `variance_pct = |quantity| / current_stock *
  100`, `None` when `current_stock` is 0 (an undefined variance against a
  zero base, deliberately excluded from matching — falls through to a
  catch-all/Supervisor rule rather than satisfying an AUTO threshold on a
  technicality). `ApprovalPolicy.max_variance_pct`'s comparison direction
  isn't fixed by the model spec alone, so it's disclosed here: for an
  ADMIN-outcome policy it's a floor variance must *exceed* to match
  (escalate when unusually high); for AUTO/SUPERVISOR-outcome policies
  it's a ceiling variance must stay *at or below* to match (only
  automate/keep-at-supervisor when routine).
  A third, unforeseen interaction found empirically, not assumed: **`seed_dev_data.py`'s
  own `call_command("flush", ...)` truncates the `ApprovalPolicy` table
  along with everything else — but a data migration only seeds it once,
  so the table stayed empty on every reseed, and every `approve()`/
  `cancel_sale()` call in that command started failing closed to Admin**
  (found by actually running the seed command post-migration, not
  assumed safe). Fixed by extracting the starting ruleset into
  `frontend.approvals.DEFAULT_APPROVAL_POLICIES` +
  `ensure_default_policies()` (idempotent, `get_or_create`-based) —
  the migration keeps its own frozen, self-contained snapshot (migrations
  must never import evolving app code) and `seed_dev_data.py` now calls
  `ensure_default_policies()` right after its own flush to restore the
  same ruleset for dev purposes. One real, disclosed behavior change this
  exposed: `seed_dev_data.py`'s `_build_non_completed_records()` had
  `self.staff` cancel a draft sale directly via the service layer — this
  only ever "worked" because the service layer never checked role before
  Phase 12 (the *view*'s `SupervisorRequiredMixin` already made this
  unreachable for a real staff user); changed to `self.supervisor` to
  match what was already true everywhere a real user hits this action.
  **Self-approval blocking (§5 rule 5) is a deliberate reversal of a
  previously-disclosed decision**: Phase 7/8.99b's `SaleApproveView`
  explicitly documented "no creator≠approver restriction, deliberately
  matching how Purchases already works." Phase 12 reverses this —
  `block_self_approval` defaults `True` per-policy, admin is always
  exempt, supervisor is not — flagged here as an intentional overturn,
  not a silent inconsistency.
  `ABCClass`/`recompute_abc_classes()` (cumulative revenue contribution,
  trailing 90 days — same window as `calculate_turnover_rate()`, 80/15/5
  split) lives on `InventoryClassification`, not `Product` or
  `InventoryRecord`: it's the same *kind* of field
  (`StockClassification`/`turnover_rate`) already there — a derived,
  batch-recomputed, sales-history classification — not static catalog
  data or live per-movement stock state. No Celery task schedules it
  (§7's brief assumed one; none exists anywhere in this project,
  `frontend/forecasting.py`'s own docstring already discloses the same
  absence) — folded into `run_full_classification()`'s own closing step
  instead, matching this project's established "every AI/analytics pass
  is a manual synchronous run" pattern.
  DRF/UI: `AdjustmentReason` (structured reason code, required alongside
  the existing free-text `reason`) lets policies route on adjustment
  reason; the admin-only Approval Policy screen
  (`/settings/approval-policies/`, `AdminRequiredMixin`) lists policies
  grouped by transaction type with a best-effort (disclosed as such, not
  a full boolean-logic prover) "possibly unreachable rule" warning and a
  rule simulator calling the same `resolve_required_level()` the real
  approval path uses; every create/update/deactivate/reactivate writes an
  `AuditLog` entry with before/after field snapshots (§4's own
  instruction: the policy table must be at least as auditable as the
  transactions it governs). Approve/cancel buttons on Purchases/
  Adjustments/Sales now render shown-but-disabled with the real denial
  reason as a tooltip when `can_approve()` returns `False`, never hidden
  (§8b) — a new `.pill-btn:disabled` style (`dashboard.css`) since none
  existed before this phase. Verified live: the full 355-test suite
  passes (333 existing + 22 new — 19 pre-existing tests needed updating,
  each because they called `PurchaseService.approve()`/
  `AdjustmentService.approve()`/`SaleService.cancel_sale()` directly with
  a STAFF-role test user that the service layer never checked before;
  noted inline at each fix, not silently patched), the AUTO path was
  proven end-to-end (posts stock, writes exactly one movement, zero
  pending-record audit entries), and `seed_dev_data.py` runs clean and
  idempotent at the full 43-product scale with the policy engine live.

- **Phase 12.1: Approval Authority Matrix hardening — two corrections to
  Phase 12's own brief, a real gap left unbuilt (reported, not invented),
  a cumulative-value cap on the AUTO path, two fail-open defaults closed,
  and one more service-layer authorization gap fixed.**

  **Two corrections to Phase 12's premise, recorded so future prompts
  stop reasoning from them (this phase's own §2 instruction):**
  1. No purchase-order approval ceiling ever existed before Phase 12. The
  ৳50,000 supervisor/admin split is new, seeded by
  `frontend/migrations/0007_seed_approval_policies.py`, and originates
  from `ApprovalPolicy` rows this project wrote — not from a migrated
  legacy setting. There is no deprecated setting anywhere to remove in a
  later phase (Phase 12 never created one, since discovery found nothing
  to deprecate) — any future prompt referencing a "deprecated ceiling
  setting TODO" is describing something that doesn't exist.
  2. Celery and Celery Beat are not installed in this project (confirmed
  again: `requirements.txt` has no `celery` dependency). Every AI/policy
  recompute (`run_full_classification()`, `run_full_forecast()`,
  `recompute_abc_classes()`) is synchronous and manually triggered. Any
  doc or prompt referencing `@shared_task`, a Celery Beat schedule, or an
  async `backfill_actual_demand()` describes an architecture that was
  never built here.

  **The "record unlock" system §3 asked this phase to harden does not
  exist anywhere in this codebase — reported before writing code, not
  invented to give §3 something to attach to (this task's own §0
  instruction, and the user's explicit choice when asked how to
  proceed).** Confirmed exhaustively: `grep -rniE "unlock"` across every
  `.py` file and every doc (one hit, unrelated — "mutates current_stock
  unlocked," plain English for "unrestricted"); no model/field/migration
  named anything like `RecordUnlock`/`EditUnlock`/`is_locked`/
  `edit_token`/`consumed`; all 7 real migrations read in full; all 66
  §15 timeline entries read — no "record unlock" phase anywhere, and no
  post-approval edit path exists for `PurchaseOrder`/`InventoryAdjustment`/
  `SaleTransaction` at all (every status transition in `services.py` is
  forward-only). §3's re-resolution contract, its 3 required tests, and
  the "invalidate/keep/never-downgrade" table are **not implemented** —
  building a full terminal-record-unlock-and-edit subsystem to give
  hardening something to harden would have been a large, unrequested
  feature build disguised as a fix. If a future phase builds a real
  unlock/edit path, §3's own table (increase → invalidate & return to
  pending; unchanged → keep, log; decrease → keep, never auto-post) is
  the right contract to implement against — written down here so it
  isn't lost.

  **§4 — cumulative cap on the AUTO adjustment path, closing a real
  salami-slicing hole.** `ApprovalPolicy.cumulative_window_days`/
  `cumulative_value_cap` (both null → no cap, unchanged behavior).
  `InventoryAdjustment` gained `resolved_policy`/`was_auto_posted`
  (previously only existed inside `AuditLog.details` — a real gap this
  phase's own §0 discovery question anticipated correctly; you cannot
  compare against a value you have to parse back out of a JSON log
  field). `frontend.approvals.resolve_adjustment_with_cumulative_cap()`
  re-resolves excluding the AUTO policy (via a new
  `resolve_required_level(exclude_policy_ids=...)` parameter) when the
  trailing-window AUTO-posted total for that product would exceed the
  cap — the ruleset's own next-priority rule decides the fallback
  (lands on the Supervisor catch-all in the seeded set), never a
  hard-coded escalation target. `ADJUSTMENT_AUTO_DEFLECTED` audit entry
  records both figures ("the trail that makes the control provable," §4's
  own words). Seeded default: ৳2,000 / 30 days on the one AUTO policy
  (priority 40) — via a new migration
  (`0009_cumulative_cap_and_backfill.py`) updating the existing seeded
  row (a migration must update what an earlier migration already wrote,
  not just apply to future rows) plus a best-effort backfill of
  `was_auto_posted`/`resolved_policy` for adjustments AUTO-posted before
  this migration ran, sourced from their own `AuditLog` entries.
  Cumulative usage per product surfaced on the Approval Policy screen
  (`cumulative_usage_by_product()`, a `.confidence-bar`-based mini panel
  per AUTO+capped policy) — "demonstrable rather than invisible," §4's
  own instruction.

  **§5a — `variance_pct is None` (zero `current_stock`) now MATCHES an
  ADMIN-outcome variance condition instead of being skipped.** Previously
  `resolve_required_level()` treated `None` as "no signal, skip this
  policy" for every variance-conditioned rule regardless of outcome —
  fail-open at exactly the boundary the whole resolver is supposed to be
  fail-closed at. An adjustment against zero stock (the "50 units found
  in overflow storage"/phantom-stock case) is undefined variance, not
  absent variance, and undefined is exactly what should escalate. Fixed
  in `resolve_required_level()`'s own variance branch, with the
  direction now conditioned per-branch (`ADMIN`: `None` matches;
  `AUTO`/`SUPERVISOR`: `None` still doesn't, unchanged — it was already
  correctly excluded there). Covered by
  `FailClosedDefaultsTests.test_variance_none_at_zero_stock_matches_admin_variance_rule`.

  **§5b — an unclassified (never-computed) `abc_class` now resolves as
  `'A'` for policy-matching, not `'C'`.** Phase 12's own §7 instruction
  ("Products with no sales history default to 'C', not blank") was
  correct for ABC as a pure analytics label but wrong once it became an
  authority input (policy row 20 escalates class-A adjustments to
  Admin) — recompute is manual (no Celery, see the correction above), so
  a newly-stocked high-value product could sit at a default `'C'`
  indefinitely and policy row 20 would simply never fire for it.
  `InventoryClassification.abc_class`'s model default changed from
  `ABCClass.C` to blank (`''`) — blank now means "never computed,"
  distinguishable in the data and on screen from a genuinely-computed
  `'C'` (`ABCClass` itself gained no 4th member; blank is the state,
  same convention `ApprovalPolicy.abc_class` already used for "matches
  anything"). The STORED field stays blank; `frontend.approvals.
  _adjustment_context()` substitutes `'A'` only at resolution time.
  Staleness surfaced explicitly rather than left implicit: a bulk
  `.update()` call (`recompute_abc_classes()`) bypasses
  `TimeStampedModel`'s `auto_now updated_at` entirely (`.update()` never
  calls `save()`) — a real, previously-silent gap found while
  implementing this — so a new `SystemSettings.abc_last_recomputed_at`
  field is set explicitly, and both the Approval Policy screen and the
  Slow-Moving & Dead Stock page show "ABC last recomputed: &lt;date&gt;"
  with a warning past 30 days (`abc_staleness_info()`). Covered by
  `FailClosedDefaultsTests.test_never_computed_abc_resolves_as_a`/
  `test_computed_c_still_resolves_as_c_not_a` (the second proving the
  fallback doesn't also swallow a real computed `'C'`).

  **§6 — swept for BUG-56 siblings (other tables `seed_dev_data.py`'s
  `flush` silently wipes that only a data migration seeds). None found.**
  All 7 real migrations read in full: `0007_seed_approval_policies.py`
  is the *only* `RunPython` data migration in this project; every other
  migration is pure schema (`AddField`/`AlterField`/`CreateModel`). Not
  padded with manufactured findings — an honest "swept, found nothing
  else" is itself the deliverable here, per this phase's own explicit
  preference for that over inflating a count.

  **§7 — the service-layer authorization gap is now a standing rule, not
  a one-off:** **authorization checks belong at the service boundary;
  view-layer gates (`SupervisorRequiredMixin`/`AdminRequiredMixin`) are
  defence in depth, never the primary control.** Phase 12's 19 updated
  tests weren't test churn — they proved the service layer accepted
  unauthorised approvals from any caller that reached it another way
  (a management command, a shell, a future API path), with views as the
  *only* real gate. Swept for the same pattern elsewhere: `PurchaseService.
  reject()`/`cancel()`, `SaleService.reject_sale()`/`approve_sale()`,
  `AdjustmentService.reject()` all mutate state with zero service-layer
  check, relying entirely on their view's mixin. Fixed the clearest,
  highest-stakes one this phase — `SaleService.approve_sale()`, the one
  place a sale's stock actually moves — with a minimal role check (not
  routed through `ApprovalPolicy`; plain sale completion was never in
  Phase 12's `ApprovalTxType` scope). The other four are reported here,
  not fixed this phase — real, listed technical debt, not a silent gap.

  Verified live: full 363-test suite passes (355 + 8 new — 9 pre-existing
  tests needed updating, every one because §5b's corrected fallback now
  routes their never-classified test fixture to the seeded ADMIN policy;
  noted inline at each fix, an admin approver added locally to the two
  affected test classes rather than the shared `ServiceTestCase` base,
  since adding it there was tried first and broke an unrelated
  notify-every-supervisor-and-admin recipient-set assertion elsewhere —
  found and reverted, not left broken), `seed_dev_data.py` runs clean and
  idempotent at 43 products with the cumulative cap and both corrected
  defaults live, and `manage.py check` passes clean.

- **Phase 12.2: ABC removed as an approval-routing input; Approval
  Policies page simplified; notification setting trimmed from admin
  settings.** Found `frontend/audit.py` regressed to disk missing 6
  constants (`ADJUSTMENT_AUTO_POSTED`/`ADJUSTMENT_AUTO_DEFLECTED`/all 4
  `APPROVAL_POLICY_*`) before this phase started — a blocker, fixed
  first (§ own Task 1), restoring the suite to green before any other
  work began; recorded as its own entry in `docs/bugsfound.md`, not
  folded into this phase's feature work.

  **ABC out of approval routing.** `ApprovalPolicy.abc_class` (field +
  migration), the resolver's abc_class matching branch, and `can_approve()`'s
  ABC awareness are all removed; the ABC-matching seeded policy (former
  priority 20, "Class-A product, high variance" → Admin) deleted via data
  migration (`0010_remove_abc_class_policy_row.py`, separate from the
  schema migration — combining a data-migration `DELETE` with a
  same-table `RemoveField` in one file hit a real Postgres error,
  `OperationalError: cannot ALTER TABLE ... because it has pending
  trigger events`; splitting into two migrations each in their own
  transaction fixed it, found by actually running it, not assumed).
  `DEFAULT_APPROVAL_POLICIES` is 9 rows now (was 10); remaining coverage
  re-verified to still end in the catch-all Supervisor rule per
  transaction type, fail-closed-to-Admin-on-no-match unchanged. Phase
  12.1 §5b's "unclassified resolves as `'A'`" fallback is gone with it —
  that rule only ever existed because ABC was an authority input; its
  two tests (`test_never_computed_abc_resolves_as_a`/
  `test_computed_c_still_resolves_as_c_not_a`) are deleted, not
  rewritten, since the behaviour they asserted no longer applies.
  **`ABCClass`, `InventoryClassification.abc_class` (field, blank
  default, and Phase 12.1's "blank = never computed" semantics),
  `recompute_abc_classes()`, and `abc_staleness_info()` are all
  unchanged and still live** — ABC remains real for the Slow-Moving &
  Dead Stock page and inventory analytics generally, only its use as a
  policy-matching input is gone. `cumulative_usage_by_product()` (only
  ever called by the now-removed UI panel below) is deleted from
  `frontend/approvals.py` entirely; `resolve_adjustment_with_cumulative_cap()`
  and the cap enforcement itself are untouched.

  **Approval Policies page simplified back to "list + add."** Removed
  from the page: the rule simulator (form, JS `runSimulation()`, and
  `ApprovalPolicySimulateView` + its URL — the resolver function itself
  untouched, only the UI that called it for hypothetical inputs is
  gone), the unreachable/shadowed-rule warning computation, the ABC
  staleness banner (stays on the Slow-Moving & Dead Stock page), and the
  cumulative-usage-by-product panel. Kept: one table per transaction
  type (priority/name/condition/outcome/self-approval/status/actions),
  add/edit modals, activate/deactivate, admin-only gating.
  `cumulative_window_days`/`cumulative_value_cap` stay fully enforced —
  moved to the bottom of the add/edit form as optional fields, shown in
  the condition-text cell only when set, not removed from anywhere
  functional.

  **Notification setting trimmed from admin settings.** Removed the
  "Notifications" panel (two checkboxes) from `settings.html` and both
  fields from `SystemSettingsForm.Meta.fields`. The model fields
  themselves are untouched: `email_notifications_enabled` is still the
  live master gate `notifications.py`'s `_maybe_send_email()` reads —
  it's now frozen at whatever value is already in the DB (default
  `True`), changeable only through Django's raw `/admin/` (no custom
  `SystemSettingsAdmin.fields` override exists to remove there too, so
  the escape hatch is real, just unstyled). `low_stock_email_enabled`
  was already fully dead code before this phase — grepped, confirmed
  nothing reads it (`InventoryService._send_low_stock_notification()`
  calls `notify_supervisors()` unconditionally) — its removal from the
  form has zero behavioral effect.

  **Task 6 (flaky forecast test, optional/time-boxed): not reproducing.**
  `RunFullForecastTests.test_replenish_alert_when_weekly_demand_exceeds_stock`
  passed clean in a full single-process suite run (`--parallel=1`, 361/361).
  The described root cause (stale `ai_models/*.joblib` on disk leaking
  between tests) is already guarded against — every forecast-training
  test class (`ForecastingPipelineTests`, `RunFullForecastTests`,
  `DemandForecastingViewTests`) already calls `_clear_forecast_model_files()`
  in both `setUp()`/`tearDown()`, pre-existing code this phase didn't
  need to touch. No change made; noted here rather than left unverified.

  Verified live: 361/361 tests (363 from Phase 12.1, minus the 2 deleted
  ABC-fallback tests) — 5 failures surfaced immediately after the ABC
  removal (2 ERRORs from the deleted-field/deleted-policy tests, 3 FAILs
  from stale "10 policies" count assertions and one test still expecting
  `ApprovalOutcome.ADMIN` for a scenario that now resolves to
  `ApprovalOutcome.SUPERVISOR` without ABC escalation) — all fixed, none
  left red. Local per-test-class `self.admin` fixtures added in Phase
  12.1 to route around ABC-driven Admin escalation are removed along
  with it (`AdjustmentServiceTests`, `AdjustmentAuditNotificationTests`,
  `AdjustmentWorkflowViewTests`, `MovementHistoryViewTests` all reverted
  to their pre-12.1 `self.supervisor` fixtures — these scenarios now
  resolve via the seeded catch-all Supervisor policy, no ABC involved).
  `manage.py check` clean.

- **BUG-57 close-out: the last four service-boundary authorization gaps
  fixed — the standing rule now has zero known violations.** §7's own
  words: "a standing rule with four known violations sitting in the
  tree is worse than no rule." `PurchaseService.reject()`/`cancel()`,
  `SaleService.reject_sale()`, and `AdjustmentService.reject()` now gate
  with the identical plain supervisor-or-admin role check `SaleService.
  approve_sale()` already used (Phase 12.1 §7) — same
  `ApprovalAuthorityError`, checked immediately after the status guard
  and before any mutation, view-layer `SupervisorRequiredMixin` left in
  place on all four (both layers, not one). Deliberately NOT routed
  through the `ApprovalPolicy` engine (`resolve_for_transaction()`/
  `can_approve()`) the way `approve()`/`cancel_sale()` are — rejection
  was never in Phase 12's `ApprovalTxType` scope, same reasoning
  `approve_sale()` already gave for its own plain check; matching that
  precedent rather than inventing a second authorization pattern for
  reject/cancel.

  **Swept the full service layer for anything else matching "mutates
  state, creates/cancels a record, or moves stock, gated only by a view
  mixin."** Found nothing further: `InventoryService.increase_stock()`/
  `decrease_stock()` are internal primitives, only ever called from
  `receive_items()` (staff-appropriate — receiving is an operational
  task, not an approval decision, matching `PurchaseReceiveView`'s own
  `AnyStaffMixin`) or from already-gated `approve()`/`approve_sale()`/
  the AUTO-outcome `AdjustmentService.create()` path (policy-gated by
  design — AUTO's entire point is posting without a human approver).
  `submit_for_approval()` (both services), `receive_items()`, and
  `create_sale()` are intentionally open to any authenticated staff —
  no role distinction beyond "logged in" was ever intended for them, so
  their `AnyStaffMixin`-only gating is not a gap of this kind.

  **7 pre-existing tests were silently relying on the gap they were
  supposed to help prevent** — each called one of the four methods
  directly with the shared `ServiceTestCase.self.user` fixture (STAFF)
  and had always passed, because nothing on the service side ever
  checked. Not test churn: a test asserting a STAFF user *can* reject a
  PO/adjustment or cancel a PO was asserting the bug's own behavior.
  Rewritten to call with `self.supervisor` instead (`PurchaseServiceTests.
  test_reject_moves_pending_to_rejected_with_reason`, `PurchaseCancelTests.
  test_cancel_from_draft_leaves_stock_untouched`/
  `test_cancel_from_pending_leaves_stock_untouched`/
  `test_cancel_rejects_already_cancelled`'s first call,
  `PurchaseAuditNotificationTests.test_cancel_logs_but_does_not_notify`,
  `AdjustmentServiceTests.test_reject_adjustment_does_not_touch_stock`).
  The several `PurchaseCancelTests` cases already expecting `ValueError`
  from a wrong-status PO (`test_cancel_rejects_approved`/
  `_partially_received`/`_already_received`, and the second call in
  `_already_cancelled`) needed no change — the status guard still runs
  before the new authorization check, so those keep proving the status
  guard specifically, unaffected by caller role. One new negative test
  added per fixed method (`test_reject_raises_for_unauthorised_staff` ×3,
  `test_cancel_raises_for_unauthorised_staff` ×1), each calling the
  service directly with `self.user` (STAFF) and asserting
  `ApprovalAuthorityError`, mirroring
  `ApprovalAuthorityServiceLayerTests`' existing shape for `approve()`/
  `cancel_sale()`. `PurchaseRejectView`/`PurchaseCancelView`/
  `SaleRejectView`/`AdjustmentRejectView` each gained an `except
  ApprovalAuthorityError: ... status=403` clause matching every other
  approval-adjacent view in this file — previously absent since a
  `SupervisorRequiredMixin`-gated view could never actually reach the
  new check via the UI, but leaving it uncaught would have surfaced as
  an unhandled 500 rather than a clean 403 the one time it could (a
  role changing mid-session, or any future caller of these views that
  isn't the current UI).

  Verified live: 365/365 tests (361 from Phase 12.2 + 4 new direct-
  service denial tests, one per fixed method; 7 existing tests rewritten
  to act as `self.supervisor` instead of the STAFF fixture that used to
  pass unchecked, none deleted), `manage.py check` clean. No templates
  touched this phase, so no `{# #}` sweep was needed.

- **BUG-59: `ProgrammingError: column approval_policies.abc_class does
  not exist` diagnosed — the Phase 12.2 ABC removal itself was NOT
  incomplete.** Diagnosis before any fix, per this task's own
  instruction: `showmigrations frontend` showed 0011 applied,
  `makemigrations --check --dry-run` reported no drift, a direct
  `information_schema.columns` query confirmed `abc_class` genuinely
  absent from the live `approval_policies` table, and a fresh Django
  test-client process hitting the exact same view against the exact
  same dev DB returned 200 clean — model, migration, and schema were
  already in full agreement. The actual cause, found by `netstat -ano`:
  **six `manage.py runserver` processes had accumulated on
  `127.0.0.1:8000`** across this session's own earlier "start the dev
  server" steps (this session's own doing — each prior restart started
  a new process without confirming the old one had actually exited;
  Windows happily let all six coexist bound to the same port), spanning
  roughly 1:17 PM to 4:22 PM. Requests landed on whichever process's
  socket accepted the connection — including ones whose in-memory
  `ApprovalPolicy` view/model bytecode predated the `abc_class`
  removal. A live reproduction against the pool confirmed the exact
  error; killing all six and leaving exactly one fresh process fixed it
  immediately (5/5 clean page loads plus one full add-policy round trip
  afterward). **A general operational lesson, not specific to ABC**:
  this project has no dev/production settings split and no process
  manager — every future "restart the server" step should verify the
  old listener is actually gone (`netstat`/`lsof` on the port) before
  starting a new one, not just start a new one and assume the old one
  died. The `frontend/views.py:2482` "prose in the traceback" symptom
  that looked alarming on its own was a side effect of the same root
  cause, not a second bug: the stale process's compiled bytecode had
  drifted from the current file's line numbering, so Django's debug
  page (which re-reads the *current* file from disk to render source
  context) displayed an unrelated but entirely valid line of
  `_policy_snapshot()`'s real docstring — confirmed by reading the file
  directly; no prompt/spec text was ever actually pasted into source.

  Also fixed while here: `LOGIN_REDIRECT_URL`/`LOGOUT_REDIRECT_URL`
  were never set in `config/settings.py`, silently defaulting to
  Django's own `/accounts/profile/`/`None`. Confirmed **latent, not
  broken** — `frontend.views.login()`/`logout_view()` are plain
  function views that `redirect()` explicitly by URL name
  (`frontend:dashboard`/`frontend:login`) and never call
  `get_success_url()` or read either setting. Set anyway, matching
  `LOGIN_URL`'s own established style/comment convention just above
  them, as defence in depth for anything that ever does fall back to
  Django's own default (the admin's own `/admin/login/` with no `next`,
  for one).

  Verified live: `manage.py migrate` reports no pending migrations,
  `manage.py check` clean, full suite 365/365 unchanged, reseed via
  `seed_dev_data.py` followed by another live page load both clean.

- **Phase 13: professional PDF documents + live company settings.** New
  `frontend/pdf.py` — the shared header/footer/style/currency/date
  infrastructure every PDF in the system now renders through
  (`render_document()` for the 3 transactional documents,
  `render_tabular_report()` for the 9 REPORT_BUILDERS exports and
  Movement History's export), replacing what used to be five
  independent, copy-pasted ReportLab setups. Discovery before any code:
  only 2 per-record PDFs existed (Purchase Order, Sale Transaction) —
  no per-Adjustment or per-Movement document, only the flat report-table
  export covered either. `SystemSettings` company fields already
  persisted for real (form → DB → survives restart, audited via
  `SETTINGS_UPDATED`) — the actual gap was that **zero PDF code
  anywhere read them**; every generator hardcoded its own title, no
  logo, no address, no branding at all.

  **Two disclosed ReportLab-only constraints, found empirically, not
  assumed** (full detail in `frontend/pdf.py`'s own module docstring):
  (1) the ৳ glyph has no coverage in any of ReportLab's built-in fonts
  (WinAnsi/Latin-1 only) and this repo ships no font file to register
  instead — PDFs use `Tk` as the currency prefix, the web UI keeps ৳
  everywhere unchanged; (2) `company_logo` accepts SVG, but ReportLab
  can't rasterize it without a new dependency (svglib et al.), which
  the phase's own standing rules forbid — an SVG logo renders the PDF
  header the same graceful text-only way a missing logo does, and
  still displays correctly on the web (plain `<img src>`).

  **Company settings, made genuinely load-bearing.** `company_logo`
  switched from `ImageField` to `FileField` — Pillow (which `ImageField`
  uses to validate) cannot open SVG at all, so the field type itself
  was the blocker, not just the validator; a new `validate_company_logo`
  (Pillow-verified for PNG/JPG, sniffed for SVG) replaces the checking
  `ImageField` used to do for free. Added `company_tax_number`/
  `company_website` (both blank-optional, no backfill needed). New
  `SystemSettings.get_company_profile()` classmethod, alongside the
  existing `get_settings()` — the one accessor every PDF reads through,
  always returning plain strings (never `None`) so no caller needs to
  special-case a blank field. Settings page gets a live client-side
  logo preview on file selection (`FileReader`, no round trip) — the
  old preview only ever showed the *saved* logo, never a newly-picked
  one before upload.

  **Every document type, one shared structure**: header band (logo or
  company-name-in-type fallback, address/phone/email/tax number,
  closing rule) and footer (page N of M via a `NumberedCanvas` that
  buffers pages since the total isn't known until the whole document is
  built once, generated-timestamp, computer-generated note, company
  name) drawn via `BaseDocTemplate`'s `onPage` callback so both repeat
  on every page regardless of length — verified against a deliberately
  long (120-row) report: 7 pages, table header genuinely repeats on
  each one, "Page N of 7" numbered correctly throughout. Party block
  (Supplier for POs, Bill To for invoices, none for adjustments — this
  schema has no location/warehouse concept anywhere, confirmed via
  `InventoryRecord` having no location breakdown, so a fabricated
  "Location: Main Warehouse" line was left out rather than invented).
  Totals block reconstructed from `frontend.pricing.
  calculate_totals_breakdown()` (new) — Subtotal/Discount/Tax/Grand
  Total derived from `calculate_line_total()`'s own formula, since
  `PurchaseOrderItem`/`SaleItem` only ever persist the final
  `line_total`, never the breakdown; reconciles exactly by
  construction, proven with a test. Signature block shows the real
  approver by name — `PurchaseOrder`/`SaleTransaction` don't store
  which policy/level resolved their approval (only
  `InventoryAdjustment.resolved_policy` does), so the approver's own
  role (`get_role_display()`) stands in as the level shown, which is
  exactly the signal that matters: whoever is shown already passed
  `can_approve()` for whatever level the transaction required — this is
  Phase 12/12.1's approval-authority work becoming visible on paper, as
  asked. Cancelled/rejected documents get a diagonal, pale-red status
  watermark drawn directly on the canvas.

  New `generate_adjustment_pdf()` (no prior document existed) + new
  `AdjustmentPDFView`/`adjustments/<pk>/pdf/` route — replaced
  Adjustments' dead "View adjustment" button (BUG-60: no handler ever
  existed) with a real download, same pattern Purchases/Sales already
  use.

  **Reports page Task 4**: the Sales Report panel's raw per-transaction
  table (redundant with Movement History) is gone, replaced by a
  revenue-by-day Chart.js bar chart (reusing the exact setup/colors
  dashboard.js's own sales chart already established — no new charting
  convention) plus a status-breakdown table (count + total per
  `SaleStatus`). The Sales Report's own PDF export mirrors this same
  aggregate shape (`generate_sales_summary_pdf()`, new); its CSV export
  is untouched and still the detailed per-transaction dump —
  `build_sales_report()` itself wasn't removed, just no longer used for
  the on-page preview or the PDF.

  **Consistency pass (Task 5)**: every PDF generator in the codebase —
  all 9 `REPORT_BUILDERS`, Movement History's export, the Sales
  summary, and all 3 transactional documents — now renders through
  `frontend/pdf.py`. None were left out.

  Verified live: full suite 385/385 (365 + 20 new — company branding
  reflected in real PDF output, blank-optional-fields rendering,
  logo upload accepting PNG/JPG/SVG and rejecting bad extension/size/
  spoofed-SVG, totals reconciliation, multi-page repeat/pagination,
  cancelled/rejected watermark presence, every new/changed PDF endpoint
  returning valid `application/pdf` — a text-extraction helper
  (`_extract_pdf_text()`, undoing ReportLab's default
  `[ASCII85Decode, FlateDecode]` stream encoding, confirmed empirically)
  makes the actual rendered text assertable rather than only checking
  status codes/content-type), `manage.py check` clean, live Playwright
  round trip (login → download real PDFs through the actual UI buttons
  for a PO/an adjustment/the Sales summary, all valid) after a fresh
  reseed. Nothing left stubbed: every company field is real, every PDF
  reads through `get_company_profile()`, every generator shares the one
  infrastructure module.

- **Phase 14: three-column footer redesign — Brand / Contact Us /
  Account.** Discovery: `includes/footer.html` is included only from
  `landing/index.html` (the public landing page); it does not appear in
  `dashboard_base.html` or any auth-flow template, but `landing()` has
  no redirect for authenticated users, so an already-logged-in visitor
  genuinely can view it — a real, not hypothetical, case for the
  Account column. Three new icons added to the shared sprite
  (`icon-phone`, `icon-map-pin`, `icon-linkedin`, same hand-built stroke
  convention as every existing one — no icon library).

  **First pass wired the Brand/Contact Us columns to `SystemSettings.
  get_company_profile()`** (Phase 13's own accessor, "same source the
  PDFs read from," per this task's own instruction) — added
  `company_linkedin_url` to the model for it. **Reversed on live user
  correction mid-task**: the footer is Stockwell's own public-facing
  brand (the product/company operating this landing page), not the
  per-tenant business identity an admin configures in Settings for
  their own invoices/POs — those are two different identities, and
  conflating them was wrong. `company_linkedin_url` was removed again
  (model field, migration, form, settings.html field, JS map) — reverted
  via a fresh forward migration attempt first, found `makemigrations`
  reported "no changes detected" once the file was deleted (Django's
  migration graph only tracks files present on disk, so a deleted
  migration file simply drops out of the state comparison); the already-
  applied column and its `django_migrations` row were real on the dev
  DB regardless, cleaned up directly (`ALTER TABLE ... DROP COLUMN`,
  matching delete from `django_migrations`) rather than left orphaned.
  `landing()`'s context addition was reverted too — nothing reads
  `get_company_profile()` from this page anymore.

  **Final shape**: Brand column is static Stockwell markup (logo, name,
  intro line) exactly as it was before this phase, unchanged in
  substance. Contact Us is a 4-row icon list (email/phone/address/
  LinkedIn) with static placeholder Stockwell contact details — real
  email (`mst.sanzida02@gmail.com`, already the established real
  contact), phone/address/LinkedIn are plausible placeholders, not
  live data, not admin-editable (a deliberate, disclosed choice this
  time, not a gap). Account column is a single "Log in" link — no
  authenticated-state branching in the final version (the user
  explicitly simplified past that concern once the footer's real
  identity was clarified as public/product-level, not per-session).
  Icons are `18px`, vertically centred against their text via flex
  `align-items:center`, coloured `--c-indigo`, one CSS rule
  (`.footer-contact-list .icon`) rather than per-instance sizing.
  `.footer-grid` narrowed from 4 columns to 3 (`1.6fr 1fr 1fr`),
  collapsing to a single column under 760px. Old, now-dead
  `.footer-contact-card`/`-icon`/`-label`/`-email` CSS (the previous
  single-CTA-card treatment) removed rather than left orphaned.

  Verified live (fresh server process each time, learning BUG-59's own
  lesson — killed stale listeners before every check): desktop, tablet,
  and mobile screenshots of the 3-column layout, "Log in" link resolves
  to a real page, LinkedIn opens `target="_blank" rel="noopener
  noreferrer"`. `manage.py check` clean; full suite unaffected (no new
  tests were needed for this template/CSS-only final state — the
  removed `company_linkedin_url` field never shipped in a form other
  code depended on).

- **Phase 15: demand forecasting pipeline bug audit.** `docs/
  DEMAND_FORECASTING.md`'s 9-item bug list (derived from the doc's own
  stale `apps.ai.*`-path reading) checked against the actual running
  `frontend/forecasting.py`, item by item, verifying against real dev
  data rather than trusting either the doc or a source read alone —
  written up as a table before any code changed, per this phase's own
  explicit instruction. Of 9: 4 already fixed (rename/dtype order in
  `get_sales_dataframe()`, the tz-aware/naive `stockout_flag` merge —
  both empirically re-confirmed against real stockout products, not
  just re-read; the MAE-mislabeling shape; `DemandForecast.updated_at`
  existing), 2 not applicable to this codebase's architecture (the
  Celery-task `log_action` import gap — no Celery tasks exist here at
  all; the month-end/month-start labeling difference — empirically
  produces correct, non-overlapping calendar tiling regardless), 1
  reviewed and confirmed deliberate/already-disclosed (duplicate
  `DemandForecast` rows across re-runs — REQ 9.9 needs forecast
  history kept for later accuracy comparison), and 2 real, confirmed,
  fixed bugs.

  **Three follow-up checks requested before the fix, all completed
  first:** (1) whether anything aggregates across `DemandForecast` rows
  in a way the "duplicates are fine, they're vintage-distinguishable"
  rationale doesn't actually cover — found one: `ForecastSummaryAPIView`
  aggregates unconditionally (`count()`/`avg(confidence_score)`) with
  no latest-batch dedup, unlike the HTML dashboard's own `_latest_batch()`
  — logged as BUG-64, not fixed (out of this pass's scope), and the
  duplicate-rows rationale itself moved out of `views.py`'s docstring
  into `docs/DEMAND_FORECASTING.md` where it's actually discoverable.
  (2) grepped every caller of `run_full_forecast()` — exactly one,
  `DemandForecastingView.post()`, which does correctly audit-log; no
  management command, cron, or scheduled-job path exists in this
  project at all, so REQ 9.14 has no hole. (3) `rolling_std_4` staying
  frozen while `rolling_avg_4` gets recomputed in the same loop was
  genuinely ambiguous (Design Note #5 only ever promised no
  *scrambling*, never addressed whether the value itself should track
  the synthetic future) — resolved explicitly: stays frozen,
  deliberately, reasoning now in both the code and the doc (a
  recomputed volatility signal built from increasingly model-smoothed
  synthetic values would drift toward artificially low numbers the
  further out the horizon runs; a frozen one anchors to real observed
  volatility instead).

  **Two real bugs fixed, both present in the doc's own reference code
  too, both empirically verified before AND after the fix, not just
  read:** `predict_demand()`'s multi-step loop never advanced
  `period_num` — instrumented the actual loop against a real trained
  model and confirmed it fed the identical value on all 4 steps of a
  4-step forecast before fixing, then added a test that spies on the
  model's own `.predict()` calls and asserts strict step-by-step
  increase (BUG-61). `run_full_forecast()` passed the weeks-denominated
  `forecast_period_weeks` setting straight through as `periods_ahead`
  to the monthly run too — fixed as a conversion (`max(1, round(weeks
  / 4))`) rather than a new settings field, per explicit instruction not
  to add `forecast_period_months` (BUG-62). Neither fix touches the
  model class, hyperparameters, `FEATURE_COLUMNS`, the chronological
  split, the residual-based confidence, task names, or any API response
  shape — confirmed no existing test pins an exact forecast value (all
  assert shape/bounds/counts), so none needed re-pinning; two new tests
  added instead.

  One design limitation logged without fixing, per explicit scope: the
  final resample bin can be a partial period (training mid-week/month
  captures an incomplete bin), biasing the very first forecast step's
  `lag_1` downward — a real fix changes what `build_features()` returns,
  which this pass's own scope excluded (BUG-63).

  Verified: full suite 387/387 (385 baseline + 2 new), `manage.py check`
  clean. Live dev server, not just diffs: killed stale listeners first
  (BUG-59's own lesson), triggered a real "Run forecast now" against a
  freshly reseeded DB (43 active products, `forecast_period_weeks=4`) —
  191 rows created, `AI_FORECASTS_GENERATED` audit entry landed with the
  correct user/details, `AI_MODEL_RETRAINED`'s `mae` correctly keyed per
  period (`{'W': 0.84, 'M': 5.22}`), zero duplicate `(product, period,
  period_start)` groups from that single run, and a spot-checked product
  showed exactly 4 weekly rows / 1 monthly row — BUG-62's conversion
  confirmed live, not just in a test. A second click confirmed the
  *intentional* cross-run accumulation behaves exactly as documented:
  382 total rows, 2 audit entries, exactly 191 duplicate groups (one
  real duplicate per row from run 1, no unexpected multiplication).
  One unrelated, pre-existing flake surfaced during this pass's own
  full-suite runs (not caused by anything here, and out of this task's
  scope): `SaleTransaction._generate_invoice_number()` is a random
  4-digit suffix over ~9000 values, `INV-<date>-NNNN` — a test creating
  many `SaleTransaction` rows in one method carries a real collision
  probability; confirmed by a clean re-run of the exact same code
  immediately after. Worth a real fix (a sequential or wider-space
  suffix) in some future pass; not touched here.

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
29. **Phase 7.5: proactive `{# #}` comment audit** — swept all 25
    templates for the BUG-03/BUG-36 multi-line-comment pattern ahead of
    Phase 8. 40 `{# #}` instances across 14 files, every one closing on
    its own line; zero multi-line, no fixes needed.
30. **Backend Phase 8: Audit Log, Notifications, Users & Roles, Settings,
    Reports** — the last 5 mock pages from Phase 3.6 are all real now, in
    that order (read-only/no-new-service first). `AuditLogListView` reads
    the real, still-immutable `AuditLog` table. Notifications gets a real
    per-user list, mark-read/mark-all/unread-count endpoints, and the
    topbar bell badge actually polls every 30s now instead of always
    showing a dot. Users & Roles required one disclosed field-list
    deviation from the mock — a required password field, since a `User`
    saved without one can never log in (`UserForm`'s docstring) — plus
    real Deactivate/Reactivate with a self-deactivation guard. Settings
    wires the `SystemSettings` singleton with a blank-falls-back-to-
    current-value rule so a partial save can't blank out real config.
    Reports needed a new PDF library — chose ReportLab over
    `10_REPORTS.md`'s own WeasyPrint example (both documented as
    acceptable in `TECH_STACK.md`; ReportLab has zero native deps, a real
    concern on this Windows dev box) — and a new `frontend/reports.py`
    holding all 9 report builders + the PDF/CSV generators, same pattern
    as `frontend/audit.py`/`frontend/notifications.py`. All 9 report types
    export real PDF and CSV; Sales/Low Stock also kept their full HTML
    preview from the mock, the other 7 (which never had a preview panel)
    export straight from their card. `SupervisorRequiredMixin` gates
    Reports (re-confirmed the Admin-or-Supervisor hierarchy holds there
    too, not just Purchases); `AdminRequiredMixin` gets its first real use
    on the other three. No mock/schema mismatch found in Audit Log/
    Notifications/Settings/Reports — Users & Roles' password gap was the
    only deviation, and it was disclosed, not silent. 25 new tests (RBAC
    gate + one success path per module, following Phase 6's live-
    verification-primary precedent rather than Phase 7's full transition-
    matrix mandate, since this task didn't repeat that instruction) — 125
    tests passing (was 100). Inventory is now the only view in the app
    with no RBAC mixin, by design (read-only, no write action to gate).
31. **Phase 8.5: role-aware UI + message feedback** — Phase 8's own RBAC
    verification found the server-side block was correct but invisible:
    `dashboard_base.html` never rendered `{% if messages %}` anywhere (only
    `accounts/login.html`/`accounts/profile.html` did), so
    `RoleRequiredMixin`'s `messages.error(request, 'Access denied.')`
    (`frontend/mixins.py`) was silently dropped on every one of the 21
    guarded views across 11 modules, every time it fired — one source line,
    newly surfaced everywhere at once by adding the exact same `{% if
    messages %}`/`.form-alert` block `login.html` already used, into
    `dashboard_base.html`'s `<main>` instead of inventing new markup.
    Action buttons also rendered for every role regardless of which mixin
    actually guarded the endpoint behind them — added `{% if
    request.user.role == 'admin' or request.user.role == 'supervisor' %}`
    around Purchases' approve/reject/cancel, Adjustments' approve/reject,
    and Sales' cancel (each matched 1:1 to that button's own
    `SupervisorRequiredMixin`-guarded view, not a separately-invented
    split), plus the same treatment on the sidebar's Users & Roles/Audit
    Log/Settings links (`AdminRequiredMixin`) and — beyond this task's
    literal 3-link list, but the identical class of gap — the Reports link
    (`SupervisorRequiredMixin`), disclosed as a deliberate scope extension
    for consistency rather than left half-fixed. Root-caused a second,
    subtler bug along the way: `fetch()` follows a 302 redirect
    transparently, so a blocked staff user's Approve click got back a 200
    (the dashboard page) and the client-side code read that as success,
    silently reloading with no explanation — even *after* hiding the
    button, a direct POST would still hit this. Fixed by extracting the
    5 near-identical `getCsrfToken()`/`postAction()` copies already
    duplicated across `purchase-form.js`/`sale-form.js`/
    `adjustment-form.js`/`user-form.js`/`notifications.js` into one new
    `frontend/static/js/row-actions.js` (per this project's own standing
    rule — §18 — to consolidate duplicate logic rather than add a 6th
    copy), whose `postAction()` checks `Response.redirected` before
    `response.ok` and reports `{blocked: true}` instead of a false
    success; `reportResult()` shows a real "You don't have permission to
    do that." Verified live (Playwright, all three roles): staff sees no
    approve/reject/cancel anywhere and none of the 4 admin/supervisor
    sidebar links; supervisor sees the actions and Reports but not
    Users/Audit/Settings; admin sees everything. Bypassing the
    now-hidden button entirely via a direct `RowActions.postAction()` call
    still correctly reported `blocked: true` and left the PO's `status`/
    `approved_by` unchanged in the database — hiding the button changed
    nothing about server-side enforcement, only whether the (still-
    necessary) block is ever visible. 125/125 tests still passing (none
    of this touched Python).
32. **Phase 8.6: 4 live-usage bug fixes + cross-role sweep** (BUG-37
    through BUG-40, `docs/bugsfound.md`). **Bug 1 (filters):** root-caused
    to `users.html` never loading `table-filter.js`, even though
    `user-form.js` unconditionally calls `TableFilter.init()` behind an
    `if (window.TableFilter...)` guard that silently no-op'd — fixed with
    one `<script>` tag; every other real `table-filter.js` consumer
    (Forecasting, Slow-Moving, Audit Log, Reports) was independently
    re-verified working, live, against real data. Products/Categories/
    Suppliers/Purchases/Sales/Inventory/Adjustments/Notifications never
    wired it at all — pre-existing, disclosed decorative debt (§10/§12),
    left alone. **Bug 2 (timezone):** `TIME_ZONE` was `'UTC'`; changed to
    `'Asia/Dhaka'` — `USE_TZ` stays `True`. Explicitly confirmed this was
    display-only, not a storage bug: every timestamp in this project is
    written via `auto_now_add`/`auto_now`/`timezone.now()`, all correctly
    UTC-aware; verified against a real `AuditLog` row that
    `timezone.localtime()` now correctly shifts it +6h. Found and
    disclosed (not fixed — out of this task's scope) a related, deeper
    gap: `PurchaseOrder`/`SaleTransaction`'s PO-number/invoice-number
    generation and their `order_date`/`transaction_date` fields
    (`DateField(auto_now_add=True)`) don't go through `TIME_ZONE` at all —
    Django's own `DateField.auto_now_add` reads the OS clock directly, a
    well-known Django gotcha, distinct from `DateTimeField`'s behavior.
    **Bug 3 (greeting time):** `dashboard.html`'s "Good morning" was
    literal text; `frontend/views.py`'s `dashboard()` now computes it
    server-side from `timezone.localtime().hour`, deliberately the same
    clock Bug 2 just fixed so the two can never disagree. **Bug 4
    ("Amara"):** root-caused to `dashboard.html` reading
    `request.user.first_name`, a field `frontend.User` doesn't have (only
    `full_name`) — Django resolves unknown attributes to `''`, so
    `|default:"Amara"` fired for every real user, not just anonymous ones.
    Fixed by switching to the already-existing `get_short_name()`.  Swept
    `topbar_actions.html`/`sidebar.html` for the same placeholder per this
    task's instruction — both use `get_full_name()` and already resolve
    correctly for real users; their `"Amara Tenzin"` fallback only fires
    for a genuinely anonymous visitor, already documented/intentional
    (§4) — left alone. Also disclosed, not fixed: `dashboard()` itself has
    no RBAC/login guard at all, unlike every other real view — out of
    this task's explicit no-RBAC-changes scope. **Cross-role sweep**
    (Playwright, `verify_admin`/`verify_super`/`verify_user`, live dev
    server + real Postgres data): sidebar gating (Users/Audit/Settings
    admin-only, Reports supervisor+) confirmed by real navigation, not
    just CSS; Purchases/Adjustments/Sales action buttons confirmed correct
    per role *and* end-to-end functional — a real supervisor Approve
    click flipped a PO pending→approved in the DB, a real Cancel click on
    a live sale restored stock and set it cancelled, Users & Roles'
    Deactivate/Reactivate round-tripped correctly on a throwaway account
    (created and cleaned up during the sweep); a supervisor approving an
    adjustment with genuinely insufficient stock correctly stayed
    `pending` with a real `alert()` error rather than corrupting data; a
    direct staff `fetch()` POST to a supervisor-gated endpoint came back
    blocked (redirected), confirming server-side enforcement holds
    independent of button visibility, consistent with Phase 8.5's own
    verification. No visible-but-dead or wired-but-misgated button found.
    2 new test classes (`TimeZoneConfigTests`, `DashboardGreetingTests`,
    `frontend/tests.py`) — 131/131 tests passing (was 125).
33. **Phase 8.7: wire table filtering on the main data tables** (BUG-37
    case (c), `docs/bugsfound.md`). Products/Suppliers/Purchases/Sales/
    Adjustments' visible search/select/segmented controls were decorative
    debt since Phase 5-7 — same root shape as Phase 8.6's Users & Roles
    fix, but wider: each page was missing the `table-filter.js` `<script>`
    tag *and* `id`s on its controls *and* `data-search`/`data-<column>`
    hooks on its `<tr>`s (the mock-era rows never had filter hooks at
    all). Status/type `<select>`s also had no `value` attribute, so the
    browser defaulted each option's value to its own display text
    ("Pending approval") rather than the model's real lowercase choice
    value (`pending`) — fixed by adding explicit `value="..."` matching
    each field's real `TextChoices`. `table-filter.js` itself untouched —
    reused exactly as-is on all 5, same module as everywhere else it
    already worked. Two pages checked out as nothing-to-wire, not
    overlooked: **Categories** has no filter controls in its template at
    all; **Inventory**'s controls are real but the page underneath them
    isn't — `inventory()` is still a one-line `render()` with zero real
    rows (see the §2/§11/§16 corrections this phase made — that entry was
    previously, incorrectly, marked ✅). Verified live (Playwright,
    `verify_user`/`verify_super`, real Postgres data): bogus search hides
    all rows on every page, each select correctly narrows to its matching
    subset, clearing restores the full set — identical for both roles,
    since this app's list pages don't vary row content by role. No
    console errors across all 7 pages checked. 131/131 tests still passing
    (frontend-only change).
34. **Phase 8.8: documentation-integrity audit.** Verification only, no
    code changes. Read every view in `frontend/views.py` (981 lines) plus
    `frontend/urls.py` and classified each against every ✅ claim in this
    file: (a) real — genuine queryset/form/service call, (b) mock —
    one-line `render()` over hardcoded template data, (c) partial — some
    real, some hardcoded. Confirmed real: Products/Categories/Suppliers/
    Purchases/Sales/Adjustments (all Phase 5-7), Reports/Notifications/
    Users & Roles/Audit Log/Settings (all Phase 8), login/logout/profile
    (Phase 4), the Dashboard shell's sidebar/topbar/notification-dropdown/
    user-menu, and all 9 `frontend/reports.py` builders — genuine
    querysets throughout, no hardcoded rows found anywhere, including the
    7 report types that only ever export (no on-page preview) — verified
    those aren't stubs either. One honest, undisclosed-until-now gap:
    2 of the 9 (AI Forecast/Classification) are real queries against
    `DemandForecast`/`InventoryClassification`, tables nothing writes to
    yet since AI is still Phase 10/11 — correct code, no data yet, not a
    bug. Confirmed mock and correctly disclosed as such already: Demand
    Forecasting/Slow-Moving pages ("All static/mocked" — no correction
    needed). **Found one more mislabeled page, beyond Phase 8.7's
    Inventory finding: the Dashboard.** `dashboard()` passes only
    `{"greeting": ...}` — no querysets, no aggregates. Every KPI card
    (`total_products` etc. are never in context — the `|default:"1,284"`
    template fallback fires unconditionally), both Chart.js charts
    (`dashboard.js` has the datasets as literal hardcoded arrays), and all
    4 widgets (Stock Alerts, Pending Approvals — including Approve/Reject
    buttons with no click handler or endpoint at all, Recent Activity,
    AI Insights) are 100% fabricated. This file's previous entry ("KPI
    cards, Chart.js sales/inventory charts, static preview panels")
    undersold this — a reader could reasonably assume only the "preview
    panels" were static. Corrected in §2/§11/§16. Swept every template for
    the `|default:"..."` fallback pattern (Dashboard's specific tell) to
    check for other instances of the same bug shape — every other hit was
    a legitimate per-row null fallback for a genuinely optional field
    (audit log's `affected_id`, suppliers' `contact_person`, etc.) or the
    already-documented anonymous-visitor identity fallback — none were
    another whole-page fabrication. Root cause noted for future phases: a
    mock template renders cleanly regardless of whether its data is real,
    so *how a page looks* is not evidence of *what built it* — only
    reading the view's actual context is. This is the third time an
    inaccurate ✅ has shipped in this file (also Phase 3.9, Phase 4.5); no
    process fix applied here beyond writing this down, since one wasn't
    asked for — flagged as worth deciding before Phase 9. No tests
    added/changed (no code changed); 131/131 still passing.
35. **Phase 8.9: build the real Inventory list view**, closing BUG-37's
    Inventory portion for good. `InventoryListView` (`AnyStaffMixin`)
    replaces the one-line `render()` with a genuine `InventoryRecord`
    queryset — product, current stock, reorder level, total value, and
    `status` read straight off the model (InventoryService already keeps
    it correct on every real mutation; deliberately not recomputed in the
    view, per 07_INVENTORY.md's own design and this project's standing
    "InventoryService is the only code path that touches stock" rule).
    `07_INVENTORY.md`'s own reference view uses `@staff_required`, which
    in this project's RBAC (`frontend/decorators.py`) means all 3 roles —
    matched here with `AnyStaffMixin` rather than leaving the view
    unguarded, closing a second, smaller gap (the old mock view had no
    login check at all). `inventory.html`'s rows, KPI/stat-strip numbers,
    and "last movement" column (via `product.movements.order_by(
    '-created_at').first()`, `{{ ...|timesince }} ago`) are all real; the
    status wording changed from the mock's "In stock" to the model's own
    `get_status_display()` ("Available") — a disclosed, honest naming
    difference, not a mismatch masked over. Filter controls wired to
    `table-filter.js` the same way as Phase 8.7's 5 pages, closing the
    gap that phase explicitly deferred pending this one. Confirmed
    strictly read-only, per the task's own explicit check: no `<form>`
    anywhere in the template, no `InventoryRecord` mutation anywhere in
    the view, and a live direct `POST /inventory/` returns `405`.
    Verified live (Playwright, all 3 roles, real Postgres data): rendered
    rows matched the DB exactly (SKU, stock, status badges "Low Stock" ×2/
    "Available" ×1), search and status filters narrowed correctly, no
    add/edit controls anywhere, no console errors. 5 new tests
    (`InventoryListViewTests` — real-data rendering, real aggregate
    counts, any-role access, 405 on POST) — 136/136 passing (was 131).
    Every module in the app now has a real view; only the Dashboard
    remains mock (Phase 8.8 finding, still open — see §16).
36. **Phase 8.95: define the Dashboard's real metrics — decision, no
    build.** No spec ever existed for the Dashboard (`INDEX.md` linked to
    a nonexistent `09_DASHBOARD.md`, BUG-17) — every KPI/chart/widget the
    old mock showed was invented UI wishlist, not a documented contract.
    Reconciled three sources against each other (the mock, treated as a
    wishlist not a spec; `API_CONTRACTS.md`'s `Dashboard`/`Inventory`
    endpoints — the only place any field names were actually documented;
    `SCHEMA.md`) into a full table: every element → precise definition →
    exact query → real-data-backable now (yes/no). Produced 8 disclosed
    decisions needing sign-off (all 4 KPI trend badges' format, chart
    windows + the Purchases series' status filter, a single preview-row-
    count constant, Pending Approvals' action-button question, Recent
    Activity's `13_AUDIT.md`-adjacent visibility question, 3 fields kept
    beyond the documented stats payload, "Active suppliers" over raw
    total, page-wide role visibility) and recommended dropping the AI
    Insights widget outright (not an empty state) since its source tables
    stay empty until Phase 10/11. Written as `docs/09_DASHBOARD.md`,
    matching the other module docs' style — closes the doc gap Phase 8.8
    identified. No code touched, as scoped.
37. **Phase 8.95.1: finalized the 8 decisions.** All approved as
    recommended except Decision 5 (Recent Activity), where the safer
    fallback was chosen over the stretch: **admin/supervisor-only**,
    leaving `13_AUDIT.md`'s "Admin only" framing for audit-derived data
    completely uncontested rather than carving out a disclosed exception
    to it. Decision 3 also picked up a refinement — a single named
    `DASHBOARD_PREVIEW_ROWS` constant instead of three separate hardcoded
    `5`s. `09_DASHBOARD.md` marked `Status: FINAL`. Still no code touched.
38. **Phase 8.96: built the real Dashboard**, closing BUG-41 and this
    file's last mock-but-marked-done page. `dashboard()` computes every
    KPI/stat/chart/widget from the exact queries `09_DASHBOARD.md`
    specifies — `Sum`/`Count`/`annotate`/`TruncWeek`/`TruncMonth`,
    DB-aggregated, never a whole table pulled into Python. `DASHBOARD_
    PREVIEW_ROWS = 5` defined once, reused for Stock Alerts/Pending
    Approvals/Recent Activity. Both Chart.js charts read real server data
    via `{{ chart_data|json_script:"dashboardChartData" }}` — `dashboard.js`'s
    hardcoded arrays are gone. Pending Approvals renders read-only, no
    Approve/Reject buttons anywhere on the page (Decision 4). Recent
    Activity gates on `request.user.role in (admin, supervisor)` —
    confirmed genuinely absent from rendered HTML for staff (test +
    live check), not CSS-hidden. AI Insights section deleted outright, not
    an empty state. Every `|default:"..."` fabrication is gone except the
    one already-approved, non-fabrication greeting-name fallback (BUG-40).
    Verified live (Playwright, real Postgres, all 3 roles): every KPI/stat
    matched a direct manual DB query exactly (products/categories/active
    suppliers/users = 3/3/3/4, inventory value = $858.00, stock units =
    111, low/out-of-stock = 2/0); Stock Alerts and Pending Approvals
    showed real rows matching the DB; switching the Daily/Weekly/Monthly
    toggle changed both the chart's data and labels to real values; no
    console errors. Found and guarded one real gap while building: `
    request.user.role` on an `AnonymousUser` has no `.role` attribute at
    all and would crash the Recent Activity check — guarded with `request.
    user.is_authenticated and ...` rather than silently assuming a logged-
    in visitor; `dashboard()` itself still has no `@login_required`/RBAC
    mixin at all (adding one wasn't one of `09_DASHBOARD.md`'s approved
    decisions, so it wasn't added — flagged instead, see §12 technical
    debt, now a real-not-cosmetic risk since real business aggregates are
    what's exposed). 8 new tests (`DashboardViewTests`) — 144/144 passing
    (was 136). **Every page in the app is now genuinely real.**
39. **Phase 8.97: closed the dashboard auth gap (Part A) + a full-app
    wiring audit (Part B).** Part A (BUG-42): `dashboard()` converted from
    a bare function view to `DashboardView(AnyStaffMixin, View)` —
    matches every other real view's convention and `09_DASHBOARD.md`'s
    "any logged-in role" decision, not gated tighter. Verified live:
    anonymous `GET /dashboard/` → `302 /login/?next=/dashboard/`; all 3
    roles load correctly; Recent Activity's Phase 8.96
    `is_authenticated` guard is now belt-and-suspenders, not
    load-bearing. 1 test updated (`test_anonymous_redirects_to_login`,
    replacing the old "doesn't crash" assertion) + 1 added (all 3 roles
    load) — 145/145 passing. Part B: read every one of the app's 31
    routes (`frontend/urls.py`) against `frontend/views.py` directly,
    classifying each as real/mock, checking its auth mixin, and grepping
    every template for `|default:`/hardcoded-`<tr>`/hardcoded-stat tells
    — deliberately not trusting this file's own prior ✅ claims, which
    have been wrong 3 times already (Phase 3.9's `bugsfound.md` drift,
    Phase 4.5's role-field check, and Inventory/Dashboard in 8.7/8.8).
    Confirmed real and correctly guarded: all 26 other real views. Found
    2 more genuine gaps, both reported per this task's explicit
    don't-fix-silently scope: **BUG-43** — `demand_forecasting`/
    `slow_moving_dead_stock` also have zero auth requirement, same shape
    as the dashboard gap just closed, lower severity since both pages
    are still honestly-disclosed mock (no real data to expose yet).
    **BUG-44** — "Export"/"Export CSV" buttons on Products/Suppliers/
    Audit Log are decorative (no handler, no endpoint), unlike Reports'
    genuinely-wired export — previously covered only by this file's
    general "decorative controls exist" language, never named
    specifically. Every other `|default:"..."` hit across every template
    reconfirmed as a legitimate per-field null fallback or the one
    already-reviewed anonymous-identity fallback (BUG-40) — no new
    fabrication found anywhere. No orphaned hardcoded `<tr>` rows found
    outside `{% empty %}` fallbacks in any real module.
40. **Phase 8.98: made every button real** — Movement History (BUG-45),
    CSV exports (BUG-44), Dashboard search-bar cleanup, plus two small
    fixes found along the way. `MovementHistoryListView`
    (`/inventory/movements/`, `AnyStaffMixin`) is the real page behind
    Inventory's previously-dead "Movement history" button, over the real
    `InventoryMovement` ledger that's existed since Phase 3 — nothing new
    to create, just expose it. **Server-side date-range filtering was the
    deliberate choice, not client-side**: the ledger is append-only and
    grows forever, so `table-filter.js` alone would only ever see whatever
    one page happened to be loaded — real `Paginator`-backed pagination
    (page size 50) alongside it. Search (product/SKU) and movement-type
    filtering stay client-side on top of the current date-filtered page,
    same split every other real list page uses. An optional
    `?product=<id>` param (used by each Inventory row's own link) narrows
    to one product. `ProductExportView`/`SupplierExportView`/
    `AuditLogExportView` each build headers/rows from a real queryset and
    hand them to `frontend/reports.py`'s existing `generate_csv_response()`
    — the exact reuse `docs/bugsfound.md`'s BUG-44 entry predicted, not a
    new export mechanism — with auth matching each source page exactly
    (`AnyStaffMixin` on Products/Suppliers, `AdminRequiredMixin` on Audit
    Log). Products/Suppliers export the full dataset, not the current
    client-side filter selection, disclosed explicitly. Movement History's
    export reuses `build_movement_report()` directly and genuinely
    respects the current date filter, since that function already reads
    `date_from`/`date_to`. The global topbar search box (`.topbar-search`,
    present on every page including the Dashboard) was removed entirely —
    confirmed it never had any JS wiring at all; `.topbar-actions` picked
    up `margin-left: auto` to stay pinned right now that the search box's
    `flex:1` isn't there to do that anymore. Found and fixed two small
    things while building, both disclosed rather than silently patched:
    **BUG-46** — `frontend/reports.py`'s `_date_bounds()` built naive
    datetimes and compared them against a `USE_TZ=True` field, triggering
    a `RuntimeWarning` on every date-filtered report (silently correct via
    Django's own coercion, never actually exercised by any test with real
    date params until this phase's own new export test) — now explicit via
    `timezone.make_aware()`. Also a flaky pre-existing test
    (`NotificationViewTests` asserting on a bare `'T3'` substring against
    a page that always contains a random CSRF token — hit once, by chance,
    during this phase's own full-suite run) — fixture titles renamed to
    collision-proof strings. Verified live (Playwright, real Postgres):
    clicking "Movement history" navigates to the real page with 7 real
    rows matching the DB; a date range with no matches shows an honest
    empty state, not a fake zero; a wide range shows all 7; the per-row
    link correctly filters to one product; timestamps render in Asia/Dhaka;
    client-side search/type filters narrow correctly; all 4 exports
    download real CSVs whose row counts match the database exactly
    (Products 3, Suppliers 3, Audit Log 233 — the full log, not the
    on-screen 500-row cap — Movement History 7); a direct staff request to
    the Admin-only Audit Log export is blocked (`302`); no console errors
    anywhere. 21 new tests — 156/156 passing (was 145).
41. **Phase 8.98a: topbar spacing investigation + real Change Password
    modal.** Part 1 — a reported regression ("notification bell/user-menu
    badges moved left, should be pinned right") could not be reproduced:
    checked 9 viewport widths (480–1440px) × 3 pages (Dashboard/Products/
    Profile) × mobile-sidebar open/closed × all 3 roles, all 27
    combinations show `.topbar-actions` correctly flush-right via Phase
    8.98's own `margin-left: auto` fix, confirmed with
    `getBoundingClientRect()` (not just eyeballing a screenshot). Checked
    for a JS-side explanation too (nothing in any `.js` file touches
    `.topbar-actions`) and for a page-specific CSS override (nothing
    outside `login.html`/`landing/index.html` — both public pages with no
    topbar at all — uses the `extra_css` block). No code change made,
    since none reproduced a real defect to fix. Most likely explanation:
    a stale browser cache of `dashboard.css` from mid-edit during Phase
    8.98 itself — this dev setup has no cache-busting query param/hash on
    static URLs, so a browser that loaded the file between the search-bar
    removal and the compensating `margin-left: auto` fix landing would
    keep serving that broken intermediate version until a hard refresh.
    **Confirmed correct**: the user hard-refreshed (Ctrl+Shift+R) and the
    spacing problem resolved — stale cached CSS, not a code defect. No
    further action needed; noted here in case the same class of "looks
    broken, code is fine" report recurs after a future static-file edit —
    this project's dev server has no cache-busting on static URLs, so
    it's a real, recurring risk, not a one-off.
    Part 2 — Profile's old inline "new password" field (no current-
    password check, no confirm field — both real, disclosed gaps since
    Phase 4) replaced with a real "Change Password" button opening a
    modal, reusing the modal.js/modal-form.js recipe exactly (no new
    pattern) and posting to a new dedicated `change_password_view`
    (`/profile/change-password/`, `@login_required`, JSON responses —
    `profile_view`'s own POST still handles name/contact/photo separately
    and still redirects, since that's a different interaction shape than
    a modal). Three real server-side checks, all independent (not short-
    circuited, so a user can see every problem with one submission):
    current password correctness (`user.check_password()`), new/confirm
    match, and the same `validate_password()` call (full
    `AUTH_PASSWORD_VALIDATORS` chain, `StrongPasswordValidator` included)
    `profile_view` already used — reused, not reimplemented.
    `PASSWORD_CHANGED` audit log + notification calls are unchanged,
    still fire exactly once per successful change (confirmed by test, not
    just by reading the code — no duplicate-call risk since the old
    inline path was removed, not left running in parallel).
    `update_session_auth_hash()` keeps the session alive post-change, same
    as before. Verified live: wrong current password → real field error;
    weak new password → the real `StrongPasswordValidator` message, not a
    generic one; mismatched confirmation → real field error (confirmed
    twice — an initial rapid-fire multi-submission test read a stale/
    cleared DOM value once, so re-verified in isolation via a direct API
    call and a clean single-submission UI test, both showing the correct
    error); a valid change succeeds, the modal's success reload shows the
    real Django flash message, and the user can immediately log back in
    with the new password. 3 tests migrated off the old inline-field
    assertions onto the new endpoint (`test_password_change_hashes_...`,
    `test_weak_new_password_rejected_...`, `test_session_stays_alive_...`)
    + 4 new (`test_wrong_current_password_rejected`,
    `test_mismatched_confirmation_rejected`, `test_requires_login`,
    `test_get_not_allowed`) — 160/160 passing (was 156).
42. **Phase 8.98b: Purchases Expected Delivery + date guard.** First
    checked whether `expected_delivery` already existed on `PurchaseOrder`
    before adding anything — it did (`SCHEMA.md`'s own field,
    `DateField(null=True, blank=True)`), and was already in
    `PurchaseOrderForm.Meta.fields` too; confirmed no migration was
    needed via `manage.py makemigrations --check --dry-run` ("No changes
    detected"). The real gaps were narrower than the task's framing
    implied: (1) no table column — added "Expected delivery" as a real
    column in `purchases.html`, `—` when unset, alongside the existing
    "Order date" column; (2) no past-date guard — added
    `PurchaseOrderForm.clean_expected_delivery()`, rejecting any date
    before `timezone.localdate()` (Asia/Dhaka, the Phase 8.6 timezone
    convention, not the OS clock). The task's Part 2 also asked for an
    "order_date can't be in the past" guard and an "expected_delivery
    can't be before order_date" guard as if they were two more separate
    rules — investigated and reported rather than building phantom
    checks: `order_date` is `auto_now_add=True` (SCHEMA.md, unchanged),
    which Django's ModelForm machinery excludes from binding entirely (a
    raw POST can't set it either) and which is always exactly "today" at
    the moment a PO is actually saved — there is no order_date value to
    compare against during `clean()` (the instance isn't saved yet), and
    no way for it to ever be a past date in the first place since nothing
    ever supplies one. So "expected_delivery not in the past" and
    "expected_delivery not before order_date" are the same real-world
    check, not two — implemented once, not duplicated. Client-side, the
    date input's `min=` attribute is the same server-computed Asia/Dhaka
    date (`PurchaseListCreateView.get()` now passes `today =
    timezone.localdate()` into context), not the browser's local clock,
    so the two can never disagree the way the Phase 8.6 dashboard-
    greeting decision already established for this exact class of
    problem. Verified live (Playwright, real Postgres): the table shows
    the new column with real dates (and `—` for POs without one,
    including older seed data — the guard only applies going forward, it
    doesn't retroactively invalidate existing rows); the Add Purchase
    modal's date input carries a real `min=` matching the server's
    Asia/Dhaka today; a direct POST bypassing the client entirely with a
    past `expected_delivery` is rejected (`400`, real field error, no PO
    created) — confirmed the client-side `min=` isn't the only guard. 5
    new tests (`PurchaseOrderExpectedDeliveryTests`) — 165/165 passing
    (was 160).
43. **Phase 8.98c: moved tax onto Product, auto-calculated on every
    transaction.** Treated as the highest-risk item in its batch (a money-
    math + transaction-record change), done one step at a time. Added
    `Product.tax_rate` (`DecimalField(max_digits=5, decimal_places=2,
    default=0)`, migration `0002_product_tax_rate.py`) and its form field
    (`ProductForm.clean_tax_rate()`, non-negative, mirrors
    `clean_purchase_price()`/`clean_selling_price()`; optional like
    `reorder_level`, defaults to 0 when blank) — genuinely undocumented in
    `SCHEMA.md`/`API_CONTRACTS.md`, disclosed as its own decision (§13).
    Removed the tax `<input>` from `line-items.js`'s repeatable row editor
    entirely (shared by Purchase and Sale) — replaced with a read-only
    `.line-item-tax-display` div, sourced from the selected product
    `<option>`'s `data-tax-rate` attribute (now rendered server-side in
    `purchases.html`/`sales.html`'s `realProductOptions` template), updated
    on product-select as well as on qty/price/discount change (the select's
    `change` listener previously only cleared row errors, never
    recalculated). Adjustment's form/template were checked and confirmed to
    have no tax field to begin with — reported as a no-op, not built as a
    phantom feature. Both order-total footers now read "Total (incl.
    tax):" instead of a bare "Total:", since the grand total was always
    tax-inclusive (it sums each already-tax-inclusive `line_total`) but
    never said so.
    Server-side, tax is sourced from `Product.tax_rate` at exactly one
    place per flow, never a client value: `frontend.forms.
    parse_line_items()` (shared by Purchase and Sale) always overwrites
    `item['tax']` with `product.tax_rate` regardless of what a raw POST
    contains, and `SaleService.create_sale()` independently re-derives it
    from the product too rather than trusting whatever `items_data` was
    handed — belt-and-suspenders, satisfying the task's literal "never
    from a form field" wording at both the form-parsing layer and the
    service layer. The `line_total` formula itself — previously duplicated
    between `PurchaseOrderItem.save()` and `SaleService.create_sale()`
    (flagged as tech debt since Phase 3, §12) — is now one function,
    `frontend.pricing.calculate_line_total()`, in a new module with zero
    internal imports (needed to dodge a circular import: `models.py`
    cannot import `services.py`, which already imports `models.py`).
    `PurchaseOrderItem.tax`/`SaleItem.tax` stay real, separately-stored
    columns rather than derived at read-time — a deliberate historical-
    snapshot design (§13) — confirmed live by changing a product's
    `tax_rate` after creating a PO and a sale against it: both existing
    lines' stored `tax`/`line_total` stayed exactly as they were, while a
    third transaction created after the change picked up the new rate
    correctly. Confirmed no entanglement with stock/ledger logic per the
    task's explicit scope guard: the only lines touched in
    `SaleService.create_sale()` were the `discount`/`tax`/`line_total`
    computation inside the existing loop — the `InventoryService.
    decrease_stock()` call directly below it is untouched, and
    `InventoryMovement`'s immutability (BUG-20) was never approached.
    A new `seed_dev_data` management command (DEBUG-only guard, same
    pattern as `seed_test_users.py`) wipes the dev DB (`call_command
    ("flush", ...)`) and reseeds it end-to-end through the real service
    layer (`PurchaseService`/`SaleService`/`AdjustmentService`/
    `InventoryService` — never raw model saves for stock) with 4
    categories, 3 suppliers, 10 products spanning 6 distinct `tax_rate`
    values including 0% (the field's own default, so both the "no tax" and
    "has tax" cases exist in the seed), 12 purchase orders (10 fully
    received to stock the catalog, 1 left `DRAFT` and 1 left `PENDING` so
    the approval workflow has real in-progress rows to look at), 4 sales,
    and 2 adjustments (1 approved, 1 pending). Live-verified against the
    real running dev server, not just the reseed script or the test suite:
    logged in via a real session, confirmed the rendered Add Product modal
    has the new tax field and the Purchase/Sale line-items editor has no
    `<input class="line-item-tax">` anywhere in the HTML; created a real
    PO and a real sale, both against a 15%-tax product, and hand-verified
    the math against the actual stored `line_total` (`18.00 × 4 × 1.15 =
    82.80`, `32.00 × 2 × 1.15 = 73.60` — exact match both times, not
    rounded-and-close); then raised that product's `tax_rate` to 25% and
    confirmed a newly-created sale used 25% while the two earlier lines
    stayed at 15%, satisfying the task's explicit "confirm changing a
    product's tax_rate flows into a NEW transaction's calculation"
    requirement. 8 new tests (`ProductTaxRateTests`: tax_rate persists from
    the form, defaults to 0 when omitted, negative value rejected;
    `TaxAutoCalculationTests`: a Purchase/Sale line's tax is sourced from
    `Product.tax_rate` even when the client sends a different `tax` value
    or omits it entirely, an existing line's tax is not retroactively
    changed by a later `tax_rate` edit while a new one picks up the change,
    and `InventoryAdjustment` genuinely has no `tax` field) — 173/173
    passing (was 165).
44. **Phase 8.98d: per-record Purchase/Sale PDF download.** Explicit
    scope: individual record PDFs only, no change to the Reports module
    at all — verified afterward by diffing `frontend/views.py`'s
    `ReportsView`/`ReportExportView` and `reports/reports.html`, neither
    touched. Rather than inventing a second PDF-rendering scheme,
    `generate_pdf_response()`'s inline `Table`/`TableStyle` block (the
    styling every one of Reports' 9 exports already uses) was pulled out
    into `_styled_data_table()` — a pure refactor, confirmed behavior-
    identical by keeping every existing report-export test green — so the
    two new builders in `frontend/reports.py`,
    `generate_purchase_order_pdf(po)`/`generate_sale_transaction_pdf(sale)`,
    could call the same helper for both a small metadata table
    (supplier/customer, status, dates, created by) and the real line-items
    table (product, SKU, quantity, unit price, discount, the Phase 8.98c
    auto-calculated tax, line total), closing with a `Total Cost`/`Total
    Amount` line. `PurchaseOrderPDFView`/`SaleTransactionPDFView`
    (`purchases/<pk>/pdf/`, `sales/<pk>/pdf/`) carry the same
    `AnyStaffMixin` gate `PurchaseListCreateView`/`SaleListCreateView`
    already use — downloading a record's PDF is just another way of
    viewing a record already visible on that same page, so it gets the
    same access rule, not a new one. A "Download PDF" pill-button
    (`icon-receipt`) was added to every row on both `purchases.html` and
    `sales.html` as a plain `<a href>` GET link — the same shape as
    Reports' own CSV/PDF export links (`ReportExportView`), not a new
    fetch-based control needing JS wiring. Live-verified against the real
    reseeded dev DB, and more thoroughly than a status-code check: for
    both a real PO (`PO-20260813-8901`, 100 × Wireless Mouse @ $8.50,
    10% tax) and a real sale (`INV-20260813-5448`, 3 × Wireless Mouse @
    $15.00, 10% tax), downloaded the actual PDF bytes and decompressed
    the content stream by hand (`ASCII85Decode` + `FlateDecode`, the two
    filters ReportLab applied) to read the literal rendered text back out
    — not just trusting the HTTP headers — confirming every field
    (supplier/customer, status, dates, each line's product/qty/price/
    discount/tax/line-total, and the grand total) matched the database
    exactly: `8.50 × 100 × 1.10 = 935.00` and `15.00 × 3 × 1.10 = 49.50`,
    both exact. Confirmed anonymous `GET` on both PDF URLs `302`s to
    login, matching the list pages' own gate; confirmed an unknown pk
    `404`s rather than leaking a stack trace. 6 new tests
    (`PerRecordPDFViewTests`: login-required + success + 404-on-unknown-pk
    for each of Purchase/Sale) — 179/179 passing (was 173).
45. **Phase 8.98e: admin user creation with emailed credentials,
    password-change admin alerts, validated profile images.** The
    largest of the improvement phases, with a hard email dependency read
    first: confirmed `EMAIL_BACKEND` is the console backend (dev/test
    only, prints to stdout instead of sending) — real delivery needs a
    real SMTP backend at deployment, stated explicitly rather than
    implied.
    Part 1 reverses Phase 8's own disclosed decision to give `UserForm` a
    required password field — a second reversal on the same field, this
    time because the Admin must never choose or see a new user's
    password at all. `frontend.validators.generate_strong_password()`
    (new, `secrets`-based) builds one that passes every validator in
    `AUTH_PASSWORD_VALIDATORS` by construction (one uppercase/lowercase/
    digit/special char is always included, and a random string this long
    can't plausibly collide with `CommonPasswordValidator`/
    `UserAttributeSimilarityValidator` either); `UserListCreateView.
    post()` sets it via `set_password()` and hands it to a new
    `frontend.notifications.send_new_user_credentials_email()`, which
    sends a real, credentials-only email directly via `send_mail()`.
    That function is deliberately NOT built on `notify_user()` — the
    task's own hard rule is that the password must never appear in a
    notification or audit log, and `notify_user()` always stores its
    exact message in a `Notification` row, so building on it would mean
    either leaking the password into that row or lying about what
    happened in the in-app notification. No `Notification` row is
    created for the new user at all (11_NOTIFICATIONS.md has no
    "account created" type anyway — same precedent as
    `PurchaseService.cancel()`'s "logs but doesn't notify" reasoning, §12/
    §13); the email is sent unconditionally, bypassing `SystemSettings.
    email_notifications_enabled`, since that flag is a discretionary
    preference and this is the only channel a new account's password can
    ever travel through (disclosed, §13). `change_password_view` now
    also calls a new `notify_admins()` (same shape as
    `notify_supervisors()`, Admin-only), reusing the already-documented
    `PASSWORD_CHANGED` type for a second recipient rather than inventing
    one — every Admin learns *who* changed their password, never what it
    became.
    Part 2: `User.profile_image` already existed (SCHEMA.md's own field,
    Phase 1) but had zero validation and was never actually displayed —
    both closed, not built from scratch. `profile_view()` now runs
    uploads through `validate_product_image()` (frontend/validators.py),
    reused unchanged from `Product.image`/`SystemSettings.company_logo`
    (same function, same precedent, no duplicate check invented); a
    rejected upload shows a real error and leaves the existing value
    untouched. `.avatar` (topbar user menu, sidebar, profile page) now
    renders the real photo when set, via a small `.avatar img` CSS rule,
    falling back to the pre-existing initials exactly as before when not
    — the field existed but nothing ever rendered it before this phase.
    Same Render-ephemeral-disk production caveat as Phase 5/deployment
    (`DEPLOYMENT.md`) — flagged, not re-solved here, per this task's own
    scope instruction.
    Live-verified end to end against the real dev DB and the real
    console backend, not just the test suite (the backend's actual
    per-request stdout proved unreliable to capture through this
    session's background-process tooling, so verification ran through
    Django's real request/response cycle via `Client()` in a foreground
    `manage.py shell` process instead — same view code, same middleware,
    same console `EmailBackend`, just not a separate OS process): an
    Admin created a real user through the real `/users/` view; the
    console backend printed a real credentials email containing a real
    generated password; the DB's stored hash matched exactly what was
    emailed; the new user logged in with it for real (`302` to
    `/dashboard/`); a direct DB sweep confirmed that password appears in
    zero `Notification` or `AuditLog` rows anywhere, and that no in-app
    `Notification` exists for the new user at all; the new user then
    changed their password, and the Admin's resulting notification named
    them without the new password appearing in its title or message; a
    `.txt` profile-image upload was rejected, a valid `.png` was
    accepted, and it then rendered as a real `<img>` on both the profile
    page and the dashboard topbar. 9 new tests (`PasswordGeneratorTests`,
    `ProfileImageValidationTests`, plus additions to
    `ChangePasswordViewTests`/`UserManagementViewTests` proving the
    generated password never appears in any `Notification`/`AuditLog`
    row) — 188/188 passing (was 179).
46. **Phase 8.99: production deployment configuration + the
    auto_now_add/OS-clock pre-deploy fix (BUG-47).** Treated the timezone
    fix as a hard blocker, done before any deployment config, per the
    task's own framing: after the first real production PO/sale is
    created with a wrong date embedded in its own identifier, that's
    permanent. Confirmed the exact mechanism with a live shell check
    before touching code: `date.today()` and `timezone.now().strftime()`
    both agreed with `timezone.localdate()` on this dev machine only
    because its OS clock (`time.tzname` → Bangladesh Standard Time) is
    already Dhaka time, not because either call was actually
    TIME_ZONE-aware — `DateField.auto_now_add` is a documented Django
    limitation (unlike `DateTimeField.auto_now_add`, which is correctly
    UTC-aware). Fixed both `PurchaseOrder.order_date`/
    `SaleTransaction.transaction_date` (now plain `DateField()`s, set via
    `timezone.localdate()` in `save()`) and `_generate_po_number()`/
    `_generate_invoice_number()` (now `timezone.localdate().strftime(...)`
    instead of `timezone.now().strftime(...)`) — confirmed via the same
    live shell check that the PO-number's embedded date is a real
    identifier, not just a display column, so this was a potential
    wrong-identifier bug, not only a wrong-date-field one. Migration
    `0003_alter_purchaseorder_order_date_and_more` is `AlterField`-only,
    zero DB-level change (removing `auto_now_add=True` only changes
    Python-side `editable`/`blank` metadata, not the column). New
    `TimezoneAwareDateGenerationTests` mocks `timezone.now()` to a UTC
    instant on a different Dhaka calendar day, proving the fix doesn't
    depend on the real OS clock at all (a regression back to
    `auto_now_add=True` would still read this test's real, unmocked run
    date and fail). Full writeup: `docs/bugsfound.md` BUG-47 (closing the
    "related finding, disclosed not fixed" note left inside BUG-38 since
    Phase 8.6).
    Deployment configuration worked through `DEPLOYMENT.md`/
    `ENVIRONMENT.md`/`SECURITY.md` item by item, verifying each against
    actual `config/settings.py` rather than assuming: `DEBUG`/
    `SECRET_KEY`/`ALLOWED_HOSTS`/`DATABASES` were already fully env-driven
    with fail-closed defaults (no hardcoded dev key, no default-True
    DEBUG, empty-list-not-wildcard `ALLOWED_HOSTS`) — confirmed, not
    re-done. Added WhiteNoise (`requirements.txt` + middleware, placed
    second per `DEPLOYMENT.md`'s own instruction) with Django 6's
    `STORAGES` dict (`STATICFILES_STORAGE`, DEPLOYMENT.md's documented
    setting name, no longer exists as of Django 5.1 — verified against
    `django.conf.global_settings` directly rather than assuming
    DEPLOYMENT.md's snippet still matched this Django version), verified
    by actually running `collectstatic` (163 files, 489 post-processed)
    then a local server with `DEBUG=False` — hit `SECURE_SSL_REDIRECT`'s
    own 301 loop immediately (expected: no local HTTPS listener), added
    `SECURE_PROXY_SSL_HEADER` for Render's edge-terminated-TLS proxy
    shape (a real, undocumented-in-this-project's-docs deployment gotcha,
    not spec'd in SECURITY.md/DEPLOYMENT.md) and re-verified with a
    spoofed `X-Forwarded-Proto: https` header — every static asset then
    served `200` with correct content-hashed filenames, gzip encoding,
    and immutable cache headers, and the CSRF cookie carried `Secure`.
    Wired `EMAIL_HOST`/`PORT`/`USE_TLS`/`HOST_USER`/`HOST_PASSWORD` from
    env (documented in `ENVIRONMENT.md`, but nothing in `settings.py` had
    ever actually read them before this phase — a real gap for Phase
    8.98e's emailed-credentials feature specifically, which has no
    fallback if the email silently never sends). Added `DB_SSLMODE` env
    override (default `'prefer'`, psycopg's own default — a no-op unless
    explicitly set, giving Render room to require SSL without a code
    change). Deliberately omitted `SECURITY.md`'s `SECURE_BROWSER_XSS_FILTER`
    — removed from Django itself in 4.0, would be inert cargo under this
    project's Django 6.0.7, disclosed rather than added as dead weight.
    `python manage.py check --deploy` passes clean (zero warnings) under
    `DEBUG=False` with a real `ALLOWED_HOSTS` set.
    Media: added `SERVE_MEDIA_IN_PRODUCTION` (default `False`) rather than
    quietly extending dev's DEBUG-gated media serving into production —
    Render's disk is ephemeral, so serving media there at all is only
    correct once a persistent disk is deliberately mounted at
    `MEDIA_ROOT`. Recommendation stated rather than guessed at: a Render
    persistent disk fits this app's actual scale (small internal
    inventory tool, not high-traffic); `django-storages` + S3/Cloudinary
    is the better long-term answer once scale justifies a new dependency
    and real cloud credentials this phase had no way to obtain or verify.
    First production admin: verified `createsuperuser` actually works
    against this project's custom `User`/`UserManager` (not assumed) —
    created and immediately deleted a throwaway superuser, confirmed
    `role='admin'`/`is_staff`/`is_superuser` all set correctly and the
    password check succeeds. Noted a real, Django-level gotcha for the
    go-live checklist: `--noinput` mode (env-var-driven, non-interactive)
    skips `AUTH_PASSWORD_VALIDATORS` entirely, so the real first admin
    should be created interactively instead, where
    `StrongPasswordValidator` actually runs. Reconfirmed
    `seed_test_users`/`seed_dev_data` stay DEBUG-guarded, refusing to run
    in production — not an alternative path.
    **The 3 "faked in dev" features, given explicit verdicts per the
    task's own anti-ambiguity gate**: emailed new-user credentials and
    the forgot-password reset are both **DEFERRED** — code/settings-ready
    (SMTP wiring exists now) but not verified against a real inbox in
    this phase (no real Gmail app password or outbound SMTP access
    available to prove delivery), so calling either "LIVE" would be
    exactly the silent-failure this gate exists to catch; forgot-password
    stays disabled in the UI until the same follow-up closes it. Uploaded
    product/profile images are **DEFERRED** — functional within a single
    running instance, lost on every redeploy until
    `SERVE_MEDIA_IN_PRODUCTION` + a persistent disk (or object storage)
    is actually attached. None of the three are silently shipped as
    "working." 2 new tests (`TimezoneAwareDateGenerationTests`) —
    190/190 passing (was 188).
47. **Phase 8.99a: finished the forgot-password flow, locally.**
    Deployment explicitly out of scope this session — no WhiteNoise/media/
    production-settings changes, just the last disabled control in the
    app and the audit gap behind it. Confirmed the gap by reading
    `PasswordResetConfirmView.form_valid()`'s actual source before writing
    any fix, rather than assuming Django's own reference flow logs/
    notifies anything (it doesn't — it just calls `form.save()` and
    redirects). Built the 4 real templates plus the 2 email-side ones
    Django needs to send a correctly-linked email
    (`password_reset_email.html`/`password_reset_subject.txt`), all
    reusing `login.html`'s exact `.auth-page`/`.auth-card` structure and
    `auth.css`/`components.css`'s existing classes — no new CSS, no new
    layout, per the task's own explicit constraint.
    Closed BUG-48: extracted the shared `notify_user()`/`notify_admins()`/
    `audit.log_action()` triplet out of `change_password_view` into a new
    `_record_password_change(user, request)` helper, and added
    `StockwellPasswordResetConfirmView`, which calls it once after
    `super().form_valid(form)` — Django's own password-setting logic
    reused unmodified, `form.user` (not `self.request.user`, anonymous at
    this point) as the target, the new password itself never read.
    Namespace decision: moved the whole flow onto `frontend:`, removed
    the dead `accounts:` django.contrib.auth.urls include outright — not
    a style preference but a real requirement, discovered live: Django's
    own default `success_url`s and default email template both reverse a
    *bare* URL name, which `NoReverseMatch`es once the route only exists
    inside a namespace, confirmed by hitting that exact error before
    fixing it with explicit `frontend:`-prefixed reverses everywhere.
    SMTP smoke test (Part 4) explicitly skipped and reported as such — no
    real Gmail app password exists in this environment; both this flow
    and Phase 8.98e's emailed credentials remain unverified against a
    real inbox, carried forward as a named follow-up rather than assumed
    working.
    Verified live against the real seeded `verify_user` account, not just
    the test suite: real console-backend email sent with a working link;
    Stockwell-styled pages confirmed (not admin's fallback ones, checked
    via distinguishing markup); weak password rejected with the real
    validator message and no audit row; valid reset succeeds and
    `verify_user` logged in with the new password for real; a real
    `AuditLog` row and a real `verify_admin` notification (new password
    absent from both title and message) both now exist for the reset
    path specifically; an invalid/tampered token shows Stockwell's own
    "link no longer works" message. `verify_user`'s password restored via
    `seed_test_users` afterward. 10 new tests (`PasswordResetFlowTests`)
    — 200/200 passing (was 190).
48. **Phase 8.99b: Sales go through approval before completing, mirroring
    Purchases.** The highest-risk phase since 8.98c — moved one step at a
    time as instructed, with two genuinely ambiguous design points raised
    to the owner *before* writing code rather than guessed at (both would
    have been expensive to redo): whether a Supervisor can approve a sale
    they created themselves (owner: match Purchases' existing looseness,
    no restriction — confirmed via reading the code that Purchases really
    has none, not assumed), and whether Sales needs a full Draft→Submit→
    Pending mirror or a simpler straight-to-Pending creation (owner: full
    mirror, matching Purchases exactly and making the task's own
    requested `SALE_SUBMITTED` audit constant a real, non-redundant
    event rather than a duplicate of `SALE_CREATED` at the same instant).
    State decision: no separate `APPROVED` status added — `SaleStatus`
    gained `DRAFT`/`PENDING`/`REJECTED` alongside the pre-existing
    `COMPLETED`/`CANCELLED`, reusing `COMPLETED` rather than renaming it
    so every existing dev row stayed valid with zero migration. Reasoning
    written up in full in §13: a Purchase's approval and receipt are
    genuinely different moments; a Sale's approval *is* the moment stock
    moves, so a distinct `APPROVED` status would have no event of its own
    to describe. Added `approved_by`/`approved_at` (mirrors
    `PurchaseOrder` exactly) and `rejected_reason` (new — `SaleTransaction`
    never had a rejection concept before). Migration is additive/
    `AlterField`-only; existing `completed` rows needed no data fix.
    Split `SaleService`: `create_sale()` now creates a `DRAFT` with zero
    `InventoryService` contact at all (confirmed by reading every changed
    line against the money-math functions — `calculate_line_total()`/
    `Product.tax_rate` — which are byte-for-byte unchanged); new
    `submit_for_approval()` (mirrors `PurchaseService`'s own method name
    and shape exactly); new `approve_sale()` — the only place a sale's
    stock now moves, re-validating availability for real at that moment
    rather than trusting whatever was true at draft time; new
    `reject_sale()` mirrors `PurchaseService.reject()`, logs but doesn't
    notify (no documented notification type for "sale rejected" — same
    precedent `AdjustmentService.reject()` already established, not
    re-litigated here). `cancel_sale()` restricted to `DRAFT`/`PENDING`
    only, and — since nothing is deducted before approval anymore — no
    longer calls `InventoryService.increase_stock()` at all; there is
    nothing to restore pre-approval, and reversing an already-completed
    sale is explicitly out of scope, named in the task itself as Phase
    8.99c's own problem.
    Confirmed live, deliberately: two drafts created against the same
    limited stock (both look satisfiable at creation, since draft sales
    reserve nothing) — the first approval succeeds, the second fails with
    a specific, clean error ("Insufficient stock for 'Bluetooth Speaker'.
    Available: 49, Requested: 51"), the sale stays pending, stock is
    exactly what the first approval left. Customer-facing consequence
    stated plainly, not discovered later: a staff member can tell a
    customer "order placed" and have it fail at approval; real stock
    reservation at draft time was deliberately not built (a materially
    bigger feature — expiry, released-on-reject, reserved-vs-available
    everywhere) per the task's own explicit instruction, with an
    indicative (non-binding) creation-time stock check recommended as the
    cheap mitigation, not built this phase either.
    `NotificationType.SALE_PENDING` added as a disclosed, deliberate
    override of the Phase 8.98e "don't invent an undocumented type"
    precedent — that precedent covered a merely-informational gap; this
    one is load-bearing, since without it the entire approval gate has no
    trigger. `SALE_COMPLETED` (existed since Phase 1, never actually
    fired by any reference code) gets its first real use, on approval,
    notifying the sale's creator — mirrors `PO_APPROVED`'s shape exactly.
    RBAC: `AnyStaffMixin` on create/submit, new `SupervisorRequiredMixin`-
    gated `SaleApproveView`/`SaleRejectView` (confirmed live an Admin can
    approve too — the hierarchy holds), no creator≠approver restriction
    per the owner's confirmed decision.
    UI: `sales.html` gained real status badges and Submit/Approve/Reject/
    Cancel row actions matching `purchases.html`'s shape exactly —
    removed a pre-existing, fully decorative "View invoice" button (no
    handler at all) found while editing this exact region, not left as
    stray dead markup once its neighborhood was already being rewritten;
    added a "Pending approval" stat card mirroring Purchases' own; the
    status filter's `<option value=...>`s match the real `TextChoices`
    (Phase 8.7's rule); "Complete sale" button copy changed to "Save
    draft" so it stops claiming something that's no longer true.
    `row-actions.js` reused unchanged for the new row actions — no sixth
    copy of the shared CSRF/fetch helper. Phase 8.98d's per-record Sale
    PDF now shows Approved By/Approved At, confirmed live by
    decompressing real PDF content streams for both a completed and a
    still-pending sale (not assumed correct from the code), matching the
    blank-dash pattern the Purchase PDF already used for
    `expected_delivery`.
    `seed_dev_data.py` updated so seeded sales reach a realistic
    `COMPLETED` state (3 of 4 pushed through submit+approve; 1 left
    `PENDING`, same in-progress variety the PO seed already had) —
    without this fix, re-running the seed command after this phase would
    have silently left every seeded sale stuck in `DRAFT`.
    Swept every other `SaleService`/`SaleStatus` call site in the existing
    test suite (Phase 8.98c's tax tests, Phase 8.98d's PDF tests, the
    Dashboard tests) — all passed unchanged, confirming none of them
    depended on immediate completion; `SaleServiceTests`/
    `SaleWorkflowViewTests`/`LowStockNotificationTests` rewritten for the
    new flow, one test per documented transition, matching Phase 7's own
    "write tests alongside the views" precedent for exactly this class of
    workflow logic. 14 net new tests — 214/214 passing (was 200).
49. **Phase 8.99c: cancellation restricted, reason required everywhere.**
    `PurchaseService._CANCELLABLE_STATUSES` narrowed to `DRAFT`/`PENDING`
    (was also `APPROVED`/`PARTIAL`), overriding `05_PURCHASES.md`'s "any
    state -> CANCELLED"; `SaleService.cancel_sale()`'s existing DRAFT/
    PENDING-only rule (Phase 8.99b) confirmed and locked in. Full
    reasoning, the named-but-unsolved "stranded approved PO" consequence,
    and `InventoryAdjustment` as the documented post-completion correction
    path are all written up in §13 — not repeated here.
    New fields: `cancelled_reason`/`cancelled_by`/`cancelled_at` on both
    `PurchaseOrder` and `SaleTransaction` (migration
    `0005_purchaseorder_cancelled_at_and_more`), a required reason on both
    services' `cancel()`/`cancel_sale()`, `ReasonForm` reused a third/
    fourth time rather than writing a new form. New `display_reason`
    property on both models feeds the list-table status-badge tooltip,
    the per-record PDFs' new "Cancelled By"/"Cancelled At"/"Reason" rows,
    and a new "Reason" column on both the Purchase Report and Sales
    Report (CSV + PDF) — `build_sales_report()`'s `status=COMPLETED`
    filter was removed for this to be non-vacuous (§13 has the full
    disclosure). Client-side: `.po-cancel-btn`/`.sale-cancel-btn` now use
    `prompt()` for the reason, mirroring the existing reject handlers —
    no new modal.
    Verified the receive/partial-receive flow is byte-for-byte
    unchanged: `receive_items()` itself was not touched, and every
    pre-existing receive test (Phase 7's full/partial-receive tests,
    Phase 8.98b's expected-delivery tests) passed unmodified. The BUG-25
    stock-untouched invariant survives under the new, narrower rule —
    proven differently than before: a blocked cancel on `APPROVED`/
    `PARTIAL` now leaves stock untouched because cancel() is refused
    outright (a `ValueError`, not a special-cased no-op), confirmed via a
    direct POST past the hidden button.
    3 tests removed (they exercised cancelling from APPROVED/PARTIAL,
    which is no longer legal), replaced with tests for each newly-refused
    transition (APPROVED/PARTIAL/RECEIVED) plus blank-reason rejection on
    both Purchase and Sale cancel — net +3 tests, 217/217 passing.
50. **Phase 8.99d: Movement History filters go fully server-side, export
    gets a PDF twin.** Date, product, movement type, and search are now
    one shared GET filter (`frontend/reports.py`'s new
    `filter_movements()`), used by both `MovementHistoryListView` and its
    export — closing a real page-vs-export mismatch (date filtering used
    two different comparisons; product/type/search weren't in the export
    at all). Search moved server-side rather than staying client-side
    with a "not exported" caveat — same unbounded-ledger reasoning BUG-45
    already used for date range; `table-filter.js`/`movement-history.js`
    (deleted) are gone from this page. The `?product=<id>` deep-link now
    lands in a real `<select>` in the same form. PDF export added,
    reusing `generate_pdf_response()`/`_styled_data_table()` (new optional
    `filters_summary` param, only used here — the 9 existing report
    exports are unaffected) with active filters stated in the header, e.g.
    "Filters: Product: Wireless Mouse; Type: Purchase Receipt". Full
    reasoning for all of the below is in §13, not repeated here.
    Investigated whether a "cancelled/rejected source document" filter
    could be added (the task's own explicit ask) — confirmed
    `reference_type`/`reference_id` are populated consistently on every
    one of the 3 real movement-writing call sites, built the honest join-
    based version, confirmed it correct, then deliberately did **not**
    wire it to a UI control: Phase 8.99c's own cancellation rules make it
    structurally impossible (not just empirically empty — 0 of 19 real
    movements match) for any movement's source to ever reach CANCELLED/
    REJECTED after stock has moved, so a filter control for it would be
    the exact `MovementType.RETURN` defect this same phase removes
    elsewhere, reintroduced. `MovementType.RETURN` itself confirmed unused
    everywhere (grepped both `.py` files — only PURCHASE/SALE/ADJUSTMENT
    are ever produced) and removed from Movement History's type filter;
    left on the model (SCHEMA.md's, no migration for no benefit).
    Corrected the task's own premise along the way: the dead `return`
    option was never on Inventory's own status filter (`available`/
    `low_stock`/`out_of_stock` — no movement-type concept at all), only on
    Movement History's — checked before "fixing" a page with nothing to
    fix. 8 new tests (filter combinations, pagination-survives-filter,
    CSV/PDF row counts against a direct DB query for 4 filter combos
    including a zero-row one, the removed RETURN option) — 225/225
    passing (was 217). Live-verified against the real dev DB throughout,
    including decompressing the PDF's content stream to confirm the
    filters line actually renders, and confirming the Reports page's own
    "Movements" report (its `category` filter, layered on the same shared
    function) still works unchanged.
51. **Phase 8.99e: Product Edit/Delete — this project's first per-entity
    update route.** Diagnosed before building anything, per the task's
    own instruction: the report was "Add and Update buttons don't work,"
    but Add was confirmed genuinely working live (page loads, modal
    opens, a real POST persists a real product with a real audit row,
    verified against the real dev DB) — the report meant Edit/Delete,
    which never existed at all (plain dead `<button>`s, no handler, no
    `data-*`, since Phase 3's mock era). Not a regression to fix; new
    work to build.
    `ProductUpdateView` (`AnyStaffMixin` — 02_RBAC.md: edit is all 3
    roles) reuses `ProductForm` completely unchanged via `instance=`, not
    forked — same validation (uniqueness, non-negative prices, active-
    only Category/Supplier, tax_rate, image) applies to edit exactly as
    create. `ProductDeactivateView` (`SupervisorRequiredMixin` —
    02_RBAC.md: deactivate is Admin/Supervisor only) is the real
    `is_active = False` soft-delete 03_PRODUCTS.md requires; the row
    pill was relabelled "Delete" -> "Deactivate" rather than kept
    mislabelled. Two different mixins on two buttons in the same row,
    matched 1:1 to 02_RBAC.md's asymmetry, Phase 8.5 template-conditional
    pattern. SKU made read-only on edit (disclosed decision) — enforced
    server-side by always overwriting the posted `sku` with the
    instance's current value before the form validates, not just by
    disabling the client input. New `InventoryService.sync_reorder_level()`
    keeps `InventoryRecord.reorder_level` (and its derived status) in
    sync with an edited `Product.reorder_level`, writing no ledger row —
    the only `InventoryService` change this phase made, per its own scope
    limit. Full reasoning for all of the above, plus the
    Suppliers/Categories "should this pattern extend to them" recommendation
    (yes structurally, not built this phase) and the Reactivate
    follow-up recommendation (yes for symmetry, not built this phase),
    is in §13.
    UI: a second modal (`#editProductModal`/`#editProductForm`) reusing
    `modal-form.js`'s `ModalForm.init()` a second time on the same page
    (explicitly designed to support this) rather than one form toggling
    mode; pre-filled entirely client-side from each row's own
    `data-product` JSON (`ProductListCreateView.get()`, mirroring
    `PurchaseOrder.receive_items_json`'s existing pattern) — no
    fetch-before-open round trip, no new fetch helper. `InventoryModal.
    open()` added to `modal.js`'s public API (only `close()` existed) so
    a row click can populate fields before the modal becomes visible.
    13 new tests (edit persistence, negative-price/inactive-category
    rejection, a SKU-tamper-is-a-no-op test replacing the literal
    "duplicate SKU on edit" ask — see §13 for why that scenario is now
    structurally impossible by design — barcode uniqueness standing in
    to prove the same validation path still runs, reorder_level sync
    with no ledger write, the RBAC split, deactivated-product exclusion
    from Purchase/Sale forms) — 238/238 passing (was 225). Live-verified
    against the real dev DB across all 3 roles: Staff edits successfully
    and is blocked (302) from deactivating; Supervisor deactivates
    successfully; a tampered SKU in the POST body is silently ignored;
    zero new `InventoryMovement` rows from create+edit+deactivate
    together; the deactivated product vanishes from Purchases'/Sales'
    product dropdowns while remaining visible (with its history) on the
    Products list itself.
52. **Phase 8.99f: the emailed-credentials flow proven LIVE — the
    DEFERRED verdict is closed.** Verification only, no rebuild — the
    task's own explicit instruction was to prove the existing Phase
    8.98e/8.99a machinery, not write a second one, and nothing here did.
    **Step 1 (console backend): no regression since 8.98e.** Created a
    real Supervisor and a real Staff user through the real `/users/` view
    against the real dev DB — a real credentials email printed with a
    real generated password, correct username, and the change-it note;
    both new users logged in with that exact password (`302` to
    `/dashboard/`); a DB-wide sweep for both passwords across every
    `AuditLog.details` and `Notification.title`/`message` came back zero
    hits, and neither new user got a `Notification` row at all — every
    invariant Phase 8.98e's own writeup claimed still holds.
    **Step 2 (real SMTP): now genuinely LIVE, not just code-verified.**
    The owner provided a real Gmail account + app password (confirmed
    it was an actual 16-character app password, not a real account
    password, before using it — see the credential-hygiene note below).
    Set `EMAIL_BACKEND`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/
    `DEFAULT_FROM_EMAIL` in `.env` (never committed — confirmed gitignored
    first). First attempt failed with a real, informative error (Gmail
    `535 Bad Credentials`) — traced to a transcription mistake on this
    session's own side (a character dropped while stripping spaces from
    the app password), not a code or account problem; fixed and retried.
    Sent one real admin-creates-a-user email and one real password-reset
    email (Phase 8.99a's flow) in the same SMTP session, per the task's
    own "prove both together, it's cheaper now than on deploy day"
    instruction — **both confirmed received in the real inbox by the
    owner**, not just "`send_mail()` didn't raise," which is exactly the
    bar the task set ("send_mail() returned without error is NOT
    verification — the inbox is"). Reverted `EMAIL_BACKEND` to the
    console backend afterward for normal dev; the real `EMAIL_HOST_*`
    values stay in `.env` (gitignored) so proving this again later — e.g.
    before a real deploy — is a one-line edit, not a re-hunt for
    credentials.
    **Credential-hygiene finding, worth keeping**: the owner's first
    offer wasn't an app password at all — it was their real Gmail account
    password. Caught before it was written anywhere or used for an SMTP
    attempt (format alone was the tell: real app passwords are 16 plain
    lowercase characters, no digits/punctuation) and flagged back rather
    than silently trying it — using a real account password for SMTP is
    both likely to fail outright (Google blocks basic auth once 2FA is
    on) and a strictly worse credential to have handled at all versus a
    scoped, individually-revocable app password. The owner generated a
    real app password once asked; that's the one actually in `.env` now.
    **Step 3 (forced-change-on-first-login): reported, not built, per the
    task's own explicit instruction.** Confirmed by grep — no
    `must_change_password`-shaped field anywhere in `models.py`/
    `SCHEMA.md`, no forced-change hook anywhere in `login_view`/
    `01_AUTH.md` — the credentials email's "please change it" is advisory
    only today; a new user can keep the generated password indefinitely.
    Recommendation: enforced is more correct for a real deployment, but
    advisory is a defensible choice for a tool this size, and building
    the enforcement machinery (a `must_change_password` flag, a redirect
    gate on every authenticated view, an exception carved out for the
    change-password page itself so the gate doesn't lock a user out of
    the one page that clears it) is real, scoped work — the owner's call,
    flagged as a candidate for its own small phase, not built here.
    **The "3 faked in dev" gate, updated**: emailed credentials and
    password-reset both move from DEFERRED to **LIVE** (see the intro
    blockquote above and the gate's own paragraph, both updated this
    phase). Uploaded product/profile images remain the one still-DEFERRED
    item of the original three — untouched by this phase, unrelated
    dependency (persistent disk/object storage, not email). No code
    changes beyond `.env` — 238/238 passing, unchanged from Phase 8.99e
    (Django's test runner overrides `EMAIL_BACKEND` to an in-memory one
    regardless of `.env`, so this phase's settings change was never
    reachable by the suite — confirmed by re-running it after the `.env`
    edit, same 238/238).
53. **Phase 8.99f-2: admin email re-confirmed, real user delete, the
    sidebar badge's hardcoded "6" fixed.** Three items, diagnosed against
    the actual code before changing anything, per the task's own
    instruction.
    **Part 1 — already proven, re-confirmed only.** Phase 8.99f (this same
    session) already sent real credentials/reset emails to a real Gmail
    inbox and got them confirmed received — not redone. One console-
    backend regression check (a real Supervisor + Staff creation) showed
    no change since: real email printed, 2 audit rows, zero `Notification`
    rows for the new users. No code touched.
    **Part 2 — the on_delete reality, stated first.** Every `User` FK in
    this project is `PROTECT` (`PurchaseOrder`/`SaleTransaction`'s
    `created_by`/`approved_by`/`cancelled_by` — 6 fields — plus
    `InventoryMovement.performed_by`, `InventoryAdjustment.requested_by`/
    `approved_by`) except `AuditLog.user` (`SET_NULL`) and
    `Notification.recipient` (`CASCADE`, harmless — a user's own in-app
    notifications). Hard-deleting a user referenced by any `PROTECT` FK
    would raise `ProtectedError` — a 500, not a delete; hard-deleting one
    referenced only via `AuditLog.user` would silently null who performed
    a real, audited action. `UserDeactivateView`/`UserReactivateView`
    (Phase 8) already existed, complete, `AdminRequiredMixin`-gated, with
    the self-deactivation guard already in place — and `users.html`'s row
    pills were *already* correctly labelled "Deactivate"/"Reactivate" and
    already wired via `user-form.js`, not a dead or mislabelled "Delete"
    button as the task predicted. The actual gap was narrower: no true
    delete existed at all, for anyone. Built one, deliberately narrow —
    new `UserDeleteView` (`AdminRequiredMixin`) only ever succeeds for a
    user who appears in *none* of the 9 tables above (new
    `_user_ids_with_history()` helper, `frontend/views.py`: 10 cheap
    `.values_list(...flat=True)` queries, one shared computation used by
    both `UserListCreateView.get()` — to decide which rows even get a
    "Delete" pill — and `UserDeleteView` itself, so the button's presence
    and the server's enforcement can't disagree). Anyone with any history
    gets a clean refusal ("This user has activity history and can't be
    deleted; deactivate instead."), not a 500. Same self-action guard as
    deactivate. New `audit.USER_DELETED` (undocumented in `13_AUDIT.md` —
    disclosed addition, load-bearing: a delete with no audit trail at all
    would be worse than the gap it closes) logs the deleted username in
    `details=`, since `affected_id` alone points at a row that no longer
    exists after this one action (every other audited user action leaves
    the row in place). Label honesty: the new button says "Delete"
    because it now genuinely, permanently deletes — no dishonesty to fix
    on the existing Deactivate/Reactivate pills, since they were already
    named correctly.
    **Part 3 — the sidebar badge.** Found: a literal, static
    `<span class="nav-item-badge">6</span>` in `includes/sidebar.html`,
    left over from the Phase 3.6 mock era, wired to nothing (confirmed
    via grep before touching it). The topbar bell's own badge
    (`#notifBadge`) turned out to be a small dot, not a number — driven by
    `notifications.js`'s existing 30-second poll of
    `/notifications/unread-count/` (`NotificationUnreadCountView`, Phase
    8: `Notification.objects.filter(recipient=request.user,
    is_read=False).count()`), hidden by default and unhidden only when
    the count is nonzero. Rather than add a context processor or a second
    poll, `pollUnreadCount()` itself was extended to update *both*
    badges from the one fetch response — one mechanism, not two, matched
    to whichever the topbar already used. The sidebar badge is now
    `hidden` by default in the markup too (same "hidden until the first
    poll resolves" shape the topbar dot already had), text set to the
    real count, and hidden again at zero — the two can't disagree since
    they're now driven by the same number in the same callback. Confirmed
    live: a user with 16 pre-existing unread notifications plus 3
    deliberately created showed `unread_count: 19` at the shared
    endpoint; marking one read dropped it to 18 immediately.
    7 new tests (5 for the delete rules — clean-user succeeds, history-
    via-PurchaseOrder refused, history-via-AuditLog-only refused,
    self-delete refused, Staff blocked — plus the `deletable` context-flag
    test and the sidebar-badge-markup test) — 245/245 passing (was 238).
    Live-verified against the real dev DB across roles: a real clean
    throwaway user hard-deleted successfully with a real `USER_DELETED`
    audit row; a real user with real `PurchaseOrder` history refused with
    the clear message; Staff blocked (`302`) from both delete and
    deactivate; deactivate/reactivate round-tripped correctly on a real
    account.
54. **Phase 8.99f-3: Add User modal audited (clean), the stranded-account
    email-failure gap closed.** **Part 1 — field-by-field audit against
    `SCHEMA.md` §1, same discipline as BUG-31/BUG-35: no changes needed.**
    `UserForm`'s 5 fields (`full_name`/`username`/`employee_id`/`email`/
    `role`) exactly match every non-blank-required `User` field; no
    invented fields, no `first_name`/`last_name` (BUG-40's lesson held),
    no password field (confirmed still correctly absent, Phase 8.98e);
    role `<option value>`s match `UserRole`'s real choice strings exactly;
    client-side `REQUIRED_FIELD_IDS` matches the server-required set
    exactly. Live-verified rather than inferred: duplicate username/email/
    employee_id and a missing required field all returned clean, field-
    mapped `400`s, no `500`. One non-blocking observation, not a defect:
    `User.contact_number` (optional, `blank=True`) isn't collected at
    creation — consistent with `profile_image` also being deferred to the
    profile page rather than the create form, not fixed here since it
    wasn't asked for and isn't required.
    **Part 3 — a real, confirmed defect: a failed credentials-email send
    was indistinguishable from a real success.**
    `send_new_user_credentials_email()` already fails open internally
    (catches its own exception, prints server-side, returns `False`) —
    but `UserListCreateView.post()` never looked at that return value, so
    a genuine SMTP failure produced the exact same `{"success": True}` as
    a real send: a real, active account with a real, usable password that
    nobody — not the Admin, not the new user — actually knows. Reproduced
    live before fixing (mocking `send_mail` itself, not the wrapper, to
    match the real failure shape): confirmed the account is created
    either way and the response was unchanged. Fix, deliberately not a
    rollback: the account creation stays (throwing away validated admin
    work — username/employee_id/role already chosen — over what's usually
    a transient delivery problem is the wrong trade), but the view now
    checks the return value and adds a `warning` key naming the affected
    email when the send failed; `user-form.js` surfaces it via `alert()`
    before the reload. Absent on every normal success — confirmed the
    existing 8.98e test asserting the bare `{'success': True}` shape still
    passes unmodified. 2 new tests (failure produces the warning and still
    creates a usable account; normal success has no warning key) — none
    of Phase 8.98e's own tests needed changes.
    **Part 2 — re-proven over real SMTP for both a Staff and a Supervisor
    creation, plus the `email_notifications_enabled` override
    specifically.** Both created through the real `/users/` endpoint
    (Gmail `+`-alias addresses so two unique, real, same-inbox addresses
    could be used) — the Staff account deliberately created with
    `SystemSettings.email_notifications_enabled` set `False` first, to
    prove the credentials email still bypasses it (Phase 8.98e's own
    disclosed decision, §13); restored `True` before the Supervisor
    creation. Both real emails confirmed received by the owner, correct
    subject/username/password/change-note content. Security invariant
    re-confirmed under real SMTP (not just console, per 8.99f): exactly
    one clean `USER_CREATED` audit row per account, zero `Notification`
    rows, `details={}` — no password anywhere. `EMAIL_BACKEND` reverted to
    console afterward, both throwaway verification accounts deleted.
    245/245 → 247/247 passing.
55. **Phase 8.99f-4: the Add User modal's stray lines + the missing
    success confirmation (BUG-51/BUG-52).** **Part 1** — grepped every
    `{# #}` in `users.html` before touching anything: 3 of 4 close on
    their own line and are fine; one, directly above the modal's info
    banner, spans 3 lines — the exact BUG-03/BUG-36 shape (Django's
    `{# #}` tokenizer isn't `DOTALL`), confirmed by rendering the page and
    finding the literal comment text inside the actual HTML output before
    fixing it, not just reading the template source. Converted to
    `{% comment %}{% endcomment %}`, same fix as both prior occurrences.
    **Part 2 diagnosis, reproduced live before changing anything**: the
    create genuinely, reliably succeeds — the "no confirmation" report is
    accurate not because anything is broken, but because nothing was ever
    built. `UserListCreateView.post()` never called `messages.success()`
    (ruling out the Phase 8.5 flashed-message-never-rendered shape) and
    never returns a redirect (ruling out the `fetch()`-follows-302 shape,
    already fixed elsewhere by `row-actions.js`'s `Response.redirected`
    check) — it's a `JsonResponse` the whole time. Checked every other
    Add-modal's own `onSubmit` (`product-form.js`, `purchase-form.js`):
    all of them *also* just `window.location.reload()` on success with no
    toast, `alert()` used only for confirm-prompts/warnings/errors
    app-wide. So "it worked when tested" meant exactly what BUG-52 states:
    every test (this project's own, and this phase's own scripted
    verification) checked the DB row and the raw JSON — never a rendered,
    visible message — because none existed to check.
    **Part 3 fix**: rather than bolt a toast onto Products' "silent
    reload is fine" default, recognized *why* Users is the one case that
    needs an exception — the meaningful outcome (did the credentials
    email really arrive) is invisible in the table, unlike a new Product
    row. Every real success now carries a `message` naming the emailed
    address, extending Phase 8.99f-3's own `warning` field (mutually
    exclusive with it) rather than inventing a second signal;
    `user-form.js` reads either and `alert()`s it before the reload — the
    same mechanism already used for the warning case. Matches Users &
    Roles' own sibling actions (deactivate/reactivate), which also just
    reload with no toast on success, by *not* adding one there either —
    the fix is scoped to the one action whose success is otherwise
    unverifiable, not applied uniformly for its own sake.
    Live-verified with a real POST shaped exactly like the browser
    modal's own `fetch()` call — not a scripted DB-only check: the
    returned payload is precisely what would get `alert()`'d
    ("User created — credentials emailed to <email>."); a duplicate
    resubmit stays a clean `400` with an inline field error. 2 existing
    tests updated to assert on the message content (the old
    `assertEqual(response.json(), {'success': True})` exact-shape
    snapshot was itself part of why the gap shipped unnoticed — it never
    looked at what a person would actually see); 1 new test (the
    comment-leak regression) plus 8.99f-3's own `warning`-key test renamed
    to assert `message`-vs-`warning` mutual exclusivity instead.
    247/247 → 248/248 passing.
56. **Phase 8.99f-5: the real root cause of "works when the tool does it,
    not when I do it" (BUG-53).** Worked the 4-cause checklist in order,
    with evidence, before touching anything. Cause (1), confirmed first
    and decisively: `EMAIL_BACKEND` was the console backend — this
    session's own established practice, every prior phase (8.99f, f-3,
    f-5 itself) temporarily flips it to real SMTP to *verify* delivery,
    then reverts it to console as the resting dev state once done. A real
    admin click always runs against whatever the resting state actually
    is, so it was never seeing a real send — reproduced live: a real POST
    on the console backend returned a genuinely successful-looking
    `{"success": True, "message": "User created — credentials emailed to
    X."}`, identical in shape to a real SMTP success, because Django's
    console backend never raises — `send_mail()` "succeeds" by printing
    to whichever terminal runs the process, which is not the same claim
    as "an email left the machine," and the application code had no way
    to tell the two apart. This is why 8.99f-3/f-4's own honesty fix
    (checking `email_sent`) didn't catch it: `email_sent` was `True` in
    both cases.
    Ruled out (2) (the running process's env is only read at startup —
    not applicable, this session's own scripts are one-shot processes,
    not a long-lived `runserver`) and confirmed (3)/config genuinely
    correct via the checklist's own bare-shell isolation test:
    `send_mail()` called directly, no user-creation code involved,
    returned `1` with no exception. Gmail combination confirmed exactly
    right: port `587` + `EMAIL_USE_TLS=True` + `EMAIL_USE_SSL` unset
    (Django's own default `False`, no project override needed/present) —
    the single most common Gmail failure (587/TLS vs. 465/SSL confusion)
    doesn't apply here. One real, unplanned SMTP hiccup surfaced live
    during this phase's own verification (`WinError 10054`, a connection
    reset on the first of two back-to-back sends) — caught correctly as
    a `warning`, not a false success, which is itself a live confirmation
    the 8.99f-3 honesty fix works for a genuine, non-mocked failure.
    Fix, matched to cause (1): `UserListCreateView.post()` now checks
    `settings.EMAIL_BACKEND` and gives the console-backend case its own,
    honest `message` — "using the local console email backend (dev
    mode) — no real email was sent... configure real SMTP to actually
    deliver this email" — distinct from both the real-send `message` and
    the failed-send `warning`. No rewrite of `send_new_user_credentials_
    email()` — the bare-shell test proved that path was never the
    problem, so it was left untouched per the task's own explicit
    instruction not to fix what wasn't broken.
    **Resting-backend decision, presented and answered**: keep the
    console backend as the resting dev default (owner's choice) —
    matches this session's own established practice, and prevents
    routine dev clicks from emailing real addresses by accident; real
    SMTP stays a deliberate, occasional action. The new message makes
    that state legible instead of silently misleading.
    **Table-visibility half confirmed fine, no change needed**:
    `UserListCreateView.get()`'s queryset has no active-only filter and
    no pagination — every newly created user, regardless of role or
    status, is visible on the very next reload; confirmed by rendering
    the real page and finding the new row, not by inference.
    Live-verified end to end over real SMTP, including a genuine
    unplanned failure and a real login: two real accounts created (a
    fresh Supervisor sent twice, since the first verification account
    was deleted mid-session by the owner testing the real Delete feature
    from 8.99f-2 — confirmed via its own `USER_DELETED` audit row, not
    guessed at), both credential emails confirmed received in the real
    inbox by the owner, login with the real emailed password succeeded
    (`302` to `/dashboard/`, `check_password()` confirmed the exact
    match). Security invariant re-confirmed clean under real SMTP once
    more. 1 new test (`@override_settings`-driven, asserting the
    console-backend message's actual content, not just its presence) —
    249/249 passing (was 248). `.env` left on the console backend
    afterward, all throwaway accounts deleted.
57. **Phase 8.99f-6: close-out audit — the email thread is closed.** Not
    a new investigation; a verification pass on top of 8.99f-5's already-
    proven root cause. **Step 1 — inventory**: every email-related bug in
    `docs/bugsfound.md` (BUG-48, BUG-52, BUG-53) grepped out and checked
    individually — all three already marked ✅ Fixed in the table, and all
    three verified genuinely fixed against actual code (not just trusted):
    `StockwellPasswordResetConfirmView`/`_record_password_change()` (BUG-
    48) still present and wired; the relevant test classes
    (`PasswordResetFlowTests`, `UserManagementViewTests` — 26 tests) all
    pass. **Outcome: all-fixed, no drift found** — the 15-minute close-out
    path, not the flip-stale-entries or fix-genuinely-open path. Steps 2a/
    2b were correctly no-ops, stated as such rather than manufacturing
    work to fill them.
    **Step 3 — one regression pass, real SMTP**: a real user created
    through the real `/users/` endpoint appeared in the table on reload,
    the credentials email arrived in the real inbox (owner-confirmed), the
    account left a single clean `USER_CREATED` audit row with empty
    `details` and zero `Notification` rows. Console-backend branch
    (BUG-53's fix) re-verified live to still show its honest "dev mode, no
    real email sent" message, unchanged. One throwaway account was
    deleted prematurely mid-verification by this phase's own cleanup step
    (not the owner this time) before a login re-test could run against
    it — disclosed rather than silently worked around; login-with-a-real-
    emailed-password was not re-tested a fourth time this session, since
    it was already independently proven three separate times (8.99f,
    8.99f-3, 8.99f-5) and every other part of Step 3's checklist passed.
    **Step 4 — verdict flip + resting state**: the Phase 8.99 deploy
    gate's "3 faked in dev" paragraph (intro blockquote, above) updated —
    emailed credentials and password-reset both now read **PROVEN LOCALLY
    over real SMTP**, not DEFERRED; Phase D's remaining scope named
    explicitly as "re-confirm the same proven send against Render," not
    "first real send." Confirmed `.env`'s resting `EMAIL_BACKEND` is
    console (per 8.99f-5's owner-made choice) and stays gitignored. Found
    and closed one small, genuine gap while confirming this: `.env.example`
    had no `EMAIL_*` keys at all — not a leaked secret (there was nothing
    there), but a real discoverability gap for the next developer, since
    `docs/ENVIRONMENT.md` documents the Gmail setup but the actual env
    file template never listed the keys. Added the same 6 keys as
    placeholders (`EMAIL_BACKEND` defaulting to console, matching
    `config/settings.py`'s own default; a note pointing at
    `ENVIRONMENT.md`'s App Password steps). No code changes, no new
    tests needed (nothing new to cover — a pure audit/confirmation/doc
    phase) — 249/249 passing, unchanged from 8.99f-5.
    **The email thread (Phases 8.99f → f-6) is closed**: admin-creates-
    user delivers a real email over real SMTP, the console fallback is
    honest about being a dev-only no-send, and every email-related bug
    found along the way ends Fixed.
58. **Phase 8.99f-7: real SMTP becomes the resting default for actual
    use.** Three-way framing stated up front, all three satisfied: (1)
    real admin use delivers real email by default, (2) the test suite
    never sends real email regardless of the configured backend, (3)
    console stays available as a deliberate, one-line opt-in. Not a naive
    flip — (1) was only safe to do once (2) was proven airtight.
    **Step 1, done first, on purpose**: proved test-suite send-safety
    with real SMTP credentials genuinely present in `.env` throughout —
    directly inspected `settings.EMAIL_BACKEND` after calling
    `setup_test_environment()` (what `manage.py test` runs at startup)
    and confirmed it resolves to `locmem`, then ran the full suite the
    same way and got the identical, expected 249/249 (later 254/254). One
    test (`test_console_backend_creation_message_discloses_dev_mode`,
    8.99f-5) deliberately overrides to the *console* backend for itself
    via `@override_settings` — still fully local, prints only, never a
    real send; noted explicitly rather than left as an unexplained
    exception to "tests never send." Added an explicit belt-and-
    suspenders guard in `config/settings.py` anyway (pins `locmem` when
    `sys.argv[1] == 'test'`, before Django's own mechanism even runs) —
    redundant with Django's own reliable behavior, but makes it structural
    to this project rather than resting solely on an external library's
    behavior never being bypassed by some other future test-running path.
    **Step 2**: `.env`'s `EMAIL_BACKEND` flipped to the SMTP backend as
    the actual resting state (a `.env` change, never a `settings.py`
    hardcode — the whole point of Phase 8.99's env-driven design). BUG-
    53's console-branch honesty message is untouched, unreachable by
    default now, still fully correct for anyone who deliberately opts
    into `EMAIL_BACKEND=console...` for a session — confirmed live via
    `override_settings`. `.env.example` fixed properly, not just left
    "empty": `EMAIL_BACKEND`/`DEFAULT_FROM_EMAIL` are *omitted* rather
    than set to `KEY=` (present-but-empty) — confirmed live that
    `os.environ.get(KEY, default)` only falls through to
    `config/settings.py`'s own safe default when the key is genuinely
    *absent*; a present-but-blank value would have shadowed that default
    with an empty string and crashed on an empty backend import path. A
    real, disclosed correctness fix to what 8.99f-6 shipped, not a
    stylistic tweak.
    **Step 3 — hardening**: new `EMAIL_TIMEOUT` (default 10s, env-
    overridable) so a hung SMTP connection fails fast into the already-
    existing caught-exception path instead of blocking the request
    indefinitely. New `UserResendCredentialsView` (`AdminRequiredMixin`)
    — the missing recovery path a real-SMTP-by-default world actually
    needs: generates a fresh `generate_strong_password()` (Admin still
    never sees it), re-sends via the identical
    `send_new_user_credentials_email()`, logs a new, disclosed
    `audit.USER_CREDENTIALS_RESENT` (no password in `details=`, same
    discipline as `USER_CREATED`). The 3-way response logic
    (`UserListCreateView.post()` built across 8.99f-3/f-4/f-5) was
    factored into a shared `_credentials_email_feedback()` so the resend
    view doesn't duplicate it (§18) — both callers now read from one
    place. UI: a "Resend credentials" pill shown while `user.last_login`
    is still `None` (a real signal — Django's own field, not a new one —
    that the original credentials were never actually used), gone the
    moment they log in for real or if the account is inactive; wired via
    `row-actions.js`'s existing `postAction()`/`reportResult()` with only
    a custom `onSuccess` callback supplied (no new fetch mechanism) so the
    message/warning actually surfaces, matching the Add User form's own
    pattern. Live-verified with a real, deliberately-wrong Gmail app
    password: create → honest `warning`, not a false success; corrected
    the password → Resend succeeded with a real `message` and a real
    audit row.
    **Step 4**: `DEFAULT_FROM_EMAIL`/`EMAIL_HOST_USER` reconfirmed
    identical (Gmail rejects/flags a mismatched From — already correct
    since Phase 8.99f, just re-verified). `docs/ENVIRONMENT.md` gained a
    "Deliverability Notes" section: SPF/DKIM/DMARC and a transactional
    provider (SendGrid/Mailgun/SES) are flagged explicitly for Phase D,
    not built now — Gmail SMTP is proven and adequate for local use, but
    has real production-unsuitable limits (low daily send caps, a
    personal-account credential as the auth story) worth naming ahead of
    time rather than discovering at deploy.
    5 new tests (fresh-password-generated-and-emailed, failure returns
    `warning` not a false success, password absent from Notification/
    AuditLog on resend, Staff blocked, the `resendable` context flag's 3
    states) — 254/254 passing (was 249). Live-verified end to end: a real
    admin click with zero manual backend flip delivered a real email,
    the row appeared in the table, and the security invariant held under
    real SMTP once more.
59. **Phase 8.99f-8: the running server was reading a stale `.env`.**
    Not a code bug, and not logged as one in `docs/bugsfound.md` —
    Django reads `.env`/environment once at
    process startup, and a live `runserver` process (PID 21028) had
    started ~2.5 minutes *before* `.env`'s most recent edit, confirmed by
    directly comparing the process's `CreationDate` (`wmic`) against the
    file's `LastWriteTime`, not inferred. A fresh `manage.py shell`
    process resolved everything correctly the whole time — proving the
    SMTP config itself was never the problem, only the long-lived
    process's stale snapshot of it. Fixed by a real stop/start (not the
    autoreloader); verified via real `curl` HTTP requests (login + a real
    user-creation POST) against the actual listening process, across two
    independent full restarts, confirming it wasn't a fluke. Full suite
    (254/254) re-confirmed passing with the fresh server running
    concurrently.
60. **Phase 8.99i: Products/Categories/Suppliers get real Edit/Deactivate/
    Reactivate/Delete — Categories and Suppliers had literally none of it.**
    **Step 0 diagnosis, per module**: Products already had
    `ProductUpdateView`/`ProductDeactivateView` (Phase 8.99e) — confirmed
    working, not rebuilt; missing only `Reactivate` (8.99e scoped it out
    as optional) and a guarded true-`Delete`, both added this phase.
    Categories and Suppliers had zero view classes and zero JS handlers
    for Edit/Delete at all — plain, unwired `<button>`s left over from the
    Phase 3.6/6 mock era, confirmed by reading `category-form.js`/
    `supplier-form.js` directly (no `handleRowAction`, no click listener)
    before writing anything.
    **The `InventoryRecord` finding (Products' delete, the one genuine
    subtlety)**: `Product` is referenced by 4 real `PROTECT` FKs
    (`PurchaseOrderItem`/`SaleItem`/`InventoryMovement`/
    `InventoryAdjustment`) — the actual history check — but also by a
    5th, `InventoryRecord.product` (`OneToOneField`, also `PROTECT`),
    which *every* product has from creation (`InventoryService.
    initialize_for_product()`) regardless of whether it's ever used.
    Deliberately excluded from the history check (it's current-state
    bookkeeping, not history) but explicitly deleted as part of a
    genuinely-safe `ProductDeleteView` delete — otherwise even a brand-
    new, never-touched product's own `InventoryRecord` would block its
    own deletion. `InventoryClassification`/`DemandForecast` are `CASCADE`
    (disposable, AI-generated) and need no handling.
    **Categories/Suppliers' history checks**: a Category is deletable iff
    zero `Product.category` references it; a Supplier iff zero
    `Product.supplier` AND zero `PurchaseOrder.supplier` reference it —
    both computed as bulk `set()`s (`_category_ids_with_products()`/
    `_supplier_ids_with_history()`), mirroring `_user_ids_with_history()`/
    `_product_ids_with_history()`'s own shape: one shared computation, read
    by both the list view's own `deletable` context flag and the delete
    view's actual enforcement.
    **The "one way to change active status" decision**: `CategoryForm`/
    `SupplierForm` already had a synthetic `status` `ChoiceField` (not a
    real model field — the *create* view interprets it manually) letting
    the Add modal set initial active/inactive. Deliberately excluded from
    both new Edit modals — `is_active` only ever changes through
    Deactivate/Reactivate for all three modules now, matching Products'
    own pre-existing pattern, rather than giving Categories/Suppliers a
    second path to the same flag. `CategoryUpdateView`/`SupplierUpdateView`
    reuse their forms via `instance=` unchanged, same as `ProductUpdateView`.
    **Label/icon honesty (found while building the new Delete buttons)**:
    Products' existing Deactivate button used `icon-trash` — the *same*
    icon the new, genuine Delete buttons use everywhere — visually
    implying destruction for what's actually a reversible soft-deactivate.
    Fixed across all three modules: `icon-x` for deactivate (matching
    Purchases/Sales/Adjustments/Users' own established convention),
    `icon-trash` reserved exclusively for true delete.
    RBAC: edit stays `AnyStaffMixin` (all 3 roles) on all three modules,
    matching Products'/02_RBAC.md's existing asymmetry; deactivate/
    reactivate/delete are `SupervisorRequiredMixin` on all three, for
    consistency — 02_RBAC.md has no documented rule for Categories at all,
    so it follows its two siblings rather than inventing a third gating
    rule. 6 new, disclosed `audit.py` constants (`PRODUCT_REACTIVATED`/
    `_DELETED`, `CATEGORY_DEACTIVATED`/`_REACTIVATED`/`_DELETED`,
    `SUPPLIER_REACTIVATED`/`_DELETED` — none in `13_AUDIT.md`, same
    treatment as `USER_DELETED`/`USER_CREDENTIALS_RESENT`, §13).
    27 new tests across 3 test classes (`ProductUpdateDeactivateViewTests`
    extended; new `CategoryUpdateDeactivateViewTests`/
    `SupplierUpdateDeactivateViewTests`) covering edit persistence +
    duplicate-field rejection + is_active untouched-by-edit for all three,
    deactivate/reactivate + RBAC + picker-exclusion for all three, the
    referenced-vs-unreferenced delete branch for all three, and — Products
    specifically — the tax_rate edit-doesn't-alter-a-completed-line's-
    stored-tax snapshot guarantee (a genuinely new test; nothing before
    this phase exercised `ProductUpdateView` against an existing
    `PurchaseOrderItem`). 254/254 → 281/281 passing.
    Live-verified against the real dev DB through the actual running
    server (`curl`, not just the Django test client) for all three
    modules: create → edit → deactivate → reactivate → delete, each
    confirmed by re-querying the DB directly (including that a deleted
    product's `InventoryRecord` is genuinely gone too) — not inferred
    from a `200` alone.
61. **Phase 8.99j: dashboard decluttered, AI pages gated (BUG-43
    closed).** Small, mostly UI, with one real security fix. Removed
    "Refresh data" and "New purchase order" from the dashboard's own
    heading row — confirmed first (grepped `dashboard.js`) that neither
    button had any JS handler behind it at all, so nothing was orphaned
    by deleting the markup. "New purchase order" specifically was exactly
    the action-button class `09_DASHBOARD.md`'s own Decision 4 keeps off
    this page on purpose (actions belong in their real modules; Pending
    Approvals stays read-only, confirmed unaffected — a "View all" link
    to `/purchases/`, no Approve/Reject anywhere near it, unchanged by
    this phase) — removing it aligns the page with its own already-
    approved spec, not just tidying. Confirmed no AI content lingers
    anywhere on the dashboard to gate (Phase 8.96's own Decision 8/§4d
    already dropped the AI Insights section outright, not as a deferred
    placeholder).
    **BUG-43 closed**: `demand_forecasting`/`slow_moving_dead_stock` had
    zero auth requirement at all since Phase 8.97's audit found and
    deliberately left them unfixed. Converted both from bare function
    views to CBVs (`DemandForecastingView`/`SlowMovingDeadStockView`),
    gated `SupervisorRequiredMixin` — **a disclosed deviation from
    BUG-43's own original suggested fix** (`AnyStaffMixin`, mirroring
    BUG-42's Dashboard fix): this phase's actual, more specific
    requirement — "staff can't see the AI models" — is narrower than
    "any logged-in role," so Admin+Supervisor only is correct here, not
    the wider gate BUG-43's own text assumed would apply. Sidebar's
    "Intelligence" nav group wrapped in the identical role conditional
    Phase 8.5 established (already used one group down, for Reports) so
    the hidden-link UX layer and the actual server-side gate can't
    disagree — verified as a pair, not assumed to agree because one of
    them was changed.
    Verified live against the real dev DB, all 3 roles plus anonymous,
    by direct URL (not just checking the nav link disappeared): anonymous
    → `302` to login on both AI URLs; Staff → `302` back to the dashboard
    on a direct GET to either (the real control) and doesn't see either
    nav link or either removed dashboard button; Supervisor/Admin → both
    pages load (`200`) and both nav links render. 8 new tests
    (`AIPageAccessTests`) + 1 more on the existing `DashboardViewTests` —
    281/281 → 287/287 passing.
62. **Phase 9.5: seed_dev_data.py rebuilt into a large, deliberately-
    backdated dataset (20 products across 8 cohorts — fast/slow/dead/
    never-sold/short-history/stockout/trending — plus pending/rejected/
    cancelled records) so Phases 10/11 have real data to be right or
    wrong about.** Full reasoning and disclosure in §13 (Part A's premise
    correction, the InventoryMovement `.update()` ledger-backdating escape
    hatch, the PO/invoice-number collision-retry addition, the
    `get_sales_dataframe()` status-filter gap found in
    `DEMAND_FORECASTING.md`, and the `transaction_date`-vs-`approved_at`
    recommendation). Stock/sales still go entirely through the real
    service layer (`PurchaseService`/`SaleService`/`InventoryService`) —
    only timestamps on rows that already went through that real path are
    corrected afterward. Verified live: all 20 cohort placements land
    exactly where intended (measured against the DB, not assumed), the
    dataset's own coherence check (`approved_at` never before its
    transaction/order date, never in the future) passes, `manage.py test`
    290/290 (287 + 3 new `ExplicitDateAssignmentTests`), idempotent across
    two full flush+reseed runs, and refuses under `DEBUG=False`. Dashboard/
    Inventory/Movement History/Sales/Purchases/Reports all confirmed
    rendering correctly against the new volume (Dashboard's 6-month
    "Inventory movement" chart now shows a real curve instead of a flat
    line; Reports' Phase 8.99c "Reason" column shows real cancelled/
    rejected text).
63. **Backend Phase 10: Slow-Moving & Dead Stock Detection — real rule-
    based classifier, no ML, verified against Phase 9.5's cohorts.**
    `frontend/classification.py` (new): `calculate_average_stock()`/
    `calculate_turnover_rate()`/`get_last_sold_date()`/`classify_product()`/
    `run_full_classification()`, translated from `DEAD_STOCK_DETECTION.md`
    with a 3rd disclosed doc revision (the start-of-window fallback bug)
    and a 4th found while testing it (a real `turnover_rate` field
    overflow) — full reasoning in §13 and in the doc's own Design Notes.
    Reclassification wired as an explicit synchronous call at the end of
    `SaleService.approve_sale()`/`cancel_sale()`, not the documented
    `post_save` signal — rejected with reasoning, not just translated
    (§13). `slow_moving.html` now renders a real queryset (was an 11-row
    mock); Run button POSTs for real via `row-actions.js` + an extended
    (backward-compatible) `async-run-button.js`. Phase 8.99j's
    `SupervisorRequiredMixin` gate (BUG-43) confirmed intact, not
    re-added — both GET and POST inherit it from the class. DRF: the one
    slice Phase 9 pre-committed here (`ClassificationListAPIView`/
    `ClassificationSummaryAPIView`, `IsSupervisorOrAbove`,
    `djangorestframework` installed for the first time this phase) — no
    other endpoint touched. Verified live: all 20 Phase 9.5 cohorts
    classify exactly as intended (including the exact-60/exact-180-day
    boundary products), pending/rejected/cancelled sales confirmed
    excluded (a product's pending sale today didn't mask its real 75-179-
    day-old completed-sale classification), never-sold shows "No recorded
    sales" not `9999`, approving a pending sale reclassifies live with no
    manual Run, the Reports "AI Classification" export produces real rows
    for the first time, and `manage.py test` 312/312 (290 + 22 new).
64. **Backend Phase 11: Demand Forecasting — real pipeline
    (`frontend/forecasting.py`), the heavier of the two AI phases; the
    reference pipeline itself was revised 7 ways before any of this
    started.** `pandas`/`scikit-learn`/`joblib` installed for the first
    time (`requirements.txt`, same disclosed-gap treatment as Pillow/
    BUG-10). Implements `DEMAND_FORECASTING.md`'s current (not original
    3-tier) pipeline: `HistGradientBoostingRegressor`, chronological
    train/test split, category_id + stockout_flag features, the
    corrected multi-step lag rotation, backtest-residual confidence,
    `backfill_actual_demand()`. Found and fixed 6 real bugs while
    building against pandas 3.0.5 (a major version, installed here) and
    this project's real seeded data — none anticipated by the doc, all
    disclosed in §13: a silently-discarded datetime conversion in
    `get_sales_dataframe()`, a tz-aware/tz-naive merge failure in
    `get_stockout_flags()`, pandas 3.0's removal of the bare `'M'`
    resample alias, Phase 9.5's stockout cohort needing more pre-stockout
    runway (a seed-data fix, not a pipeline one), `run_full_forecast()`
    needing independent per-period training (a real robustness gap found
    by testing, not documented), and a cosmetic sklearn feature-name
    warning. Reclassification-equivalent wiring: none needed this
    phase — forecasting has no per-sale hook, only the manual Run.
    `forecasting.html` now renders real `DemandForecast` data (was a
    static `TREND_DATA`/table mock); Run button POSTs for real via the
    same `row-actions.js` + extended `async-run-button.js` pattern
    Phase 10 established; "How this forecast works" corrected from the
    stale 3-tier copy to the real 2-tier (skip / pooled model). Phase
    8.99j's `SupervisorRequiredMixin` gate confirmed intact, not
    re-added. DRF: the second slice Phase 9 pre-committed
    (`ForecastListAPIView`/`ForecastSummaryAPIView`), reusing Phase 10's
    one permission class — no new one added. Verified live against Phase
    9.5's cohorts: short-history and never-sold products correctly
    skipped (no row, no error), the stockout cohort's `stockout_flag`
    confirmed surviving into training features, `predict_demand()`'s
    auto-train-on-missing-file fallback proven end-to-end, backfill
    correctly leaves not-yet-elapsed forecasts alone, the Reports "AI
    Forecast" export produces real rows for the first time, and
    `manage.py test` 333/333 (312 + 21 new).
65. **Phase 11.5: expanded the Phase 9.5 seed for model quality — 20 → 43
    products, ~30 → ~55 weeks of history on every forecastable cohort, 4
    new demand-pattern cohorts (`trending_down`, `seasonal`, `steady`,
    `spiky`) added and `trending` grown from 2 → 5 products, each built
    from an explicit shape (base + trend and/or sinusoidal seasonal term +
    bounded noise) rather than a random walk.** Same seed-only ledger-
    backdating mechanism as Phase 9.5, extended not re-disclosed (§13); a
    new `_stock_and_sell()` helper replaced the old fixed two-receive
    schedule (receives now sized off each shaped series' own total
    demand). No `forecasting.py`/`classification.py`/service/model changes
    — seed data only, per this phase's explicit scope. Verified live: all
    8 original Phase 9.5 cohorts unchanged (same classification outcomes,
    same coherence/idempotency guarantees across two full flush+reseed
    runs), 40 of 43 products now forecast vs. Phase 11's 17 of 20 (the 3
    remaining skips are the same *kind* of gap — 2 never-sold, 1 short-
    history — not a new one), every patterned cohort's single-step-ahead
    forecast recovers its intended direction (trending-up/down land at/
    near their own recent average in the right direction; steady stays
    tight; spiky comes in elevated but bounded), and average confidence is
    higher for steady (0.73) than spiky (0.68), matching the residual-std
    confidence machinery's intent. `manage.py test` still 333/333 (seed
    command isn't exercised by the suite, so nothing needed updating).
    One real, unfixed finding reported separately (§13, not silently
    patched): `predict_demand()`'s recursive multi-step loop never
    advances `period_num` past the first forecasted step, which plausibly
    explains non-monotonic multi-period sequences for trending/seasonal
    products — distinct from Phase 11's already-documented tree-
    extrapolation ceiling, and only made visible by this phase's wider
    variety of longer-running patterned cohorts.
66. **Phase 12: Approval Authority Matrix — the static supervisor-or-admin
    role check becomes a policy engine ("the admin defines which
    transactions the supervisor may approve").** New `ApprovalPolicy`
    model + `frontend/approvals.py` resolver, governing
    `PurchaseService.approve()`, `AdjustmentService.approve()`/new
    `create()` (AUTO fast path), and `SaleService.cancel_sale()` — gated
    inside the service layer, not only the view. Fail-closed: no match →
    Admin, never Supervisor/Auto. Discovery found two premise gaps before
    any code was written (§13): no pre-existing PO approval ceiling
    anywhere to migrate from (seeded a fresh, user-confirmed ৳50,000 split
    instead), and `InventoryAdjustment` has no stored value/variance
    concept (both computed at resolution time). A third gap found by
    actually running the seed command: `flush` wiped the migration-seeded
    policy table every reseed, fixed via `ensure_default_policies()`. New
    `AdjustmentReason` structured reason code; new `ABCClass`/
    `recompute_abc_classes()` on `InventoryClassification` (folded into
    `run_full_classification()`, no Celery task — none exists in this
    project). Admin-only Approval Policy screen with a rule simulator and
    a best-effort "possibly unreachable rule" warning; approve/cancel
    buttons across Purchases/Adjustments/Sales now render shown-but-
    disabled with the real denial reason, never hidden. Self-approval
    blocked per-policy (admin exempt) — a deliberate, disclosed reversal
    of Phase 7/8.99b's "no creator≠approver restriction" decision.
    Proposed REQ coverage (RBAC's own doc states `REQ 2.1 → 2.12`; not
    edited — this project's docs stay historical per its own established
    convention, only project_memory.md records the extension): REQ 2.13
    (ApprovalPolicy model + resolver), 2.14 (fail-closed escalation),
    2.15 (AUTO outcome), 2.16 (self-approval blocking, admin-exempt),
    2.17 (ABC classification), 2.18 (structured adjustment reason codes),
    2.19 (admin-only policy screen + simulator), 2.20 (policy audit
    trail) — no collision with any REQ number actually cited elsewhere in
    this file (none are; REQ numbers are a docs-only convention in this
    project, not something the codebase's own history otherwise tracks).
    Verified live: 355/355 tests (333 + 22 new; 19 pre-existing tests
    updated — each called the service layer directly with a STAFF test
    user the layer never checked before Phase 12, noted inline per fix),
    AUTO path proven end-to-end (one movement, zero pending-record audit
    entries), `seed_dev_data.py` clean and idempotent at 43 products with
    the policy engine live.
67. **Phase 12.1: Approval Authority Matrix hardening.** Two corrections
    to Phase 12's own brief recorded in §13 (no PO ceiling ever existed
    before Phase 12 — nothing deprecated to remove later; no Celery, all
    recompute is manual). The "record unlock" system §3 asked to be
    hardened does not exist anywhere in this codebase (exhaustive
    discovery: models, services, views, all 7 migrations, all 66 timeline
    entries) — reported, not built; the user chose to skip it and
    document the gap rather than build a new subsystem this phase wasn't
    asked to design. Everything else implemented: `ApprovalPolicy.
    cumulative_window_days`/`cumulative_value_cap` close a real
    salami-slicing hole on the AUTO adjustment path (N sub-threshold
    adjustments no longer move unbounded stock with zero approval
    events) — new `InventoryAdjustment.resolved_policy`/`was_auto_posted`
    fields, `ADJUSTMENT_AUTO_DEFLECTED` audit trail, ৳2,000/30-day default,
    cumulative usage surfaced on the policy screen. Two fail-open
    defaults closed in the resolver: undefined variance (zero stock) now
    escalates instead of falling through (§5a); an unclassified `abc_class`
    now resolves as `'A'` (strictest) instead of Phase 12's own wrong
    `'C'` default (§5b), with ABC staleness surfaced explicitly since a
    bulk `.update()` call was found to silently bypass `auto_now`
    entirely. Swept for BUG-56 siblings (other flush-wiped, migration-
    seeded tables) — found none; the policy table is the only one.
    New standing rule recorded: authorization belongs at the service
    boundary, view mixins are defence in depth only — found one more
    unguarded case (`SaleService.approve_sale()`, the one place a sale's
    stock moves) and fixed it; four more (`PurchaseService.reject()`/
    `cancel()`, `SaleService.reject_sale()`, `AdjustmentService.reject()`)
    reported as real, listed technical debt, not fixed this phase.
    Proposed REQ coverage, continuing Phase 12's own 2.13→2.20 (RBAC's
    doc still states `REQ 2.1 → 2.12`; not edited, same historical-docs
    convention): REQ 2.21 (cumulative cap on AUTO), 2.22 (fail-closed
    variance-at-zero-stock), 2.23 (fail-closed unclassified-ABC), 2.24
    (service-boundary authorization as a standing architectural rule) —
    no collision with anything cited elsewhere in this file. Verified
    live: 363/363 tests (355 + 8 new; 9 pre-existing tests updated, every
    one because §5b's fix now routes their never-classified fixture
    product to the seeded ADMIN policy), `seed_dev_data.py` clean and
    idempotent at 43 products with both fail-closed fixes and the
    cumulative cap live, `manage.py check` clean.
68. **Phase 12.2: ABC removed from approval routing (kept for
    analytics); simulator and unreachable-rule warnings removed from the
    Approval Policies page; notification toggle removed from admin
    settings.** Started by fixing a real regression found on disk —
    `frontend/audit.py` was missing 6 constants `services.py`/`views.py`
    already imported — restored first as a blocker (own entry in
    `docs/bugsfound.md`), before any Phase 12.2 feature work. `ApprovalPolicy.
    abc_class` removed (field + 2 migrations, split across a data
    migration and a schema migration after combining them in one file
    hit a real Postgres trigger-pending error); the ABC-matching seeded
    policy row deleted; `DEFAULT_APPROVAL_POLICIES` now 9 rows, catch-all
    coverage and fail-closed-to-Admin reverified. Phase 12.1 §5b's
    "unclassified ABC resolves as 'A'" fallback and its 2 tests are gone
    with it — that rule only existed because ABC was an authority input.
    `ABCClass`/`InventoryClassification.abc_class`/`recompute_abc_classes()`/
    `abc_staleness_info()` all untouched, ABC stays real for Slow-Moving &
    Dead Stock and analytics. Approval Policies page cut down to one
    table per transaction type + add/edit/activate/deactivate — simulator,
    unreachable-rule warnings, and the cumulative-usage panel removed
    from the UI (cumulative cap enforcement itself untouched, moved to
    the bottom of the form). Removed the Notifications panel from
    `settings.html`/`SystemSettingsForm`; `email_notifications_enabled`
    stays the live gate in `notifications.py`, now frozen at its current
    DB value (Django admin is the only remaining way to change it);
    `low_stock_email_enabled` was already dead code, confirmed via grep
    before removing it from the form. Investigated the flaky-forecast-test
    report (Task 6, time-boxed): not reproducing — every forecast-training
    test class already clears `ai_models/*.joblib` in setUp/tearDown, a
    full single-process 361-test run passed clean; no change needed.
    Verified live: 361/361 tests (363 − 2 deleted ABC-fallback tests; 5
    failures surfaced by the ABC removal, all fixed — 2 ERRORs from
    tests referencing the deleted field/policy, 3 FAILs from stale
    policy-count assertions and one outcome assertion that no longer
    escalates to Admin without ABC), `manage.py check` clean. Nothing
    committed, per this phase's own instruction.
69. **BUG-57 close-out: the last four service-boundary authorization
    gaps fixed.** `PurchaseService.reject()`/`cancel()`, `SaleService.
    reject_sale()`, `AdjustmentService.reject()` now gate with the exact
    plain supervisor-or-admin check `SaleService.approve_sale()`
    established in Phase 12.1 §7 — same `ApprovalAuthorityError`, same
    placement (after the status guard, before mutation), same choice not
    to route through the `ApprovalPolicy` engine (reject/cancel were
    never in its `ApprovalTxType` scope). View-layer `SupervisorRequiredMixin`
    kept on all four; each view gained the matching `except
    ApprovalAuthorityError: status=403` clause the other approval views
    already had. Full sweep of the service layer for the same
    view-mixin-only pattern found nothing else: `InventoryService.
    increase_stock()`/`decrease_stock()` are internal primitives only
    reached from already-gated or policy-gated callers;
    `submit_for_approval()`/`receive_items()`/`create_sale()` are
    intentionally open to any staff, not a role-escalation gap. 7
    pre-existing tests had been silently exercising the gap itself (a
    STAFF fixture rejecting/cancelling and passing, because nothing
    checked) — rewritten to a supervisor actor, none deleted; a new
    direct-service denial test added per fixed method. Verified live:
    365/365 tests, `manage.py check` clean. No templates touched, no
    commit made.
70. **BUG-59: diagnosed and fixed a `ProgrammingError` on
    `/settings/approval-policies/` that looked like an incomplete ABC
    removal but wasn't.** Model, migration (0011 applied), schema
    (`information_schema.columns`), and `makemigrations --check` were
    all already consistent — `abc_class` was genuinely gone. Root cause:
    six accumulated `manage.py runserver` processes bound to the same
    port from this session's own earlier restarts, one of which still
    held pre-removal bytecode; requests landed on whichever process
    answered. Killed all six, ran with exactly one; re-verified 5/5 live
    plus a full add-policy round trip. New operational lesson recorded:
    verify the old listener is actually gone before starting a new one
    on future "restart the server" steps — this project has no process
    manager to do it automatically. Also set `LOGIN_REDIRECT_URL`/
    `LOGOUT_REDIRECT_URL` (previously unset, defaulting to Django's own
    values) — confirmed latent, not broken, since the real login/logout
    views redirect explicitly and never read either setting. 365/365
    tests unchanged, `manage.py check` clean, reseed verified clean.
71. **Phase 13: professional PDF documents + live company settings.**
    New `frontend/pdf.py` — one shared header/footer/style/currency/
    date module every PDF now renders through, replacing five
    independent ReportLab setups. `SystemSettings.company_logo` became
    a `FileField` (Pillow, which `ImageField` needs, can't open SVG) with
    a new `validate_company_logo`; added `company_tax_number`/
    `company_website`; new `get_company_profile()` accessor every PDF
    reads through. Two disclosed ReportLab-only constraints: no ৳ glyph
    in any built-in font (PDFs use "Tk"), no SVG rasterization without a
    forbidden new dependency (SVG logo falls back to text-only header,
    same as no logo). Every document gets a real header/footer
    (NumberedCanvas for accurate "Page N of M"), party block, a totals
    block reconciled via new `calculate_totals_breakdown()`
    (frontend/pricing.py), and a signature block naming the real
    approver — Phase 12/12.1's approval-authority work made visible on
    paper. New `generate_adjustment_pdf()` + `AdjustmentPDFView` (no
    per-adjustment document existed before), fixing BUG-60 (a dead "View
    adjustment" button) along the way. Reports page: Sales Report's raw
    transaction table replaced with a Chart.js revenue-by-day chart +
    status breakdown, matching the shape of the page's other cards; its
    PDF export mirrors the new aggregate shape, CSV export untouched.
    Verified live: 385/385 tests (20 new), `manage.py check` clean, a
    real Playwright round trip downloading real PDFs through the actual
    UI after a fresh reseed. Nothing left stubbed.
72. **Phase 14: three-column footer redesign (Brand / Contact Us /
    Account).** Discovery: `includes/footer.html` renders only on the
    public landing page, but that page has no auth-redirect, so an
    already-logged-in visitor is a real case, not hypothetical. First
    pass wired Brand/Contact Us to `SystemSettings.get_company_profile()`
    (adding `company_linkedin_url`) — **reversed on live user
    correction**: the footer is Stockwell's own public brand identity,
    not the per-tenant business identity Settings configures for a
    tenant's own invoices. Field/migration/form/JS all removed again;
    the already-applied dev-DB column and its orphaned
    `django_migrations` row (left behind once the migration file was
    deleted, since `makemigrations` only compares against files still on
    disk) were cleaned up directly rather than left inconsistent. Final:
    static Stockwell branding (unchanged from before), a 4-row icon
    contact list (email/phone/address/LinkedIn — new `icon-phone`/
    `icon-map-pin`/`icon-linkedin` in the shared sprite) with real email
    + placeholder phone/address/LinkedIn, and a single "Log in" link.
    `.footer-grid` narrowed 4→3 columns, collapses to 1 under 760px; dead
    `.footer-contact-card` CSS (the old single-CTA-card treatment)
    removed. Verified live at desktop/tablet/mobile, links resolve,
    LinkedIn opens `target="_blank" rel="noopener noreferrer"`,
    `manage.py check` clean, full suite unaffected.

---

## 16. Next Priorities

Highest priority first:

1. **Wire the RBAC decorator/mixin (§5, Phase 4) and the service layer
   into real module views, together, module by module** — **done, all of
   it.** Products (Phase 5), Categories, Suppliers (Phase 6), Purchases,
   Sales, Adjustments (Phase 7), Audit Log, Notifications, Users & Roles,
   Settings, Reports (Phase 8), and now Inventory (Phase 8.9 —
   `InventoryListView`, real `InventoryRecord` queryset, `AnyStaffMixin`,
   filters wired), Dashboard (Phase 8.96 — real KPIs/stats/charts/widgets
   against `docs/09_DASHBOARD.md`; Phase 8.97 — real auth gate,
   `AnyStaffMixin`), and Movement History (Phase 8.98, new — the real page
   behind Inventory's own "Movement history" button) are all real and
   correctly guarded, see §2/§5/§11/§12/§15. **Every module in the app now
   has a genuinely real, correctly-guarded view, and every visible
   Export/CSV button actually exports real data (Phase 8.98, BUG-44/45) —
   nothing mock-but-marked-done, unguarded, or decoratively dead remains
   among the app's 15 sidebar-linked pages or their sub-pages.** The one
   gap named here previously — `demand_forecasting`/`slow_moving_dead_
   stock` having no auth requirement (BUG-43) — is now closed (Phase
   8.99j, `SupervisorRequiredMixin`, both server-side and nav-link
   gating); both pages remain honestly-disclosed mock pending Phase
   10/11, only the access gate changed.
2. **Reconcile `INDEX.md`'s broken links**; write the remaining missing
   module docs (`04_SUPPLIERS.md`, `08_ADJUSTMENTS.md`, `12_SEARCH.md`,
   `14_SETTINGS.md` — `09_DASHBOARD.md` no longer belongs on this list,
   written Phase 8.95).
3. **Then** password reset (deferred from Phase 4), DRF API layer + its
   `BasePermission` classes (`02_RBAC.md`, deferred from Phase 4 — DRF
   still isn't installed), Celery (needed for the notification email
   `.delay()` upgrade — see §2 — and for `10_REPORTS.md`'s own async
   report-generation pattern, currently synchronous), and the real AI
   pipelines — in that order.

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
- **RBAC**: ✅ **mechanism done, applied everywhere it needs to be, and now
  UI-honest about it too** (Backend Phase 4 mechanism; enforcement landed
  module by module through Phase 5–8; template-level role conditionals +
  Django messages actually rendering landed Phase 8.5, see §12/§15/§16).
  Still needed: DRF `BasePermission` classes (needs DRF).
- **Products**: real CRUD — ✅ **create + list + edit + deactivate done**
  (create/list: Phase 5; edit/deactivate: Phase 8.99e — this project's
  first per-entity update route, see §13). SKU auto-generation implemented
  per `03_PRODUCTS.md`'s own documented format and disclosed as its own
  architecture decision (§13, Phase 5.5 — this bullet's "needs its own
  documented rule" gap is resolved), image upload validation done (§5).
  Edit reuses `ProductForm` unchanged via `instance=` (`AnyStaffMixin`,
  all 3 roles per 02_RBAC.md); Deactivate is the real
  `is_active = False` soft-delete `03_PRODUCTS.md` requires
  (`SupervisorRequiredMixin`, Admin/Supervisor only — an asymmetric gate
  from Edit's, both correctly applied). SKU is read-only on edit
  (disclosed, §13). Nothing still pending for Products' own CRUD —
  Reactivate + a guarded true-Delete both landed Phase 8.99i (§13/§15
  item 60).
- **Categories**: real CRUD — ✅ **done, full lifecycle** (create + list:
  Phase 6, §2/§5; edit/deactivate/reactivate/delete: Phase 8.99i, §13/§15
  item 60 — previously zero view classes and zero JS handlers existed for
  any of this, confirmed before building). Nothing still pending.
- **Suppliers**: real CRUD — ✅ **done, full lifecycle** (create + list:
  Phase 6, §2/§5; no dedicated doc exists — see §12; built from
  `SCHEMA.md` + the existing `suppliers.html` UI, reconciled per BUG-35;
  edit/deactivate/reactivate/delete: Phase 8.99i, §13/§15 item 60, same
  starting point as Categories — nothing wired at all before this phase).
  Nothing still pending.
- **Purchases/Sales/Adjustments services**: ✅ **done** (Backend Phase
  3/3.4, §2) — `PurchaseService`, `SaleService`, `AdjustmentService`, all
  with audit/notification hooks (Phase 3.5). ✅ **Now wired to real
  views/forms too** (Phase 7, §2/§5/§15) — full create + approval-workflow
  UI for all three, every stock mutation routed through the service
  layer. Still pending: edit views, PO/sale detail pages (this project
  has no per-entity detail routes anywhere yet, by design — see §13).
- **Inventory service**: ✅ **done** (Backend Phase 3/3.8, §2) —
  `InventoryService`, `select_for_update()`-safe. The list page is real
  too now (Phase 8.9, §2/§16) — read-only by design (§6/§13, still no
  create form, correctly), `AnyStaffMixin`-guarded rather than left
  unguarded like the old mock view was.
- **Dashboard**: ✅ **done** (Phase 8.95/8.96, §2/§16) — real KPI/stat/
  chart/widget aggregation against `docs/09_DASHBOARD.md` (written this
  cycle, no dedicated doc existed before), replacing every hardcoded
  number. Still open: `dashboard()` itself has no `@login_required`/RBAC
  mixin (§12 technical debt) — out of `09_DASHBOARD.md`'s approved scope,
  not silently added.
- **Reports**: ✅ **done** (Backend Phase 8, §2/§5/§15) — all 9 report
  types, PDF (ReportLab, not WeasyPrint — see §15's Phase 8 entry for why)
  + CSV export, `SupervisorRequiredMixin`-gated, every export audit-logged.
- **Notifications**: ✅ **done** (Backend Phase 8, §2/§5/§15) — real list
  page, mark-read/mark-all-read, 30s-polling topbar badge that only shows
  when something's unread. Service layer (`notify_user`/
  `notify_supervisors`) was already done since Phase 3.5; still sync email
  not Celery (§2).
- **Search** (no dedicated doc — see §12): global search, filters, AI
  classification filter per `INDEX.md`'s one-line description.
- **Audit**: ✅ **done** (Backend Phase 8, §2/§5/§15) — real, `Admin`-only
  viewer page on top of the `log_action()` service that's been recording
  since Phase 3.5.
- **Settings** (no dedicated doc — see §12): ✅ **done** (Backend Phase 8,
  §2/§5/§15) — real admin UI on the existing `SystemSettings` singleton,
  blank-falls-back-to-current-value on every optional field.
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

## Phase G — Commit and Push a Large Backlog (2026-08-16)

The last real commit before this one was `1dd31d4 Phase 8.5`; everything
from Phase 8.6 through 8.99j (and 8.99i-D) had accumulated uncommitted
across this whole session. Ran the full secret-safety checklist before
touching anything: `.env` confirmed gitignored and never committed in repo
history (zero compromise, no remediation needed); no secret in `git diff
--cached` (nothing staged yet) or in a tracked-file grep for
`EMAIL_HOST_PASSWORD`/`SECRET_KEY`/etc.; `.env.example` confirmed
placeholder-only. Found one real gap — `test-results/` (Playwright
artifacts) existed on disk, untracked, uncovered by `.gitignore` — fixed
by adding it plus `ai_models/` (Phase 11, proactive) to `.gitignore`.
`manage.py check` and the full suite (287 tests) both passed clean on the
pre-commit tree. Given the scale (63 files, ~11.3k insertions touching
nearly every core module), split-by-phase commits via `git add -p` risked
leaving an intermediate commit in a broken state that `manage.py
check`/tests can't validate in isolation — used one comprehensive commit
(`7a7272b`) with a phase-organized body instead, per the task's own
sanctioned fallback. Pushed `c2807e9..7a7272b` to `origin/main` with
nothing else queued behind it (fetch showed local exactly 1 ahead, no
divergence).

## Phase 8.99k — Real Logo + Landing Page Cleanup (2026-08-17)

Replaced the placeholder `.brand-mark` gradient box (indigo→amber CSS
gradient) with the real logo everywhere: `frontend/static/images/logo.png`
(240×272 RGBA, chroma-keyed transparent from the source PNG which had no
alpha channel — verified the source's near-white background was cleanly
separable from the artwork colors before keying, no halo). All 8 template
occurrences (`sidebar.html`, `navbar.html`, `footer.html`, `login.html`,
4×`password_reset_*.html`) now use `<img class="brand-mark" src="{% static
%}" alt="">`; the 5 auth-page duplicates were consolidated into one new
`includes/auth_brand.html` include. `.brand-mark` in `components.css` lost
its gradient background (now sizes/positions the `<img>` only). Confirmed
via `collectstatic` under `DJANGO_DEBUG=False` that `images/logo.png`
resolves through WhiteNoise's hashed manifest. Two unrelated gradients
(`.avatar-stack`, `.avatar` initials) use the same indigo→amber pattern —
left alone, they're fake-user/initials avatars, not the brand mark.

Removed all "Request a demo" content from the landing page (hero CTA,
navbar, and the whole `#contact` cta-band section + its now-orphaned
`.cta-band` CSS and the footer's dead `#contact` link) — no view/route
existed for it, so no backend cleanup was needed. Sole remaining CTAs
("See how it works", "Log in") promoted from secondary/ghost to primary
styling since they no longer sit beside a demo button.

Found and fixed a real contrast bug while assessing the "dark sections
don't fit" complaint: `--c-slate-200` (`#2d3c66`, documented in
`tokens.css` as a *border* color) was being reused as *text* color on the
ink-dark sections (ledger ticker, AI-split card, footer) — measured
contrast ~1.66:1 against `--c-ink`, far below WCAG AA. Replaced with
`color-mix(in srgb, var(--c-white) 72%, transparent)` (~9-10:1) everywhere
it was used as text-on-dark; left it alone everywhere it's used as an
actual border. This, not the dark backgrounds themselves, was the
"doesn't fit the page style" issue — the ink-dark sections use the same
token consistently and read as intentional once legible.

**User follow-up, same day**: the "keep it dark, just fix contrast" call
above was overridden — user wanted the footer and `#ai` section actually
light, the fake user-avatar circles in the hero gone, and "Contact us"
kept (using the user's real email, not a placeholder). Changes: removed
`.avatar-stack` (hero-proof circles) entirely, now-orphaned CSS deleted.
`.ai-split` background changed `--c-ink` → `--c-indigo-tint`, its "Reorder
recommendation" card reverted from translucent-dark overlay styling to
the plain light `.feature-card` treatment, all internal text back to
`--c-ink`/`--c-slate`. `.site-footer` background changed `--c-ink` →
`--c-mist` (page bg) with a `--c-slate-200` top border for separation;
footer text/links back to `--c-slate`, hover to `--c-indigo` (matching
`base.css`'s global link-hover convention). The ledger ticker's dark
background was deliberately left alone (not part of the complaint, still
a legible signature element after the earlier contrast fix). Re-added
"Contact us" as a plain `mailto:` link in both the navbar (`nav-links`,
not a button — no CTA-button demo replacement) and the footer's Company
list, addressed to the user's real email — no `#contact` section was
rebuilt, since the task only asked for a link, not the removed CTA band.

**Second follow-up, same day**: footer called "flat," navbar's "Contact
us" needed to scroll to the footer (not fire `mailto:` directly), and the
footer needed visible contact info, not just a buried link. Changes:
`footer.html` gets `id="contact"`; navbar's "Contact us" now links to
`{% url 'frontend:landing' %}#contact` instead of `mailto:`. Added a new
`icon-mail` symbol to `includes/icons.html` (reused the exact envelope
path already used inline on the login form's username field, for
consistency). Added a visible `.footer-contact-card` in the footer's
brand column — white card, mail icon, "Get in touch" + the real email as
clickable text — and removed the now-redundant "Contact us" li from the
Company link list. For "eye-catching, not flat": `.site-footer` background
changed `--c-mist` → `--c-indigo-tint` (footer no longer blends into the
page background) plus a 4px `::before` gradient accent bar
(`--c-indigo`→`--c-amber`, a callback to the original brand-mark gradient,
now repurposed as decoration). Added `scroll-margin-top: var(--header-h)`
to the general `section` rule and to `.site-footer` so anchor-scrolling
(to `#features`/`#ai`/`#contact`) isn't obscured by the sticky navbar —
this was a pre-existing gap for `#features`/`#ai` too, fixed for free.
Verified the click-to-scroll behavior with Playwright: clicking "Contact
us" lands on a fully-visible footer (it's the last element on the page,
so the browser clamps to max-scroll rather than the full scroll-margin
offset — expected, not a bug, confirmed by checking `document.scrollHeight`
against the resulting `scrollY`).

## Phase — Built-vs-Designed Documentation Audit (2026-08-24)

Report-only pass, pre-viva: grep-driven audit of every `docs/*.md` claim
against actual code, focused on the task's named suspicion areas
(scheduled/periodic claims, model fields nothing writes to, notification
types never emitted, audit constants never logged, settings fields never
read, API endpoints with no route). No code changed. Full findings in
`docs/bugsfound.md` BUG-65 → BUG-71; full detail there, not repeated here.

**Source material gap**: `requirement_analysis_doc_2.docx` doesn't exist
anywhere on the filesystem — REQ ranges were reconstructed from each doc
file's own "Requirements Coverage" header instead (REQ 4/8/11/14/17/18
unmapped — BUG-71).

**Baseline phantoms (all already fully disclosed above, this pass just
re-confirmed each is still accurate)**: PO approval ceiling — was
phantom, now real via the Phase 12 Approval Authority Matrix (§13).
Record unlock system — confirmed still fully phantom, nothing built it
(§13, "record unlock" search). `abc_class` — nuanced, not pure phantom:
real and computed for analytics (`recompute_abc_classes()`), deliberately
scoped out of approval-policy routing only (Phase 12.2, §13).
`CELERY_BEAT_SCHEDULE`/scheduled-task claims — confirmed phantom across
5 doc files (`11_NOTIFICATIONS.md`, `DEAD_STOCK_DETECTION.md`,
`DEMAND_FORECASTING.md`, `DEPLOYMENT.md`, `TECH_STACK.md`); no Celery
dependency, no `@shared_task`, no scheduler anywhere — everything AI/email
runs manually or synchronously (§2, §13 throughout).

**New findings this pass**: 9 of 66 `frontend/audit.py` action constants
are defined but never logged (BUG-65) — 2 are DRIFTED (consolidated into
a broader constant), 1 is DRIFTED (folded into the adjustment audit
trail), 6 are genuine gaps (`USER_UPDATED`/`USER_ROLE_CHANGED` because no
edit-user/change-role view exists at all; `INVENTORY_VIEWED`,
`SALE_INVOICE_PRINTED`, `LOW_STOCK_ALERT_SENT`, `OUT_OF_STOCK_ALERT_SENT`
because the real features were never wired to also write an audit row).
`SystemSettings.forecast_retrain_days` (BUG-66) and `default_reorder_level`
(BUG-67) are both admin-editable and stored but read by nothing —
changing either has zero effect. `docs/API_CONTRACTS.md` (BUG-68)
documents ~30+ REST endpoints; only 4 read-only AI endpoints actually
exist in `frontend/api_urls.py` (already known at the code level, but the
doc file itself was never corrected). `docs/TECH_STACK.md` (BUG-69)
still names Bootstrap 5.3 as the CSS framework; the real frontend is 100%
custom vanilla CSS. `docs/INDEX.md` (BUG-70) references 4 module files
and a `modules/`/`ai/`/`api/`/etc. subdirectory layout that don't exist —
every real doc file is flat under `docs/`.

**Pervasive, not re-flagged per-instance**: nearly every `docs/*.md` code
example references a multi-app `apps/<name>/` Django layout; the actual
project is a single `frontend` app throughout (already the subject of
explicit call-outs in `frontend/audit.py`'s and `frontend/approvals.py`'s
own docstrings) — a standing, deliberate divergence, not a bug.

**Prioritized recommendation (fix / remove / disclose before viva)**:
- *Fix if time allows*: BUG-65's 6 genuine audit gaps (cheap — each is
  one more `audit.log_action()` call at an existing call site).
- *Remove from docs*: BUG-68 (`API_CONTRACTS.md`'s unbuilt endpoint
  list), BUG-69 (`TECH_STACK.md`'s Bootstrap section), BUG-70
  (`INDEX.md`'s dead file/subdirectory references) — all cheap doc edits,
  no code risk.
- *Disclose as known limitation*: everything Celery/scheduler-shaped
  (already thoroughly disclosed here), `forecast_retrain_days`/
  `default_reorder_level` (BUG-66/67, cheap to fix but low-value —
  could go either way), the missing source `.docx` (BUG-71, not
  fixable by this project).

## Phase — Dead-Stock: Stagnation Index + Confidence Gating (2026-08-24)

Upgraded `classify_product()` from a single-factor recency branch to a
multi-criteria weighted expert system. Full detail in
`docs/DEAD_STOCK_DETECTION.md`'s Design Note #5 and Classification Logic
table (authoritative for the mechanism) and `docs/bugsfound.md` BUG-72/73;
this entry covers the decisions that aren't visible from the code alone.

**ABC classification removed entirely — a scope decision, not a bug.**
`ABCClass`, `InventoryClassification.abc_class`,
`SystemSettings.abc_last_recomputed_at`, `frontend.approvals.
recompute_abc_classes()`/`abc_staleness_info()`, and the ABC column +
staleness banner on `slow_moving.html` are gone, dropped in the same
migration (`0013_stagnation_index_and_abc_removal.py`) as the new
stagnation-index fields. Grepped every reference first (field,
computation, call sites, serializers, templates, report/CSV/PDF columns,
admin, tests, fixtures, seed data, docs) before deleting anything:
confirmed zero test coverage, zero serializer/report/admin exposure, and
— critically — zero mentions of "ABC" anywhere in the actual spec docs
(`docs/*.md`, excluding this project's own session-generated
`bugsfound.md`/`project_memory.md`/`CODEBASE_MAP.md`). No documented
requirement depends on it, so removing it isn't a step backwards. The
only live UI surface was the "ABC" column + staleness banner on the
Slow-Moving page — replaced with a "Stagnation index" column (same table
position), which is the honest, current answer to "why is this product
classified this way."

**Coverage factor, exactly as specified, not improvised**:
`avg_daily_demand` and the Frequency factor's `sale_event_count` both
read the same trailing-90-day window `calculate_turnover_rate()` already
used (`_total_sold()`, extracted as a shared helper both call — the same
window is now structural, not just documented). `current_stock == 0` ->
coverage 0.00 regardless of demand; `current_stock > 0` and
`avg_daily_demand == 0` -> coverage 1.00 (the core dead-stock signal);
otherwise `days_of_cover` is capped at a large ceiling *before* dividing
by `target_days_of_cover` — the same DecimalField-overflow class of bug
`calculate_turnover_rate()`'s own cap already guards against (a real
`DataError` from an earlier session).

**Weight validation**: `SystemSettings.clean()` rejects a save where the
four weights don't sum to exactly 1.00 — no silent normalisation, since a
classifier that quietly rescaled an admin's entered numbers would make
the stored weights and the weights actually driving classification
permanently diverge. Runs via `ModelForm.full_clean()`, so both the
Settings page form and Django admin's own form reject the same way with
no separate code path. Verified live through the real HTTP stack, not
just Django's test client: POSTing weights summing to 0.95 to `/settings/`
returns 400 with `"...must sum to exactly 1.00 — currently 0.95."`;
summing to 1.00 returns 200 and persists.

**`INSUFFICIENT_DATA` gate**: `stock_age_days < min_observation_days OR
sale_event_count < min_sale_events` — an OR, not an AND. Stock age
anchor is the first `InventoryMovement.created_at`, falling back to
`Product.created_at` for a product with no movement history yet. A
genuinely never-sold product (0 completed sales) now *always* lands here
under default settings (`min_sale_events=2`), never in `DEAD` — the exact
bug the old sentinel (`days_since=9999` for never-sold, immediately
`>= dead_threshold`) produced. `stagnation_index`/`confidence`/all four
factor scores are `None` for these rows (nothing was scored), but
`confidence` is still computed unconditionally — it's most informative
exactly when data is thin.

**Every surface updated for the fourth state**: `ClassificationListAPIView`
filter whitelist, `ClassificationSummaryAPIView` needed no change (already
value-driven), `SlowMovingDeadStockView`'s `_BADGE`/`counts`/`chart_data`,
`slow-moving.js`'s doughnut (4th label/dataset value/color —
`ChartColors.slate200`, muted grey, distinct from the three status
colors), `slow_moving.html`'s 4th KPI card, 4th toggle button, and the
"Classification rules" explainer panel (rewritten to describe the real
multi-factor mechanism — the old panel would otherwise have kept
describing day-threshold logic the system no longer runs, which the
prompt specifically flagged as "the worst thing for an examiner to
read"). New `.badge-neutral` CSS token (`--c-slate-100`/`--c-slate`) —
deliberately not `badge-indigo` (the generic/AI-accent fallback):
insufficient_data isn't a problem state and must not read as one.
`InventoryClassificationSerializer` also gained the new fields
(stagnation_index/confidence/four factor scores) for API-level "see why."

**BUG-72 (contradictory `days_since_last_sale`) and BUG-73 (missing audit
log on `cancel_sale()`)** — see `docs/bugsfound.md` for both; the first
is fixed at the point of write (nullable field, real value or `None`,
never a sentinel), the second mirrors `approve_sale()`'s existing
`AI_PRODUCT_RECLASSIFIED` call exactly.

**DEAD_STOCK_DETECTION.md header** now states plainly that no scheduler
exists anywhere in this project (no Celery, no cron) and reclassification
is event-driven — on sale approval/cancellation, plus manual "Run
classification now" — framed as the deliberate architecture it is, with
the honest limitation stated alongside it: nothing recomputes when a
product simply *stops* selling, since no event fires for "time passed
with no sale," so a classification can go stale between triggers. Design
Note #2 (the old "turnover doesn't actually gate classification, flagged
as a future enhancement" note) is retired as now implemented. Fixed only
in this file, per instruction — the wider five-file Celery-claim cleanup
(`11_NOTIFICATIONS.md`, `DEMAND_FORECASTING.md`, `DEPLOYMENT.md`,
`TECH_STACK.md`) is separate, already logged as BUG-CELERY-related
findings in the Task F audit above.

**Tests**: 387 -> 391 (net +4; 8 old day-boundary/never-sold-is-dead
tests removed as testing behavior that no longer exists, 12 new tests
added — insufficient_data gating, multi-factor scoring proofs, weight-sum
rejection, confidence-vs-observation-window, the BUG-72 persistence
invariant, coverage edge cases including the overflow-cap, and the
per-class-counts-sum-to-active-product-count invariant). Full suite: 391
passed. Live dev server (fresh single `runserver`, stale PID from an
earlier session killed first — same BUG-59 discipline): ran classification
against the real 43-product backdated seed dataset (fast=2, slow=31,
dead=0, insufficient_data=10, summing to 43), confirmed insufficient_data
renders in the doughnut JSON, KPI card, toggle button, and table rows on
`/ai/slow-moving/`; confirmed the Settings page renders all 9 new fields
and both the reject (0.95 sum) and accept (1.00 sum) paths live; zero
"ABC" references left on the rendered page; no 500s anywhere.

## Phase — PROMPT_1B: Index Calibration (2026-08-24)

The Prompt 2 stagnation index's first live run against real shaped seed
data produced ZERO dead-stock classifications on data known to contain
dead stock — a detection regression against the old day-threshold rule.
Full incident, root cause, and fix in `docs/bugsfound.md` BUG-74 and
`docs/DEAD_STOCK_DETECTION.md` Design Note #6 (both authoritative); this
entry covers the diagnostic process and the decisions that aren't
visible from either.

**Diagnosis (Phase 1, no code)** — broke the composite down per-product
against the live dev DB's real 43-product run: index distribution
min=27/max=54/mean=43.58/stdev=4.82 (badly compressed); the 5 products
the old 180-day rule called dead all landed in `insufficient_data`
instead of being scored; per-factor stdev showed `frequency_score` at a
literal, exact 0.000 across every scored product (mathematically
incapable of varying — the gate required `sale_event_count >=
min_sale_events` to reach that branch, and the formula was `1 -
sale_event_count/min_sale_events`, so the term could never be positive)
and `coverage_score` saturated at 1.0000 for 30/33 (clamped the instant
`days_of_cover` crossed `target_days_of_cover`). Root cause wasn't
"averaging compresses distributions" in the abstract — it was averaging
two factors that were structurally *constants*, plus a gate
(`min_sale_events`, windowed to the same 90 days as demand) that
conflated "too new to judge" with "used to sell, went dormant," diverting
every genuinely-dead product away from the index before it ever saw one.

**Phase 3 fix, three mechanisms plus a new override layer** (see
`docs/DEAD_STOCK_DETECTION.md` for the authoritative precedence table):
gate is age-only now, `sale_event_count` feeds `confidence` only;
`frequency_score` counts distinct weekly buckets (12, trailing 90 days)
with a sale instead of the formula that contradicted its own gate;
`coverage_score` ramps linearly between `target_days_of_cover` and a new
`SystemSettings.extreme_coverage_days` (default 730) instead of clamping.
Override rules (Force-DEAD/Force-SLOW/Force-FAST), evaluated on raw
signals before both the gate and the index, preserve the old rule as an
explicit floor — this is what actually guarantees no regression, not the
index fix alone (two of the five anti-regression products, Laptop Stand
and Notebook, do reach DEAD via the fixed index itself with no override
needed, which was a useful independent confirmation the index fix is
sound on its own, not just papered over by the override).

**Design review mid-implementation**: the first version of Force-SLOW had
no precondition beyond `days_of_cover >= extreme_coverage_days`, and on
re-measurement it downgraded Bluetooth Speaker from a DEAD-by-index 75 to
SLOW. Checked its actual four factor scores before accepting that as
correct: recency 0.4167, turnover 0.9578, coverage 1.0000, frequency
0.9167 — broadly stagnant on every factor, not "recent-selling-but-
drowning-in-stock" (the case Force-SLOW is actually meant to catch).
Added the precondition `stagnation_index < dead_index_threshold` to
Force-SLOW specifically (not to Force-FAST, which had no such conflict
in the diagnosed data) — a floor for extreme overstock the index might
still call fast-ish, never a ceiling on a product already independently
flagged dead. This required restructuring the override evaluation into
two stages: Force-DEAD/Force-FAST (raw signals only, run before the
index) and Force-SLOW (deferred until after the index is computed, since
its precondition needs the index value) — `_evaluate_hard_overrides()`
vs. the inline Force-SLOW check in `classify_product()`.

**Weights examined, not carried forward blind, and deliberately NOT made
variance-proportional.** Post-fix per-factor stdev: recency 0.331,
turnover 0.135, coverage 0.338, frequency 0.299 — turnover now has the
*lowest* variance despite the *second-highest* weight (0.30). Proposed
keeping the weights as policy rather than re-deriving them from this
run's statistics; user confirmed explicitly: weights encode business
policy, not a fit against one 43-product seed catalogue — turnover's
tight spread here reflects this catalogue's shape (a real SME with mixed
durables/perishables would show far more), and deriving weights from one
run's variance would be a weaker viva claim ("fit to synthetic data"),
not a stronger one. The resulting class separation (fast 21-39 / slow
43-48 / dead 75-100, both thresholds sitting cleanly in the gaps) was
also judged too clean to perturb for an unproven statistical gain.
Recorded in `docs/DEAD_STOCK_DETECTION.md` Design Note #6 as
examined-and-retained, not silently inherited.

**Re-measured distribution** (same 43-product seed set): `{fast: 28,
slow: 5, dead: 9, insufficient_data: 1}` (was `{fast: 2, slow: 31, dead:
0, insufficient_data: 10}`). Index stdev 4.82 -> 25.30. No class above
~70% (fast is largest at 65%). `insufficient_data` 23.3% -> 2.3% (the one
remaining case, Scented Candle Set, is genuinely age 20 — the intended
behaviour).

**Tests**: 391 -> 400 (net +9, all new — no renames or removals this
pass; the two Phase-4 tests whose fixtures now hit the new override
mechanism, `test_changing_a_weight_changes_classification_outcome` and
`test_pending_sale_excluded_from_last_sold_date`, were updated in place
rather than replaced). New: anti-regression by product name (all 5
diagnosed dead products, built as test fixtures matching their real
measured age/stock/days_since rather than invoking the seed script
inside a test), age-20-vs-age-300 insufficient_data/dead split,
frequency/coverage variance guards (directly re-testing the two
structurally-constant factors from the incident), override-evaluated-
before-gate, override rule text recorded, override precedence (a product
matching both a Force-DEAD condition and the Force-SLOW candidate
condition classifies DEAD, with the DEAD rule text, not the SLOW one),
and catalogue-level non-degeneracy. Full suite: 400 passed.

**Live dev server**: fresh single `runserver` (a stale PID from earlier
in this same session was found still listening and killed first — same
BUG-59 discipline, still needed even within one session). Re-ran
classification against the real 43-product seed set via the actual
"Run classification now" endpoint: `{fast: 28, slow: 5, dead: 9,
insufficient_data: 1}`, matching the offline re-measurement exactly.
`/ai/slow-moving/` renders correctly: doughnut JSON, KPI cards
(`total_flagged` = 14 = 5+9, correct), toggle, and the "Classification
rules" panel now documents both layers explicitly (override rules first,
then the age-only gate, then the weighted index) — the old panel
described only the index half, which would have been actively misleading
now that overrides exist. `flagged_by_rule` text ("No sales in 210
days") surfaces in both the main table and the "Needs attention" widget.
No 500s.

**Open item, not yet acted on**: on the current dev seed data,
`insufficient_data` holds exactly one product (Scented Candle Set, age
20). Honest — that is genuinely the only product too young to score
under the current settings — but fragile for demo purposes: one seed-data
change (a different `days_old` for that one product, or its removal)
would empty the state entirely and hide the whole `insufficient_data`
code path — badge, KPI card, toughest of the four doughnut slices,
toggle filter — from view during a walkthrough, with nothing in the UI
to indicate the path still exists. Worth widening the seed dataset later
so at least 2-3 products land there durably, rather than depending on
exactly one borderline case.

**Standing process note — BUG-03/BUG-36 has now recurred three times**
(three separate sessions each introduced a multi-line `{# #}` Django
comment, which this project's own Django version does not support
across lines and renders as visible leaked text). Most recently: Task E
(2026-08-24), in `settings.html`, in the very panel added to expose the
new weight fields — caught only because the git-push safety audit
explicitly re-grepped every touched template rather than trusting that
"I read the file, it looked fine." Reading is not sufficient for this
class of bug — the multi-line span is easy to introduce during editing
and easy to miss on a visual re-read, but trivial to catch with a
one-line regex. Worth adding either a pre-commit hook or a standing test
that scans every `frontend/templates/**/*.html` file for a `{#...#}`
span containing a newline and fails the build if one is found, rather
than relying on each session's own git-push audit to catch it after the
fact.

## Phase — Close the Audit-Log Gaps, Doc Corrections, Recovered-REQ Audit (2026-08-24)

Four-part pass against `docs/bugsfound.md` BUG-65 → BUG-71's own findings.
Full detail for every item in `docs/bugsfound.md` (BUG-65/67 updated in
place to Closed; BUG-68/69/70 updated to Closed; BUG-75 → BUG-81 new);
this entry covers the reasoning and the parts that didn't fit in the log.

**PART A — audit-log gaps.** 4 of the 6 genuine gaps closed with one
`log_action()` call each at an existing call site (`INVENTORY_VIEWED`,
`SALE_INVOICE_PRINTED`, `LOW_STOCK_ALERT_SENT`, `OUT_OF_STOCK_ALERT_SENT`
— see BUG-65). The remaining 2 (`USER_UPDATED`/`USER_ROLE_CHANGED`)
deliberately NOT closed, per instruction — no user-edit/role-change view
exists to log from, and building one was out of scope. Disclosed instead:
a comment block in `frontend/audit.py` states plainly that both
constants are unreachable, and `docs/13_AUDIT.md`'s REQ 16.3 should read
as PARTIAL, not silently implied-complete by a defined constant that
never fires. The 3 DRIFTED constants got the same disclosure treatment
(comments in `audit.py`, not new code) rather than being touched.
**Checked, not fixed:** does any settings change get audited? Yes —
`SETTINGS_UPDATED` fires on every save, but carries no `details=` payload,
so REQ 17.10's "configuration history" is PARTIAL — an event log exists
(who changed settings, when), a field-level diff does not. Reported per
instruction, not built — the user didn't ask for this one closed, only
checked.

**PART B — doc corrections (no code).** `API_CONTRACTS.md` rewritten to
the 4 real endpoints (full serializer fields, query params, verified
pagination shape) plus the one honest sentence. `TECH_STACK.md`'s
Bootstrap section replaced with a "Frontend Design System" section
documenting the real hand-built vanilla-CSS system — framed deliberately
as the stronger claim, not an apology, per instruction. `INDEX.md`
rebuilt from an actual `docs/` directory listing: flat file map (no
subdirectories), the 4 named non-existent module files gone (replaced
with a note on where those 4 features' real code lives), and 3 MORE
non-existent files caught in the rebuild that weren't in the original
finding (`MIGRATIONS.md`/`SERIALIZERS.md`/`PERMISSIONS.md`) — worth
noting: "rebuild from an actual directory listing" caught more than the
named list, which is exactly the point of doing it that way instead of
patching the 4 named entries in place. Scheduler claim corrected
consistently across all 5 files (`11_NOTIFICATIONS.md`,
`DEAD_STOCK_DETECTION.md` — already done in an earlier pass —
`DEMAND_FORECASTING.md`, `DEPLOYMENT.md`, `TECH_STACK.md`): a short
header note in each plus the literal `CELERY_BEAT_SCHEDULE` dict removed
from `DEMAND_FORECASTING.md` (the only file that had the literal block —
the others only had `@shared_task`/worker-service references, corrected
with a note rather than a full strip, since that reference code still
has value as "here's the shape if you built it"). Single-app-divergence
note added once, at the top of `INDEX.md`, ahead of every `apps/<name>/`
example a reader would otherwise hit cold — not repeated per-file.

**PART C — two settings phantoms.** `default_reorder_level` closed:
`ProductForm.clean_reorder_level()` now reads
`SystemSettings.get_settings().default_reorder_level` instead of a
hardcoded `10` — genuinely closes REQ 17.3. Test deliberately changes
the setting to a non-default value (37) so it would fail under the old
behaviour, not pass by coincidence (the setting's own default happens to
equal the old hardcoded value). `forecast_retrain_days` — already
disclosed as BUG-66, unclosable without a scheduler (which doesn't exist
and wasn't asked for) — left alone, not deleted, matching instruction:
deleting hides the gap, disclosing shows it was found.

**PART D — recovered-requirements audit.** `RECOVERED_REQUIREMENTS.md`
does not exist anywhere in the accessible filesystem — same class of gap
as BUG-71's missing `.docx` (BUG-75). Proceeded anyway on the six
highest-suspicion items' own concrete claims, each independently
verifiable against code regardless of the exact REQ wording:

- **REQ 11.9/11.10 (dashboard AI content) — PHANTOM, confirmed, cost
  reported, not built (per instruction).** The dashboard's own Phase
  8.96 comment already promised this ("returns once Phase 10/11 populate
  ... for real") and `09_DASHBOARD.md` §4d already specced the exact
  query shape. Phase 10/11 are done; nothing came back to close it.
  **Cost estimate**, by direct analogy to the three widgets already on
  the page (Stock Alerts/Pending Approvals/Recent Activity, each ~15-25
  lines of view code + a `widget-list` block in the template):
  `DashboardView.get()` needs two more queries
  (`DemandForecast.objects.order_by('-created_at')[:DASHBOARD_PREVIEW_ROWS]`,
  `InventoryClassification.objects.order_by('-classified_at')[:DASHBOARD_PREVIEW_ROWS]`
  — both already written in §4d, no design work needed) plus two more
  `widget-list` blocks in `dashboard.html` following the exact markup
  pattern the other three widgets already use. Realistic estimate: half
  a day including a live-server check, most of it template markup, not
  logic — the two queries are one-liners against tables that now have
  real rows. Left for the user to decide whether to slot in, per
  instruction.
- **REQ 14.1 (global search) — PHANTOM, confirmed.** No topbar search,
  no dedicated search view/URL, anywhere. 11 separate per-page
  client-side filters (`table-filter.js`) exist instead, each scoped to
  its own page only.
- **REQ 4.7 (supplier performance) — PHANTOM, confirmed.** No
  performance fields on `Supplier`, no `SupplierDetailView` at all to
  hang one on.
- **REQ 8.12 (adjustment history in inventory reports) — DRIFTED, not
  phantom.** The capability is real (`build_adjustment_report()`, one of
  the 9 report types), just not embedded in `build_inventory_report()`
  specifically — a sibling report, not a merged one.
- **REQ 18.12 (icon consistency, Reject/Cancel) — mostly already fixed.**
  Verified directly: `icon-circle-slash` (Reject) vs `icon-x` (Cancel)
  are distinct everywhere now, matching the already-committed BUG-55-class
  fix from earlier in this session. Smaller residual finding: `icon-x` is
  also shared with "Deactivate" across 4 pages — lower severity than the
  originally-flagged confusion, reported as its own item (BUG-80).
- **REQ 18.7 (loading indicators) — PARTIAL, confirmed.** AI run buttons
  (`AsyncRunButton`) have real loading state; report PDF/CSV exports
  (`reports.js`) are a bare `window.location.href` navigation with zero
  visual feedback.

**Verification.** New tests added alongside the 4 audit-log fixes and
the `default_reorder_level` fix (both existing test classes extended
in-place with new assertions, plus one new dedicated test) — full suite
run after all code changes; see `docs/bugsfound.md` for the pass/fail
count. Live dev server: performed each of the 4 newly-audited actions
for real (visited `/inventory/`, downloaded a sale PDF, approved a real
sale that dropped a test product to its reorder level) and confirmed all
4 new action types render on the actual `/audit-log/` list page, not
just exist in the DB.

## Phase — REQ 11.9/11.10: Dashboard AI Insights (2026-08-24)

Closed the highest-priority phantom from the built-vs-designed audit
(`docs/bugsfound.md` BUG-76): the dashboard, "the first page an examiner
opens," had no AI content despite the project's own "AI-assisted
inventory management" framing. Full technical detail in
`docs/09_DASHBOARD.md` §4d (now the authoritative spec, superseding its
own struck-through original) and `docs/bugsfound.md` BUG-76; this entry
covers the verification/design decisions that don't fit either.

**Discovery caught the spec being wrong, not just stale.** `09_DASHBOARD.md`
§4d's own re-add query shape (`DemandForecast.objects.order_by(
'-created_at')[:4]`, `InventoryClassification.objects.order_by(
'-classified_at')[:4]`) was written back when neither table had a single
row and was never re-verified once they did. Both queries run without
error — every field name is real — but neither means what a reader would
assume: `run_full_classification()` updates every active product's
`classified_at` in the same batch, so "most recently classified" is a
near-arbitrary tie-break, not a priority ordering; `DemandForecast` rows
accumulate by design (REQ 9.9), so "most recently created" returns
whatever a handful of products happened to be re-forecast last, not
products that need reordering. This is exactly the risk the task called
out explicitly ("that file documents features that were never built,
treat its specification as a proposal, not a contract") — confirmed
concretely rather than taken on faith either way.

**Reuse, not duplication — three separate places this mattered:**
1. `frontend.forecasting.latest_forecast_batch()` (new) extracted
   directly out of `DemandForecastingView._latest_batch()` (the class
   lost that private method entirely, now calls the shared function) —
   the dedup-by-latest-created-per-(product, period, period_start) logic
   now lives in exactly one place, so the dashboard widget and the
   forecasting page's own HTML table can never define "current forecast"
   two different ways.
2. Classification counts use the same `.values('classification').
   annotate(count=Count('id'))` shape `ClassificationSummaryAPIView`
   already uses, and a new test (`test_classification_counts_match_
   slow_moving_page`) asserts the dashboard's counts are literally equal
   to `/ai/slow-moving/`'s own per-classification counts, not just
   independently plausible.
3. Deliberately did NOT consume `ForecastSummaryAPIView` — its BUG-64
   aggregation defect (no dedup by run) stays open and now has zero
   consumers on the HTML side; both real UI surfaces (forecasting page,
   dashboard widget) go through `latest_forecast_batch()` instead.

**One design decision worth flagging: "needs replenishment" is weekly-only,
not both periods.** First implementation checked `forecasted_demand >
current_stock` across every latest-batch forecast regardless of period.
Live-verifying against the real 43-product seed data caught this: the
condition never fired (0 products), which on inspection wasn't a bug in
the query, it was the query being *broader* than the concept it was
supposed to represent. `run_full_forecast()`'s own `replenish_alerts`
logic — the thing that already fires a real notification for this exact
signal — restricts to weekly forecasts only, because a monthly forecast
exceeding current stock is a routine, healthy pattern for anything
restocked more than once a month, not a signal. Narrowed the widget to
match that existing, already-justified definition rather than inventing
a broader one (still legitimately "0 products need reorder" on this
seed data after the fix — verified that's the real data, not a bug, by
querying a sample directly: stock levels in this dataset are generously
above weekly demand across the board).

**Role gating**: both widgets use the identical condition Recent Activity
already established (`request.user.role in (ADMIN, SUPERVISOR)`) — chosen
specifically because both widgets link to pages already gated the same
way (`SupervisorRequiredMixin` on both `DemandForecastingView`/
`SlowMovingDeadStockView`); showing a Staff user a widget linking
somewhere they can't go would be a dead end, not an insight.

**Slot left for Step 4** (capital-at-risk ranking, per instruction): the
classification widget's priority list is a plain queryset with one sort
key (`-stagnation_index`); a comment in `DashboardView.get()` marks
exactly where a risk-value annotation or blended sort key drops in
without restructuring the widget or its template.

**Multi-line `{# #}` check** (this bug's third recurrence, most recently
in `settings.html`): grepped the one touched template
(`dashboard/dashboard.html`) with the same DOTALL regex used for the
last two checks — clean. The two new prose comments in this template use
`{% comment %}/{% endcomment %}`, not `{# #}`, specifically because they
span multiple lines; the one genuine single-line `{# #}` note (about
`flagged_by_rule`) stays on one line.

**Performance**: dashboard timed on the live dev server, 5 requests each,
warm cache, before any code changes and again after: ~0.20-0.30s ->
~0.30-0.39s. A real increase (4 more queries, all against small tables —
191 `DemandForecast` rows, 44 `InventoryClassification` rows on this
dataset) but nowhere near the 3-second budget (REQ 11.2) — not cached or
deferred, since there was nothing to justify that complexity against.

**Tests**: 401 -> 406 (net +5: one stale test retired —
`test_ai_insights_section_dropped_entirely`, whose premise was no longer
true even though its literal string assertions happened to still pass
against the new widgets' actual copy, which is worse than a clean
failure would have been — plus 6 new tests, minus the 1 retired). Full
suite passing. Live dev server: loaded the dashboard as all three roles
(Admin/Supervisor both show both widgets with real seed data; Staff
shows neither, no error) with a fresh single `runserver` each time a code
change required a restart (`--noreload`, so the process must be
restarted after every edit — caught once, when a `runserver` still
serving a pre-fix build would have quietly given a "before" reading for
an "after" check).

**Recorded for Step 4, not built now**: REQ 17.10 ("configuration
history") is PARTIAL — `SETTINGS_UPDATED` fires on every settings save
but carries no `details=` diff payload (docs/bugsfound.md BUG-65's "also
checked" note). Step 4 is expected to add
`AI_CLASSIFIER_WEIGHTS_CHANGED` with old/new values for the classifier's
own weight changes specifically. If that pattern proves out there, the
natural follow-up is extending `SETTINGS_UPDATED` itself to carry a
field-level diff (`SystemSettingsForm.changed_data`/`cleaned_data` vs.
the pre-save instance is the obvious source) — closing REQ 17.10 for
every settings field, not just classifier weights. Explicitly not built
in this pass — the plan is recorded so it isn't rediscovered from
scratch when Step 4 starts.
