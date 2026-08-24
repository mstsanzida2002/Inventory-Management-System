# Bugs Found

A complete log of every bug discovered across this project's development,
with — where applicable — the specific `docs/*.md` file and passage whose
documentation directly produced the bug when implemented faithfully.

## How to read this

Each entry has a **Source Documentation** field. Three possibilities:

- **A specific file + quoted passage** — the bug exists *because* a doc's
  own reference code, model definition, or specification was itself
  incorrect or incomplete. Implementing it exactly as written reproduces
  the bug.
- **N/A — implementation bug** — found during development but not caused
  by any documentation; a coding mistake, a CSS/browser gotcha, or a
  cross-file consistency slip introduced independently of the docs.
- **N/A — documentation gap** — no bug in running code, but the
  documentation itself is incomplete, broken, or missing in a way that
  affects development (broken links, missing files, undocumented modules).

Status legend: ✅ **Fixed** · 🚩 **Reported, not fixed** (out of scope for
the phase that found it, or deliberately deferred) · 🔧 **Self-introduced
and fixed same phase** (a bug in code written *this project*, not sourced
from any doc, caught and fixed before it shipped).

For full narrative context on any bug, see `docs/project_memory.md`
(cross-referenced by section below).

---

## Summary Table

| ID | Summary | Source Documentation | Status |
|---|---|---|---|
| BUG-01 | `.file-drop-preview[hidden]` doesn't hide (CSS cascade) | N/A — implementation bug | ✅ Fixed |
| BUG-02 | `.modal-overlay { inset: 0 }` fragile positioning | N/A — implementation bug | ✅ Fixed |
| BUG-03 | Multi-line Django `{# #}` comments leak as visible text (4 templates) | N/A — implementation bug | ✅ Fixed |
| BUG-04 | `.empty-state[hidden]` doesn't hide (same CSS cascade class as BUG-01) | N/A — implementation bug | ✅ Fixed |
| BUG-05 | `.topbar-title` overflows/overlaps icons on mobile | N/A — implementation bug | ✅ Fixed |
| BUG-06 | Login form posts to wrong URL namespace | N/A — implementation bug | ✅ Fixed |
| BUG-07 | `accounts/login.html` references undefined `form` object | Possibly `01_AUTH.md` (unconfirmed — see entry) | ✅ Fixed |
| BUG-08 | 5 sidebar links point to unregistered routes (404) | N/A — documented modules simply unbuilt, not a doc bug | ✅ Fixed (disabled) |
| BUG-09 | `landing/index.html` inlines raw SVGs instead of the shared sprite | N/A — implementation bug | ✅ Fixed |
| BUG-10 | `ImageField` used without Pillow installed | `SCHEMA.md` (§1 User, §4 Product, §13 SystemSettings — `ImageField` fields) | ✅ Fixed |
| BUG-11 | `PermissionsMixin` `related_name` clash with `auth.User` | `SCHEMA.md` §1 User (`class User(AbstractBaseUser, PermissionsMixin, ...)`) | ✅ Fixed |
| BUG-12 | `Product`/`InventoryRecord` duplicate `current_stock`/`reorder_level` | `SCHEMA.md` §4 Product + §7 InventoryRecord | 🚩 Reported |
| BUG-13 | Redundant `models.Index` on already-`unique=True` fields | `SCHEMA.md` §1 User, §4 Product | ✅ Fixed (Phase 3.4) |
| BUG-14 | `Product.category`/`Product.supplier` both `related_name='products'` | `SCHEMA.md` §4 Product | 🚩 Reported |
| BUG-15 | `InventoryClassification.classified_at` duplicates inherited `updated_at` | `SCHEMA.md` §10 InventoryClassification | 🚩 Reported |
| BUG-16 | `INDEX.md`'s File Map links to subfolders that don't exist | `INDEX.md` (entire File Map table) | 🚩 Reported |
| BUG-17 | 8 files `INDEX.md` references don't exist on disk | `INDEX.md` (File Map table) | 🚩 Reported |
| BUG-18 | `SystemSettingsAdmin.has_add_permission` DB query broke entire `/admin/` index | N/A — self-introduced this project, no doc specifies admin config | 🔧 Fixed same phase |
| BUG-19 | Deleting any `auth.User` crashes (cascade collector hits unmigrated tables) | `SCHEMA.md` (indirectly — every model's `settings.AUTH_USER_MODEL` FK) + zero migrations | ✅ Fixed (Phase 3.7) |
| BUG-20 | `InventoryMovement` "immutable ledger" is a docstring only, not code-enforced | `SCHEMA.md` §7 InventoryMovement | ✅ Fixed (Phase 3.4) |
| BUG-21 | `SystemSettings` "singleton" not enforced at the model level | `SCHEMA.md` §13 SystemSettings | ✅ Fixed (Phase 3.4) |
| BUG-22 | "System settingss" double-s typo in admin (no `verbose_name_plural`) | `SCHEMA.md` §13 SystemSettings (no verbose_name given) | ✅ Fixed (Phase 3.4) |
| BUG-23 | `SaleService`: `Decimal * float TypeError` on default discount/tax | `06_SALES.md` (`SaleService.create_sale`) | ✅ Fixed |
| BUG-24 | `PurchaseOrderItem.save()`: identical `Decimal * float TypeError` | `SCHEMA.md` §5 PurchaseOrderItem | ✅ Fixed |
| BUG-25 | `PurchaseService.cancel()` documented but missing from the doc's own code sample | `05_PURCHASES.md` (state machine + business rules vs. Service Layer code block) | ✅ Fixed (Phase 3.4) |
| BUG-26 | No `docs/08_ADJUSTMENTS.md` exists at all | `INDEX.md` references it; file missing from disk | 🚩 Reported |
| BUG-27 | `MAX_LOGIN_ATTEMPTS`/`LOCKOUT_DURATION` have no `SystemSettings` fields despite being called "configurable" | `01_AUTH.md` business rules table vs. `SCHEMA.md` §13 SystemSettings (no matching fields) | ✅ Resolved (Phase 4) |
| BUG-28 | `login_view`'s `is_active` check is unreachable dead code as written | `01_AUTH.md` (`login_view` reference code) | ✅ Fixed (Phase 4) |
| BUG-29 | `ACCOUNT_LOCKED`/`PASSWORD_CHANGED` documented as audit actions but never called in the doc's own reference code | `01_AUTH.md` (Audit Actions table vs. `login_view`/`profile_update_view` code) | ✅ Fixed (Phase 4) |
| BUG-30 | `profile_update_view`'s password change bypasses `AUTH_PASSWORD_VALIDATORS` entirely | `01_AUTH.md` (`profile_update_view` reference code) | ✅ Fixed (Phase 4) |
| BUG-31 | Product mock UI labeled Supplier optional / Unit & Reorder level required, backwards from `SCHEMA.md`/`03_PRODUCTS.md` | `SCHEMA.md` §4 Product vs. Phase 3's hand-built `products.html` modal | ✅ Fixed (Phase 5) |
| BUG-32 | `modal-form.js`'s blur handler clears a required+non-negative field's visible error even while the value is still negative | N/A — implementation bug (pre-existing in the shared modal architecture, first exercised by Phase 5's negative-price test) | 🚩 Reported (cosmetic — submit-time `validateAll()` still blocks it) |
| BUG-33 | `modal-form.js` evaluates `extraValidate()` unconditionally, even when standard field validation already failed | N/A — implementation bug (pre-existing architecture; only became costly once an `extraValidate` hook did real network work, in Phase 5) | ✅ Fixed (Phase 5.6, in the shared file) |
| BUG-34 | Product creation wrote a real `InventoryMovement` with no true cause, violating this project's own prior architecture decision | `docs/project_memory.md` §13 ("No 'Add Inventory Transaction' modal" decision) — Phase 5's own implementation | ✅ Fixed (Phase 5.5) |
| BUG-35 | Category/Supplier mock modals had fields with no schema backing (category parent/code; supplier code/city/country/postal_code/website/tax_id/notes) and mislabeled most of Supplier's genuinely-required fields as optional | `SCHEMA.md` §2 Category, §3 Supplier vs. Phase 3's hand-built `categories.html`/`suppliers.html` modals | ✅ Fixed (Phase 6) |
| BUG-36 | A multi-line Django `{# #}` comment leaked as literal text containing a `<template>` substring, which the browser parsed as a real tag and swallowed the rest of the page's body into an inert fragment | N/A — implementation bug (recurrence of BUG-03's exact root cause, in a new file, with a much worse blast radius) | ✅ Fixed (Phase 7) |
| BUG-37 | Users & Roles' search/role/status filter silently did nothing — `users.html` never loaded `table-filter.js`, even though `user-form.js` calls `TableFilter.init()`; Products/Suppliers/Purchases/Sales/Adjustments' filter controls were decorative (no script, no ids, no data-* hooks); Inventory's page was still 100% hardcoded mock underneath its controls | N/A — implementation bug | ✅ Fixed (Phase 8.6 — Users; Phase 8.7 — the other 5; Phase 8.9 — Inventory, once the real page existed to filter) |
| BUG-38 | Timestamps displayed in UTC instead of Bangladesh time everywhere, AuditLog included | N/A — implementation bug (`TIME_ZONE = 'UTC'` left at the Django default) | ✅ Fixed (Phase 8.6) |
| BUG-39 | Dashboard greeting hardcoded to "Good morning" regardless of actual time of day | N/A — implementation bug (mock-era placeholder text never made dynamic) | ✅ Fixed (Phase 8.6) |
| BUG-40 | Dashboard greeting showed "Amara" for every logged-in user — `request.user.first_name` doesn't exist on the custom `frontend.User` model, so it silently resolved empty and the `\|default:"Amara"` mock fallback fired unconditionally | `SCHEMA.md` §1 User (no `first_name` field — only `full_name`) vs. `dashboard.html`'s hand-built mock markup | ✅ Fixed (Phase 8.6) |
| BUG-41 | `project_memory.md` marked the Dashboard page ✅, but `dashboard()` passes no queryset context at all — every KPI card, both charts, and all 4 widgets are hardcoded; only the greeting/user name (BUG-39/40) are real | N/A — documentation-accuracy bug, not a code defect | ✅ Fixed (Phase 8.96 — Dashboard genuinely built against `docs/09_DASHBOARD.md`, approved Phase 8.95/8.95.1) |
| BUG-42 | `dashboard()` had no `@login_required`/RBAC mixin at all — harmless while the page was fabricated (BUG-41), a real risk once Phase 8.96 made it compute genuine business data | N/A — implementation gap, not sourced from any doc | ✅ Fixed (Phase 8.97 Part A — `AnyStaffMixin`) |
| BUG-43 | `demand_forecasting`/`slow_moving_dead_stock` views also have no auth requirement at all — same shape as BUG-42, lower severity since both pages are still 100% disclosed mock (no real data to expose) | N/A — implementation gap | ✅ Fixed (Phase 8.99j — `SupervisorRequiredMixin`, both layers: server-side gate + sidebar nav gating) |
| BUG-44 | "Export CSV"/"Export" buttons on Audit Log, Products, and Suppliers pages are decorative — no click handler, no real CSV/PDF generation, unlike Reports' genuinely-wired export (`ReportExportView`) | N/A — implementation gap, pre-existing since each page's own phase (Products/Suppliers Phase 5/6, Audit Log Phase 8) but never itemized by name until this audit | ✅ Fixed (Phase 8.98 — real CSV on all 3, plus Movement History's new export) |
| BUG-45 | Inventory's "Movement history" button (page-level and per-row) did nothing — no page existed to open | N/A — implementation gap, pre-existing since Phase 8.9 built the rest of the Inventory page around it | ✅ Fixed (Phase 8.98 — real `MovementHistoryListView`) |
| BUG-46 | `frontend/reports.py`'s `_date_bounds()` built naive datetimes and compared them against a `USE_TZ=True` `DateTimeField`, triggering a `RuntimeWarning` on every date-filtered report/export — silently correct by Django's own coercion, but noisy, and never actually exercised by any test until Phase 8.98's own new date-filtered export test | N/A — implementation gap, latent since Phase 8 (Reports), first exercised by a test in Phase 8.98 | ✅ Fixed (Phase 8.98 — `timezone.make_aware()`) |
| BUG-47 | `PurchaseOrder.order_date`/`SaleTransaction.transaction_date` (`DateField(auto_now_add=True)`) and their PO/invoice number generation read the OS clock's raw local date / raw UTC respectively, ignoring `TIME_ZONE` entirely — invisible on this project's Dhaka-clocked dev machine, would have produced wrong dates *and* wrong identifiers on a UTC production server near Dhaka midnight | N/A — implementation bug (a well-known Django `DateField.auto_now_add` gotcha, flagged but not fixed as a "related finding" inside BUG-38, Phase 8.6) | ✅ Fixed (Phase 8.99, pre-deploy blocker) |
| BUG-48 | A password changed via the "Forgot password?" email-reset flow wrote no `AuditLog` row and notified no Admin — Django's own `PasswordResetConfirmView` never goes through `change_password_view`, which is the only place those two calls lived — while the identical change made via the profile modal was fully recorded. A genuine compliance-record gap: an Admin-invisible way to change a password, invisible specifically because reset was still a disabled link when the modal (and its audit/notify calls) were built | N/A — implementation gap, not sourced from any doc (`01_AUTH.md`'s own reference `PasswordResetConfirmView` usage has no audit/notify call either — same gap, undetected because the flow itself was never finished until now) | ✅ Fixed (Phase 8.99a) |
| BUG-49 | Movement History's export silently disagreed with the page: date-range used two different comparisons between the page (`created_at__date__gte`) and the export (`_date_bounds()`'s timezone-aware range), and the export had no product/movement-type/search filtering at all — a user could filter by type on screen and export the CSV/PDF believing it reflected that filter, when it silently exported every type | `docs/project_memory.md` §2/§15 item 40, `docs/bugsfound.md` BUG-45's own Phase 8.98 entry (which documented the client-side search/type split as deliberate, not anticipating this consequence) | ✅ Fixed (Phase 8.99d) |
| BUG-50 | Sidebar notification badge (`includes/sidebar.html`) showed a hardcoded, static "6" for every user regardless of their real unread count — a Phase 3.6 mock-era literal that Phase 8's real `NotificationUnreadCountView`/topbar-bell-poll work never replaced, unlike the topbar dot it sits right next to | N/A — implementation gap, same class as BUG-37/39/40 (a mock leftover from before the page went real, never swept up when the rest of the page did) | ✅ Fixed (Phase 8.99f-2) |
| BUG-51 | A multi-line `{# #}` comment in the Add User modal (`users.html`, just above the info banner) didn't close on its own line, so it rendered as literal visible page text — the "stray lines" in the popup | N/A — implementation bug; a third occurrence of BUG-03's exact root cause (BUG-36 was the second), in a third file | ✅ Fixed (Phase 8.99f-4) |
| BUG-52 | Add User's real success path returned a bare `{"success": True}` with no user-visible confirmation — indistinguishable, from the browser, between "the credentials email really sent" and "it silently failed." The same shape as Phase 8.99f-3's stranded-account finding (a failed send and a real one looking identical), just on the happy path instead of the failure path — no Add-modal in this app has ever shown a success toast, which is fine when the new row is its own confirmation (Products) but not here, where the meaningful outcome (did the email arrive) is invisible in the table | N/A — implementation gap, not sourced from any doc | ✅ Fixed (Phase 8.99f-4) |
| BUG-53 | The Add User success message claimed "credentials emailed to X" even on the console email backend, where nothing actually leaves the machine — `send_mail()` never raises on that backend, it just prints to whichever terminal runs the Django process, so `email_sent` was `True` in exactly the same way for a real SMTP send and a local-only print. This is why the feature "worked" during this session's own scripted SMTP verification (always run with real SMTP temporarily enabled) but not for a real admin click against the resting dev environment (console by default) | N/A — implementation gap; a genuine, previously-unmodeled distinction between "the mail API didn't raise" and "an email actually left the machine" | ✅ Fixed (Phase 8.99f-5) |
| BUG-54 | `.env.example`'s `EMAIL_BACKEND`/`DEFAULT_FROM_EMAIL` were set to placeholder VALUES (`KEY=something`) rather than omitted — since `os.environ.get(KEY, default)` only falls through to `config/settings.py`'s own safe default when the key is genuinely absent, a present-but-different value there is fine, but the *intent* (a truly optional, backend-agnostic example) was undermined by hardcoding a specific backend choice into the "example" file itself, and a literal blank (`KEY=`, considered during the same fix) would have been worse — present-but-empty overrides the default with `''` and crashes on an empty backend import path. Confirmed live before fixing, not assumed | N/A — implementation gap introduced by Phase 8.99f-6's own `.env.example` addition, caught and corrected one phase later | ✅ Fixed (Phase 8.99f-7) |
| BUG-56 | `seed_dev_data.py`'s own `call_command("flush", ...)` truncates every table, including `ApprovalPolicy` — but that table was only ever seeded once, by a data migration (`0007_seed_approval_policies.py`). Every reseed after Phase 12 left the table empty, so `PurchaseService.approve()`/`AdjustmentService.approve()`/`SaleService.cancel_sale()` all failed closed to Admin on the very next seed run (correct behavior for a genuinely-unmatched transaction, wrong here — the table wasn't unmatched, it was empty) | N/A — implementation gap; a new data-migration-seeded table interacting with a pre-existing dev-only flush command neither Phase 12 nor Phase 9.5 anticipated | ✅ Fixed (Phase 12 — `frontend.approvals.ensure_default_policies()`, idempotent, called by `seed_dev_data.py` right after its own flush; the migration keeps its own frozen snapshot, not importing the evolving app module) |
| BUG-57 | Before Phase 12, `PurchaseService.approve()`/`AdjustmentService.approve()`/`SaleService.cancel_sale()` (and, until this fix, `PurchaseService.reject()`/`cancel()`, `SaleService.reject_sale()`/`approve_sale()`, `AdjustmentService.reject()`) had **zero authorization check inside the service layer** — every one of them would execute for any caller, any role, no matter who passed in as the acting user. The *only* thing preventing a STAFF user (or an unauthenticated management command, or a future API path bypassing the view entirely) from approving a purchase order or completing a sale was the view's `SupervisorRequiredMixin`/`AdminRequiredMixin` — a defence-in-depth layer that was silently doing 100% of the real work. Found by Phase 12's own test suite: 19 pre-existing tests called these methods directly with a STAFF test user and had always passed, because nothing ever checked. Phase 12.1's sweep for the same pattern found `SaleService.approve_sale()` in the same unguarded state and fixed it; the other four (`PurchaseService.reject()`/`cancel()`, `SaleService.reject_sale()`, `AdjustmentService.reject()`) were reported, not fixed, that phase | N/A — architectural gap, present since the service layer was first built (Phase 3) | ✅ Fully fixed (close-out phase): the remaining four gated with the identical plain supervisor-or-admin role check `approve_sale()` already used (same `ApprovalAuthorityError`, same check-before-mutation placement, same "view mixin stays, service check is the real boundary" shape — no second pattern invented). A codebase-wide sweep at this phase (every service method that mutates state, creates/cancels a record, or moves stock) found no further gaps: `InventoryService.increase_stock()`/`decrease_stock()` are internal primitives only ever called from already-gated methods or the AUTO adjustment path (gated by policy resolution, not a human approver, by design); `submit_for_approval()` (both services), `receive_items()`, and `create_sale()` are intentionally open to any authenticated staff (`AnyStaffMixin` in the view, no role distinction was ever intended above "logged in") — not privilege-escalation gaps. 7 pre-existing tests were calling these four methods directly with a STAFF fixture and had always silently succeeded — each rewritten to use a supervisor, and a new direct-service negative test added per method proving the unauthorized call now raises. New standing rule from Phase 12.1, now with zero known violations: authorization checks belong at the service boundary; view-layer gates are defence in depth, never the primary control. |
| BUG-55 | Products' Deactivate row pill used `icon-trash` — the same icon used everywhere else in this app for a genuine, permanent delete (Users' real Delete button, and the new Product/Category/Supplier Delete buttons built this same phase) — visually implying destruction for what's actually a reversible soft-deactivate | N/A — implementation bug, pre-existing since Phase 8.99e built the Deactivate button; only surfaced once genuine Delete buttons using the same icon existed side-by-side with it | ✅ Fixed (Phase 8.99i — `icon-x` for deactivate on all three modules, matching Purchases/Sales/Adjustments/Users' own convention; `icon-trash` reserved for true delete) |
| BUG-58 | `frontend/audit.py` was found regressed on disk — missing 6 constants (`ADJUSTMENT_AUTO_POSTED`, `ADJUSTMENT_AUTO_DEFLECTED`, `APPROVAL_POLICY_CREATED`/`UPDATED`/`DEACTIVATED`/`REACTIVATED`) that `services.py`/`views.py` already imported and called, causing 4 immediate `AttributeError` test failures. First flagged (not fixed, per that turn's own instruction to report rather than silently undo an out-of-session change) during an unrelated CSS bug-fix task; the cause of the regression itself was never identified — file history wasn't investigated, only the missing-vs-referenced diff | N/A — implementation gap; regression of unknown origin, not sourced from any doc | ✅ Fixed (Phase 12.2 Task 1 — restored by diffing every `audit.` reference across the codebase against what's defined in the file, confirmed empty diff after the fix, before any other Phase 12.2 work began) |
| BUG-59 | `/settings/approval-policies/` threw `ProgrammingError: column approval_policies.abc_class does not exist` in the browser, even though `abc_class` had genuinely been fully removed (model, migration 0011 applied, `makemigrations --check` clean, no code reference anywhere on `ApprovalPolicy`) — confirmed by hitting the same view through a fresh Django test-client process against the same dev DB, which returned 200 clean. The real cause: **six separate `manage.py runserver` processes had accumulated on `127.0.0.1:8000` across the session** (`netstat -ano` showed six PIDs LISTENING on the same port, started at six different times spanning several hours), each left running from an earlier "start the dev server" step and never stopped before the next one started. Windows allowed all six binds to coexist; each incoming request landed on whichever process's socket happened to accept it, including processes whose in-memory `ApprovalPolicy` model/view bytecode predated the Phase 12.2 `abc_class` removal — a live reproduction confirmed one specific request 500'd with exactly this error while the DB/model/migrations were already fully correct. A secondary, initially-alarming symptom (prose text — a docstring fragment — rendered at `views.py` line 2482 in the traceback) turned out to be a harmless artifact of the same root cause: the stale process's compiled bytecode had a different line-number mapping than the current file on disk, so Django's traceback renderer (which re-reads the *current* file to display source context) landed on an unrelated but syntactically valid line of `_policy_snapshot()`'s real docstring — not corrupted source, verified by reading the file directly | N/A — operational/process-hygiene gap, not a code or migration defect | ✅ Fixed (killed all six stale PIDs, started exactly one fresh `runserver`; re-verified the page 5/5 clean plus a full add-policy round trip on the sole remaining process, `python manage.py migrate` reports no pending migrations, reseed via `seed_dev_data.py` followed by another live page load both clean, full suite 365/365). Also fixed while investigating: `LOGIN_REDIRECT_URL`/`LOGOUT_REDIRECT_URL` were never set in `config/settings.py`, silently defaulting to Django's own `/accounts/profile/`/`None` — confirmed latent, not broken (the custom `frontend.views.login()`/`logout_view()` redirect explicitly by URL name and never read either setting), set anyway to `frontend:dashboard`/`frontend:login` for correctness. |
| BUG-60 | Adjustments' non-pending rows showed a "View adjustment" pill button (`icon-external`) with no `href`, no click handler, and no JS wiring anywhere in the codebase — a dead button, present since the Adjustments page was first built, that had never done anything when clicked | N/A — implementation gap, same class as BUG-44/45 (a button that looks actionable but silently does nothing) | ✅ Fixed (Phase 13, incidental to building the new per-adjustment PDF — the dead button was replaced with a real "Download PDF" link, same `pill-btn`-as-`<a>` pattern Purchases/Sales already use for their own PDF exports, rather than leaving it dead beside genuinely new PDF infrastructure) |
| BUG-61 | `predict_demand()`'s multi-step forecast loop never advanced `period_num` — every step of a multi-step forecast (`periods_ahead > 1`) fed the model the same, last-observed `period_num`, telling it every future period was the same point in time rather than 1/2/3/4 periods further out. Present in `docs/DEMAND_FORECASTING.md`'s own reference code too, and never addressed by any of the doc's 7 Design Notes revisions — revision #5 fixed a *different* problem (the old `np.roll()` scrambling `period_num` into the wrong array slot), not this one (the value in the right slot simply never changing). Confirmed empirically, not just by reading: instrumented the actual loop against a real trained model and real dev data — `period_num` fed to the model was identical across all 4 steps of a 4-step forecast | `docs/DEMAND_FORECASTING.md`'s own `predict_demand()` reference code (lines ~270-281) — the bug is in the doc's own example, faithfully translated | ✅ Fixed (`frontend/forecasting.py`'s `predict_demand()` now increments `last_row[period_num_idx]` once per loop iteration, before capturing that step's `features` — verified with a test that spies on the trained model's own `.predict()` calls and asserts `period_num` strictly increases by exactly 1 each step, not just non-decreasing) |
| BUG-62 | `run_full_forecast()` passed `SystemSettings.forecast_period_weeks` straight through as `periods_ahead` to *both* the weekly and monthly runs. The setting is weeks-denominated (its own name says so, and it's the only horizon knob exposed anywhere — form, template, serializer). With the seeded default of 4, the weekly run correctly forecast 4 weeks ahead, but the monthly run forecast 4 *months* ahead — a materially longer horizon than the setting promises, silently, with no error or warning | `docs/DEMAND_FORECASTING.md`'s own `run_demand_forecasts()` Celery-task reference code — same unconverted pass-through, faithfully translated | ✅ Fixed (converts weeks to months for the monthly run only: `periods_ahead = max(1, round(weeks / 4))`, computed once per `run_full_forecast()` call rather than adding a second `forecast_period_months` setting — the weeks setting stays the one horizon control an admin sees, matching every existing caller/serializer/template. Floored at 1 so a horizon under 2 weeks never produces a zero-length monthly run. Test: asserts the monthly run creates exactly the converted row count, not the raw weeks value) |
| BUG-63 | **OBSERVED, NOT FIXED — deliberate, out of scope for this pass.** `build_features()`'s final resample bin (the most recent week/month) is frequently a *partial* period — "this week so far," not a complete one — since resampling bins by calendar boundary regardless of whether the period has actually finished. That partial, artificially-low bin becomes `lag_1` for the very first forecast step, biasing the first prediction downward (an in-progress week that's only 2 days old looks like unusually low demand, when it's really just incomplete). Every subsequent step is less affected, since `lag_1` is overwritten by the model's own (unbiased) prior prediction from then on | N/A — design limitation inherent to calendar-boundary resampling of a still-accumulating period, present in the doc's own reference pipeline and not addressed by any of its 7 Design Notes revisions | 🚩 Logged, not fixed — a real fix (dropping the final partial bin, or scaling it up to a full-period-equivalent) changes what `build_features()` returns and what `train_model()` trains on, which is explicitly out of scope for this bug-fixing pass ("the model, features, pipeline shape... stay exactly as they are"). Documented in `docs/DEMAND_FORECASTING.md`'s Design Notes so it's discoverable, not silently left for the next person to rediscover |
| BUG-64 | **OBSERVED, NOT FIXED — out of scope for this pass.** `ForecastSummaryAPIView` (`frontend/api_views.py`) aggregates unconditionally across *every* `DemandForecast` row ever created (`count()`, `avg(confidence_score)`, distinct product count) — with no de-duplication by "latest run" the way `DemandForecastingView.get()`'s own HTML dashboard already does (`_latest_batch()`, keyed on `(product, period, period_start)`, most-recent `created_at` wins). Repeated "Run forecast now" clicks are deliberate, kept-by-design duplicates (REQ 9.9 needs historical forecast rows to compare against `actual_demand` later) — but that design's own rationale only holds for a consumer that treats vintage as meaningful, and `ForecastSummaryAPIView`'s raw aggregate doesn't: two runs 5 minutes apart share a `model_version` at day resolution and are indistinguishable in this endpoint's own output, so `total_forecasts`/`avg_confidence` skew toward whichever products got re-run most, not toward how many products are genuinely being forecast right now. No accuracy metric (MAE/MAPE comparing `forecasted_demand` to `actual_demand`) exists anywhere in the codebase — the specific "corrupts REQ 9.9 accuracy comparison" framing this was originally flagged under doesn't apply, since nothing computes that comparison at all, but the summary-count skew is real | N/A — a real gap in one specific read endpoint, not the accumulation design itself (which is sound and intentional — see `docs/DEMAND_FORECASTING.md`'s Design Notes) | 🚩 Logged, not fixed — this pass's approved scope was `period_num` (BUG-61) and the weeks/months conversion (BUG-62) only. `ForecastSummaryAPIView` would need its own dedup pass (mirroring `_latest_batch()`) to report on "the current forecast" rather than "every forecast ever made" |
| BUG-65 | **Built-vs-Designed audit finding.** `docs/13_AUDIT.md`'s "All Action Constants" list names 46 action strings (`frontend/audit.py` defines 66, having grown further since); of those, 9 are defined but never passed to `log_action()` anywhere in real (non-test) code: `INVENTORY_VIEWED`, `LOW_STOCK_ALERT_SENT`, `OUT_OF_STOCK_ALERT_SENT`, `PASSWORD_RESET_REQUESTED`, `PASSWORD_RESET_COMPLETED`, `PHYSICAL_COUNT_PERFORMED`, `SALE_INVOICE_PRINTED`, `USER_ROLE_CHANGED`, `USER_UPDATED`. Three sub-cases, verified individually rather than lumped: (1) `PASSWORD_RESET_REQUESTED`/`COMPLETED` are DRIFTED, not phantom — a password reset via the emailed link genuinely is audited (`StockwellPasswordResetConfirmView.form_valid()` calls `_record_password_change()`), just consolidated under the more general `PASSWORD_CHANGED` constant rather than these two dedicated ones, so an Admin can't filter the audit log for "reset via link" specifically. (2) `PHYSICAL_COUNT_PERFORMED` is also DRIFTED — physical counts are real, handled through `InventoryAdjustment`'s `COUNT_CORRECTION` reason code and logged under `ADJUSTMENT_REQUESTED`/`ADJUSTMENT_APPROVED` instead of a dedicated constant, because the feature was folded into the general adjustment workflow rather than built as its own flow. (3) The remaining 6 are genuinely PHANTOM: `USER_UPDATED`/`USER_ROLE_CHANGED` have no matching capability at all — `frontend/urls.py`'s `users/` routes are List/Create/Deactivate/Reactivate/Delete/Resend-credentials only, no edit-existing-user or change-role-after-creation view exists to log; `INVENTORY_VIEWED`/`SALE_INVOICE_PRINTED`/`LOW_STOCK_ALERT_SENT`/`OUT_OF_STOCK_ALERT_SENT` name real, working features (the Inventory list page, PDF invoice download, and both `Notification` alerts fire correctly) that simply were never wired to also write an `AuditLog` row alongside their existing behavior | `docs/13_AUDIT.md`'s own "All Action Constants" section (lines 61-133) names constants for capabilities/audit granularity that were never completed to match | 🚩 Logged, not fixed — report-only audit pass, no code changes made |
| BUG-66 | **Built-vs-Designed audit finding.** `SystemSettings.forecast_retrain_days` is admin-editable (present in `SystemSettingsForm`, `settings.html`, `settings-form.js`) and stored, but nothing anywhere reads it — no code path checks "has it been N days since the model was last retrained" and triggers a retrain. Retraining only ever happens manually (matches the broader no-Celery reality — see BUG baseline note on `CELERY_BEAT_SCHEDULE` below), so setting this field to e.g. `7` currently has zero behavioral effect; an admin changing it would reasonably but incorrectly believe they've configured automatic weekly retraining | N/A — documentation/implementation gap; not previously disclosed in `docs/project_memory.md` (checked — only `low_stock_email_enabled`'s dead-code status was previously logged, not this field) | 🚩 Logged, not fixed — report-only audit pass, no code changes made |
| BUG-67 | **Built-vs-Designed audit finding.** `SystemSettings.default_reorder_level` is admin-editable, stored, and shown in `admin.py`'s `list_display`, but is never consumed to prefill or default a new `Product.reorder_level` — `ProductForm`/`Product.reorder_level` use their own independent model-level `default=10`, unrelated to this setting. Changing the system-wide "default reorder level" has no effect on any product created afterward | N/A — documentation/implementation gap; not previously disclosed | 🚩 Logged, not fixed — report-only audit pass, no code changes made |
| BUG-68 | **Built-vs-Designed audit finding — documentation gap, large.** `docs/API_CONTRACTS.md` documents a full DRF REST surface (~30+ endpoints across auth, users, products, purchases, sales, inventory, adjustments, reports, notifications, dashboard, plus detail/run routes for both AI features). `frontend/api_urls.py` (the project's only DRF route file) implements exactly 4 read-only endpoints: `ai/classifications/`, `ai/classifications/summary/`, `ai/forecasts/`, `ai/forecasts/summary/`. Every other documented resource group works only as a server-rendered Django view, not a REST endpoint. This is already self-disclosed at the code level (`frontend/api_urls.py`'s own module docstring, and `docs/project_memory.md` §13) but `docs/API_CONTRACTS.md` itself was never edited to reflect it — read on its own, it still describes a full API that doesn't exist | `docs/API_CONTRACTS.md` — the file as a whole overstates the built surface; never corrected after Phases 10/11/11.5 scoped the DRF layer down to read-only AI slices | 🚩 Logged, not fixed — report-only audit pass, no code changes made |
| BUG-69 | **Built-vs-Designed audit finding — documentation gap.** `docs/TECH_STACK.md` names Bootstrap 5.3 (+ Bootstrap Icons, CDN `<link>`/`<script>` tags) as the frontend CSS framework. The actual, shipped frontend is a 100% custom vanilla-CSS design system (`tokens.css`/`components.css`/`dashboard.css`/`landing.css`) with no Bootstrap dependency anywhere in the codebase. Self-disclosed only as an aside in `docs/frontend_work.md` ("no Bootstrap despite `TECH_STACK.md`") — `TECH_STACK.md` itself was never corrected | `docs/TECH_STACK.md` line 24 and lines 267-275 | 🚩 Logged, not fixed — report-only audit pass, no code changes made |
| BUG-70 | **Built-vs-Designed audit finding — documentation gap.** `docs/INDEX.md`'s file map references `modules/04_SUPPLIERS.md`, `modules/08_ADJUSTMENTS.md`, `modules/12_SEARCH.md`, `modules/14_SETTINGS.md`, plus `ai/`, `api/`, `security/`, `setup/`, `database/`, `testing/`, `deployment/` subdirectory paths for every other file. None of these subdirectories exist — every doc file that does exist is flat under `docs/`, and those 4 specific module files don't exist at all under any path. The underlying features (Suppliers, Adjustments, Search, Settings) are all real and working in the codebase — this is a documentation-navigation gap (`INDEX.md` doesn't match the actual `docs/` layout), not a feature phantom, but it means those 4 features have no dedicated spec to audit doc-claims against | `docs/INDEX.md`'s "File Map" section | 🚩 Logged, not fixed — report-only audit pass, no code changes made |
| BUG-71 | **Built-vs-Designed audit finding — source document gap.** `requirement_analysis_doc_2.docx`, the document this audit was instructed to walk REQ 1→18 against, does not exist anywhere in the accessible filesystem (targeted search of Desktop/Documents/Downloads and the project repo; a broader filesystem search found nothing either). REQ-number ranges were instead reconstructed from each `docs/*.md` file's own embedded "Requirements Coverage" header. Ranges recovered this way: REQ 1 (`01_AUTH.md`, also REQ 15 range reused — see below), REQ 2 (`02_RBAC.md`), REQ 3 (`03_PRODUCTS.md`), REQ 5 (`05_PURCHASES.md`), REQ 6 (`06_SALES.md`), REQ 7 (`07_INVENTORY.md`), REQ 9 (`DEMAND_FORECASTING.md`), REQ 10 (`DEAD_STOCK_DETECTION.md`), REQ 12 (`10_REPORTS.md`), REQ 13 (`11_NOTIFICATIONS.md`), REQ 15 (`SECURITY.md`, overlapping `01_AUTH.md`'s own second range), REQ 16 (`13_AUDIT.md`). REQ 4, 8, 11, 14, 17, 18 could not be mapped to any surviving doc file (consistent with BUG-70's missing `04_SUPPLIERS.md`/`08_ADJUSTMENTS.md`/`12_SEARCH.md`/`14_SETTINGS.md`, though the correspondence is not confirmed since the source docx is unavailable) — their content is unknown | N/A — documentation/source-material gap | 🚩 Logged, not fixed — report-only audit pass, no code changes made |

---

## Frontend Bug-Fix Session (pre-dates this conversation's visible history — from `docs/project_memory.md` record)

### BUG-01 — `.file-drop-preview[hidden]` doesn't hide
**Root cause:** `img, svg { display: block; }` in `base.css` is an *author*
CSS rule. Author CSS always beats the browser's *User-Agent* stylesheet
rule `[hidden] { display: none; }`, regardless of specificity — this is a
cascade *origin* rule, not a specificity contest. Toggling the `hidden`
attribute on the image-preview element did nothing visually.
**Source Documentation:** N/A — implementation bug. No doc specifies this
CSS; it's a general CSS/browser gotcha.
**Status:** ✅ Fixed — added explicit `.file-drop-preview[hidden] { display: none; }`.

### BUG-02 — `.modal-overlay { inset: 0 }` fragile positioning
**Root cause:** The `inset` CSS shorthand, if unparsed/unsupported in a
given rendering context, leaves the element with no explicit offsets,
causing it to render at its DOM-flow static position instead of covering
the viewport — matching a user-reported symptom of the Add Product modal
appearing inline instead of as a popup.
**Source Documentation:** N/A — implementation bug/defensive hardening.
**Status:** ✅ Fixed — replaced with explicit `top/right/bottom/left: 0`.

### BUG-03 — Multi-line Django `{# #}` comments leak as visible text
**Root cause:** Django's `{# comment #}` tag is single-line only. Its
tokenizer regex is not `DOTALL`, so if the closing `#}` isn't on the same
line as the opening `{#`, the entire block fails to match as a comment
token and renders as literal page text instead of being stripped.
**Source Documentation:** N/A — implementation bug (Django templating
behavior, not something any project doc specifies).
**Status:** ✅ Fixed across 4 templates (`purchases.html`, `sales.html`,
`adjustments.html`, `forecasting.html`) — converted to
`{% comment %}...{% endcomment %}`.

### BUG-04 — `.empty-state[hidden]` doesn't hide
**Root cause:** Same cascade-origin class of bug as BUG-01 —
`.empty-state { display: flex; ... }` unconditionally overrides the native
`[hidden]` UA rule.
**Source Documentation:** N/A — implementation bug.
**Status:** ✅ Fixed — added `.empty-state[hidden] { display: none; }`.

### BUG-05 — `.topbar-title` overflows/overlaps icons on mobile
**Root cause:** No `white-space`/`overflow` handling existed on
`.topbar-title`; the longest title in the app ("Slow-Moving & Dead Stock")
wrapped to 3 lines at narrow viewport widths, overlapping the
notification/avatar icons in the fixed-height topbar. Pre-existing latent
bug in a shared component that no prior (shorter-titled) page had
triggered.
**Source Documentation:** N/A — implementation bug.
**Status:** ✅ Fixed — added `white-space: nowrap; overflow: hidden;
text-overflow: ellipsis;`.

---

## Frontend Bugs Fixed This Conversation

### BUG-06 — Login form posts to the wrong URL namespace
**Root cause:** `accounts/login.html`'s `<form action="{% url
'accounts:login' %}">` targeted Django's *built-in*
`django.contrib.auth.urls` login view (registered in `config/urls.py`
under the `accounts` namespace), while `includes/navbar.html`'s "Log in"
link pointed to `{% url 'frontend:login' %}` — the project's actual styled
mock page. Two different, inconsistent routes for the same feature,
introduced independently in separate work sessions.
**Source Documentation:** N/A — implementation bug; a cross-template
consistency slip, not derived from any doc.
**Status:** ✅ Fixed — form action and `includes/footer.html`'s login link
both changed to `{% url 'frontend:login' %}`, matching `navbar.html`.

### BUG-07 — `accounts/login.html` references an undefined `form` object
**Root cause:** The template contains `{% if form.non_field_errors %}` /
`form.username.errors` / `form.password.errors` conditionals, but
`frontend.views.login` calls `render(request, "accounts/login.html")`
with no context at all — `form` is always undefined, so these
conditionals silently no-op.
**Source Documentation:** Possibly `01_AUTH.md`, which documents a
complete `login_view` that *does* pass a real Django `AuthenticationForm`
into its template context — this template's structure is consistent with
that pattern. **This link is not confirmed**; it's plausible the template
was written in anticipation of `01_AUTH.md`'s documented view eventually
being implemented, but `frontend.views.login()` itself was never updated
to match. Flagged as an inference, not a verified causal chain.
**Status:** ✅ Fixed — dead conditionals removed rather than fabricating a
fake form context, since no real auth view exists yet.

### BUG-08 — 5 sidebar links point to unregistered routes (404)
**Root cause:** `includes/sidebar.html` hardcodes `href`s for Reports
(`/reports/`), Notifications (`/notifications/`), Users & Roles
(`/users/`), Audit Log (`/audit-log/`), and Settings (`/settings/`) — none
of these routes are registered in `frontend/urls.py`.
**Source Documentation:** N/A — these are genuinely documented modules
(`10_REPORTS.md`, `11_NOTIFICATIONS.md`, and `13_AUDIT.md` all exist and
are substantial specs; only a dedicated Settings doc and Users&Roles doc
are missing — see BUG-17) that simply haven't been built yet. Not a bug
caused by bad documentation — a build-progress gap. The sidebar's own
code comment already acknowledged this as a known placeholder.
**Status:** ✅ Fixed (mitigated) — converted from live `<a href>` 404s to
disabled, non-navigable `<span class="nav-item-disabled">` elements.

### BUG-09 — `landing/index.html` inlines raw SVGs instead of the shared sprite
**Root cause:** Every other page includes `includes/icons.html` (the
shared `<symbol>` sprite) and references icons via `<use href="#icon-*">`.
`landing/index.html` never included the sprite at all and instead inlined
5 raw `<svg>` elements with hand-written paths.
**Source Documentation:** N/A — implementation bug; a consistency lapse,
not derived from any doc (there is no formal spec mandating sprite reuse,
just the established project convention).
**Status:** ✅ Fixed — converted to `<use href="#icon-*">` against 5
existing sprite symbols (`icon-package-check`, `icon-receipt`,
`icon-sliders`, `icon-clock`, `icon-trending-up`), and added the missing
`{% include "includes/icons.html" %}`.

---

## Backend Phase 1 — Database Models

### BUG-10 — `ImageField` used without Pillow installed
**Root cause:** `SCHEMA.md` documents `ImageField` on 3 models
(`User.profile_image`, `Product.image`, `SystemSettings.company_logo`).
Django's `ImageField` hard-requires the Pillow package to even pass
`manage.py check` (`fields.E210` otherwise) — Pillow was not in
`requirements.txt`.
**Source Documentation:**
```
SCHEMA.md §1 User:          profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)
SCHEMA.md §4 Product:       image = models.ImageField(upload_to='products/', blank=True, null=True)
SCHEMA.md §13 SystemSettings: company_logo = models.ImageField(upload_to='company/', blank=True, null=True)
```
`TECH_STACK.md` never separately lists Pillow as a dependency, even though
it's an unavoidable consequence of using `ImageField` anywhere.
**Status:** ✅ Fixed — installed `Pillow==12.3.0`, added to `requirements.txt`.

### BUG-11 — `PermissionsMixin` `related_name` clash with `auth.User`
**Root cause:** `PermissionsMixin` (inherited by the new `User` model)
hardcodes `related_name="user_set"` for both `groups` and
`user_permissions` — not parametrized by app or class name. Since
`django.contrib.auth`'s own `User` model is still loaded (it's a required
built-in app, and `AUTH_USER_MODEL` hasn't been switched — see
`docs/project_memory.md` §5), two concrete models both used
`PermissionsMixin` simultaneously, clashing on the same reverse-accessor
name (`fields.E304` on `manage.py check`).
**Source Documentation:**
```
SCHEMA.md §1 User:
class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    ...
```
SCHEMA.md specifies `PermissionsMixin` as a base class but never shows
`groups`/`user_permissions` overrides — implementing the class exactly as
written, in an environment where `django.contrib.auth` is still active,
produces this clash. This is a well-known, standard Django gotcha for any
custom-user-model project, not specific to this codebase.
**Status:** ✅ Fixed — added explicit `related_name` overrides
(`frontend_user_set`, `frontend_user_permissions_set`) on `User.groups`/
`user_permissions`. Renames a reverse accessor only; no schema-shape change.
**Follow-up (Phase 3.7):** this fix only addressed the `related_name`
clash symptom — `AUTH_USER_MODEL` itself was still unset, exactly as this
writeup's root cause described, confirmed live (`settings.AUTH_USER_MODEL`
== `'auth.User'`, every cross-model FK resolved to
`django.contrib.auth.models.User`). Now actually switched to
`'frontend.User'`; see BUG-19 for the migration/db reset that went with it.

