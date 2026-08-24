"""
Phase 8.98c — the one shared place the line_total formula lives, used by
both `PurchaseOrderItem.save()` (frontend/models.py) and
`SaleService.create_sale()` (frontend/services.py). Before this, the exact
same formula was duplicated in both places (flagged as frontend debt in
project_memory.md long before this — see §12 technical debt) — this module
doesn't touch stock/ledger logic at all, it's pure money math, so it lives
on its own rather than inside services.py (which frontend/models.py can't
import without a circular import — services.py already imports from
models.py).
"""
from decimal import Decimal


def calculate_line_total(unit_price, quantity, discount=0, tax=0):
    """(unit_price * quantity) * (1 - discount%) * (1 + tax%), matching
    SCHEMA.md's own PurchaseOrderItem/SaleItem reference formula exactly.
    Coerces every input to Decimal first — a plain int/float default (0)
    divided by 100 produces a float, and Decimal * float raises TypeError
    (SCHEMA.md's own reference code has this same bug, see BUG-23/24)."""
    unit_price = Decimal(str(unit_price))
    quantity = Decimal(str(quantity))
    discount = Decimal(str(discount))
    tax = Decimal(str(tax))
    return (unit_price * quantity) * (1 - discount / 100) * (1 + tax / 100)


def calculate_totals_breakdown(items):
    """Phase 13 — a Subtotal/Discount/Tax/Grand Total breakdown for the
    PDF totals block (generate_purchase_order_pdf/generate_sale_transaction_pdf,
    frontend/reports.py), reconstructed from calculate_line_total()'s own
    formula rather than stored anywhere: PurchaseOrderItem/SaleItem only
    ever persist the final `line_total`, not the pre-discount/pre-tax
    breakdown. `items`: any iterable of objects with unit_price/quantity/
    discount/tax/line_total attributes (both item models share this exact
    shape). Returns (subtotal, discount_total, tax_total, grand_total) as
    Decimals — subtotal - discount_total + tax_total == grand_total
    exactly, by construction, since every figure here is derived from the
    same per-item formula line_total already uses."""
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    tax_total = Decimal("0")
    grand_total = Decimal("0")
    for item in items:
        unit_price = Decimal(str(item.unit_price))
        quantity = Decimal(str(item.quantity if hasattr(item, "quantity") else item.ordered_qty))
        discount = Decimal(str(item.discount))
        tax = Decimal(str(item.tax))
        gross = unit_price * quantity
        after_discount = gross * (1 - discount / 100)
        line_total = Decimal(str(item.line_total))
        subtotal += gross
        discount_total += gross - after_discount
        tax_total += line_total - after_discount
        grand_total += line_total
    return subtotal, discount_total, tax_total, grand_total
