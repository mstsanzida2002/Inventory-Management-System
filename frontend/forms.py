"""
docs/03_PRODUCTS.md's business-rules table, enforced server-side (Phase 5).
The Add Product modal in products/products.html is hand-built HTML, not
`{{ form.* }}` rendering — this form exists for real validation only, its
field ids already match the template's existing input ids/names.

Cross-checked every model field's blank/required state against what the
existing mock UI already labeled "(optional)"/required, and reconciled the
two directions found:
  - Supplier had no `blank=True` on the model (and 03_PRODUCTS.md's own
    business rules say "Supplier | Required, must be active") but the mock
    UI labeled it optional — fixed by making it required in the template
    (frontend/templates/products/products.html) instead of loosening the
    form.
  - `unit`/`reorder_level` both have model-level `default=`s but no
    `blank=True`, which would otherwise make Django's ModelForm require
    them despite the UI already treating them as optional with a sensible
    fallback — fixed here by explicitly making them not required and
    falling back to the same default the model itself declares.
"""
from decimal import Decimal, InvalidOperation
import json

from django import forms
from django.contrib.auth.password_validation import validate_password

from frontend.models import (
    Category,
    InventoryAdjustment,
    Product,
    PurchaseOrder,
    SaleTransaction,
    Supplier,
    SystemSettings,
    UnitOfMeasurement,
    User,
)
from frontend.validators import validate_product_image

# Category/Supplier's mock modal already has a real Active/Inactive
# <select name="status">, matching each model's is_active BooleanField
# 1:1, but as text choices rather than a checkbox. Kept as-is (not
# converted to a checkbox) rather than changing existing template markup
# — `status` is a form-only field on each form below, consumed by the
# view to set instance.is_active, exactly like ProductForm.initial_stock
# was a form-only field consumed by the view (Phase 5).
STATUS_CHOICES = [("Active", "Active"), ("Inactive", "Inactive")]


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "sku", "barcode", "category", "supplier", "brand",
            "unit", "purchase_price", "selling_price", "reorder_level",
            "description", "image",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # SKU auto-generates if left blank (03_PRODUCTS.md: "Unique,
        # auto-generated if not provided: PRD-YYYYMMDD-XXXX").
        self.fields["sku"].required = False
        # Already blank=True/null=True on the model; explicit for clarity
        # alongside the other optional-field overrides below.
        self.fields["barcode"].required = False
        # UI already treats these as optional with a sensible fallback —
        # see class docstring.
        self.fields["unit"].required = False
        self.fields["reorder_level"].required = False
        self.fields["image"].validators.append(validate_product_image)
        # 03_PRODUCTS.md: "Category | Required, must be active" / "Supplier
        # | Required, must be active" — restrict the valid choice sets
        # server-side too, not just in the template's rendered <option>
        # list (a tampered POST with an inactive category/supplier id must
        # still be rejected).
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip()
        return sku or self._generate_sku()

    def clean_barcode(self):
        barcode = (self.cleaned_data.get("barcode") or "").strip()
        return barcode or None

    def clean_unit(self):
        return self.cleaned_data.get("unit") or UnitOfMeasurement.PIECE

    def clean_reorder_level(self):
        value = self.cleaned_data.get("reorder_level")
        return value if value is not None else 10

    def clean_purchase_price(self):
        value = self.cleaned_data.get("purchase_price")
        if value is not None and value < 0:
            raise forms.ValidationError("Purchase price cannot be negative.")
        return value

    def clean_selling_price(self):
        value = self.cleaned_data.get("selling_price")
        if value is not None and value < 0:
            raise forms.ValidationError("Selling price cannot be negative.")
        return value

    @staticmethod
    def _generate_sku():
        # Same random-suffix pattern PurchaseOrder/SaleTransaction already
        # use for po_number/invoice_number (frontend/models.py) — no
        # retry-on-collision loop there either; matched for consistency.
        from django.utils import timezone
        import random
        return f"PRD-{timezone.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


class CategoryForm(forms.ModelForm):
    """Phase 6 — mirrors ProductForm's pattern. The mock modal
    (categories/categories.html) also had "Parent category" and
    "Category code" fields with no corresponding model field anywhere in
    SCHEMA.md (no hierarchy, no code column on Category) — removed from
    the template rather than invented as new model fields, per this
    phase's explicit instruction."""
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, initial="Active")

    class Meta:
        model = Category
        fields = ["name", "description"]