### BUG-12 — `Product`/`InventoryRecord` duplicate `current_stock`/`reorder_level`
**Root cause:** Both models independently define `current_stock` and
`reorder_level` fields with no documented relationship between them (is
one a denormalized cache of the other? Which is authoritative?).
**Source Documentation:**
```
SCHEMA.md §4 Product:
    reorder_level   = models.PositiveIntegerField(default=10)
    current_stock   = models.PositiveIntegerField(default=0)   # updated by inventory service

SCHEMA.md §7 InventoryRecord:
    current_stock   = models.PositiveIntegerField(default=0)
    reorder_level   = models.PositiveIntegerField(default=10)
```
**Status:** 🚩 Reported, not fixed — implemented literally as documented
per Phase 1 scope ("do not add/remove fields not explicitly documented").
Confirmed still in sync in practice: `InventoryService` (Phase 3) updates
both `InventoryRecord.current_stock` and syncs `Product.current_stock` on
every mutation — but nothing in the schema itself *enforces* that they
can't drift apart.

### BUG-13 — Redundant `models.Index` on already-`unique=True` fields
**Root cause:** `User.email`, `Product.sku`, and `Product.barcode` are all
declared `unique=True` (which already creates a DB-level unique index) but
also carry a separate, explicit `models.Index` entry on the same field —
a harmless but redundant duplicate index.
**Source Documentation:**
```
SCHEMA.md §1 User:    email = models.EmailField(unique=True)   ... indexes = [models.Index(fields=['email']), ...]
SCHEMA.md §4 Product: sku = models.CharField(..., unique=True) ... indexes = [models.Index(fields=['sku']), models.Index(fields=['barcode']), ...]
```
**Status:** ✅ Fixed (Phase 3.4) — the redundant `models.Index` entries
removed from `User.email`/`Product.sku`/`Product.barcode`'s `Meta.indexes`
(the `unique=True` constraint's own index is untouched, still enforced).
Confirmed live via `SCHEMA.md`'s Phase 3.4 model diff.

### BUG-14 — `Product.category`/`Product.supplier` both `related_name='products'`
**Root cause:** Both FKs use the identical `related_name`. Harmless in
practice (they're reverse accessors on two *different* models —
`Category.products` and `Supplier.products` — so there's no actual
collision), but reads like an unintentional copy-paste in the schema doc.
**Source Documentation:**
```
SCHEMA.md §4 Product:
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.PROTECT, related_name='products')
```
**Status:** 🚩 Reported, not fixed — implemented literally as documented.

### BUG-15 — `InventoryClassification.classified_at` duplicates inherited `updated_at`
**Root cause:** `InventoryClassification` inherits `TimeStampedModel`
(which already provides `updated_at = models.DateTimeField(auto_now=True)`)
but also declares its own `classified_at = models.DateTimeField(auto_now=True)`
— functionally identical, redundant field.
**Source Documentation:**
```
SCHEMA.md §10 InventoryClassification:
    classified_at = models.DateTimeField(auto_now=True)
```
**Status:** 🚩 Reported, not fixed — implemented literally as documented.

### BUG-16 — `INDEX.md`'s File Map links to subfolders that don't exist
**Root cause:** `INDEX.md`'s entire File Map table links every doc as if
it lived inside a subfolder (`setup/TECH_STACK.md`, `database/SCHEMA.md`,
`modules/01_AUTH.md`, `ai/DEMAND_FORECASTING.md`, `api/API_CONTRACTS.md`,
`security/SECURITY.md`, `testing/TESTING.md`,
`deployment/DEPLOYMENT.md`), but `docs/` is, and always has been, a
completely flat directory. Every single link in that table is broken as
written.
**Source Documentation:** `INDEX.md`, File Map table (all rows).
**Status:** 🚩 Reported, not fixed — a docs-only defect; either the links
need flattening or the files need moving into the referenced subfolders.

### BUG-17 — 8 files `INDEX.md` references don't exist on disk
**Root cause:** `INDEX.md` links to `database/MIGRATIONS.md`,
`modules/04_SUPPLIERS.md`, `modules/08_ADJUSTMENTS.md`,
`modules/09_DASHBOARD.md`, `modules/12_SEARCH.md`,
`modules/14_SETTINGS.md`, `api/SERIALIZERS.md`, and `api/PERMISSIONS.md`
— none of these files exist anywhere in the repo, at any path.
**Source Documentation:** `INDEX.md`, File Map table.
**Status:** 🚩 Reported, not fixed. Practical consequence: any task
touching Suppliers, Adjustments, Dashboard, Search, Settings, serializer
patterns, or DRF permission classes has no dedicated spec — this is
exactly why `AdjustmentService` (Phase 3, BUG-26) had to be designed from
first principles instead of a documented spec.

---

## Backend Phase 2 — Django Admin

### BUG-18 — `SystemSettingsAdmin.has_add_permission` DB query broke the entire `/admin/` index
**Root cause:** To enforce the (documented-but-unenforced, see BUG-21)
`SystemSettings` singleton at the admin layer, `has_add_permission` was
written to call `SystemSettings.objects.exists()`. Django calls
`has_add_permission` for **every** registered model on **every** admin
page load (to decide whether to render "Add" links in the sidebar/index),
not just when that model's own add view is visited — so this one query
took down the entire `/admin/` index page with a 500, not just the
SystemSettings page.
**Source Documentation:** N/A — self-introduced. No doc specifies any
admin-layer singleton enforcement at all (see BUG-21); this bug was
entirely a product of the mitigation code written this project, and was
found and fixed within the same phase, before it could ship.
**Status:** 🔧 Fixed same phase — wrapped the query in
`try/except DatabaseError`, failing open.

### BUG-19 — Deleting any `auth.User` crashes
**Root cause:** Django's cascade-delete collector walks *every* reverse
FK pointing at `settings.AUTH_USER_MODEL` before permitting a delete. That
now includes every Phase 1 model's `created_by`/`approved_by`/
`performed_by`/`requested_by`/`recipient`/`user` FK — and since
`frontend`'s tables don't exist yet (zero migrations applied to the real
DB), the collector crashes trying to query them
(`OperationalError: no such table`). Deleting a user account — an
operation completely unrelated to the new schema — is now broken as
collateral damage.
**Source Documentation:** Indirectly `SCHEMA.md` — every one of these FKs
is written exactly as documented (`models.ForeignKey(settings.AUTH_USER_MODEL, ...)`
appears in `PurchaseOrder`, `SaleTransaction`, `InventoryMovement`,
`InventoryAdjustment`, `Notification`, `AuditLog`). The bug isn't a doc
defect — it's an emergent interaction between correctly-implemented
SCHEMA.md FKs and the deliberately-deferred migration state (see
`docs/project_memory.md` §16 for why migrations were deferred).
**Status:** ✅ Fixed (Phase 3.7) — resolved exactly as predicted, by
applying migrations to the real database (as part of the `AUTH_USER_MODEL`
switch, BUG-11). Re-verified live: created and deleted a throwaway
`frontend.User` with no crash.

### BUG-20 — `InventoryMovement` "immutable ledger" is a docstring only, not code-enforced
**Root cause:** `InventoryMovement`'s docstring states "Immutable ledger —
never update or delete," but unlike `AuditLog` (which overrides `save()`/
`delete()` to raise `PermissionError`), `InventoryMovement` has no such
enforcement in code. Nothing stops a direct mutation outside the admin
layer.
**Source Documentation:**
```
SCHEMA.md §7 InventoryMovement:
class InventoryMovement(TimeStampedModel):
    """Immutable ledger — never update or delete."""
    ...
    # (no save()/delete() override — contrast with AuditLog below)

SCHEMA.md §12 AuditLog:
    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("AuditLog records are immutable and cannot be modified.")
        super().save(*args, **kwargs)
    def delete(self, *args, **kwargs):
        raise PermissionError("AuditLog records cannot be deleted.")
```
SCHEMA.md documents the identical invariant for two models but only
provides enforcement code for one of them.
**Status:** ✅ Fixed (Phase 3.4) — `InventoryMovement.save()`/`delete()`
now override and raise `PermissionError`, mirroring `AuditLog` exactly.
The admin-layer mitigation (`has_change_permission`/`has_delete_permission`
disabled) is still in place too, but the enforcement is now real at the
model level — direct ORM code can no longer mutate it either.

