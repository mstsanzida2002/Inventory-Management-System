"""
Phase 8.98c — dev-environment convenience command: wipes the whole dev
database and reseeds it with a small, realistic dataset built on the new
Product.tax_rate model (varied tax rates, including 0% — the field's own
default — so both the "no tax" and "has tax" cases are exercised).

Phase 9.5 — extended into a much larger, deliberately-backdated dataset so
Phases 10/11 (AI demand forecasting, slow-moving/dead-stock classification)
have something real to be right or wrong about. Three mechanisms otherwise
block that:

1. SaleTransaction.save()/PurchaseOrder.save() only assign transaction_date/
   order_date when the field is still unset (`if self.transaction_date is
   None: ...` / `if self.order_date is None: ...`) — this was ALREADY the
   case going into Phase 9.5 (BUG-47, Phase 8.99), not something this phase
   changed. It means a caller that constructs the model with the field
   already populated (SaleTransaction.objects.create(transaction_date=...))
   gets that exact date, not "today" — the normal flow (SaleService.
   create_sale(), every real view) never supplies one, so the real-world
   BUG-47 guarantee ("every genuine sale lands on the Dhaka calendar day it
   was actually made on") is completely undisturbed. See
   ExplicitDateAssignmentTests (frontend/tests.py) for the proof, and
   docs/project_memory.md §13 for the full disclosure of this Phase 9.5
   finding (the task's own premise assumed a code change was needed here;
   verified against the actual code before writing one, and none was).
2. `approved_at` (SaleTransaction/PurchaseOrder/InventoryAdjustment) is set
   unconditionally to timezone.now() *inside* PurchaseService.approve()/
   SaleService.approve_sale()/AdjustmentService.approve() — not via save()/
   auto_now, and deliberately NOT changed to accept a backdating parameter
   (that would be a service-layer API change for a seeding-only concern).
   This command calls the real service methods for their real business
   logic (status transition, stock movement, notification, audit log) and
   then does a plain, ordinary `.save(update_fields=['approved_at'])`
   afterward to correct the timestamp — approved_at isn't guarded the way
   InventoryMovement's fields are, so this is a normal mutation, not a
   bypass of anything.
3. InventoryMovement.created_at is `auto_now_add=True` (via
   TimeStampedModel) and InventoryMovement.save() raises PermissionError
   whenever self.pk is already set (BUG-20) — there is no create-then-
   update path through the model. The only way to backdate it is a
   queryset-level `.update(created_at=...)`, which goes straight to SQL and
   never calls save() at all. Done here, in this command only — see
   docs/project_memory.md §13 for the disclosure (DEBUG-guarded dev-seed
   concern, not a production code path; BUG-20's guard is untouched; any
   future `.update()` on InventoryMovement outside a seed command is a bug,
   not precedent set by this file).

All stock/ledger data is still produced by going through the real service
layer (PurchaseService/SaleService/AdjustmentService/InventoryService,
frontend/services.py) exactly as the views do — never by setting
current_stock or writing InventoryMovement rows directly. Only the
*timestamp* on rows that already went through that real path is corrected
afterward, in a second pass, via mechanisms (2) and (3) above.

Phase 11.5 — extends this same, already-disclosed escape hatch to a much
larger dataset (20 -> 43 products), not a new one: the 8 original 9.5
cohorts are unchanged in shape, and 5 more products were added to the
existing "trending" (up) cohort, plus 4 new demand-pattern cohorts
(trending_down, seasonal, steady, spiky) built the same way — real
service calls, backdated via the same two mechanisms above. The
forecastable cohorts (fast_long, trending, trending_down, seasonal,
steady) now run a full ~55-week (12+ month) window instead of ~30 weeks,
so the pooled model has materially more post-burn-in training rows per
product. Every new cohort's weekly demand is generated from an explicit
shape (base + linear trend and/or sinusoidal seasonal component + bounded
noise, see _weekly_series()) rather than a random walk, so the forecast's
recovery of each shape can be checked directly rather than assumed.

Notifications: email is deliberately switched off for the whole run
(SystemSettings.email_notifications_enabled = False before any purchase/
sale is created) — this dataset creates roughly 250+ approval-type events,
each of which would otherwise trigger a real synchronous send_mail() call
(frontend/notifications.py's `_maybe_send_email()`) to verify_super's/
verify_admin's addresses. Left off after seeding too; an admin can
re-enable it from the Settings page. In-app Notification rows themselves
are unaffected — only the email side effect is suppressed.

Refuses to run when DEBUG is False, same guard as seed_test_users.py: a
full-database flush must never be reachable against a real deployment —
more load-bearing now than before Phase 9.5, since this command is also
the only place in the codebase permitted to bypass InventoryMovement's
immutability guard.
"""
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

