# 📚 Claude Code Documentation Index
# AI-Powered Smart Inventory Management System

> **For Claude Code:** Read this file first. Then navigate to the specific markdown file
> for the module or task you are working on. Every file is self-contained with
> models, business rules, API contracts, and implementation notes.
>
> **Single-app divergence, read before the examples below:** every doc
> file's own code examples reference a multi-app Django layout
> (`apps/products/`, `apps/ai/classification/`, `apps/settings_manager/`,
> etc., and this file's own links below used to point at `modules/`/`ai/`/
> `api/`/`setup/`/etc. subdirectories that don't exist). The actual project
> is a **single Django app**, `frontend/`, throughout — every module's
> models/views/services live in `frontend/*.py`, not in a per-module app
> package. This is a deliberate, disclosed architectural choice (see
> `docs/project_memory.md` §13), not an inconsistency to fix — read every
> `apps/<name>/...` import path and subdirectory link in these docs as
> reference material to translate, not a literal path that exists on disk.
> `docs/CODEBASE_MAP.md` is the accurate map of what's actually where.

---

## 🗂️ File Map

All doc files are flat under `docs/` — there is no `modules/`/`ai/`/`api/`/
`setup/`/`database/`/`security/`/`testing/`/`deployment/` subdirectory
structure (an earlier version of this index claimed one; corrected here
per `docs/bugsfound.md` BUG-70, rebuilt from an actual directory listing).

### ⚙️ Setup & Configuration
| File | When to Read |
|---|---|
| [`TECH_STACK.md`](TECH_STACK.md) | Starting the project, installing dependencies, environment config |
| [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) | Creating folder layout, Django app setup |
| [`ENVIRONMENT.md`](ENVIRONMENT.md) | .env variables, settings files, secrets |

### 🗃️ Database
| File | When to Read |
|---|---|
| [`SCHEMA.md`](SCHEMA.md) | All models, fields, relationships, indexes |

No separate `MIGRATIONS.md` exists — migration strategy/ordering, where
covered at all, is inline in `SCHEMA.md` and `docs/project_memory.md`.

### 🧩 Modules (Feature Code)
| File | Module | When to Read |
|---|---|---|
| [`01_AUTH.md`](01_AUTH.md) | Authentication | Login, register, password reset, sessions |
| [`02_RBAC.md`](02_RBAC.md) | Role-Based Access Control | Permissions, decorators, middleware |
| [`03_PRODUCTS.md`](03_PRODUCTS.md) | Products & Categories | CRUD, SKU, barcode, stock monitoring |
| [`05_PURCHASES.md`](05_PURCHASES.md) | Purchase Management | PO workflow, approvals, receiving |
| [`06_SALES.md`](06_SALES.md) | Sales Management | Transactions, invoices, cancellations |
| [`07_INVENTORY.md`](07_INVENTORY.md) | Inventory Management | Real-time tracking, valuation, status |
| [`09_DASHBOARD.md`](09_DASHBOARD.md) | Dashboard | KPIs, charts, role-specific views |
| [`10_REPORTS.md`](10_REPORTS.md) | Reports | All 9 report types, PDF/CSV export |
| [`11_NOTIFICATIONS.md`](11_NOTIFICATIONS.md) | Notifications | In-system + email alerts |
| [`13_AUDIT.md`](13_AUDIT.md) | Audit Logs | Immutable logging, admin access |

**No dedicated doc file exists for Suppliers, Inventory Adjustments,
Search/Filtering, or System Settings** (the old index named
`04_SUPPLIERS.md`, `08_ADJUSTMENTS.md`, `12_SEARCH.md`, `14_SETTINGS.md`
— none of the four ever existed on disk; see `docs/bugsfound.md` BUG-70).
All four features are real and working in the codebase regardless —
Suppliers (`frontend/models.py` `Supplier`, CRUD views in
`frontend/views.py`), Inventory Adjustments (`InventoryAdjustment`,
`AdjustmentService`), search/filtering (client-side `table-filter.js` per
list page, plus the AI-classification `?filter=` param on
`ClassificationListAPIView`), and System Settings (`SystemSettings`,
`SystemSettingsForm`, `/settings/`) — they simply have no dedicated spec
to audit doc-claims against. Use `docs/CODEBASE_MAP.md` and
`docs/SCHEMA.md` for these instead.

### 🤖 AI Modules
| File | When to Read |
|---|---|
| [`DEMAND_FORECASTING.md`](DEMAND_FORECASTING.md) | Building the forecasting pipeline, Scikit-learn model |
| [`DEAD_STOCK_DETECTION.md`](DEAD_STOCK_DETECTION.md) | Two-layer classification: override rules, then the weighted stagnation index |

Both files' own Celery-task reference code is unbuilt — see the
Corrections section below.

### 🔌 API
| File | When to Read |
|---|---|
| [`API_CONTRACTS.md`](API_CONTRACTS.md) | The one real DRF slice (4 read-only AI endpoints) — corrected, see below |

No separate `SERIALIZERS.md`/`PERMISSIONS.md` exists — the two real
serializers and the one real permission class are documented directly in
`API_CONTRACTS.md` and inline in `frontend/serializers.py`/
`frontend/permissions.py`.

### 🔐 Security
| File | When to Read |
|---|---|
| [`SECURITY.md`](SECURITY.md) | All security implementations: HTTPS, CSRF, XSS, SQLi, Argon2 |

### 🧪 Testing
| File | When to Read |
|---|---|
| [`TESTING.md`](TESTING.md) | Test structure, unit/integration/AI test patterns, coverage |

### 🚀 Deployment
| File | When to Read |
|---|---|
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Render setup, static files, env config — Celery-worker steps are reference-only, see below |

### 📝 Project History (not part of the original doc set)
| File | When to Read |
|---|---|
| [`CODEBASE_MAP.md`](CODEBASE_MAP.md) | Read-only navigation guide to the actual `frontend/` app — where things really are |
| [`project_memory.md`](project_memory.md) | Full chronological build history, architecture decisions, design write-ups |
| [`bugsfound.md`](bugsfound.md) | Every bug found, including every documentation-vs-code drift on this list |
| [`frontend_work.md`](frontend_work.md) | Frontend page/component inventory headline list |

---

## 🧠 Quick Decision Guide for Claude Code

```
Working on a new Django model?         → SCHEMA.md
Adding a new API endpoint?             → API_CONTRACTS.md + relevant module file
Implementing permission checks?        → 02_RBAC.md
Building the forecasting pipeline?     → DEMAND_FORECASTING.md
Building dead stock logic?             → DEAD_STOCK_DETECTION.md
Adding notifications?                  → 11_NOTIFICATIONS.md
Writing a report with PDF export?      → 10_REPORTS.md
Setting up the project fresh?          → TECH_STACK.md → PROJECT_STRUCTURE.md → ENVIRONMENT.md
Writing tests?                         → TESTING.md
Deploying to Render?                   → DEPLOYMENT.md
Audit logging a new action?            → 13_AUDIT.md
Finding where something actually lives? → CODEBASE_MAP.md (not the module file's own path examples)
```

---

## 📐 System Overview (Quick Reference)

**Stack:** Django + DRF + PostgreSQL + Scikit-learn + a hand-built vanilla-CSS
design system + Chart.js. **No Celery, no Redis, no scheduler of any
kind** — see Corrections below.

**Roles:** System Administrator · Inventory Supervisor · Inventory Staff

**AI Features:** Demand Forecasting (Scikit-learn) · Slow-Moving & Dead Stock Detection (two-layer: override rules + weighted stagnation index)

**Key Constraints:**
- Inventory quantities NEVER go negative
- Purchase orders require Supervisor approval before stock is received
- Inventory adjustments require Supervisor approval before stock is modified
- Audit logs are IMMUTABLE — never allow update or delete
- All passwords hashed with Argon2
- All API endpoints enforce RBAC before execution

---

## ⚠️ Corrections (documentation-vs-code drift, all in `docs/bugsfound.md`)

- **No Celery, no Redis, no scheduler anywhere in this project.**
  Every `CELERY_BEAT_SCHEDULE`/`@shared_task`/periodic-job claim across
  `11_NOTIFICATIONS.md`, `DEAD_STOCK_DETECTION.md`,
  `DEMAND_FORECASTING.md`, `DEPLOYMENT.md`, and `TECH_STACK.md` is
  reference material only — every real task in this codebase runs
  synchronously, triggered by an actual event or a manual "Run now"
  button. REQ 9.7 and REQ 17.4 (periodic retraining) are consequently
  PHANTOM — disclosed, not built.
- **`API_CONTRACTS.md`** used to document a ~30-endpoint REST surface;
  only 4 read-only AI endpoints actually exist. Corrected.
- **`TECH_STACK.md`** used to name Bootstrap 5.3 as the CSS framework;
  the real frontend is 100% custom vanilla CSS. Corrected.
- **This file** used to reference a `modules/`/`ai/`/`api/`/etc.
  subdirectory structure and 4 module files that never existed. Corrected
  above.
