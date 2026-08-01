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
from django import forms

from frontend.models import Category, Product, Supplier, UnitOfMeasurement
from frontend.validators import validate_product_image


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