### BUG-21 — `SystemSettings` "singleton" not enforced at the model level
**Root cause:** `SystemSettings` is documented as a singleton via
`get_settings()` (`get_or_create(pk=1)`), but that's a *convention*, not a
*constraint* — nothing on the model itself (no overridden `save()`, no
unique trick) prevents `SystemSettings.objects.create(...)` from making a
second row.
**Source Documentation:**
```
SCHEMA.md §13 SystemSettings:
    """Singleton — only one row should ever exist."""
    ...
    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
```
The docstring asserts the invariant; no code in the class body enforces it.
**Status:** ✅ Fixed (Phase 3.4) — `SystemSettings.save()` now forces
`self.pk = 1` before every save, so no caller (ORM, admin, or otherwise)
can ever produce a second row: a plain instantiate+save() converges onto
row 1, and a second `.objects.create()` raises `IntegrityError` instead of
silently duplicating. The admin-layer mitigation (BUG-18's
`has_add_permission` guard) is still in place too, but the invariant is
now real at the model level, not just at `/admin/`.

### BUG-22 — "System settingss" double-s typo in admin
**Root cause:** `SystemSettings` has no `verbose_name`/`verbose_name_plural`
set in its `Meta`, so Django's default auto-pluralization (appending "s"
to the auto-derived verbose name "System settings") renders "System
settingss" in the admin index.
**Source Documentation:** `SCHEMA.md` §13 SystemSettings `Meta` block
(`db_table` only, no `verbose_name`/`verbose_name_plural` given).
**Status:** ✅ Fixed (Phase 3.4) — `models.py` was in scope for this later
phase (it was Phase 2's admin-only scope that excluded it, not
permanently off-limits). `Meta.verbose_name`/`verbose_name_plural` both
set to `'System Settings'`; confirmed live via
`SystemSettings._meta.verbose_name_plural` — `/admin/` now reads "System
Settings", not "System settingss".