# Fixed seed: makes the dataset byte-for-byte identical across runs (matters
# for Verification's "idempotent — run twice" requirement to mean something
# stronger than "same cohort counts" — it means the exact same rows).
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

# (name, category, supplier index, unit, purchase_price, selling_price, tax_rate, reorder_level, cohort)
# Cohort key matches the per-cohort generator function below that decides
# this product's purchase/sale timeline.
PRODUCTS = [
    # -- fast, long history (>= 6 months of weekly sales) --------------------
    ("Wireless Mouse", "Electronics", 0, UnitOfMeasurement.PIECE, "8.50", "15.00", "10.00", 15, "fast_long"),
    ("Basmati Rice 5kg", "Groceries", 1, UnitOfMeasurement.PACK, "6.50", "9.50", "0.00", 20, "fast_long"),
    ("A4 Copy Paper Ream", "Stationery", 2, UnitOfMeasurement.PACK, "3.10", "4.75", "7.50", 20, "fast_long"),
    # -- fast, shorter recent history -----------------------------------------
    ("USB-C Charging Cable 1m", "Electronics", 0, UnitOfMeasurement.PIECE, "2.20", "5.00", "10.00", 25, "fast_short"),
    ("Cooking Oil 1L", "Groceries", 1, UnitOfMeasurement.LITER, "1.80", "2.75", "5.00", 30, "fast_short"),
    ("Non-Stick Frying Pan", "Home & Kitchen", 2, UnitOfMeasurement.PIECE, "9.00", "16.00", "12.50", 8, "fast_short"),
    # -- slow (last sold 60-179 days ago, real earlier history) --------------
    ("Bluetooth Speaker", "Electronics", 1, UnitOfMeasurement.PIECE, "18.00", "32.00", "15.00", 10, "slow"),
    ("Ballpoint Pen (Box of 12)", "Stationery", 2, UnitOfMeasurement.BOX, "1.40", "2.50", "7.50", 15, "slow"),
    ("Ceramic Mug Set (4pc)", "Home & Kitchen", 1, UnitOfMeasurement.BOX, "5.50", "9.00", "0.00", 12, "slow"),
    ("Stainless Steel Water Bottle", "Home & Kitchen", 0, UnitOfMeasurement.PIECE, "4.00", "7.50", "10.00", 20, "slow"),
    # -- dead (last sold 180+ days ago) ---------------------------------------
    ("Desk Organizer Tray", "Stationery", 2, UnitOfMeasurement.PIECE, "3.50", "6.50", "7.50", 10, "dead"),
    ("Electric Kettle", "Home & Kitchen", 1, UnitOfMeasurement.PIECE, "12.00", "21.00", "12.50", 8, "dead"),
    ("Powdered Milk 1kg", "Groceries", 2, UnitOfMeasurement.PACK, "5.00", "7.50", "0.00", 15, "dead"),
    # -- never sold (the 9999-day sentinel) -----------------------------------
    ("Laptop Stand", "Electronics", 0, UnitOfMeasurement.PIECE, "10.00", "18.00", "10.00", 10, "never"),
    ("Notebook (200 pages)", "Stationery", 2, UnitOfMeasurement.PIECE, "1.10", "2.00", "0.00", 25, "never"),
    # -- short history (< 4 weeks) — proves Phase 11's dropna skip path ------
    ("Scented Candle Set", "Home & Kitchen", 1, UnitOfMeasurement.BOX, "6.00", "11.00", "12.50", 10, "short"),
    # -- stockout (a real stock_after == 0 window >= 1 week) -----------------
    ("Wireless Earbuds", "Electronics", 1, UnitOfMeasurement.PIECE, "15.00", "28.00", "15.00", 10, "stockout"),
    ("Whole Wheat Flour 2kg", "Groceries", 0, UnitOfMeasurement.PACK, "3.20", "4.80", "0.00", 20, "stockout"),
    # -- trending up (rising weekly demand, >= 4 required — 9.5 had 2) -------
    ("Portable Power Bank", "Electronics", 2, UnitOfMeasurement.PIECE, "14.00", "25.00", "10.00", 12, "trending"),
    ("Steel Lunch Box", "Home & Kitchen", 0, UnitOfMeasurement.PIECE, "5.50", "10.00", "5.00", 15, "trending"),
    ("External Hard Drive 1TB", "Electronics", 1, UnitOfMeasurement.PIECE, "35.00", "58.00", "10.00", 8, "trending"),
    ("Yoga Mat", "Home & Kitchen", 2, UnitOfMeasurement.PIECE, "6.00", "12.00", "5.00", 12, "trending"),
    ("Sticky Notes Pack", "Stationery", 0, UnitOfMeasurement.PACK, "0.80", "1.75", "7.50", 30, "trending"),
    # -- trending down (falling weekly demand — new pattern, Phase 11.5) -----
    ("Analog Wall Clock", "Home & Kitchen", 1, UnitOfMeasurement.PIECE, "7.00", "13.00", "10.00", 10, "trending_down"),
    ("Wired Earphones", "Electronics", 2, UnitOfMeasurement.PIECE, "3.50", "7.50", "10.00", 20, "trending_down"),
    ("Correction Fluid Bottle", "Stationery", 0, UnitOfMeasurement.PIECE, "0.60", "1.40", "7.50", 25, "trending_down"),
    ("Powdered Juice Mix", "Groceries", 1, UnitOfMeasurement.PACK, "1.20", "2.20", "0.00", 25, "trending_down"),
    # -- weekly-seasonal (repeating ~4-week rhythm — new pattern, Phase 11.5) -
    ("Birthday Candle Pack", "Home & Kitchen", 0, UnitOfMeasurement.PACK, "1.00", "2.20", "5.00", 20, "seasonal"),
    ("Printer Ink Cartridge", "Stationery", 1, UnitOfMeasurement.PIECE, "9.00", "16.50", "12.50", 12, "seasonal"),
    ("Frozen Vegetable Pack", "Groceries", 2, UnitOfMeasurement.PACK, "2.40", "3.80", "0.00", 25, "seasonal"),
    ("Phone Screen Protector", "Electronics", 0, UnitOfMeasurement.PIECE, "1.50", "3.50", "10.00", 30, "seasonal"),
    ("Paper Napkin Pack", "Groceries", 1, UnitOfMeasurement.PACK, "1.00", "1.90", "0.00", 30, "seasonal"),
    # -- steady baseline (flat-ish, mild noise — new pattern, Phase 11.5) ----
    ("AA Batteries (Pack of 4)", "Electronics", 1, UnitOfMeasurement.PACK, "1.60", "3.20", "10.00", 25, "steady"),
    ("Dish Washing Liquid", "Home & Kitchen", 2, UnitOfMeasurement.LITER, "1.90", "3.40", "5.00", 20, "steady"),
    ("Whiteboard Marker Set", "Stationery", 0, UnitOfMeasurement.BOX, "2.50", "4.50", "7.50", 15, "steady"),
    ("Tea Bags Box (100pc)", "Groceries", 1, UnitOfMeasurement.BOX, "3.00", "5.00", "0.00", 20, "steady"),
    ("HDMI Cable 2m", "Electronics", 2, UnitOfMeasurement.PIECE, "2.80", "6.00", "10.00", 20, "steady"),
    ("Hand Sanitizer 200ml", "Home & Kitchen", 0, UnitOfMeasurement.PIECE, "1.20", "2.50", "5.00", 25, "steady"),
    ("Sticky Tape Roll", "Stationery", 2, UnitOfMeasurement.PIECE, "0.50", "1.20", "7.50", 30, "steady"),
    # -- spiky / intermittent (mostly-zero weeks — new pattern, Phase 11.5) --
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
        # Backdated events are always strictly before today, never "today"
        # itself — keeps every computed approved_at safely in the past
        # regardless of what wall-clock time this command happens to run at
        # (Part A step 5's "approved_at never in the future" requirement).
        self.max_event_date = self.today - timedelta(days=1)

        self.stdout.write("Flushing database...")
        call_command("flush", interactive=False)

        self.stdout.write("Recreating verification accounts...")
        call_command("seed_test_users")

        self.staff = User.objects.get(username="verify_user")
        self.supervisor = User.objects.get(username="verify_super")

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

        # Phase 10 — SaleService.approve_sale()/cancel_sale() now
        # reclassify synchronously on every call (frontend/classification.
        # py). This seed calls approve_sale() ~180+ times per run, each
        # one firing a real classify_product() against whatever the DB
        # looks like at that exact moment in *real* execution time — which
        # is not yet backdated (this method's own backdating follow-up
        # runs after approve_sale() returns, see _sell()/_receive()).
        # Every one of those intermediate classifications is wrong and
        # gets silently overwritten by the next real event for that same
        # product; only this final pass, run after every date/timestamp in
        # the entire dataset is already correct, produces the classification
        # state the cohort table above was actually built to prove. See
        # docs/project_memory.md §13 for the full disclosure — this is the
        # "bulk seed run triggers reclassification many times" cost Phase
        # 10's own task spec asked to be checked and reported, not silently
        # absorbed.
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

    # ------------------------------------------------------------ primitives

    def _dt(self, on_date, hour, minute=0):
        return timezone.make_aware(datetime.combine(on_date, time(hour, minute)))

    def _new_po(self, product):
        """PurchaseOrder._generate_po_number()'s 4-digit random suffix has
        no collision-retry loop (disclosed, docs/project_memory.md §13) —
        fine for real usage (one or two POs a day), but this seed creates
        every PO within the same few seconds of real wall-clock time, so
        every po_number embeds the *same* real calendar day (the number is
        generated before this method's caller backdates order_date) and
        draws from the same 9000-value space. At this volume that's a
        near-certain birthday-paradox collision, not a rare fluke — retried
        here, in the seed only; the real generator is untouched."""
        for _ in range(20):
            try:
                return PurchaseOrder.objects.create(supplier=product.supplier, created_by=self.staff)
            except IntegrityError:
                continue
        raise CommandError(f"Could not generate a unique po_number for {product.name} after 20 attempts.")

    def _new_sale(self, product, qty, discount):
        """Same collision-retry reasoning as _new_po() above, for
        SaleTransaction._generate_invoice_number()."""
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
        """Real receive: create -> submit -> approve -> receive a single-
        item PO, then backdate order_date/approved_at/the resulting
        InventoryMovement's created_at to `on_date`. Returns the PO."""
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
        po.approved_at = self._dt(on_date, APPROVE_HOUR)  # approved same day, shortly after order
        po.save(update_fields=["order_date", "approved_at"])
        InventoryMovement.objects.filter(pk__gt=movement_floor).update(created_at=self._dt(on_date, RECEIVE_HOUR))
        return po

    def _sell(self, product, qty, on_date, discount=Decimal("0")):
        """Real sell-through: create -> submit -> approve a single-item
        sale, then backdate transaction_date/approved_at/the resulting
        InventoryMovement's created_at to `on_date`. Returns the sale."""
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
        """(days_ago, qty) pairs on a roughly-weekly cadence from
        start_days_ago down to end_days_ago, built from an explicit shape
        — linear trend plus an optional sinusoidal seasonal component
        plus bounded noise — not a random walk (Phase 11.5: the point is
        signal the forecaster can demonstrably recover, not just more
        rows). seasonal_amplitude=0.0 (the default) reduces this to
        Phase 9.5's original trend-plus-noise shape byte-for-byte."""
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
        """Phase 11.5: stocks a shaped, ~55-week sell_events series (from
        _weekly_series) with three receives sized off the series' own
        total demand, spread across the window, then runs everything
        through _run_timeline() for chronological coherence. A hand-
        picked two-receive schedule (Phase 9.5's original approach for
        fast_long/trending) doesn't scale once a product's year-long
        total demand isn't known until the shaped series is actually
        generated — each receive here covers 55% of total demand, so
        even a badly front- or back-loaded shape (trending_down/
        trending_up) keeps real stock non-negative throughout."""
        total_demand = sum(qty for _, qty in sell_events)
        receive_qty = max(15, int(total_demand * 0.55))
        receive_days = [start_days_ago + 5, int(start_days_ago * 0.65), int(start_days_ago * 0.3)]
        timeline = [(d, "receive", receive_qty) for d in receive_days]
        timeline += [(days_ago, "sell", qty) for days_ago, qty in sell_events]
        self._run_timeline(product, timeline)

    # ---------------------------------------------------------- cohort builders
    # Each returns the intended "days ago" of the product's last completed
    # sale, so _print_cohort_report() can cross-check it against what the
    # DB actually measures.

    def _run_timeline(self, product, timeline):
        """timeline: [(days_ago, 'receive'|'sell', qty), ...], any order.
        Executes oldest-first so real Python call order matches the
        intended backdated order — required so stock_before/stock_after
        (computed from *real* stock at the moment of each real call) stay
        coherent with the backdated created_at each row is stamped with
        afterward. Calling receives before sells regardless of their
        relative dates (as an earlier draft of this file did) would let a
        later-dated receive's units silently apply to an earlier-dated
        sell, corrupting the ledger's own internal stock_after sequence —
        caught and fixed before this ever ran for real."""
        for days_ago, action, qty in sorted(timeline, key=lambda e: (-e[0], e[1] != "receive")):
            on_date = self.today - timedelta(days=days_ago)
            if action == "receive":
                self._receive(product, qty, on_date)
            else:
                self._sell(product, qty, on_date)

    def _build_fast_long(self, product):
        """Phase 11.5: extended from ~30 weeks (224 days) to a full
        55-week (12+ month) window, so build_features()'s dropna()
        burn-in (the first ~4 weekly buckets) eats a much smaller share
        of this product's training rows."""
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
        return None  # no sale ever — get_last_sold_date() -> None -> 9999 sentinel

    def _build_short_history(self, product):
        self._receive(product, 30, self.today - timedelta(days=20))
        self._sell(product, 3, self.today - timedelta(days=15))
        self._sell(product, 4, self.today - timedelta(days=5))
        return 5

    def _build_stockout(self, product):
        """Phase 11 finding, fixed here rather than in the pipeline: the
        original version of this cohort (receive day-70, sell down to 0 by
        day-55, restock day-40) put the stockout inside the first ~4
        weekly buckets of the product's *entire* sales history —
        build_features()'s dropna() (lag_4 needs 4 prior periods) drops
        exactly those buckets, so the stockout week never survived into
        the training features at all. stockout_flag came back correctly
        computed by get_stockout_flags() in isolation, then silently
        vanished at the merge — not a pipeline bug, a seed-data one: this
        cohort needed more pre-stockout runway. Six sales before the
        stockout (day-130..day-80, ~7 weekly buckets) now sit ahead of it,
        so the dropna() burn-in eats only the leading weeks, not the
        stockout week itself."""
        self._receive(product, 20, self.today - timedelta(days=140))
        for days_ago, qty in [(130, 3), (120, 3), (110, 3), (100, 3), (90, 3), (80, 5)]:
            self._sell(product, qty, self.today - timedelta(days=days_ago))
        # Real gap: no movement at all between day -80 and day -65 (15
        # days, comfortably >= 1 week) — this window is what stockout_flag
        # exists to catch, and it can only be built by not calling
        # anything here, not by a flag on a fabricated row.
        self._receive(product, 40, self.today - timedelta(days=65))
        for days_ago, qty in [(50, 5), (35, 5), (20, 6)]:
            self._sell(product, qty, self.today - timedelta(days=days_ago))
        last = 10
        self._sell(product, 6, self.today - timedelta(days=last))
        return last

    def _build_trending(self, product):
        """Trending-up: >=4 products required (Phase 11.5; 9.5 had only
        2, over a ~21-week window). Each grows from base_qty toward
        roughly 4x base_qty across the full 55-week window — an
        explicit shape, not a random walk, so the forecaster's recovery
        of the upward trend can be checked directly per product."""
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
        """Trending-down: a pattern 9.5 didn't have (>= 3 required).
        Declines from base_qty toward a low floor over the 55-week
        window (_weekly_series' own max(1, ...) prevents it hitting
        zero) — tests whether the forecaster tracks decline, not just
        growth, relevant to dead-stock onset."""
        base_qty, trend = {
            "Analog Wall Clock": (16, -0.24), "Wired Earphones": (14, -0.20),
            "Correction Fluid Bottle": (12, -0.18), "Powdered Juice Mix": (15, -0.22),
        }[product.name]
        sell_events = self._weekly_series(384, 6, base_qty=base_qty, trend_per_week=trend, skip_prob=0.05)
        last_days_ago = min(d for d, _ in sell_events)
        self._stock_and_sell(product, sell_events, start_days_ago=384)
        return last_days_ago

    def _build_seasonal(self, product):
        """Weekly-seasonal: a repeating ~4-week rhythm (reliable peaks
        every month) at weekly granularity (>= 4 required) — the exact
        pattern lag_1..lag_4 exist to capture, untested by any 9.5
        cohort. 55 weeks gives ~13 full cycles, comfortably clearing
        dropna()'s ~4-week burn-in with room for the rhythm to repeat
        many times over."""
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
        """Steady baseline: flat-ish demand with mild noise, no trend or
        seasonal component (>= 6 required) — the "normal" majority the
        model should predict tightly, i.e. a narrower confidence
        interval than the spiky cohort below."""
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

    # ------------------------------------------------------- non-AI-path records

    def _build_non_completed_records(self):
        """Deliberately-incomplete records: must exist so the AI
        docs'/services' "completed only" filtering has something real to
        exclude. Uses only cohort products that already have a stable,
        already-measured last-sold date (never touches the two "never
        sold" products, so that cohort stays unambiguous regardless of
        whether a given query correctly filters by status — see this
        phase's Part D-adjacent finding that docs/DEMAND_FORECASTING.md's
        own get_sales_dataframe() reference code has no status filter at
        all, unlike docs/DEAD_STOCK_DETECTION.md's get_last_sold_date()).
        Real "now" timestamps — out of the AI-relevant date path entirely,
        so no backdating is needed or attempted here."""
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
        SaleService.cancel_sale(draft_cancel, self.staff, "Customer changed their mind before checkout.")
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

    # -------------------------------------------------------------- verification

    def _verify_coherence(self):
        """Part A step 5: approved_at must never be before the record's own
        business date, and never in the future, across the whole dataset."""
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
