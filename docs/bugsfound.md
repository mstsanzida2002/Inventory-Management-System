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
