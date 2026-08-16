"""
Phase 8.98c — dev-environment convenience command: wipes the whole dev
database and reseeds it with a small, realistic dataset built on the new
Product.tax_rate model (varied tax rates, including 0% — the field's own
default — so both the "no tax" and "has tax" cases are exercised).

Per this phase's own instruction ("Existing dev records are disposable —
this is a fresh-start refactor... No historical-data migration needed"),
this does not try to migrate/backfill old PurchaseOrderItem/SaleItem rows
that had a form-entered tax value — it wipes everything and starts over so
every row in the reseeded DB is consistent with the new model.

All stock/ledger data is produced by going through the real service layer
(PurchaseService/SaleService/AdjustmentService/InventoryService, frontend/
services.py) exactly as the views do — never by setting current_stock or
writing InventoryMovement rows directly — so the reseeded data is a
realistic, ledger-consistent starting point, not a shortcut around the
same rules real usage is bound by.

Refuses to run when DEBUG is False, same guard as seed_test_users.py: a
full-database flush must never be reachable against a real deployment.
"""
from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from frontend.models import (
    AdjustmentType,
    Category,
    InventoryAdjustment,
    POStatus,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    UnitOfMeasurement,
    User,
)
from frontend.services import AdjustmentService, InventoryService, PurchaseService, SaleService

CATEGORIES = [
    {"name": "Electronics", "description": "Consumer electronics and accessories."},
    {"name": "Groceries", "description": "Packaged food and household consumables."},
    {"name": "Stationery", "description": "Office and school supplies."},
    {"name": "Home & Kitchen", "description": "Kitchenware and home goods."},
]

SUPPLIERS = [
    {
        "supplier_name": "Brightline Traders", "company_name": "Brightline Traders Ltd",
        "contact_person": "Farhan Rahman", "email": "farhan@brightline.example",
        "phone": "+880-1711-000001", "address": "House 12, Road 5, Banani, Dhaka",
    },
    {
        "supplier_name": "Meridian Wholesale", "company_name": "Meridian Wholesale Co",
        "contact_person": "Priya Sen", "email": "priya@meridian.example",
        "phone": "+880-1711-000002", "address": "Plot 44, Tejgaon Industrial Area, Dhaka",
    },
    {
        "supplier_name": "Coastal Supply Co", "company_name": "Coastal Supply Co",
        "contact_person": "Imran Chowdhury", "email": "imran@coastal.example",
        "phone": "+880-1711-000003", "address": "22 Agrabad Commercial Area, Chattogram",
    },
]

# (name, category, supplier index, unit, purchase_price, selling_price, tax_rate, reorder_level)
PRODUCTS = [
    ("Wireless Mouse", "Electronics", 0, UnitOfMeasurement.PIECE, "8.50", "15.00", "10.00", 15),
    ("USB-C Charging Cable 1m", "Electronics", 0, UnitOfMeasurement.PIECE, "2.20", "5.00", "10.00", 25),
    ("Bluetooth Speaker", "Electronics", 1, UnitOfMeasurement.PIECE, "18.00", "32.00", "15.00", 10),
    ("Basmati Rice 5kg", "Groceries", 1, UnitOfMeasurement.PACK, "6.50", "9.50", "0.00", 20),
    ("Cooking Oil 1L", "Groceries", 1, UnitOfMeasurement.LITER, "1.80", "2.75", "5.00", 30),
    ("A4 Copy Paper Ream", "Stationery", 2, UnitOfMeasurement.PACK, "3.10", "4.75", "7.50", 20),
    ("Ballpoint Pen (Box of 12)", "Stationery", 2, UnitOfMeasurement.BOX, "1.40", "2.50", "7.50", 15),
    ("Non-Stick Frying Pan", "Home & Kitchen", 2, UnitOfMeasurement.PIECE, "9.00", "16.00", "12.50", 8),
    ("Stainless Steel Water Bottle", "Home & Kitchen", 0, UnitOfMeasurement.PIECE, "4.00", "7.50", "10.00", 20),
    ("Ceramic Mug Set (4pc)", "Home & Kitchen", 1, UnitOfMeasurement.BOX, "5.50", "9.00", "0.00", 12),
]