---

## Backend Phase 3 — Service Layer

### BUG-23 — `SaleService`: `Decimal * float` `TypeError` on default discount/tax
**Root cause:** `item.get('discount', 0)` defaults to plain Python `int 0`
when a line item omits a discount. `0 / 100` in Python 3 produces a
`float` (`0.0`), and `Decimal * float` raises `TypeError` — so
`SaleService.create_sale()` crashed on the single most common case: a
sale line with no discount or tax specified.
**Source Documentation:**
```
06_SALES.md, Service Layer, SaleService.create_sale:
    line_total = (item['unit_price'] * item['quantity']) \
                 * (1 - item.get('discount', 0) / 100) \
                 * (1 + item.get('tax', 0) / 100)
```
Implemented exactly as documented; the bug ships with the doc's own
reference code.
**Status:** ✅ Fixed — `frontend/services.py` coerces `discount`/`tax` to
`Decimal(str(...))` before dividing, preserving the documented formula's
behavior while making it actually run.

### BUG-24 — `PurchaseOrderItem.save()`: identical `Decimal * float TypeError`
**Root cause:** The exact same bug as BUG-23, in a different file:
`discount`/`tax` fields default to `0` (int), and `self.discount / 100`
produces a `float`. This one is more severe — it lives in `models.py`
itself, meaning **any** `PurchaseOrderItem.save()` call with a default
(no-discount) line item crashes, not just a service-layer code path.
**Source Documentation:**
```
SCHEMA.md §5 PurchaseOrderItem:
    discount        = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax             = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ...
    def save(self, *args, **kwargs):
        self.line_total = (self.unit_price * self.ordered_qty) * (1 - self.discount/100) * (1 + self.tax/100)
        super().save(*args, **kwargs)
```
Implemented verbatim in Phase 1 exactly as SCHEMA.md specifies; the bug
ships with the doc's own reference code.
**Status:** ✅ Fixed (Phase 3, with explicit user confirmation before
touching `models.py`, since prior phases treated it as settled) —
`Decimal(str(self.discount))`/`Decimal(str(self.tax))` coercion added
before the division. No schema/migration change; behavior-only fix.

