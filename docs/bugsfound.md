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
| BUG-13 | Redundant `models.Index` on already-`unique=True` fields | `SCHEMA.md` §1 User, §4 Product | 🚩 Reported |
| BUG-14 | `Product.category`/`Product.supplier` both `related_name='products'` | `SCHEMA.md` §4 Product | 🚩 Reported |
| BUG-15 | `InventoryClassification.classified_at` duplicates inherited `updated_at` | `SCHEMA.md` §10 InventoryClassification | 🚩 Reported |
| BUG-16 | `INDEX.md`'s File Map links to subfolders that don't exist | `INDEX.md` (entire File Map table) | 🚩 Reported |
| BUG-17 | 8 files `INDEX.md` references don't exist on disk | `INDEX.md` (File Map table) | 🚩 Reported |
| BUG-18 | `SystemSettingsAdmin.has_add_permission` DB query broke entire `/admin/` index | N/A — self-introduced this project, no doc specifies admin config | 🔧 Fixed same phase |
| BUG-19 | Deleting any `auth.User` crashes (cascade collector hits unmigrated tables) | `SCHEMA.md` (indirectly — every model's `settings.AUTH_USER_MODEL` FK) + zero migrations | 🚩 Reported |
| BUG-20 | `InventoryMovement` "immutable ledger" is a docstring only, not code-enforced | `SCHEMA.md` §7 InventoryMovement | 🚩 Reported |
| BUG-21 | `SystemSettings` "singleton" not enforced at the model level | `SCHEMA.md` §13 SystemSettings | 🚩 Reported |
| BUG-22 | "System settingss" double-s typo in admin (no `verbose_name_plural`) | `SCHEMA.md` §13 SystemSettings (no verbose_name given) | 🚩 Reported |
| BUG-23 | `SaleService`: `Decimal * float TypeError` on default discount/tax | `06_SALES.md` (`SaleService.create_sale`) | ✅ Fixed |
| BUG-24 | `PurchaseOrderItem.save()`: identical `Decimal * float TypeError` | `SCHEMA.md` §5 PurchaseOrderItem | ✅ Fixed |
| BUG-25 | `PurchaseService.cancel()` documented but missing from the doc's own code sample | `05_PURCHASES.md` (state machine + business rules vs. Service Layer code block) | 🚩 Reported |
| BUG-26 | No `docs/08_ADJUSTMENTS.md` exists at all | `INDEX.md` references it; file missing from disk | 🚩 Reported |

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
**Status:** 🚩 Reported, not fixed — implemented literally as documented.

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
**Status:** 🚩 Reported, not fixed — resolves automatically once
migrations are applied to the real database. Worked around during Phase 2
verification with a raw SQL delete for a throwaway test superuser.

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
**Status:** 🚩 Reported, not fixed at the model level. Mitigated at the
admin layer only (`has_change_permission`/`has_delete_permission`
disabled in `InventoryMovementAdmin`) — direct ORM code can still mutate it.

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
**Status:** 🚩 Reported, not fixed at the model level. Mitigated at the
admin layer only (`has_add_permission` blocks a second row through
`/admin/` — see BUG-18 for the bug that mitigation itself introduced).

### BUG-22 — "System settingss" double-s typo in admin
**Root cause:** `SystemSettings` has no `verbose_name`/`verbose_name_plural`
set in its `Meta`, so Django's default auto-pluralization (appending "s"
to the auto-derived verbose name "System settings") renders "System
settingss" in the admin index.
**Source Documentation:** `SCHEMA.md` §13 SystemSettings `Meta` block
(`db_table` only, no `verbose_name`/`verbose_name_plural` given).
**Status:** 🚩 Reported, not fixed — cosmetic, `models.py` out of scope
for Phase 2.

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
**Status:** 🚩 Reported, not implemented — the state machine and the
reference code disagree with each other within the same document.

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
