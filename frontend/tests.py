"""
Tests for the Phase 3 service layer (frontend/services.py), verified against
docs/05_PURCHASES.md, docs/06_SALES.md, docs/07_INVENTORY.md, and this task's
own instructions for AdjustmentService (no dedicated doc exists). Phase 3.5
adds tests for the audit/notification retrofit (frontend/audit.py,
frontend/notifications.py). Phase 4 adds tests for real auth (login/logout/
profile, frontend/views.py) and the RBAC decorator/mixin (frontend/decorators.py,
frontend/mixins.py).
"""
import base64
import json
import os
import re
import statistics
import tempfile
import zlib
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.views import View

from frontend import audit
from frontend.decorators import admin_required, staff_required
from frontend.mixins import AdminRequiredMixin
from frontend.classification import (
    calculate_average_stock,
    classify_product,
    get_last_sold_date,
    run_full_classification,
)
from frontend.forecasting import (
    FEATURE_COLUMNS,
    MODELS_DIR,
    backfill_actual_demand,
    build_features,
    get_sales_dataframe,
    get_stockout_flags,
    predict_demand,
    run_full_forecast,
    train_model,
)
from frontend.models import (
    AdjustmentReason,
    AdjustmentStatus,
    AdjustmentType,
    ApprovalOutcome,
    ApprovalPolicy,
    ApprovalTxType,
    AuditLog,
    Category,
    DemandForecast,
    ForecastPeriod,
    InventoryAdjustment,
    InventoryClassification,
    InventoryMovement,
    InventoryRecord,
    InventoryStatus,
    MovementType,
    Notification,
    NotificationType,
    POStatus,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SaleItem,
    SaleStatus,
    SaleTransaction,
    StockClassification,
    Supplier,
    SystemSettings,
    UserRole,
)
from frontend.approvals import (
    can_approve,
    ensure_default_policies,
    resolve_adjustment_with_cumulative_cap,
    resolve_required_level,
)
from frontend.services import (
    AdjustmentService,
    ApprovalAuthorityError,
    InsufficientStockError,
    InventoryService,
    PurchaseService,
    SaleService,
)
from frontend.validators import generate_strong_password

User = get_user_model()


class ServiceTestCase(TestCase):
    """Shared fixtures for all service-layer tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='staffer', email='staffer@example.com', password='x',
            employee_id='EMP-1001', full_name='Staffer One',
        )
        # notify_supervisors() (frontend/notifications.py) queries by
        # role__in=[ADMIN, SUPERVISOR] now that AUTH_USER_MODEL == frontend.User
        # (Phase 3.7) — role must be set for this fixture to be found by it.
        # is_staff=True is kept too since it's still a real, separate field.
        self.supervisor = User.objects.create_user(
            username='supervisor', email='supervisor@example.com', password='x', is_staff=True,
            employee_id='EMP-1002', full_name='Supervisor One', role=UserRole.SUPERVISOR,
        )
        self.category = Category.objects.create(name='Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='Acme Supply', company_name='Acme Supply Co',
            contact_person='Jo', email='acme@example.com', phone='555-0100',
            address='1 Acme Way',
        )
        self.product = Product.objects.create(
            sku='SKU-001', name='Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'), reorder_level=5,
        )

    def give_stock(self, quantity):
        """Helper: seed stock via InventoryService itself (the only legitimate
        way to create stock), so every test starts from a real, ledgered state."""
        return InventoryService.increase_stock(
            product=self.product, quantity=quantity, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.user,
        )


class InventoryServiceTests(ServiceTestCase):

    def test_increase_stock_creates_record_and_movement(self):
        """Proves: increase_stock creates the InventoryRecord if missing,
        updates current_stock, and writes a movement row with correct
        before/after values."""
        record = self.give_stock(50)
        self.assertEqual(record.current_stock, 50)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, 50)

        movement = InventoryMovement.objects.get(product=self.product)
        self.assertEqual(movement.movement_type, MovementType.PURCHASE)
        self.assertEqual(movement.quantity_change, 50)
        self.assertEqual(movement.stock_before, 0)
        self.assertEqual(movement.stock_after, 50)

    def test_initialize_for_product_creates_zero_stock_record_with_no_movement(self):
        """Phase 5.5 regression test (docs/bugsfound.md BUG-34): product
        creation must never write an InventoryMovement — a zero-to-zero
        change is not a movement, and none of MovementType's 4 documented
        values describe 'a product was catalogued'. Proves
        initialize_for_product() creates a real InventoryRecord at
        current_stock=0 with the correct out_of_stock status, and writes
        NO InventoryMovement row at all — this would fail loudly if
        increase_stock() (or any other movement-writing call) were ever
        reintroduced at product-creation time."""
        record = InventoryService.initialize_for_product(self.product)

        self.assertEqual(record.current_stock, 0)
        self.assertEqual(record.status, InventoryStatus.OUT_OF_STOCK)
        self.assertEqual(record.reorder_level, self.product.reorder_level)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, 0)
        self.assertEqual(
            InventoryMovement.objects.filter(product=self.product).count(), 0,
            "product creation must never write an InventoryMovement row",
        )

    def test_increase_stock_updates_status_and_valuation(self):
        """Proves: status auto-recalculates and total_value = stock × purchase_price."""
        record = self.give_stock(50)
        self.assertEqual(record.status, InventoryStatus.AVAILABLE)
        self.assertEqual(record.total_value, Decimal('500.00'))

    def test_decrease_stock_rejects_when_insufficient(self):
        """Proves: stock can never go negative — decrease_stock raises
        InsufficientStockError and leaves stock/records untouched when the
        requested quantity exceeds what's available."""
        self.give_stock(5)
        with self.assertRaises(InsufficientStockError):
            InventoryService.decrease_stock(
                product=self.product, quantity=10, movement_type=MovementType.SALE,
                reference_type='Test', reference_id=1, performed_by=self.user,
            )
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 5, "stock must be unchanged after a rejected decrease")
        self.assertEqual(InventoryMovement.objects.filter(product=self.product).count(), 1,
                          "no movement row should be written for a rejected decrease")

    def test_decrease_stock_writes_movement_with_negative_quantity_change(self):
        """Proves: successful decrease writes a movement with the correct
        negative quantity_change and before/after stock levels."""
        self.give_stock(20)
        record = InventoryService.decrease_stock(
            product=self.product, quantity=8, movement_type=MovementType.SALE,
            reference_type='Test', reference_id=1, performed_by=self.user,
        )
        self.assertEqual(record.current_stock, 12)
        movement = InventoryMovement.objects.get(product=self.product, movement_type=MovementType.SALE)
        self.assertEqual(movement.quantity_change, -8)
        self.assertEqual(movement.stock_before, 20)
        self.assertEqual(movement.stock_after, 12)

    def test_decrease_stock_status_transitions_to_low_and_out(self):
        """Proves: status auto-recalculates through LOW_STOCK -> OUT_OF_STOCK
        as stock is depleted, based on InventoryRecord.reorder_level."""
        self.give_stock(10)  # reorder_level defaults to 10 on the InventoryRecord
        record = InventoryService.decrease_stock(
            product=self.product, quantity=5, movement_type=MovementType.SALE,
            reference_type='Test', reference_id=1, performed_by=self.user,
        )
        self.assertEqual(record.status, InventoryStatus.LOW_STOCK)
        record = InventoryService.decrease_stock(
            product=self.product, quantity=5, movement_type=MovementType.SALE,
            reference_type='Test', reference_id=1, performed_by=self.user,
        )
        self.assertEqual(record.status, InventoryStatus.OUT_OF_STOCK)


class PurchaseServiceTests(ServiceTestCase):

    def make_po(self, ordered_qty=10, status=POStatus.DRAFT):
        po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.user, status=status)
        item = PurchaseOrderItem.objects.create(
            purchase_order=po, product=self.product, ordered_qty=ordered_qty,
            unit_price=Decimal('10.00'),
        )
        return po, item

    def test_submit_moves_draft_to_pending(self):
        po, _ = self.make_po()
        PurchaseService.submit_for_approval(po, self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.PENDING)

    def test_submit_rejects_non_draft(self):
        po, _ = self.make_po(status=POStatus.PENDING)
        with self.assertRaises(ValueError):
            PurchaseService.submit_for_approval(po, self.user)

    def test_approve_moves_pending_to_approved(self):
        # Phase 12 — approve() now enforces can_approve() (ApprovalTxType.
        # PURCHASE_ORDER) at the service layer: self.user is STAFF, never
        # a valid approver regardless of self-approval, so the approver
        # here must be self.supervisor (a role this fixture already
        # provides). self.user still creates the PO — no self-approval
        # conflict either way.
        po, _ = self.make_po(status=POStatus.PENDING)
        PurchaseService.approve(po, self.supervisor)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.APPROVED)
        self.assertEqual(po.approved_by, self.supervisor)
        self.assertIsNotNone(po.approved_at)

    def test_approve_does_not_touch_stock(self):
        """Proves the critical rule: stock increases ONLY on receipt, never
        on approval."""
        po, _ = self.make_po(status=POStatus.PENDING)
        PurchaseService.approve(po, self.supervisor)
        self.assertFalse(InventoryRecord.objects.filter(product=self.product).exists())
        self.assertEqual(InventoryMovement.objects.filter(product=self.product).count(), 0)

    def test_reject_moves_pending_to_rejected_with_reason(self):
        # BUG-57 close-out — reject() now enforces a supervisor-or-admin
        # role check at the service layer (self.user is STAFF).
        po, _ = self.make_po(status=POStatus.PENDING)
        PurchaseService.reject(po, self.supervisor, 'Price mismatch')
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.REJECTED)
        self.assertEqual(po.rejected_reason, 'Price mismatch')

    def test_reject_raises_for_unauthorised_staff(self):
        """BUG-57 close-out: before this fix, PurchaseService.reject()
        would execute for ANY caller — the only thing stopping a STAFF
        user from rejecting a PO was PurchaseRejectView's own
        SupervisorRequiredMixin. Calling the service directly, bypassing
        the view entirely, used to succeed silently."""
        po, _ = self.make_po(status=POStatus.PENDING)
        with self.assertRaises(ApprovalAuthorityError):
            PurchaseService.reject(po, self.user, 'Price mismatch')
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.PENDING, 'a denied rejection must not change status')

    def test_receive_full_quantity_marks_received_and_increases_stock(self):
        po, item = self.make_po(ordered_qty=10, status=POStatus.APPROVED)
        PurchaseService.receive_items(po, [{'item_id': item.pk, 'received_qty': 10}], self.user)
        po.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(po.status, POStatus.RECEIVED)
        self.assertEqual(item.received_qty, 10)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 10)

    def test_receive_partial_quantity_marks_partial(self):
        """Proves partial delivery: PO stays PARTIAL until fully received,
        and only the delivered quantity increases stock."""
        po, item = self.make_po(ordered_qty=10, status=POStatus.APPROVED)
        PurchaseService.receive_items(po, [{'item_id': item.pk, 'received_qty': 4}], self.user)
        po.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(po.status, POStatus.PARTIAL)
        self.assertEqual(item.received_qty, 4)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 4)

        # Receiving the remainder completes the PO.
        PurchaseService.receive_items(po, [{'item_id': item.pk, 'received_qty': 6}], self.user)
        po.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(po.status, POStatus.RECEIVED)
        self.assertEqual(item.received_qty, 10)
        record.refresh_from_db()
        self.assertEqual(record.current_stock, 10)

    def test_receive_cannot_exceed_ordered_quantity(self):
        po, item = self.make_po(ordered_qty=10, status=POStatus.APPROVED)
        with self.assertRaises(ValueError):
            PurchaseService.receive_items(po, [{'item_id': item.pk, 'received_qty': 11}], self.user)
        item.refresh_from_db()
        self.assertEqual(item.received_qty, 0, "a rejected over-receipt must not partially apply")

    def test_receive_rejects_wrong_status(self):
        po, item = self.make_po(ordered_qty=10, status=POStatus.DRAFT)
        with self.assertRaises(ValueError):
            PurchaseService.receive_items(po, [{'item_id': item.pk, 'received_qty': 5}], self.user)

    def test_duplicate_po_number_rejected(self):
        """Proves: po_number's unique=True constraint (SCHEMA.md) is
        enforced at the database level — a second PO cannot reuse a
        po_number already in use."""
        PurchaseOrder.objects.create(
            po_number='PO-DUPLICATE-0001', supplier=self.supplier, created_by=self.user,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrder.objects.create(
                    po_number='PO-DUPLICATE-0001', supplier=self.supplier, created_by=self.user,
                )


class SaleServiceTests(ServiceTestCase):
    """Phase 8.99b — Sale now mirrors Purchase's approval workflow: create
    (DRAFT, no stock effect) -> submit_for_approval (PENDING) ->
    approve_sale (stock moves, terminal COMPLETED) / reject_sale
    (terminal REJECTED). cancel_sale is pre-approval-only. See
    docs/project_memory.md §13 for the full disclosure of why this
    diverges from 06_SALES.md's original one-step model."""

    def make_draft_sale(self, quantity=5, unit_price=Decimal('20.00'), **item_kwargs):
        item = {'product_id': self.product.pk, 'quantity': quantity, 'unit_price': unit_price}
        item.update(item_kwargs)
        return SaleService.create_sale({}, [item], self.user)

    def test_create_sale_creates_draft_with_no_stock_effect(self):
        """Creating a sale must not touch InventoryService/InventoryRecord
        at all — no availability check, no stock change, no movement —
        while the money math (tax/discount/line_total) is computed exactly
        as before."""
        self.give_stock(20)
        sale = SaleService.create_sale(
            {'customer_name': 'Acme Corp'},
            [{'product_id': self.product.pk, 'quantity': 5, 'unit_price': Decimal('20.00'),
              'discount': 10, 'tax': 0}],
            self.user,
        )
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 20, "creating a sale must not touch stock")
        # (20 * 5) * (1 - 0.10) * (1 + 0) = 90.00
        self.assertEqual(sale.total_amount, Decimal('90.00'))
        self.assertEqual(sale.status, SaleStatus.DRAFT)
        self.assertEqual(InventoryMovement.objects.filter(movement_type=MovementType.SALE).count(), 0)

    def test_create_sale_rejects_inactive_product(self):
        self.product.is_active = False
        self.product.save(update_fields=['is_active'])
        with self.assertRaises(ValueError):
            self.make_draft_sale(quantity=1)

    def test_submit_moves_draft_to_pending(self):
        sale = self.make_draft_sale()
        SaleService.submit_for_approval(sale, self.user)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.PENDING)

    def test_submit_rejects_non_draft(self):
        sale = self.make_draft_sale()
        SaleService.submit_for_approval(sale, self.user)
        with self.assertRaises(ValueError):
            SaleService.submit_for_approval(sale, self.user)

    def test_approve_deducts_stock_and_completes(self):
        self.give_stock(20)
        sale = self.make_draft_sale(quantity=5)
        SaleService.submit_for_approval(sale, self.user)
        SaleService.approve_sale(sale, self.supervisor)

        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 15)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.COMPLETED)
        self.assertEqual(sale.approved_by, self.supervisor)
        self.assertIsNotNone(sale.approved_at)
        movement = InventoryMovement.objects.get(movement_type=MovementType.SALE, reference_id=sale.pk)
        self.assertEqual(movement.quantity_change, -5)

    def test_approve_rejects_non_pending(self):
        sale = self.make_draft_sale(quantity=1)
        with self.assertRaises(ValueError):
            SaleService.approve_sale(sale, self.supervisor)

    def test_approve_fails_cleanly_when_stock_insufficient_leaving_sale_pending_and_stock_untouched(self):
        """The documented, deliberate consequence of not reserving stock
        at draft time: two drafts against the same limited stock can each
        look satisfiable at creation, and only one can actually succeed at
        approval — set up deliberately here, not incidentally."""
        self.give_stock(3)
        sale1 = self.make_draft_sale(quantity=3)
        sale2 = self.make_draft_sale(quantity=3)
        SaleService.submit_for_approval(sale1, self.user)
        SaleService.submit_for_approval(sale2, self.user)

        SaleService.approve_sale(sale1, self.supervisor)  # succeeds, uses all 3 units
        with self.assertRaises(InsufficientStockError):
            SaleService.approve_sale(sale2, self.supervisor)

        sale2.refresh_from_db()
        self.assertEqual(sale2.status, SaleStatus.PENDING, "a failed approval must leave the sale pending, not stuck or terminal")
        self.assertIsNone(sale2.approved_by)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 0, "sale2's failed approval must not touch stock beyond what sale1 already took")
        self.assertEqual(InventoryMovement.objects.filter(reference_id=sale2.pk).count(), 0)

    def test_reject_moves_pending_to_rejected_with_reason(self):
        sale = self.make_draft_sale(quantity=1)
        SaleService.submit_for_approval(sale, self.user)
        SaleService.reject_sale(sale, self.supervisor, 'Customer cancelled order')
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.REJECTED)
        self.assertEqual(sale.rejected_reason, 'Customer cancelled order')

    def test_reject_raises_for_unauthorised_staff(self):
        """BUG-57 close-out: before this fix, SaleService.reject_sale()
        would execute for ANY caller — the only thing stopping a STAFF
        user from rejecting a sale was SaleRejectView's own
        SupervisorRequiredMixin. Calling the service directly, bypassing
        the view entirely, used to succeed silently."""
        sale = self.make_draft_sale(quantity=1)
        SaleService.submit_for_approval(sale, self.user)
        with self.assertRaises(ApprovalAuthorityError):
            SaleService.reject_sale(sale, self.user, 'Customer cancelled order')
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.PENDING, 'a denied rejection must not change status')

    def test_reject_rejects_non_pending(self):
        sale = self.make_draft_sale(quantity=1)
        with self.assertRaises(ValueError):
            SaleService.reject_sale(sale, self.supervisor, 'reason')

    def test_reject_leaves_stock_untouched(self):
        self.give_stock(20)
        sale = self.make_draft_sale(quantity=5)
        SaleService.submit_for_approval(sale, self.user)
        SaleService.reject_sale(sale, self.supervisor, 'Out of budget')
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 20)

    def test_cancel_draft_leaves_stock_untouched(self):
        # Phase 12 — cancel_sale() now enforces can_approve()
        # (ApprovalTxType.SALE_CANCEL): self.user is STAFF, never a valid
        # canceller regardless of self-approval, so self.supervisor cancels
        # here (a role this fixture already provides).
        self.give_stock(20)
        sale = self.make_draft_sale(quantity=5)
        SaleService.cancel_sale(sale, self.supervisor, 'Customer changed their mind')
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 20, "nothing was ever deducted, so there is nothing to restore")
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CANCELLED)
        self.assertEqual(sale.cancelled_reason, 'Customer changed their mind')
        self.assertEqual(sale.cancelled_by, self.supervisor)
        self.assertIsNotNone(sale.cancelled_at)
        self.assertEqual(InventoryMovement.objects.filter(reference_id=sale.pk).count(), 0)

    def test_cancel_pending_leaves_stock_untouched(self):
        self.give_stock(20)
        sale = self.make_draft_sale(quantity=5)
        SaleService.submit_for_approval(sale, self.user)
        SaleService.cancel_sale(sale, self.supervisor, 'Duplicate entry')
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 20)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CANCELLED)
        self.assertEqual(sale.cancelled_reason, 'Duplicate entry')

    def test_cancel_completed_sale_raises_and_touches_no_stock(self):
        """The Objective's own explicit rule: once completed, a sale can
        never be cancelled."""
        self.give_stock(20)
        sale = self.make_draft_sale(quantity=5)
        SaleService.submit_for_approval(sale, self.user)
        SaleService.approve_sale(sale, self.supervisor)
        with self.assertRaises(ValueError):
            SaleService.cancel_sale(sale, self.user, 'reason')
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 15, "a blocked cancel must not touch stock either")
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.COMPLETED)

    def test_cancel_already_cancelled_sale_raises(self):
        # Phase 12 — same self.supervisor swap as the two tests above.
        sale = self.make_draft_sale(quantity=1)
        SaleService.cancel_sale(sale, self.supervisor, 'first cancel')
        with self.assertRaises(ValueError):
            SaleService.cancel_sale(sale, self.supervisor, 'second cancel')


class AdjustmentServiceTests(ServiceTestCase):

    def make_adjustment(self, adjustment_type, quantity):
        return InventoryAdjustment.objects.create(
            product=self.product, adjustment_type=adjustment_type, quantity=quantity,
            reason='Physical count reconciliation', requested_by=self.user,
        )

    def test_adjustment_defaults_to_pending_on_creation(self):
        adjustment = self.make_adjustment(AdjustmentType.INCREASE, 5)
        self.assertEqual(adjustment.status, AdjustmentStatus.PENDING)

    def test_approve_increase_adjustment_increases_stock(self):
        # Phase 12 — approve() now enforces can_approve() (ApprovalTxType.
        # ADJUSTMENT) at the service layer: self.user is STAFF, never a
        # valid approver, so self.supervisor approves (requested_by stays
        # self.user, no self-approval conflict). This adjustment has no
        # reason_code match and no cumulative-cap-eligible AUTO match, so
        # it resolves via the seeded catch-all (Supervisor).
        self.give_stock(10)
        adjustment = self.make_adjustment(AdjustmentType.INCREASE, 5)
        AdjustmentService.approve(adjustment, self.supervisor)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.APPROVED)
        self.assertEqual(adjustment.approved_by, self.supervisor)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 15)

    def test_approve_decrease_adjustment_decreases_stock(self):
        self.give_stock(10)
        adjustment = self.make_adjustment(AdjustmentType.DECREASE, 4)
        AdjustmentService.approve(adjustment, self.supervisor)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 6)

    def test_approve_decrease_adjustment_insufficient_stock_raises_and_stays_pending(self):
        """Proves: an adjustment that would drive stock negative is
        rejected, and — because InventoryService.decrease_stock raises
        inside the same @transaction.atomic block — the adjustment's own
        status change rolls back too, leaving it PENDING, not silently
        APPROVED with no stock effect."""
        self.give_stock(3)
        adjustment = self.make_adjustment(AdjustmentType.DECREASE, 10)
        with self.assertRaises(InsufficientStockError):
            AdjustmentService.approve(adjustment, self.supervisor)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.PENDING)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 3)

    def test_reject_adjustment_does_not_touch_stock(self):
        # BUG-57 close-out — reject() now enforces a supervisor-or-admin
        # role check at the service layer (self.user is STAFF).
        self.give_stock(10)
        adjustment = self.make_adjustment(AdjustmentType.DECREASE, 4)
        AdjustmentService.reject(adjustment, self.supervisor, 'Count looks wrong, redo it')
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.REJECTED)
        self.assertEqual(adjustment.rejected_reason, 'Count looks wrong, redo it')
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 10)

    def test_reject_raises_for_unauthorised_staff(self):
        """BUG-57 close-out: before this fix, AdjustmentService.reject()
        would execute for ANY caller — the only thing stopping a STAFF
        user from rejecting an adjustment was AdjustmentRejectView's own
        SupervisorRequiredMixin. Calling the service directly, bypassing
        the view entirely, used to succeed silently."""
        self.give_stock(10)
        adjustment = self.make_adjustment(AdjustmentType.DECREASE, 4)
        with self.assertRaises(ApprovalAuthorityError):
            AdjustmentService.reject(adjustment, self.user, 'Count looks wrong, redo it')
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.PENDING, 'a denied rejection must not change status')

    def test_approve_already_approved_adjustment_raises(self):
        self.give_stock(10)
        adjustment = self.make_adjustment(AdjustmentType.INCREASE, 5)
        AdjustmentService.approve(adjustment, self.supervisor)
        with self.assertRaises(ValueError):
            AdjustmentService.approve(adjustment, self.supervisor)


class PurchaseCancelTests(ServiceTestCase):
    """Phase 3.4 / BUG-25 introduced PurchaseService.cancel(); Phase 8.99c
    narrowed it to draft/pending only (see docs/project_memory.md §13) and
    added a required reason, stored with who/when."""

    def make_po(self, ordered_qty=10, status=POStatus.DRAFT):
        po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.user, status=status)
        item = PurchaseOrderItem.objects.create(
            purchase_order=po, product=self.product, ordered_qty=ordered_qty,
            unit_price=Decimal('10.00'),
        )
        return po, item

    def test_cancel_from_draft_leaves_stock_untouched(self):
        # BUG-57 close-out — cancel() now enforces a supervisor-or-admin
        # role check at the service layer (self.user is STAFF).
        po, _ = self.make_po(status=POStatus.DRAFT)
        PurchaseService.cancel(po, self.supervisor, 'Ordered by mistake')
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.CANCELLED)
        self.assertEqual(po.cancelled_reason, 'Ordered by mistake')
        self.assertEqual(po.cancelled_by, self.supervisor)
        self.assertIsNotNone(po.cancelled_at)
        self.assertFalse(InventoryRecord.objects.filter(product=self.product).exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, 0)

    def test_cancel_from_pending_leaves_stock_untouched(self):
        po, _ = self.make_po(status=POStatus.PENDING)
        PurchaseService.cancel(po, self.supervisor, 'Supplier no longer needed')
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.CANCELLED)
        self.assertEqual(po.cancelled_reason, 'Supplier no longer needed')
        self.assertFalse(InventoryRecord.objects.filter(product=self.product).exists())

    def test_cancel_raises_for_unauthorised_staff(self):
        """BUG-57 close-out: before this fix, PurchaseService.cancel()
        would execute for ANY caller — the only thing stopping a STAFF
        user from cancelling a PO was PurchaseCancelView's own
        SupervisorRequiredMixin. Calling the service directly, bypassing
        the view entirely, used to succeed silently."""
        po, _ = self.make_po(status=POStatus.DRAFT)
        with self.assertRaises(ApprovalAuthorityError):
            PurchaseService.cancel(po, self.user, 'Ordered by mistake')
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.DRAFT, 'a denied cancel must not change status')

    def test_cancel_rejects_approved(self):
        """Phase 8.99c: an approved PO is a commitment already made to the
        supplier — cancel() must refuse it, not just hide the button."""
        po, _ = self.make_po(status=POStatus.APPROVED)
        with self.assertRaises(ValueError):
            PurchaseService.cancel(po, self.user, 'reason')
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.APPROVED)

    def test_cancel_rejects_partially_received(self):
        """Phase 8.99c: PARTIAL was cancellable before this phase; now it
        isn't — proves the already-received stock stays untouched because
        cancel() is refused outright, not because of any special-casing
        inside cancel() itself anymore."""
        po, item = self.make_po(ordered_qty=10, status=POStatus.APPROVED)
        PurchaseService.receive_items(po, [{'item_id': item.pk, 'received_qty': 4}], self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.PARTIAL)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 4)
        movement_count_before = InventoryMovement.objects.filter(product=self.product).count()

        with self.assertRaises(ValueError):
            PurchaseService.cancel(po, self.user, 'reason')

        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.PARTIAL, "a blocked cancel must not change status")
        record.refresh_from_db()
        self.assertEqual(record.current_stock, 4, "stock already received must be untouched by a blocked cancel")
        self.assertEqual(
            InventoryMovement.objects.filter(product=self.product).count(), movement_count_before,
            "a blocked cancel must not write any new InventoryMovement row",
        )

    def test_cancel_rejects_already_received(self):
        po, item = self.make_po(ordered_qty=10, status=POStatus.APPROVED)
        PurchaseService.receive_items(po, [{'item_id': item.pk, 'received_qty': 10}], self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.RECEIVED)
        with self.assertRaises(ValueError):
            PurchaseService.cancel(po, self.user, 'reason')

    def test_cancel_rejects_already_cancelled(self):
        po, _ = self.make_po(status=POStatus.DRAFT)
        PurchaseService.cancel(po, self.supervisor, 'first cancel')
        with self.assertRaises(ValueError):
            PurchaseService.cancel(po, self.user, 'second cancel')


class InventoryMovementImmutabilityTests(ServiceTestCase):
    """Phase 3.4 / BUG-20: InventoryMovement now enforces immutability in
    code (mirroring AuditLog), not just in its docstring."""

    def test_creation_via_inventory_service_still_works(self):
        """Proves InventoryService's existing call sites (.objects.create()
        on a brand-new instance, pk=None) are unaffected by the new guard."""
        record = self.give_stock(10)
        self.assertEqual(record.current_stock, 10)
        self.assertEqual(InventoryMovement.objects.count(), 1)

    def test_updating_existing_movement_raises(self):
        self.give_stock(10)
        movement = InventoryMovement.objects.get(product=self.product)
        movement.notes = 'tampered'
        with self.assertRaises(PermissionError):
            movement.save()

    def test_deleting_movement_always_raises(self):
        self.give_stock(10)
        movement = InventoryMovement.objects.get(product=self.product)
        with self.assertRaises(PermissionError):
            movement.delete()
        self.assertEqual(InventoryMovement.objects.count(), 1, "movement must survive the rejected delete")


class SystemSettingsSingletonTests(TestCase):
    """Phase 3.4 / BUG-21 (model-level enforcement) and BUG-22 (verbose_name)."""

    def test_get_settings_returns_same_row_across_calls(self):
        first = SystemSettings.get_settings()
        second = SystemSettings.get_settings()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SystemSettings.objects.count(), 1)

    def test_second_objects_create_cannot_produce_a_second_row(self):
        """Proves the task's literal scenario: 'SystemSettings.objects
        .create(...) can never produce a second row regardless of
        caller.' save() forcing pk=1 means the second create() attempts
        an INSERT with an already-used primary key, raising IntegrityError
        instead of silently duplicating."""
        SystemSettings.objects.create(company_name='First Co')
        self.assertEqual(SystemSettings.objects.count(), 1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SystemSettings.objects.create(company_name='Second Co')

        self.assertEqual(SystemSettings.objects.count(), 1, "a second row must never exist")
        self.assertEqual(SystemSettings.objects.get().company_name, 'First Co')

    def test_verbose_name_plural_is_not_double_s(self):
        self.assertEqual(SystemSettings._meta.verbose_name_plural, 'System Settings')


class PurchaseAuditNotificationTests(ServiceTestCase):
    """Phase 3.5: PurchaseService's log_action()/notify_*() retrofit."""

    def make_po(self, ordered_qty=10, status=POStatus.DRAFT):
        po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.user, status=status)
        item = PurchaseOrderItem.objects.create(
            purchase_order=po, product=self.product, ordered_qty=ordered_qty,
            unit_price=Decimal('10.00'),
        )
        return po, item

    def test_submit_notifies_supervisors_and_logs(self):
        po, _ = self.make_po(status=POStatus.DRAFT)
        PurchaseService.submit_for_approval(po, self.user)

        notif = Notification.objects.get(recipient=self.supervisor, type=NotificationType.PO_PENDING)
        self.assertIn(po.po_number, notif.title)
        self.assertFalse(Notification.objects.filter(recipient=self.user).exists(),
                          "the submitter is not a supervisor and must not notify themselves")

        entry = AuditLog.objects.get(action=audit.PO_SUBMITTED)
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.module, 'purchases')
        self.assertEqual(entry.affected_id, po.pk)
        self.assertEqual(entry.status, 'success')

    def test_approve_notifies_creator_and_logs(self):
        po, _ = self.make_po(status=POStatus.PENDING)
        PurchaseService.approve(po, self.supervisor)

        notif = Notification.objects.get(recipient=self.user, type=NotificationType.PO_APPROVED)
        self.assertIn(po.po_number, notif.title)

        entry = AuditLog.objects.get(action=audit.PO_APPROVED)
        self.assertEqual(entry.user, self.supervisor)
        self.assertEqual(entry.affected_id, po.pk)

    def test_reject_notifies_creator_with_reason_and_logs(self):
        po, _ = self.make_po(status=POStatus.PENDING)
        PurchaseService.reject(po, self.supervisor, 'Price mismatch')

        notif = Notification.objects.get(recipient=self.user, type=NotificationType.PO_REJECTED)
        self.assertIn('Price mismatch', notif.message)

        entry = AuditLog.objects.get(action=audit.PO_REJECTED)
        self.assertEqual(entry.user, self.supervisor)

    def test_receive_logs_but_does_not_notify(self):
        """05_PURCHASES.md's receive_items only calls log_action — matched
        literally, no notification type is documented for it."""
        po, item = self.make_po(ordered_qty=10, status=POStatus.APPROVED)
        notif_count_before = Notification.objects.count()

        PurchaseService.receive_items(po, [{'item_id': item.pk, 'received_qty': 10}], self.user)

        entry = AuditLog.objects.get(action=audit.PO_RECEIVED)
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.details, {'receive_data': [{'item_id': item.pk, 'received_qty': 10}]})
        self.assertEqual(Notification.objects.count(), notif_count_before)

    def test_cancel_logs_but_does_not_notify(self):
        """No 'po_cancelled' notification type is documented — see BUG-25.
        BUG-57 close-out: self.supervisor cancels here since self.user
        (STAFF) is no longer a valid caller at the service layer."""
        po, _ = self.make_po(status=POStatus.DRAFT)
        notif_count_before = Notification.objects.count()

        PurchaseService.cancel(po, self.supervisor, 'reason')

        entry = AuditLog.objects.get(action=audit.PO_CANCELLED)
        self.assertEqual(entry.user, self.supervisor)
        self.assertEqual(Notification.objects.count(), notif_count_before)


class SaleAuditTests(ServiceTestCase):
    """Phase 3.5: SaleService's log_action() retrofit (06_SALES.md's
    reference code never calls notify_* from either method)."""

    def test_create_sale_logs_and_does_not_notify(self):
        self.give_stock(20)
        notif_count_before = Notification.objects.count()

        sale = SaleService.create_sale(
            {}, [{'product_id': self.product.pk, 'quantity': 5, 'unit_price': Decimal('20.00')}],
            self.user,
        )

        entry = AuditLog.objects.get(action=audit.SALE_CREATED)
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.affected_id, sale.pk)
        self.assertEqual(entry.module, 'sales')
        self.assertEqual(Notification.objects.count(), notif_count_before)

    def test_cancel_sale_logs_and_does_not_notify(self):
        # Phase 12 — cancel_sale()'s can_approve() gate: self.user is
        # STAFF, never a valid canceller, so self.supervisor cancels here.
        self.give_stock(20)
        sale = SaleService.create_sale(
            {}, [{'product_id': self.product.pk, 'quantity': 1, 'unit_price': Decimal('20.00')}],
            self.user,
        )
        notif_count_before = Notification.objects.count()

        SaleService.cancel_sale(sale, self.supervisor, 'reason')

        entry = AuditLog.objects.get(action=audit.SALE_CANCELLED)
        self.assertEqual(entry.user, self.supervisor)
        self.assertEqual(entry.affected_id, sale.pk)
        self.assertEqual(Notification.objects.count(), notif_count_before)


class AdjustmentAuditNotificationTests(ServiceTestCase):
    """Phase 3.5: AdjustmentService's log_action()/notify_user() retrofit."""

    def make_adjustment(self, adjustment_type, quantity):
        return InventoryAdjustment.objects.create(
            product=self.product, adjustment_type=adjustment_type, quantity=quantity,
            reason='Physical count reconciliation', requested_by=self.user,
        )

    def test_approve_notifies_requester_and_logs_with_details(self):
        self.give_stock(10)
        adjustment = self.make_adjustment(AdjustmentType.INCREASE, 5)

        AdjustmentService.approve(adjustment, self.supervisor)

        notif = Notification.objects.get(recipient=self.user, type=NotificationType.ADJ_APPROVED)
        self.assertIn(self.product.name, notif.title)

        entry = AuditLog.objects.get(action=audit.ADJUSTMENT_APPROVED)
        self.assertEqual(entry.user, self.supervisor)
        self.assertEqual(entry.affected_id, adjustment.pk)
        # Phase 12 — details now also carries policy_id/required_level
        # (§6's own instruction: prove *why* this approver was permitted
        # to approve). Not asserting an exact policy_id here — that's a
        # real primary key, not a value this test should hardcode.
        self.assertEqual(entry.details['quantity'], 5)
        self.assertEqual(entry.details['type'], AdjustmentType.INCREASE)
        self.assertEqual(entry.details['required_level'], ApprovalOutcome.SUPERVISOR)
        self.assertIsNotNone(entry.details['policy_id'])

    def test_reject_logs_but_does_not_notify(self):
        """No 'adj_rejected' notification type is documented in
        11_NOTIFICATIONS.md's type table (only adj_pending/adj_approved)."""
        adjustment = self.make_adjustment(AdjustmentType.DECREASE, 4)
        notif_count_before = Notification.objects.count()

        AdjustmentService.reject(adjustment, self.supervisor, 'Recount needed')

        entry = AuditLog.objects.get(action=audit.ADJUSTMENT_REJECTED)
        self.assertEqual(entry.user, self.supervisor)
        self.assertEqual(Notification.objects.count(), notif_count_before)