### BUG-25 — `PurchaseService.cancel()` documented but missing from the doc's own code sample
**Root cause:** `05_PURCHASES.md`'s state machine diagram explicitly shows
"any state → CANCELLED," and its business-rules table states "Cancelled
PO does NOT affect inventory" — but the doc's own `PurchaseService` code
block only implements `submit_for_approval`, `approve`, `reject`, and
`receive_items`. No `cancel()` method appears anywhere in the reference
code.
**Source Documentation:**
```
05_PURCHASES.md, PO Workflow (State Machine):
    Any state ──(cancel by admin/supervisor)──► CANCELLED

05_PURCHASES.md, Business Rules table:
    | Cancelled PO | Does NOT affect inventory |

05_PURCHASES.md, Service Layer:
    class PurchaseService:
        # submit_for_approval, approve, reject, receive_items only —
        # no cancel() method defined anywhere in this code block.
```
**Status:** ✅ Fixed (Phase 3.4) — `PurchaseService.cancel()` implemented:
enforced against `_CANCELLABLE_STATUSES`, pure status change with no
`InventoryService` call from any prior state (including PARTIAL — stock
already received via `receive_items()` stays received, matching "does NOT
affect inventory" literally). Since no `cancel()` reference code existed
to copy, the implementation follows the state-machine diagram and
business-rules table instead — the two places in the doc that actually
agreed. Logs via `audit.PO_CANCELLED` but does not notify (no
`po_cancelled` notification type is documented in `11_NOTIFICATIONS.md`
either — matched literally, not an oversight). Covered by
`PurchaseCancelTests` (draft/pending/approved/partial, plus rejection of
already-received/already-cancelled).

### BUG-26 — No `docs/08_ADJUSTMENTS.md` exists at all
**Root cause:** `INDEX.md`'s File Map lists `modules/08_ADJUSTMENTS.md`
("Inventory Adjustments | Requests, approvals, audit trail"), but no such
file exists anywhere in `docs/` (confirmed during Backend Phase 1 —
see BUG-17 — and again during Phase 3 when `AdjustmentService` needed a
spec to follow).
**Source Documentation:** `INDEX.md`, File Map table, row 8. File itself:
missing.
**Status:** 🚩 Reported (duplicate of BUG-17, called out again here since
it directly blocked Phase 3). `AdjustmentService`'s shape
(`approve`/`reject` only, no `submit_for_approval`, mirroring
`PurchaseService`) was derived from the `InventoryAdjustment` model shape
in `SCHEMA.md` §8 plus this task's own explicit instruction — not guessed
business rules, but also not backed by a dedicated spec the way Purchases
and Sales are.

### BUG-27 — `MAX_LOGIN_ATTEMPTS`/`LOCKOUT_DURATION` have no `SystemSettings` fields
**Root cause:** `01_AUTH.md`'s business rules table describes account
lockout thresholds as "configurable" (twice — once for the attempt count,
once for the duration), which reads as a `SystemSettings`-managed value
matching the pattern used for `session_timeout_seconds` right next to it
in the same table. But `SCHEMA.md` §13 `SystemSettings` has no matching
fields at all — only `ENVIRONMENT.md` documents these two as env vars
(`MAX_LOGIN_ATTEMPTS`, `LOCKOUT_DURATION`).
**Source Documentation:**
```
01_AUTH.md, Business Rules table:
    | Account lockout | Temporary lock after N consecutive failed logins (configurable, default 5) |
    | Lockout duration | Configurable (default 300 seconds) |

SCHEMA.md §13 SystemSettings: no max_login_attempts/lockout_duration field anywhere.

ENVIRONMENT.md, .env.example:
    MAX_LOGIN_ATTEMPTS=5
    LOCKOUT_DURATION=300
```
**Status:** ✅ Resolved (Phase 4) — used as env vars per `ENVIRONMENT.md`
(`config/settings.py` reads `MAX_LOGIN_ATTEMPTS`/`LOCKOUT_DURATION` via
`os.environ.get`, defaulting to 5/300), since that's the only source that
actually defines them anywhere. No `SystemSettings` fields added to work
around the gap — this task's own instruction was explicit about that.

### BUG-28 — `login_view`'s `is_active` check is unreachable dead code
**Root cause:** The reference code calls `authenticate()`, then — only if
it returned a real user — checks `if not user.is_active`. Django's
default `ModelBackend.authenticate()` already refuses to authenticate an
inactive user internally (`user_can_authenticate()` checks
`is_active` and returns `None` otherwise), so a non-`None` `user` from
`authenticate()` is *already* guaranteed active. The `is_active` branch,
placed after that point, can never execute as written.
**Source Documentation:**
```
01_AUTH.md, login_view:
    user = authenticate(request, username=user_obj.username, password=password)
    if user is None:
        ...
    if not user.is_active:   # unreachable: authenticate() already filtered this out
        messages.error(request, 'Your account is inactive. Contact administrator.')
        ...
```
**Status:** ✅ Fixed (Phase 4) — moved the `is_active` check to before
`authenticate()` is called (right after the lockout check), so a
deactivated account gets the correct, specific message. This also fixes
a secondary correctness issue the dead code masked: with the check
unreachable, a deactivated user entering their *correct* password would
have fallen into the `user is None` branch instead (since `authenticate()`
returns `None` for them too) and had their `failed_login_attempts`
incremented for a login that wasn't actually their mistake.

### BUG-29 — `ACCOUNT_LOCKED`/`PASSWORD_CHANGED` documented but never called
**Root cause:** `01_AUTH.md`'s own "Audit Actions for This Module" table
lists both `ACCOUNT_LOCKED` ("Account locked after max attempts") and
`PASSWORD_CHANGED` ("User changes password") as real action constants.
Neither reference-code snippet in the same document actually calls
`log_action()` with either one — `login_view` only ever logs
`LOGIN_FAILED`, even on the specific attempt that triggers a lock;
`profile_update_view` calls `notify_user()` for a password change but
never calls `log_action()` for it at all.
**Source Documentation:**
```
01_AUTH.md, Audit Actions table:
    | ACCOUNT_LOCKED | Account locked after max attempts |
    | PASSWORD_CHANGED | User changes password |

01_AUTH.md, login_view: only ever calls log_action(..., 'LOGIN_FAILED', ...).
01_AUTH.md, profile_update_view: calls notify_user(...) for password change,
    never log_action(..., 'PASSWORD_CHANGED', ...).
```
**Status:** ✅ Fixed (Phase 4) — both now actually called: `ACCOUNT_LOCKED`
fires alongside `LOGIN_FAILED` specifically on the attempt that triggers a
lock; `PASSWORD_CHANGED` fires whenever `profile_view`'s password-change
branch succeeds. This task's own deliverables list named both
explicitly, so this wasn't a judgment call — the doc's action table won
over its incomplete example code.

### BUG-30 — `profile_update_view`'s password change bypasses `AUTH_PASSWORD_VALIDATORS`
**Root cause:** The reference code calls `user.set_password(new_password)`
directly from `request.POST`, with no call to Django's
`validate_password()` anywhere in the path. Every validator in
`AUTH_PASSWORD_VALIDATORS` — including `SECURITY.md`'s own
`StrongPasswordValidator` — is silently skipped for this one code path,
even though the same document lists password policy as a hard security
requirement.
**Source Documentation:**
```
01_AUTH.md, profile_update_view:
    new_password = request.POST.get('new_password')
    if new_password:
        user.set_password(new_password)   # no validate_password() call anywhere
        user.save()
```
**Status:** ✅ Fixed (Phase 4) — `django.contrib.auth.password_validation.
validate_password(new_password, user)` is now called first; a
`ValidationError` is caught and its messages surfaced the same way any
other validator failure would be, before `set_password()` ever runs.

### BUG-31 — Product mock UI's optional/required labels didn't match the schema
**Root cause:** `SCHEMA.md`'s `Product.supplier` FK has no `blank=True`
(and `03_PRODUCTS.md`'s business rules table says "Supplier | Required,
must be active"), but the Phase 3 mock modal labeled it "(optional)" with
a "No supplier assigned" default option. `unit`/`reorder_level` have
model-level `default=`s but, like every other field, no `blank=True` —
Django's `ModelForm` makes a field required based on `blank`, not on
whether it has a default, so both would have been wrongly required by a
literal `ModelForm` despite the mock UI already (correctly, as it turns
out) treating them as optional-with-a-fallback.
**Source Documentation:** `SCHEMA.md` §4 Product vs. the mock
`products/products.html` built earlier in the project, before any backend
enforcement existed to catch the mismatch.
**Status:** ✅ Fixed (Phase 5) — Supplier's label/options updated to
required, matching the schema; `unit`/`reorder_level` made explicitly
optional on `ProductForm` with a `clean_*` fallback to the same default
the model itself declares (`PIECE` / `10`).

### BUG-32 — `modal-form.js`'s blur handler can clear a still-invalid field's error
**Root cause:** For a field in both `requiredFieldIds` and
`nonNegativeFieldIds` (e.g. Purchase price), `modal-form.js` wires
`validateRequired` to `blur` and `validateNonNegative` to `input`. Typing
a negative number fires `input` and correctly shows "cannot be negative."
But moving focus to the *next* field fires `blur` on this one, which
re-runs only `validateRequired` — and since the field is non-empty, that
call clears the error, even though the value is still negative.
**Source Documentation:** N/A — implementation bug in `modal-form.js`/
`form-validation.js` (shared architecture, unchanged since it was first
built for the Product modal). Pre-existing; Phase 5 is simply the first
time a negative-value-then-tab-away sequence was actually tested.
**Status:** 🚩 Reported, not fixed — this phase's brief kept
`modal-form.js`/`form-validation.js` exactly as-is. Cosmetic only:
`validateAll()` re-checks non-negativity at submit time regardless of
what's currently displayed, so a still-negative value cannot actually be
submitted — confirmed live (see `docs/project_memory.md` §15 Phase 5
verification notes).

### BUG-33 — `modal-form.js` runs `extraValidate()` even when standard validation already failed
**Root cause:** The submit handler computes
`isStandardValid = validateAll()` and
`isExtraValid = config.extraValidate()` as two unconditional statements,
then combines them — `extraValidate()` always runs, even on an obviously
invalid submit (e.g. every required field still empty). Harmless for
Purchase/Sale's line-items check (pure client-side), but Phase 5's
`extraValidate` performs the real product-creation request, so this meant
a real (synchronous, main-thread-blocking) server round-trip on every
submit click, not just valid-looking ones.
**Source Documentation:** N/A — implementation bug in `modal-form.js`
(shared architecture, unchanged since Purchase/Sale first added
`extraValidate` for line-items).
**Status:** ✅ Worked around (Phase 5) — `product-form.js`'s
`extraValidate` now checks for any `.has-error` field left by
`validateAll()` and returns `false` immediately without touching the
network if one exists, rather than changing `modal-form.js` itself.
**Update (Phase 5.5):** moot for Products specifically — `onSubmit` is
only ever called *after* `validateAll()`/`extraValidate()` both already
passed (it's inside modal-form.js's own `if (!isStandardValid ||
!isExtraValid) return;` gate), so moving the real request from
`extraValidate` into `onSubmit` (needed anyway for BUG-34/the async fix,
see below) structurally eliminates the wasted-request problem for this
form — the `.has-error` workaround was deleted, not carried forward. At
this point the underlying characteristic in `modal-form.js`
(`extraValidate()` itself still evaluates unconditionally) was still
unchanged and would still have bitten any future module that puts
expensive work directly in `extraValidate` instead of `onSubmit`.
**Fixed for real (Phase 5.6):** `extraValidate()` is now short-circuited
behind `isStandardValid` —
`isExtraValid = isStandardValid && (config.extraValidate ? config.extraValidate() : true)`
— so it never runs at all once a required/non-negative field has already
failed, in `modal-form.js` itself, for every module. Verified live with a
call-counting wrapper around `LineItems.validate()` (the concrete
`extraValidate` every current Purchase/Sale form uses): with Purchase's
required Supplier field left empty, the call count stayed at 0 after
submit (previously would have been 1); filling it in brought the count to
1, confirming `extraValidate` still runs normally once standard
validation passes. Sale's form has no `requiredFieldIds` configured at
all, so there was nothing to gate against — confirmed its call count is
unchanged (still 1 per submit attempt) either way, i.e. no regression.
Products no longer uses `extraValidate` at all (Phase 5.5), so this fix
is invisible to it. Scope was `modal-form.js` only — no per-entity file
needed to change, which is exactly the point: every module's `extraValidate`
is correct now, including ones Phase 7 hasn't written yet.

### BUG-34 — Product creation wrote a real `InventoryMovement` with no true cause
**Root cause:** Phase 5's `ProductListCreateView.post()` called
`InventoryService.increase_stock(product, quantity=<initial_stock from
the form>, movement_type=MovementType.ADJUSTMENT, ...)` for every new
product, to satisfy the Phase 3 mock UI's pre-existing "Initial stock"
field. `increase_stock()`'s entire contract — enforced by every other
call site in the project — is "log a real movement with a real cause";
`MovementType` only has 4 documented values (purchase/sale/adjustment/
return), none of which describe "a catalog entry was created," and
`ADJUSTMENT` was chosen only because it was the least-wrong of the four,
not because it was accurate. Creating a product means a catalog entry
now exists — it does not mean physical stock arrived, which only
happens for real once a Purchase Order is received. This directly
violated a decision this project had already made and written down for
itself: `docs/project_memory.md` §13's "No 'Add Inventory Transaction'
modal" entry, present since before Phase 5, explicitly states every
inventory endpoint is GET-only and `InventoryMovement` rows are created
only as an internal side effect of purchase-receive/sale/
adjustment-approval — never via a direct user form. Phase 5 built
exactly the direct-user-form path that decision had already ruled out,
without cross-checking against it.
**Source Documentation:**
```
docs/project_memory.md §13 (pre-existing, written before Phase 5):
    "No 'Add Inventory Transaction' modal... every inventory endpoint
    is documented as GET-only, and InventoryMovement rows are explicitly
    described as created only as an internal side effect of
    purchase-receive/sale/adjustment-approval — never via a direct user
    form."

frontend/views.py, ProductListCreateView.post() (Phase 5, before the fix):
    InventoryService.increase_stock(
        product=product, quantity=form.cleaned_data["initial_stock"],
        movement_type=MovementType.ADJUSTMENT, reference_type="Product",
        reference_id=product.pk, performed_by=request.user,
        notes="Initial stock recorded at product creation.",
    )

03_PRODUCTS.md's own product_create_view, by contrast, creates
InventoryRecord with the implied current_stock=0 default and nothing
else — no quantity parameter, no movement, matching the §13 decision.
```
**Status:** ✅ Fixed (Phase 5.5). Presented as an explicit decision
rather than resolved silently, since the Add Product modal's "Initial
stock" field implied an undocumented "onboard with existing stock"
workflow with no support in `03_PRODUCTS.md`/`07_INVENTORY.md`/
`SCHEMA.md` — chose to remove the field entirely (over adding a 5th
documented `MovementType`) so every product's first real stock arrives
the same way every other module's stock does: through a received
Purchase Order. `frontend/services.py` gained
`InventoryService.initialize_for_product(product)` — creates the
`InventoryRecord` at `current_stock=0` (reusing
`InventoryRecord.update_status()` for a correctly-computed `out_of_stock`
status) and writes **no** `InventoryMovement` row, since a zero-to-zero
change is not a movement. Kept as its own method rather than calling
`increase_stock(quantity=0)`, since that method's contract (write a real
movement) doesn't apply here regardless of quantity. The 3 Phase 5 test
products that had gone through the old path — with their now-incorrectly-
labeled `InventoryMovement`/`AuditLog` rows — were deleted from the dev
DB rather than left in place; fresh verification products were created
through the corrected path instead (see
`docs/project_memory.md` §15, Phase 5.5 entry).

### BUG-35 — Category/Supplier mock modals didn't match SCHEMA.md
**Root cause:** Same class of bug as BUG-31, found applying the identical
scrutiny to two more modules. Two directions of mismatch:
1. **Fields with no schema backing.** `categories.html`'s mock modal had
   "Parent category" (a full hierarchy — `Category` has no self-FK
   anywhere in `SCHEMA.md`) and "Category code" (no such column).
   `suppliers.html`'s mock modal had "Supplier code", "City", "Country",
   "Postal code", "Website", "Tax ID", and "Notes" — none exist on
   `Supplier`, and the model's single free-text `address` field doesn't
   decompose into the mock's separate street/city/country/postal inputs.
2. **Required fields mislabeled optional.** `Supplier.supplier_name`/
   `company_name`/`contact_person`/`email`/`phone`/`address` all lack
   `blank=True` — every one is required — but the mock UI marked
   `contact_person`/`email`/`phone`/address's constituent fields
   "(optional)". Also: the model has two distinct required name fields
   (`supplier_name` and `company_name`, both used in `Supplier.__str__`),
   but the mock had only one "Supplier name" input.
**Source Documentation:**
```
SCHEMA.md §2 Category:
    class Category(TimeStampedModel):
        name = models.CharField(max_length=100, unique=True)
        description = models.TextField(blank=True)
        is_active = models.BooleanField(default=True)
    # No parent FK, no code field, anywhere in this block.

SCHEMA.md §3 Supplier:
    class Supplier(TimeStampedModel):
        supplier_name   = models.CharField(max_length=150)
        company_name    = models.CharField(max_length=200)
        contact_person  = models.CharField(max_length=100)
        email           = models.EmailField(unique=True)
        phone           = models.CharField(max_length=20)
        address         = models.TextField()
        is_active       = models.BooleanField(default=True)
    # None of supplier_name/company_name/contact_person/email/phone/
    # address has blank=True — all required. No code/city/country/
    # postal_code/website/tax_id/notes field anywhere in this block.
```
**Status:** ✅ Fixed (Phase 6) — schema-less fields removed from both
modals rather than invented as new model columns (no dedicated Suppliers
doc exists to sanction inventing them — see BUG-17/BUG-26). Supplier's
mock modal gained a new required "Company name" field (mapped to
`company_name`) alongside the existing "Supplier name" field (mapped, by
literal name match, to `supplier_name` — the least presumptive reading
available without a dedicated doc to consult); `contact_person`/`email`/
`phone`/`address` relabeled required to match the model; the four
address-shaped inputs collapsed into the one real `address` field.
Category's "Active/Inactive" status select and Supplier's already
matched their models 1:1 (`is_active`) and needed no field changes,
just backend wiring.

### BUG-36 — Multi-line `{# #}` comment's leaked text broke the whole page
**Root cause:** Same underlying defect as BUG-03 — Django's `{# comment #}`
tag is single-line only, so a comment whose closing `#}` isn't on the same
line as the opening `{#` fails to parse as a comment at all and renders
as literal page text. `purchases.html`'s new `#realProductOptions`
`<template>` block was introduced with exactly this shape:
```
{# Real product <option>s for the line-items editor (Phase 7 — replaces
   mock-catalog.js's name-keyed options; retired, see project_memory.md).
   A <template> so it's inert markup, read by purchase-form.js at init. #}
<template id="realProductOptions">
```
BUG-03's instances just left visible junk text on the page — annoying but
harmless. This one was much worse: the leaked comment text itself
contained the literal substring `<template>` (from "A `<template>` so
it's inert markup..."), unescaped, in the middle of the HTML stream. The
browser's parser has no way to know this came from a doc comment — it saw
a real `<template>` start tag and did exactly what the spec says: entered
template-content parsing mode and started routing everything that
followed into that element's inert `.content` fragment. The *next* real
tag encountered was the actual, intended `<template id="realProductOptions">`
block, which nested one level deeper inside the fake one; its own
`</template>` only closed itself, leaving the outer (fake, comment-
sourced) template still open with no matching close anywhere in the
document. Every real sibling after that point — both real product
`<option>`s' container, the entire Add Purchase Order modal, the Receive
Items modal, and the page's own `<script>` tags — ended up nested inside
that dead template fragment: present in `document.body.innerHTML`'s
string output (which is why the raw response body looked fine), but
completely invisible to `document.querySelector`/`getElementById` and
therefore to every click handler and `data-modal-open` trigger on the
page. `modal.js` never errored — there was simply nothing live for it to
find.
**Source Documentation:** N/A — implementation bug, not sourced from any
project doc. Found via Playwright reporting `#addPurchaseModal` as 0
elements despite the raw HTTP response clearly containing that markup;
diagnosed by walking the live DOM tree (`document.body.children`, 2 deep)
down to a stray `<option>`/`<template>` pair sitting where the real modal
should have been.
**Status:** ✅ Fixed (Phase 7) — converted to `{% comment %}...{% endcomment %}`,
the same fix BUG-03 already established as this project's standard for
any comment that needs more than one line. Re-verified live: the modal
element count went from 0 to 1, and the full create → submit → approve →
receive flow worked end to end afterward. Worth remembering going
forward, more strongly than BUG-03 already implied: a leaked Django
comment isn't just cosmetic — if its text happens to contain something
that looks like an HTML tag (`<template>`, `<select>`, `<table>`, and a
few others all have special parsing rules), it can silently take down
everything after it on the page.

### BUG-37 — Users & Roles' filter controls were dead (missing `<script>` tag)
**Root cause:** `frontend/static/js/user-form.js` (Phase 8) always called
`TableFilter.init({...})` for the search box + role/status selects,
guarded only by `if (window.TableFilter && ...)`. That guard silently
no-ops when `window.TableFilter` is undefined — and it was: `users.html`'s
`extra_js` block loaded `modal.js`/`form-validation.js`/`dom-utils.js`/
`modal-form.js`/`user-form.js`, but never `table-filter.js` itself, unlike
every other real consumer of it (`audit_log.html`, `reports.html`,
`forecasting.html`, `slow_moving.html` all load it explicitly). The real
`data-search`/`data-role`/`data-status` attributes and empty-state markup
were all present and correct — only the script tag was missing.
**Source Documentation:** N/A — implementation bug, not sourced from any
project doc.
**Status:** ✅ Fixed (Phase 8.6) — added
`<script src="{% static 'js/table-filter.js' %}"></script>` to
`users.html`'s `extra_js` block, before `user-form.js`. Re-verified live
(Playwright, real DB data): a bogus search term correctly hides all rows
and shows the empty state; filtering by role correctly narrows the table.
Every other page that actually loads `table-filter.js` (Forecasting,
Slow-Moving, Audit Log, Reports) was independently re-verified working in
the same sweep — none had this bug. Products/Categories/Suppliers/
Purchases/Sales/Inventory/Adjustments/Notifications never load
`table-filter.js` at all — their visible search/select controls are
decorative by design, already tracked as known debt (`project_memory.md`
§10/§12), not a regression from Phase 5-8 and not touched here.

**Phase 8.7 — case (c) closed:** Products/Suppliers/Purchases/Sales/
Adjustments now load `table-filter.js` too — same shared module, no new
filtering mechanism. Each needed: (1) the missing `<script>` tag, (2)
`id`s on the search input and select(s) (none had one — the module keys
off DOM ids, not just presence), and (3) `data-search`/`data-<column>`
attributes on each `<tr>` (also missing everywhere — the mock-era rows
only ever had visual columns, no filter hooks). Status/type `<select>`
options had no `value` attribute either, meaning the browser defaulted
each option's value to its own display text ("Pending approval",
"Increase", ...) — harmless for a decorative control, but would have
silently broken filtering by matching against `po.status`'s real lowercase
choice values (`pending`, `approved`, ...) with the human label instead;
every option got an explicit `value="<real choice value>"` matching the
model's `TextChoices`. Two pages checked out as genuinely nothing to wire,
not overlooked:
- **Categories** (`categories.html`) has no search box or select at all —
  just a grid of cards. No filter control exists to connect.
- **Inventory** (`inventory.html`) has real-looking filter controls, but
  `frontend/views.py`'s `inventory()` view is still a one-line `render()`
  with no queryset — every row in the table is hardcoded mock HTML (SKU-
  20194, SKU-11832, ...), not real `InventoryRecord` data. `project_memory.md`
  §2 currently lists this page with a ✅ ("read-only by design"), which is
  misleading: read-only was the *intended* design, but the view was never
  actually built past the original Phase 3.6-era mock, unlike every other
  "✅ real" module. Wiring `table-filter.js` against fabricated rows would
  make the page *look* functional while filtering data that isn't real —
  flagged here rather than done, per this task's own instruction not to
  invent behavior. Building the real Inventory view (a real queryset from
  `InventoryRecord`, matching every other module's pattern) is a
  prerequisite and belongs in its own session, not folded into a
  filter-wiring task.
Verified live (Playwright, `verify_user`/`verify_super`, real Postgres
data) on all 5 newly-wired pages: bogus search hides all rows, clearing
restores them, each status/type select correctly narrows to the matching
subset, and clearing returns to the full set — identical results for both
roles (this app's list pages don't vary row *content* by role, only
action-button visibility, already covered in Phase 8.6's sweep). No
console errors on any of the 7 pages checked (5 wired + Categories +
Inventory). `table-filter.js` itself was not modified — reused exactly
as-is, same as every other consumer. 131/131 tests passing (frontend-only
change; no Python touched).

**Phase 8.9 — Inventory portion closed for real.** Built the real
`InventoryListView` (`AnyStaffMixin`, matching `07_INVENTORY.md`'s own
`@staff_required` — which in this project's RBAC means all 3 roles, not a
stricter gate) over a genuine `InventoryRecord` queryset, replacing the
one-line `render()`. `status` is read straight off the model (already
kept correct by `InventoryService` on every real mutation), not
recomputed. `inventory.html`'s rows, KPI/stat-strip numbers, and "last
movement" column are all real now; filter controls got the same
`data-search`/`data-status` + `table-filter.js` wiring as the 5 pages
above, closing the gap this entry itself flagged as deliberately
deferred. Confirmed strictly read-only: no `<form>` anywhere in the
template, no mutation call anywhere in the view, and a live direct POST
to `/inventory/` returns `405` — the only code paths that ever touch
`InventoryRecord` remain `InventoryService.increase_stock()`/
`decrease_stock()`/`initialize_for_product()`, called exclusively from
Purchase/Sale/Adjustment's service-layer methods, unchanged by this work.
5 new tests (`InventoryListViewTests`) — 136/136 passing (was 131).

### BUG-38 — Timestamps rendered in UTC instead of Bangladesh time
**Root cause:** `config/settings.py` had `TIME_ZONE = 'UTC'` (the Django
project-template default) with `USE_TZ = True`. `USE_TZ=True` means every
stored datetime is a correct, real UTC instant — the bug was never in
storage, only in *display*: every `{{ value|date:... }}` template render
and every `timezone.localtime()` call converts to whatever `TIME_ZONE`
says, and nothing in this project activates a different per-request
timezone. AuditLog — a compliance record — was the most consequential
case, but every rendered timestamp across the app (Purchases, Sales,
Notifications, admin) was equally affected.
**Stored vs. displayed — explicitly confirmed separately, per this task's
instruction:** all datetime storage in this project goes through
`auto_now_add`/`auto_now` (`TimeStampedModel.created_at`/`updated_at`,
`AuditLog.timestamp`) or explicit `timezone.now()` calls — all of which
are UTC-aware under `USE_TZ=True` and stored correctly in Postgres as
`timestamptz`. Confirmed against a real `AuditLog` row: stored value
`2026-08-11 03:58:48+00:00`, `timezone.localtime()` of that same value
correctly yields `2026-08-11 09:58:48+06:00`. **No stored timestamp was
ever wrong — this was purely a display/interpretation bug, and no data
correction is needed or was performed.**
**Related finding, disclosed not fixed at the time (out of this task's
scope) — RESOLVED Phase 8.99, see BUG-47:**
`PurchaseOrder._generate_po_number()`/`SaleTransaction.
_generate_invoice_number()` embed `timezone.now().strftime('%Y%m%d')` —
the UTC calendar date, not the local one. Separately, `PurchaseOrder.
order_date`/`SaleTransaction.transaction_date` (`DateField(auto_now_add=
True)`) resolve via Django's own `datetime.date.today()`, which reads the
host machine's OS clock directly and is **not** affected by
`settings.TIME_ZONE` at all (a well-known Django `DateField.auto_now_add`
gotcha — it only applies to `DateTimeField`). Near local midnight in
Bangladesh, these three values can still disagree with each other and
with the now-correctly-displayed Dhaka timestamps elsewhere on the same
record. Not fixed here at the time: correcting it changes a generated
business identifier's format (PO/invoice numbers), which was outside this
task's named scope ("if a fix would require changing business logic, stop
and flag it") — closed as its own pre-deploy blocker in Phase 8.99, once
the identifier-format change was explicitly in scope (see BUG-47).
**Source Documentation:** N/A — implementation bug (default left
unchanged; no doc specifies a timezone).
**Status:** ✅ Fixed (Phase 8.6) — `TIME_ZONE = 'Asia/Dhaka'` in
`config/settings.py`, `USE_TZ` left `True`. Re-verified live: the Audit
Log page's timestamp column now shows Dhaka local time, confirmed against
a direct `timezone.localtime()` check of the same underlying row.

### BUG-39 — Dashboard greeting never changed by time of day
**Root cause:** `dashboard/dashboard.html`'s heading had the literal text
"Good morning" hardcoded, a leftover from the original static mock — the
view (`frontend/views.py`'s `dashboard()`) passed no context at all.
**Source Documentation:** N/A — implementation bug (mock-era placeholder
text never made dynamic when the view went live in earlier phases).
**Status:** ✅ Fixed (Phase 8.6) — `dashboard()` now computes a
`greeting` ("Good morning"/"Good afternoon"/"Good evening") server-side
from `timezone.localtime().hour`, passed via context. Computed
server-side rather than client-side JS specifically so it can never
disagree with the Bangladesh-time timestamps BUG-38 just fixed elsewhere
on the same page (both now read the same `TIME_ZONE`-driven clock).
Verified live (Playwright) across all three roles at real server local
time (10:2x, Dhaka) — all three showed "Good morning", correctly; unit
tests added mocking `frontend.views.timezone.localtime()` to cover the
morning/afternoon/evening boundaries directly (`DashboardGreetingTests`,
`frontend/tests.py`).

### BUG-40 — Dashboard greeting showed "Amara" for every logged-in user
**Root cause:** `dashboard.html` read `{{ request.user.first_name|
default:"Amara" }}` — but `frontend.User` (`AbstractBaseUser` +
`PermissionsMixin`, not Django's `AbstractUser`) has no `first_name`
field at all, only `full_name`. Django's template engine resolves an
unknown attribute to an empty string rather than raising, so `|default`
fired unconditionally — every real user, regardless of who was logged in,
saw the mock name "Amara". `User.get_short_name()` (added Phase 4,
returns the first token of `full_name`) already existed and was already
the correct source for exactly this use — the template just never called
it.
**Swept the rest of the topbar/dashboard shell for the same placeholder,
per this task's instruction — found 2 more, both already correct:**
`includes/topbar_actions.html` and `includes/sidebar.html` both use
`request.user.get_full_name|default:"Amara Tenzin"` — `get_full_name()`
resolves correctly for any real authenticated user (verified live for all
three roles below), so the "Amara Tenzin" fallback there only ever fires
for a genuinely anonymous visitor, which is documented, intentional
behavior for this project's handful of not-yet-login-gated pages
(`project_memory.md` §4). Left as-is — not the bug, and changing it isn't
needed.
**Related finding, disclosed not fixed (out of this task's scope — RBAC
wiring):** `frontend/views.py`'s `dashboard()` view has no
`@login_required`/RBAC guard at all, unlike every other real module view
in this project. An anonymous visitor can currently reach `/dashboard/`
directly and would see the anonymous-fallback path described above. This
predates this task, is not one of the four named bugs, and touching RBAC
mixins was explicitly out of scope for this session.
**Source Documentation:** `SCHEMA.md` §1 User (field list has no
`first_name`/`last_name`) vs. `dashboard.html`'s hand-built mock markup,
which assumed a `first_name` field that was never real.
**Status:** ✅ Fixed (Phase 8.6) — `dashboard.html` now reads
`{{ request.user.get_short_name|default:"there" }}` (neutral fallback,
not a mock identity). Verified live (Playwright) as `verify_admin`/
`verify_super`/`verify_user`: headings read "Good morning, Naomi" /
"Good morning, Marcus" / "Good morning, Talia" respectively — no
"Amara" anywhere. Unit test added (`test_greeting_shows_real_user_name_
not_amara`, `frontend/tests.py`) asserting the response contains the
real user's first name and does not contain "Amara".

### BUG-41 — Dashboard page marked ✅ in `project_memory.md`, but it's almost entirely mock
**Root cause:** Found during Phase 8.8's documentation-integrity audit
(itself prompted by Phase 8.7 catching the same class of mistake on the
Inventory page). `frontend/views.py`'s `dashboard()` view:
```python
def dashboard(request):
    hour = timezone.localtime().hour
    ...
    return render(request, "dashboard/dashboard.html", {"greeting": greeting})
```
passes exactly one context key — `greeting`. Every other number and row on
the page comes from `dashboard.html`'s own `|default:"..."` fallbacks
(`{{ total_products|default:"1,284" }}`, `{{ total_categories|default:
"36" }}`, `{{ inventory_value|default:"186,420" }}`, etc.) or from
`dashboard.js`'s hardcoded Chart.js dataset arrays, or from static
`<tr>`/`<div>` markup for the Stock Alerts, Pending Approvals (including
Approve/Reject `<button>`s with no click handler or endpoint — visually
identical to Purchases' real ones, but wired to nothing), Recent Activity,
and AI Insights sections. None of these context variables are ever set by
the view, so every `|default` fires unconditionally, the same shape as
BUG-40 but across ~15 values instead of one. `project_memory.md`'s prior
entry — "KPI cards, Chart.js sales/inventory charts, static preview
panels" — was technically not false, but easy to misread: a reader could
reasonably conclude only the "preview panels" were static and the KPI
cards/charts were real, especially sitting under the same ✅ used for
genuinely-real modules like Products.
**Source Documentation:** N/A — documentation-accuracy bug in
`project_memory.md` itself, not a code defect. The underlying page being
mock is expected/correct for this project's current stage (Dashboard has
no dedicated module doc — `09_DASHBOARD.md` is on the missing-docs list,
BUG-17); the bug is specifically that this file's own record of that fact
was misleading.
**Status:** ✅ Fixed (Phase 8.96), closing the loop `09_DASHBOARD.md`
(Phase 8.95, approved 8.95.1) opened. `dashboard()` now computes every
KPI/stat/chart/widget from real, DB-aggregated queries (`Sum`/`Count`/
`annotate`, never a whole table pulled into Python to count it) — no
`|default:"..."` fabrication remains anywhere in `dashboard.html` except
the one already-approved, non-fabrication fallback from BUG-40
(`request.user.get_short_name|default:"there"`, for the pre-existing
anonymous-visitor edge case, unchanged). `dashboard.js`'s hardcoded chart
arrays are gone — both charts now read real data passed via
`{{ chart_data|json_script:"dashboardChartData" }}`. The AI Insights
section was deleted entirely, not replaced with an empty state, per
Decision 8/§4d. Pending Approvals renders as a read-only summary with
**no** Approve/Reject buttons anywhere on the page (Decision 4). Recent
Activity renders only for `request.user.role in (admin, supervisor)` —
confirmed absent from the *rendered HTML*, not just hidden, for a staff
user (Decision 5). `DASHBOARD_PREVIEW_ROWS = 5` is defined once and reused
for all 3 preview widgets (Decision 3). Verified live (Playwright, real
Postgres, all 3 roles): every KPI/stat value matched a direct manual DB
query exactly (products/categories/active suppliers/users = 3/3/3/4,
inventory value = $858.00, stock units = 111, low/out-of-stock = 2/0);
Stock Alerts and Pending Approvals showed real product/adjustment rows
matching the DB; Recent Activity showed 5 real `AuditLog` rows (all
non-`authentication` actions) for admin/supervisor and was genuinely
absent for staff; switching the Daily/Weekly/Monthly toggle changed both
the chart's data and its labels to real values (e.g. a real $89.10 sale
appearing in both the daily and monthly buckets); no console errors. 8 new
tests (`DashboardViewTests`) — 144/144 passing (was 136). This was the
last mock-but-marked-done page from Phase 8.8's audit — that
outstanding-work list is now empty.

### BUG-42 — `dashboard()` had no auth requirement at all
**Root cause:** Flagged as a live risk at the end of Phase 8.96 (§12
technical debt) — `dashboard()` was a bare function view, never given
`@login_required` or any RBAC mixin across Phases 8.6/8.8/8.9/8.96, each
of which touched this file for other reasons and disclosed the gap rather
than fixing it (out of each of those tasks' own scope). Harmless while
the page showed fabricated numbers; a real risk the moment Phase 8.96
made it compute genuine inventory value, stock levels, and headcounts —
an unauthenticated request could reach real business data.
**Source Documentation:** N/A — implementation gap, not sourced from any
doc. `09_DASHBOARD.md`'s own "Any role, same content" decision (Decision
8) already implied *some* authentication boundary (its endpoints are
still scoped to logged-in roles in `API_CONTRACTS.md`, just not
role-differentiated) — this was never actually enforced in code.
**Status:** ✅ Fixed (Phase 8.97 Part A). `dashboard()` converted from a
function view to `DashboardView(AnyStaffMixin, View)` — matching every
other real view's convention exactly and `09_DASHBOARD.md`'s "any logged-
in role, not gated to one" decision. The Recent Activity widget's
`request.user.is_authenticated` check (Phase 8.96) is now
belt-and-suspenders, not load-bearing — kept anyway, harmless. Verified
live: `GET /dashboard/` unauthenticated → `302` to
`/login/?next=/dashboard/`; all 3 roles still load the page correctly;
Recent Activity still absent from the rendered HTML for staff. 1 test
updated (anonymous now asserts a redirect, not "doesn't crash") + 1 new
test added (all 3 roles load successfully) — 145/145 passing (was 144).

### BUG-43 — Demand Forecasting/Slow-Moving pages also have no auth requirement
**Root cause:** Found during Phase 8.97's full-app wiring audit (Part B),
prompted by BUG-42. `demand_forecasting`/`slow_moving_dead_stock`
(`frontend/views.py`) are bare function views with zero decorators —
the same shape as BUG-42, `/ai/forecasting/` and `/ai/slow-moving/` are
reachable by anyone, logged in or not. Lower severity than BUG-42: both
pages are still 100% disclosed mock (confirmed in Phase 8.8's audit,
correctly labeled "All static/mocked" in `project_memory.md`) — there is
no real data to expose yet, only static example content the same as any
anonymous visitor could see on the public landing page.
**Source Documentation:** N/A — implementation gap.
**Status:** ✅ Fixed (Phase 8.99j). Converted both from bare function
views to CBVs (`DemandForecastingView`/`SlowMovingDeadStockView`),
gated `SupervisorRequiredMixin` — a disclosed deviation from this entry's
own original suggestion (`AnyStaffMixin`, mirroring BUG-42's fix):
Phase 8.99j's actual, more specific requirement ("staff can't see the AI
models") is narrower than "any logged-in role," so Admin+Supervisor only
is the correct gate here, not the same one BUG-42 used. Sidebar's
"Intelligence" nav group wrapped in the matching
`{% if request.user.role == 'admin' or request.user.role == 'supervisor' %}`
conditional (Phase 8.5's own established pattern, already used for the
Reports link right below it) so the hidden-link UX layer and the actual
server-side gate agree. Verified live, all 3 roles + anonymous: anonymous
redirects to login; Staff gets a real `302` on a direct GET to either URL
(not just a hidden link) and doesn't see either nav link; Supervisor/
Admin both load (`200`) and both see the links. 8 new tests
(`AIPageAccessTests`) — Phase 10/11 no longer need to carry this as a
Step 0 prerequisite; both pages are still 100% mock pending those
phases, only the access gate changed here.

### BUG-44 — Decorative "Export"/"Export CSV" buttons on 3 pages
**Root cause:** Found during Phase 8.97's audit while checking that every
actionable control does something real. Audit Log's "Export CSV" button
(`audit_log.html`) and Products'/Suppliers' "Export" buttons
(`products.html`/`suppliers.html`) render with no click handler anywhere
in their respective JS files and no backing endpoint — visually similar
to Reports' genuinely-wired PDF/CSV export (`ReportExportView`,
Phase 8), but inert. Pre-existing since each page's own build phase
(Products/Suppliers Phase 5/6, Audit Log Phase 8) — general "decorative
controls exist" language already covered this class of thing in
`project_memory.md` §10, but no prior entry named these three buttons
specifically.
**Source Documentation:** N/A — implementation gap, no doc specifies
export behavior for these three pages.
**Status:** ✅ Fixed (Phase 8.98). All 3 buttons wired to real CSV, plus a
4th (Movement History's new export, built in the same phase — see BUG-45).
`ProductExportView`/`SupplierExportView`/`AuditLogExportView`
(`frontend/views.py`) each build their own headers/rows from a real
queryset and hand them to `frontend/reports.py`'s existing
`generate_csv_response()` — the exact reuse this entry predicted, not a
new export mechanism. Auth matches each source page exactly:
`AnyStaffMixin` on Products/Suppliers (matching those pages' own gating),
`AdminRequiredMixin` on Audit Log (matching `AuditLogListView`'s own gate
and `13_AUDIT.md`'s "Admin only" rule — confirmed a staff request gets
redirected, not a bypass). Products/Suppliers export the **full dataset**,
not the current `table-filter.js` selection — that filter is client-side
only with no server-side equivalent to read, stated explicitly rather than
silently only exporting what happened to be on screen. Verified live: all
3 downloads are real CSVs whose row counts match the database exactly
(Products 3 rows, Suppliers 3 rows, Audit Log 233 rows — the full log, not
the on-screen page's 500-row display cap). 5 new tests
(`ExportViewTests`) — see BUG-45 for the shared test-suite total.

### BUG-45 — "Movement history" button did nothing (Inventory page)
**Root cause:** `inventory.html`'s page-level "Movement history" button
and every row's per-product "view movement history" pill button
(Phase 8.9) were both plain `<button type="button">` elements with no
`href`, no `data-*` trigger, and no JS handler anywhere — pure leftover
mock markup from before the Inventory page went real. `InventoryMovement`
(the immutable ledger, Phase 3) had recorded every real stock change
since Phase 3 — nothing about the *data* was missing, only a page to view
it existed nowhere in `frontend/urls.py`.
**Source Documentation:** N/A — implementation gap. `07_INVENTORY.md`'s
own reference code does document an `inventory_detail_view` per product
(`/inventory/<product_id>/`, showing that one product's movements) — this
implementation instead builds one shared, filterable ledger page
(`/inventory/movements/`, optionally narrowed by `?product=<id>`) rather
than a per-product detail route, consistent with this project's existing
`§13` architecture decision that no per-entity detail routes exist
anywhere in the app yet (Products/Suppliers/etc. don't have them either) —
a deliberate, disclosed choice, not an oversight.
**Status:** ✅ Fixed (Phase 8.98). `MovementHistoryListView`
(`AnyStaffMixin`, matching Inventory's own gating) + `/inventory/movements/`
+ `inventory/movement_history.html`. Server-side date-range filtering
(`date_from`/`date_to`, real `Paginator`-backed pagination, page size 50)
— a deliberate choice over client-side filtering: the ledger is
append-only and grows forever, so `table-filter.js` alone would only ever
see whichever one page happened to be loaded. Search (product/SKU) and
movement-type filtering stay client-side (`table-filter.js`) on top of
whatever page of date-filtered results is currently on screen — the same
split every other real list page in this app already uses. An optional
`?product=<id>` param (used by the per-row links) narrows to one
product's history. Confirmed strictly read-only: no `<form>` posts
anywhere except the GET-only date-filter form, no `InventoryMovement`
mutation anywhere in the view, live `POST /inventory/movements/` → `405`.
Export CSV (see BUG-44) reuses `frontend/reports.py`'s existing
`build_movement_report()`/`generate_csv_response()` directly and
genuinely respects the current date filter (unlike the Products/Suppliers/
Audit Log exports), since `build_movement_report()` already reads
`date_from`/`date_to` off the request. Verified live (Playwright, real
Postgres): clicking "Movement history" on Inventory navigates to the real
page; 7 real rows shown, matching the database exactly; a date range with
no matches shows the honest "No movements recorded for this filter" empty
state (not a fake zero); a wide range shows all 7 again; the per-row link
correctly filters to one product; timestamps render in Asia/Dhaka (e.g.
"Aug 11, 2026 16:00", matching a direct DB `timezone.localtime()` check);
client-side search/type filters narrow correctly (type=sale → exactly the
2 real sale movements); Export CSV downloads 8 lines (header + all 7
movements). 6 new tests (`MovementHistoryViewTests`) — 156/156 passing
across this whole phase (was 145).

### BUG-46 — `_date_bounds()` built naive datetimes against a tz-aware field
**Root cause:** `frontend/reports.py`'s `_date_bounds()` (Phase 8,
existing before this phase) parsed `date_from`/`date_to` via plain
`datetime.strptime()`, producing naive `datetime` objects, then compared
them against `InventoryMovement.created_at` — a `DateTimeField` under
`USE_TZ=True`. Django still produces a correct result (it coerces a naive
datetime into the currently-active timezone, `Asia/Dhaka`, before
comparing) but emits a `RuntimeWarning` every time. No test ever actually
exercised this path with `date_from`/`date_to` set until Phase 8.98's own
new `test_export_produces_real_csv_respecting_the_date_filter` — the
first test in this project to pass real date-filter params through to
`build_movement_report()`/`_date_bounds()`.
**Source Documentation:** N/A — implementation gap, no doc specifies
timezone handling for this helper.
**Status:** ✅ Fixed (Phase 8.98) — `_date_bounds()` now wraps both bounds
in `django.utils.timezone.make_aware()`, making the existing (already-
correct) intent explicit instead of relying on Django's implicit,
warning-emitting coercion. Behavior is unchanged — this was a latent
correctness-adjacent cleanup surfaced by, and fixed alongside, this
phase's own new export test, not a scope expansion.

**Also fixed in passing, test-only:** `NotificationViewTests`'s fixture
used bare `'T1'`/`'T2'`/`'T3'` as notification titles, then asserted
`assertNotContains(response, 'T3')` against a full rendered page — which
always includes a randomly-generated CSRF token. A 2-character substring
check against a page containing random tokens has a real, if small,
chance of a false-positive collision; this phase's own full-suite run hit
it once (a token containing `vT3E` tripped the assertion). Not an
application bug — renamed the fixture titles to long, collision-proof
strings (`NotifOwnTitleOne`/`NotifOwnTitleTwo`/`NotifOtherUserTitleThree`)
rather than leaving a rare, hard-to-reproduce flake in the suite once
found. Re-ran the affected test class 3× standalone afterward with no
recurrence.

### BUG-47 — `PurchaseOrder`/`SaleTransaction` date generation ignored `TIME_ZONE`, reading the OS clock or raw UTC instead
**Root cause:** two related, independently-buggy mechanisms, both flagged
(not fixed) as a "related finding" inside BUG-38's own writeup back in
Phase 8.6, closed for real here:
1. `PurchaseOrder.order_date`/`SaleTransaction.transaction_date` were
   `DateField(auto_now_add=True)`. Django's `DateField.pre_save()` (unlike
   `DateTimeField.pre_save()`) resolves `auto_now_add` via plain
   `datetime.date.today()` — the host OS clock's raw local date — and is
   **not** affected by `settings.TIME_ZONE`/`USE_TZ` at all. This is a
   well-known, documented Django gotcha specific to `DateField`/`TimeField`
   (`DateTimeField` has no such gap; its `auto_now_add` correctly goes
   through `timezone.now()`).
2. `PurchaseOrder._generate_po_number()`/`SaleTransaction.
   _generate_invoice_number()` built their `PO-YYYYMMDD-`/`INV-YYYYMMDD-`
   prefix via `timezone.now().strftime('%Y%m%d')` — `timezone.now()` is
   correctly UTC-aware, but `.strftime()` on an aware datetime formats it
   in whatever tzinfo it already carries (UTC), not `TIME_ZONE`. This
   silently embedded the UTC calendar date in the identifier, not the
   Dhaka one.
Both were invisible on this project's dev machine because its OS clock is
itself set to Bangladesh time (`time.tzname` confirms `('Bangladesh
Standard Time', 'Bangladesh Daylight Time')`) — `date.today()` and the
Dhaka date coincide there by construction, not because the code was
correct. On a UTC production server (Render's default), the two diverge
for roughly 6 hours around each Dhaka midnight: an order raised at, say,
2 AM Dhaka (20:00 UTC the previous day) would have been stamped and
numbered with yesterday's date.
**Existing dev records checked, not just assumed correct:** every
`PurchaseOrder`/`SaleTransaction` row in the dev DB at the time of this
fix has `order_date`/`transaction_date` and its PO/invoice number's date
component agreeing with each other and with `created_at` — confirmed by
direct query, not inferred. This is consistent with the root cause above
(dev OS clock = Dhaka time) and does **not** indicate the bug was
harmless; it means this dev environment's specific clock setup happened
never to cross the divergence window during this project's development.
No data correction was needed or performed.
**Identifier-format impact — explicitly confirmed, not just a wrong date
column:** because the PO/invoice number's `YYYYMMDD` segment is generated
by the same buggy mechanism, this bug could have produced a wrong
*identifier*, not merely a wrong date field alongside a correct one — a
PO raised just after Dhaka midnight could have been numbered
`PO-<yesterday>-XXXX` while its (also-buggy) `order_date` agreed with it,
making the mismatch invisible without comparing against `created_at`.
Fixed at the same time as the date fields, via the same
`timezone.localdate()` call, so the identifier and the date column can no
longer disagree with each other going forward.
**Source Documentation:** N/A — implementation bug; no doc specifies this
edge case, and the `auto_now_add`-for-`DateField` gap is a genuine Django
framework limitation, not a project-specific mistake.
**Status:** ✅ Fixed (Phase 8.99, pre-deploy blocker). `order_date`/
`transaction_date` are now plain `DateField()`s (migration
`0003_alter_purchaseorder_order_date_and_more`, `AlterField` only — no
DB-level column change, since `auto_now_add`'s effect is Python-side
`editable`/`blank` metadata, not a schema constraint), set explicitly in
each model's `save()` via `timezone.localdate()` before `po_number`/
`invoice_number` generation, which itself now also calls
`timezone.localdate()` instead of `timezone.now().strftime(...)`. Added
`TimezoneAwareDateGenerationTests` (`frontend/tests.py`) — mocks
`django.utils.timezone.now()` to a UTC instant on a different Dhaka
calendar day (`2026-01-01 20:00 UTC` = `2026-01-02 02:00 Dhaka`) and
asserts both the stored date and the generated number's date segment
land on the Dhaka day, not the OS clock's real (unmocked) date or the
UTC day — a regression back to either buggy mechanism fails this test
immediately. 190/190 tests passing (was 188).

### BUG-48 — Password reset via email left no audit trail and told no Admin
**Root cause:** `change_password_view` (Phase 8.98a) is the only place
`audit.log_action(..., audit.PASSWORD_CHANGED, ...)` and
`frontend.notifications.notify_admins(...)` were ever called for a
password change. The "Forgot password?" flow uses Django's own
`django.contrib.auth.views.PasswordResetConfirmView`, unmodified until
this phase — its `form_valid()` calls `form.save()` (which does the
actual `set_password()`) and redirects, with no knowledge of this
project's `change_password_view` or its audit/notify calls at all. So a
password changed via a reset email was a real, successful password
change that left **zero trace** in the audit log and **notified no one**
— while the byte-for-byte identical change made through the profile
modal was fully recorded. Confirmed by reading Django's own
`PasswordResetConfirmView.form_valid()` source directly before writing
any fix, per this phase's own instruction not to assume.
**Why this went undetected until now:** the reset flow itself was a
disabled link (Phase 4.5) until this phase finished it — the gap existed
in reachable Django code the whole time (anyone who knew/guessed a valid
reset URL could already trigger it), but was never exercised through the
UI, so it was never noticed as a live compliance gap until the link
itself was turned back on.
**Source Documentation:** N/A — implementation gap. `01_AUTH.md`'s own
`PasswordResetView`/`PasswordResetConfirmView` reference code
(`apps/authentication/urls.py`) wires up Django's stock views directly,
with no audit/notify override either — the doc's own reference
implementation has the identical gap, not just this project's translation
of it.
**Status:** ✅ Fixed (Phase 8.99a). Extracted the shared
`notify_user()`/`notify_admins()`/`audit.log_action()` triplet out of
`change_password_view` into a new `_record_password_change(user, request)`
helper (`frontend/views.py`) — reused, not duplicated. New
`StockwellPasswordResetConfirmView(PasswordResetConfirmView)` overrides
only `form_valid()`: calls `super().form_valid(form)` (Django's own,
unmodified password-setting logic) then `_record_password_change(
form.user, self.request)` — `form.user` (set by `SetPasswordForm.
__init__`, unrelated to `save()`) is the user whose password was just
reset; the new password itself is never read or passed to either
function. Verified live against the real seeded `verify_user` account,
not just the test suite: real reset email sent (console backend) with a
real working link, password actually changed, a real `AuditLog`
`PASSWORD_CHANGED` row exists, `verify_admin` received a real
notification naming Talia Nakamura with the new password absent from
both its title and message, and login with the new password succeeded
(`302` to `/dashboard/`) — same shape `ChangePasswordViewTests` already
proved for the modal path. 10 new tests
(`PasswordResetFlowTests`) — 200/200 passing (was 190).

### BUG-49 — Movement History's export silently disagreed with the page's own filter
**Root cause:** Phase 8.98 built two independent filtering code paths for
the same data. `MovementHistoryListView` (the page) filtered dates with
`created_at__date__gte`/`__lte`; `frontend/reports.py`'s
`build_movement_report()` (the export) filtered dates with its own
`_date_bounds()` — a different, timezone-aware range built via a separate
comparison. The two happened to agree closely enough in practice that
nothing caught it, but they were never the same code. Worse: the page's
`product`/movement-type filtering had no equivalent in the export at all
— type filtering was client-side only (`table-filter.js`), and the export
function never read it off the request. A user could filter Movement
History to `type=sale` on screen, click Export CSV, and receive every
movement type in the file — the export silently ignoring a filter the
user had just visibly applied, with nothing telling them so.
**Why this went undetected until now:** BUG-45's own Phase 8.98 entry
documented the client-side search/type split as a deliberate, disclosed
choice — true for what it covered (search/type were never claimed to be
exported), but it didn't anticipate that a *filtered page* implies a user
expectation the *export* matches it, which no test or manual check ever
exercised together.
**Source Documentation:** N/A — implementation gap; no doc specifies
Movement History's filter/export shape at all (it isn't in
`07_INVENTORY.md`'s reference code — see BUG-45).
**Status:** ✅ Fixed (Phase 8.99d). One shared `filter_movements()`
function (`frontend/reports.py`) is now the single source of truth for
date/product/movement-type/search filtering, called by both
`MovementHistoryListView` and `build_movement_report()` — the two code
paths were unified into one, not synchronized by convention. Search also
moved server-side (dropping `table-filter.js` from this page entirely),
so every filter a user can apply is now genuinely reflected in both CSV
and PDF export (PDF is new this phase too). Verified live against the
real dev DB: CSV/PDF row counts matched a direct DB query for 4 filter
combinations, including one returning zero rows (an honest empty export,
not an error). 8 new tests — 225/225 passing (was 217). See
`docs/project_memory.md` §13/§15 item 50 for the full phase writeup,
including why a related "filter by cancelled/rejected source document"
idea was investigated and deliberately not shipped as a UI control.

### BUG-50 — Sidebar notification badge was a hardcoded mock value
**Root cause:** `includes/sidebar.html`'s Notifications nav item had a
literal `<span class="nav-item-badge">6</span>` — Phase 3.6 mock-era
markup, wired to nothing. Phase 8 built the real
`NotificationUnreadCountView` and a genuinely live topbar bell badge
(`#notifBadge`, polled every 30s by `notifications.js`) but never swept
the sidebar's own badge up into that work — the two sit right next to
each other conceptually (both claim to show "how many unread
notifications do I have") but only one of them was ever real. Every user,
regardless of their actual unread count (including zero), saw "6" in the
sidebar on every page.
**Why this went undetected until now:** the topbar bell badge was the
one built and verified in Phase 8's own live-verification pass; the
sidebar badge was pre-existing markup nobody was asked to touch at the
time, so it was never swept for staleness the way BUG-37/39/40's mock
leftovers eventually were.
**Source Documentation:** N/A — implementation gap, no doc specifies the
sidebar's own badge behavior.
**Status:** ✅ Fixed (Phase 8.99f-2). `notifications.js`'s existing
`pollUnreadCount()` now updates both the topbar dot and the sidebar
badge from the same `fetch('/notifications/unread-count/')` response —
one poll, not two — so they can't disagree. The sidebar badge starts
`hidden` in the server-rendered markup (same as the topbar dot always
did) and shows the real count once the first poll resolves, hiding again
at zero. Verified live: a real user with 16 pre-existing unread
notifications plus 3 deliberately created showed `unread_count: 19` at
the shared endpoint; marking one read dropped it to 18 immediately. See
`docs/project_memory.md` §13/§15 item 53 for the full phase writeup
(also covers Part 1's admin-email re-confirmation and Part 2's new,
guarded `UserDeleteView`).

### BUG-51 — Leaked multi-line `{# #}` comment in the Add User modal
**Root cause:** the exact BUG-03/BUG-36 shape, a third time. Django's
`{# comment #}` tag is single-line only (its tokenizer regex isn't
`DOTALL`) — a comment whose closing `#}` isn't on the same line as its
opening `{#` fails to match as a comment token at all and renders as
literal page text instead. `users.html` had one directly above the Add
User modal's "temporary password" info banner:
```
{# Phase 8.98e: no password field — a strong password is generated
   server-side and emailed to the new user. You (the Admin) never
   see it. #}
```
spanning 3 lines — confirmed by rendering the page and finding the
literal text (delimiters and all) inside the live HTML, not just by
reading the template source. This is precisely what "extra/stray lines
in the popup" looks like to a user: a chunk of developer-facing prose
sitting inside an otherwise clean form.
**Why this went undetected until now:** the comment was added in Phase
8.98e and never exercised by any test that renders and inspects the
modal's actual HTML output — every existing user-creation test asserted
on the POST response/DB state, never on the GET-rendered form.
**Source Documentation:** N/A — implementation bug, general Django
templating behavior, not something any project doc specifies (same as
BUG-03/BUG-36).
**Status:** ✅ Fixed (Phase 8.99f-4) — converted to
`{% comment %}{% endcomment %}`, the same fix BUG-03/BUG-36 used. The
other 3 `{# #}` comments in `users.html` were checked individually and
all close on their own line — confirmed not broken, not just assumed.
New test (`test_add_user_modal_has_no_leaked_comment_text`) renders the
page and asserts the leaked text is gone and the real info banner still
renders — the missing test class BUG-03/BUG-36 didn't leave behind
either, now covering this specific file.

### BUG-52 — Add User's real success had no user-visible confirmation
**Root cause:** `UserListCreateView.post()` returned a bare
`{"success": True}` on a genuine success, and `user-form.js`'s
`onSubmit()` did nothing with it beyond `window.location.reload()` — no
Add-modal in this app has ever shown a positive confirmation on success
(Products/Purchases/etc. all just reload silently too, confirmed by
reading their own `onSubmit`s), which is a reasonable default when the
new row is its own confirmation. User creation is the one case where
that default fails: the meaningful outcome — whether the credentials
email actually reached the new user — is completely invisible in the
table, so an Admin genuinely could not tell, from the browser, whether
"the user was created" also meant "they can actually log in."
**Why this went undetected until now:** every automated test (including
this same phase's own DB/`response.json()`-level checks) verified the
row existed and the response's `success` flag, never a rendered,
user-visible message — because there wasn't one to check. "Worked when
tested, not when actually used" is exactly what that gap looks like:
a scripted/terminal check reads the JSON directly, where a real admin
in a browser sees nothing.
**Source Documentation:** N/A — implementation gap, not sourced from any
doc.
**Status:** ✅ Fixed (Phase 8.99f-4), alongside Phase 8.99f-3's identical
gap on the failure path (BUG-52's warning-side sibling, not separately
numbered — found and fixed one phase earlier). Every real success now
carries a `message` naming the emailed address
(`"User created — credentials emailed to jane@example.com."`);
`user-form.js` reads `message` or `warning` (mutually exclusive) and
`alert()`s whichever is present before reloading — the same mechanism
already used for the warning case, not a new toast component. Verified
live via a real POST through the actual endpoint (the identical request
shape the browser's fetch() sends): the returned payload is exactly what
the browser would alert(); a duplicate resubmit correctly stays a clean
`400` with an inline field error, not a crash. 2 existing tests updated
to assert on the message content rather than an exact-empty-dict
snapshot (the old assertion was itself part of why this shipped
unnoticed — it never looked at what a person would actually see).

### BUG-53 — Success message overclaimed on the console email backend
**Root cause:** Django's console email backend (`config/settings.py`'s
own default, and this project's resting dev state) never raises —
`send_mail()` "succeeds" by printing the message to whichever terminal
happens to be running the Django process, not by delivering it anywhere.
`send_new_user_credentials_email()`'s `email_sent` return value was
therefore `True` in exactly the same way for a genuine SMTP delivery and
a purely local print, and BUG-52's own fix (`message` on `email_sent`)
inherited that ambiguity: the response said "credentials emailed to X"
regardless of which actually happened.
**Why this went undetected until now:** this session's own verification
practice (every prior SMTP-proving phase — 8.99f, 8.99f-3) always
temporarily flipped `EMAIL_BACKEND` to real SMTP before testing, then
reverted it to console afterward as the resting state. That made every
scripted check in this session pass against a real send, while a real
admin's own click — always against whatever the resting environment
actually is — never got one. Reported as "works when the tool does it,
not when I do it," which is a precise description of two processes
observing the same code against two different `EMAIL_BACKEND` values.
**Source Documentation:** N/A — implementation gap; a distinction (`the
mail API didn't raise` vs. `an email actually left the machine`) no doc
in this project models, since `EMAIL_BACKEND` swapping is a deployment/
environment concern, not a business rule.
**Status:** ✅ Fixed (Phase 8.99f-5). Diagnosed via the task's own 4-cause
checklist before any code change: printed the effective runtime email
config (confirmed `EMAIL_BACKEND` was console; every other Gmail
setting — `EMAIL_HOST`/`PORT=587`/`USE_TLS=True`/`USE_SSL` unset —
already correct); ran a bare `send_mail()` isolated from all
user-creation code (returned `1`, no exception, config genuinely fine);
reproduced the exact symptom live with a real POST on the console
backend, getting the same honest-*looking* `message` a real send would
produce. `UserListCreateView.post()` now checks
`settings.EMAIL_BACKEND` and gives the console case its own distinct
message stating plainly that no real email was sent and where the
credentials actually went (the server's own terminal) — never the same
text as a real SMTP success. `send_new_user_credentials_email()` itself
was not touched — the bare-shell test proved that path was never the
problem. Resting-backend question put to the owner directly rather than
decided unilaterally: console stays the default (safer — no routine dev
click emails a real address by accident), with the new message making
that state legible instead of silently misleading. Live-verified over
real SMTP end to end, including one genuine unplanned send failure
(`WinError 10054`, a connection reset) correctly surfaced as a `warning`
rather than a false success, and a real login with a real emailed
password (`302` to `/dashboard/`, `check_password()` confirmed). 1 new
test (`@override_settings`, asserting the console message's actual
wording, not just that a message exists) — 249/249 passing.
