# 📚 Claude Code Documentation Index
# AI-Powered Smart Inventory Management System

> **For Claude Code:** Read this file first. Then navigate to the specific markdown file
> for the module or task you are working on. Every file is self-contained with
> models, business rules, API contracts, and implementation notes.

---

## 🗂️ File Map

### ⚙️ Setup & Configuration
| File | When to Read |
|---|---|
| [`setup/TECH_STACK.md`](setup/TECH_STACK.md) | Starting the project, installing dependencies, environment config |
| [`setup/PROJECT_STRUCTURE.md`](setup/PROJECT_STRUCTURE.md) | Creating folder layout, Django app setup |
| [`setup/ENVIRONMENT.md`](setup/ENVIRONMENT.md) | .env variables, settings files, secrets |

### 🗃️ Database
| File | When to Read |
|---|---|
| [`database/SCHEMA.md`](database/SCHEMA.md) | All models, fields, relationships, indexes |
| [`database/MIGRATIONS.md`](database/MIGRATIONS.md) | Migration strategy and ordering |

### 🧩 Modules (Feature Code)
| File | Module | When to Read |
|---|---|---|
| [`modules/01_AUTH.md`](modules/01_AUTH.md) | Authentication | Login, register, password reset, sessions |
| [`modules/02_RBAC.md`](modules/02_RBAC.md) | Role-Based Access Control | Permissions, decorators, middleware |
| [`modules/03_PRODUCTS.md`](modules/03_PRODUCTS.md) | Products & Categories | CRUD, SKU, barcode, stock monitoring |
| [`modules/04_SUPPLIERS.md`](modules/04_SUPPLIERS.md) | Supplier Management | CRUD, history, associations |
| [`modules/05_PURCHASES.md`](modules/05_PURCHASES.md) | Purchase Management | PO workflow, approvals, receiving |
| [`modules/06_SALES.md`](modules/06_SALES.md) | Sales Management | Transactions, invoices, cancellations |
| [`modules/07_INVENTORY.md`](modules/07_INVENTORY.md) | Inventory Management | Real-time tracking, valuation, status |
| [`modules/08_ADJUSTMENTS.md`](modules/08_ADJUSTMENTS.md) | Inventory Adjustments | Requests, approvals, audit trail |
| [`modules/09_DASHBOARD.md`](modules/09_DASHBOARD.md) | Dashboard | KPIs, charts, role-specific views |
| [`modules/10_REPORTS.md`](modules/10_REPORTS.md) | Reports | All 9 report types, PDF/CSV export |
| [`modules/11_NOTIFICATIONS.md`](modules/11_NOTIFICATIONS.md) | Notifications | In-system + email alerts |
| [`modules/12_SEARCH.md`](modules/12_SEARCH.md) | Search & Filtering | Global search, filters, AI classification filter |
| [`modules/13_AUDIT.md`](modules/13_AUDIT.md) | Audit Logs | Immutable logging, admin access |
| [`modules/14_SETTINGS.md`](modules/14_SETTINGS.md) | System Settings | Company info, thresholds, AI config |

### 🤖 AI Modules
| File | When to Read |
|---|---|
| [`ai/DEMAND_FORECASTING.md`](ai/DEMAND_FORECASTING.md) | Building the forecasting pipeline, Scikit-learn model, Celery tasks |
| [`ai/DEAD_STOCK_DETECTION.md`](ai/DEAD_STOCK_DETECTION.md) | Classification logic, business rules, detection tasks |

### 🔌 API
| File | When to Read |
|---|---|
| [`api/API_CONTRACTS.md`](api/API_CONTRACTS.md) | All DRF endpoints, request/response shapes, status codes |
| [`api/SERIALIZERS.md`](api/SERIALIZERS.md) | Serializer patterns, validation rules |
| [`api/PERMISSIONS.md`](api/PERMISSIONS.md) | DRF permission classes, custom permission logic |

### 🔐 Security
| File | When to Read |
|---|---|
| [`security/SECURITY.md`](security/SECURITY.md) | All security implementations: HTTPS, CSRF, XSS, SQLi, Argon2 |

### 🧪 Testing
| File | When to Read |
|---|---|
| [`testing/TESTING.md`](testing/TESTING.md) | Test structure, unit/integration/AI test patterns, coverage |

### 🚀 Deployment
| File | When to Read |
|---|---|
| [`deployment/DEPLOYMENT.md`](deployment/DEPLOYMENT.md) | Render setup, Celery workers, static files, env config |

---

## 🧠 Quick Decision Guide for Claude Code

```
Working on a new Django model?         → database/SCHEMA.md
Adding a new API endpoint?             → api/API_CONTRACTS.md + relevant module file
Implementing permission checks?        → modules/02_RBAC.md + api/PERMISSIONS.md
Building the forecasting pipeline?     → ai/DEMAND_FORECASTING.md
Building dead stock logic?             → ai/DEAD_STOCK_DETECTION.md
Writing Celery tasks?                  → ai/DEMAND_FORECASTING.md (has task patterns)
Adding notifications?                  → modules/11_NOTIFICATIONS.md
Writing a report with PDF export?      → modules/10_REPORTS.md
Setting up the project fresh?          → setup/TECH_STACK.md → setup/PROJECT_STRUCTURE.md → setup/ENVIRONMENT.md
Writing tests?                         → testing/TESTING.md
Deploying to Render?                   → deployment/DEPLOYMENT.md
Implementing search/filter?            → modules/12_SEARCH.md
Audit logging a new action?            → modules/13_AUDIT.md
```

---

## 📐 System Overview (Quick Reference)

**Stack:** Django + DRF + PostgreSQL + Redis + Celery + Scikit-learn + Bootstrap 5 + Chart.js

**Roles:** System Administrator · Inventory Supervisor · Inventory Staff

**AI Features:** Demand Forecasting (Scikit-learn) · Slow-Moving & Dead Stock Detection (rule-based + analytics)

**Key Constraints:**
- Inventory quantities NEVER go negative
- Purchase orders require Supervisor approval before stock is received
- Inventory adjustments require Supervisor approval before stock is modified
- Audit logs are IMMUTABLE — never allow update or delete
- All passwords hashed with Argon2
- All API endpoints enforce RBAC before execution