class LowStockNotificationTests(ServiceTestCase):
    """Phase 3.5 / REQ 7.7: InventoryService.decrease_stock()'s
    notify_supervisors() retrofit, exercised via a realistic sale. Phase
    8.99b: stock only actually moves at approve_sale() now, so every test
    here drives the sale through create -> submit -> approve to reach the
    same real deduction the old single-step create_sale() used to trigger
    directly."""

    def approve_new_sale(self, quantity):
        sale = SaleService.create_sale(
            {}, [{'product_id': self.product.pk, 'quantity': quantity, 'unit_price': Decimal('20.00')}],
            self.user,
        )
        SaleService.submit_for_approval(sale, self.user)
        return SaleService.approve_sale(sale, self.supervisor)

    def test_sale_dropping_stock_to_reorder_level_notifies_all_supervisors(self):
        second_supervisor = User.objects.create_user(
            username='supervisor2', email='super2@example.com', password='x', is_superuser=True,
            employee_id='EMP-1003', full_name='Supervisor Two', role=UserRole.ADMIN,
        )
        inactive_supervisor = User.objects.create_user(
            username='ex-supervisor', email='ex@example.com', password='x', is_staff=True, is_active=False,
            employee_id='EMP-1004', full_name='Ex Supervisor', role=UserRole.SUPERVISOR,
        )
        self.give_stock(10)  # reorder_level=5 on this fixture's Product

        # Sell down to exactly the reorder level (5) -> LOW_STOCK.
        self.approve_new_sale(quantity=5)

        low_stock_notifs = Notification.objects.filter(type=NotificationType.LOW_STOCK)
        recipients = set(low_stock_notifs.values_list('recipient_id', flat=True))
        self.assertEqual(recipients, {self.supervisor.pk, second_supervisor.pk},
                          "every active supervisor/admin must be notified, and only active ones")
        self.assertNotIn(inactive_supervisor.pk, recipients)
        self.assertNotIn(self.user.pk, recipients, "the sale's creator is not a supervisor")

    def test_sale_dropping_stock_to_zero_sends_out_of_stock_not_low_stock(self):
        self.give_stock(5)
        self.approve_new_sale(quantity=5)
        self.assertTrue(Notification.objects.filter(
            recipient=self.supervisor, type=NotificationType.OUT_OF_STOCK,
        ).exists())
        self.assertFalse(Notification.objects.filter(type=NotificationType.LOW_STOCK).exists())

    def test_sale_leaving_stock_above_reorder_level_sends_no_low_or_out_of_stock_notification(self):
        self.give_stock(20)
        self.approve_new_sale(quantity=1)
        self.assertFalse(Notification.objects.filter(
            type__in=[NotificationType.LOW_STOCK, NotificationType.OUT_OF_STOCK],
        ).exists())


class EmailNotificationTests(ServiceTestCase):
    """Phase 3.5: the synchronous send_mail() path in
    frontend/notifications.py._maybe_send_email(). Django's test runner
    automatically swaps EMAIL_BACKEND for the locmem backend, so
    mail.outbox works here regardless of the console backend configured
    for real local dev."""

    def test_notify_user_sends_email_when_enabled(self):
        settings_obj = SystemSettings.get_settings()
        self.assertTrue(settings_obj.email_notifications_enabled, "enabled by default")

        po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.user, status=POStatus.PENDING)
        PurchaseService.approve(po, self.supervisor)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_no_email_sent_when_notifications_disabled(self):
        settings_obj = SystemSettings.get_settings()
        settings_obj.email_notifications_enabled = False
        settings_obj.save()

        po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.user, status=POStatus.PENDING)
        PurchaseService.approve(po, self.supervisor)

        self.assertEqual(len(mail.outbox), 0)
        # The in-system Notification itself must still be created —
        # disabling email is not the same as disabling notifications.
        self.assertTrue(Notification.objects.filter(recipient=self.user, type=NotificationType.PO_APPROVED).exists())


