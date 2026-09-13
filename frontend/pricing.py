from decimal import Decimal


def calculate_line_total(unit_price, quantity, discount=0, tax=0):
    """(price*qty)*(1-discount%)*(1+tax%); all inputs coerced to Decimal."""
    unit_price = Decimal(str(unit_price))
    quantity = Decimal(str(quantity))
    discount = Decimal(str(discount))
    tax = Decimal(str(tax))
    return (unit_price * quantity) * (1 - discount / 100) * (1 + tax / 100)


def calculate_totals_breakdown(items):
    """Subtotal/discount/tax/grand-total, derived from each item's own fields."""
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
