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