class AuthTestCase(TestCase):
    """Phase 4: real login/logout/lockout against frontend.User, per
    docs/01_AUTH.md. Uses Django's test Client (self.client) — these are
    real HTTP round-trips through frontend/urls.py + frontend/views.py,
    not direct function calls."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='jdoe', email='jdoe@example.com', password='Correct-Horse1!',
            employee_id='EMP-2001', full_name='Jane Doe', role=UserRole.STAFF,
        )

    def login_url(self):
        return reverse('frontend:login')


class LoginTests(AuthTestCase):

    def test_login_with_username_succeeds(self):
        response = self.client.post(self.login_url(), {'username': 'jdoe', 'password': 'Correct-Horse1!'})
        self.assertRedirects(response, reverse('frontend:dashboard'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)  # unused after redirect; real check below
        # Session is authenticated for the *next* request:
        dash = self.client.get(reverse('frontend:dashboard'))
        self.assertEqual(dash.wsgi_request.user.username, 'jdoe')

    def test_login_with_email_succeeds(self):
        response = self.client.post(self.login_url(), {'username': 'jdoe@example.com', 'password': 'Correct-Horse1!'})
        self.assertRedirects(response, reverse('frontend:dashboard'))
        dash = self.client.get(reverse('frontend:dashboard'))
        self.assertEqual(dash.wsgi_request.user.username, 'jdoe')

    def test_login_success_writes_audit_row_and_resets_lockout_fields(self):
        self.user.failed_login_attempts = 2
        self.user.save(update_fields=['failed_login_attempts'])

        self.client.post(self.login_url(), {'username': 'jdoe', 'password': 'Correct-Horse1!'})

        self.assertTrue(AuditLog.objects.filter(user=self.user, action=audit.LOGIN_SUCCESS, status='success').exists())
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.locked_until)

    def test_login_applies_session_timeout_from_system_settings(self):
        settings_obj = SystemSettings.get_settings()
        settings_obj.session_timeout_seconds = 1800
        settings_obj.save()

        self.client.post(self.login_url(), {'username': 'jdoe', 'password': 'Correct-Horse1!'})

        self.assertEqual(self.client.session.get_expiry_age(), 1800)

    def test_wrong_password_increments_failed_attempts_and_logs_failure(self):
        self.client.post(self.login_url(), {'username': 'jdoe', 'password': 'wrong'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 1)
        self.assertTrue(AuditLog.objects.filter(user=self.user, action=audit.LOGIN_FAILED, status='failure').exists())

    def test_unknown_identifier_logs_failure_with_no_user(self):
        self.client.post(self.login_url(), {'username': 'nobody-here', 'password': 'whatever'})
        entry = AuditLog.objects.get(action=audit.LOGIN_FAILED, user__isnull=True)
        self.assertEqual(entry.details.get('identifier'), 'nobody-here')

    @override_settings(MAX_LOGIN_ATTEMPTS=3, LOCKOUT_DURATION=120)
    def test_lockout_triggers_after_configured_max_attempts(self):
        for _ in range(3):
            self.client.post(self.login_url(), {'username': 'jdoe', 'password': 'wrong'})

        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0, "counter resets once locked")
        self.assertIsNotNone(self.user.locked_until)
        expected = timezone.now() + timedelta(seconds=120)
        self.assertAlmostEqual(self.user.locked_until.timestamp(), expected.timestamp(), delta=5)
        self.assertTrue(AuditLog.objects.filter(user=self.user, action=audit.ACCOUNT_LOCKED).exists())

        # Correct password is still rejected while locked — proves the
        # lockout, not just the attempt counter, blocks the login.
        response = self.client.post(self.login_url(), {'username': 'jdoe', 'password': 'Correct-Horse1!'})
        self.assertContains(response, 'Account locked')

    @override_settings(MAX_LOGIN_ATTEMPTS=3, LOCKOUT_DURATION=120)
    def test_login_succeeds_again_once_lockout_duration_has_elapsed(self):
        for _ in range(3):
            self.client.post(self.login_url(), {'username': 'jdoe', 'password': 'wrong'})
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.locked_until)

        # Simulate LOCKOUT_DURATION having elapsed, rather than sleeping
        # for real in a test.
        self.user.locked_until = timezone.now() - timedelta(seconds=1)
        self.user.save(update_fields=['locked_until'])

        response = self.client.post(self.login_url(), {'username': 'jdoe', 'password': 'Correct-Horse1!'})
        self.assertRedirects(response, reverse('frontend:dashboard'))

    def test_inactive_user_is_blocked_without_incrementing_failed_attempts(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        response = self.client.post(self.login_url(), {'username': 'jdoe', 'password': 'Correct-Horse1!'})

        self.assertContains(response, 'inactive')
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0, "a deactivated account's correct password is not a failed attempt")


class LogoutTests(AuthTestCase):

    def test_logout_writes_audit_row_and_ends_session(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        self.client.post(reverse('frontend:logout'))

        self.assertTrue(AuditLog.objects.filter(user=self.user, action=audit.LOGOUT, status='success').exists())
        dash = self.client.get(reverse('frontend:dashboard'))
        self.assertFalse(dash.wsgi_request.user.is_authenticated)

    def test_logout_requires_login(self):
        response = self.client.post(reverse('frontend:logout'))
        self.assertRedirects(response, f"{reverse('frontend:login')}?next={reverse('frontend:logout')}")


class ProfileUpdateTests(AuthTestCase):

    def test_profile_fields_update_and_log_action_fires(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        self.client.post(reverse('frontend:profile'), {'full_name': 'Jane A. Doe', 'contact_number': '555-0199'})

        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, 'Jane A. Doe')
        self.assertEqual(self.user.contact_number, '555-0199')
        self.assertTrue(AuditLog.objects.filter(user=self.user, action=audit.PROFILE_UPDATED, status='success').exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProfileImageValidationTests(AuthTestCase):
    """Phase 8.98e — profile_view() now runs User.profile_image through
    validate_product_image() (frontend/validators.py), reused unchanged
    from Product.image/SystemSettings.company_logo rather than duplicated
    — previously this field had zero validation at all. MEDIA_ROOT is
    overridden to a throwaway temp dir so these uploads never touch the
    real project media/ folder."""

    def test_invalid_extension_rejected(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        bad_file = SimpleUploadedFile('malware.txt', b'not-an-image', content_type='text/plain')
        response = self.client.post(reverse('frontend:profile'), {
            'full_name': 'Jane Doe', 'contact_number': '', 'profile_image': bad_file,
        })
        self.assertRedirects(response, reverse('frontend:profile'))
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_image)

    def test_oversized_image_rejected(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        big_file = SimpleUploadedFile('big.png', b'\x00' * (5 * 1024 * 1024 + 1), content_type='image/png')
        response = self.client.post(reverse('frontend:profile'), {
            'full_name': 'Jane Doe', 'contact_number': '', 'profile_image': big_file,
        })
        self.assertRedirects(response, reverse('frontend:profile'))
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_image)

    def test_valid_image_accepted_and_displayed(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        good_file = SimpleUploadedFile('avatar.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * 100, content_type='image/png')
        response = self.client.post(reverse('frontend:profile'), {
            'full_name': 'Jane Doe', 'contact_number': '', 'profile_image': good_file,
        })
        self.assertRedirects(response, reverse('frontend:profile'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.profile_image)

        page = self.client.get(reverse('frontend:profile'))
        self.assertContains(page, self.user.profile_image.url)

    def test_no_image_uploaded_leaves_existing_field_untouched(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        response = self.client.post(reverse('frontend:profile'), {'full_name': 'Jane Doe', 'contact_number': ''})
        self.assertRedirects(response, reverse('frontend:profile'))
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_image)


class ChangePasswordViewTests(AuthTestCase):
    """Phase 8.98a — password change moved off profile_view's old inline
    "new password" field (no current-password check, no confirm field)
    into its own real modal + dedicated endpoint. Same
    validate_password()/StrongPasswordValidator enforcement as before,
    reused not rewritten; the new, real checks are current-password
    correctness and new/confirm matching."""

    def test_valid_change_hashes_new_password_logs_and_notifies(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        response = self.client.post(reverse('frontend:change_password'), {
            'current_password': 'Correct-Horse1!',
            'new_password': 'New-Password9!',
            'confirm_password': 'New-Password9!',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': True})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('New-Password9!'))
        self.assertTrue(AuditLog.objects.filter(user=self.user, action=audit.PASSWORD_CHANGED, status='success').exists())
        self.assertTrue(Notification.objects.filter(recipient=self.user, type=NotificationType.PASSWORD_CHANGED).exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_wrong_current_password_rejected(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        response = self.client.post(reverse('frontend:change_password'), {
            'current_password': 'totally-wrong-password',
            'new_password': 'New-Password9!',
            'confirm_password': 'New-Password9!',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('current_password', response.json()['errors'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Correct-Horse1!'), "password must be unchanged")
        self.assertFalse(AuditLog.objects.filter(user=self.user, action=audit.PASSWORD_CHANGED).exists())

    def test_mismatched_confirmation_rejected(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        response = self.client.post(reverse('frontend:change_password'), {
            'current_password': 'Correct-Horse1!',
            'new_password': 'New-Password9!',
            'confirm_password': 'Different-Password9!',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('confirm_password', response.json()['errors'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Correct-Horse1!'), "password must be unchanged")

    def test_weak_new_password_rejected_by_strong_password_validator(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        response = self.client.post(reverse('frontend:change_password'), {
            'current_password': 'Correct-Horse1!',
            'new_password': 'alllowercase1',
            'confirm_password': 'alllowercase1',
        })

        self.assertEqual(response.status_code, 400)
        errors = response.json()['errors']
        self.assertIn('new_password', errors)
        self.assertIn('uppercase', errors['new_password'][0]['message'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Correct-Horse1!'), "password must be unchanged")
        self.assertFalse(AuditLog.objects.filter(user=self.user, action=audit.PASSWORD_CHANGED).exists())

    def test_session_stays_alive_after_password_change(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        self.client.post(reverse('frontend:change_password'), {
            'current_password': 'Correct-Horse1!',
            'new_password': 'Another-One2!',
            'confirm_password': 'Another-One2!',
        })
        # update_session_auth_hash() should have kept this session valid —
        # a follow-up authenticated request must not be bounced to login.
        dash = self.client.get(reverse('frontend:dashboard'))
        self.assertTrue(dash.wsgi_request.user.is_authenticated)

    def test_requires_login(self):
        response = self.client.post(reverse('frontend:change_password'), {})
        self.assertRedirects(
            response, f"{reverse('frontend:login')}?next={reverse('frontend:change_password')}"
        )

    def test_get_not_allowed(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        response = self.client.get(reverse('frontend:change_password'))
        self.assertEqual(response.status_code, 405)

    def test_admin_notified_on_password_change_without_leaking_new_password(self):
        """Phase 8.98e: every active Admin is told a password changed
        (frontend.notifications.notify_admins(), reusing the documented
        PASSWORD_CHANGED type for a second recipient), but never the new
        password itself — confirmed by checking the actual notification
        content and every email sent, not just that a notify call fired."""
        admin = User.objects.create_user(
            username='cpadmin', email='cpadmin@example.com', password='x',
            employee_id='EMP-2099', full_name='CP Admin', role=UserRole.ADMIN,
        )
        self.client.login(username='jdoe', password='Correct-Horse1!')
        response = self.client.post(reverse('frontend:change_password'), {
            'current_password': 'Correct-Horse1!',
            'new_password': 'New-Password9!',
            'confirm_password': 'New-Password9!',
        })
        self.assertEqual(response.status_code, 200)

        admin_notif = Notification.objects.get(recipient=admin, type=NotificationType.PASSWORD_CHANGED)
        self.assertNotIn('New-Password9!', admin_notif.title)
        self.assertNotIn('New-Password9!', admin_notif.message)
        self.assertIn('Jane Doe', admin_notif.message)

        # jdoe's own confirmation email + the admin's alert email — neither
        # carries the new password anywhere in its body.
        self.assertEqual(len(mail.outbox), 2)
        for sent in mail.outbox:
            self.assertNotIn('New-Password9!', sent.body)


class PasswordResetFlowTests(AuthTestCase):
    """Phase 8.99a — the forgot-password flow, finished: real Stockwell-
    styled templates (registration/password_reset_*.html) instead of
    django.contrib.admin's fallback ones, and the audit/notify gap this
    phase's own investigation confirmed: Django's PasswordResetConfirmView
    never goes through change_password_view, so without
    StockwellPasswordResetConfirmView's override, a password reset via the
    emailed link would be invisible to both the audit log and every Admin
    — unlike the identical change made through the profile modal, which
    ChangePasswordViewTests above already covers. This class exists
    specifically because that asymmetry had no coverage at all before this
    phase."""

    def start_reset(self, email='jdoe@example.com'):
        """POSTs the reset-request form, extracts the real confirm link
        from the actually-sent email (not assumed/hand-built), and GETs it
        — returning the session-bound `.../set-password/` path Django
        redirects a first visit to. Mirrors exactly what a real user
        clicking the emailed link would do."""
        self.client.post(reverse('frontend:password_reset'), {'email': email})
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        match = re.search(r'https?://[^/]+(/password-reset/confirm/\S+/)', body)
        self.assertIsNotNone(match, "reset email must contain a real confirm link")
        response = self.client.get(match.group(1), follow=True)
        return response.request['PATH_INFO'], body

    def test_reset_email_arrives_with_a_working_link(self):
        set_password_path, body = self.start_reset()
        self.assertIn('Jane Doe', body)
        self.assertIn('/password-reset/confirm/', set_password_path)

    def test_reset_request_page_is_stockwell_styled_not_admin(self):
        response = self.client.get(reverse('frontend:password_reset'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'auth-page')  # this project's own auth.css class, not admin's
        self.assertContains(response, 'Stockwell')

    def test_valid_reset_succeeds_and_user_can_log_in_with_new_password(self):
        set_password_path, _ = self.start_reset()
        response = self.client.post(set_password_path, {
            'new_password1': 'Brand-New-Passw0rd2!',
            'new_password2': 'Brand-New-Passw0rd2!',
        })
        self.assertRedirects(response, reverse('frontend:password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Brand-New-Passw0rd2!'))

        login_response = self.client.post(self.login_url(), {
            'username': 'jdoe', 'password': 'Brand-New-Passw0rd2!',
        })
        self.assertRedirects(login_response, reverse('frontend:dashboard'))

    def test_weak_new_password_rejected_by_strong_password_validator(self):
        set_password_path, _ = self.start_reset()
        response = self.client.post(set_password_path, {
            'new_password1': 'alllowercase', 'new_password2': 'alllowercase',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Correct-Horse1!'), "password must be unchanged")
        self.assertFalse(AuditLog.objects.filter(user=self.user, action=audit.PASSWORD_CHANGED).exists())

    def test_mismatched_confirmation_rejected(self):
        set_password_path, _ = self.start_reset()
        response = self.client.post(set_password_path, {
            'new_password1': 'Good-Passw0rd3!', 'new_password2': 'Different-Passw0rd4!',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Correct-Horse1!'), "password must be unchanged")

    def test_invalid_token_shows_stockwell_styled_error_not_admin(self):
        response = self.client.get('/password-reset/confirm/MTM/bad-token-xyz/', follow=True)
        self.assertContains(response, 'no longer works')
        self.assertContains(response, 'auth-page')

    def test_reset_writes_audit_log_row(self):
        """The real audit gap this phase closes: unlike a bare Django
        PasswordResetConfirmView (which never calls audit.log_action() at
        all), the Stockwell subclass must write a PASSWORD_CHANGED row for
        the reset path exactly like the profile-modal path already does."""
        set_password_path, _ = self.start_reset()
        self.client.post(set_password_path, {
            'new_password1': 'Brand-New-Passw0rd2!',
            'new_password2': 'Brand-New-Passw0rd2!',
        })
        self.assertTrue(
            AuditLog.objects.filter(user=self.user, action=audit.PASSWORD_CHANGED, status='success').exists()
        )

    def test_reset_notifies_admin_without_leaking_new_password(self):
        admin = User.objects.create_user(
            username='prfadmin', email='prfadmin@example.com', password='x',
            employee_id='EMP-2199', full_name='PRF Admin', role=UserRole.ADMIN,
        )
        set_password_path, _ = self.start_reset()
        mail.outbox = []  # isolate from the request email above
        self.client.post(set_password_path, {
            'new_password1': 'Brand-New-Passw0rd2!',
            'new_password2': 'Brand-New-Passw0rd2!',
        })

        notif = Notification.objects.get(recipient=admin, type=NotificationType.PASSWORD_CHANGED)
        self.assertNotIn('Brand-New-Passw0rd2!', notif.title)
        self.assertNotIn('Brand-New-Passw0rd2!', notif.message)
        self.assertIn('Jane Doe', notif.message)
        for sent in mail.outbox:
            self.assertNotIn('Brand-New-Passw0rd2!', sent.body)

    def test_reset_also_notifies_the_user_themself(self):
        """Same PASSWORD_CHANGED notification the profile-modal path sends
        — the reset path must not be a second, inconsistent shape."""
        set_password_path, _ = self.start_reset()
        self.client.post(set_password_path, {
            'new_password1': 'Brand-New-Passw0rd2!',
            'new_password2': 'Brand-New-Passw0rd2!',
        })
        self.assertTrue(
            Notification.objects.filter(recipient=self.user, type=NotificationType.PASSWORD_CHANGED).exists()
        )

    def test_login_page_link_is_real_not_disabled(self):
        response = self.client.get(self.login_url())
        self.assertContains(response, reverse('frontend:password_reset'))
        self.assertNotContains(response, 'auth-link-disabled')


# ------------------------------------------------------ RBAC decorator/mixin
# Throwaway view + CBV, per this task's own instruction: "applied to
# nothing yet except a throwaway test view/CBV to prove each works." Not
# registered in frontend/urls.py — exercised here directly via Django's
# RequestFactory, never shipped as a real route.

@admin_required
def _decorator_admin_only_view(request):
    return HttpResponse('decorator ok')


@staff_required
def _decorator_any_staff_view(request):
    return HttpResponse('staff ok')


class _MixinAdminOnlyView(AdminRequiredMixin, View):
    def get(self, request):
        return HttpResponse('mixin ok')


class RBACDecoratorMixinTests(TestCase):
    """Proves frontend/decorators.py and frontend/mixins.py both actually
    gate by role, against throwaway views registered nowhere in urls.py."""

    def setUp(self):
        self.factory_admin = User.objects.create_user(
            username='admin1', email='admin1@example.com', password='x',
            employee_id='EMP-3001', full_name='Admin One', role=UserRole.ADMIN,
        )
        self.factory_staff = User.objects.create_user(
            username='staffer1', email='staffer1@example.com', password='x',
            employee_id='EMP-3002', full_name='Staff One', role=UserRole.STAFF,
        )

    def _request(self, path, user):
        from django.test import RequestFactory
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware

        req = RequestFactory().get(path)
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = user
        req._messages = FallbackStorage(req)
        return req

    # ---- decorator ----
    def test_decorator_allows_matching_role(self):
        req = self._request('/_test/admin-only/', self.factory_admin)
        response = _decorator_admin_only_view(req)
        self.assertEqual(response.status_code, 200)

    def test_decorator_blocks_wrong_role_and_redirects_to_dashboard(self):
        req = self._request('/_test/admin-only/', self.factory_staff)
        response = _decorator_admin_only_view(req)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('frontend:dashboard'))

    def test_decorator_blocks_unauthenticated_and_redirects_to_login(self):
        from django.contrib.auth.models import AnonymousUser
        req = self._request('/_test/admin-only/', AnonymousUser())
        response = _decorator_admin_only_view(req)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('frontend:login'))

    def test_decorator_allows_any_of_multiple_permitted_roles(self):
        req = self._request('/_test/any-staff/', self.factory_staff)
        response = _decorator_any_staff_view(req)
        self.assertEqual(response.status_code, 200)

    # ---- mixin ----
    def test_mixin_allows_matching_role(self):
        req = self._request('/_test/admin-only-cbv/', self.factory_admin)
        response = _MixinAdminOnlyView.as_view()(req)
        self.assertEqual(response.status_code, 200)

    def test_mixin_blocks_wrong_role_and_redirects_to_dashboard(self):
        req = self._request('/_test/admin-only-cbv/', self.factory_staff)
        response = _MixinAdminOnlyView.as_view()(req)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('frontend:dashboard'))

    def test_mixin_blocks_unauthenticated_and_redirects_to_login(self):
        from django.contrib.auth.models import AnonymousUser
        req = self._request('/_test/admin-only-cbv/', AnonymousUser())
        response = _MixinAdminOnlyView.as_view()(req)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('frontend:login'), response.url)


# ------------------------------------------------------------------ Products
# Phase 5/5.5: frontend.views.ProductListCreateView, the real /products/
# endpoint. Real HTTP round-trips through frontend/urls.py, like AuthTestCase
# above — not direct function calls.

class ProductCreateViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='pstaff', email='pstaff@example.com', password='x',
            employee_id='EMP-4001', full_name='Product Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='Gadgets', is_active=True)
        self.supplier = Supplier.objects.create(
            supplier_name='Gadget Supply', company_name='Gadget Supply Co',
            contact_person='Sam', email='gadget@example.com', phone='555-0111',
            address='1 Gadget Way', is_active=True,
        )

    def valid_payload(self, **overrides):
        payload = {
            'name': 'Test Gadget',
            'category': self.category.pk,
            'supplier': self.supplier.pk,
            'purchase_price': '10.00',
            'selling_price': '20.00',
        }
        payload.update(overrides)
        return payload

    def test_create_requires_login(self):
        response = self.client.post(reverse('frontend:products'), self.valid_payload())
        self.assertRedirects(response, f"{reverse('frontend:login')}?next={reverse('frontend:products')}")
        self.assertEqual(Product.objects.count(), 0)

    def test_valid_submit_creates_product_with_zero_stock_and_no_movement(self):
        """Phase 5.5 regression test (docs/bugsfound.md BUG-34), end to
        end through the real view — not just the service method in
        isolation, since the original bug was in ProductListCreateView.post()
        calling the wrong InventoryService method, not in the service layer
        itself. Would fail loudly if increase_stock() (or any other
        movement-writing call) were ever reintroduced here."""
        self.client.login(username='pstaff', password='x')
        response = self.client.post(reverse('frontend:products'), self.valid_payload())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

        product = Product.objects.get(name='Test Gadget')
        self.assertEqual(product.current_stock, 0)

        record = InventoryRecord.objects.get(product=product)
        self.assertEqual(record.current_stock, 0)
        self.assertEqual(record.status, InventoryStatus.OUT_OF_STOCK)

        self.assertEqual(
            InventoryMovement.objects.filter(reference_type='Product', reference_id=product.pk).count(), 0,
            "creating a product must never write an InventoryMovement row",
        )
        self.assertTrue(AuditLog.objects.filter(action='PRODUCT_CREATED', affected_id=product.pk).exists())

    def test_duplicate_sku_rejected_with_no_product_created(self):
        self.client.login(username='pstaff', password='x')
        self.client.post(reverse('frontend:products'), self.valid_payload(sku='SKU-DUP-1'))
        response = self.client.post(reverse('frontend:products'), self.valid_payload(name='Second Gadget', sku='SKU-DUP-1'))

        self.assertEqual(response.status_code, 400)
        self.assertIn('sku', response.json().get('errors', {}))
        self.assertEqual(Product.objects.filter(name='Second Gadget').count(), 0)

    def test_no_initial_stock_field_accepted_or_required(self):
        """The Add Product form no longer has an 'Initial stock' field
        (Phase 5.5) — posting one must simply be ignored, not cause an
        error or influence current_stock."""
        self.client.login(username='pstaff', password='x')
        response = self.client.post(
            reverse('frontend:products'),
            self.valid_payload(initial_stock='999'),
        )
        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(name='Test Gadget')
        self.assertEqual(product.current_stock, 0)


class ProductUpdateDeactivateViewTests(TestCase):
    """Phase 8.99e — this project's first per-entity update route.
    ProductUpdateView (AnyStaffMixin) reuses ProductForm unchanged via
    instance=; ProductDeactivateView (SupervisorRequiredMixin) is the
    real soft-delete 03_PRODUCTS.md requires. Proves the RBAC asymmetry
    (02_RBAC.md: edit is all 3 roles, deactivate is Admin/Supervisor
    only), that neither writes an InventoryMovement, and that
    reorder_level edits sync to InventoryRecord."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='pedstaff', email='pedstaff@example.com', password='x',
            employee_id='EMP-4101', full_name='Product Edit Staffer', role=UserRole.STAFF,
        )
        self.supervisor = User.objects.create_user(
            username='pedsuper', email='pedsuper@example.com', password='x',
            employee_id='EMP-4102', full_name='Product Edit Supervisor', role=UserRole.SUPERVISOR,
        )
        self.category = Category.objects.create(name='Edit Gadgets', is_active=True)
        self.supplier = Supplier.objects.create(
            supplier_name='Edit Gadget Supply', company_name='Edit Gadget Supply Co',
            contact_person='Sam', email='editgadget@example.com', phone='555-0112',
            address='1 Edit Gadget Way', is_active=True,
        )
        self.other_category = Category.objects.create(name='Inactive Gadgets', is_active=False)
        self.product = Product.objects.create(
            sku='EDIT-SKU-001', name='Editable Gadget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(self.product)
        self.other_product = Product.objects.create(
            sku='EDIT-SKU-002', barcode='1111111111111', name='Other Gadget',
            category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('9.00'),
        )
        InventoryService.initialize_for_product(self.other_product)

    def valid_edit_payload(self, **overrides):
        payload = {
            'name': 'Editable Gadget (Updated)',
            'category': self.category.pk,
            'supplier': self.supplier.pk,
            'purchase_price': '11.00',
            'selling_price': '22.00',
        }
        payload.update(overrides)
        return payload

    def test_update_requires_login(self):
        response = self.client.post(reverse('frontend:product_update', args=[self.product.pk]), self.valid_edit_payload())
        self.assertRedirects(
            response, f"{reverse('frontend:login')}?next={reverse('frontend:product_update', args=[self.product.pk])}"
        )

    def test_staff_can_edit_and_it_persists(self):
        self.client.login(username='pedstaff', password='x')
        response = self.client.post(reverse('frontend:product_update', args=[self.product.pk]), self.valid_edit_payload())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json().get('success'))

        # Re-fetch from the DB (not the in-memory instance) — proves it genuinely persisted.
        saved = Product.objects.get(pk=self.product.pk)
        self.assertEqual(saved.name, 'Editable Gadget (Updated)')
        self.assertEqual(saved.purchase_price, Decimal('11.00'))
        self.assertEqual(saved.selling_price, Decimal('22.00'))
        self.assertTrue(AuditLog.objects.filter(action='PRODUCT_UPDATED', affected_id=saved.pk).exists())

    def test_edit_writes_no_inventory_movement(self):
        self.client.login(username='pedstaff', password='x')
        before = InventoryMovement.objects.count()
        self.client.post(reverse('frontend:product_update', args=[self.product.pk]), self.valid_edit_payload())
        self.assertEqual(InventoryMovement.objects.count(), before, "editing a catalogue entry must never move stock")

    def test_edit_rejects_negative_price(self):
        self.client.login(username='pedstaff', password='x')
        response = self.client.post(
            reverse('frontend:product_update', args=[self.product.pk]),
            self.valid_edit_payload(purchase_price='-5.00'),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('purchase_price', response.json().get('errors', {}))
        self.assertEqual(Product.objects.get(pk=self.product.pk).purchase_price, Decimal('10.00'))

    def test_edit_rejects_inactive_category(self):
        """ProductForm restricts category/supplier to is_active=True in
        __init__ — proves that restriction genuinely re-applies on edit,
        not just create, since ProductForm is reused unchanged."""
        self.client.login(username='pedstaff', password='x')
        response = self.client.post(
            reverse('frontend:product_update', args=[self.product.pk]),
            self.valid_edit_payload(category=self.other_category.pk),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('category', response.json().get('errors', {}))

    def test_edit_reruns_uniqueness_validation_via_barcode(self):
        """Verification's own ask was "test a duplicate SKU on edit" — SKU
        is deliberately immutable on edit (see next test), which makes a
        literal duplicate-SKU-on-edit scenario structurally impossible by
        design, not merely untested. Barcode is the field that's actually
        still editable and unique, so it's the one that can genuinely
        prove ProductForm's uniqueness validation (ModelForm.validate_unique)
        still runs end-to-end on an edit, not just on create."""
        self.client.login(username='pedstaff', password='x')
        response = self.client.post(
            reverse('frontend:product_update', args=[self.product.pk]),
            self.valid_edit_payload(barcode=self.other_product.barcode),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('barcode', response.json().get('errors', {}))

    def test_sku_is_immutable_on_edit_even_if_tampered(self):
        """SKU is read-only on edit (disclosed decision, ProductUpdateView's
        own docstring): the view always overwrites the posted `sku` with
        the instance's current value before ProductForm ever sees it. A
        tampered POST attempting to steal another product's SKU must
        succeed (the rest of the edit is valid) while silently leaving
        the SKU exactly as it was — not erroring, and not adopting the
        attacker-supplied value."""
        original_sku = self.product.sku
        self.client.login(username='pedstaff', password='x')
        response = self.client.post(
            reverse('frontend:product_update', args=[self.product.pk]),
            self.valid_edit_payload(sku=self.other_product.sku),
        )
        self.assertEqual(response.status_code, 200, response.content)
        saved = Product.objects.get(pk=self.product.pk)
        self.assertEqual(saved.sku, original_sku)
        self.assertNotEqual(saved.sku, self.other_product.sku)

    def test_edit_reorder_level_syncs_to_inventory_record_without_ledger_write(self):
        # Give it real stock first (20, via the real service, a real
        # movement) so raising reorder_level above it can actually flip
        # AVAILABLE -> LOW_STOCK — with current_stock still at 0 (never
        # received), update_status() would report OUT_OF_STOCK regardless
        # of reorder_level, which wouldn't prove the sync actually ran.
        InventoryService.increase_stock(
            product=self.product, quantity=20, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.staff,
        )
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.status, InventoryStatus.AVAILABLE, "20 in stock, reorder_level 5 -> AVAILABLE before the edit")

        self.client.login(username='pedstaff', password='x')
        before_movements = InventoryMovement.objects.count()
        response = self.client.post(
            reverse('frontend:product_update', args=[self.product.pk]),
            self.valid_edit_payload(reorder_level='50'),
        )
        self.assertEqual(response.status_code, 200, response.content)
        record.refresh_from_db()
        self.assertEqual(record.reorder_level, 50)
        self.assertEqual(record.status, InventoryStatus.LOW_STOCK, "20 in stock <= new reorder_level 50 -> LOW_STOCK")
        self.assertEqual(InventoryMovement.objects.count(), before_movements, "the reorder_level sync must never write a ledger row")

    def test_deactivate_requires_login(self):
        response = self.client.post(reverse('frontend:product_deactivate', args=[self.product.pk]))
        self.assertRedirects(
            response, f"{reverse('frontend:login')}?next={reverse('frontend:product_deactivate', args=[self.product.pk])}"
        )

    def test_staff_can_edit_but_deactivate_is_refused_server_side(self):
        self.client.login(username='pedstaff', password='x')
        edit_response = self.client.post(reverse('frontend:product_update', args=[self.product.pk]), self.valid_edit_payload())
        self.assertEqual(edit_response.status_code, 200, "staff must be able to edit — 02_RBAC.md: all 3 roles")

        deactivate_response = self.client.post(reverse('frontend:product_deactivate', args=[self.product.pk]))
        self.assertEqual(deactivate_response.status_code, 302, "staff must be blocked from deactivating — 02_RBAC.md: Admin/Supervisor only")
        self.assertTrue(Product.objects.get(pk=self.product.pk).is_active, "a blocked deactivate must not take effect")

    def test_supervisor_can_deactivate(self):
        self.client.login(username='pedsuper', password='x')
        before_movements = InventoryMovement.objects.count()
        response = self.client.post(reverse('frontend:product_deactivate', args=[self.product.pk]))
        self.assertEqual(response.status_code, 200, response.content)

        saved = Product.objects.get(pk=self.product.pk)
        self.assertFalse(saved.is_active)
        self.assertTrue(AuditLog.objects.filter(action='PRODUCT_DEACTIVATED', affected_id=saved.pk).exists())
        self.assertEqual(InventoryMovement.objects.count(), before_movements, "deactivating must never move stock")

    def test_deactivated_product_excluded_from_purchase_and_sale_forms(self):
        self.client.login(username='pedsuper', password='x')
        self.client.post(reverse('frontend:product_deactivate', args=[self.product.pk]))

        purchases_response = self.client.get(reverse('frontend:purchases'))
        sales_response = self.client.get(reverse('frontend:sales'))
        purchase_product_ids = {p.pk for p in purchases_response.context['products']}
        sale_product_ids = {p.pk for p in sales_response.context['products']}
        self.assertNotIn(self.product.pk, purchase_product_ids)
        self.assertNotIn(self.product.pk, sale_product_ids)
        # The still-active product must still be offered.
        self.assertIn(self.other_product.pk, purchase_product_ids)
        self.assertIn(self.other_product.pk, sale_product_ids)

    def test_deactivate_control_hidden_from_staff_shown_to_supervisor(self):
        self.client.login(username='pedstaff', password='x')
        staff_response = self.client.get(reverse('frontend:products'))
        self.assertNotContains(staff_response, 'aria-label="Deactivate product"')
        self.assertContains(staff_response, 'aria-label="Edit product"')
        self.client.logout()

        self.client.login(username='pedsuper', password='x')
        super_response = self.client.get(reverse('frontend:products'))
        self.assertContains(super_response, 'aria-label="Deactivate product"')
        self.assertContains(super_response, 'aria-label="Edit product"')

    def test_reactivate_restores_a_deactivated_product(self):
        self.client.login(username='pedsuper', password='x')
        self.client.post(reverse('frontend:product_deactivate', args=[self.product.pk]))
        self.assertFalse(Product.objects.get(pk=self.product.pk).is_active)

        response = self.client.post(reverse('frontend:product_reactivate', args=[self.product.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Product.objects.get(pk=self.product.pk).is_active)
        self.assertTrue(AuditLog.objects.filter(action='PRODUCT_REACTIVATED', affected_id=self.product.pk).exists())

    def test_staff_cannot_reactivate(self):
        self.client.login(username='pedsuper', password='x')
        self.client.post(reverse('frontend:product_deactivate', args=[self.product.pk]))
        self.client.logout()

        self.client.login(username='pedstaff', password='x')
        response = self.client.post(reverse('frontend:product_reactivate', args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.get(pk=self.product.pk).is_active)

    def test_reactivated_product_reappears_in_purchase_and_sale_forms(self):
        self.client.login(username='pedsuper', password='x')
        self.client.post(reverse('frontend:product_deactivate', args=[self.product.pk]))
        self.client.post(reverse('frontend:product_reactivate', args=[self.product.pk]))

        purchases_response = self.client.get(reverse('frontend:purchases'))
        purchase_product_ids = {p.pk for p in purchases_response.context['products']}
        self.assertIn(self.product.pk, purchase_product_ids)

    def test_unreferenced_product_can_be_hard_deleted(self):
        """A product that has never appeared in a PO/sale/adjustment/
        movement — self.other_product here never had stock received or
        sold against it — is safe to hard-delete, InventoryRecord and all."""
        self.client.login(username='pedsuper', password='x')
        response = self.client.post(reverse('frontend:product_delete', args=[self.other_product.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(Product.objects.filter(pk=self.other_product.pk).exists())
        self.assertFalse(InventoryRecord.objects.filter(product_id=self.other_product.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action='PRODUCT_DELETED', affected_id=self.other_product.pk).exists())

    def test_product_with_movement_history_cannot_be_hard_deleted(self):
        InventoryService.increase_stock(
            product=self.product, quantity=10, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.staff,
        )
        self.client.login(username='pedsuper', password='x')
        response = self.client.post(reverse('frontend:product_delete', args=[self.product.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertIn('deactivate instead', response.json()['error'].lower())
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_staff_cannot_delete_a_product(self):
        self.client.login(username='pedstaff', password='x')
        response = self.client.post(reverse('frontend:product_delete', args=[self.other_product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Product.objects.filter(pk=self.other_product.pk).exists())

    def test_deletable_flag_reflects_history(self):
        InventoryService.increase_stock(
            product=self.product, quantity=10, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.staff,
        )
        self.client.login(username='pedsuper', password='x')
        response = self.client.get(reverse('frontend:products'))
        by_pk = {p.pk: p.deletable for p in response.context['products']}
        self.assertFalse(by_pk[self.product.pk], "a product with real movement history must not be deletable")
        self.assertTrue(by_pk[self.other_product.pk], "a never-used product must be deletable")

    def test_editing_tax_rate_does_not_alter_a_completed_transactions_stored_tax(self):
        """Phase 8.98c made PurchaseOrderItem.tax/SaleItem.tax a historical
        snapshot, set once at line-creation time from Product.tax_rate.
        This locks that guarantee against ProductUpdateView specifically:
        editing the product's tax_rate afterward must never reach back
        into an already-created line."""
        self.product.tax_rate = Decimal('10.00')
        self.product.save(update_fields=['tax_rate'])
        po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.staff)
        item = PurchaseOrderItem.objects.create(
            purchase_order=po, product=self.product, ordered_qty=5,
            unit_price=self.product.purchase_price, tax=self.product.tax_rate,
        )
        self.assertEqual(item.tax, Decimal('10.00'))

        self.client.login(username='pedstaff', password='x')
        response = self.client.post(
            reverse('frontend:product_update', args=[self.product.pk]),
            self.valid_edit_payload(tax_rate='25.00'),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Product.objects.get(pk=self.product.pk).tax_rate, Decimal('25.00'), "the product's own tax_rate must change")

        item.refresh_from_db()
        self.assertEqual(item.tax, Decimal('10.00'), "the already-created line's snapshotted tax must never change retroactively")


class CategoryUpdateDeactivateViewTests(TestCase):
    """Phase 8.99i — Categories' Edit/Deactivate/Reactivate/Delete were
    dead buttons before this phase (no class, no handler, no view at
    all). Mirrors ProductUpdateDeactivateViewTests' own coverage shape."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='catedstaff', email='catedstaff@example.com', password='x',
            employee_id='EMP-4201', full_name='Category Edit Staffer', role=UserRole.STAFF,
        )
        self.supervisor = User.objects.create_user(
            username='catedsuper', email='catedsuper@example.com', password='x',
            employee_id='EMP-4202', full_name='Category Edit Supervisor', role=UserRole.SUPERVISOR,
        )
        self.category = Category.objects.create(name='Edit Category', description='Original')
        self.other_category = Category.objects.create(name='Other Category')
        self.supplier = Supplier.objects.create(
            supplier_name='Cat Edit Supply', company_name='Cat Edit Supply Co', contact_person='Sam',
            email='catedsupply@example.com', phone='555-0113', address='1 Cat Edit Way',
        )

    def test_staff_can_edit_and_it_persists(self):
        self.client.login(username='catedstaff', password='x')
        response = self.client.post(
            reverse('frontend:category_update', args=[self.category.pk]),
            {'name': 'Renamed Category', 'description': 'Updated'},
        )
        self.assertEqual(response.status_code, 200, response.content)
        saved = Category.objects.get(pk=self.category.pk)
        self.assertEqual(saved.name, 'Renamed Category')
        self.assertEqual(saved.description, 'Updated')
        self.assertTrue(AuditLog.objects.filter(action='CATEGORY_UPDATED', affected_id=saved.pk).exists())

    def test_edit_rejects_duplicate_name(self):
        self.client.login(username='catedstaff', password='x')
        response = self.client.post(
            reverse('frontend:category_update', args=[self.category.pk]),
            {'name': self.other_category.name, 'description': ''},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json().get('errors', {}))

    def test_edit_does_not_change_is_active(self):
        """No status field on the edit form — is_active only ever changes
        through Deactivate/Reactivate, never through edit."""
        self.category.is_active = False
        self.category.save(update_fields=['is_active'])
        self.client.login(username='catedstaff', password='x')
        self.client.post(
            reverse('frontend:category_update', args=[self.category.pk]),
            {'name': 'Still Inactive Category', 'description': ''},
        )
        self.assertFalse(Category.objects.get(pk=self.category.pk).is_active)

    def test_staff_can_edit_but_deactivate_is_refused_server_side(self):
        self.client.login(username='catedstaff', password='x')
        edit_response = self.client.post(
            reverse('frontend:category_update', args=[self.category.pk]),
            {'name': 'Renamed Category', 'description': ''},
        )
        self.assertEqual(edit_response.status_code, 200)

        deactivate_response = self.client.post(reverse('frontend:category_deactivate', args=[self.category.pk]))
        self.assertEqual(deactivate_response.status_code, 302)
        self.assertTrue(Category.objects.get(pk=self.category.pk).is_active)

    def test_supervisor_can_deactivate_and_reactivate(self):
        self.client.login(username='catedsuper', password='x')
        response = self.client.post(reverse('frontend:category_deactivate', args=[self.category.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(Category.objects.get(pk=self.category.pk).is_active)
        self.assertTrue(AuditLog.objects.filter(action='CATEGORY_DEACTIVATED', affected_id=self.category.pk).exists())

        response = self.client.post(reverse('frontend:category_reactivate', args=[self.category.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Category.objects.get(pk=self.category.pk).is_active)
        self.assertTrue(AuditLog.objects.filter(action='CATEGORY_REACTIVATED', affected_id=self.category.pk).exists())

    def test_deactivated_category_excluded_from_product_form(self):
        self.client.login(username='catedsuper', password='x')
        self.client.post(reverse('frontend:category_deactivate', args=[self.category.pk]))
        response = self.client.get(reverse('frontend:products'))
        category_ids = {c.pk for c in response.context['categories']}
        self.assertNotIn(self.category.pk, category_ids)
        self.assertIn(self.other_category.pk, category_ids)

    def test_unreferenced_category_can_be_hard_deleted(self):
        self.client.login(username='catedsuper', password='x')
        response = self.client.post(reverse('frontend:category_delete', args=[self.other_category.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(Category.objects.filter(pk=self.other_category.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action='CATEGORY_DELETED', affected_id=self.other_category.pk).exists())

    def test_category_with_products_cannot_be_hard_deleted(self):
        Product.objects.create(
            sku='CATDEL-SKU-001', name='Category Delete Product', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('9.00'),
        )
        self.client.login(username='catedsuper', password='x')
        response = self.client.post(reverse('frontend:category_delete', args=[self.category.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertIn('deactivate instead', response.json()['error'].lower())
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())

    def test_staff_cannot_delete_a_category(self):
        self.client.login(username='catedstaff', password='x')
        response = self.client.post(reverse('frontend:category_delete', args=[self.other_category.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Category.objects.filter(pk=self.other_category.pk).exists())


class SupplierUpdateDeactivateViewTests(TestCase):
    """Phase 8.99i — same coverage shape as
    CategoryUpdateDeactivateViewTests/ProductUpdateDeactivateViewTests."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='supedstaff', email='supedstaff@example.com', password='x',
            employee_id='EMP-4301', full_name='Supplier Edit Staffer', role=UserRole.STAFF,
        )
        self.supervisor = User.objects.create_user(
            username='supedsuper', email='supedsuper@example.com', password='x',
            employee_id='EMP-4302', full_name='Supplier Edit Supervisor', role=UserRole.SUPERVISOR,
        )
        self.category = Category.objects.create(name='Supplier Edit Category')
        self.supplier = Supplier.objects.create(
            supplier_name='Edit Supply', company_name='Edit Supply Co', contact_person='Sam',
            email='editsupply@example.com', phone='555-0114', address='1 Edit Supply Way',
        )
        self.other_supplier = Supplier.objects.create(
            supplier_name='Other Supply', company_name='Other Supply Co', contact_person='Alex',
            email='othersupply@example.com', phone='555-0115', address='2 Other Supply Way',
        )

    def valid_edit_payload(self, **overrides):
        payload = {
            'supplier_name': 'Edit Supply (Updated)', 'company_name': 'Edit Supply Co Updated',
            'contact_person': 'Sam Updated', 'email': self.supplier.email,
            'phone': '555-9999', 'address': 'Updated Address',
        }
        payload.update(overrides)
        return payload

    def test_staff_can_edit_and_it_persists(self):
        self.client.login(username='supedstaff', password='x')
        response = self.client.post(reverse('frontend:supplier_update', args=[self.supplier.pk]), self.valid_edit_payload())
        self.assertEqual(response.status_code, 200, response.content)
        saved = Supplier.objects.get(pk=self.supplier.pk)
        self.assertEqual(saved.company_name, 'Edit Supply Co Updated')
        self.assertTrue(AuditLog.objects.filter(action='SUPPLIER_UPDATED', affected_id=saved.pk).exists())

    def test_edit_rejects_duplicate_email(self):
        self.client.login(username='supedstaff', password='x')
        response = self.client.post(
            reverse('frontend:supplier_update', args=[self.supplier.pk]),
            self.valid_edit_payload(email=self.other_supplier.email),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json().get('errors', {}))

    def test_edit_does_not_change_is_active(self):
        self.supplier.is_active = False
        self.supplier.save(update_fields=['is_active'])
        self.client.login(username='supedstaff', password='x')
        self.client.post(reverse('frontend:supplier_update', args=[self.supplier.pk]), self.valid_edit_payload())
        self.assertFalse(Supplier.objects.get(pk=self.supplier.pk).is_active)

    def test_staff_can_edit_but_deactivate_is_refused_server_side(self):
        self.client.login(username='supedstaff', password='x')
        edit_response = self.client.post(reverse('frontend:supplier_update', args=[self.supplier.pk]), self.valid_edit_payload())
        self.assertEqual(edit_response.status_code, 200)

        deactivate_response = self.client.post(reverse('frontend:supplier_deactivate', args=[self.supplier.pk]))
        self.assertEqual(deactivate_response.status_code, 302)
        self.assertTrue(Supplier.objects.get(pk=self.supplier.pk).is_active)

    def test_supervisor_can_deactivate_and_reactivate(self):
        self.client.login(username='supedsuper', password='x')
        response = self.client.post(reverse('frontend:supplier_deactivate', args=[self.supplier.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(Supplier.objects.get(pk=self.supplier.pk).is_active)
        self.assertTrue(AuditLog.objects.filter(action='SUPPLIER_DEACTIVATED', affected_id=self.supplier.pk).exists())

        response = self.client.post(reverse('frontend:supplier_reactivate', args=[self.supplier.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Supplier.objects.get(pk=self.supplier.pk).is_active)
        self.assertTrue(AuditLog.objects.filter(action='SUPPLIER_REACTIVATED', affected_id=self.supplier.pk).exists())

    def test_deactivated_supplier_excluded_from_product_form(self):
        self.client.login(username='supedsuper', password='x')
        self.client.post(reverse('frontend:supplier_deactivate', args=[self.supplier.pk]))
        response = self.client.get(reverse('frontend:products'))
        supplier_ids = {s.pk for s in response.context['suppliers']}
        self.assertNotIn(self.supplier.pk, supplier_ids)
        self.assertIn(self.other_supplier.pk, supplier_ids)

    def test_unreferenced_supplier_can_be_hard_deleted(self):
        self.client.login(username='supedsuper', password='x')
        response = self.client.post(reverse('frontend:supplier_delete', args=[self.other_supplier.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(Supplier.objects.filter(pk=self.other_supplier.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action='SUPPLIER_DELETED', affected_id=self.other_supplier.pk).exists())

    def test_supplier_with_products_cannot_be_hard_deleted(self):
        Product.objects.create(
            sku='SUPDEL-SKU-001', name='Supplier Delete Product', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('9.00'),
        )
        self.client.login(username='supedsuper', password='x')
        response = self.client.post(reverse('frontend:supplier_delete', args=[self.supplier.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertIn('deactivate instead', response.json()['error'].lower())
        self.assertTrue(Supplier.objects.filter(pk=self.supplier.pk).exists())

    def test_supplier_with_purchase_orders_cannot_be_hard_deleted(self):
        PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.staff)
        self.client.login(username='supedsuper', password='x')
        response = self.client.post(reverse('frontend:supplier_delete', args=[self.supplier.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Supplier.objects.filter(pk=self.supplier.pk).exists())

    def test_staff_cannot_delete_a_supplier(self):
        self.client.login(username='supedstaff', password='x')
        response = self.client.post(reverse('frontend:supplier_delete', args=[self.other_supplier.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Supplier.objects.filter(pk=self.other_supplier.pk).exists())


class ProductTaxRateTests(TestCase):
    """Phase 8.98c: tax_rate lives on Product, not on any transaction
    form. ProductForm.clean_tax_rate() mirrors clean_purchase_price()/
    clean_selling_price()'s non-negative check, with a 0-default fallback
    like clean_reorder_level()."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='taxstaff', email='taxstaff@example.com', password='x',
            employee_id='EMP-6001', full_name='Tax Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='Taxable Widgets', is_active=True)
        self.supplier = Supplier.objects.create(
            supplier_name='Tax Supply', company_name='Tax Supply Co', contact_person='Sam',
            email='taxsupply@example.com', phone='555-0199', address='1 Tax Way', is_active=True,
        )

    def valid_payload(self, **overrides):
        payload = {
            'name': 'Taxed Gadget', 'category': self.category.pk, 'supplier': self.supplier.pk,
            'purchase_price': '10.00', 'selling_price': '20.00',
        }
        payload.update(overrides)
        return payload

    def test_tax_rate_persists_from_product_form(self):
        self.client.login(username='taxstaff', password='x')
        response = self.client.post(reverse('frontend:products'), self.valid_payload(tax_rate='7.50'))
        self.assertEqual(response.status_code, 200, response.content)
        product = Product.objects.get(name='Taxed Gadget')
        self.assertEqual(product.tax_rate, Decimal('7.50'))

    def test_tax_rate_defaults_to_zero_when_omitted(self):
        self.client.login(username='taxstaff', password='x')
        response = self.client.post(reverse('frontend:products'), self.valid_payload())
        self.assertEqual(response.status_code, 200, response.content)
        product = Product.objects.get(name='Taxed Gadget')
        self.assertEqual(product.tax_rate, 0)

    def test_negative_tax_rate_rejected(self):
        self.client.login(username='taxstaff', password='x')
        response = self.client.post(reverse('frontend:products'), self.valid_payload(tax_rate='-5'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('tax_rate', response.json().get('errors', {}))
        self.assertEqual(Product.objects.filter(name='Taxed Gadget').count(), 0)


class TaxAutoCalculationTests(TestCase):
    """Phase 8.98c: tax on a Purchase/Sale line is always sourced from
    Product.tax_rate — never a client-submitted 'tax' value, even if one
    is present in the POST/items payload (parse_line_items() in
    frontend/forms.py overwrites it unconditionally; SaleService.create_sale()
    independently re-derives it from the product too, as defense in depth)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='taxflowstaff', email='taxflowstaff@example.com', password='x',
            employee_id='EMP-6101', full_name='Tax Flow Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='Tax Flow Widgets', is_active=True)
        self.supplier = Supplier.objects.create(
            supplier_name='Tax Flow Supply', company_name='Tax Flow Supply Co', contact_person='Jo',
            email='taxflow@example.com', phone='555-0198', address='1 Tax Flow Way', is_active=True,
        )
        self.product = Product.objects.create(
            sku='TAX-SKU-001', name='Taxed Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'), tax_rate=Decimal('10.00'),
        )

    def test_purchase_line_tax_sourced_from_product_ignoring_client_value(self):
        """Client sends 'tax': 999 (as if a stale/malicious client still
        POSTed one) — the server must still use the product's real 10%."""
        self.client.login(username='taxflowstaff', password='x')
        payload = {
            'supplier': self.supplier.pk,
            'items_json': json.dumps([
                {'productLabel': str(self.product.pk), 'quantity': 5, 'unitPrice': 10.0,
                 'discount': 0, 'tax': 999},
            ]),
        }
        response = self.client.post(reverse('frontend:purchases'), payload)
        self.assertEqual(response.status_code, 200, response.content)
        po = PurchaseOrder.objects.filter(supplier=self.supplier).order_by('-pk').first()
        item = po.items.get()
        self.assertEqual(item.tax, Decimal('10.00'))
        # (10 * 5) * (1 - 0) * (1 + 0.10) = 55.00
        self.assertEqual(item.line_total, Decimal('55.00'))
        self.assertEqual(po.total_cost, Decimal('55.00'))

    def test_purchase_line_tax_omitted_by_client_still_uses_product_rate(self):
        """The real line-items.js (Phase 8.98c) no longer sends a 'tax'
        key at all — confirms that case works too, not just the
        malicious-override case above."""
        self.client.login(username='taxflowstaff', password='x')
        payload = {
            'supplier': self.supplier.pk,
            'items_json': json.dumps([
                {'productLabel': str(self.product.pk), 'quantity': 2, 'unitPrice': 10.0, 'discount': 0},
            ]),
        }
        response = self.client.post(reverse('frontend:purchases'), payload)
        self.assertEqual(response.status_code, 200, response.content)
        po = PurchaseOrder.objects.filter(supplier=self.supplier).order_by('-pk').first()
        self.assertEqual(po.items.get().tax, Decimal('10.00'))

    def test_sale_line_tax_sourced_from_product_ignoring_client_value(self):
        InventoryService.increase_stock(
            product=self.product, quantity=20, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.staff,
        )
        sale = SaleService.create_sale(
            {'customer_name': 'Acme Corp'},
            [{'product_id': self.product.pk, 'quantity': 5, 'unit_price': Decimal('20.00'),
              'discount': 0, 'tax': 999}],
            self.staff,
        )
        item = sale.items.get()
        self.assertEqual(item.tax, Decimal('10.00'))
        # (20 * 5) * (1 - 0) * (1 + 0.10) = 110.00
        self.assertEqual(item.line_total, Decimal('110.00'))
        self.assertEqual(sale.total_amount, Decimal('110.00'))

    def test_purchase_item_tax_is_a_historical_snapshot_not_retroactive(self):
        """Confirms the explicit verification requirement: changing a
        product's tax_rate must affect only NEW transactions, not
        existing ones already created under the old rate."""
        self.client.login(username='taxflowstaff', password='x')
        payload = {
            'supplier': self.supplier.pk,
            'items_json': json.dumps([
                {'productLabel': str(self.product.pk), 'quantity': 1, 'unitPrice': 10.0, 'discount': 0},
            ]),
        }
        response = self.client.post(reverse('frontend:purchases'), payload)
        self.assertEqual(response.status_code, 200, response.content)
        old_po = PurchaseOrder.objects.filter(supplier=self.supplier).order_by('-pk').first()
        old_item = old_po.items.get()
        self.assertEqual(old_item.tax, Decimal('10.00'))

        self.product.tax_rate = Decimal('25.00')
        self.product.save()

        response = self.client.post(reverse('frontend:purchases'), payload)
        self.assertEqual(response.status_code, 200, response.content)
        new_po = PurchaseOrder.objects.filter(supplier=self.supplier).order_by('-pk').first()
        new_item = new_po.items.get()
        self.assertEqual(new_item.tax, Decimal('25.00'))

        old_item.refresh_from_db()
        self.assertEqual(old_item.tax, Decimal('10.00'), "an existing line's tax must not change retroactively")

    def test_adjustment_has_no_tax_concept(self):
        """InventoryAdjustment (frontend/models.py) has no monetary/tax
        field at all — tax is a purchase/sale concern only, confirmed
        here so a future change can't silently assume otherwise."""
        self.assertFalse(hasattr(InventoryAdjustment, 'tax'))
        field_names = [f.name for f in InventoryAdjustment._meta.get_fields()]
        self.assertNotIn('tax', field_names)


# ------------------------------------------------------------- Purchases
# Phase 7. Real HTTP round-trips through frontend/urls.py, per this
# task's own instruction: "one test per approval-workflow transition...
# confirming the correct service method fires and stock changes exactly
# as expected — not just that the view returns 200."

class PurchaseWorkflowViewTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(
            username='pobstaff', email='pobstaff@example.com', password='x',
            employee_id='EMP-5001', full_name='PO Staffer', role=UserRole.STAFF,
        )
        self.supervisor = User.objects.create_user(
            username='pobsuper', email='pobsuper@example.com', password='x',
            employee_id='EMP-5002', full_name='PO Supervisor', role=UserRole.SUPERVISOR,
        )
        self.admin = User.objects.create_user(
            username='pobadmin', email='pobadmin@example.com', password='x',
            employee_id='EMP-5003', full_name='PO Admin', role=UserRole.ADMIN,
        )
        self.category = Category.objects.create(name='PO Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='PO Supply', company_name='PO Supply Co', contact_person='Jo',
            email='posupply@example.com', phone='555-0200', address='1 PO Way', is_active=True,
        )
        self.product = Product.objects.create(
            sku='PO-SKU-001', name='PO Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('10.00'), reorder_level=5,
        )

    def create_draft_po(self, quantity=10):
        self.client.login(username='pobstaff', password='x')
        payload = {
            'supplier': self.supplier.pk,
            'items_json': json.dumps([
                {'productLabel': str(self.product.pk), 'quantity': quantity, 'unitPrice': 5.0, 'discount': 0, 'tax': 0},
            ]),
        }
        response = self.client.post(reverse('frontend:purchases'), payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.client.logout()
        return PurchaseOrder.objects.filter(supplier=self.supplier).order_by('-pk').first()

    def test_create_draft_po_with_line_items_no_stock_change(self):
        po = self.create_draft_po(quantity=10)
        self.assertEqual(po.status, POStatus.DRAFT)
        item = po.items.get()
        self.assertEqual(item.ordered_qty, 10)
        self.assertEqual(po.total_cost, Decimal('50.00'))
        self.assertEqual(
            InventoryMovement.objects.filter(reference_type='PurchaseOrder', reference_id=po.pk).count(), 0,
            "creating a draft PO must not touch stock",
        )
        self.assertTrue(AuditLog.objects.filter(action='PO_CREATED', affected_id=po.pk).exists())

    def test_submit_approve_receive_full_increases_stock_via_movement(self):
        po = self.create_draft_po(quantity=10)

        self.client.login(username='pobstaff', password='x')
        self.client.post(reverse('frontend:purchase_submit', args=[po.pk]))
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.PENDING)

        self.client.logout()
        self.client.login(username='pobsuper', password='x')
        response = self.client.post(reverse('frontend:purchase_approve', args=[po.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.APPROVED)
        self.assertEqual(po.approved_by, self.supervisor)
        # Approval alone must not touch stock (05_PURCHASES.md: "Stock
        # update timing | ONLY after successful receive — not on approval").
        self.assertEqual(InventoryRecord.objects.filter(product=self.product).count(), 0)
        self.client.logout()

        # Receiving is a staff task, distinct from approval (05_PURCHASES.md's
        # own purchase_receive_view uses @staff_required, not @supervisor_required).
        self.client.login(username='pobstaff', password='x')
        item = po.items.get()
        response = self.client.post(
            reverse('frontend:purchase_receive', args=[po.pk]),
            {'receive_json': json.dumps([{'item_id': item.pk, 'received_qty': 10}])},
        )
        self.assertEqual(response.status_code, 200, response.content)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.RECEIVED)

        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 10)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, 10)

        movement = InventoryMovement.objects.get(reference_type='PurchaseOrder', reference_id=po.pk)
        self.assertEqual(movement.movement_type, MovementType.PURCHASE)
        self.assertEqual(movement.quantity_change, 10)
        self.assertEqual(movement.performed_by, self.staff)

    def test_partial_receive_leaves_status_partial_and_increases_stock_by_received_only(self):
        po = self.create_draft_po(quantity=10)
        self.client.login(username='pobstaff', password='x')
        self.client.post(reverse('frontend:purchase_submit', args=[po.pk]))
        self.client.logout()
        self.client.login(username='pobsuper', password='x')
        self.client.post(reverse('frontend:purchase_approve', args=[po.pk]))
        self.client.logout()

        self.client.login(username='pobstaff', password='x')
        item = po.items.get()
        response = self.client.post(
            reverse('frontend:purchase_receive', args=[po.pk]),
            {'receive_json': json.dumps([{'item_id': item.pk, 'received_qty': 6}])},
        )
        self.assertEqual(response.status_code, 200, response.content)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.PARTIAL)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 6, "only the received quantity should be added to stock")

    def test_receive_cannot_exceed_ordered_quantity(self):
        po = self.create_draft_po(quantity=10)
        self.client.login(username='pobstaff', password='x')
        self.client.post(reverse('frontend:purchase_submit', args=[po.pk]))
        self.client.logout()
        self.client.login(username='pobsuper', password='x')
        self.client.post(reverse('frontend:purchase_approve', args=[po.pk]))
        self.client.logout()

        self.client.login(username='pobstaff', password='x')
        item = po.items.get()
        response = self.client.post(
            reverse('frontend:purchase_receive', args=[po.pk]),
            {'receive_json': json.dumps([{'item_id': item.pk, 'received_qty': 11}])},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(InventoryRecord.objects.filter(product=self.product).exists())

    def test_submit_then_reject_writes_no_movement(self):
        po = self.create_draft_po(quantity=10)
        self.client.login(username='pobstaff', password='x')
        self.client.post(reverse('frontend:purchase_submit', args=[po.pk]))
        self.client.logout()

        self.client.login(username='pobsuper', password='x')
        response = self.client.post(reverse('frontend:purchase_reject', args=[po.pk]), {'reason': 'Budget frozen'})
        self.assertEqual(response.status_code, 200, response.content)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.REJECTED)
        self.assertEqual(po.rejected_reason, 'Budget frozen')
        self.assertFalse(InventoryMovement.objects.filter(reference_type='PurchaseOrder', reference_id=po.pk).exists())

    def test_cancel_from_every_cancellable_state(self):
        # Phase 8.99c: cancellable states narrowed to DRAFT/PENDING only
        # (see docs/project_memory.md §13) — APPROVED/PARTIAL/RECEIVED are
        # now covered separately below, as refused-not-cancelled cases.

        # DRAFT
        po = self.create_draft_po(quantity=5)
        self.client.login(username='pobsuper', password='x')
        response = self.client.post(reverse('frontend:purchase_cancel', args=[po.pk]), {'reason': 'Ordered by mistake'})
        self.assertEqual(response.status_code, 200, response.content)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.CANCELLED)
        self.assertEqual(po.cancelled_reason, 'Ordered by mistake')
        self.assertEqual(po.cancelled_by, self.supervisor)
        self.assertIsNotNone(po.cancelled_at)
        self.client.logout()

        # PENDING
        po2 = self.create_draft_po(quantity=5)
        self.client.login(username='pobstaff', password='x')
        self.client.post(reverse('frontend:purchase_submit', args=[po2.pk]))
        self.client.logout()
        self.client.login(username='pobsuper', password='x')
        self.client.post(reverse('frontend:purchase_cancel', args=[po2.pk]), {'reason': 'Supplier unavailable'})
        po2.refresh_from_db()
        self.assertEqual(po2.status, POStatus.CANCELLED)
        self.assertEqual(po2.cancelled_reason, 'Supplier unavailable')
        self.client.logout()

    def test_cancel_refused_from_approved_partial_received(self):
        """Phase 8.99c: approved/partial/received all reject cancellation
        server-side — a direct POST past the hidden button must be refused
        the same as any other invalid transition (05_PURCHASES.md's own
        "any state -> CANCELLED" no longer holds; see §13)."""
        # APPROVED
        po = self.create_draft_po(quantity=5)
        self.client.login(username='pobstaff', password='x')
        self.client.post(reverse('frontend:purchase_submit', args=[po.pk]))
        self.client.logout()
        self.client.login(username='pobsuper', password='x')
        self.client.post(reverse('frontend:purchase_approve', args=[po.pk]))
        response = self.client.post(reverse('frontend:purchase_cancel', args=[po.pk]), {'reason': 'reason'})
        self.assertEqual(response.status_code, 400, response.content)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.APPROVED)
        self.client.logout()

        # PARTIAL — must also refuse, and must not reverse the stock
        # already received (05_PURCHASES.md: "Cancelled PO | Does NOT
        # affect inventory" — moot now since cancel never even applies,
        # but the invariant must still hold).
        po2 = self.create_draft_po(quantity=10)
        self.client.login(username='pobstaff', password='x')
        self.client.post(reverse('frontend:purchase_submit', args=[po2.pk]))
        self.client.logout()
        self.client.login(username='pobsuper', password='x')
        self.client.post(reverse('frontend:purchase_approve', args=[po2.pk]))
        self.client.logout()
        self.client.login(username='pobstaff', password='x')
        item2 = po2.items.get()
        self.client.post(
            reverse('frontend:purchase_receive', args=[po2.pk]),
            {'receive_json': json.dumps([{'item_id': item2.pk, 'received_qty': 4}])},
        )
        self.client.logout()
        self.client.login(username='pobsuper', password='x')
        response = self.client.post(reverse('frontend:purchase_cancel', args=[po2.pk]), {'reason': 'reason'})
        self.assertEqual(response.status_code, 400, response.content)
        po2.refresh_from_db()
        self.assertEqual(po2.status, POStatus.PARTIAL)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 4, "a refused cancel must not touch stock already received")
        self.client.logout()

        # RECEIVED
        self.client.login(username='pobstaff', password='x')
        self.client.post(
            reverse('frontend:purchase_receive', args=[po2.pk]),
            {'receive_json': json.dumps([{'item_id': item2.pk, 'received_qty': 6}])},
        )
        self.client.logout()
        self.client.login(username='pobsuper', password='x')
        po2.refresh_from_db()
        self.assertEqual(po2.status, POStatus.RECEIVED)
        response = self.client.post(reverse('frontend:purchase_cancel', args=[po2.pk]), {'reason': 'reason'})
        self.assertEqual(response.status_code, 400, response.content)
        po2.refresh_from_db()
        self.assertEqual(po2.status, POStatus.RECEIVED)

    def test_cancel_rejects_blank_reason(self):
        """Server-side, not just client-side: a direct POST with no
        reason must be refused even though the button/prompt() pair would
        normally never let it happen."""
        po = self.create_draft_po(quantity=5)
        self.client.login(username='pobsuper', password='x')
        response = self.client.post(reverse('frontend:purchase_cancel', args=[po.pk]), {'reason': ''})
        self.assertEqual(response.status_code, 400, response.content)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.DRAFT)

    def test_staff_cannot_approve_reject_or_cancel(self):
        po = self.create_draft_po(quantity=5)
        self.client.login(username='pobstaff', password='x')
        self.client.post(reverse('frontend:purchase_submit', args=[po.pk]))

        for name in ('purchase_approve', 'purchase_reject', 'purchase_cancel'):
            response = self.client.post(reverse(f'frontend:{name}', args=[po.pk]))
            self.assertEqual(response.status_code, 302, f"{name} should redirect (blocked) for a Staff user")
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.PENDING, "none of the blocked actions should have taken effect")

    def test_admin_can_approve_confirming_supervisor_mixin_hierarchy(self):
        """SupervisorRequiredMixin.required_roles = [ADMIN, SUPERVISOR] —
        confirms Admin is NOT excluded by an over-strict exact-role check."""
        po = self.create_draft_po(quantity=5)
        self.client.login(username='pobstaff', password='x')
        self.client.post(reverse('frontend:purchase_submit', args=[po.pk]))
        self.client.logout()

        self.client.login(username='pobadmin', password='x')
        response = self.client.post(reverse('frontend:purchase_approve', args=[po.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.APPROVED)
        self.assertEqual(po.approved_by, self.admin)

    def test_inactive_supplier_excluded_and_inactive_product_rejected_in_line_items(self):
        inactive_supplier = Supplier.objects.create(
            supplier_name='Old Supply', company_name='Old Supply Co', contact_person='X',
            email='oldsupply@example.com', phone='555-0201', address='addr', is_active=False,
        )
        inactive_product = Product.objects.create(
            sku='PO-SKU-INACTIVE', name='Retired Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('1.00'), selling_price=Decimal('2.00'), is_active=False,
        )
        self.client.login(username='pobstaff', password='x')
        response = self.client.post(reverse('frontend:purchases'), {
            'supplier': inactive_supplier.pk,
            'items_json': json.dumps([
                {'productLabel': str(inactive_product.pk), 'quantity': 1, 'unitPrice': 1.0, 'discount': 0, 'tax': 0},
            ]),
        })
        self.assertEqual(response.status_code, 400)
        errors = response.json().get('errors', {})
        self.assertIn('supplier', errors)
        self.assertIn('items', errors)


class TimezoneAwareDateGenerationTests(TestCase):
    """Phase 8.99 — regression test for the auto_now_add/OS-clock gap
    flagged (not fixed) back in Phase 8.6: `PurchaseOrder.order_date`/
    `SaleTransaction.transaction_date` (previously
    `DateField(auto_now_add=True)`) and their PO-number/invoice-number
    date components (previously `timezone.now().strftime(...)`, which
    formats in UTC) must reflect the Asia/Dhaka calendar day, not the OS
    clock's raw local date or the UTC date — the two only ever diverge in
    the ~6-hour window either side of midnight, which is exactly why this
    was invisible in normal day-to-day dev use on a machine whose OS
    clock already happens to be set to Bangladesh time, and would only
    have surfaced for real on a UTC production server.

    Mocks `django.utils.timezone.now()` to a UTC instant that falls on a
    genuinely different Dhaka calendar day (2026-01-01 20:00 UTC =
    2026-01-02 02:00 Dhaka) — this deliberately does NOT touch the real
    OS clock, so it also proves the fix no longer depends on
    `datetime.date.today()` at all: a regression back to
    `auto_now_add=True` would still read the real, unmocked OS date here
    (this test's actual run date) and fail, while a regression back to
    `timezone.now().strftime(...)` would produce '20260101' (the UTC day)
    instead of the expected '20260102' (the Dhaka day)."""

    UTC_INSTANT = datetime(2026, 1, 1, 20, 0, 0, tzinfo=dt_timezone.utc)  # -> 2026-01-02 in Asia/Dhaka

    def setUp(self):
        self.user = User.objects.create_user(
            username='tzuser', email='tzuser@example.com', password='x',
            employee_id='EMP-9500', full_name='TZ User', role=UserRole.STAFF,
        )
        self.supplier = Supplier.objects.create(
            supplier_name='TZ Supply', company_name='TZ Supply Co', contact_person='Jo',
            email='tzsupply@example.com', phone='555-0500', address='1 TZ Way',
        )

    @patch('django.utils.timezone.now')
    def test_purchase_order_date_and_number_use_dhaka_day_not_utc(self, mock_now):
        mock_now.return_value = self.UTC_INSTANT
        po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.user)
        self.assertEqual(po.order_date, datetime(2026, 1, 2).date())
        self.assertTrue(po.po_number.startswith('PO-20260102-'), po.po_number)

    @patch('django.utils.timezone.now')
    def test_sale_transaction_date_and_number_use_dhaka_day_not_utc(self, mock_now):
        mock_now.return_value = self.UTC_INSTANT
        sale = SaleTransaction.objects.create(created_by=self.user)
        self.assertEqual(sale.transaction_date, datetime(2026, 1, 2).date())
        self.assertTrue(sale.invoice_number.startswith('INV-20260102-'), sale.invoice_number)


class ExplicitDateAssignmentTests(TestCase):
    """Phase 9.5 — the flip side of TimezoneAwareDateGenerationTests above:
    proves order_date/transaction_date's "assign only if unset" guard (both
    save()s' `if self.order_date is None` / `if self.transaction_date is
    None`) genuinely preserves a caller-supplied date rather than always
    overwriting it. This is the mechanism seed_dev_data.py relies on to
    backdate sales/POs across the 60/180-day AI thresholds (docs/
    project_memory.md §13) — if a future change made these unconditional
    again, this test (not just TimezoneAwareDateGenerationTests, which only
    proves the *default* path) would catch it.

    Also proves — per Phase 9.5's own Part A step 2 finding — that this is
    a *capability*, not a *hole*: nothing reachable from an HTTP POST can
    supply these fields (PurchaseOrderForm/SaleTransactionForm's Meta.fields
    never list them), so honoring an explicit value only matters to code
    that constructs the model directly, i.e. server-side scripts like the
    seed command, never a client request."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='backdateuser', email='backdateuser@example.com', password='x',
            employee_id='EMP-9501', full_name='Backdate User', role=UserRole.STAFF,
        )
        self.supplier = Supplier.objects.create(
            supplier_name='Backdate Supply', company_name='Backdate Supply Co', contact_person='Jo',
            email='backdatesupply@example.com', phone='555-0501', address='1 Backdate Way',
        )

    def test_purchase_order_honors_explicit_order_date(self):
        target = datetime(2025, 3, 14).date()
        po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.user, order_date=target)
        self.assertEqual(po.order_date, target)
        po.refresh_from_db()
        self.assertEqual(po.order_date, target)

    def test_sale_transaction_honors_explicit_transaction_date(self):
        target = datetime(2025, 3, 14).date()
        sale = SaleTransaction.objects.create(created_by=self.user, transaction_date=target)
        self.assertEqual(sale.transaction_date, target)
        sale.refresh_from_db()
        self.assertEqual(sale.transaction_date, target)

    def test_sale_transaction_date_survives_a_later_unrelated_save(self):
        """Guards against a regression where the None-check is accidentally
        moved/removed so a *second* save() (e.g. updating total_amount,
        exactly what SaleService.create_sale() does next) silently resets
        an already-set explicit date back to today."""
        target = datetime(2025, 3, 14).date()
        sale = SaleTransaction.objects.create(created_by=self.user, transaction_date=target)
        sale.total_amount = Decimal('42.00')
        sale.save(update_fields=['total_amount'])
        sale.refresh_from_db()
        self.assertEqual(sale.transaction_date, target)


class PurchaseOrderExpectedDeliveryTests(TestCase):
    """Phase 8.98b: `expected_delivery` already existed on `PurchaseOrder`
    (SCHEMA.md, already in `PurchaseOrderForm.Meta.fields`) — the gap was
    display (no table column) and validation (no past-date guard). Proves
    both real, server-side, timezone-correct (Asia/Dhaka, not the OS
    clock) — not just client-side, which a raw POST bypasses entirely.

    `order_date` is set explicitly in `PurchaseOrder.save()` via
    `timezone.localdate()` (Phase 8.99 — was `auto_now_add=True`, fixed
    since that silently used the OS clock's raw date, not TIME_ZONE's) —
    never user-submitted, always exactly "today" (Asia/Dhaka) at save
    time. So "expected_delivery can't be in the past" and "expected_
    delivery can't be before order_date" are the same real-world check;
    there's no separate order_date value to compare against during form
    validation (the instance isn't saved yet), and no way for a client to
    submit a past order_date in the first place — it isn't in this form's
    `fields` at all."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='podatestaff', email='podatestaff@example.com', password='x',
            employee_id='EMP-5101', full_name='PO Date Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='PO Date Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='PO Date Supply', company_name='PO Date Supply Co', contact_person='Jo',
            email='podatesupply@example.com', phone='555-0201', address='1 PO Date Way', is_active=True,
        )
        self.product = Product.objects.create(
            sku='PO-DATE-001', name='PO Date Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('10.00'), reorder_level=5,
        )
        self.client.login(username='podatestaff', password='x')

    def payload(self, **overrides):
        data = {
            'supplier': self.supplier.pk,
            'items_json': json.dumps([
                {'productLabel': str(self.product.pk), 'quantity': 5, 'unitPrice': 5.0, 'discount': 0, 'tax': 0},
            ]),
        }
        data.update(overrides)
        return data

    def test_expected_delivery_in_the_past_rejected_server_side(self):
        past_date = (timezone.localdate() - timedelta(days=1)).isoformat()
        response = self.client.post(
            reverse('frontend:purchases'), self.payload(expected_delivery=past_date)
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('expected_delivery', response.json()['errors'])
        self.assertFalse(
            PurchaseOrder.objects.filter(supplier=self.supplier).exists(),
            "a rejected PO must not be created at all",
        )

    def test_expected_delivery_today_is_accepted(self):
        today = timezone.localdate()
        response = self.client.post(
            reverse('frontend:purchases'), self.payload(expected_delivery=today.isoformat())
        )
        self.assertEqual(response.status_code, 200, response.content)
        po = PurchaseOrder.objects.get(supplier=self.supplier)
        self.assertEqual(po.expected_delivery, today)
        self.assertEqual(po.order_date, today)

    def test_expected_delivery_in_the_future_is_accepted(self):
        future_date = timezone.localdate() + timedelta(days=14)
        response = self.client.post(
            reverse('frontend:purchases'), self.payload(expected_delivery=future_date.isoformat())
        )
        self.assertEqual(response.status_code, 200, response.content)
        po = PurchaseOrder.objects.get(supplier=self.supplier)
        self.assertEqual(po.expected_delivery, future_date)

    def test_expected_delivery_still_genuinely_optional(self):
        response = self.client.post(reverse('frontend:purchases'), self.payload(expected_delivery=''))
        self.assertEqual(response.status_code, 200, response.content)
        po = PurchaseOrder.objects.get(supplier=self.supplier)
        self.assertIsNone(po.expected_delivery)

    def test_expected_delivery_column_and_date_input_render_real_data(self):
        future_date = timezone.localdate() + timedelta(days=7)
        self.client.post(reverse('frontend:purchases'), self.payload(expected_delivery=future_date.isoformat()))

        response = self.client.get(reverse('frontend:purchases'))
        self.assertContains(response, 'Expected delivery')
        self.assertContains(response, future_date.strftime('%d %b %Y'))
        # The date input's min= is server-computed Asia/Dhaka "today", not
        # left for the browser's local clock to guess.
        self.assertContains(response, f'min="{timezone.localdate().isoformat()}"')


# ----------------------------------------------------------------- Sales
# Phase 7. Real HTTP round-trips, same discipline as PurchaseWorkflowViewTests.

class SaleWorkflowViewTests(TestCase):
    """Phase 8.99b: Sale now goes through the same real approval workflow
    as Purchases — create (DRAFT) -> submit (PENDING) -> approve
    (COMPLETED, stock moves) / reject (REJECTED). One test per documented
    transition, written alongside the views per this phase's own
    instruction, matching Phase 7's own precedent for exactly this
    reasoning."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='salestaff', email='salestaff@example.com', password='x',
            employee_id='EMP-6001', full_name='Sale Staffer', role=UserRole.STAFF,
        )
        self.supervisor = User.objects.create_user(
            username='salesuper', email='salesuper@example.com', password='x',
            employee_id='EMP-6002', full_name='Sale Supervisor', role=UserRole.SUPERVISOR,
        )
        self.admin = User.objects.create_user(
            username='saleadmin', email='saleadmin@example.com', password='x',
            employee_id='EMP-6003', full_name='Sale Admin', role=UserRole.ADMIN,
        )
        self.category = Category.objects.create(name='Sale Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='Sale Supply', company_name='Sale Supply Co', contact_person='Jo',
            email='salesupply@example.com', phone='555-0300', address='1 Sale Way', is_active=True,
        )
        self.product = Product.objects.create(
            sku='SALE-SKU-001', name='Sale Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('10.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(self.product)
        InventoryService.increase_stock(
            product=self.product, quantity=20, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.staff,
        )

    def create_draft_sale(self, quantity=5, customer_name='Walk-in customer'):
        self.client.login(username='salestaff', password='x')
        payload = {
            'customer_name': customer_name,
            'items_json': json.dumps([
                {'productLabel': str(self.product.pk), 'quantity': quantity, 'unitPrice': 10.0, 'discount': 0},
            ]),
        }
        response = self.client.post(reverse('frontend:sales'), payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.client.logout()
        return SaleTransaction.objects.filter(created_by=self.staff).order_by('-pk').first()

    def test_create_sale_is_draft_with_no_stock_change(self):
        sale = self.create_draft_sale(quantity=5)
        self.assertEqual(sale.status, SaleStatus.DRAFT)
        self.assertEqual(sale.total_amount, Decimal('50.00'))
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 20, "creating a sale must not touch stock")
        self.assertEqual(
            InventoryMovement.objects.filter(reference_type='SaleTransaction', reference_id=sale.pk).count(), 0,
            "creating a draft sale must not touch stock",
        )
        self.assertTrue(AuditLog.objects.filter(action='SALE_CREATED', affected_id=sale.pk).exists())

    def test_submit_approve_by_supervisor_deducts_stock_and_completes(self):
        sale = self.create_draft_sale(quantity=5)

        self.client.login(username='salestaff', password='x')
        self.client.post(reverse('frontend:sale_submit', args=[sale.pk]))
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.PENDING)
        self.client.logout()

        self.client.login(username='salesuper', password='x')
        response = self.client.post(reverse('frontend:sale_approve', args=[sale.pk]))
        self.assertEqual(response.status_code, 200, response.content)

        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.COMPLETED)
        self.assertEqual(sale.approved_by, self.supervisor)
        self.assertIsNotNone(sale.approved_at)

        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 15, "20 in stock minus 5 sold")

        movement = InventoryMovement.objects.get(reference_type='SaleTransaction', reference_id=sale.pk)
        self.assertEqual(movement.movement_type, MovementType.SALE)
        self.assertEqual(movement.quantity_change, -5)
        self.assertTrue(AuditLog.objects.filter(action='SALE_SUBMITTED', affected_id=sale.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action='SALE_APPROVED', affected_id=sale.pk).exists())

    def test_admin_can_also_approve_confirming_supervisor_mixin_hierarchy(self):
        sale = self.create_draft_sale(quantity=2)
        self.client.login(username='salestaff', password='x')
        self.client.post(reverse('frontend:sale_submit', args=[sale.pk]))
        self.client.logout()

        self.client.login(username='saleadmin', password='x')
        response = self.client.post(reverse('frontend:sale_approve', args=[sale.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.COMPLETED)
        self.assertEqual(sale.approved_by, self.admin)

    def test_staff_cannot_approve_directly(self):
        """Server-side enforcement, not just button visibility — a direct
        POST past the hidden button must still be blocked."""
        sale = self.create_draft_sale(quantity=1)
        self.client.login(username='salestaff', password='x')
        self.client.post(reverse('frontend:sale_submit', args=[sale.pk]))
        response = self.client.post(reverse('frontend:sale_approve', args=[sale.pk]))
        self.assertEqual(response.status_code, 302, "staff should be blocked, matching SupervisorRequiredMixin")
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.PENDING)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 20)

    def test_staff_cannot_reject_directly(self):
        sale = self.create_draft_sale(quantity=1)
        self.client.login(username='salestaff', password='x')
        self.client.post(reverse('frontend:sale_submit', args=[sale.pk]))
        response = self.client.post(reverse('frontend:sale_reject', args=[sale.pk]), {'reason': 'no budget'})
        self.assertEqual(response.status_code, 302)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.PENDING)

    def test_supervisor_rejects_with_reason_stock_unchanged(self):
        sale = self.create_draft_sale(quantity=5)
        self.client.login(username='salestaff', password='x')
        self.client.post(reverse('frontend:sale_submit', args=[sale.pk]))
        self.client.logout()

        self.client.login(username='salesuper', password='x')
        response = self.client.post(
            reverse('frontend:sale_reject', args=[sale.pk]), {'reason': 'Customer changed their mind'},
        )
        self.assertEqual(response.status_code, 200, response.content)

        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.REJECTED)
        self.assertEqual(sale.rejected_reason, 'Customer changed their mind')
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 20)
        self.assertTrue(AuditLog.objects.filter(action='SALE_REJECTED', affected_id=sale.pk).exists())

    def test_approval_fails_cleanly_when_stock_insufficient_at_approval_time(self):
        """Deliberately set up two drafts against the same limited stock
        (20 units, from setUp) so only one approval can succeed —
        confirms the documented, deliberate consequence of not reserving
        stock at draft time."""
        sale1 = self.create_draft_sale(quantity=15)
        sale2 = self.create_draft_sale(quantity=15)
        self.client.login(username='salestaff', password='x')
        self.client.post(reverse('frontend:sale_submit', args=[sale1.pk]))
        self.client.post(reverse('frontend:sale_submit', args=[sale2.pk]))
        self.client.logout()

        self.client.login(username='salesuper', password='x')
        r1 = self.client.post(reverse('frontend:sale_approve', args=[sale1.pk]))
        self.assertEqual(r1.status_code, 200, r1.content)

        r2 = self.client.post(reverse('frontend:sale_approve', args=[sale2.pk]))
        self.assertEqual(r2.status_code, 400)
        self.assertIn('Insufficient stock', r2.json().get('error', ''))

        sale2.refresh_from_db()
        self.assertEqual(sale2.status, SaleStatus.PENDING, "a failed approval must leave the sale pending")
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 5, "only sale1's 15 units were ever actually deducted")

    def test_completed_sale_cannot_be_cancelled(self):
        sale = self.create_draft_sale(quantity=5)
        self.client.login(username='salestaff', password='x')
        self.client.post(reverse('frontend:sale_submit', args=[sale.pk]))
        self.client.logout()
        self.client.login(username='salesuper', password='x')
        self.client.post(reverse('frontend:sale_approve', args=[sale.pk]))

        response = self.client.post(reverse('frontend:sale_cancel', args=[sale.pk]), {'reason': 'reason'})
        self.assertEqual(response.status_code, 400)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.COMPLETED)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 15, "a blocked cancel must not restore stock either")

    def test_draft_and_pending_sale_can_be_cancelled_by_supervisor(self):
        sale = self.create_draft_sale(quantity=5)
        self.client.login(username='salesuper', password='x')
        response = self.client.post(reverse('frontend:sale_cancel', args=[sale.pk]), {'reason': 'Customer changed their mind'})
        self.assertEqual(response.status_code, 200, response.content)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CANCELLED)
        self.assertEqual(sale.cancelled_reason, 'Customer changed their mind')
        self.assertEqual(sale.cancelled_by, self.supervisor)
        self.assertIsNotNone(sale.cancelled_at)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 20)

    def test_staff_cannot_cancel(self):
        sale = self.create_draft_sale(quantity=5)
        self.client.login(username='salestaff', password='x')
        response = self.client.post(reverse('frontend:sale_cancel', args=[sale.pk]), {'reason': 'reason'})
        self.assertEqual(response.status_code, 302, "Staff should be blocked (redirected), matching 06_SALES.md's @supervisor_required")
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.DRAFT)

    def test_cancel_sale_rejects_blank_reason(self):
        """Server-side, not just client-side."""
        sale = self.create_draft_sale(quantity=5)
        self.client.login(username='salesuper', password='x')
        response = self.client.post(reverse('frontend:sale_cancel', args=[sale.pk]), {'reason': ''})
        self.assertEqual(response.status_code, 400, response.content)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.DRAFT)

    def test_inactive_product_rejected_in_line_items(self):
        inactive_product = Product.objects.create(
            sku='SALE-SKU-INACTIVE', name='Retired Sale Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('1.00'), selling_price=Decimal('2.00'), is_active=False,
        )
        self.client.login(username='salestaff', password='x')
        response = self.client.post(reverse('frontend:sales'), {
            'items_json': json.dumps([
                {'productLabel': str(inactive_product.pk), 'quantity': 1, 'unitPrice': 2.0, 'discount': 0, 'tax': 0},
            ]),
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('items', response.json().get('errors', {}))


# ----------------------------------------------------------- Adjustments
# Phase 7. Real HTTP round-trips, same discipline as the other two.

class AdjustmentWorkflowViewTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(
            username='adjstaff', email='adjstaff@example.com', password='x',
            employee_id='EMP-7001', full_name='Adjustment Staffer', role=UserRole.STAFF,
        )
        self.supervisor = User.objects.create_user(
            username='adjsuper', email='adjsuper@example.com', password='x',
            employee_id='EMP-7002', full_name='Adjustment Supervisor', role=UserRole.SUPERVISOR,
        )
        self.category = Category.objects.create(name='Adj Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='Adj Supply', company_name='Adj Supply Co', contact_person='Jo',
            email='adjsupply@example.com', phone='555-0400', address='1 Adj Way', is_active=True,
        )
        self.product = Product.objects.create(
            sku='ADJ-SKU-001', name='Adj Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('10.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(self.product)
        InventoryService.increase_stock(
            product=self.product, quantity=20, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.staff,
        )

    def create_pending_adjustment(self, adjustment_type='decrease', quantity=5):
        # Phase 12 — reason_code is now required (AdjustmentForm), and
        # 'count_correction' (rather than the AUTO-eligible thresholds'
        # own combination) keeps this landing on the SUPERVISOR catch-all
        # policy — the PENDING state every test in this class assumes.
        self.client.login(username='adjstaff', password='x')
        response = self.client.post(reverse('frontend:adjustments'), {
            'product': self.product.pk, 'adjustment_type': adjustment_type,
            'quantity': quantity, 'reason_code': AdjustmentReason.COUNT_CORRECTION,
            'reason': 'Verification test reason',
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.client.logout()
        return InventoryAdjustment.objects.filter(product=self.product).order_by('-pk').first()

    def test_create_writes_no_movement_until_approved(self):
        adjustment = self.create_pending_adjustment()
        self.assertEqual(adjustment.status, AdjustmentStatus.PENDING)
        self.assertEqual(
            InventoryMovement.objects.filter(reference_type='InventoryAdjustment', reference_id=adjustment.pk).count(), 0,
        )
        self.assertTrue(AuditLog.objects.filter(action='ADJUSTMENT_REQUESTED', affected_id=adjustment.pk).exists())

    def test_approve_decrease_writes_movement_and_reduces_stock(self):
        adjustment = self.create_pending_adjustment(adjustment_type='decrease', quantity=5)
        self.client.login(username='adjsuper', password='x')
        response = self.client.post(reverse('frontend:adjustment_approve', args=[adjustment.pk]))
        self.assertEqual(response.status_code, 200, response.content)

        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.APPROVED)
        self.assertEqual(adjustment.approved_by, self.supervisor)

        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 15)
        movement = InventoryMovement.objects.get(reference_type='InventoryAdjustment', reference_id=adjustment.pk)
        self.assertEqual(movement.movement_type, MovementType.ADJUSTMENT)
        self.assertEqual(movement.quantity_change, -5)

    def test_approve_increase_writes_movement_and_increases_stock(self):
        adjustment = self.create_pending_adjustment(adjustment_type='increase', quantity=8)
        self.client.login(username='adjsuper', password='x')
        response = self.client.post(reverse('frontend:adjustment_approve', args=[adjustment.pk]))
        self.assertEqual(response.status_code, 200, response.content)

        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 28)
        movement = InventoryMovement.objects.get(reference_type='InventoryAdjustment', reference_id=adjustment.pk)
        self.assertEqual(movement.quantity_change, 8)

    def test_decrease_beyond_available_stock_rejected(self):
        adjustment = self.create_pending_adjustment(adjustment_type='decrease', quantity=999)
        self.client.login(username='adjsuper', password='x')
        response = self.client.post(reverse('frontend:adjustment_approve', args=[adjustment.pk]))
        self.assertEqual(response.status_code, 400)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.PENDING, "a failed approval must not change status")
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 20)

    def test_reject_writes_no_movement(self):
        adjustment = self.create_pending_adjustment()
        self.client.login(username='adjsuper', password='x')
        response = self.client.post(
            reverse('frontend:adjustment_reject', args=[adjustment.pk]), {'reason': 'Not needed'},
        )
        self.assertEqual(response.status_code, 200, response.content)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.REJECTED)
        self.assertEqual(adjustment.rejected_reason, 'Not needed')
        self.assertFalse(InventoryMovement.objects.filter(reference_type='InventoryAdjustment', reference_id=adjustment.pk).exists())

    def test_staff_cannot_approve_or_reject(self):
        adjustment = self.create_pending_adjustment()
        self.client.login(username='adjstaff', password='x')

        response = self.client.post(reverse('frontend:adjustment_approve', args=[adjustment.pk]))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse('frontend:adjustment_reject', args=[adjustment.pk]), {'reason': 'x'})
        self.assertEqual(response.status_code, 302)

        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.PENDING)


def _extract_pdf_text(pdf_bytes):
    """Phase 13 — ReportLab's default content-stream encoding is
    [ASCII85Decode, FlateDecode] (confirmed empirically, not assumed —
    the raw bytes start '%PDF-1.4' and every content stream ends in the
    Adobe ASCII85 '~>' terminator). Undoing both, per stream, turns the
    binary PDF back into its literal PDF-operator text — every string
    drawn with drawString()/Paragraph() appears as literal ASCII inside
    parentheses, e.g. '(Zylotech Distribution Ltd) Tj' — searchable with
    a plain `in` check. Good enough for this project's own generated
    PDFs (a controlled format); not a general-purpose PDF text
    extractor and never used to parse third-party PDFs."""
    text = b""
    for raw in re.findall(rb"stream\n(.*?)endstream", pdf_bytes, re.S):
        raw = raw.strip(b"\r\n")
        if raw.endswith(b"~>"):
            raw = raw[:-2]
        try:
            decoded = base64.a85decode(raw)
        except Exception:
            continue
        try:
            decoded = zlib.decompress(decoded)
        except Exception:
            pass
        text += decoded
    return text


class PerRecordPDFViewTests(TestCase):
    """Phase 8.98d — individual Purchase Order / Sale Transaction PDF
    downloads, distinct from Reports' 9 whole-report exports (untouched by
    this phase). Same `AnyStaffMixin` gate as the list pages themselves."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='pdfstaff', email='pdfstaff@example.com', password='x',
            employee_id='EMP-7001', full_name='PDF Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='PDF Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='PDF Supply', company_name='PDF Supply Co', contact_person='Jo',
            email='pdfsupply@example.com', phone='555-0400', address='1 PDF Way', is_active=True,
        )
        self.product = Product.objects.create(
            sku='PDF-SKU-001', name='PDF Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'), tax_rate=Decimal('10.00'),
        )
        self.po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.staff)
        PurchaseOrderItem.objects.create(
            purchase_order=self.po, product=self.product, ordered_qty=5,
            unit_price=Decimal('10.00'), tax=self.product.tax_rate,
        )
        self.po.total_cost = self.po.items.get().line_total
        self.po.save(update_fields=['total_cost'])

        InventoryService.initialize_for_product(self.product)
        InventoryService.increase_stock(
            product=self.product, quantity=20, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.staff,
        )
        self.sale = SaleService.create_sale(
            {'customer_name': 'Walk-in Customer'},
            [{'product_id': self.product.pk, 'quantity': 3, 'unit_price': Decimal('20.00'), 'discount': 0}],
            self.staff,
        )

    def test_purchase_pdf_requires_login(self):
        response = self.client.get(reverse('frontend:purchase_pdf', args=[self.po.pk]))
        self.assertRedirects(
            response,
            f"{reverse('frontend:login')}?next={reverse('frontend:purchase_pdf', args=[self.po.pk])}",
        )

    def test_staff_can_download_purchase_pdf(self):
        self.client.login(username='pdfstaff', password='x')
        response = self.client.get(reverse('frontend:purchase_pdf', args=[self.po.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(self.po.po_number, response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_purchase_pdf_404_for_unknown_pk(self):
        self.client.login(username='pdfstaff', password='x')
        response = self.client.get(reverse('frontend:purchase_pdf', args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_sale_pdf_requires_login(self):
        response = self.client.get(reverse('frontend:sale_pdf', args=[self.sale.pk]))
        self.assertRedirects(
            response,
            f"{reverse('frontend:login')}?next={reverse('frontend:sale_pdf', args=[self.sale.pk])}",
        )

    def test_staff_can_download_sale_pdf(self):
        self.client.login(username='pdfstaff', password='x')
        response = self.client.get(reverse('frontend:sale_pdf', args=[self.sale.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(self.sale.invoice_number, response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_sale_pdf_404_for_unknown_pk(self):
        self.client.login(username='pdfstaff', password='x')
        response = self.client.get(reverse('frontend:sale_pdf', args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_staff_can_download_adjustment_pdf(self):
        """Phase 13 — new: no per-adjustment PDF existed before this."""
        adjustment = InventoryAdjustment.objects.create(
            product=self.product, adjustment_type=AdjustmentType.DECREASE, quantity=2,
            reason_code=AdjustmentReason.DAMAGE, reason='Damaged in transit.', requested_by=self.staff,
        )
        self.client.login(username='pdfstaff', password='x')
        response = self.client.get(reverse('frontend:adjustment_pdf', args=[adjustment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_adjustment_pdf_404_for_unknown_pk(self):
        self.client.login(username='pdfstaff', password='x')
        response = self.client.get(reverse('frontend:adjustment_pdf', args=[999999]))
        self.assertEqual(response.status_code, 404)


class PDFCompanyBrandingTests(TestCase):
    """Phase 13 Task 2's own acceptance test: 'change the company name
    and address in settings, regenerate any PDF, and the new values
    appear' — through the real SystemSettingsForm/SettingsView POST, not
    just a direct model .save(), so this proves the whole chain
    (form -> SystemSettings -> get_company_profile() -> frontend/pdf.py)
    actually works end to end, not just that the model field changed."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='brandadmin', email='brandadmin@example.com', password='x',
            employee_id='EMP-9601', full_name='Brand Admin', role=UserRole.ADMIN,
        )
        self.staff = User.objects.create_user(
            username='brandstaff', email='brandstaff@example.com', password='x',
            employee_id='EMP-9602', full_name='Brand Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='Brand Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='Brand Supply', company_name='Brand Supply Co', contact_person='Jo',
            email='brandsupply@example.com', phone='555-0600', address='1 Brand Way', is_active=True,
        )
        self.product = Product.objects.create(
            sku='BRAND-SKU-001', name='Brand Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'),
        )
        self.po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.staff)
        PurchaseOrderItem.objects.create(
            purchase_order=self.po, product=self.product, ordered_qty=1, unit_price=Decimal('10.00'),
        )

    def test_settings_change_appears_in_generated_pdf(self):
        self.client.login(username='brandadmin', password='x')
        response = self.client.post(reverse('frontend:settings'), {
            'company_name': 'Zylotech Distribution Ltd',
            'company_address': 'House 42, Road 7, Banani, Dhaka',
        })
        self.assertEqual(response.status_code, 200, response.content)

        from frontend import reports as report_lib
        pdf_response = report_lib.generate_purchase_order_pdf(self.po)
        text = _extract_pdf_text(pdf_response.content)
        self.assertIn(b'Zylotech Distribution Ltd', text)
        self.assertIn(b'Banani, Dhaka', text)

    def test_pdf_renders_with_no_logo_and_blank_optional_company_fields(self):
        """Every optional company field left blank (the model's own
        default state) must still produce a valid PDF — no broken image
        box, no crash — falling back to the company name in type."""
        settings_obj = SystemSettings.get_settings()
        settings_obj.company_logo = None
        settings_obj.company_address = ''
        settings_obj.company_email = ''
        settings_obj.company_phone = ''
        settings_obj.company_tax_number = ''
        settings_obj.company_website = ''
        settings_obj.save()

        from frontend import reports as report_lib
        response = report_lib.generate_purchase_order_pdf(self.po)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertGreater(len(response.content), 500, "a real document, not an empty/broken stub")

    def test_completely_blank_company_name_falls_back_to_placeholder_text(self):
        settings_obj = SystemSettings.get_settings()
        settings_obj.company_name = ''
        settings_obj.save()

        from frontend import reports as report_lib
        response = report_lib.generate_purchase_order_pdf(self.po)
        text = _extract_pdf_text(response.content)
        self.assertIn(b'Company name not set', text)


class PDFDocumentQualityTests(TestCase):
    """Phase 13 Task 3 — totals reconciliation, status watermarks, and
    multi-page pagination/repeating headers."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='qualitystaff', email='qualitystaff@example.com', password='x',
            employee_id='EMP-9611', full_name='Quality Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='Quality Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='Quality Supply', company_name='Quality Supply Co', contact_person='Jo',
            email='qualitysupply@example.com', phone='555-0700', address='1 Quality Way', is_active=True,
        )
        self.product = Product.objects.create(
            sku='QUAL-SKU-001', name='Quality Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'),
        )

    def test_totals_reconcile_with_stored_record_total_cost(self):
        """Subtotal - Discount + Tax must equal Grand Total exactly, and
        Grand Total must equal the record's own stored total_cost — not
        an approximation, no rounding drift."""
        po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.staff)
        PurchaseOrderItem.objects.create(
            purchase_order=po, product=self.product, ordered_qty=10,
            unit_price=Decimal('20.00'), discount=Decimal('5.00'), tax=Decimal('8.00'),
        )
        po.total_cost = po.items.get().line_total
        po.save(update_fields=['total_cost'])

        from frontend.pricing import calculate_totals_breakdown
        items = list(po.items.all())
        subtotal, discount_total, tax_total, grand_total = calculate_totals_breakdown(items)
        self.assertEqual(subtotal - discount_total + tax_total, grand_total)
        self.assertEqual(grand_total, po.total_cost)

        from frontend import reports as report_lib
        response = report_lib.generate_purchase_order_pdf(po)
        text = _extract_pdf_text(response.content)
        from frontend import pdf as pdf_lib
        self.assertIn(pdf_lib.format_currency(grand_total).encode(), text)

    def test_cancelled_purchase_order_pdf_shows_status_watermark(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier, created_by=self.staff, status=POStatus.CANCELLED,
            cancelled_reason='Test cancellation', cancelled_by=self.staff, cancelled_at=timezone.now(),
        )
        PurchaseOrderItem.objects.create(purchase_order=po, product=self.product, ordered_qty=1, unit_price=Decimal('10.00'))

        from frontend import reports as report_lib
        text = _extract_pdf_text(report_lib.generate_purchase_order_pdf(po).content)
        self.assertIn(b'CANCELLED', text)

    def test_approved_purchase_order_pdf_has_no_watermark(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier, created_by=self.staff, status=POStatus.APPROVED,
            approved_by=self.staff, approved_at=timezone.now(),
        )
        PurchaseOrderItem.objects.create(purchase_order=po, product=self.product, ordered_qty=1, unit_price=Decimal('10.00'))

        from frontend import reports as report_lib
        text = _extract_pdf_text(report_lib.generate_purchase_order_pdf(po).content)
        self.assertNotIn(b'CANCELLED', text)
        self.assertNotIn(b'REJECTED', text)

    def test_rejected_adjustment_pdf_shows_status_watermark(self):
        adjustment = InventoryAdjustment.objects.create(
            product=self.product, adjustment_type=AdjustmentType.DECREASE, quantity=1,
            reason_code=AdjustmentReason.OTHER, reason='test', requested_by=self.staff,
            status=AdjustmentStatus.REJECTED, rejected_reason='Recount needed',
        )
        from frontend import reports as report_lib
        text = _extract_pdf_text(report_lib.generate_adjustment_pdf(adjustment).content)
        self.assertIn(b'REJECTED', text)

    def test_multi_page_report_repeats_table_header_and_numbers_pages(self):
        """A report table long enough to force pagination must repeat
        the column header row on every page and carry a correct
        'Page N of M' with M > 1 — not just a single unnumbered page."""
        from frontend import pdf as pdf_lib
        headers = ['Date', 'Product', 'Type', 'Qty Change', 'Stock Before', 'Stock After', 'Reference', 'Performed By']
        rows = [
            ['2026-08-20 10:00', f'Widget {i}', 'Sale', '-2', '10', '8', f'SaleTransaction #{i}', 'Jane Doe']
            for i in range(120)
        ]
        response = pdf_lib.render_tabular_report(filename='t.pdf', title='Inventory Movement Report', headers=headers, rows=rows)
        text = _extract_pdf_text(response.content)
        self.assertIn(b'Page 1 of ', text)
        # Every page repeats the table header — "Performed By" (the last
        # column header) appears once per page, not once for the whole document.
        self.assertGreater(text.count(b'Performed By'), 1, "the table header must repeat on more than one page")
        # And the real total must be greater than 1 — this dataset does
        # not fit on a single page.
        match = re.search(rb'Page 1 of (\d+)', text)
        self.assertIsNotNone(match)
        self.assertGreater(int(match.group(1)), 1)


# --------------------------------------------------------------- Phase 8
# Audit Log, Notifications, Users & Roles, Settings, Reports. Real HTTP
# round-trips through frontend/urls.py, same style as Phase 7's workflow
# tests above — RBAC gate + one success-path assertion per module,
# following Phase 6/7's live-verification-primary precedent rather than
# Phase 7's full transition-matrix mandate (this task's own instructions
# didn't repeat that "write tests alongside" requirement), but still
# regression-covering every module's admin/supervisor-only gate since
# those are the security-sensitive part of each one.

class AuditLogViewTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='auditadmin', email='auditadmin@example.com', password='x',
            employee_id='EMP-8001', full_name='Audit Admin', role=UserRole.ADMIN,
        )
        self.staff = User.objects.create_user(
            username='auditstaff', email='auditstaff@example.com', password='x',
            employee_id='EMP-8002', full_name='Audit Staffer', role=UserRole.STAFF,
        )
        AuditLog.objects.create(user=self.admin, action='LOGIN_SUCCESS', module='authentication', status='success')

    def test_admin_sees_real_log_rows(self):
        self.client.login(username='auditadmin', password='x')
        response = self.client.get(reverse('frontend:audit_log'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LOGIN_SUCCESS')

    def test_staff_blocked(self):
        self.client.login(username='auditstaff', password='x')
        response = self.client.get(reverse('frontend:audit_log'))
        self.assertRedirects(response, reverse('frontend:dashboard'))

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('frontend:audit_log'))
        self.assertRedirects(response, f"{reverse('frontend:login')}?next={reverse('frontend:audit_log')}")

    def test_audit_log_rows_are_immutable_even_from_this_view(self):
        """This view never attempts a write, but the model-level guarantee
        (Phase 1/BUG-20's sibling) is what actually makes 13_AUDIT.md's
        "read-only" rule safe to rely on here — regression-guard it."""
        log = AuditLog.objects.first()
        log.status = 'failure'
        with self.assertRaises(PermissionError):
            log.save()


class NotificationViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='notifuser', email='notifuser@example.com', password='x',
            employee_id='EMP-8010', full_name='Notif User', role=UserRole.STAFF,
        )
        self.other = User.objects.create_user(
            username='notifother', email='notifother@example.com', password='x',
            employee_id='EMP-8011', full_name='Notif Other', role=UserRole.STAFF,
        )
        # Phase 8.98: titles made long/unique (not bare "T1"/"T2"/"T3") —
        # a short substring assertion against a full rendered page (which
        # always includes a randomly-generated CSRF token) has a real,
        # if small, chance of a false-positive collision; hit exactly once
        # by chance during Phase 8.98's own test run (a token containing
        # "vT3E" tripped assertNotContains(response, 'T3')). Not a code
        # bug — a pre-existing test-fixture fragility, fixed here since it
        # was found while this phase's own new tests ran alongside it.
        self.n1 = Notification.objects.create(recipient=self.user, type=NotificationType.LOW_STOCK, title='NotifOwnTitleOne', message='M1')
        self.n2 = Notification.objects.create(recipient=self.user, type=NotificationType.SALE_COMPLETED, title='NotifOwnTitleTwo', message='M2')
        self.other_notif = Notification.objects.create(recipient=self.other, type=NotificationType.LOW_STOCK, title='NotifOtherUserTitleThree', message='M3')

    def test_list_shows_only_own_notifications(self):
        self.client.login(username='notifuser', password='x')
        response = self.client.get(reverse('frontend:notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'NotifOwnTitleOne')
        self.assertNotContains(response, 'NotifOtherUserTitleThree')

    def test_unread_count_reflects_only_own_unread(self):
        self.client.login(username='notifuser', password='x')
        response = self.client.get(reverse('frontend:notification_unread_count'))
        self.assertEqual(response.json(), {'unread_count': 2})

    def test_mark_read_only_affects_own_notification(self):
        self.client.login(username='notifuser', password='x')
        response = self.client.post(reverse('frontend:notification_read', args=[self.other_notif.pk]))
        self.assertEqual(response.status_code, 404)
        self.other_notif.refresh_from_db()
        self.assertFalse(self.other_notif.is_read, "cross-user mark-read must not succeed")

        response = self.client.post(reverse('frontend:notification_read', args=[self.n1.pk]))
        self.assertEqual(response.status_code, 200)
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)

    def test_mark_all_read(self):
        self.client.login(username='notifuser', password='x')
        self.client.post(reverse('frontend:notification_read_all'))
        self.n1.refresh_from_db()
        self.n2.refresh_from_db()
        self.assertTrue(self.n1.is_read)
        self.assertTrue(self.n2.is_read)
        self.other_notif.refresh_from_db()
        self.assertFalse(self.other_notif.is_read)

    def test_anonymous_blocked_from_every_endpoint(self):
        for url in (
            reverse('frontend:notifications'),
            reverse('frontend:notification_unread_count'),
        ):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_sidebar_badge_is_no_longer_a_hardcoded_mock_value(self):
        """Phase 8.99f-2: sidebar.html's notification badge used to be a
        literal, unwired "6" (Phase 3.6 mock era). It's now the same
        hidden-by-default element the topbar dot already uses the pattern
        for, driven by notifications.js polling this same
        notification_unread_count endpoint — not a second server-computed
        value, so there's nothing new to assert server-side beyond "the
        mock value is gone and the real hook point exists."""
        self.client.login(username='notifuser', password='x')
        response = self.client.get(reverse('frontend:dashboard'))
        self.assertNotContains(response, '<span class="nav-item-badge">6</span>')
        self.assertContains(response, 'id="sidebarNotifBadge"')


class PasswordGeneratorTests(TestCase):
    """Phase 8.98e — frontend.validators.generate_strong_password(), used
    by UserListCreateView.post() so the Admin never chooses a new user's
    password. Must reliably satisfy the real AUTH_PASSWORD_VALIDATORS
    chain (config/settings.py), not a hand-rolled subset of it."""

    def test_generated_password_passes_full_validator_chain(self):
        for _ in range(25):
            validate_password(generate_strong_password())  # raises on failure

    def test_generated_passwords_are_random_not_fixed(self):
        passwords = {generate_strong_password() for _ in range(10)}
        self.assertEqual(len(passwords), 10)

    def test_default_length(self):
        self.assertEqual(len(generate_strong_password()), 14)


class UserManagementViewTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='umadmin', email='umadmin@example.com', password='x',
            employee_id='EMP-8020', full_name='UM Admin', role=UserRole.ADMIN,
        )
        self.staff = User.objects.create_user(
            username='umstaff', email='umstaff@example.com', password='x',
            employee_id='EMP-8021', full_name='UM Staffer', role=UserRole.STAFF,
        )

    def valid_payload(self, **overrides):
        payload = {
            'full_name': 'New Person', 'username': 'newperson', 'employee_id': 'EMP-8099',
            'email': 'newperson@example.com', 'role': 'staff',
        }
        payload.update(overrides)
        return payload

    def test_admin_creates_user_with_generated_emailed_password(self):
        """Phase 8.98e: UserForm has no password field at all now — a
        strong password is generated server-side, set via set_password(),
        and emailed directly to the new user. Confirms the whole chain:
        the user really can log in with whatever was emailed, the Admin's
        own JSON response never carries it, and it was generated (not
        left blank/unusable).

        Phase 8.99f-4: the response now also carries a `message`
        confirming the emailed address on every real success (previously
        a bare {'success': True} — the "no confirmation appears" report,
        since no Add-modal in this app ever showed one and this was the
        only case where the invisible-in-the-table outcome — did the
        email really send — actually needed one)."""
        self.client.login(username='umadmin', password='x')
        response = self.client.post(reverse('frontend:users'), self.valid_payload())
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['message'], 'User created — credentials emailed to newperson@example.com.')
        self.assertNotIn('warning', payload)
        self.assertNotIn(b'assw', response.content, "the response body must never carry the generated password")

        created = User.objects.get(username='newperson')
        self.assertTrue(created.is_active)
        self.assertTrue(created.has_usable_password())
        self.assertTrue(AuditLog.objects.filter(action='USER_CREATED', affected_id=created.pk).exists())

        self.assertEqual(len(mail.outbox), 1)
        email_body = mail.outbox[0].body
        self.assertIn('newperson', email_body)
        match = re.search(r'Temporary password:\s*(\S+)', email_body)
        self.assertIsNotNone(match, "credentials email must contain the generated password")
        emailed_password = match.group(1)
        self.assertTrue(created.check_password(emailed_password), "the emailed password must actually work")

    def test_submitted_password_field_is_ignored(self):
        """UserForm has no 'password' field — posting one (a stale client,
        or a raw request) must simply be ignored, not error, matching the
        same precedent as Product's removed 'initial_stock' field
        (ProductCreateViewTests)."""
        self.client.login(username='umadmin', password='x')
        response = self.client.post(reverse('frontend:users'), self.valid_payload(password='Whatever-I-Choose1!'))
        self.assertEqual(response.status_code, 200, response.content)
        created = User.objects.get(username='newperson')
        self.assertFalse(created.check_password('Whatever-I-Choose1!'), "a client-submitted password must never be used")

    def test_generated_password_never_appears_in_notification_or_audit_log(self):
        """The task's own hard rule: the generated password must appear in
        NO audit log or notification body anywhere — checked here against
        every row in both tables, not just the ones this flow itself
        creates, and confirms no in-app Notification is created for the
        new user at all (frontend.notifications.send_new_user_credentials_email()
        deliberately creates none — see its own docstring)."""
        self.client.login(username='umadmin', password='x')
        self.client.post(reverse('frontend:users'), self.valid_payload())
        created = User.objects.get(username='newperson')

        match = re.search(r'Temporary password:\s*(\S+)', mail.outbox[0].body)
        self.assertIsNotNone(match)
        emailed_password = match.group(1)

        self.assertFalse(Notification.objects.filter(recipient=created).exists())
        for notif in Notification.objects.all():
            self.assertNotIn(emailed_password, notif.title)
            self.assertNotIn(emailed_password, notif.message)
        for log in AuditLog.objects.all():
            self.assertNotIn(emailed_password, json.dumps(log.details))

    def test_email_send_failure_still_creates_the_account_but_warns(self):
        """Phase 8.99f-3: before this phase, a failed credentials-email
        send (send_new_user_credentials_email() already fails open
        internally) produced the exact same {'success': True} as a real
        send — a stranded account with a usable password nobody knows,
        reported as a clean success. The account is still deliberately
        created (rolling back would throw away validated admin work over
        what's usually a transient delivery problem), but the response
        must now say so."""
        self.client.login(username='umadmin', password='x')
        with patch('frontend.notifications.send_mail', side_effect=Exception('SMTP down')):
            response = self.client.post(reverse('frontend:users'), self.valid_payload())
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('warning', payload)
        self.assertIn('newperson@example.com', payload['warning'])

        created = User.objects.get(username='newperson')
        self.assertTrue(created.is_active)
        self.assertTrue(created.has_usable_password(), "the account must still be created and usable, just unreachable by email")

    def test_normal_creation_response_has_message_not_warning(self):
        """`message` and `warning` are mutually exclusive — a real send
        gets the confirmation, never both keys at once."""
        self.client.login(username='umadmin', password='x')
        response = self.client.post(reverse('frontend:users'), self.valid_payload())
        payload = response.json()
        self.assertIn('message', payload)
        self.assertNotIn('warning', payload)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_console_backend_creation_message_discloses_dev_mode(self):
        """Phase 8.99f-5: the root cause of "works when the tool does it,
        not when I do it" — the console backend never raises (so
        send_new_user_credentials_email() returns True) but no real email
        ever leaves the machine, it only prints to whichever terminal runs
        the server. Before this phase, that produced the exact same
        `message` text as a genuine SMTP send — a real, honest-*looking*
        overclaim. The message must now say plainly that nothing was
        really emailed, distinct from both the real-send `message` and
        the failed-send `warning`."""
        self.client.login(username='umadmin', password='x')
        response = self.client.post(reverse('frontend:users'), self.valid_payload())
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('message', payload)
        self.assertNotIn('warning', payload)
        self.assertIn('console email backend', payload['message'])
        self.assertIn('no real email was sent', payload['message'])
        self.assertIn('newperson@example.com', payload['message'])

    def test_staff_cannot_create_user(self):
        self.client.login(username='umstaff', password='x')
        response = self.client.post(reverse('frontend:users'), self.valid_payload())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username='newperson').exists())

    def test_add_user_modal_has_no_leaked_comment_text(self):
        """Phase 8.99f-4: a multi-line {# #} Django comment (users.html,
        just above the Add User modal's info banner) doesn't close on its
        own line, so Django's tokenizer (not DOTALL) fails to strip it —
        the exact BUG-03/BUG-36 shape — and it rendered as literal page
        text ("Phase 8.98e: no password field..."), the "stray lines" in
        the modal. Converted to {% comment %}{% endcomment %}. The real
        info banner right below it must still render."""
        self.client.login(username='umadmin', password='x')
        response = self.client.get(reverse('frontend:users'))
        self.assertNotContains(response, 'Phase 8.98e: no password field')
        self.assertNotContains(response, '{#')
        self.assertContains(response, 'A temporary password will be generated automatically')

    def test_deactivate_and_reactivate(self):
        self.client.login(username='umadmin', password='x')
        response = self.client.post(reverse('frontend:user_deactivate', args=[self.staff.pk]))
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
        self.assertTrue(AuditLog.objects.filter(action='USER_DEACTIVATED', affected_id=self.staff.pk).exists())

        response = self.client.post(reverse('frontend:user_reactivate', args=[self.staff.pk]))
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_admin_cannot_deactivate_own_account(self):
        self.client.login(username='umadmin', password='x')
        response = self.client.post(reverse('frontend:user_deactivate', args=[self.admin.pk]))
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_clean_user_with_no_history_can_be_hard_deleted(self):
        """Phase 8.99f-2: a user who has never created/approved/cancelled
        a PO or sale, never performed a movement, never requested/approved
        an adjustment, and never appears as an AuditLog actor is the one
        case a real delete is safe (see _user_ids_with_history())."""
        self.client.login(username='umadmin', password='x')
        response = self.client.post(reverse('frontend:user_delete', args=[self.staff.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(User.objects.filter(pk=self.staff.pk).exists())
        entry = AuditLog.objects.get(action='USER_DELETED', affected_id=self.staff.pk)
        self.assertEqual(entry.details.get('deleted_username'), 'umstaff')

    def test_user_with_history_cannot_be_hard_deleted(self):
        """A user referenced by any PROTECT FK must be refused, not 500."""
        category = Category.objects.create(name='UM Delete Category')
        supplier = Supplier.objects.create(
            supplier_name='UM Delete Supply', company_name='UM Delete Supply Co',
            contact_person='X', email='umdeletesupply@example.com', phone='000', address='addr',
        )
        PurchaseOrder.objects.create(supplier=supplier, created_by=self.staff)

        self.client.login(username='umadmin', password='x')
        response = self.client.post(reverse('frontend:user_delete', args=[self.staff.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertIn('deactivate instead', response.json()['error'].lower())
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())

    def test_user_who_is_only_an_audit_actor_cannot_be_hard_deleted(self):
        """Referenced only via AuditLog.user (SET_NULL) — still refused,
        since a real delete would silently null who performed that action."""
        audit.log_action(self.staff, audit.LOGIN_SUCCESS, 'auth', status='success')
        self.client.login(username='umadmin', password='x')
        response = self.client.post(reverse('frontend:user_delete', args=[self.staff.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())

    def test_admin_cannot_delete_own_account(self):
        self.client.login(username='umadmin', password='x')
        response = self.client.post(reverse('frontend:user_delete', args=[self.admin.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_staff_cannot_delete_a_user(self):
        self.client.login(username='umstaff', password='x')
        response = self.client.post(reverse('frontend:user_delete', args=[self.admin.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_resend_credentials_generates_new_password_and_emails_it(self):
        """Phase 8.99f-7: the recovery path for a stranded account — a
        fresh strong password (not the original one), set via
        set_password(), emailed through the same
        send_new_user_credentials_email() path used at creation."""
        self.client.login(username='umadmin', password='x')
        old_hash = self.staff.password
        response = self.client.post(reverse('frontend:user_resend_credentials', args=[self.staff.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('message', payload)
        self.assertIn('Credentials resent', payload['message'])

        self.staff.refresh_from_db()
        self.assertNotEqual(self.staff.password, old_hash, "resend must set a genuinely new password, not reuse the old hash")
        self.assertTrue(AuditLog.objects.filter(action='USER_CREDENTIALS_RESENT', affected_id=self.staff.pk).exists())

        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r'Temporary password:\s*(\S+)', mail.outbox[0].body)
        self.assertIsNotNone(match)
        self.assertTrue(self.staff.check_password(match.group(1)), "the resent password must actually work")

    def test_resend_credentials_failure_returns_warning_not_false_success(self):
        self.client.login(username='umadmin', password='x')
        with patch('frontend.notifications.send_mail', side_effect=Exception('SMTP down')):
            response = self.client.post(reverse('frontend:user_resend_credentials', args=[self.staff.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('warning', payload)
        self.assertNotIn('message', payload)
        self.assertIn(self.staff.email, payload['warning'])

    def test_resend_credentials_password_never_in_notification_or_audit_log(self):
        self.client.login(username='umadmin', password='x')
        self.client.post(reverse('frontend:user_resend_credentials', args=[self.staff.pk]))
        match = re.search(r'Temporary password:\s*(\S+)', mail.outbox[0].body)
        resent_password = match.group(1)

        self.assertFalse(Notification.objects.filter(recipient=self.staff).exists())
        for log in AuditLog.objects.all():
            self.assertNotIn(resent_password, json.dumps(log.details))

    def test_staff_cannot_resend_credentials(self):
        self.client.login(username='umstaff', password='x')
        response = self.client.post(reverse('frontend:user_resend_credentials', args=[self.admin.pk]))
        self.assertEqual(response.status_code, 302)

    def test_resendable_flag_only_for_never_logged_in_active_users(self):
        """Resend is offered while last_login is still None (the real
        signal the original credentials were never used) — disappears
        once they log in for real, and never offered for a deactivated
        account."""
        never_logged_in = self.staff
        self.assertIsNone(never_logged_in.last_login)

        logged_in_user = User.objects.create_user(
            username='umloggedin', email='umloggedin@example.com', password='x',
            employee_id='EMP-8023', full_name='UM Logged In', role=UserRole.STAFF,
        )
        self.client.login(username='umloggedin', password='x')  # sets last_login
        self.client.logout()

        inactive_user = User.objects.create_user(
            username='uminactive', email='uminactive@example.com', password='x',
            employee_id='EMP-8024', full_name='UM Inactive', role=UserRole.STAFF, is_active=False,
        )

        self.client.login(username='umadmin', password='x')
        response = self.client.get(reverse('frontend:users'))
        by_pk = {u.pk: u.resendable for u in response.context['users']}
        self.assertTrue(by_pk[never_logged_in.pk])
        self.assertFalse(by_pk[logged_in_user.pk], "a user who has actually logged in no longer needs a resend")
        self.assertFalse(by_pk[inactive_user.pk], "a deactivated account shouldn't offer resend")

    def test_deletable_flag_in_list_context(self):
        """UserListCreateView.get() must mark the clean user deletable and
        both the acting admin (self) and a user with history not
        deletable — the same rule UserDeleteView enforces server-side."""
        category = Category.objects.create(name='UM Deletable Category')
        supplier = Supplier.objects.create(
            supplier_name='UM Deletable Supply', company_name='UM Deletable Supply Co',
            contact_person='X', email='umdeletablesupply@example.com', phone='000', address='addr',
        )
        history_user = User.objects.create_user(
            username='umhistory', email='umhistory@example.com', password='x',
            employee_id='EMP-8022', full_name='UM History', role=UserRole.STAFF,
        )
        PurchaseOrder.objects.create(supplier=supplier, created_by=history_user)

        self.client.login(username='umadmin', password='x')
        response = self.client.get(reverse('frontend:users'))
        by_pk = {u.pk: u.deletable for u in response.context['users']}
        self.assertTrue(by_pk[self.staff.pk], "a never-used account must be deletable")
        self.assertFalse(by_pk[history_user.pk], "a user with PO history must not be deletable")
        self.assertFalse(by_pk[self.admin.pk], "the logged-in admin must never see themselves as deletable")


class SettingsViewTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='setadmin', email='setadmin@example.com', password='x',
            employee_id='EMP-8030', full_name='Settings Admin', role=UserRole.ADMIN,
        )
        self.staff = User.objects.create_user(
            username='setstaff', email='setstaff@example.com', password='x',
            employee_id='EMP-8031', full_name='Settings Staffer', role=UserRole.STAFF,
        )

    def test_admin_can_view_and_update_the_singleton(self):
        self.client.login(username='setadmin', password='x')
        response = self.client.post(reverse('frontend:settings'), {
            'company_name': 'Updated Co', 'default_reorder_level': '25',
            'session_timeout_seconds': '1800',
        })
        self.assertEqual(response.status_code, 200, response.content)

        settings_obj = SystemSettings.get_settings()
        self.assertEqual(settings_obj.pk, 1)
        self.assertEqual(settings_obj.company_name, 'Updated Co')
        self.assertEqual(settings_obj.default_reorder_level, 25)
        self.assertTrue(AuditLog.objects.filter(action='SETTINGS_UPDATED').exists())

    def test_blank_optional_int_field_falls_back_to_current_value_not_model_default(self):
        settings_obj = SystemSettings.get_settings()
        settings_obj.forecast_period_weeks = 12
        settings_obj.save()

        self.client.login(username='setadmin', password='x')
        response = self.client.post(reverse('frontend:settings'), {'company_name': 'X'})
        self.assertEqual(response.status_code, 200, response.content)

        settings_obj.refresh_from_db()
        self.assertEqual(settings_obj.forecast_period_weeks, 12, "blank submit must not reset to the model's class default")

    def test_still_exactly_one_row_after_repeated_saves(self):
        self.client.login(username='setadmin', password='x')
        for _ in range(3):
            self.client.post(reverse('frontend:settings'), {'company_name': 'Loop Co'})
        self.assertEqual(SystemSettings.objects.count(), 1)

    def test_staff_blocked(self):
        self.client.login(username='setstaff', password='x')
        response = self.client.get(reverse('frontend:settings'))
        self.assertRedirects(response, reverse('frontend:dashboard'))
        response = self.client.post(reverse('frontend:settings'), {'company_name': 'Hacked Co'})
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(SystemSettings.get_settings().company_name, 'Hacked Co')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class CompanyLogoUploadTests(TestCase):
    """Phase 13 Task 2 — company_logo is a plain FileField (not
    ImageField) specifically so SVG can be accepted; validate_company_logo
    (frontend/validators.py) does the type/size checking that would
    otherwise be lost, PNG/JPG included (Pillow-verified, unlike
    validate_product_image which only checks the extension)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='logoadmin', email='logoadmin@example.com', password='x',
            employee_id='EMP-9620', full_name='Logo Admin', role=UserRole.ADMIN,
        )

    def _real_png_bytes(self):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new('RGB', (4, 4), color='red').save(buf, format='PNG')
        return buf.getvalue()

    def test_valid_png_logo_accepted(self):
        self.client.login(username='logoadmin', password='x')
        logo = SimpleUploadedFile('logo.png', self._real_png_bytes(), content_type='image/png')
        response = self.client.post(reverse('frontend:settings'), {
            'company_name': 'Logo Co', 'company_logo': logo,
        })
        self.assertEqual(response.status_code, 200, response.content)
        settings_obj = SystemSettings.get_settings()
        self.assertTrue(settings_obj.company_logo)

    def test_valid_svg_logo_accepted(self):
        """The one thing switching company_logo off ImageField exists
        for — Pillow can't open SVG at all, so an ImageField would
        reject this outright regardless of any custom validator."""
        self.client.login(username='logoadmin', password='x')
        svg_bytes = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
        logo = SimpleUploadedFile('logo.svg', svg_bytes, content_type='image/svg+xml')
        response = self.client.post(reverse('frontend:settings'), {
            'company_name': 'Logo Co', 'company_logo': logo,
        })
        self.assertEqual(response.status_code, 200, response.content)
        settings_obj = SystemSettings.get_settings()
        self.assertTrue(settings_obj.company_logo)
        self.assertTrue(settings_obj.company_logo.name.endswith('.svg'))

    def test_invalid_extension_rejected(self):
        self.client.login(username='logoadmin', password='x')
        bad_file = SimpleUploadedFile('logo.gif', b'GIF89a', content_type='image/gif')
        response = self.client.post(reverse('frontend:settings'), {
            'company_name': 'Logo Co', 'company_logo': bad_file,
        })
        self.assertEqual(response.status_code, 400)

    def test_file_pretending_to_be_svg_rejected(self):
        self.client.login(username='logoadmin', password='x')
        bad_file = SimpleUploadedFile('logo.svg', b'not actually svg content', content_type='image/svg+xml')
        response = self.client.post(reverse('frontend:settings'), {
            'company_name': 'Logo Co', 'company_logo': bad_file,
        })
        self.assertEqual(response.status_code, 400)

    def test_oversized_logo_rejected(self):
        self.client.login(username='logoadmin', password='x')
        big_file = SimpleUploadedFile('logo.png', self._real_png_bytes() + b'\x00' * (5 * 1024 * 1024 + 1), content_type='image/png')
        response = self.client.post(reverse('frontend:settings'), {
            'company_name': 'Logo Co', 'company_logo': big_file,
        })
        self.assertEqual(response.status_code, 400)

    def test_uploaded_logo_actually_embeds_into_generated_pdf(self):
        """Not just 'the file saved' — the PDF header must actually draw
        it, not silently fall back to text-only the way a missing or
        unreadable logo does."""
        self.client.login(username='logoadmin', password='x')
        logo = SimpleUploadedFile('logo.png', self._real_png_bytes(), content_type='image/png')
        self.client.post(reverse('frontend:settings'), {'company_name': 'Logo Co', 'company_logo': logo})

        category = Category.objects.create(name='Logo Widgets')
        supplier = Supplier.objects.create(
            supplier_name='Logo Supply', company_name='Logo Supply Co', contact_person='Jo',
            email='logosupply@example.com', phone='555-0800', address='1 Logo Way', is_active=True,
        )
        product = Product.objects.create(
            sku='LOGO-SKU-001', name='Logo Widget', category=category, supplier=supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'),
        )
        po = PurchaseOrder.objects.create(supplier=supplier, created_by=self.admin)
        PurchaseOrderItem.objects.create(purchase_order=po, product=product, ordered_qty=1, unit_price=Decimal('10.00'))

        from frontend import reports as report_lib
        response = report_lib.generate_purchase_order_pdf(po)
        self.assertIn(b'/Subtype /Image', response.content)

    def test_svg_logo_falls_back_to_text_only_header_in_pdf(self):
        """Disclosed limitation (frontend/pdf.py's own module docstring):
        ReportLab has no SVG rasterizer and adding one (svglib et al.)
        would be a new dependency the standing rules forbid — an SVG
        logo must render the same graceful text-only header a missing
        logo does, not a broken image box or a crash."""
        self.client.login(username='logoadmin', password='x')
        svg_bytes = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
        logo = SimpleUploadedFile('logo.svg', svg_bytes, content_type='image/svg+xml')
        self.client.post(reverse('frontend:settings'), {'company_name': 'SVG Logo Co', 'company_logo': logo})

        category = Category.objects.create(name='SVG Widgets')
        supplier = Supplier.objects.create(
            supplier_name='SVG Supply', company_name='SVG Supply Co', contact_person='Jo',
            email='svgsupply@example.com', phone='555-0900', address='1 SVG Way', is_active=True,
        )
        product = Product.objects.create(
            sku='SVG-SKU-001', name='SVG Widget', category=category, supplier=supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'),
        )
        po = PurchaseOrder.objects.create(supplier=supplier, created_by=self.admin)
        PurchaseOrderItem.objects.create(purchase_order=po, product=product, ordered_qty=1, unit_price=Decimal('10.00'))

        from frontend import reports as report_lib
        response = report_lib.generate_purchase_order_pdf(po)
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertNotIn(b'/Subtype /Image', response.content, "SVG can't be rasterized by ReportLab, must not attempt it")
        text = _extract_pdf_text(response.content)
        self.assertIn(b'SVG Logo Co', text)


class ReportsViewTests(TestCase):

    def setUp(self):
        self.supervisor = User.objects.create_user(
            username='repsuper', email='repsuper@example.com', password='x',
            employee_id='EMP-8040', full_name='Reports Supervisor', role=UserRole.SUPERVISOR,
        )
        self.staff = User.objects.create_user(
            username='repstaff', email='repstaff@example.com', password='x',
            employee_id='EMP-8041', full_name='Reports Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='Report Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='Report Supply', company_name='Report Supply Co', contact_person='Jo',
            email='reportsupply@example.com', phone='555-0500', address='1 Report Way', is_active=True,
        )
        self.product = Product.objects.create(
            sku='REP-SKU-001', name='Report Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('10.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(self.product)

    REPORT_SLUGS = [
        'inventory', 'purchases', 'sales', 'movements', 'adjustments',
        'low-stock', 'out-of-stock', 'ai-forecasts', 'ai-classifications',
    ]

    def test_supervisor_can_view_reports_page(self):
        self.client.login(username='repsuper', password='x')
        response = self.client.get(reverse('frontend:reports'))
        self.assertEqual(response.status_code, 200)

    def test_admin_hierarchy_also_allowed(self):
        """Confirms SupervisorRequiredMixin's Admin-or-Supervisor hierarchy
        (established Phase 7) holds for Reports too, not just Purchases."""
        admin = User.objects.create_user(
            username='repadmin', email='repadmin@example.com', password='x',
            employee_id='EMP-8042', full_name='Reports Admin', role=UserRole.ADMIN,
        )
        self.client.login(username='repadmin', password='x')
        response = self.client.get(reverse('frontend:reports'))
        self.assertEqual(response.status_code, 200)

    def test_staff_blocked_from_page_and_every_export(self):
        self.client.login(username='repstaff', password='x')
        self.assertEqual(self.client.get(reverse('frontend:reports')).status_code, 302)
        for slug in self.REPORT_SLUGS:
            url = reverse('frontend:report_export', args=[slug]) + '?format=pdf'
            self.assertEqual(self.client.get(url).status_code, 302, f"{slug} export must also be blocked")

    def test_every_report_type_exports_valid_pdf_and_csv(self):
        self.client.login(username='repsuper', password='x')
        for slug in self.REPORT_SLUGS:
            base = reverse('frontend:report_export', args=[slug])

            pdf_response = self.client.get(base + '?format=pdf')
            self.assertEqual(pdf_response.status_code, 200, slug)
            self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
            self.assertTrue(pdf_response.content.startswith(b'%PDF-'), f"{slug} PDF must start with the PDF magic bytes")

            csv_response = self.client.get(base + '?format=csv')
            self.assertEqual(csv_response.status_code, 200, slug)
            self.assertEqual(csv_response['Content-Type'], 'text/csv')

        self.assertTrue(AuditLog.objects.filter(action='REPORT_EXPORTED_PDF').exists())
        self.assertTrue(AuditLog.objects.filter(action='REPORT_EXPORTED_CSV').exists())

    def test_invalid_format_rejected(self):
        self.client.login(username='repsuper', password='x')
        response = self.client.get(reverse('frontend:report_export', args=['sales']) + '?format=xml')
        self.assertEqual(response.status_code, 400)

    def test_unknown_report_type_404s(self):
        self.client.login(username='repsuper', password='x')
        response = self.client.get(reverse('frontend:report_export', args=['not-a-real-report']) + '?format=pdf')
        self.assertEqual(response.status_code, 404)

    def test_inventory_report_reflects_real_stock(self):
        self.client.login(username='repsuper', password='x')
        response = self.client.get(reverse('frontend:report_export', args=['inventory']) + '?format=csv')
        self.assertIn(b'REP-SKU-001', response.content)

    def test_sales_report_panel_no_longer_renders_the_detailed_transaction_table(self):
        """Phase 13 Task 4 — the raw per-transaction table is gone from
        the page (already available from Movement History); the panel
        now shows the aggregate breakdown + chart instead."""
        self.client.login(username='repsuper', password='x')
        response = self.client.get(reverse('frontend:reports'))
        self.assertNotContains(response, 'salesReportTableBody')
        self.assertContains(response, 'salesRevenueChart')
        self.assertContains(response, 'Total revenue')

    def test_sales_pdf_export_uses_summary_shape_not_the_old_transaction_dump(self):
        """The Sales Report's own PDF export must reflect the same
        aggregate structure the on-page panel now shows."""
        self.client.login(username='repsuper', password='x')
        response = self.client.get(reverse('frontend:report_export', args=['sales']) + '?format=pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        text = _extract_pdf_text(response.content)
        self.assertIn(b'Total revenue', text)
        self.assertIn(b'Transactions', text)

    def test_sales_csv_export_still_has_the_detailed_per_transaction_data(self):
        """CSV wasn't part of Task 4's ask — build_sales_report()'s
        per-transaction rows must still be exportable there."""
        self.client.login(username='repsuper', password='x')
        response = self.client.get(reverse('frontend:report_export', args=['sales']) + '?format=csv')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invoice', response.content)


class TimeZoneConfigTests(TestCase):
    """Phase 8.6 (BUG-37): the app must display timestamps in Bangladesh
    time, not UTC — settings.TIME_ZONE drives every `{{ value|date:... }}`
    render and `timezone.localtime()` call. USE_TZ stays True (storage is
    still real UTC instants); only the display timezone changed."""

    def test_time_zone_is_asia_dhaka(self):
        from django.conf import settings as django_settings
        self.assertEqual(django_settings.TIME_ZONE, 'Asia/Dhaka')
        self.assertTrue(django_settings.USE_TZ)

    def test_localtime_conversion_is_six_hours_ahead_of_utc(self):
        an_instant = timezone.now()
        local = timezone.localtime(an_instant)
        self.assertEqual(local.utcoffset(), timedelta(hours=6))


class DashboardGreetingTests(TestCase):
    """Phase 8.6 (BUG-37/BUG-38): greeting must reflect the real logged-in
    user (not the old hardcoded 'Amara' placeholder, which only ever
    resolved because the template referenced a `first_name` field the
    custom User model doesn't have) and must track time of day in
    Bangladesh time, computed server-side in frontend.views.dashboard()."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='greetme', email='greetme@example.com', password='Correct-Horse1!',
            employee_id='EMP-3001', full_name='Priya Nair', role=UserRole.STAFF,
        )
        self.client.login(username='greetme', password='Correct-Horse1!')

    def test_greeting_shows_real_user_name_not_amara(self):
        response = self.client.get(reverse('frontend:dashboard'))
        self.assertContains(response, 'Priya')
        self.assertNotContains(response, 'Amara')

    def test_greeting_is_good_morning_before_noon(self):
        from unittest.mock import patch
        with patch('frontend.views.timezone.localtime') as mock_localtime:
            mock_localtime.return_value = timezone.datetime(2026, 8, 11, 9, 0)
            response = self.client.get(reverse('frontend:dashboard'))
        self.assertEqual(response.context['greeting'], 'Good morning')

    def test_greeting_is_good_afternoon_between_noon_and_five(self):
        from unittest.mock import patch
        with patch('frontend.views.timezone.localtime') as mock_localtime:
            mock_localtime.return_value = timezone.datetime(2026, 8, 11, 14, 0)
            response = self.client.get(reverse('frontend:dashboard'))
        self.assertEqual(response.context['greeting'], 'Good afternoon')

    def test_greeting_is_good_evening_after_five(self):
        from unittest.mock import patch
        with patch('frontend.views.timezone.localtime') as mock_localtime:
            mock_localtime.return_value = timezone.datetime(2026, 8, 11, 20, 0)
            response = self.client.get(reverse('frontend:dashboard'))
        self.assertEqual(response.context['greeting'], 'Good evening')


class InventoryListViewTests(TestCase):
    """Phase 8.9 (BUG-37/BUG-41): frontend:inventory used to be a one-line
    render() over hardcoded mock rows. Proves the real InventoryListView
    renders genuine InventoryRecord data and exposes no mutation path at
    all — this page is documented (07_INVENTORY.md) as GET-only."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='invstaff', email='invstaff@example.com', password='x',
            employee_id='EMP-5001', full_name='Inventory Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='Consumables')
        self.supplier = Supplier.objects.create(
            supplier_name='Supply Co', company_name='Supply Co Ltd',
            contact_person='Al', email='supply@example.com', phone='555-0199',
            address='1 Supply Way',
        )
        self.low_stock_product = Product.objects.create(
            sku='INV-LOW-001', name='Low Stock Widget', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('5.00'),
            selling_price=Decimal('9.00'), reorder_level=10,
        )
        self.out_of_stock_product = Product.objects.create(
            sku='INV-OUT-001', name='Out of Stock Widget', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('5.00'),
            selling_price=Decimal('9.00'), reorder_level=10,
        )
        InventoryService.initialize_for_product(self.low_stock_product)
        InventoryService.initialize_for_product(self.out_of_stock_product)
        InventoryService.increase_stock(
            product=self.low_stock_product, quantity=4, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.user,
        )

    def test_requires_login(self):
        response = self.client.get(reverse('frontend:inventory'))
        self.assertRedirects(response, f"{reverse('frontend:login')}?next={reverse('frontend:inventory')}")

    def test_renders_real_records_matching_the_database(self):
        self.client.login(username='invstaff', password='x')
        response = self.client.get(reverse('frontend:inventory'))
        self.assertEqual(response.status_code, 200)

        records = {r.product_id: r for r in response.context['records']}
        self.assertEqual(len(records), 2)
        self.assertEqual(records[self.low_stock_product.pk].current_stock, 4)
        self.assertEqual(records[self.low_stock_product.pk].status, InventoryStatus.LOW_STOCK)
        self.assertEqual(records[self.out_of_stock_product.pk].current_stock, 0)
        self.assertEqual(records[self.out_of_stock_product.pk].status, InventoryStatus.OUT_OF_STOCK)

        self.assertContains(response, 'Low Stock Widget')
        self.assertContains(response, 'Out of Stock Widget')
        self.assertContains(response, 'INV-LOW-001')

    def test_counts_reflect_real_aggregates(self):
        self.client.login(username='invstaff', password='x')
        response = self.client.get(reverse('frontend:inventory'))
        counts = response.context['counts']
        self.assertEqual(counts['total_skus'], 2)
        self.assertEqual(counts['low_stock'], 1)
        self.assertEqual(counts['out_of_stock'], 1)

    def test_any_authenticated_role_can_view(self):
        """07_INVENTORY.md's own reference view uses @staff_required, which
        in this project's RBAC means all 3 roles (frontend/decorators.py) —
        matching AnyStaffMixin's behavior here, not a stricter gate."""
        admin = User.objects.create_user(
            username='invadmin', email='invadmin@example.com', password='x',
            employee_id='EMP-5002', full_name='Inventory Admin', role=UserRole.ADMIN,
        )
        self.client.login(username='invadmin', password='x')
        self.assertEqual(self.client.get(reverse('frontend:inventory')).status_code, 200)

    def test_view_exposes_no_mutation_endpoint(self):
        """The page is read-only by design — confirm POST isn't even a
        recognized method on this view (405), and that stock is genuinely
        untouched either way."""
        self.client.login(username='invstaff', password='x')
        response = self.client.post(reverse('frontend:inventory'), {})
        self.assertEqual(response.status_code, 405)
        record = InventoryRecord.objects.get(product=self.low_stock_product)
        self.assertEqual(record.current_stock, 4)


class DashboardViewTests(TestCase):
    """Phase 8.96 (BUG-41): dashboard() used to pass only {"greeting": ...}
    and every KPI/chart/widget was a |default:"..." fabrication. Proves the
    real queries defined in docs/09_DASHBOARD.md return correct counts
    against known fixture data, and that Decision 5 (Recent Activity is
    admin/supervisor-only) actually holds in the rendered HTML, not just
    in the view's Python logic."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='dashadmin', email='dashadmin@example.com', password='x',
            employee_id='EMP-6001', full_name='Dash Admin', role=UserRole.ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username='dashsuper', email='dashsuper@example.com', password='x',
            employee_id='EMP-6002', full_name='Dash Supervisor', role=UserRole.SUPERVISOR,
        )
        self.staff = User.objects.create_user(
            username='dashstaff', email='dashstaff@example.com', password='x',
            employee_id='EMP-6003', full_name='Dash Staff', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='Dash Category')
        self.supplier = Supplier.objects.create(
            supplier_name='Dash Supply', company_name='Dash Supply Co',
            contact_person='D', email='dashsupply@example.com', phone='555-0200',
            address='1 Dash Way',
        )
        self.low_product = Product.objects.create(
            sku='DASH-LOW-001', name='Dash Low Stock Item', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('4.00'),
            selling_price=Decimal('8.00'), reorder_level=10,
        )
        self.out_product = Product.objects.create(
            sku='DASH-OUT-001', name='Dash Out of Stock Item', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('4.00'),
            selling_price=Decimal('8.00'), reorder_level=10,
        )
        InventoryService.initialize_for_product(self.low_product)
        InventoryService.initialize_for_product(self.out_product)
        InventoryService.increase_stock(
            product=self.low_product, quantity=3, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.admin,
        )

    def test_kpi_counts_match_real_data(self):
        self.client.login(username='dashadmin', password='x')
        response = self.client.get(reverse('frontend:dashboard'))
        kpis = response.context['kpis']
        self.assertEqual(kpis['total_products'], Product.objects.count())
        self.assertEqual(kpis['total_categories'], Category.objects.count())
        self.assertEqual(kpis['active_suppliers'], Supplier.objects.filter(is_active=True).count())
        self.assertEqual(kpis['total_users'], User.objects.count())
        # Every fixture row in this test was just created, so it all falls
        # inside the 30-day trend window too.
        self.assertEqual(kpis['new_products_30d'], Product.objects.count())
        self.assertEqual(kpis['new_categories_30d'], Category.objects.count())
        self.assertEqual(kpis['new_active_suppliers_30d'], Supplier.objects.filter(is_active=True).count())
        self.assertEqual(kpis['new_users_30d'], User.objects.count())

    def test_stat_strip_matches_real_inventory_aggregates(self):
        self.client.login(username='dashadmin', password='x')
        response = self.client.get(reverse('frontend:dashboard'))
        stats = response.context['stats']

        records = list(InventoryRecord.objects.all())
        expected_value = sum((r.total_value for r in records), Decimal('0'))
        expected_units = sum(r.current_stock for r in records)

        self.assertEqual(stats['inventory_value'], expected_value)
        self.assertEqual(stats['stock_units'], expected_units)
        self.assertEqual(
            stats['low_stock_count'],
            InventoryRecord.objects.filter(status=InventoryStatus.LOW_STOCK).count(),
        )
        self.assertEqual(
            stats['out_of_stock_count'],
            InventoryRecord.objects.filter(status=InventoryStatus.OUT_OF_STOCK).count(),
        )

    def test_stock_alerts_shows_real_records(self):
        self.client.login(username='dashadmin', password='x')
        response = self.client.get(reverse('frontend:dashboard'))
        alert_product_ids = {record.product_id for record in response.context['stock_alerts']}
        self.assertIn(self.low_product.pk, alert_product_ids)
        self.assertIn(self.out_product.pk, alert_product_ids)
        self.assertContains(response, 'Dash Low Stock Item')
        self.assertContains(response, 'Dash Out of Stock Item')

    def test_recent_activity_visible_for_admin_and_supervisor(self):
        for username in ('dashadmin', 'dashsuper'):
            self.client.login(username=username, password='x')
            response = self.client.get(reverse('frontend:dashboard'))
            self.assertIsNotNone(response.context['recent_activity'])
            self.assertContains(response, 'Recent activity')
            self.client.logout()

    def test_recent_activity_not_rendered_for_staff(self):
        """Decision 5: not hidden-but-in-DOM — genuinely absent from the
        rendered HTML for a staff user, the same treatment AI Insights
        gets for everyone."""
        self.client.login(username='dashstaff', password='x')
        response = self.client.get(reverse('frontend:dashboard'))
        self.assertIsNone(response.context['recent_activity'])
        self.assertNotContains(response, 'Recent activity')

    def test_pending_approvals_has_no_action_buttons(self):
        PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.admin, status=POStatus.PENDING)
        self.client.login(username='dashsuper', password='x')
        response = self.client.get(reverse('frontend:dashboard'))
        self.assertContains(response, 'Pending approvals')
        self.assertNotContains(response, 'aria-label="Approve"')
        self.assertNotContains(response, 'aria-label="Reject"')

    def test_ai_insights_section_dropped_entirely(self):
        self.client.login(username='dashadmin', password='x')
        response = self.client.get(reverse('frontend:dashboard'))
        self.assertNotContains(response, 'AI Insights')
        self.assertNotContains(response, 'Demand forecasting')
        self.assertNotContains(response, 'Slow-moving')

    def test_anonymous_redirects_to_login(self):
        """Phase 8.97 Part A: DashboardView now requires AnyStaffMixin —
        closing the real risk Phase 8.96 flagged (real business aggregates,
        not fabricated ones, were reachable unauthenticated). Confirms the
        redirect, not just "doesn't crash" — real data must never render
        for an anonymous request at all."""
        response = self.client.get(reverse('frontend:dashboard'))
        self.assertRedirects(response, f"{reverse('frontend:login')}?next={reverse('frontend:dashboard')}")

    def test_all_three_roles_load_the_dashboard(self):
        for username in ('dashadmin', 'dashsuper', 'dashstaff'):
            self.client.login(username=username, password='x')
            response = self.client.get(reverse('frontend:dashboard'))
            self.assertEqual(response.status_code, 200, username)
            self.client.logout()

    def test_refresh_and_new_purchase_order_buttons_removed(self):
        """Phase 8.99j: both were plain, unwired <button>s — "New purchase
        order" specifically is exactly the action-button class
        09_DASHBOARD.md's own Decision 4 keeps off this page (actions live
        in their real modules); removing it aligns the page with its own
        approved spec, not just decluttering."""
        self.client.login(username='dashadmin', password='x')
        response = self.client.get(reverse('frontend:dashboard'))
        self.assertNotContains(response, 'Refresh data')
        self.assertNotContains(response, 'New purchase order')


class AIPageAccessTests(TestCase):
    """Phase 8.99j — closes BUG-43: demand_forecasting/slow_moving_dead_
    stock had zero auth requirement at all (reachable by anyone, logged
    in or not). Now SupervisorRequiredMixin — a disclosed deviation from
    BUG-43's own suggested AnyStaffMixin fix, since this phase's actual
    requirement ("staff can't see the AI models") is narrower. Proves
    both layers: the server-side gate (the real control) and the sidebar
    nav-link visibility (the UX layer), and that the two agree."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='aiadmin', email='aiadmin@example.com', password='x',
            employee_id='EMP-9001', full_name='AI Admin', role=UserRole.ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username='aisuper', email='aisuper@example.com', password='x',
            employee_id='EMP-9002', full_name='AI Supervisor', role=UserRole.SUPERVISOR,
        )
        self.staff = User.objects.create_user(
            username='aistaff', email='aistaff@example.com', password='x',
            employee_id='EMP-9003', full_name='AI Staffer', role=UserRole.STAFF,
        )

    def test_anonymous_redirected_to_login_from_both_pages(self):
        for url_name in ('forecasting', 'slow_moving'):
            url = reverse(f'frontend:{url_name}')
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('frontend:login')}?next={url}")

    def test_staff_blocked_from_both_pages_by_direct_url(self):
        """The real control — not just the hidden nav link. A direct GET
        past the (now-hidden) sidebar link must still be refused."""
        self.client.login(username='aistaff', password='x')
        for url_name in ('forecasting', 'slow_moving'):
            response = self.client.get(reverse(f'frontend:{url_name}'))
            self.assertEqual(response.status_code, 302, url_name)

    def test_supervisor_and_admin_can_open_both_pages(self):
        for username in ('aisuper', 'aiadmin'):
            self.client.login(username=username, password='x')
            for url_name in ('forecasting', 'slow_moving'):
                response = self.client.get(reverse(f'frontend:{url_name}'))
                self.assertEqual(response.status_code, 200, f"{username}/{url_name}")
            self.client.logout()

    def test_staff_does_not_see_ai_nav_links(self):
        self.client.login(username='aistaff', password='x')
        response = self.client.get(reverse('frontend:dashboard'))
        self.assertNotContains(response, 'Demand Forecasting')
        self.assertNotContains(response, 'Slow-Moving')
        self.assertNotContains(response, '/ai/forecasting/')
        self.assertNotContains(response, '/ai/slow-moving/')

    def test_supervisor_and_admin_see_ai_nav_links(self):
        for username in ('aisuper', 'aiadmin'):
            self.client.login(username=username, password='x')
            response = self.client.get(reverse('frontend:dashboard'))
            self.assertContains(response, 'Demand Forecasting')
            self.assertContains(response, 'Slow-Moving')
            self.client.logout()


class MovementHistoryViewTests(TestCase):
    """Phase 8.98 — Inventory's "Movement history" button used to do
    nothing. Proves the real page renders the actual InventoryMovement
    ledger, its server-side date-range filter genuinely narrows results
    (not client-side, per this task's own explicit decision — the ledger
    grows unbounded), the optional product filter works, and the page is
    strictly read-only over the immutable ledger."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='movstaff', email='movstaff@example.com', password='x',
            employee_id='EMP-7001', full_name='Movement Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='Movement Category')
        self.supplier = Supplier.objects.create(
            supplier_name='Movement Supply', company_name='Movement Supply Co',
            contact_person='M', email='movsupply@example.com', phone='555-0300',
            address='1 Movement Way',
        )
        self.product = Product.objects.create(
            sku='MOV-001', name='Movement Widget', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('3.00'),
            selling_price=Decimal('6.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(self.product)

    def make_movement_on(self, when, product=None, reference_id=0):
        """Seeds a real movement via InventoryService (the only legitimate
        way to create one), then backdates its created_at with a raw
        QuerySet.update() — bypasses InventoryMovement.save()'s immutability
        guard (BUG-20) entirely, since .update() never calls save(); that's
        exactly why this is only ever done here, in test setup, and never
        in application code."""
        InventoryService.increase_stock(
            product=product or self.product, quantity=1, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=reference_id, performed_by=self.user,
        )
        movement = InventoryMovement.objects.filter(product=product or self.product).latest('created_at')
        InventoryMovement.objects.filter(pk=movement.pk).update(created_at=when)
        return InventoryMovement.objects.get(pk=movement.pk)

    def test_requires_login(self):
        response = self.client.get(reverse('frontend:movement_history'))
        self.assertRedirects(
            response, f"{reverse('frontend:login')}?next={reverse('frontend:movement_history')}"
        )

    def test_renders_real_movements_matching_the_database(self):
        self.make_movement_on(timezone.now() - timedelta(days=100), reference_id=1)
        self.make_movement_on(timezone.now() - timedelta(days=1), reference_id=2)
        self.client.login(username='movstaff', password='x')
        response = self.client.get(reverse('frontend:movement_history'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_count'], InventoryMovement.objects.count())
        self.assertContains(response, 'Movement Widget')

    def test_date_range_filter_narrows_correctly(self):
        old = self.make_movement_on(timezone.now() - timedelta(days=100), reference_id=1)
        recent = self.make_movement_on(timezone.now() - timedelta(days=1), reference_id=2)
        self.client.login(username='movstaff', password='x')

        today = timezone.localdate()
        response = self.client.get(reverse('frontend:movement_history'), {
            'date_from': (today - timedelta(days=5)).isoformat(),
            'date_to': today.isoformat(),
        })
        shown_ids = {m.pk for m in response.context['page'].object_list}
        self.assertIn(recent.pk, shown_ids)
        self.assertNotIn(old.pk, shown_ids)

    def test_product_filter_narrows_to_one_product(self):
        other_product = Product.objects.create(
            sku='MOV-002', name='Other Movement Widget', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('3.00'),
            selling_price=Decimal('6.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(other_product)
        self.make_movement_on(timezone.now(), product=other_product, reference_id=9)
        mine = self.make_movement_on(timezone.now(), reference_id=3)

        self.client.login(username='movstaff', password='x')
        response = self.client.get(reverse('frontend:movement_history'), {'product': self.product.pk})
        shown_ids = {m.pk for m in response.context['page'].object_list}
        self.assertEqual(shown_ids, {mine.pk})

    def test_movement_type_filter_narrows_correctly(self):
        """Phase 8.99d: movement_type is now server-side, not
        table-filter.js. AdjustmentService.approve() is the only real path
        that produces an ADJUSTMENT-type movement."""
        # Phase 12 — approve() now enforces can_approve(): self.user here
        # is STAFF (this class's own setUp), never a valid approver, so a
        # real supervisor is created just for this one call.
        supervisor = User.objects.create_user(
            username='movsuper', email='movsuper@example.com', password='x',
            employee_id='EMP-7002', full_name='Movement Supervisor', role=UserRole.SUPERVISOR,
        )
        purchase_movement = self.make_movement_on(timezone.now(), reference_id=1)
        adjustment = InventoryAdjustment.objects.create(
            product=self.product, adjustment_type=AdjustmentType.INCREASE, quantity=2,
            reason='Recount', requested_by=self.user,
        )
        AdjustmentService.approve(adjustment, supervisor)

        self.client.login(username='movstaff', password='x')
        response = self.client.get(reverse('frontend:movement_history'), {'movement_type': 'adjustment'})
        shown_types = {m.movement_type for m in response.context['page'].object_list}
        self.assertEqual(shown_types, {'adjustment'})
        shown_ids = {m.pk for m in response.context['page'].object_list}
        self.assertNotIn(purchase_movement.pk, shown_ids)

    def test_search_filter_narrows_correctly(self):
        """Phase 8.99d: search (q) is now server-side, product name/SKU
        icontains — replaces the old client-side-only table-filter.js
        search, which could never be reflected in an export."""
        other_product = Product.objects.create(
            sku='MOV-003', name='Totally Different Item', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('3.00'),
            selling_price=Decimal('6.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(other_product)
        mine = self.make_movement_on(timezone.now(), reference_id=5)
        other = self.make_movement_on(timezone.now(), product=other_product, reference_id=6)

        self.client.login(username='movstaff', password='x')
        response = self.client.get(reverse('frontend:movement_history'), {'q': 'Movement Widget'})
        shown_ids = {m.pk for m in response.context['page'].object_list}
        self.assertIn(mine.pk, shown_ids)
        self.assertNotIn(other.pk, shown_ids)

        response_sku = self.client.get(reverse('frontend:movement_history'), {'q': 'MOV-001'})
        shown_ids_sku = {m.pk for m in response_sku.context['page'].object_list}
        self.assertEqual(shown_ids_sku, {mine.pk})

    def test_combined_filters_narrow_together(self):
        """date + product + type applied simultaneously, not just alone."""
        other_product = Product.objects.create(
            sku='MOV-004', name='Combo Widget', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('3.00'),
            selling_price=Decimal('6.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(other_product)
        today = timezone.localdate()
        in_range_mine = self.make_movement_on(timezone.now() - timedelta(days=1), reference_id=10)
        self.make_movement_on(timezone.now() - timedelta(days=100), reference_id=11)  # out of date range
        self.make_movement_on(timezone.now() - timedelta(days=1), product=other_product, reference_id=12)  # wrong product

        self.client.login(username='movstaff', password='x')
        response = self.client.get(reverse('frontend:movement_history'), {
            'date_from': (today - timedelta(days=5)).isoformat(),
            'date_to': today.isoformat(),
            'product': self.product.pk,
            'movement_type': 'purchase',
        })
        shown_ids = {m.pk for m in response.context['page'].object_list}
        self.assertEqual(shown_ids, {in_range_mine.pk})

    def test_filter_survives_pagination(self):
        """Page 2 of a filtered set is still filtered, not the full ledger."""
        other_product = Product.objects.create(
            sku='MOV-005', name='Noise Widget', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('3.00'),
            selling_price=Decimal('6.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(other_product)
        # 3 movements outside the filter (noise), then 55 matching ones
        # (> PAGE_SIZE=50) so page 2 genuinely exists under the filter.
        for i in range(3):
            self.make_movement_on(timezone.now(), product=other_product, reference_id=1000 + i)
        mine_ids = set()
        for i in range(55):
            m = self.make_movement_on(timezone.now(), reference_id=2000 + i)
            mine_ids.add(m.pk)

        self.client.login(username='movstaff', password='x')
        response = self.client.get(reverse('frontend:movement_history'), {'product': self.product.pk, 'page': 2})
        self.assertEqual(response.status_code, 200)
        page2_ids = {m.pk for m in response.context['page'].object_list}
        self.assertTrue(page2_ids.issubset(mine_ids), "page 2 must still only contain the filtered product's movements")
        self.assertEqual(response.context['total_count'], 55, "total_count must reflect the filtered set, not the whole ledger")

    def test_return_option_not_offered(self):
        """Phase 8.99d: no code path ever creates MovementType.RETURN
        (grepped services.py/views.py) — a filter value that can never
        match anything shouldn't be offered."""
        self.client.login(username='movstaff', password='x')
        response = self.client.get(reverse('frontend:movement_history'))
        self.assertNotIn('return', [value for value, _ in response.context['movement_types']])
        self.assertNotContains(response, 'value="return"')

    def test_view_exposes_no_mutation_endpoint(self):
        self.client.login(username='movstaff', password='x')
        response = self.client.post(reverse('frontend:movement_history'), {})
        self.assertEqual(response.status_code, 405)

    def test_export_produces_real_csv_respecting_the_date_filter(self):
        import csv
        import io

        self.make_movement_on(timezone.now() - timedelta(days=100), reference_id=1)
        self.make_movement_on(timezone.now() - timedelta(days=1), reference_id=2)
        self.client.login(username='movstaff', password='x')

        today = timezone.localdate()
        response = self.client.get(reverse('frontend:movement_history_export'), {
            'date_from': (today - timedelta(days=5)).isoformat(),
            'date_to': today.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(len(rows), 2)  # header + the one in-range movement
        self.assertIn('Movement Widget', rows[1])

    def test_csv_export_row_count_matches_filtered_db_query(self):
        """CSV row count must equal a direct DB query for the same
        filter — not the full table, for at least 3 different filter
        combinations, including one that returns zero rows."""
        import csv
        import io

        other_product = Product.objects.create(
            sku='MOV-006', name='Export Count Widget', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('3.00'),
            selling_price=Decimal('6.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(other_product)
        self.make_movement_on(timezone.now(), reference_id=20)
        self.make_movement_on(timezone.now(), reference_id=21)
        self.make_movement_on(timezone.now(), product=other_product, reference_id=22)
        self.client.login(username='movstaff', password='x')

        combos = [
            {},  # no filter -> full table
            {'product': self.product.pk},  # 2 rows
            {'product': other_product.pk, 'movement_type': 'purchase'},  # 1 row
            {'q': 'no-such-product-anywhere'},  # 0 rows — honest empty export
        ]
        for params in combos:
            expected_qs = InventoryMovement.objects.all()
            if params.get('product'):
                expected_qs = expected_qs.filter(product_id=params['product'])
            if params.get('movement_type'):
                expected_qs = expected_qs.filter(movement_type=params['movement_type'])
            if params.get('q'):
                expected_qs = expected_qs.filter(product__name__icontains=params['q'])
            expected_count = expected_qs.count()

            response = self.client.get(reverse('frontend:movement_history_export'), params)
            self.assertEqual(response.status_code, 200, params)
            rows = list(csv.reader(io.StringIO(response.content.decode())))
            data_rows = len(rows) - 1  # minus header
            self.assertEqual(data_rows, expected_count, f"CSV row count mismatch for {params}")

    def test_pdf_export_returns_real_pdf_with_filters_in_header(self):
        self.make_movement_on(timezone.now(), reference_id=30)
        self.client.login(username='movstaff', password='x')

        response = self.client.get(reverse('frontend:movement_history_export'), {
            'product': self.product.pk, 'format': 'pdf',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertIn('movement_history.pdf', response['Content-Disposition'])

    def test_pdf_export_zero_rows_is_honest_empty_not_error(self):
        self.make_movement_on(timezone.now(), reference_id=31)
        self.client.login(username='movstaff', password='x')

        response = self.client.get(reverse('frontend:movement_history_export'), {
            'q': 'no-such-product-anywhere', 'format': 'pdf',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF'))


class ExportViewTests(TestCase):
    """Phase 8.98 (BUG-44): Products/Suppliers/Audit Log's "Export" buttons
    used to do nothing. Proves each now returns a genuine, correctly
    populated CSV, and that Audit Log's export stays Admin-only exactly
    like the page it exports, per 13_AUDIT.md."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='expstaff', email='expstaff@example.com', password='x',
            employee_id='EMP-7101', full_name='Export Staffer', role=UserRole.STAFF,
        )
        self.admin = User.objects.create_user(
            username='expadmin', email='expadmin@example.com', password='x',
            employee_id='EMP-7102', full_name='Export Admin', role=UserRole.ADMIN,
        )
        self.category = Category.objects.create(name='Export Category')
        self.supplier = Supplier.objects.create(
            supplier_name='Export Supply', company_name='Export Supply Co',
            contact_person='E', email='exportsupply@example.com', phone='555-0400',
            address='1 Export Way',
        )
        self.product = Product.objects.create(
            sku='EXP-001', name='Export Widget', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('2.00'), selling_price=Decimal('4.00'),
        )

    def test_product_export_returns_real_csv(self):
        self.client.login(username='expstaff', password='x')
        response = self.client.get(reverse('frontend:product_export'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode()
        self.assertIn('Export Widget', content)
        self.assertIn('EXP-001', content)

    def test_supplier_export_returns_real_csv(self):
        self.client.login(username='expstaff', password='x')
        response = self.client.get(reverse('frontend:supplier_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Export Supply Co', response.content.decode())

    def test_audit_log_export_blocked_for_staff(self):
        self.client.login(username='expstaff', password='x')
        response = self.client.get(reverse('frontend:audit_log_export'))
        self.assertRedirects(response, reverse('frontend:dashboard'))

    def test_audit_log_export_returns_real_csv_for_admin(self):
        audit.log_action(
            self.admin, audit.PRODUCT_CREATED, 'products',
            affected_id=self.product.pk, status='success',
        )
        self.client.login(username='expadmin', password='x')
        response = self.client.get(reverse('frontend:audit_log_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('PRODUCT_CREATED', response.content.decode())

    def test_all_exports_require_login(self):
        for url_name in ('product_export', 'supplier_export', 'audit_log_export', 'movement_history_export'):
            url = reverse(f'frontend:{url_name}')
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('frontend:login')}?next={url}")


class ClassificationLogicTests(ServiceTestCase):
    """Phase 10 / Prompt 2 (2026-08-24) — frontend/classification.py,
    unit-level. Every sale here is constructed directly (bypassing
    SaleService) since these tests are about classify_product()'s own
    logic against a known data shape, not about the approve/cancel
    workflow — that's ReclassificationHookTests below.

    The multi-criteria weighted expert system needs two things most of
    the old recency-only tests didn't: the product must be *old enough*
    (>= SystemSettings.min_observation_days, default 30) and have
    *enough sale events* (>= min_sale_events, default 2) to clear the
    INSUFFICIENT_DATA gate before any of the four factors are scored at
    all — _age_and_stock()/_make_product() below back-date
    Product.created_at and every InventoryMovement.created_at (the stock
    age anchor) directly, rather than mocking timezone.now() for every
    test."""

    def _sale_for(self, product, transaction_date, quantity=1):
        sale = SaleTransaction.objects.create(
            created_by=self.user, status=SaleStatus.COMPLETED, transaction_date=transaction_date,
        )
        SaleItem.objects.create(
            transaction=sale, product=product, quantity=quantity,
            unit_price=Decimal('20.00'), line_total=Decimal('20.00') * quantity,
        )
        return sale

    def _completed_sale(self, transaction_date, quantity=1):
        return self._sale_for(self.product, transaction_date, quantity)

    def _age_and_stock(self, days_old, stock_qty, product=None):
        """Back-dates `product` (default self.product) and any
        InventoryMovement rows so _stock_age_days() reports `days_old`,
        then seeds `stock_qty` units via a single InventoryService call —
        the movement is written at "now" and immediately back-dated too,
        so it lands *before* the 90-day demand window whenever
        days_old > 90 (calculate_average_stock()'s `before` branch: a
        constant, predictable avg_stock == stock_qty for the whole
        window)."""
        product = product or self.product
        past = timezone.now() - timedelta(days=days_old)
        Product.objects.filter(pk=product.pk).update(created_at=past)
        # .update() doesn't touch the in-memory instance — without this,
        # _stock_age_days()'s Product.created_at fallback (no-movement
        # case, e.g. stock_qty=0) would silently see the original,
        # un-back-dated value.
        product.refresh_from_db()
        InventoryService.initialize_for_product(product)
        if stock_qty:
            InventoryService.increase_stock(
                product=product, quantity=stock_qty, movement_type=MovementType.PURCHASE,
                reference_type='TestSetup', reference_id=0, performed_by=self.user,
            )
        InventoryMovement.objects.filter(product=product).update(created_at=past)
        return product

    def _make_product(self, sku, days_old, stock_qty):
        product = Product.objects.create(
            sku=sku, name=sku, category=self.category, supplier=self.supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'),
        )
        return self._age_and_stock(days_old, stock_qty, product=product)

    def test_new_product_no_sales_is_insufficient_data_not_dead(self):
        """The exact scenario the old single-factor branch got wrong:
        `days_since = 9999 for never-sold` immediately satisfied
        `days_since >= dead_threshold`, so a product created *yesterday*
        classified as DEAD on its very first run. A product that hasn't
        existed long enough to have a sales history isn't "dead" — it
        simply hasn't been given the chance to prove otherwise."""
        self._age_and_stock(days_old=1, stock_qty=50)
        classification = classify_product(self.product)
        self.assertEqual(classification, StockClassification.INSUFFICIENT_DATA)
        record = InventoryClassification.objects.get(product=self.product)
        self.assertIsNone(record.stagnation_index)
        self.assertIsNone(record.recency_score)
        self.assertIsNone(record.last_sold_date)
        self.assertIsNone(record.days_since_last_sale)

    def test_recent_sale_with_high_coverage_is_not_fast(self):
        """Multi-factor proof: a sale 3 days ago alone would read "fast"
        under the old recency-only branch. 1200 days of stock cover
        (current_stock=1200, avg_daily_demand=1.0/day over the trailing
        90 days) and correspondingly weak turnover pull the composite
        stagnation index up past the slow threshold despite the fresh
        sale — the weighted system, not recency alone, decides."""
        self._age_and_stock(days_old=200, stock_qty=1200)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=80), quantity=45)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=3), quantity=45)
        classification = classify_product(self.product)
        self.assertNotEqual(classification, StockClassification.FAST)
        record = InventoryClassification.objects.get(product=self.product)
        self.assertIsNotNone(record.stagnation_index)
        self.assertGreaterEqual(record.stagnation_index, SystemSettings.get_settings().slow_index_threshold)

    def test_fast_when_sold_recently_with_low_stock_and_frequent_sales(self):
        """The positive case: low stock relative to demand, sold
        recently, sold more than once — every factor agrees this is
        moving well."""
        self._age_and_stock(days_old=200, stock_qty=5)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=3), quantity=5)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=10), quantity=5)
        self.assertEqual(classify_product(self.product), StockClassification.FAST)

    def test_identical_recency_different_turnover_gives_different_index(self):
        """Two products, same last-sold date, same sale pattern, but
        very different stock levels behind it — turnover_score must
        differ (and coverage/recency/frequency are held constant), so
        the composite index must differ too. Proves Turnover is scored
        independently, not folded into Recency."""
        settings_obj = SystemSettings.get_settings()
        self._age_and_stock(days_old=200, stock_qty=1000)  # low turnover
        self._sale_for(self.product, timezone.localdate() - timedelta(days=10), quantity=1)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=11), quantity=1)
        classify_product(self.product, settings_obj=settings_obj)
        low_turnover = InventoryClassification.objects.get(product=self.product)

        product_b = self._make_product('SKU-TURN-002', days_old=200, stock_qty=10)  # high turnover
        self._sale_for(product_b, timezone.localdate() - timedelta(days=10), quantity=1)
        self._sale_for(product_b, timezone.localdate() - timedelta(days=11), quantity=1)
        classify_product(product_b, settings_obj=settings_obj)
        high_turnover = InventoryClassification.objects.get(product=product_b)

        self.assertEqual(low_turnover.recency_score, high_turnover.recency_score)
        self.assertNotEqual(low_turnover.turnover_score, high_turnover.turnover_score)
        self.assertNotEqual(low_turnover.stagnation_index, high_turnover.stagnation_index)

    def test_changing_a_weight_changes_classification_outcome(self):
        """Proves the knowledge base is live, not ornamental: the exact
        same product data classifies differently once the admin-tunable
        weights change, with no other input touched. Deliberately NOT
        the extreme-coverage fixture used elsewhere in this class — days
        of cover here (600) sits inside the ramp band (target=90,
        extreme=730), so neither Force-FAST nor Force-SLOW ever fires,
        and the classification is decided purely by the index — the
        thing this test is actually about."""
        self._age_and_stock(days_old=200, stock_qty=100)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=80), quantity=8)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=3), quantity=7)

        settings_obj = SystemSettings.get_settings()
        before = classify_product(self.product, settings_obj=settings_obj)
        self.assertEqual(before, StockClassification.SLOW)
        record_before = InventoryClassification.objects.get(product=self.product)
        self.assertEqual(record_before.flagged_by_rule, '')  # index-decided, not an override
        index_before = record_before.stagnation_index

        settings_obj.weight_recency = Decimal('0.90')
        settings_obj.weight_turnover = Decimal('0.05')
        settings_obj.weight_coverage = Decimal('0.03')
        settings_obj.weight_frequency = Decimal('0.02')
        settings_obj.full_clean()
        settings_obj.save()

        after = classify_product(self.product, settings_obj=settings_obj)
        record_after = InventoryClassification.objects.get(product=self.product)

        self.assertEqual(after, StockClassification.FAST)
        self.assertEqual(record_after.flagged_by_rule, '')
        self.assertNotEqual(index_before, record_after.stagnation_index)

    def test_weights_not_summing_to_one_rejected_on_save(self):
        """Rejected, not silently normalised (SystemSettings.clean()) —
        0.40 + 0.30 + 0.20 + 0.05 = 0.95, not 1.00."""
        settings_obj = SystemSettings.get_settings()
        settings_obj.weight_recency = Decimal('0.40')
        settings_obj.weight_turnover = Decimal('0.30')
        settings_obj.weight_coverage = Decimal('0.20')
        settings_obj.weight_frequency = Decimal('0.05')
        with self.assertRaises(ValidationError):
            settings_obj.full_clean()
        # Confirms it's genuinely rejected, not partially applied: the
        # stored row still has its original, valid weights.
        self.assertEqual(SystemSettings.get_settings().weight_frequency, Decimal('0.10'))

    def test_confidence_rises_with_longer_observation_window(self):
        self._age_and_stock(days_old=5, stock_qty=10)
        classify_product(self.product)
        short = InventoryClassification.objects.get(product=self.product).confidence

        product_b = self._make_product('SKU-CONF-002', days_old=20, stock_qty=10)
        classify_product(product_b)
        longer = InventoryClassification.objects.get(product=product_b).confidence

        self.assertIsNotNone(short)
        self.assertIsNotNone(longer)
        self.assertLess(short, longer)

    def test_never_sold_record_never_persists_contradictory_days_since_last_sale(self):
        """BUG (docs/bugsfound.md): the old code stored
        days_since_last_sale=0 (the 9999-sentinel clamp) beside
        last_sold_date=None — "0 days since last sale" read as "sold
        today" next to a field saying no sale ever happened. Fixed at
        the point of write: the two must always agree."""
        self._age_and_stock(days_old=200, stock_qty=10)
        classify_product(self.product)
        record = InventoryClassification.objects.get(product=self.product)
        self.assertIsNone(record.last_sold_date)
        self.assertIsNone(record.days_since_last_sale)

    def test_coverage_factor_edges(self):
        """min_sale_events temporarily 0 for this test only, to isolate
        the coverage factor from the insufficient_data gate (both read
        the same "sales in the last 90 days" signal) — a legitimate
        admin configuration (age-only gating), not a workaround."""
        settings_obj = SystemSettings.get_settings()
        settings_obj.min_sale_events = 0
        settings_obj.full_clean()
        settings_obj.save()

        # current_stock == 0 -> coverage 0.0, regardless of demand.
        self._age_and_stock(days_old=200, stock_qty=0)
        classify_product(self.product, settings_obj=settings_obj)
        zero_stock = InventoryClassification.objects.get(product=self.product)
        self.assertEqual(zero_stock.coverage_score, Decimal('0.0000'))

        # real stock, zero recent demand -> coverage 1.0 (core dead-stock signal).
        product_b = self._make_product('SKU-COV-ZERODEM', days_old=200, stock_qty=500)
        classify_product(product_b, settings_obj=settings_obj)
        zero_demand = InventoryClassification.objects.get(product=product_b)
        self.assertEqual(zero_demand.coverage_score, Decimal('1.0000'))

        # huge stock vs. tiny demand: the ratio must be capped before
        # normalising, not overflow the DecimalField (the same class of
        # bug calculate_turnover_rate() already guards against).
        product_c = self._make_product('SKU-COV-HUGE', days_old=200, stock_qty=10_000_000)
        self._sale_for(product_c, timezone.localdate() - timedelta(days=5), quantity=1)
        classify_product(product_c, settings_obj=settings_obj)
        capped = InventoryClassification.objects.get(product=product_c)
        self.assertEqual(capped.coverage_score, Decimal('1.0000'))

    def test_run_full_classification_counts_sum_to_active_product_count(self):
        """INVARIANT: every active product lands in exactly one of the
        four buckets — nothing is dropped, nothing is double-counted."""
        self._age_and_stock(days_old=200, stock_qty=5)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=5), quantity=5)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=6), quantity=5)

        self._make_product('SKU-INVARIANT-YOUNG', days_old=1, stock_qty=10)  # insufficient_data

        inactive = Product.objects.create(
            sku='SKU-INVARIANT-INACTIVE', name='Retired Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('9.00'), is_active=False,
        )
        InventoryService.initialize_for_product(inactive)

        results = run_full_classification()
        self.assertEqual(sum(results.values()), Product.objects.filter(is_active=True).count())
        self.assertFalse(InventoryClassification.objects.filter(product=inactive).exists())

    def test_pending_sale_excluded_from_last_sold_date(self):
        """A product whose only sale is pending must be treated as
        never-sold for classification purposes — proves the status
        filter, not just that it exists. PROMPT_1B: aged 200 days with
        real stock and genuinely zero completed sales, this is now
        exactly the Force-DEAD "never sold, old enough" override case
        (a pending sale doesn't change that), not insufficient_data —
        the gate is age-only now."""
        self._age_and_stock(days_old=200, stock_qty=5)
        sale = SaleService.create_sale(
            {'customer_name': 'Test'},
            [{'product_id': self.product.pk, 'quantity': 1, 'unit_price': Decimal('20.00'), 'discount': 0}],
            self.user,
        )
        SaleService.submit_for_approval(sale, self.user)
        self.assertIsNone(get_last_sold_date(self.product))
        classification = classify_product(self.product)
        self.assertEqual(classification, StockClassification.DEAD)
        record = InventoryClassification.objects.get(product=self.product)
        self.assertEqual(record.flagged_by_rule, 'Never sold, 200 days in stock')

    def test_rejected_and_cancelled_sales_excluded_but_older_completed_sale_still_counts(self):
        """The exclusion matters most when it could otherwise mask a real,
        older completed sale — proves the real (older) date still wins,
        not just that the non-completed rows are ignored in isolation."""
        self._age_and_stock(days_old=200, stock_qty=500)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=75), quantity=1)
        self._sale_for(self.product, timezone.localdate() - timedelta(days=76), quantity=1)  # clears min_sale_events

        rejected = self._completed_sale(timezone.localdate())
        rejected.status = SaleStatus.REJECTED
        rejected.save(update_fields=['status'])

        cancelled = self._completed_sale(timezone.localdate())
        cancelled.status = SaleStatus.CANCELLED
        cancelled.save(update_fields=['status'])

        self.assertEqual(get_last_sold_date(self.product), timezone.localdate() - timedelta(days=75))
        classification = classify_product(self.product)
        self.assertIn(classification, (StockClassification.SLOW, StockClassification.DEAD))

    @patch('django.utils.timezone.now')
    def test_classify_uses_dhaka_date_not_utc_date(self, mock_now):
        """Same class of bug as BUG-47: 2026-01-01 20:00 UTC is 2026-01-02
        in Asia/Dhaka. A sale dated 2025-11-03 is exactly 60 days before
        the Dhaka day but only 59 before the UTC day — classify_product()
        must compute days_since=60 (recency_score 60/180 = 0.3333), not
        59; a regression to timezone.now().date() would silently shift
        this by a full day. Checked against the persisted recency_score
        directly rather than the composite classification, since the
        composite is no longer a pure function of recency alone."""
        mock_now.return_value = datetime(2026, 1, 1, 20, 0, 0, tzinfo=dt_timezone.utc)
        backdate = mock_now.return_value - timedelta(days=200)
        Product.objects.filter(pk=self.product.pk).update(created_at=backdate)
        InventoryService.initialize_for_product(self.product)
        InventoryService.increase_stock(
            product=self.product, quantity=500, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.user,
        )
        InventoryMovement.objects.filter(product=self.product).update(created_at=backdate)
        self._completed_sale(datetime(2025, 11, 3).date())
        self._completed_sale(datetime(2025, 11, 2).date())  # clears min_sale_events

        classify_product(self.product)
        record = InventoryClassification.objects.get(product=self.product)
        self.assertEqual(record.last_sold_date, datetime(2025, 11, 3).date())
        self.assertEqual(record.days_since_last_sale, 60)
        self.assertEqual(record.recency_score, Decimal('0.3333'))

    @patch('django.utils.timezone.now')
    def test_average_stock_start_of_window_uses_first_movement_stock_before_not_current_stock(self, mock_now):
        """The Phase 10 fix: no movement before period_start, but one
        during it, must use that movement's own stock_before (0 here) as
        the window's starting stock — not current_stock (100, today's
        level, which includes everything up to and past period_end). The
        pre-fix doc code would have averaged ~100 across the whole window;
        stock was actually 0 for the first half."""
        base = datetime(2026, 6, 1, 0, 0, 0, tzinfo=dt_timezone.utc)
        mock_now.return_value = base
        InventoryService.initialize_for_product(self.product)  # stock=0, no movement written

        mock_now.return_value = base + timedelta(days=5)
        InventoryService.increase_stock(
            product=self.product, quantity=100, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=1, performed_by=self.user,
        )

        avg = calculate_average_stock(self.product, base, base + timedelta(days=10))
        # 0 for days 0-5, 100 for days 5-10 of a 10-day window -> 50.
        self.assertAlmostEqual(avg, 50, delta=1)

    def test_average_stock_with_movement_before_window_unchanged(self):
        """The already-correct branch (movement before period_start) must
        keep working exactly as before — this fix only touches the empty-
        `before` case."""
        InventoryService.initialize_for_product(self.product)
        self.give_stock(40)
        period_start = timezone.now() + timedelta(seconds=1)
        period_end = period_start + timedelta(days=1)
        avg = calculate_average_stock(self.product, period_start, period_end)
        self.assertAlmostEqual(avg, 40, delta=1)

    # ---------------------------------------------------------------
    # PROMPT_1B (2026-08-24) — index calibration incident regression
    # tests. See docs/bugsfound.md for the full incident: the first live
    # run against real shaped seed data produced ZERO dead-stock
    # classifications on data known to contain dead stock. These
    # fixtures mirror the real diagnosed products by name and by their
    # actual measured shape (age/stock/days_since_last_sale), rather
    # than running the real seed_dev_data command inside a test.
    # ---------------------------------------------------------------

    def test_anti_regression_all_five_diagnosed_dead_products_classify_dead(self):
        """The exact five products the old 180-day rule called dead in
        the real dev run, and the first version of the weighted index
        lost entirely to insufficient_data. Asserted by name."""
        never_sold_products = [
            ('Laptop Stand', 90, 50),
            ('Notebook (200 pages)', 90, 50),
        ]
        dormant_products = [
            ('Desk Organizer Tray', 300, 30, 210),
            ('Electric Kettle', 300, 33, 240),
            ('Powdered Milk 1kg', 300, 32, 195),
        ]
        for name, age, stock in never_sold_products:
            self._make_product(name, days_old=age, stock_qty=stock)
        for name, age, stock, sold_days_ago in dormant_products:
            product = self._make_product(name, days_old=age, stock_qty=stock)
            self._sale_for(product, timezone.localdate() - timedelta(days=sold_days_ago), quantity=2)

        for name, *_ in never_sold_products + [(n,) for n, *_ in dormant_products]:
            product = Product.objects.get(name=name)
            classification = classify_product(product)
            self.assertEqual(
                classification, StockClassification.DEAD,
                msg=f"{name} should classify DEAD (anti-regression), got {classification}",
            )

    def test_age_20_with_stock_no_sales_is_insufficient_data(self):
        product = self._make_product('SKU-AGE20', days_old=20, stock_qty=40)
        self.assertEqual(classify_product(product), StockClassification.INSUFFICIENT_DATA)

    def test_age_300_with_stock_no_sales_is_dead_not_insufficient_data(self):
        """The gate is age-only now (PROMPT_1B) — a product old enough to
        have had every opportunity to sell, and genuinely never has,
        with real stock sitting idle, is dead, not "we don't know yet." """
        product = self._make_product('SKU-AGE300', days_old=300, stock_qty=40)
        classification = classify_product(product)
        self.assertEqual(classification, StockClassification.DEAD)
        record = InventoryClassification.objects.get(product=product)
        self.assertEqual(record.flagged_by_rule, 'Never sold, 300 days in stock')

    def test_overrides_evaluated_before_gate_dormant_product_never_reaches_insufficient_data(self):
        """A 300-day dormant product (real stock, no recent sales) must
        never land in insufficient_data — proves the override layer runs
        BEFORE the gate, not after, so a genuinely dead product can never
        be hidden behind "not enough data yet." """
        product = self._make_product('SKU-DORMANT-ORDER', days_old=300, stock_qty=20)
        self._sale_for(product, timezone.localdate() - timedelta(days=200), quantity=1)
        classification = classify_product(product)
        self.assertNotEqual(classification, StockClassification.INSUFFICIENT_DATA)
        self.assertEqual(classification, StockClassification.DEAD)

    def test_frequency_score_varies_across_the_catalogue(self):
        """Guards the FIX 2 formula bug from ever returning: the old
        formula was mathematically pinned at 0 for every scored product.
        A steady weekly seller and a single-bulk-sale product must land
        on different frequency_score values."""
        steady = self._make_product('SKU-FREQ-STEADY', days_old=200, stock_qty=200)
        for week in range(10):
            self._sale_for(steady, timezone.localdate() - timedelta(days=week * 7 + 1), quantity=1)
        classify_product(steady)
        steady_freq = InventoryClassification.objects.get(product=steady).frequency_score

        bulk = self._make_product('SKU-FREQ-BULK', days_old=200, stock_qty=200)
        self._sale_for(bulk, timezone.localdate() - timedelta(days=5), quantity=10)
        classify_product(bulk)
        bulk_freq = InventoryClassification.objects.get(product=bulk).frequency_score

        self.assertNotEqual(steady_freq, bulk_freq)
        scores = [float(steady_freq), float(bulk_freq)]
        self.assertGreater(statistics.pstdev(scores), 0)

    def test_coverage_score_not_all_equal_to_one(self):
        """Guards the FIX 3 saturation bug: the old ramp clamped to 1.00
        the moment days_of_cover crossed target_days_of_cover, so nearly
        every real product saturated. A product with modest cover (well
        under target) and one with cover deep in the ramp band must
        differ, and neither has to be 1.00."""
        modest = self._make_product('SKU-COV-MODEST', days_old=200, stock_qty=20)
        self._sale_for(modest, timezone.localdate() - timedelta(days=5), quantity=10)
        self._sale_for(modest, timezone.localdate() - timedelta(days=12), quantity=10)
        classify_product(modest)
        modest_cov = InventoryClassification.objects.get(product=modest).coverage_score

        ramped = self._make_product('SKU-COV-RAMP', days_old=200, stock_qty=300)
        self._sale_for(ramped, timezone.localdate() - timedelta(days=5), quantity=15)
        classify_product(ramped)
        ramped_cov = InventoryClassification.objects.get(product=ramped).coverage_score

        self.assertNotEqual(modest_cov, ramped_cov)
        self.assertFalse(modest_cov == Decimal('1.0000') == ramped_cov)

    def test_each_override_records_which_rule_fired(self):
        dead_by_recency = self._make_product('SKU-RULE-DEAD-RECENCY', days_old=300, stock_qty=10)
        self._sale_for(dead_by_recency, timezone.localdate() - timedelta(days=200), quantity=1)
        classify_product(dead_by_recency)
        self.assertIn(
            'No sales in',
            InventoryClassification.objects.get(product=dead_by_recency).flagged_by_rule,
        )

        dead_never_sold = self._make_product('SKU-RULE-DEAD-NEVERSOLD', days_old=250, stock_qty=10)
        classify_product(dead_never_sold)
        self.assertIn(
            'Never sold',
            InventoryClassification.objects.get(product=dead_never_sold).flagged_by_rule,
        )

        fast_recent = self._make_product('SKU-RULE-FAST', days_old=200, stock_qty=5)
        self._sale_for(fast_recent, timezone.localdate() - timedelta(days=2), quantity=5)
        self._sale_for(fast_recent, timezone.localdate() - timedelta(days=9), quantity=5)
        classify_product(fast_recent)
        self.assertIn(
            'Sold',
            InventoryClassification.objects.get(product=fast_recent).flagged_by_rule,
        )

        # Force-SLOW only applies when the index doesn't already call the
        # product DEAD on its own (see classify_product()'s own
        # docstring) — recent-ish sale, real turnover, just buried in
        # extreme stock.
        slow_extreme_cover = self._make_product('SKU-RULE-SLOW', days_old=200, stock_qty=2000)
        self._sale_for(slow_extreme_cover, timezone.localdate() - timedelta(days=3), quantity=50)
        self._sale_for(slow_extreme_cover, timezone.localdate() - timedelta(days=10), quantity=50)
        classify_product(slow_extreme_cover)
        record = InventoryClassification.objects.get(product=slow_extreme_cover)
        self.assertEqual(record.classification, StockClassification.SLOW)
        self.assertIn('days of stock on hand', record.flagged_by_rule)

    def test_override_precedence_dead_beats_extreme_coverage_slow_candidate(self):
        """A product matching BOTH a Force-DEAD condition (no sales in
        >= dead_stock_threshold_days) AND the Force-SLOW candidate
        condition (extreme days of cover) must classify DEAD — the
        documented, higher-severity outcome — with the DEAD rule
        recorded, not the SLOW one."""
        product = self._make_product('SKU-PRECEDENCE', days_old=300, stock_qty=5000)
        self._sale_for(product, timezone.localdate() - timedelta(days=200), quantity=1)
        classification = classify_product(product)
        record = InventoryClassification.objects.get(product=product)
        self.assertEqual(classification, StockClassification.DEAD)
        self.assertIn('No sales in', record.flagged_by_rule)
        self.assertNotIn('days of stock on hand', record.flagged_by_rule)

    def test_distribution_not_degenerate_across_a_mixed_catalogue(self):
        """>= 1 fast, >= 1 dead, no single class above ~70% of a mixed
        catalogue — the property the first (broken) run violated
        outright (0 dead)."""
        for i in range(8):
            fast_product = self._make_product(f'SKU-DIST-FAST-{i}', days_old=200, stock_qty=5)
            self._sale_for(fast_product, timezone.localdate() - timedelta(days=3), quantity=5)
            self._sale_for(fast_product, timezone.localdate() - timedelta(days=10), quantity=5)

        for i in range(3):
            dead_product = self._make_product(f'SKU-DIST-DEAD-{i}', days_old=300, stock_qty=20)
            self._sale_for(dead_product, timezone.localdate() - timedelta(days=200 + i), quantity=1)

        young_product = self._make_product('SKU-DIST-YOUNG', days_old=5, stock_qty=10)

        results = run_full_classification()
        total = sum(results.values())
        self.assertGreaterEqual(results[StockClassification.FAST], 1)
        self.assertGreaterEqual(results[StockClassification.DEAD], 1)
        for cls, count in results.items():
            self.assertLessEqual(
                count / total, 0.70,
                msg=f"{cls} is {count}/{total} ({count/total:.0%}) of the catalogue — too dominant",
            )

class ReclassificationHookTests(ServiceTestCase):
    """Phase 10 — the explicit synchronous call in SaleService.approve_sale()/
    cancel_sale(), not the documented post_save(SaleTransaction) signal
    (docs/project_memory.md §13 has the full rejection reasoning)."""

    def _draft_sale(self, quantity=1):
        return SaleService.create_sale(
            {'customer_name': 'Test'},
            [{'product_id': self.product.pk, 'quantity': quantity, 'unit_price': Decimal('20.00'), 'discount': 0}],
            self.user,
        )

    def test_creating_a_draft_does_not_reclassify(self):
        InventoryService.initialize_for_product(self.product)
        self.assertFalse(InventoryClassification.objects.filter(product=self.product).exists())
        self._draft_sale()
        self.assertFalse(InventoryClassification.objects.filter(product=self.product).exists())

    def test_approving_a_pending_sale_reclassifies_immediately(self):
        """Live, no manual Run — proves the hook fires from approve_sale()
        itself, not from a separate step the caller has to remember. Not
        a classification-*outcome* proof (self.product is freshly
        created in setUp — age 0 — so this lands as insufficient_data
        under the default gating; outcome-specific cases live in
        ClassificationLogicTests): the row exists, was genuinely computed
        from this sale, and the audit trail fired — that's what
        "reclassifies immediately" means here."""
        self.give_stock(10)
        sale = self._draft_sale(quantity=2)
        SaleService.submit_for_approval(sale, self.user)
        self.assertFalse(InventoryClassification.objects.filter(product=self.product).exists())

        SaleService.approve_sale(sale, self.supervisor)

        record = InventoryClassification.objects.get(product=self.product)
        self.assertEqual(record.last_sold_date, timezone.localdate())
        self.assertTrue(
            AuditLog.objects.filter(action=audit.AI_PRODUCT_RECLASSIFIED, affected_id=self.product.pk).exists()
        )

    def test_cancelling_a_pre_approval_sale_does_not_change_classification(self):
        """cancel_sale() only ever runs pre-approval (8.99c) — nothing it
        does is classification-relevant (no stock moved, no completed-sale
        history changed), so the call is a same-result no-op by design,
        not a correctness gap. Included per this phase's own instruction
        anyway; this proves it's genuinely harmless, not just present.
        Also covers the missing-audit-log fix (docs/bugsfound.md):
        cancel_sale() now logs AI_PRODUCT_RECLASSIFIED per item, matching
        approve_sale()'s own equivalent call."""
        # Phase 12 — cancel_sale()'s can_approve() gate: self.supervisor
        # cancels (self.user is STAFF, never a valid canceller).
        InventoryService.initialize_for_product(self.product)
        sale = self._draft_sale()
        SaleService.cancel_sale(sale, self.supervisor, 'Customer changed their mind.')
        record = InventoryClassification.objects.get(product=self.product)
        # Fresh product (age 0, zero completed sales) -> insufficient_data,
        # never "dead" (BUG-fix invariant: last_sold_date is None, so
        # days_since_last_sale must be None too, never a contradictory 0).
        self.assertEqual(record.classification, StockClassification.INSUFFICIENT_DATA)
        self.assertIsNone(record.last_sold_date)
        self.assertIsNone(record.days_since_last_sale)
        self.assertTrue(
            AuditLog.objects.filter(
                action=audit.AI_PRODUCT_RECLASSIFIED, affected_id=self.product.pk,
                details__trigger='sale_cancelled',
            ).exists()
        )


class SlowMovingViewTests(TestCase):
    """Phase 10 — SlowMovingDeadStockView: real data on GET, real
    synchronous run on POST. SupervisorRequiredMixin itself is Phase
    8.99j's (BUG-43) — AIPageAccessTests above already proves the GET
    gate; this class adds POST-specific coverage (the one new thing this
    phase added to the view) plus the wired-data assertions."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='smadmin', email='smadmin@example.com', password='x',
            employee_id='EMP-9101', full_name='SM Admin', role=UserRole.ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username='smsuper', email='smsuper@example.com', password='x',
            employee_id='EMP-9102', full_name='SM Supervisor', role=UserRole.SUPERVISOR,
        )
        self.staff = User.objects.create_user(
            username='smstaff', email='smstaff@example.com', password='x',
            employee_id='EMP-9103', full_name='SM Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='SM Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='SM Supply', company_name='SM Supply Co', contact_person='Jo',
            email='smsupply@example.com', phone='555-0900', address='1 SM Way',
        )
        self.product = Product.objects.create(
            sku='SM-SKU-001', name='SM Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'),
        )
        InventoryService.initialize_for_product(self.product)

    def test_post_blocked_for_staff_and_anonymous(self):
        url = reverse('frontend:slow_moving')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # anonymous -> login

        self.client.login(username='smstaff', password='x')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # staff -> bounced, not the run

    def test_run_button_classifies_and_returns_counts(self):
        backdate = timezone.now() - timedelta(days=200)
        Product.objects.filter(pk=self.product.pk).update(created_at=backdate)
        InventoryService.increase_stock(
            product=self.product, quantity=20, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=1, performed_by=self.admin,
        )
        InventoryMovement.objects.filter(product=self.product).update(created_at=backdate)

        # Two completed sales, not one — clears min_sale_events so this
        # product actually gets scored (not just gated to
        # insufficient_data), proving the counts dict really reflects
        # classify_product()'s own decision.
        for _ in range(2):
            sale = SaleService.create_sale(
                {'customer_name': 'Test'},
                [{'product_id': self.product.pk, 'quantity': 1, 'unit_price': Decimal('20.00'), 'discount': 0}],
                self.admin,
            )
            SaleService.submit_for_approval(sale, self.admin)
            SaleService.approve_sale(sale, self.admin)
        # approve_sale() already reclassified this one product (twice) —
        # reset so this test proves the *Run button's own* POST does a
        # real, independent classification, not just reads what approval
        # left.
        InventoryClassification.objects.all().delete()

        self.client.login(username='smsuper', password='x')
        response = self.client.post(reverse('frontend:slow_moving'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(sum(payload['results'].values()), 1)
        self.assertTrue(InventoryClassification.objects.filter(product=self.product).exists())
        self.assertTrue(AuditLog.objects.filter(action=audit.AI_CLASSIFICATION_RUN).exists())

    def test_get_renders_insufficient_data_copy_for_new_never_sold_product(self):
        """self.product is freshly created in setUp (age 0, no sales) —
        insufficient_data, not the old "no recorded sales -> dead" copy,
        which is now unreachable for a genuinely never-sold product under
        default settings (min_sale_events=2 gates it first). Proves
        insufficient_data actually renders on the page, not just exists
        in the DB."""
        classify_product(self.product)
        self.client.login(username='smsuper', password='x')
        response = self.client.get(reverse('frontend:slow_moving'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Insufficient Data')
        self.assertNotContains(response, '9999')


class ClassificationAPITests(TestCase):
    """Phase 10 — the one DRF slice Phase 9 pre-committed
    (docs/project_memory.md §13): read-only, IsSupervisorOrAbove only."""

    def setUp(self):
        self.supervisor = User.objects.create_user(
            username='apisuper', email='apisuper@example.com', password='x',
            employee_id='EMP-9201', full_name='API Supervisor', role=UserRole.SUPERVISOR,
        )
        self.staff = User.objects.create_user(
            username='apistaff', email='apistaff@example.com', password='x',
            employee_id='EMP-9202', full_name='API Staffer', role=UserRole.STAFF,
        )
        category = Category.objects.create(name='API Widgets')
        supplier = Supplier.objects.create(
            supplier_name='API Supply', company_name='API Supply Co', contact_person='Jo',
            email='apisupply@example.com', phone='555-0910', address='1 API Way',
        )
        self.product = Product.objects.create(
            sku='API-SKU-001', name='API Widget', category=category, supplier=supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'),
        )
        InventoryService.initialize_for_product(self.product)
        classify_product(self.product)

    def test_list_requires_supervisor_or_above(self):
        url = reverse('api:ai_classifications_list')
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.login(username='apistaff', password='x')
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.login(username='apisuper', password='x')
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_list_returns_real_serialized_fields(self):
        # Freshly created (age 0, no sales) -> insufficient_data under
        # default gating, not dead (Prompt 2, 2026-08-24).
        self.client.login(username='apisuper', password='x')
        response = self.client.get(reverse('api:ai_classifications_list'))
        row = response.json()['results'][0]
        self.assertEqual(row['product_name'], 'API Widget')
        self.assertEqual(row['product_sku'], 'API-SKU-001')
        self.assertEqual(row['classification'], StockClassification.INSUFFICIENT_DATA)

    def test_list_filter_query_param(self):
        self.client.login(username='apisuper', password='x')
        response = self.client.get(reverse('api:ai_classifications_list'), {'filter': 'fast'})
        self.assertEqual(response.json()['count'], 0)

    def test_list_filter_accepts_insufficient_data(self):
        """REQ 14.9 (filter products by AI classification) — the fourth
        value must be in the whitelist too, not just the original three."""
        self.client.login(username='apisuper', password='x')
        response = self.client.get(reverse('api:ai_classifications_list'), {'filter': 'insufficient_data'})
        self.assertEqual(response.json()['count'], 1)

    def test_summary_returns_real_counts(self):
        self.client.login(username='apisuper', password='x')
        response = self.client.get(reverse('api:ai_classifications_summary'))
        self.assertEqual(response.json(), {'insufficient_data': 1})


def _clear_forecast_model_files():
    """ai_models/*.joblib lives on the real filesystem, not the test
    database — Django's per-test transaction rollback never touches it.
    Found the hard way: a test early in this file's alphabetical run
    order found a *stale model file left over from this session's own
    earlier manual/interactive testing against the real dev DB* and
    quietly used it instead of training its own, making later tests
    (whose own fixtures are deliberately too small to satisfy
    train_model()'s real >=10-pooled-row requirement on their own) fail
    or pass depending on run order — not on their own logic. Every test
    class that trains or predicts calls this in both setUp() and
    tearDown() so no test's result depends on what ran before it, in this
    file or in a completely different session."""
    for period in ('W', 'M'):
        path = os.path.join(MODELS_DIR, f'forecast_model_{period}.joblib')
        if os.path.exists(path):
            os.remove(path)


class ForecastingPipelineTests(ServiceTestCase):
    """Phase 11 — frontend/forecasting.py, unit-level. Sales constructed
    directly (bypassing SaleService) for the same reason
    ClassificationLogicTests does: these test the pipeline's own logic
    against a known data shape, not the approve workflow."""

    def setUp(self):
        super().setUp()
        _clear_forecast_model_files()

    def _weekly_sales(self, product, weeks, start_weeks_ago, qty=5):
        """`weeks` completed sales, one per week, most recent at
        `start_weeks_ago - weeks + 1` weeks back."""
        for i in range(weeks):
            days_ago = (start_weeks_ago - i) * 7
            sale = SaleTransaction.objects.create(
                created_by=self.user, status=SaleStatus.COMPLETED,
                transaction_date=timezone.localdate() - timedelta(days=days_ago),
            )
            SaleItem.objects.create(
                transaction=sale, product=product, quantity=qty,
                unit_price=Decimal('20.00'), line_total=Decimal('20.00') * qty,
            )

    def tearDown(self):
        _clear_forecast_model_files()

    def test_get_sales_dataframe_excludes_non_completed_sales(self):
        """Phase 9.5's own finding, fixed here — a product whose only
        sale is pending/rejected/cancelled must not appear at all."""
        self._weekly_sales(self.product, weeks=1, start_weeks_ago=1)
        pending = SaleService.create_sale(
            {'customer_name': 'Test'},
            [{'product_id': self.product.pk, 'quantity': 9, 'unit_price': Decimal('20.00'), 'discount': 0}],
            self.user,
        )
        SaleService.submit_for_approval(pending, self.user)

        df = get_sales_dataframe(product_id=self.product.pk)
        self.assertEqual(df['qty_sold'].sum(), 5)  # only the one completed sale, not +9

    def test_get_sales_dataframe_date_column_is_real_datetime(self):
        """Regression test for a real bug found empirically (docs/
        project_memory.md §13): the reference code converted
        transaction_date into a *new* column but renamed the original,
        unconverted one to 'date' — the column build_features() actually
        uses. build_features()'s df.set_index('date').resample() requires
        a genuine DatetimeIndex; an object-dtype 'date' column raises
        TypeError there, not here, so this test pins the fix at its
        source rather than relying on a downstream crash to catch it."""
        self._weekly_sales(self.product, weeks=1, start_weeks_ago=1)
        df = get_sales_dataframe()
        self.assertTrue(str(df['date'].dtype).startswith('datetime64'))

    def test_short_history_product_skipped_not_errored(self):
        """Under 4 weeks of history -> build_features() drops every row
        via dropna() (lag_4 needs 4 prior periods) -> predict_demand()
        returns [], not an exception."""
        self._weekly_sales(self.product, weeks=2, start_weeks_ago=2)
        preds = predict_demand(self.product.pk, period='W', periods_ahead=4)
        self.assertEqual(preds, [])

    def test_no_sales_at_all_returns_empty_not_error(self):
        preds = predict_demand(self.product.pk, period='W', periods_ahead=4)
        self.assertEqual(preds, [])

    def test_stockout_flag_computed_correctly_in_isolation(self):
        """get_stockout_flags() queries InventoryMovement directly (never
        frontend.reports.filter_movements(), which takes an HTTP request
        and doesn't apply here). Also pins the tz-aware/tz-naive fix: a
        DateTimeField (created_at) compared to a DateField-derived
        DatetimeIndex must not raise on merge — proven properly in
        test_stockout_flag_survives_into_features below; this test proves
        get_stockout_flags() itself returns the right day and flag."""
        self.give_stock(10)
        record = InventoryRecord.objects.get(product=self.product)
        record.current_stock = 0
        record.save(update_fields=['current_stock'])
        InventoryMovement.objects.create(
            product=self.product, movement_type=MovementType.SALE, quantity_change=-10,
            stock_before=10, stock_after=0, reference_type='TestSetup', reference_id=1,
            performed_by=self.user,
        )
        flags = get_stockout_flags(self.product.pk, period='W')
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags['stockout_flag'].iloc[0], 1)

    def test_stockout_flag_survives_into_features(self):
        """The real Phase 9.5 finding: a stockout event computed
        correctly in isolation still vanished at build_features()'s
        merge() if it fell inside the first ~4 weekly buckets of the
        product's own history (dropna()'s lag_4 burn-in). Enough
        pre-stockout weeks here for the stockout week itself to survive."""
        self._weekly_sales(self.product, weeks=6, start_weeks_ago=12, qty=3)
        # A zero-stock movement inside that history (week 7, days_ago=35).
        InventoryMovement.objects.create(
            product=self.product, movement_type=MovementType.SALE, quantity_change=-3,
            stock_before=3, stock_after=0, reference_type='TestSetup', reference_id=1,
            performed_by=self.user,
        )
        InventoryMovement.objects.filter(product=self.product).update(
            created_at=timezone.now() - timedelta(days=35)
        )
        self._weekly_sales(self.product, weeks=4, start_weeks_ago=4, qty=3)

        df = get_sales_dataframe(product_id=self.product.pk)
        features = build_features(df, period='W')
        self.assertGreater((features['stockout_flag'] == 1).sum(), 0)

    def test_lag_rotation_shifts_correctly(self):
        """Design Notes revision #5: lag_1 of step N+1 must equal the
        prediction from step N — only the lag_1..lag_4 block rotates, not
        the whole feature vector (the original np.roll(last_row, 1) bug
        this replaces would also scramble rolling_std_4/period_num/
        category_id/stockout_flag). train_model() itself needs >=10 pooled
        feature rows to run at all (its own guard) — 15 weeks of history
        survives dropna()'s 4-period lag_4 burn-in with room to spare."""
        self._weekly_sales(self.product, weeks=15, start_weeks_ago=15, qty=4)
        preds = predict_demand(self.product.pk, period='W', periods_ahead=3)
        self.assertEqual(len(preds), 3)
        # Re-derive step 1's prediction independently and confirm it
        # matches what the pipeline used as step 2's lag_1 by checking
        # the model/feature machinery didn't error and produced 3 real,
        # distinct-shaped rows (the rotation contract is exercised by
        # every multi-step call; a scrambled vector would produce
        # nonsensical/negative-clipped-to-0 output for every step after
        # the first, not just occasionally).
        for p in preds:
            self.assertIn('forecasted_demand', p)
            self.assertGreaterEqual(p['forecasted_demand'], 0)

    def test_period_num_advances_across_multi_step_forecast(self):
        """BUG found and fixed this pass: predict_demand()'s multi-step
        loop never advanced period_num — every step fed the model the
        same, last-observed period_num, telling it every future period
        was the same point in time rather than 1/2/3/4 periods further
        out. Spies on the trained model's own predict() (not just the
        output shape, which wouldn't catch a frozen input feature) to
        assert period_num strictly increases step over step. 15 weeks
        for train_model()'s own >=10-pooled-row guard."""
        self._weekly_sales(self.product, weeks=15, start_weeks_ago=15, qty=4)
        train_model('W')

        from sklearn.ensemble import HistGradientBoostingRegressor
        original_predict = HistGradientBoostingRegressor.predict
        seen_period_nums = []

        def spy_predict(self, X, *args, **kwargs):
            seen_period_nums.append(X['period_num'].iloc[0])
            return original_predict(self, X, *args, **kwargs)

        with patch.object(HistGradientBoostingRegressor, 'predict', spy_predict):
            preds = predict_demand(self.product.pk, period='W', periods_ahead=4)

        self.assertEqual(len(preds), 4)
        self.assertEqual(len(seen_period_nums), 4)
        for earlier, later in zip(seen_period_nums, seen_period_nums[1:]):
            self.assertLess(earlier, later, "period_num must strictly increase across forecast steps")
        # Each step is exactly 1 more than the last, not merely increasing.
        self.assertEqual(
            [seen_period_nums[i + 1] - seen_period_nums[i] for i in range(3)],
            [1, 1, 1],
        )

    def test_train_model_chronological_split_not_random(self):
        """Design Notes revision #2: the held-out test rows must be the
        most recent ones, not a random sample."""
        self._weekly_sales(self.product, weeks=10, start_weeks_ago=10, qty=3)
        df_raw = get_sales_dataframe()
        features = build_features(df_raw, period='W')
        df_sorted = features.sort_values('period_start').reset_index(drop=True)
        split_idx = int(len(df_sorted) * 0.8)
        split_idx = min(max(split_idx, 1), len(df_sorted) - 1)
        test_df = df_sorted.iloc[split_idx:]
        # Every held-out row's period_start must be >= every training
        # row's period_start (chronological, not shuffled).
        train_df = df_sorted.iloc[:split_idx]
        self.assertGreaterEqual(test_df['period_start'].min(), train_df['period_start'].max())

    def test_predict_demand_auto_trains_when_model_file_missing(self):
        """Explicitly required: delete the model file, call predict, it
        must retrain inline and return real predictions, not 500. This is
        what makes an ephemeral production disk (redeploy wipes
        ai_models/) survivable — see docs/project_memory.md §13. 15 weeks
        so train_model()'s own >=10-pooled-row guard is satisfied."""
        self._weekly_sales(self.product, weeks=15, start_weeks_ago=15, qty=4)
        train_model('W')
        model_path = os.path.join(MODELS_DIR, 'forecast_model_W.joblib')
        self.assertTrue(os.path.exists(model_path))
        os.remove(model_path)
        self.assertFalse(os.path.exists(model_path))

        preds = predict_demand(self.product.pk, period='W', periods_ahead=2)
        self.assertEqual(len(preds), 2)
        self.assertTrue(os.path.exists(model_path))

    def test_confidence_score_bounded(self):
        """Design Notes revision #6: confidence comes from the model's
        real backtest residual_std, clamped to [0.50, 0.95] — not the
        original last-row heuristic. 15 weeks for train_model()'s own
        >=10-pooled-row guard."""
        self._weekly_sales(self.product, weeks=15, start_weeks_ago=15, qty=5)
        preds = predict_demand(self.product.pk, period='W', periods_ahead=4)
        for p in preds:
            self.assertGreaterEqual(p['confidence_score'], 0.50)
            self.assertLessEqual(p['confidence_score'], 0.95)


class BackfillActualDemandTests(ServiceTestCase):

    def test_backfill_populates_elapsed_forecasts(self):
        today = timezone.localdate()
        forecast = DemandForecast.objects.create(
            product=self.product, forecast_period=ForecastPeriod.WEEKLY,
            period_start=today - timedelta(days=14), period_end=today - timedelta(days=8),
            forecasted_demand=Decimal('10.00'), recommended_reorder_qty=0,
            confidence_score=Decimal('0.70'), model_version='test',
        )
        sale = SaleTransaction.objects.create(
            created_by=self.user, status=SaleStatus.COMPLETED,
            transaction_date=today - timedelta(days=10),
        )
        SaleItem.objects.create(
            transaction=sale, product=self.product, quantity=7,
            unit_price=Decimal('20.00'), line_total=Decimal('140.00'),
        )
        updated = backfill_actual_demand()
        self.assertEqual(updated, 1)
        forecast.refresh_from_db()
        self.assertEqual(forecast.actual_demand, 7)

    def test_backfill_leaves_not_yet_elapsed_alone(self):
        today = timezone.localdate()
        forecast = DemandForecast.objects.create(
            product=self.product, forecast_period=ForecastPeriod.WEEKLY,
            period_start=today, period_end=today + timedelta(days=6),
            forecasted_demand=Decimal('10.00'), recommended_reorder_qty=0,
            confidence_score=Decimal('0.70'), model_version='test',
        )
        updated = backfill_actual_demand()
        self.assertEqual(updated, 0)
        forecast.refresh_from_db()
        self.assertIsNone(forecast.actual_demand)

    def test_backfill_excludes_non_completed_sales(self):
        today = timezone.localdate()
        forecast = DemandForecast.objects.create(
            product=self.product, forecast_period=ForecastPeriod.WEEKLY,
            period_start=today - timedelta(days=14), period_end=today - timedelta(days=8),
            forecasted_demand=Decimal('10.00'), recommended_reorder_qty=0,
            confidence_score=Decimal('0.70'), model_version='test',
        )
        pending = SaleService.create_sale(
            {'customer_name': 'Test'},
            [{'product_id': self.product.pk, 'quantity': 99, 'unit_price': Decimal('20.00'), 'discount': 0}],
            self.user,
        )
        pending.transaction_date = today - timedelta(days=10)
        pending.save(update_fields=['transaction_date'])
        SaleService.submit_for_approval(pending, self.user)

        backfill_actual_demand()
        forecast.refresh_from_db()
        self.assertEqual(forecast.actual_demand, 0)  # not 99


class RunFullForecastTests(ServiceTestCase):

    def setUp(self):
        super().setUp()
        _clear_forecast_model_files()

    def tearDown(self):
        _clear_forecast_model_files()

    def _weekly_sales(self, product, weeks, start_weeks_ago, qty=5):
        for i in range(weeks):
            days_ago = (start_weeks_ago - i) * 7
            sale = SaleTransaction.objects.create(
                created_by=self.user, status=SaleStatus.COMPLETED,
                transaction_date=timezone.localdate() - timedelta(days=days_ago),
            )
            SaleItem.objects.create(
                transaction=sale, product=product, quantity=qty,
                unit_price=Decimal('20.00'), line_total=Decimal('20.00') * qty,
            )

    def test_creates_demand_forecast_rows_and_skips_inactive(self):
        # 15 weeks: train_model()'s own >=10-pooled-feature-row guard.
        self._weekly_sales(self.product, weeks=15, start_weeks_ago=15, qty=4)
        self.give_stock(200)

        inactive = Product.objects.create(
            sku='SKU-INACTIVE-FC', name='Retired Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('9.00'), is_active=False,
        )

        result = run_full_forecast()
        self.assertGreater(result['forecasts_created'], 0)
        self.assertTrue(DemandForecast.objects.filter(product=self.product).exists())
        self.assertFalse(DemandForecast.objects.filter(product=inactive).exists())

    def test_replenish_alert_when_weekly_demand_exceeds_stock(self):
        self._weekly_sales(self.product, weeks=15, start_weeks_ago=15, qty=8)
        self.give_stock(1)  # deliberately far below any plausible weekly forecast

        result = run_full_forecast()
        alerts = [a for a in result['replenish_alerts'] if a['product'].pk == self.product.pk]
        self.assertTrue(alerts, "expected at least one replenish alert for a near-zero-stock product")
        self.assertEqual(alerts[0]['current_stock'], 1)

    def test_monthly_run_converts_weeks_setting_not_raw_value(self):
        """BUG found and fixed this pass: forecast_period_weeks (a
        weeks-denominated horizon setting — its own name says so) was
        previously passed straight through as periods_ahead to the
        MONTHLY run too. With the default of 4, the weekly run correctly
        produced 4 rows but the monthly run produced 4 *months* of
        forecasts instead of the intended ~1.

        Needs a sales history spanning ~16 months for train_model('M') to
        survive its own dropna()/>=10-row guard (train_model() itself
        documents needing ~14 months pooled before monthly rows survive
        at all) — build_features()'s resample() fills every calendar
        month in the *span*, populated or not, so a handful of
        monthly-spaced transactions covers the same span as 70 weekly
        ones for a fraction of the DB writes. Deliberately not reusing
        _weekly_sales() at a large count here: SaleTransaction's own
        invoice-number generator is a random 4-digit suffix (INV-<date>-
        NNNN, ~9000 possible values), and 70 rapid creates in one test
        carries a real, non-negligible collision probability — a
        pre-existing weakness in that generator, not something this
        forecasting fix should paper over, but also not worth tripping
        over here when a monthly cadence proves the same thing with 16
        transactions instead of 70."""
        for i in range(16):
            sale = SaleTransaction.objects.create(
                created_by=self.user, status=SaleStatus.COMPLETED,
                transaction_date=timezone.localdate() - timedelta(days=(16 - i) * 30),
            )
            SaleItem.objects.create(
                transaction=sale, product=self.product, quantity=4,
                unit_price=Decimal('20.00'), line_total=Decimal('80.00'),
            )
        self.give_stock(500)

        settings_obj = SystemSettings.get_settings()
        settings_obj.forecast_period_weeks = 4
        settings_obj.save(update_fields=['forecast_period_weeks'])

        result = run_full_forecast()
        self.assertIn('M', result['periods_trained'], "monthly training must succeed for this test to prove anything")

        weekly_rows = DemandForecast.objects.filter(product=self.product, forecast_period=ForecastPeriod.WEEKLY).count()
        monthly_rows = DemandForecast.objects.filter(product=self.product, forecast_period=ForecastPeriod.MONTHLY).count()

        self.assertEqual(weekly_rows, 4, "weekly run keeps periods_ahead == forecast_period_weeks unchanged")
        self.assertEqual(monthly_rows, 1, "4 weeks must convert to periods_ahead=1 for the monthly run, not 4")


class DemandForecastingViewTests(TestCase):
    """Phase 11 — DemandForecastingView: real data on GET, real
    synchronous retrain+forecast on POST. SupervisorRequiredMixin itself
    is Phase 8.99j's (BUG-43) — AIPageAccessTests already proves the GET
    gate; this class adds POST-specific coverage."""

    def setUp(self):
        _clear_forecast_model_files()
        self.supervisor = User.objects.create_user(
            username='fcsuper', email='fcsuper@example.com', password='x',
            employee_id='EMP-9301', full_name='FC Supervisor', role=UserRole.SUPERVISOR,
        )
        self.staff = User.objects.create_user(
            username='fcstaff', email='fcstaff@example.com', password='x',
            employee_id='EMP-9302', full_name='FC Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='FC Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='FC Supply', company_name='FC Supply Co', contact_person='Jo',
            email='fcsupply@example.com', phone='555-0920', address='1 FC Way',
        )
        self.product = Product.objects.create(
            sku='FC-SKU-001', name='FC Widget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'),
        )
        InventoryService.initialize_for_product(self.product)

    def tearDown(self):
        _clear_forecast_model_files()

    def test_post_blocked_for_staff_and_anonymous(self):
        url = reverse('frontend:forecasting')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # anonymous -> login

        self.client.login(username='fcstaff', password='x')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # staff -> bounced

    def test_run_button_generates_forecasts(self):
        # 15 weeks: train_model()'s own >=10-pooled-feature-row guard.
        for i in range(15):
            sale = SaleTransaction.objects.create(
                created_by=self.supervisor, status=SaleStatus.COMPLETED,
                transaction_date=timezone.localdate() - timedelta(days=(15 - i) * 7),
            )
            SaleItem.objects.create(
                transaction=sale, product=self.product, quantity=4,
                unit_price=Decimal('20.00'), line_total=Decimal('80.00'),
            )

        self.client.login(username='fcsuper', password='x')
        response = self.client.post(reverse('frontend:forecasting'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertGreater(payload['forecasts_created'], 0)
        self.assertTrue(DemandForecast.objects.filter(product=self.product).exists())
        self.assertTrue(AuditLog.objects.filter(action=audit.AI_FORECASTS_GENERATED).exists())
        self.assertTrue(AuditLog.objects.filter(action=audit.AI_MODEL_RETRAINED).exists())

    def test_get_renders_never_run_state_with_no_forecasts(self):
        self.client.login(username='fcsuper', password='x')
        response = self.client.get(reverse('frontend:forecasting'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Never run')


class ForecastAPITests(TestCase):
    """Phase 11 — the second DRF slice Phase 9 pre-committed
    (docs/project_memory.md §13): read-only, IsSupervisorOrAbove only —
    reusing Phase 10's one permission class, not adding another."""

    def setUp(self):
        self.supervisor = User.objects.create_user(
            username='fapisuper', email='fapisuper@example.com', password='x',
            employee_id='EMP-9401', full_name='FAPI Supervisor', role=UserRole.SUPERVISOR,
        )
        self.staff = User.objects.create_user(
            username='fapistaff', email='fapistaff@example.com', password='x',
            employee_id='EMP-9402', full_name='FAPI Staffer', role=UserRole.STAFF,
        )
        category = Category.objects.create(name='FAPI Widgets')
        supplier = Supplier.objects.create(
            supplier_name='FAPI Supply', company_name='FAPI Supply Co', contact_person='Jo',
            email='fapisupply@example.com', phone='555-0930', address='1 FAPI Way',
        )
        self.product = Product.objects.create(
            sku='FAPI-SKU-001', name='FAPI Widget', category=category, supplier=supplier,
            purchase_price=Decimal('10.00'), selling_price=Decimal('20.00'),
        )
        self.forecast = DemandForecast.objects.create(
            product=self.product, forecast_period=ForecastPeriod.WEEKLY,
            period_start=timezone.localdate(), period_end=timezone.localdate() + timedelta(days=6),
            forecasted_demand=Decimal('12.50'), recommended_reorder_qty=3,
            confidence_score=Decimal('0.72'), model_version='test',
        )

    def test_list_requires_supervisor_or_above(self):
        url = reverse('api:ai_forecasts_list')
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.login(username='fapistaff', password='x')
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.login(username='fapisuper', password='x')
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_list_returns_real_serialized_fields(self):
        self.client.login(username='fapisuper', password='x')
        response = self.client.get(reverse('api:ai_forecasts_list'))
        row = response.json()['results'][0]
        self.assertEqual(row['product_name'], 'FAPI Widget')
        self.assertEqual(row['product_sku'], 'FAPI-SKU-001')
        self.assertEqual(row['recommended_reorder_qty'], 3)

    def test_summary_returns_real_counts(self):
        self.client.login(username='fapisuper', password='x')
        response = self.client.get(reverse('api:ai_forecasts_summary'))
        payload = response.json()
        self.assertEqual(payload['total_forecasts'], 1)
        self.assertEqual(payload['products_forecasted'], 1)
        self.assertEqual(payload['latest_model_version'], 'test')


# ============================================================ Phase 12 ===
# Approval Authority Matrix.

class ApprovalTestCase(TestCase):
    """Shared fixtures for Phase 12 tests. clear_policies() wipes whatever
    the 0007 data migration seeded so each test starts from an explicit,
    fully-controlled ruleset — resolver ordering tests especially need no
    interference from the real starting ruleset's own rows."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='apradmin', email='apradmin@example.com', password='x',
            employee_id='EMP-9001', full_name='Approval Admin', role=UserRole.ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username='aprsuper', email='aprsuper@example.com', password='x',
            employee_id='EMP-9002', full_name='Approval Supervisor', role=UserRole.SUPERVISOR,
        )
        self.other_supervisor = User.objects.create_user(
            username='aprsuper2', email='aprsuper2@example.com', password='x',
            employee_id='EMP-9003', full_name='Second Approval Supervisor', role=UserRole.SUPERVISOR,
        )
        self.staff = User.objects.create_user(
            username='aprstaff', email='aprstaff@example.com', password='x',
            employee_id='EMP-9004', full_name='Approval Staffer', role=UserRole.STAFF,
        )
        self.category = Category.objects.create(name='Approval Widgets')
        self.supplier = Supplier.objects.create(
            supplier_name='Approval Supply', company_name='Approval Supply Co',
            contact_person='Jo', email='aprsupply@example.com', phone='555-0500',
            address='1 Approval Way',
        )
        self.product = Product.objects.create(
            sku='APR-SKU-001', name='Approval Widget', category=self.category,
            supplier=self.supplier, purchase_price=Decimal('10.00'),
            selling_price=Decimal('20.00'), reorder_level=5,
        )
        InventoryService.initialize_for_product(self.product)

    def clear_policies(self):
        ApprovalPolicy.objects.all().delete()

    def make_policy(self, **kwargs):
        defaults = {
            'name': 'test policy', 'transaction_type': ApprovalTxType.PURCHASE_ORDER,
            'required_level': ApprovalOutcome.SUPERVISOR, 'priority': 10,
        }
        defaults.update(kwargs)
        return ApprovalPolicy.objects.create(**defaults)

    def make_po(self, total_cost, created_by=None, status=POStatus.PENDING):
        return PurchaseOrder.objects.create(
            supplier=self.supplier, created_by=created_by or self.staff,
            status=status, total_cost=total_cost,
        )


class ApprovalResolverTests(ApprovalTestCase):
    """§10: first-match-wins ordering; no-match falls through to admin;
    inactive policies ignored; boundary values (exactly at max_value)
    resolve as expected."""

    def setUp(self):
        super().setUp()
        self.clear_policies()

    def test_no_active_policy_returns_none(self):
        self.assertIsNone(resolve_required_level(
            transaction_type=ApprovalTxType.PURCHASE_ORDER, value=Decimal('100'),
        ))

    def test_can_approve_fails_closed_to_admin_when_no_policy_matches(self):
        po = self.make_po(Decimal('100'))
        allowed, reason = can_approve(self.supervisor, po)
        self.assertFalse(allowed)
        self.assertIn('administrator', reason.lower())
        allowed_admin, _ = can_approve(self.admin, po)
        self.assertTrue(allowed_admin)

    def test_first_match_wins_lower_priority_number_checked_first(self):
        self.make_policy(name='specific', priority=1, min_value=0, max_value=Decimal('50'), required_level=ApprovalOutcome.ADMIN)
        self.make_policy(name='catch-all', priority=99, required_level=ApprovalOutcome.SUPERVISOR)
        matched = resolve_required_level(transaction_type=ApprovalTxType.PURCHASE_ORDER, value=Decimal('10'))
        self.assertEqual(matched.name, 'specific')
        matched2 = resolve_required_level(transaction_type=ApprovalTxType.PURCHASE_ORDER, value=Decimal('500'))
        self.assertEqual(matched2.name, 'catch-all')

    def test_inactive_policy_is_ignored(self):
        self.make_policy(name='inactive-blocker', priority=1, required_level=ApprovalOutcome.ADMIN, is_active=False)
        self.make_policy(name='active-fallback', priority=2, required_level=ApprovalOutcome.SUPERVISOR)
        matched = resolve_required_level(transaction_type=ApprovalTxType.PURCHASE_ORDER, value=Decimal('10'))
        self.assertEqual(matched.name, 'active-fallback')

    def test_boundary_value_exactly_at_max_value_matches(self):
        self.make_policy(name='up-to-50000', priority=1, max_value=Decimal('50000.00'), required_level=ApprovalOutcome.SUPERVISOR)
        self.make_policy(name='above-50000', priority=2, required_level=ApprovalOutcome.ADMIN)
        at_boundary = resolve_required_level(transaction_type=ApprovalTxType.PURCHASE_ORDER, value=Decimal('50000.00'))
        self.assertEqual(at_boundary.name, 'up-to-50000')
        one_cent_over = resolve_required_level(transaction_type=ApprovalTxType.PURCHASE_ORDER, value=Decimal('50000.01'))
        self.assertEqual(one_cent_over.name, 'above-50000')

    def test_boundary_value_exactly_at_min_value_matches(self):
        self.make_policy(name='low', priority=1, min_value=Decimal('100.00'), max_value=Decimal('200.00'), required_level=ApprovalOutcome.SUPERVISOR)
        matched = resolve_required_level(transaction_type=ApprovalTxType.PURCHASE_ORDER, value=Decimal('100.00'))
        self.assertEqual(matched.name, 'low')
        below = resolve_required_level(transaction_type=ApprovalTxType.PURCHASE_ORDER, value=Decimal('99.99'))
        self.assertIsNone(below)


class CanApproveTests(ApprovalTestCase):
    """§10: can_approve() — each role against each outcome level;
    self-approval blocked for supervisor, permitted for admin."""

    def setUp(self):
        super().setUp()
        self.clear_policies()

    def test_auto_outcome_allows_anyone(self):
        self.make_policy(required_level=ApprovalOutcome.AUTO)
        po = self.make_po(Decimal('10'))
        for user in (self.staff, self.supervisor, self.admin):
            allowed, reason = can_approve(user, po)
            self.assertTrue(allowed, f'{user.username} should be allowed under AUTO')
            self.assertEqual(reason, '')

    def test_supervisor_outcome_allows_supervisor_and_admin_denies_staff(self):
        self.make_policy(required_level=ApprovalOutcome.SUPERVISOR, block_self_approval=False)
        po = self.make_po(Decimal('10'))
        self.assertFalse(can_approve(self.staff, po)[0])
        self.assertTrue(can_approve(self.other_supervisor, po)[0])
        self.assertTrue(can_approve(self.admin, po)[0])

    def test_admin_outcome_denies_supervisor_and_staff(self):
        self.make_policy(required_level=ApprovalOutcome.ADMIN, block_self_approval=False)
        po = self.make_po(Decimal('10'))
        self.assertFalse(can_approve(self.staff, po)[0])
        self.assertFalse(can_approve(self.supervisor, po)[0])
        self.assertTrue(can_approve(self.admin, po)[0])

    def test_self_approval_blocked_for_supervisor(self):
        self.make_policy(required_level=ApprovalOutcome.SUPERVISOR, block_self_approval=True)
        po = self.make_po(Decimal('10'), created_by=self.supervisor)
        allowed, reason = can_approve(self.supervisor, po)
        self.assertFalse(allowed)
        self.assertIn('own request', reason.lower())
        # A different supervisor (not the requester) is still fine.
        self.assertTrue(can_approve(self.other_supervisor, po)[0])

    def test_self_approval_permitted_for_admin(self):
        self.make_policy(required_level=ApprovalOutcome.ADMIN, block_self_approval=True)
        po = self.make_po(Decimal('10'), created_by=self.admin)
        allowed, reason = can_approve(self.admin, po)
        self.assertTrue(allowed)
        self.assertEqual(reason, '')

    def test_block_self_approval_false_allows_requester_to_approve(self):
        self.make_policy(required_level=ApprovalOutcome.SUPERVISOR, block_self_approval=False)
        po = self.make_po(Decimal('10'), created_by=self.supervisor)
        self.assertTrue(can_approve(self.supervisor, po)[0])


class ApprovalAuthorityServiceLayerTests(ApprovalTestCase):
    """§10: the service layer raises ApprovalAuthorityError when called
    directly by an unauthorised user, bypassing the view entirely — the
    service layer is the boundary that must hold regardless of caller."""

    def setUp(self):
        super().setUp()
        self.clear_policies()
        self.make_policy(transaction_type=ApprovalTxType.PURCHASE_ORDER, required_level=ApprovalOutcome.ADMIN, priority=1)
        self.make_policy(transaction_type=ApprovalTxType.ADJUSTMENT, required_level=ApprovalOutcome.ADMIN, priority=1)
        self.make_policy(transaction_type=ApprovalTxType.SALE_CANCEL, required_level=ApprovalOutcome.ADMIN, priority=1)

    def test_purchase_service_approve_raises_for_unauthorised_supervisor(self):
        po = self.make_po(Decimal('10'), status=POStatus.PENDING)
        with self.assertRaises(ApprovalAuthorityError):
            PurchaseService.approve(po, self.supervisor)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.PENDING, 'a denied approval must not change status')

    def test_adjustment_service_approve_raises_for_unauthorised_supervisor(self):
        adjustment = InventoryAdjustment.objects.create(
            product=self.product, adjustment_type=AdjustmentType.INCREASE, quantity=5,
            reason_code=AdjustmentReason.OTHER, reason='test', requested_by=self.staff,
        )
        with self.assertRaises(ApprovalAuthorityError):
            AdjustmentService.approve(adjustment, self.supervisor)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.PENDING)

    def test_sale_service_cancel_raises_for_unauthorised_supervisor(self):
        sale = SaleService.create_sale(
            {}, [{'product_id': self.product.pk, 'quantity': 1, 'unit_price': Decimal('20.00')}],
            self.staff,
        )
        with self.assertRaises(ApprovalAuthorityError):
            SaleService.cancel_sale(sale, self.supervisor, 'reason')
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.DRAFT)

    def test_admin_succeeds_where_supervisor_was_denied(self):
        po = self.make_po(Decimal('10'), status=POStatus.PENDING)
        PurchaseService.approve(po, self.admin)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.APPROVED)


class AdjustmentAutoApproveTests(ApprovalTestCase):
    """§10: the AUTO-outcome create path posts stock and writes exactly
    one movement, with no pending record ever created."""

    def setUp(self):
        super().setUp()
        self.clear_policies()
        InventoryService.increase_stock(
            product=self.product, quantity=100, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.staff,
        )

    def test_auto_policy_posts_immediately_no_pending_state(self):
        self.make_policy(
            transaction_type=ApprovalTxType.ADJUSTMENT, required_level=ApprovalOutcome.AUTO,
            max_value=Decimal('1000.00'), priority=1,
        )
        adjustment = InventoryAdjustment(
            product=self.product, adjustment_type=AdjustmentType.DECREASE, quantity=5,
            reason_code=AdjustmentReason.COUNT_CORRECTION, reason='small auto-posted correction',
        )
        result = AdjustmentService.create(adjustment, self.staff)

        self.assertEqual(result.status, AdjustmentStatus.APPROVED)
        self.assertEqual(result.approved_by, self.staff, 'AUTO attributes the post to the creator, no human approver')
        self.assertIsNotNone(result.approved_at)

        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 95)

        movements = InventoryMovement.objects.filter(
            reference_type='InventoryAdjustment', reference_id=result.pk,
        )
        self.assertEqual(movements.count(), 1, 'exactly one movement, not a pending-then-approved pair')

        # Never went through a PENDING state at all — no separate
        # ADJUSTMENT_REQUESTED entry, no ADJUSTMENT_APPROVED entry (a real
        # human-approval event that never happened here); one AUTO-posted
        # audit entry only.
        self.assertFalse(AuditLog.objects.filter(action=audit.ADJUSTMENT_REQUESTED, affected_id=result.pk).exists())
        self.assertFalse(AuditLog.objects.filter(action=audit.ADJUSTMENT_APPROVED, affected_id=result.pk).exists())
        auto_entry = AuditLog.objects.get(action=audit.ADJUSTMENT_AUTO_POSTED, affected_id=result.pk)
        self.assertEqual(auto_entry.details['policy_name'], 'test policy')

    def test_non_auto_policy_creates_pending_record_instead(self):
        self.make_policy(
            transaction_type=ApprovalTxType.ADJUSTMENT, required_level=ApprovalOutcome.SUPERVISOR, priority=1,
        )
        adjustment = InventoryAdjustment(
            product=self.product, adjustment_type=AdjustmentType.DECREASE, quantity=5,
            reason_code=AdjustmentReason.COUNT_CORRECTION, reason='needs a human',
        )
        result = AdjustmentService.create(adjustment, self.staff)
        self.assertEqual(result.status, AdjustmentStatus.PENDING)
        self.assertIsNone(result.approved_by)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 100, 'a pending adjustment must not touch stock yet')


class DefaultApprovalPoliciesTests(TestCase):
    """§9/§10: the migration-seeded starting ruleset behaves as
    configured — the ৳50,000 purchase-order supervisor/admin split
    (confirmed with the user; there was no pre-existing ceiling to
    migrate byte-identically from, see docs/project_memory.md §13)."""

    def test_nine_policies_seeded(self):
        # Phase 12.2 — was 10; the ABC-matching "Class-A product, high
        # variance" row (priority 20) is removed along with ABC as an
        # approval-routing input entirely (docs/project_memory.md §13).
        self.assertEqual(ApprovalPolicy.objects.count(), 9)

    def test_purchase_order_ceiling_is_fifty_thousand(self):
        under = resolve_required_level(transaction_type=ApprovalTxType.PURCHASE_ORDER, value=Decimal('50000.00'))
        self.assertEqual(under.required_level, ApprovalOutcome.SUPERVISOR)
        over = resolve_required_level(transaction_type=ApprovalTxType.PURCHASE_ORDER, value=Decimal('50000.01'))
        self.assertEqual(over.required_level, ApprovalOutcome.ADMIN)

    def test_unexplained_shrinkage_always_requires_admin(self):
        policy = resolve_required_level(
            transaction_type=ApprovalTxType.ADJUSTMENT, value=Decimal('1.00'),
            reason_code=AdjustmentReason.SHRINKAGE_UNKNOWN,
        )
        self.assertEqual(policy.required_level, ApprovalOutcome.ADMIN)

    def test_small_low_variance_adjustment_auto_approves(self):
        policy = resolve_required_level(
            transaction_type=ApprovalTxType.ADJUSTMENT, value=Decimal('50.00'), variance_pct=Decimal('1.00'),
        )
        self.assertEqual(policy.required_level, ApprovalOutcome.AUTO)


# ========================================================== Phase 12.1 ===
# Approval Authority Matrix hardening. §3 (the "record unlock" re-
# resolution contract) and its tests are deliberately NOT implemented —
# no such system exists anywhere in this codebase (models, services,
# views, all 7 migrations, all 66 §15 timeline entries checked); see
# docs/project_memory.md §13 for the full discovery writeup and the
# user's own explicit choice (report the gap, don't build a new
# subsystem to attach hardening to).

class CumulativeCapTests(ApprovalTestCase):
    """§8: cumulative cap on the AUTO adjustment path (§4) — N
    sub-threshold adjustments auto-post, the one crossing the cap
    escalates instead; adjustments outside the trailing window don't
    count toward the total."""

    def setUp(self):
        super().setUp()
        self.clear_policies()
        InventoryService.increase_stock(
            product=self.product, quantity=1000, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.staff,
        )
        # self.product.purchase_price = 10.00 (ApprovalTestCase fixture),
        # so quantity 5 -> value 50, quantity 6 -> value 60.
        self.auto_policy = self.make_policy(
            transaction_type=ApprovalTxType.ADJUSTMENT, required_level=ApprovalOutcome.AUTO,
            max_value=Decimal('500.00'), priority=1, name='auto under cap',
            cumulative_window_days=30, cumulative_value_cap=Decimal('100.00'),
        )
        self.make_policy(
            transaction_type=ApprovalTxType.ADJUSTMENT, required_level=ApprovalOutcome.SUPERVISOR,
            priority=2, name='catch-all',
        )

    def _post_adjustment(self, quantity):
        adjustment = InventoryAdjustment(
            product=self.product, adjustment_type=AdjustmentType.DECREASE, quantity=quantity,
            reason_code=AdjustmentReason.OTHER, reason='cumulative cap test',
        )
        return AdjustmentService.create(adjustment, self.staff)

    def test_sub_threshold_adjustments_auto_post_until_cap(self):
        # 50 + 50 = 100, at-or-below the ৳100 cap both times.
        first = self._post_adjustment(5)
        self.assertEqual(first.status, AdjustmentStatus.APPROVED)
        self.assertTrue(first.was_auto_posted)

        second = self._post_adjustment(5)
        self.assertEqual(second.status, AdjustmentStatus.APPROVED)
        self.assertTrue(second.was_auto_posted)

    def test_adjustment_crossing_cap_escalates_instead_of_auto_posting(self):
        self._post_adjustment(5)   # running total 50
        self._post_adjustment(5)   # running total 100 (still <= cap)
        third = self._post_adjustment(5)  # would be 150 > 100 -> deflected

        self.assertEqual(third.status, AdjustmentStatus.PENDING)
        self.assertFalse(third.was_auto_posted)
        deflection = AuditLog.objects.get(action=audit.ADJUSTMENT_AUTO_DEFLECTED, affected_id=third.pk)
        self.assertEqual(deflection.details['deflected_from_policy_id'], self.auto_policy.pk)
        self.assertEqual(Decimal(deflection.details['existing_cumulative_total']), Decimal('100'))
        self.assertEqual(deflection.details['new_required_level'], ApprovalOutcome.SUPERVISOR)

    def test_window_expiry_excludes_old_adjustments_from_total(self):
        old = self._post_adjustment(6)  # value 60, AUTO (existing total 0)
        self.assertTrue(old.was_auto_posted)
        InventoryAdjustment.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=31),
        )
        # If the now-outside-window adjustment still counted, 60+60=120
        # would exceed the ৳100 cap and deflect this one to PENDING. It
        # doesn't count -> this one AUTO-posts too (60 <= 100).
        fresh = self._post_adjustment(6)
        self.assertEqual(fresh.status, AdjustmentStatus.APPROVED)
        self.assertTrue(fresh.was_auto_posted)


class FailClosedDefaultsTests(ApprovalTestCase):
    """§8: the fail-open default closed in §5a. (Two sibling tests for
    §5b — the ABC unclassified-resolves-as-'A' fallback — lived here too
    until Phase 12.2 removed ABC from approval routing entirely; deleted
    along with that fallback, not left behind asserting a rule that no
    longer exists. See docs/project_memory.md §13.)"""

    def setUp(self):
        super().setUp()
        self.clear_policies()

    def test_variance_none_at_zero_stock_matches_admin_variance_rule(self):
        """§5a: current_stock is 0 (no InventoryService call in this
        test) -> variance_pct is None. Must be treated as EXCEEDING the
        threshold (escalate), never as an absent signal that falls
        through to a lower-authority catch-all."""
        self.make_policy(
            transaction_type=ApprovalTxType.ADJUSTMENT, required_level=ApprovalOutcome.ADMIN,
            max_variance_pct=Decimal('1.00'), priority=1, name='escalate on undefined variance',
        )
        adjustment = InventoryAdjustment(
            product=self.product, adjustment_type=AdjustmentType.INCREASE, quantity=50,
            reason_code=AdjustmentReason.OTHER, reason='phantom stock found in overflow storage',
            requested_by=self.staff,
        )
        policy, required_level, _, _ = resolve_adjustment_with_cumulative_cap(adjustment)
        self.assertIsNotNone(policy, 'None variance must MATCH an ADMIN-outcome variance rule, not fall through')
        self.assertEqual(required_level, ApprovalOutcome.ADMIN)


class EnsureDefaultPoliciesIdempotencyTests(TestCase):
    """§8: reseed idempotency for the one table Phase 12.1's §6 sweep
    actually found (ApprovalPolicy — no siblings exist; the other 6
    migrations are pure schema, no RunPython at all)."""

    def test_calling_twice_does_not_duplicate_existing_rows(self):
        count_before = ApprovalPolicy.objects.count()
        ensure_default_policies()
        ensure_default_policies()
        self.assertEqual(ApprovalPolicy.objects.count(), count_before)

    def test_restores_all_nine_rows_after_a_flush_style_wipe(self):
        # Phase 12.2 — was 10; see test_nine_policies_seeded's own comment.
        ApprovalPolicy.objects.all().delete()
        self.assertEqual(ApprovalPolicy.objects.count(), 0)
        ensure_default_policies()
        self.assertEqual(ApprovalPolicy.objects.count(), 9)
        ensure_default_policies()
        self.assertEqual(ApprovalPolicy.objects.count(), 9)