class SupplierForm(forms.ModelForm):
    """Phase 6 — mirrors ProductForm's pattern. No dedicated Suppliers doc
    exists (project_memory.md §12/§17); built from SCHEMA.md's Supplier
    model plus the existing suppliers.html mock, reconciling two kinds of
    mismatch found between them (same treatment as BUG-31's Product fix):

    1. Every one of supplier_name/company_name/contact_person/email/
       phone/address has no `blank=True` on the model — all genuinely
       required — but the mock UI labeled contact_person/email/phone/
       address "(optional)". Fixed by making them required in the
       template, not by loosening the form.
    2. The mock had one "Supplier name" field but the model has two
       distinct required name fields (supplier_name AND company_name,
       used together in Supplier.__str__). Mapped the existing field to
       supplier_name (matches by field name, the least presumptive
       reading) and added a new required "Company name" field for
       company_name, rather than guessing which one the single mock
       field "really" meant.
    3. The mock's code/city/country/postal_code/website/tax_id/notes
       fields have no corresponding model field anywhere in SCHEMA.md —
       removed from the template rather than invented as new columns.
       The mock's single free-text address model field also doesn't
       decompose into street/city/country/postal code, so the mock's
       four separate address inputs were collapsed into the one real
       `address` field.
    """
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, initial="Active")

    class Meta:
        model = Supplier
        fields = ["supplier_name", "company_name", "contact_person", "email", "phone", "address"]


# ---------------------------------------------------------------- Phase 7
# Purchases/Sales/Adjustments. Unlike Products/Categories/Suppliers, the
# existing purchases.html/sales.html/adjustments.html mock modals were
# already field-correct against SCHEMA.md — each one's own template
# comment already cites the exact model fields it's built from, and
# checking field-by-field found no BUG-31/BUG-35-style mismatch here (see
# docs/bugsfound.md's Phase 7 entry for the full check). The real gap was
# elsewhere: mock-catalog.js's product/supplier <option value="..."> used
# each item's *name* as the value, since no real Product/Supplier table
# existed when it was built — now that one does (Phase 5/6), the real
# templates render real Product/Supplier <option value="{{ pk }}">
# instead, and mock-catalog.js is retired (see frontend/views.py).


def parse_line_items(raw_json, min_quantity=1):
    """Shared by PurchaseOrderForm/SaleTransactionForm's item validation.
    line-items.js (kept exactly as-is per this phase's instruction) is
    unaware of any of this — it just POSTs whatever HTML the product
    <select> options carry as their value attribute back as
    item['productLabel']. Since the real templates now render those
    options with the product's real pk as the value (not its name, the
    way mock-catalog.js did), 'productLabel' is a product pk string here,
    not a display name — read literally as one, not renamed, since
    renaming would suggest line-items.js's own wire format changed, and
    it didn't.

    Returns (items, errors): items is a list of dicts with real Product
    instances and Decimal-coerced discount/tax (same coercion
    InventoryService/PurchaseOrderItem.save() already do — see BUG-23/24);
    errors is a list of user-facing strings, empty if items is usable.
    """
    try:
        raw_items = json.loads(raw_json or "[]")
    except (ValueError, TypeError):
        return [], ["Line items could not be read. Please try again."]

    if not isinstance(raw_items, list) or not raw_items:
        return [], ["At least one line item is required."]

    errors = []
    parsed = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            errors.append(f"Line {index}: malformed line item.")
            continue

        try:
            product = Product.objects.get(pk=raw.get("productLabel"), is_active=True)
        except (Product.DoesNotExist, ValueError, TypeError):
            errors.append(f"Line {index}: product is invalid or no longer active.")
            continue

        try:
            quantity = int(raw.get("quantity"))
        except (TypeError, ValueError):
            quantity = None
        if quantity is None or quantity < min_quantity:
            errors.append(f"Line {index}: quantity must be at least {min_quantity}.")
            continue

        try:
            unit_price = Decimal(str(raw.get("unitPrice")))
        except (InvalidOperation, TypeError, ValueError):
            unit_price = None
        if unit_price is None or unit_price < 0:
            errors.append(f"Line {index}: unit price cannot be negative.")
            continue

        try:
            discount = Decimal(str(raw.get("discount") or 0))
            tax = Decimal(str(raw.get("tax") or 0))
        except InvalidOperation:
            errors.append(f"Line {index}: discount/tax must be numeric.")
            continue
        if discount < 0 or tax < 0:
            errors.append(f"Line {index}: discount/tax cannot be negative.")
            continue

        parsed.append({
            "product": product, "quantity": quantity,
            "unit_price": unit_price, "discount": discount, "tax": tax,
        })

    return parsed, errors


class PurchaseOrderForm(forms.ModelForm):
    """Header fields only — line items arrive separately as items_json,
    parsed by parse_line_items() (PurchaseOrderItem rows aren't part of a
    ModelForm here since there's no formset in play; matches how
    ProductForm.initial_stock/CategoryForm.status are already form-only
    fields consumed directly by the view, Phase 5/6). expected_delivery/
    notes match the model's own null=True/blank=True — genuinely optional,
    not a mismatch to fix."""

    class Meta:
        model = PurchaseOrder
        fields = ["supplier", "expected_delivery", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expected_delivery"].required = False
        self.fields["notes"].required = False
        # 05_PURCHASES.md: "Inactive supplier | Cannot create PO for
        # inactive supplier."
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)


