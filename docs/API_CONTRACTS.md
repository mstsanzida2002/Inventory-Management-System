# 🔌 API Contracts
# AI-Powered Smart Inventory Management System

> **Claude Code:** Reference this when building or consuming any DRF endpoint.
> All endpoints are prefixed `/api/v1/`. All require authentication unless noted.
> Role requirements are listed per endpoint.

---

## Auth Endpoints

| Method | Endpoint | Role | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login/` | Public | Login with username/email + password |
| POST | `/api/v1/auth/logout/` | Any | Logout |
| GET | `/api/v1/auth/profile/` | Any | Get own profile |
| PUT | `/api/v1/auth/profile/update/` | Any | Update own profile |
| POST | `/api/v1/auth/password-change/` | Any | Change password |
| POST | `/api/v1/auth/password-reset/` | Public | Request password reset email |

**Login Request:**
```json
{ "identifier": "admin_user", "password": "SecurePass123!" }
```
**Login Response (200):**
```json
{ "message": "Login successful", "role": "admin", "full_name": "John Doe" }
```
**Login Response (401):**
```json
{ "error": "Invalid credentials." }
```
**Login Response (423):**
```json
{ "error": "Account locked until 2024-01-15 10:30:00." }
```

---

## User Management Endpoints (Admin Only)

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/users/` | Admin | List all users |
| POST | `/api/v1/users/` | Admin | Create user |
| GET | `/api/v1/users/{id}/` | Admin | Get user detail |
| PUT | `/api/v1/users/{id}/` | Admin | Update user |
| PATCH | `/api/v1/users/{id}/deactivate/` | Admin | Deactivate user |
| PATCH | `/api/v1/users/{id}/reactivate/` | Admin | Reactivate user |

---

## Product Endpoints

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/products/` | Any | List products (active only) |
| POST | `/api/v1/products/` | Admin/Supervisor | Create product |
| GET | `/api/v1/products/{id}/` | Any | Product detail |
| PUT | `/api/v1/products/{id}/` | Admin/Supervisor | Update product |
| PATCH | `/api/v1/products/{id}/status/` | Admin/Supervisor | Toggle active/inactive |

**Query Params:** `?q=search_term&category=id&supplier=id&status=active|inactive`

**Product Create Request:**
```json
{
  "sku": "SKU-001",
  "barcode": "8901234567890",
  "name": "Product Name",
  "category": 1,
  "supplier": 2,
  "purchase_price": "150.00",
  "selling_price": "200.00",
  "reorder_level": 20,
  "unit": "pcs"
}
```

---

## Purchase Order Endpoints

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/purchases/` | Any | List POs |
| POST | `/api/v1/purchases/` | Any | Create PO (draft) |
| GET | `/api/v1/purchases/{id}/` | Any | PO detail |
| POST | `/api/v1/purchases/{id}/submit/` | Any | Submit for approval |
| POST | `/api/v1/purchases/{id}/approve/` | Supervisor+ | Approve PO |
| POST | `/api/v1/purchases/{id}/reject/` | Supervisor+ | Reject PO |
| POST | `/api/v1/purchases/{id}/receive/` | Any | Receive items |
| POST | `/api/v1/purchases/{id}/cancel/` | Supervisor+ | Cancel PO |

**Receive Request:**
```json
{
  "items": [
    { "item_id": 1, "received_qty": 50 },
    { "item_id": 2, "received_qty": 25 }
  ]
}
```

**Reject Request:**
```json
{ "reason": "Price mismatch with quotation." }
```

---

## Sales Endpoints

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/sales/` | Any | List sales |
| POST | `/api/v1/sales/` | Any | Create sale |
| GET | `/api/v1/sales/{id}/` | Any | Sale detail |
| POST | `/api/v1/sales/{id}/cancel/` | Supervisor+ | Cancel sale |

**Sale Create Request:**
```json
{
  "customer_name": "Acme Corp",
  "notes": "Bulk order",
  "items": [
    { "product_id": 5, "quantity": 10, "unit_price": "200.00", "discount": 5, "tax": 0 }
  ]
}
```

**Sale Create Response (201):**
```json
{
  "id": 42,
  "invoice_number": "INV-20240115-3421",
  "total_amount": "1900.00",
  "status": "completed"
}
```

**Insufficient Stock Response (400):**
```json
{ "error": "Insufficient stock for 'Product Name'. Available: 5, Requested: 10" }
```

---

## Inventory Endpoints

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/inventory/` | Any | List all inventory records |
| GET | `/api/v1/inventory/{product_id}/` | Any | Product inventory detail |
| GET | `/api/v1/inventory/{product_id}/movements/` | Any | Stock movement history |
| GET | `/api/v1/inventory/stats/` | Any | Aggregate stats for dashboard |
| GET | `/api/v1/inventory/low-stock/` | Any | Low stock items |
| GET | `/api/v1/inventory/out-of-stock/` | Any | Out of stock items |

