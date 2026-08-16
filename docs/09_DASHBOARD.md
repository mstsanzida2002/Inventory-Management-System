# 📊 Module 09 — Dashboard
# AI-Powered Smart Inventory Management System

> **Claude Code:** Unlike every other numbered module doc in this project,
> this one was not part of the original spec handed to Claude Code — no
> `REQ` range is assigned to it anywhere in this project's requirements
> numbering, and `INDEX.md` linked to a file (`modules/09_DASHBOARD.md`)
> that never existed until now (see `docs/bugsfound.md` BUG-17). This
> document originates the spec instead of translating one, produced in
> Phase 8.95 by reconciling three sources against each other: the
> pre-existing `dashboard.html` UI mock (treated as a wishlist, not a
> source of truth — it fabricates every number via `|default:"..."`
> template fallbacks, see BUG-41), `API_CONTRACTS.md`'s `Dashboard
> Endpoints` and `Inventory Endpoints` sections (the only place any
> dashboard field names were actually documented before this file), and
> `SCHEMA.md` (what can actually be queried). Read `project_memory.md`
> §13 for this project's standing "confirm the doc, don't invent
> silently" rule — every threshold, window, and row limit below that
> isn't sourced from the two documents above is called out explicitly as
> a disclosed decision, not a silent guess.
>
> **This document is a decision spec, approved before Phase 8.96 builds
> against it — it defines what to build, not how.** No implementation
> code ships from this document; illustrative query expressions appear
> per-row because "the exact query" is literally part of what was asked
> for, not because they're meant to be copy-pasted verbatim.
>
> **Status: FINAL.** Every decision below was reviewed and approved
> (Phase 8.95.1) — no open items remain. Phase 8.96 builds directly
> against this document; any deviation found necessary during that build
> should come back here as a disclosed update, not a silent one.

---

## Requirements Coverage

No `REQ` range assigned (see note above). Functionally covers
`API_CONTRACTS.md`'s two `Dashboard Endpoints` (`GET /dashboard/stats/`,
`GET /dashboard/charts/`) and reuses `GET /inventory/stats/`'s documented
fields, which overlap with the Dashboard stats payload.

---

## Business Rules

| Rule | Detail |
|---|---|
| Dashboard is read-mostly | Every KPI/chart/widget is a query against existing data — nothing on this page creates or mutates a row, mirroring Inventory's own "GET-only" rule (§ below, Pending Approvals) |
| No new thresholds invented | Every "low"/"pending"/"recent" cutoff either reuses a real model field (`InventoryRecord.status`, `PurchaseOrder.status`) or is called out as a disclosed, arbitrary decision — never a number invented to match the mock's fabricated data |
| Role visibility | `API_CONTRACTS.md` marks both dashboard endpoints **"Any"** role, with no role-conditional payload documented. `INDEX.md`'s one-line description ("KPIs, charts, **role-specific views**") conflicts with this — flagged as a doc inconsistency, resolved (Decision 8) as **"Any role, same content"** for the page overall, with exactly one exception: the Recent Activity widget is admin/supervisor-only (Decision 5) |
| AI-dependent content stays out until it's real | Nothing sources from `DemandForecast`/`InventoryClassification` until Phase 10/11 populate them — see the AI Insights row |

**Constant:** `DASHBOARD_PREVIEW_ROWS = 5` — one named constant, defined
once (module-level in wherever `dashboard()` ends up living), governing
every "top N" preview list on this page: Stock Alerts, Pending Approvals
(combined), and Recent Activity. Decision 3 originally proposed three
separate hardcoded `5`s per-widget; consolidated into one constant so a
future change to the preview depth is a one-line edit, not a three-place
find-and-replace.

---

## 1. KPI Cards (top row, 4 cards)

| Card | Definition | Query | Window | Backable now? |
|---|---|---|---|---|
| Total products | Every `Product` row, unfiltered — matches Products page's own `counts['total']` (`ProductListCreateView.get()`), which is not `is_active`-filtered either | `Product.objects.count()` | None — live snapshot | **Yes** |
| Categories | Every `Category` row, unfiltered — matches Categories page's own total | `Category.objects.count()` | None | **Yes** — not in `API_CONTRACTS.md`'s stats payload; see Decision 6 |
| Active suppliers | `Supplier` rows with `is_active=True` — matches Suppliers page's own `counts['active']` | `Supplier.objects.filter(is_active=True).count()` | None | **Yes** — `API_CONTRACTS.md` documents `total_suppliers` (unqualified); see Decision 7 for why "active" is kept |
| System users | Every `User` row, all roles, active + inactive — matches Users & Roles page's own `counts['total']` | `User.objects.count()` | None | **Yes** — not in `API_CONTRACTS.md`'s stats payload; see Decision 6 |

**Trend badges** (the mock's "+4.2%", "+1.1%", "2 new", "3 new" pills under each value): see **Decision 1** — none of these percentages are backable (no history/snapshot table exists anywhere in `SCHEMA.md` to compute a real period-over-period percentage change). All 4 cards get the same real, computable format instead: **"+N new in the last 30 days"**, counting rows whose `created_at >= now - 30 days`. This is exactly what the mock's own "2 new" / "3 new" pills already imply for Suppliers/Users — Products/Categories' fabricated percentages are simply replaced with the same honest shape, not two different formats.

---

## 2. Compact Stat Strip (4 items, below the KPI row)

| Item | Definition | Query | Window | Backable now? |
|---|---|---|---|---|
| Inventory value | Sum of `total_value` across every `InventoryRecord` — **identical to the real Inventory page's own `counts["total_value"]`** (Phase 8.9), reused verbatim | `InventoryRecord.objects.aggregate(v=Sum('total_value'))['v'] or 0` | None | **Yes** — documented (`total_inventory_value`) |
| Stock units on hand | Sum of `current_stock` across every `InventoryRecord` | `InventoryRecord.objects.aggregate(u=Sum('current_stock'))['u'] or 0` | None | **Yes** — not documented but trivially in-scope of "inventory stats"; see Decision 6 |
| Low stock items | Count where `status = InventoryStatus.LOW_STOCK` — reads the model's own field, not recomputed (same precedent as Phase 8.9) | `InventoryRecord.objects.filter(status=InventoryStatus.LOW_STOCK).count()` | None | **Yes** — documented (`low_stock_count`) |
| Out of stock | Count where `status = InventoryStatus.OUT_OF_STOCK` | `InventoryRecord.objects.filter(status=InventoryStatus.OUT_OF_STOCK).count()` | None | **Yes** — documented (`out_of_stock_count`) |

---

## 3. Charts (2)

### 3a. Sales & Purchases (Daily / Weekly / Monthly segmented toggle)

| Series | Definition | Query shape | Backable now? |
|---|---|---|---|
| Sales | Sum of `SaleTransaction.total_amount` where `status = SaleStatus.COMPLETED`, grouped by `transaction_date` per bucket | `SaleTransaction.objects.filter(status=SaleStatus.COMPLETED, transaction_date__gte=<window start>).values('transaction_date').annotate(total=Sum('total_amount'))` | **Yes** |
| Purchases | Sum of `PurchaseOrder.total_cost`, grouped by `order_date` per bucket — **status-filtered, see Decision 2b** | `PurchaseOrder.objects.filter(status__in=[POStatus.APPROVED, POStatus.PARTIAL, POStatus.RECEIVED], order_date__gte=<window start>).values('order_date').annotate(total=Sum('total_cost'))` | **Yes**, with the disclosed status filter below |

- **Window (Decision 2a):** Daily = last 7 days · Weekly = last 8 weeks · Monthly = last 6 months.
- **Purchases status filter (Decision 2b):** only `APPROVED`/`PARTIAL`/`RECEIVED` orders count as real committed spend — `DRAFT` and `PENDING` aren't decided yet, `REJECTED`/`CANCELLED` never happened. `PurchaseOrder.total_cost` already sums the line items regardless of received quantity, so `PARTIAL` orders count their full committed value, not just what's arrived — consistent with "purchases" meaning committed spend, not physical receipt.
- **Disclosed limitation:** grouped by `order_date` (when the PO was created), not a receipt date — no such field exists on `PurchaseOrder`/`PurchaseOrderItem` in `SCHEMA.md`. The alternative (deriving a received-value series from `InventoryMovement.quantity_change × product.purchase_price`) uses *current* price for historical movements, which is no more accurate and adds a join for no real gain — not recommended.

### 3b. Inventory Movement (Received vs. Dispatched)

| Series | Definition | Query shape |
|---|---|---|
| Received | Sum of `InventoryMovement.quantity_change` where `quantity_change > 0`, grouped by month | `InventoryMovement.objects.filter(quantity_change__gt=0, created_at__gte=<6mo ago>).values(month=TruncMonth('created_at')).annotate(total=Sum('quantity_change'))` |
| Dispatched | Sum of `-quantity_change` where `quantity_change < 0`, grouped by month (shown as a positive magnitude) | same shape, `quantity_change__lt=0` |

- **Window:** last 6 months — **not a decision**, the mock's own subtitle ("last 6 months") already specifies this exactly; kept as-is.
- **Backable now?** **Yes**, no threshold decisions needed — `quantity_change`'s sign already cleanly separates stock-in from stock-out across all 4 `MovementType` values.

---

## 4. Widgets (4)

### 4a. Stock Alerts

- **Definition:** the most urgent `InventoryRecord`s needing attention.
- **Query:** `InventoryRecord.objects.filter(status__in=[InventoryStatus.LOW_STOCK, InventoryStatus.OUT_OF_STOCK]).select_related('product').order_by('current_stock')[:DASHBOARD_PREVIEW_ROWS]`
- **Row limit:** `DASHBOARD_PREVIEW_ROWS` (= 5) — **Decision 3**, an arbitrary but reasonable round number; the mock shows 4, no documented count exists either way.
- **Backable now?** **Yes.**
- **Link:** "View all" → `/inventory/`. **Known gap, not this phase's to fix:** the mock's own link (`/inventory/?status=low`) implies a URL-driven filter, but Phase 8.9's real Inventory page filters entirely client-side via `table-filter.js` — a `?status=` query param currently does nothing there. Recommend linking to plain `/inventory/` (no param) for now rather than adding query-param support to `table-filter.js` as an undiscussed side effect of this phase.

### 4b. Pending Approvals

- **Definition:** outstanding items awaiting a supervisor/admin decision, combining two models.
- **Query:** `PurchaseOrder.objects.filter(status=POStatus.PENDING)` and `InventoryAdjustment.objects.filter(status=AdjustmentStatus.PENDING)`, each ordered by `-created_at`, interleaved in Python and capped at `DASHBOARD_PREVIEW_ROWS` combined — two small querysets on different tables, not worth a DB-level `UNION` at this data volume.
- **Row limit:** `DASHBOARD_PREVIEW_ROWS` (= 5) combined — **Decision 3** again.
- **Backable now?** **Yes** — both counts are individually documented (`pending_po_approvals`, `pending_adjustments`); recommend also surfacing the two counts as a small header label ("3 POs · 2 adjustments") alongside the combined list.
- **Action buttons — Decision 4, FINAL: read-only, no live buttons.** The mock shows working-looking Approve/Reject buttons in this widget. **Approved: read-only summary rows + a "View all" link to the real module** (`/purchases/?status=pending`, `/adjustments/?status=pending` — same inert-query-param caveat as 4a), **not** embedded action buttons. Reasoning:
  1. The Dashboard has no RBAC gate at all and is meant to be visible to every role. Approve/Reject requires `SupervisorRequiredMixin`. Rendering those buttons unconditionally for a staff user reintroduces the exact "button visible but the click gets silently blocked" bug class Phase 8.5 found and fixed everywhere else in this app (`project_memory.md` §15 item 31) — avoidable entirely by not rendering the buttons here rather than re-adding the `{% if request.user.role == ... %}` guard a third time in a third place.
  2. A real Approve/Reject action needs more context than a summary card can show — Reject requires a reason (`prompt()` on Purchases/Adjustments today), Receive needs a per-line-item modal. Reusing the real endpoints from a cramped dashboard widget means either duplicating that UX or shipping a degraded version of it.
  3. The real Purchases/Adjustments pages already do this well and are one click away. A "View all" link costs nothing and adds no duplicate logic to maintain.

### 4c. Recent Activity

- **Definition:** a curated feed of recent real business events, sourced
  from `AuditLog`.
- **Query:** `AuditLog.objects.exclude(module='authentication').select_related('user').order_by('-timestamp')[:DASHBOARD_PREVIEW_ROWS]`
- **Row limit:** `DASHBOARD_PREVIEW_ROWS` (= 5) — **Decision 3**.
- **Backable now?** **Yes** — `AuditLog` already records every real action (`PRODUCT_CREATED`, `PO_APPROVED`, `SALE_CREATED`, `ADJUSTMENT_APPROVED`, etc.) with a real user and timestamp; `timesince` (already used for Inventory's "last movement" column, Phase 8.9) gives the same "X ago" relative display the mock fakes.
- **`module='authentication'` exclusion — what it removes, if this widget is ever widened later:** `LOGIN_SUCCESS`/`LOGIN_FAILED`/`LOGOUT`/`ACCOUNT_LOCKED`/`PROFILE_UPDATED`/`PASSWORD_CHANGED` (confirmed exhaustive against every `log_action()` call site in `views.py`/`services.py`) — session/security hygiene, not "what happened in the business." Kept in this document's query even though the visibility decision below makes it moot for now (an admin/supervisor viewing this widget doesn't need session-hygiene noise mixed into a business-activity feed either), and it's one less thing to reconsider if visibility is ever loosened later.
- **Decision 5, FINAL: admin/supervisor-only widget.** `13_AUDIT.md` documents the full audit log as **"Only System Administrator can view,"** and the real `AuditLogListView` is `AdminRequiredMixin`-gated. Rather than carve out a narrower, disclosed exception to that rule for this widget, the decision is to **not stretch it at all**: Recent Activity only renders for `request.user.role in ('admin', 'supervisor')` — the same visibility boundary already applied to the Reports sidebar link (Phase 8.5) and consistent with `SupervisorRequiredMixin`'s existing role hierarchy elsewhere in this app. Staff users simply don't see this widget (the dashboard layout for staff has one fewer card in the right column; no placeholder, no "ask an admin" message — it's just absent, the same treatment AI Insights gets for everyone). `13_AUDIT.md`'s "Admin only" framing for audit-derived data stays uncontested by this page. This is the one deliberate exception to Decision 8's "Any role, same content" default for the rest of the page.

### 4d. AI Insights (Demand Forecasting + Slow-Moving preview tables)

- **Definition:** mini-previews of `DemandForecast`/`InventoryClassification` rows.
- **Query shape:** `DemandForecast.objects.order_by('-created_at')[:4]`, `InventoryClassification.objects.order_by('-classified_at')[:4]`.
- **Backable now? No.** Confirmed empty in Phase 8.8's audit — nothing writes to either table until the AI pipeline (Phase 10/11) exists.
- **Recommendation: drop this section from the Phase 8.96 build entirely** — not an empty state, not a placeholder card, just don't render it yet. The standalone Demand Forecasting/Slow-Moving pages are themselves still fully mocked pending Phase 10/11; a Dashboard preview of those pages would be a mock of a mock, and a second place to remember to "un-fake" later. Re-add it once Phase 10/11 lands and the source pages go real — at that point it's a straightforward query addition against tables that finally have rows, not a redesign.

---

## Disclosed Decisions (summary) — all FINAL, approved 2026-08-12 (Phase 8.95.1)

Matching this project's SKU-format-style precedent (`project_memory.md`
§13). No open items remain; Phase 8.96 builds directly against these:

1. **Approved as-is.** All 4 KPI trend badges become **"+N new in the last 30 days"**, replacing the mock's two different, both-fabricated formats (fake percentages on Products/Categories, unspecified-but-plausible "N new" on Suppliers/Users) with one real, consistent one.
2. **Approved as-is.** Chart windows: Daily = 7 days, Weekly = 8 weeks, Monthly = 6 months (Sales & Purchases chart) — chosen to match the Inventory Movement chart's own already-specified 6-month window, so the two charts feel consistent rather than arbitrary relative to each other. **2b:** Purchases-chart series counts only `APPROVED`/`PARTIAL`/`RECEIVED` orders, excluding `DRAFT`/`PENDING`/`REJECTED`/`CANCELLED`.
3. **Approved, with one change.** Row limit for Stock Alerts, Pending Approvals (combined), and Recent Activity is a single named constant, **`DASHBOARD_PREVIEW_ROWS = 5`**, not three separate hardcoded `5`s — see the Business Rules section. Still a round, arbitrary-but-reasonable default with no documented basis either way; consolidating it into one constant just means a future change to the preview depth is a one-line edit.
4. **Approved as-is.** Pending Approvals widget is **read-only** (summary + "View all" link) — **no** embedded Approve/Reject buttons. Full reasoning in §4b.
5. **Approved — the fallback: admin/supervisor-only.** Recent Activity only renders for admin/supervisor roles. `13_AUDIT.md`'s "Admin only" framing for audit-derived data stays **uncontested** — no stretch of that rule, no disclosed exception needed, because the widget simply isn't shown to staff. Full reasoning in §4c.
6. **Approved as-is.** Categories/System users (KPI cards) and Stock units on hand (stat strip) are kept even though they're absent from `API_CONTRACTS.md`'s documented stats payload — all three are cheap, real, single-model aggregate counts with no threshold or judgment call involved, unlike the widgets above. This is a **disclosed deviation from the documented stats contract, not an undocumented one** — recorded here specifically so it reads as a considered addition, not something Phase 8.96 (or a future audit) has to rediscover.
7. **Approved as-is.** "Active suppliers" (not the doc's unqualified "total_suppliers") is kept — `is_active` is already the operative status field for every other real module in this app (Products' supplier/category filtering, Users & Roles' deactivate/reactivate); an inactive supplier isn't operationally interesting on an at-a-glance dashboard.
8. **Approved as-is.** Role visibility resolved as **"Any role, same content"** (per `API_CONTRACTS.md`'s concrete endpoint table), not `INDEX.md`'s vaguer "role-specific views" — a doc inconsistency, surfaced rather than silently picked either way. This is the page-wide default; **Recent Activity (Decision 5) is the sole, deliberate exception** — admin/supervisor-only, everything else on the page is identical for every role. **AI Insights widget: dropped, not deferred-with-placeholder** — see §4d, unchanged from the original recommendation.

## Deferred / Not Yet Backable

- **AI Insights widget** (§4d) — drop until Phase 10/11.
- **`/inventory/?status=`, `/purchases/?status=pending`, `/adjustments/?status=pending` deep-links** referenced by "View all" links in §4a/4b currently resolve to the real pages but the query param does nothing (all 3 pages filter client-side only, Phase 8.7/8.9). Not this phase's gap to close — noted so Phase 8.96 doesn't accidentally assume it works.

## Out of scope for this document (noticed, not analyzed)

The page-heading-row's "Refresh data" and "New purchase order" buttons are
still fully decorative in the mock and weren't part of this task's 4/2/4
element list. Brief note in case it's useful for Phase 8.96: "Refresh
data" is likely redundant with a normal page reload (nothing here is
proposed to auto-update client-side) and could just be dropped; "New
purchase order" duplicates real UI the Purchases page already owns
(supplier picker, line-items editor) and is better left as a link to
`/purchases/` than reimplemented here. Not decided, just flagged.
