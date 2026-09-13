import math
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.db.models import Max, Min
from django.utils import timezone

from frontend.approvals import ensure_default_policies
from frontend.classification import run_full_classification
from frontend.models import (
    AdjustmentType,
    Category,
    InventoryAdjustment,
    InventoryMovement,
    POStatus,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SaleStatus,
    SaleTransaction,
    Supplier,
    SystemSettings,
    UnitOfMeasurement,
    User,
)
from frontend.services import AdjustmentService, InventoryService, PurchaseService, SaleService

# Rule: fixed seed -- the dataset is byte-for-byte identical across runs.
RNG_SEED = 42

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

# Rule: (name, category, supplier idx, unit, cost, price, tax, reorder, cohort)
PRODUCTS = [
    # Rule: fast, long history -- clears the dropna() burn-in comfortably.
    ("Wireless Mouse", "Electronics", 0, UnitOfMeasurement.PIECE, "8.50", "15.00", "10.00", 15, "fast_long"),
    ("Basmati Rice 5kg", "Groceries", 1, UnitOfMeasurement.PACK, "6.50", "9.50", "0.00", 20, "fast_long"),
    ("A4 Copy Paper Ream", "Stationery", 2, UnitOfMeasurement.PACK, "3.10", "4.75", "7.50", 20, "fast_long"),
    # Rule: fast, shorter recent history.
    ("USB-C Charging Cable 1m", "Electronics", 0, UnitOfMeasurement.PIECE, "2.20", "5.00", "10.00", 25, "fast_short"),
    ("Cooking Oil 1L", "Groceries", 1, UnitOfMeasurement.LITER, "1.80", "2.75", "5.00", 30, "fast_short"),
    ("Non-Stick Frying Pan", "Home & Kitchen", 2, UnitOfMeasurement.PIECE, "9.00", "16.00", "12.50", 8, "fast_short"),
    # Rule: slow -- last sold 60-179 days ago, real earlier history.
    ("Bluetooth Speaker", "Electronics", 1, UnitOfMeasurement.PIECE, "18.00", "32.00", "15.00", 10, "slow"),
    ("Ballpoint Pen (Box of 12)", "Stationery", 2, UnitOfMeasurement.BOX, "1.40", "2.50", "7.50", 15, "slow"),
    ("Ceramic Mug Set (4pc)", "Home & Kitchen", 1, UnitOfMeasurement.BOX, "5.50", "9.00", "0.00", 12, "slow"),
    ("Stainless Steel Water Bottle", "Home & Kitchen", 0, UnitOfMeasurement.PIECE, "4.00", "7.50", "10.00", 20, "slow"),
    # Rule: dead -- last sold 180+ days ago.
    ("Desk Organizer Tray", "Stationery", 2, UnitOfMeasurement.PIECE, "3.50", "6.50", "7.50", 10, "dead"),
    ("Electric Kettle", "Home & Kitchen", 1, UnitOfMeasurement.PIECE, "12.00", "21.00", "12.50", 8, "dead"),
    ("Powdered Milk 1kg", "Groceries", 2, UnitOfMeasurement.PACK, "5.00", "7.50", "0.00", 15, "dead"),
    # Rule: never sold -- exercises the 9999-day sentinel.
    ("Laptop Stand", "Electronics", 0, UnitOfMeasurement.PIECE, "10.00", "18.00", "10.00", 10, "never"),
    ("Notebook (200 pages)", "Stationery", 2, UnitOfMeasurement.PIECE, "1.10", "2.00", "0.00", 25, "never"),
    # Rule: short history (< 4 weeks) -- proves the dropna() skip path.
    ("Scented Candle Set", "Home & Kitchen", 1, UnitOfMeasurement.BOX, "6.00", "11.00", "12.50", 10, "short"),
    # Rule: stockout -- a real stock_after == 0 window of at least 1 week.
    ("Wireless Earbuds", "Electronics", 1, UnitOfMeasurement.PIECE, "15.00", "28.00", "15.00", 10, "stockout"),
    ("Whole Wheat Flour 2kg", "Groceries", 0, UnitOfMeasurement.PACK, "3.20", "4.80", "0.00", 20, "stockout"),
    # Rule: trending up -- >=4 products, tests upward-trend recovery.
    ("Portable Power Bank", "Electronics", 2, UnitOfMeasurement.PIECE, "14.00", "25.00", "10.00", 12, "trending"),
    ("Steel Lunch Box", "Home & Kitchen", 0, UnitOfMeasurement.PIECE, "5.50", "10.00", "5.00", 15, "trending"),
    ("External Hard Drive 1TB", "Electronics", 1, UnitOfMeasurement.PIECE, "35.00", "58.00", "10.00", 8, "trending"),
    ("Yoga Mat", "Home & Kitchen", 2, UnitOfMeasurement.PIECE, "6.00", "12.00", "5.00", 12, "trending"),
    ("Sticky Notes Pack", "Stationery", 0, UnitOfMeasurement.PACK, "0.80", "1.75", "7.50", 30, "trending"),
    # Rule: trending down -- tests decline recovery, not just growth.
    ("Analog Wall Clock", "Home & Kitchen", 1, UnitOfMeasurement.PIECE, "7.00", "13.00", "10.00", 10, "trending_down"),
    ("Wired Earphones", "Electronics", 2, UnitOfMeasurement.PIECE, "3.50", "7.50", "10.00", 20, "trending_down"),
    ("Correction Fluid Bottle", "Stationery", 0, UnitOfMeasurement.PIECE, "0.60", "1.40", "7.50", 25, "trending_down"),
    ("Powdered Juice Mix", "Groceries", 1, UnitOfMeasurement.PACK, "1.20", "2.20", "0.00", 25, "trending_down"),
    # Rule: seasonal -- a ~4-week rhythm, the pattern lag_1..lag_4 exist to capture.
    ("Birthday Candle Pack", "Home & Kitchen", 0, UnitOfMeasurement.PACK, "1.00", "2.20", "5.00", 20, "seasonal"),
    ("Printer Ink Cartridge", "Stationery", 1, UnitOfMeasurement.PIECE, "9.00", "16.50", "12.50", 12, "seasonal"),
    ("Frozen Vegetable Pack", "Groceries", 2, UnitOfMeasurement.PACK, "2.40", "3.80", "0.00", 25, "seasonal"),
    ("Phone Screen Protector", "Electronics", 0, UnitOfMeasurement.PIECE, "1.50", "3.50", "10.00", 30, "seasonal"),
    ("Paper Napkin Pack", "Groceries", 1, UnitOfMeasurement.PACK, "1.00", "1.90", "0.00", 30, "seasonal"),
    # Rule: steady baseline -- the "normal" majority, tight confidence interval.
    ("AA Batteries (Pack of 4)", "Electronics", 1, UnitOfMeasurement.PACK, "1.60", "3.20", "10.00", 25, "steady"),
    ("Dish Washing Liquid", "Home & Kitchen", 2, UnitOfMeasurement.LITER, "1.90", "3.40", "5.00", 20, "steady"),
    ("Whiteboard Marker Set", "Stationery", 0, UnitOfMeasurement.BOX, "2.50", "4.50", "7.50", 15, "steady"),
    ("Tea Bags Box (100pc)", "Groceries", 1, UnitOfMeasurement.BOX, "3.00", "5.00", "0.00", 20, "steady"),
    ("HDMI Cable 2m", "Electronics", 2, UnitOfMeasurement.PIECE, "2.80", "6.00", "10.00", 20, "steady"),
    ("Hand Sanitizer 200ml", "Home & Kitchen", 0, UnitOfMeasurement.PIECE, "1.20", "2.50", "5.00", 25, "steady"),
    ("Sticky Tape Roll", "Stationery", 2, UnitOfMeasurement.PIECE, "0.50", "1.20", "7.50", 30, "steady"),
    # Rule: spiky/intermittent -- mostly-zero weeks, stresses residual_std wide.
    ("Gift Wrapping Paper Roll", "Home & Kitchen", 1, UnitOfMeasurement.PIECE, "1.50", "3.00", "5.00", 15, "spiky"),
    ("Extension Cord 5m", "Electronics", 0, UnitOfMeasurement.PIECE, "4.50", "8.50", "10.00", 12, "spiky"),
    ("Office Stapler Heavy Duty", "Stationery", 1, UnitOfMeasurement.PIECE, "3.20", "6.00", "7.50", 10, "spiky"),
    ("Canned Tuna Pack", "Groceries", 2, UnitOfMeasurement.PACK, "1.80", "3.00", "0.00", 20, "spiky"),
]