class SaleTransactionForm(forms.ModelForm):
    """Header fields only, same split as PurchaseOrderForm above.
    customer_name/notes are both genuinely optional on the model
    (blank=True) — matches 06_SALES.md's "Customer info | Optional" rule
    exactly, no mismatch to fix. No status field here (unlike Category/
    Supplier) — SaleTransaction.status defaults to COMPLETED and the
    documented workflow has no draft/pending state for a sale; setting it
    is SaleService.cancel_sale()'s job, not this form's."""

    class Meta:
        model = SaleTransaction
        fields = ["customer_name", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer_name"].required = False
        self.fields["notes"].required = False


class AdjustmentForm(forms.ModelForm):
    """product/adjustment_type/quantity/reason match InventoryAdjustment
    field-for-field already — the mock's own template comment already
    cites this exact field list, and checking against SCHEMA.md found no
    mismatch. Deliberately did NOT restrict the product queryset to
    is_active=True the way Product/Purchase/Sale forms do: no documented
    rule (SCHEMA.md, or otherwise) says an adjustment can only target an
    active product, and correcting a stale count on a product being
    deactivated is a legitimate real-world reason for one — not inventing
    a restriction the docs don't state."""

    class Meta:
        model = InventoryAdjustment
        fields = ["product", "adjustment_type", "quantity", "reason"]

    def clean_quantity(self):
        # PositiveIntegerField's own form field allows 0, but an
        # adjustment of exactly 0 units is a no-op, not a real request —
        # same "reject a technically-valid-but-meaningless value" call as
        # parse_line_items()'s min_quantity=1 above.
        value = self.cleaned_data.get("quantity")
        if value is not None and value <= 0:
            raise forms.ValidationError("Quantity must be greater than zero.")
        return value


# ---------------------------------------------------------------- Phase 8
# Users & Roles / Settings. No dedicated doc for either (project_memory.md
# §12/§17) — built from SCHEMA.md's User/SystemSettings models plus the
# existing users.html/settings.html mocks.


class UserForm(forms.ModelForm):
    """The users.html mock's own template comment explicitly says password
    is "deliberately NOT a form field here" (a Phase 3.6-era call made
    before this page had a real backend to submit to at all). That's no
    longer tenable now that this creates a real, real User row: a User
    saved without ever calling set_password() gets Django's
    set_unusable_password() by default (AbstractBaseUser.set_password(None)),
    which means the account could never log in — a genuinely broken admin
    tool, not a faithful "keep the mock's field list" translation. Adding
    a required password field here is a disclosed judgment call, not a
    silent deviation: same category of call as Supplier's added "Company
    name" field (Phase 6) or Purchase's added Submit button (Phase 7) —
    the mock was missing something the real feature cannot work without.
    Reuses the exact same StrongPasswordValidator/AUTH_PASSWORD_VALIDATORS
    stack profile_view already runs a changed password through (Phase 4).
    """

    password = forms.CharField(widget=forms.PasswordInput, min_length=8)

    class Meta:
        model = User
        fields = ["full_name", "username", "employee_id", "email", "role"]

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        validate_password(password)
        return password


class SystemSettingsForm(forms.ModelForm):
    """settings.html's mock already lists exactly SystemSettings' own
    fields (its own template comment says so, and checking against
    SCHEMA.md §13 found no mismatch) — every field below maps 1:1, nothing
    invented, nothing dropped."""

    class Meta:
        model = SystemSettings
        fields = [
            "company_name", "company_logo", "company_address", "company_email", "company_phone",
            "default_reorder_level", "forecast_period_weeks", "forecast_retrain_days",
            "slow_moving_threshold_days", "dead_stock_threshold_days", "session_timeout_seconds",
            "email_notifications_enabled", "low_stock_email_enabled",
        ]

    # PositiveIntegerFields with no blank=True on the model (same shape as
    # ProductForm.reorder_level, Phase 5) — left required=False below so a
    # blank submission doesn't hard-fail, but unlike a create-only form
    # like ProductForm, this is always an *update* of the one singleton
    # row (SystemSettingsForm is only ever instantiated with instance=),
    # so "left blank" falls back to the row's own current value, not a
    # hardcoded model default — falling back to the class default here
    # would silently blank out a real admin-configured value on every
    # save that happens to omit a field.
    _FALLBACK_TO_INSTANCE_FIELDS = [
        "company_name", "default_reorder_level", "forecast_period_weeks",
        "forecast_retrain_days", "slow_moving_threshold_days",
        "dead_stock_threshold_days", "session_timeout_seconds",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.fields:
            self.fields[name].required = False
        self.fields["company_logo"].validators.append(validate_product_image)

    def clean(self):
        cleaned = super().clean()
        for name in self._FALLBACK_TO_INSTANCE_FIELDS:
            if not cleaned.get(name):
                cleaned[name] = getattr(self.instance, name)
        return cleaned


class ReasonForm(forms.Form):
    """Shared by PurchaseOrder.reject and InventoryAdjustment.reject —
    both services require a non-empty reason (PurchaseService.reject()'s
    `reason` param feeds PurchaseOrder.rejected_reason, a required-content
    TextField in practice even though blank=True at the model level; same
    for InventoryAdjustment.rejected_reason). One shared form instead of
    two identical ones."""
    reason = forms.CharField(widget=forms.Textarea, min_length=1, error_messages={
        "required": "A reason is required.",
        "min_length": "A reason is required.",
    })