**Query Params:** `?status=available|low_stock|out_of_stock&q=search`

---

## Inventory Adjustment Endpoints

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/adjustments/` | Any | List adjustments |
| POST | `/api/v1/adjustments/` | Any | Create adjustment request |
| GET | `/api/v1/adjustments/{id}/` | Any | Adjustment detail |
| POST | `/api/v1/adjustments/{id}/approve/` | Supervisor+ | Approve adjustment |
| POST | `/api/v1/adjustments/{id}/reject/` | Supervisor+ | Reject adjustment |

**Create Request:**
```json
{
  "product": 5,
  "adjustment_type": "increase",
  "quantity": 50,
  "reason": "Physical count reconciliation — 50 units found in overflow storage."
}
```

---

## AI Endpoints

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/ai/forecasts/` | Supervisor+ | All forecasts |
| GET | `/api/v1/ai/forecasts/{product_id}/` | Supervisor+ | Product forecasts |
| POST | `/api/v1/ai/forecasts/run/` | Supervisor+ | Trigger forecast task |
| GET | `/api/v1/ai/classifications/` | Supervisor+ | All classifications |
| GET | `/api/v1/ai/classifications/summary/` | Supervisor+ | Summary counts |
| POST | `/api/v1/ai/classifications/run/` | Supervisor+ | Trigger classification task |

**Query Params for classifications:** `?filter=fast|slow|dead`

---

## Report Endpoints

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/reports/inventory/` | Supervisor+ | Inventory report |
| GET | `/api/v1/reports/purchases/` | Supervisor+ | Purchase report |
| GET | `/api/v1/reports/sales/` | Supervisor+ | Sales report |
| GET | `/api/v1/reports/movements/` | Supervisor+ | Movement report |
| GET | `/api/v1/reports/adjustments/` | Supervisor+ | Adjustment report |
| GET | `/api/v1/reports/low-stock/` | Supervisor+ | Low stock report |
| GET | `/api/v1/reports/out-of-stock/` | Supervisor+ | Out of stock report |
| GET | `/api/v1/reports/ai-forecasts/` | Supervisor+ | AI forecast report |
| GET | `/api/v1/reports/ai-classifications/` | Supervisor+ | AI classification report |

**Common Query Params:** `?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&category=id&supplier=id&format=pdf|csv`

---

## Notification Endpoints

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/notifications/` | Any | List own notifications |
| PATCH | `/api/v1/notifications/{id}/read/` | Any | Mark as read |
| PATCH | `/api/v1/notifications/mark-all-read/` | Any | Mark all as read |

---

## Dashboard Endpoints

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/v1/dashboard/stats/` | Any | KPI metrics |
| GET | `/api/v1/dashboard/charts/` | Any | Chart data |

**Stats Response:**
```json
{
  "total_products": 450,
  "total_suppliers": 32,
  "total_inventory_value": "1250000.00",
  "low_stock_count": 12,
  "out_of_stock_count": 3,
  "pending_po_approvals": 5,
  "pending_adjustments": 2,
  "today_sales_total": "45000.00",
  "monthly_sales_total": "980000.00"
}
```

---

## Standard HTTP Status Codes

| Code | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 204 | No Content (delete/deactivate) |
| 400 | Bad Request (validation error) |
| 401 | Unauthorized (not logged in) |
| 403 | Forbidden (logged in but wrong role) |
| 404 | Not Found |
| 409 | Conflict (duplicate SKU, etc.) |
| 423 | Locked (account lockout) |
| 500 | Internal Server Error |

---

## Standard Error Response Shape

```json
{
  "error": "Human-readable error message.",
  "details": {
    "field_name": ["Specific validation error."]
  }
}
```

## Standard List Response Shape

```json
{
  "count": 150,
  "next": "http://domain/api/v1/products/?page=2",
  "previous": null,
  "results": [...]
}
```
