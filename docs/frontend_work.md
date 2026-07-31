# Frontend Work Log

Concise summary of all frontend work on Stockwell. No build step — Django
templates + vanilla JS/CSS, custom design system (no Bootstrap despite
`TECH_STACK.md`). Full detail lives in `docs/project_memory.md`; bug detail
in `docs/bugsfound.md`. This file is just the frontend headline list.

---

## Pages shipped (17)

**Public**: Landing, Login (UI only).
**Core**: Dashboard, Products, Categories, Suppliers, Purchases, Sales,
Inventory (read-only), Adjustments.
**Intelligence**: Demand Forecasting, Slow-Moving & Dead Stock.
**Insights/Admin**: Reports, Notifications, Users & Roles, Audit Log,
Settings.

All 15 sidebar links resolve to a real page — nothing disabled, nothing
404s.

## Design system

- **Tokens** (`tokens.css`): colors (indigo/amber/ink brand palette +
  success/warning/danger status), 9-step type scale, 10-step spacing
  scale, radius/shadow/motion tokens.
- **Components** (`components.css`): buttons, cards, badges, form fields +
  grid, modal, line-items grid, empty states, spinners.
- **Shell** (`dashboard.css`): sidebar, topbar, KPI cards, panels, widget
  lists, dropdowns.

## Reusable JS architecture (all vanilla, no framework)

| Module | Does |
|---|---|
| `modal.js` | Open/close, ESC, overlay click, focus trap |
| `form-validation.js` | Required/non-negative field validation |
| `modal-form.js` | Wires a form inside a modal to validation + submit/reset |
| `dom-utils.js` | Shared row/action-button builders |
| `mock-catalog.js` + `line-items.js` | Repeatable product line-item editor (Purchases/Sales) |
| `table-filter.js` | Search + select + segmented client-side row filtering |
| `async-run-button.js` | Simulated loading-state buttons |
| `chart-colors.js` | Chart.js palette mirroring CSS tokens |

Every "Add X" modal (Product, Category, Supplier, Purchase, Sale,
Adjustment, User) follows one fixed recipe on top of these — no one-off
modal implementations anywhere.

## Notable builds

- **Modal system + first Add Product flow** — established the pattern
  every later module copied verbatim.
- **Purchase/Sale line-items editor** — repeatable rows with live total
  calculation.
- **Demand Forecasting / Slow-Moving pages** — first real data-viz pages
  (Chart.js), first use of `table-filter.js`.
- **Notification dropdown** — first dropdown component in the app
  (`dashboard.css` + `dashboard.js`), used by the topbar bell.
- **Reports/Audit Log** — first pages combining `table-filter.js` across
  multiple mock tables per page.

## Known frontend debt (see `docs/bugsfound.md` for full detail)

- CSS cascade gotcha (`[hidden]` beaten by classes that set `display`) —
  fixed twice, worth checking on any new toggled element.
- Multi-line Django `{# #}` comments silently render as visible text —
  always use `{% comment %}`.
- `line_total` calc duplicated across JS and the (now-existing) backend —
  not reconciled yet.
- Everything is still static mock data — no page reads from the real
  service layer or database yet (that's the next phase).