class Command(BaseCommand):
    help = (
        "Wipe the dev database and reseed it with realistic categories/suppliers/"
        "products (varied tax_rate)/purchases/sales/adjustments. DEBUG-only, destructive."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_dev_data refuses to run with DEBUG=False — this flushes the "
                "entire database and must never run against a real deployment."
            )

        self.stdout.write("Flushing database...")
        call_command("flush", interactive=False)

        self.stdout.write("Recreating verification accounts...")
        call_command("seed_test_users")

        staff = User.objects.get(username="verify_user")
        supervisor = User.objects.get(username="verify_super")

        self.stdout.write("Creating categories...")
        categories = {c["name"]: Category.objects.create(**c) for c in CATEGORIES}

        self.stdout.write("Creating suppliers...")
        suppliers = [Supplier.objects.create(**s) for s in SUPPLIERS]

        self.stdout.write("Creating products...")
        products = []
        for name, cat_name, supplier_idx, unit, purchase_price, selling_price, tax_rate, reorder_level in PRODUCTS:
            product = Product.objects.create(
                sku=f"SKU-{len(products) + 1:04d}",
                name=name,
                category=categories[cat_name],
                supplier=suppliers[supplier_idx],
                unit=unit,
                purchase_price=Decimal(purchase_price),
                selling_price=Decimal(selling_price),
                tax_rate=Decimal(tax_rate),
                reorder_level=reorder_level,
            )
            InventoryService.initialize_for_product(product)
            products.append(product)

        self.stdout.write("Creating and receiving purchase orders (stocking the catalog)...")
        for product in products:
            po = PurchaseOrder.objects.create(supplier=product.supplier, created_by=staff)
            item = PurchaseOrderItem.objects.create(
                purchase_order=po, product=product, ordered_qty=100,
                unit_price=product.purchase_price, discount=Decimal("0"), tax=product.tax_rate,
            )
            po.total_cost = item.line_total
            po.save(update_fields=["total_cost"])
            PurchaseService.submit_for_approval(po, staff)
            PurchaseService.approve(po, supervisor)
            PurchaseService.receive_items(po, [{"item_id": item.pk, "received_qty": 100}], supervisor)

        # One PO left in DRAFT and one left PENDING, so the approval workflow
        # has real in-progress examples to look at, not just fully-received ones.
        draft_product, pending_product = products[0], products[1]
        draft_po = PurchaseOrder.objects.create(supplier=draft_product.supplier, created_by=staff)
        PurchaseOrderItem.objects.create(
            purchase_order=draft_po, product=draft_product, ordered_qty=40,
            unit_price=draft_product.purchase_price, tax=draft_product.tax_rate,
        )
        pending_po = PurchaseOrder.objects.create(supplier=pending_product.supplier, created_by=staff)
        PurchaseOrderItem.objects.create(
            purchase_order=pending_po, product=pending_product, ordered_qty=25,
            unit_price=pending_product.purchase_price, tax=pending_product.tax_rate,
        )
        PurchaseService.submit_for_approval(pending_po, staff)

        self.stdout.write("Creating sales...")
        # Phase 8.99b — Sale now has the same create(DRAFT) -> submit
        # (PENDING) -> approve(COMPLETED) gate Purchases already had, so
        # SaleService.create_sale() alone no longer produces a realistic
        # "it happened" sale — it has to be pushed through the same way
        # the purchase orders above are. Same in-progress-state variety
        # as the PO seed data: 3 fully completed, 1 left PENDING so the
        # approval queue has a real row to look at.
        sale_lines = [
            [{"product_id": products[0].pk, "quantity": 3, "unit_price": products[0].selling_price, "discount": 0}],
            [{"product_id": products[3].pk, "quantity": 5, "unit_price": products[3].selling_price, "discount": 5},
             {"product_id": products[4].pk, "quantity": 2, "unit_price": products[4].selling_price, "discount": 0}],
            [{"product_id": products[7].pk, "quantity": 1, "unit_price": products[7].selling_price, "discount": 0}],
        ]
        for items in sale_lines:
            sale = SaleService.create_sale({"customer_name": "Walk-in Customer"}, items, staff)
            SaleService.submit_for_approval(sale, staff)
            SaleService.approve_sale(sale, supervisor)

        pending_sale = SaleService.create_sale(
            {"customer_name": "Walk-in Customer"},
            [{"product_id": products[8].pk, "quantity": 4, "unit_price": products[8].selling_price, "discount": 10}],
            staff,
        )
        SaleService.submit_for_approval(pending_sale, staff)
        sale_lines.append(None)  # keeps the summary count below accurate (4 total sales)

        self.stdout.write("Creating adjustments...")
        approved_adjustment = InventoryAdjustment.objects.create(
            product=products[5], adjustment_type=AdjustmentType.DECREASE, quantity=3,
            reason="Damaged in storage.", requested_by=staff,
        )
        AdjustmentService.approve(approved_adjustment, supervisor)
        InventoryAdjustment.objects.create(
            product=products[6], adjustment_type=AdjustmentType.INCREASE, quantity=10,
            reason="Recount found extra stock on shelf.", requested_by=staff,
        )

        self.stdout.write(self.style.SUCCESS(
            f"\nDone — {len(categories)} categories, {len(suppliers)} suppliers, "
            f"{len(products)} products (tax rates: "
            f"{', '.join(str(p.tax_rate) for p in products)}), "
            f"{PurchaseOrder.objects.count()} purchase orders, "
            f"{len(sale_lines)} sales, {InventoryAdjustment.objects.count()} adjustments."
        ))