ORDER_HOUR, APPROVE_HOUR, RECEIVE_HOUR = 9, 10, 11
SALE_APPROVE_HOUR = 15


class Command(BaseCommand):
    help = (
        "Wipe the dev database and reseed it with a large, deliberately-"
        "backdated dataset (Phase 9.5, expanded Phase 11.5) spanning distinct "
        "fast/slow/dead/never-sold/short-history/stockout/trending-up/"
        "trending-down/seasonal/steady/spiky cohorts, so the AI features "
        "(Phase 10/11) have real data to be right or wrong about. "
        "DEBUG-only, destructive."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_dev_data refuses to run with DEBUG=False — this flushes the "
                "entire database and bypasses InventoryMovement's immutability "
                "guard to backdate the ledger; it must never run against a real "
                "deployment."
            )

        self.rng = random.Random(RNG_SEED)
        self.today = timezone.localdate()
        # Rule: strictly before today -- approved_at must never land in the future.
        self.max_event_date = self.today - timedelta(days=1)

        self.stdout.write("Flushing database...")
        call_command("flush", interactive=False)

        self.stdout.write("Recreating verification accounts...")
        call_command("seed_test_users")

        self.staff = User.objects.get(username="verify_user")
        self.supervisor = User.objects.get(username="verify_super")

        # Rule: flush wipes ApprovalPolicy -- approve()/cancel() below need one.
        self.stdout.write("Restoring default approval policies (flush wiped them)...")
        ensure_default_policies()

        self.stdout.write("Disabling email notifications for the bulk seed run...")
        settings_obj = SystemSettings.get_settings()
        settings_obj.email_notifications_enabled = False
        settings_obj.save(update_fields=["email_notifications_enabled"])

        self.stdout.write("Creating categories...")
        self.categories = {c["name"]: Category.objects.create(**c) for c in CATEGORIES}

        self.stdout.write("Creating suppliers...")
        self.suppliers = [Supplier.objects.create(**s) for s in SUPPLIERS]

        self.stdout.write("Creating products...")
        self.products = {}
        cohort_table = []
        for i, (name, cat_name, supplier_idx, unit, purchase_price, selling_price, tax_rate, reorder_level, cohort) in enumerate(PRODUCTS):
            product = Product.objects.create(
                sku=f"SKU-{i + 1:04d}",
                name=name,
                category=self.categories[cat_name],
                supplier=self.suppliers[supplier_idx],
                unit=unit,
                purchase_price=Decimal(purchase_price),
                selling_price=Decimal(selling_price),
                tax_rate=Decimal(tax_rate),
                reorder_level=reorder_level,
            )
            InventoryService.initialize_for_product(product)
            self.products[name] = product
            cohort_table.append({"name": name, "cohort": cohort, "product": product})

        self.stdout.write("Building cohort purchase/sale histories (this takes a while)...")
        cohort_fns = {
            "fast_long": self._build_fast_long,
            "fast_short": self._build_fast_short,
            "slow": self._build_slow,
            "dead": self._build_dead,
            "never": self._build_never,
            "short": self._build_short_history,
            "stockout": self._build_stockout,
            "trending": self._build_trending,
            "trending_down": self._build_trending_down,
            "seasonal": self._build_seasonal,
            "steady": self._build_steady,
            "spiky": self._build_spiky,
        }
        intended_last_sale = {}
        for row in cohort_table:
            fn = cohort_fns[row["cohort"]]
            last_sale_days_ago = fn(row["product"])
            intended_last_sale[row["name"]] = last_sale_days_ago

        self.stdout.write("Creating non-completed records (pending/rejected/cancelled)...")
        non_completed_summary = self._build_non_completed_records()

        self.stdout.write("Creating adjustments...")
        adjustment_summary = self._build_adjustments()

        self.stdout.write("Verifying coherence (approved_at vs transaction_date/order_date)...")
        self._verify_coherence()

        self.stdout.write("Verifying cohort placement against measured last-sold dates...")
        self._print_cohort_report(cohort_table, intended_last_sale)

        self._print_ledger_summary()

        # Rule: mid-seed classify calls run against not-yet-backdated data.
        self.stdout.write("Running final classification pass (corrects ~180+ mid-seed reclassifications)...")
        run_full_classification()

        self.stdout.write(self.style.SUCCESS(
            f"\nDone — {len(self.categories)} categories, {len(self.suppliers)} suppliers, "
            f"{len(self.products)} products, "
            f"{PurchaseOrder.objects.count()} purchase orders, "
            f"{SaleTransaction.objects.count()} sales "
            f"({non_completed_summary}), "
            f"{InventoryAdjustment.objects.count()} adjustments ({adjustment_summary}), "
            f"{InventoryMovement.objects.count()} ledger movements."
        ))

    def _dt(self, on_date, hour, minute=0):
        return timezone.make_aware(datetime.combine(on_date, time(hour, minute)))

    def _new_po(self, product):
        # Workaround: retries on a po_number collision -- many POs share one second.
        for _ in range(20):
            try:
                return PurchaseOrder.objects.create(supplier=product.supplier, created_by=self.staff)
            except IntegrityError:
                continue
        raise CommandError(f"Could not generate a unique po_number for {product.name} after 20 attempts.")

    def _new_sale(self, product, qty, discount):
        for _ in range(20):
            try:
                return SaleService.create_sale(
                    {"customer_name": "Walk-in Customer"},
                    [{"product_id": product.pk, "quantity": qty, "unit_price": product.selling_price, "discount": discount}],
                    self.staff,
                )
            except IntegrityError:
                continue
        raise CommandError(f"Could not generate a unique invoice_number for {product.name} after 20 attempts.")

    def _receive(self, product, qty, on_date):
        po = self._new_po(product)
        item = PurchaseOrderItem.objects.create(
            purchase_order=po, product=product, ordered_qty=qty,
            unit_price=product.purchase_price, discount=Decimal("0"), tax=product.tax_rate,
        )
        po.total_cost = item.line_total
        po.save(update_fields=["total_cost"])
        PurchaseService.submit_for_approval(po, self.staff)
        PurchaseService.approve(po, self.supervisor)

        movement_floor = InventoryMovement.objects.aggregate(Max("pk"))["pk__max"] or 0
        PurchaseService.receive_items(po, [{"item_id": item.pk, "received_qty": qty}], self.supervisor)

        po.order_date = on_date
        po.approved_at = self._dt(on_date, APPROVE_HOUR)
        po.save(update_fields=["order_date", "approved_at"])
        InventoryMovement.objects.filter(pk__gt=movement_floor).update(created_at=self._dt(on_date, RECEIVE_HOUR))
        return po

    def _sell(self, product, qty, on_date, discount=Decimal("0")):
        sale = self._new_sale(product, qty, discount)
        SaleService.submit_for_approval(sale, self.staff)

        movement_floor = InventoryMovement.objects.aggregate(Max("pk"))["pk__max"] or 0
        SaleService.approve_sale(sale, self.supervisor)

        approved_dt = self._dt(on_date, SALE_APPROVE_HOUR)
        sale.transaction_date = on_date
        sale.approved_at = approved_dt
        sale.save(update_fields=["transaction_date", "approved_at"])
        InventoryMovement.objects.filter(pk__gt=movement_floor).update(created_at=approved_dt)
        return sale

    def _weekly_series(self, start_days_ago, end_days_ago, base_qty, trend_per_week=0.0,
                        seasonal_amplitude=0.0, seasonal_period_weeks=4, skip_prob=0.0, noise_scale=1.0):
        # Rule: an explicit shape, not a random walk -- recovery is checkable.
        events = []
        days_ago = start_days_ago
        period = 0
        while days_ago >= end_days_ago:
            if self.rng.random() >= skip_prob:
                jitter_days = self.rng.randint(-2, 2)
                seasonal = seasonal_amplitude * math.sin(2 * math.pi * period / seasonal_period_weeks)
                qty = max(1, round(
                    base_qty + trend_per_week * period + seasonal
                    + self.rng.uniform(-noise_scale, noise_scale)
                ))
                events.append((max(end_days_ago, days_ago + jitter_days), qty))
            days_ago -= 7
            period += 1
        return events

    def _stock_and_sell(self, product, sell_events, start_days_ago):
        # Rule: each receive covers 55% of total demand -- keeps stock non-negative.
        total_demand = sum(qty for _, qty in sell_events)
        receive_qty = max(15, int(total_demand * 0.55))
        receive_days = [start_days_ago + 5, int(start_days_ago * 0.65), int(start_days_ago * 0.3)]
        timeline = [(d, "receive", receive_qty) for d in receive_days]
        timeline += [(days_ago, "sell", qty) for days_ago, qty in sell_events]
        self._run_timeline(product, timeline)

    def _run_timeline(self, product, timeline):
        # Rule: executes oldest-first -- keeps stock_before/stock_after coherent.
        for days_ago, action, qty in sorted(timeline, key=lambda e: (-e[0], e[1] != "receive")):
            on_date = self.today - timedelta(days=days_ago)
            if action == "receive":
                self._receive(product, qty, on_date)
            else:
                self._sell(product, qty, on_date)

    def _build_fast_long(self, product):
        base_qty = {"Wireless Mouse": 6, "Basmati Rice 5kg": 8, "A4 Copy Paper Ream": 10}[product.name]
        sell_events = self._weekly_series(384, 6, base_qty=base_qty, skip_prob=0.15)
        last_days_ago = min(d for d, _ in sell_events)
        self._stock_and_sell(product, sell_events, start_days_ago=384)
        return last_days_ago

    def _build_fast_short(self, product):
        self._receive(product, 80, self.today - timedelta(days=55))
        plan = [(50, 4), (45, 5), (35, 3), (22, 6), (10, 4)]
        for days_ago, qty in plan:
            self._sell(product, qty, self.today - timedelta(days=days_ago))
        return plan[-1][0]

    def _build_slow(self, product):
        last_sale_offset = {
            "Bluetooth Speaker": 75, "Ballpoint Pen (Box of 12)": 95,
            "Ceramic Mug Set (4pc)": 110, "Stainless Steel Water Bottle": 130,
        }[product.name]
        self._receive(product, 60, self.today - timedelta(days=200))
        earlier = [190, 175, 160, 140, 120]
        offsets = sorted([o for o in earlier if o > last_sale_offset], reverse=True) + [last_sale_offset]
        for days_ago in offsets:
            qty = self.rng.randint(2, 4)
            self._sell(product, qty, self.today - timedelta(days=days_ago))
        return last_sale_offset

    def _build_dead(self, product):
        last_sale_offset = {
            "Desk Organizer Tray": 210, "Electric Kettle": 240, "Powdered Milk 1kg": 195,
        }[product.name]
        self._receive(product, 40, self.today - timedelta(days=300))
        earlier = [280, 260]
        offsets = sorted([o for o in earlier if o > last_sale_offset], reverse=True) + [last_sale_offset]
        for days_ago in offsets:
            qty = self.rng.randint(2, 4)
            self._sell(product, qty, self.today - timedelta(days=days_ago))
        return last_sale_offset

    def _build_never(self, product):
        self._receive(product, 50, self.today - timedelta(days=90))
        return None

    def _build_short_history(self, product):
        self._receive(product, 30, self.today - timedelta(days=20))
        self._sell(product, 3, self.today - timedelta(days=15))
        self._sell(product, 4, self.today - timedelta(days=5))
        return 5

    def _build_stockout(self, product):
        # Rule: extra pre-stockout runway -- dropna()'s burn-in must not eat it.
        self._receive(product, 20, self.today - timedelta(days=140))
        for days_ago, qty in [(130, 3), (120, 3), (110, 3), (100, 3), (90, 3), (80, 5)]:
            self._sell(product, qty, self.today - timedelta(days=days_ago))
        # Rule: a real gap, not a flag on a row -- what stockout_flag catches.
        self._receive(product, 40, self.today - timedelta(days=65))
        for days_ago, qty in [(50, 5), (35, 5), (20, 6)]:
            self._sell(product, qty, self.today - timedelta(days=days_ago))
        last = 10
        self._sell(product, 6, self.today - timedelta(days=last))
        return last

    def _build_trending(self, product):
        base_qty, trend = {
            "Portable Power Bank": (3, 0.16), "Steel Lunch Box": (3, 0.15),
            "External Hard Drive 1TB": (2, 0.11), "Yoga Mat": (3, 0.16),
            "Sticky Notes Pack": (4, 0.20),
        }[product.name]
        sell_events = self._weekly_series(384, 4, base_qty=base_qty, trend_per_week=trend, skip_prob=0.05)
        last_days_ago = min(d for d, _ in sell_events)
        self._stock_and_sell(product, sell_events, start_days_ago=384)
        return last_days_ago

    def _build_trending_down(self, product):
        base_qty, trend = {
            "Analog Wall Clock": (16, -0.24), "Wired Earphones": (14, -0.20),
            "Correction Fluid Bottle": (12, -0.18), "Powdered Juice Mix": (15, -0.22),
        }[product.name]
        sell_events = self._weekly_series(384, 6, base_qty=base_qty, trend_per_week=trend, skip_prob=0.05)
        last_days_ago = min(d for d, _ in sell_events)
        self._stock_and_sell(product, sell_events, start_days_ago=384)
        return last_days_ago

    def _build_seasonal(self, product):
        base_qty, amplitude = {
            "Birthday Candle Pack": (6, 4), "Printer Ink Cartridge": (5, 3),
            "Frozen Vegetable Pack": (8, 5), "Phone Screen Protector": (6, 4),
            "Paper Napkin Pack": (7, 4),
        }[product.name]
        sell_events = self._weekly_series(
            384, 5, base_qty=base_qty, seasonal_amplitude=amplitude,
            seasonal_period_weeks=4, skip_prob=0.05, noise_scale=0.75,
        )
        last_days_ago = min(d for d, _ in sell_events)
        self._stock_and_sell(product, sell_events, start_days_ago=384)
        return last_days_ago

    def _build_steady(self, product):
        base_qty = {
            "AA Batteries (Pack of 4)": 7, "Dish Washing Liquid": 5,
            "Whiteboard Marker Set": 4, "Tea Bags Box (100pc)": 6,
            "HDMI Cable 2m": 5, "Hand Sanitizer 200ml": 6, "Sticky Tape Roll": 5,
        }[product.name]
        sell_events = self._weekly_series(384, 4, base_qty=base_qty, skip_prob=0.08, noise_scale=0.8)
        last_days_ago = min(d for d, _ in sell_events)
        self._stock_and_sell(product, sell_events, start_days_ago=384)
        return last_days_ago

    def _build_spiky(self, product):
        """Spiky/intermittent: mostly-zero weeks with occasional demand
        (>= 3 required) — a high skip_prob leaves real gaps (no sale
        event that week at all, not a fabricated zero row) between
        sales, and a wide noise_scale on the weeks that do occur.
        Realistic for slow movers, and the case that most stresses the
        confidence-interval machinery (residual_std should come back
        wide here, narrow for the steady cohort)."""
        base_qty = {
            "Gift Wrapping Paper Roll": 6, "Extension Cord 5m": 5,
            "Office Stapler Heavy Duty": 4, "Canned Tuna Pack": 6,
        }[product.name]
        sell_events = self._weekly_series(384, 6, base_qty=base_qty, skip_prob=0.55, noise_scale=4.0)
        last_days_ago = min(d for d, _ in sell_events)
        self._stock_and_sell(product, sell_events, start_days_ago=384)
        return last_days_ago

    def _build_non_completed_records(self):
        # Rule: never touches the "never sold" products -- keeps that cohort clean.
        mouse = self.products["Wireless Mouse"]
        speaker = self.products["Bluetooth Speaker"]
        pen = self.products["Ballpoint Pen (Box of 12)"]
        cable = self.products["USB-C Charging Cable 1m"]
        mug = self.products["Ceramic Mug Set (4pc)"]
        oil = self.products["Cooking Oil 1L"]
        bottle = self.products["Stainless Steel Water Bottle"]
        pan = self.products["Non-Stick Frying Pan"]
        tray = self.products["Desk Organizer Tray"]

        pending = 0
        for product, qty in [(mouse, 2), (speaker, 1), (pen, 3)]:
            sale = self._new_sale(product, qty, Decimal("0"))
            SaleService.submit_for_approval(sale, self.staff)
            pending += 1

        rejected = 0
        for product, qty, reason in [
            (cable, 2, "Customer disputed the unit price after submission."),
            (mug, 1, "Duplicate entry — same order already recorded separately."),
        ]:
            sale = self._new_sale(product, qty, Decimal("0"))
            SaleService.submit_for_approval(sale, self.staff)
            SaleService.reject_sale(sale, self.supervisor, reason)
            rejected += 1

        cancelled = 0
        draft_cancel = self._new_sale(oil, 2, Decimal("0"))
        # Rule: self.supervisor -- staff could never reach this cancel in the real app.
        SaleService.cancel_sale(draft_cancel, self.supervisor, "Customer changed their mind before checkout.")
        cancelled += 1
        pending_cancel = self._new_sale(bottle, 3, Decimal("0"))
        SaleService.submit_for_approval(pending_cancel, self.staff)
        SaleService.cancel_sale(pending_cancel, self.supervisor, "Stock reserved for a larger corporate order instead.")
        cancelled += 1

        po_cancelled = 0
        for product, qty, reason, submit_first in [
            (pan, 20, "Supplier quoted a price increase we did not accept.", False),
            (tray, 15, "Duplicate purchase order raised in error.", True),
        ]:
            po = self._new_po(product)
            item = PurchaseOrderItem.objects.create(
                purchase_order=po, product=product, ordered_qty=qty,
                unit_price=product.purchase_price, tax=product.tax_rate,
            )
            po.total_cost = item.line_total
            po.save(update_fields=["total_cost"])
            if submit_first:
                PurchaseService.submit_for_approval(po, self.staff)
            PurchaseService.cancel(po, self.supervisor, reason)
            po_cancelled += 1

        return (
            f"{pending} pending, {rejected} rejected, {cancelled} cancelled sales; "
            f"{po_cancelled} cancelled POs"
        )

    def _build_adjustments(self):
        approved = InventoryAdjustment.objects.create(
            product=self.products["A4 Copy Paper Ream"], adjustment_type=AdjustmentType.DECREASE, quantity=3,
            reason="Damaged in storage.", requested_by=self.staff,
        )
        AdjustmentService.approve(approved, self.supervisor)
        InventoryAdjustment.objects.create(
            product=self.products["Basmati Rice 5kg"], adjustment_type=AdjustmentType.INCREASE, quantity=10,
            reason="Recount found extra stock on shelf.", requested_by=self.staff,
        )
        rejected = InventoryAdjustment.objects.create(
            product=self.products["Wireless Mouse"], adjustment_type=AdjustmentType.DECREASE, quantity=5,
            reason="Suspected miscount — requesting recheck before approval.", requested_by=self.staff,
        )
        AdjustmentService.reject(rejected, self.supervisor, "Recount confirmed original figure was correct.")
        return "1 approved, 1 pending, 1 rejected"

    def _verify_coherence(self):
        """approved_at must never precede its own business date, or be in the future."""
        now = timezone.now()
        violations = []

        for po in PurchaseOrder.objects.filter(approved_at__isnull=False):
            if po.approved_at.date() < po.order_date:
                violations.append(f"PO {po.po_number}: approved_at {po.approved_at} before order_date {po.order_date}")
            if po.approved_at > now:
                violations.append(f"PO {po.po_number}: approved_at {po.approved_at} is in the future")

        for sale in SaleTransaction.objects.filter(approved_at__isnull=False):
            if sale.approved_at.date() < sale.transaction_date:
                violations.append(f"Sale {sale.invoice_number}: approved_at {sale.approved_at} before transaction_date {sale.transaction_date}")
            if sale.approved_at > now:
                violations.append(f"Sale {sale.invoice_number}: approved_at {sale.approved_at} is in the future")

        if violations:
            raise CommandError(
                "Backdated dataset failed its own coherence check:\n" + "\n".join(violations)
            )
        self.stdout.write(self.style.SUCCESS("  Coherence OK — no approved_at precedes its own order/transaction date, none are in the future."))

    def _print_cohort_report(self, cohort_table, intended_last_sale):
        self.stdout.write("\nCohort placement (product -> cohort -> intended vs measured days-since-last-sale):")
        for row in cohort_table:
            product = row["product"]
            measured = SaleTransaction.objects.filter(
                items__product=product, status=SaleStatus.COMPLETED,
            ).order_by("-transaction_date").values_list("transaction_date", flat=True).first()
            measured_days = (self.today - measured).days if measured else None
            intended_days = intended_last_sale[row["name"]]
            flag = "OK" if measured_days == intended_days else "MISMATCH"
            self.stdout.write(
                f"  {row['name']:<32} {row['cohort']:<10} "
                f"intended={intended_days if intended_days is not None else 'never':<6} "
                f"measured={measured_days if measured_days is not None else 'never':<6} [{flag}]"
            )

    def _print_ledger_summary(self):
        span = InventoryMovement.objects.aggregate(earliest=Min("created_at"), latest=Max("created_at"))
        self.stdout.write(
            f"\nInventoryMovement.created_at spans {span['earliest']} .. {span['latest']}"
        )
        for name in ("Wireless Earbuds", "Whole Wheat Flour 2kg"):
            zero_rows = InventoryMovement.objects.filter(product=self.products[name], stock_after=0).count()
            self.stdout.write(f"  {name}: {zero_rows} stock_after=0 row(s) confirmed")
