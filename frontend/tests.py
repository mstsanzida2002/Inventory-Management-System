"""
Tests for the Phase 3 service layer (frontend/services.py), verified against
docs/05_PURCHASES.md, docs/06_SALES.md, docs/07_INVENTORY.md, and this task's
own instructions for AdjustmentService (no dedicated doc exists). Phase 3.5
adds tests for the audit/notification retrofit (frontend/audit.py,
frontend/notifications.py). Phase 4 adds tests for real auth (login/logout/
profile, frontend/views.py) and the RBAC decorator/mixin (frontend/decorators.py,
frontend/mixins.py).
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.views import View

from frontend import audit
from frontend.decorators import admin_required, staff_required
from frontend.mixins import AdminRequiredMixin
from frontend.models import (
    AdjustmentStatus,
    AdjustmentType,
    AuditLog,
    Category,
    InventoryAdjustment,
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
    SaleStatus,
    Supplier,
    SystemSettings,
    UserRole,
)
from frontend.services import (
    AdjustmentService,
    InsufficientStockError,
    InventoryService,
    PurchaseService,
    SaleService,
)

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
        po, _ = self.make_po(status=POStatus.PENDING)
        PurchaseService.approve(po, self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.APPROVED)
        self.assertEqual(po.approved_by, self.user)
        self.assertIsNotNone(po.approved_at)

    def test_approve_does_not_touch_stock(self):
        """Proves the critical rule: stock increases ONLY on receipt, never
        on approval."""
        po, _ = self.make_po(status=POStatus.PENDING)
        PurchaseService.approve(po, self.user)
        self.assertFalse(InventoryRecord.objects.filter(product=self.product).exists())
        self.assertEqual(InventoryMovement.objects.filter(product=self.product).count(), 0)

    def test_reject_moves_pending_to_rejected_with_reason(self):
        po, _ = self.make_po(status=POStatus.PENDING)
        PurchaseService.reject(po, self.user, 'Price mismatch')
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.REJECTED)
        self.assertEqual(po.rejected_reason, 'Price mismatch')

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

    def test_create_sale_deducts_stock_and_computes_total(self):
        self.give_stock(20)
        sale = SaleService.create_sale(
            {'customer_name': 'Acme Corp'},
            [{'product_id': self.product.pk, 'quantity': 5, 'unit_price': Decimal('20.00'),
              'discount': 10, 'tax': 0}],
            self.user,
        )
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 15)
        # (20 * 5) * (1 - 0.10) * (1 + 0) = 90.00
        self.assertEqual(sale.total_amount, Decimal('90.00'))
        self.assertEqual(sale.status, SaleStatus.COMPLETED)

    def test_create_sale_rejects_insufficient_stock_and_persists_nothing(self):
        """Proves: stock is pre-validated for ALL items before anything is
        created — a failing sale creates no SaleTransaction and deducts no
        stock at all (not even for items that would have succeeded)."""
        self.give_stock(3)
        with self.assertRaises(InsufficientStockError):
            SaleService.create_sale(
                {}, [{'product_id': self.product.pk, 'quantity': 10, 'unit_price': Decimal('20.00')}],
                self.user,
            )
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 3, "stock must be untouched after a rejected sale")
        self.assertEqual(InventoryMovement.objects.filter(movement_type=MovementType.SALE).count(), 0)

    def test_create_sale_atomic_across_multiple_items(self):
        """Proves atomicity across a multi-line sale: if item 2 fails
        pre-validation, item 1's stock (which alone would have succeeded)
        is not deducted either."""
        other_product = Product.objects.create(
            sku='SKU-002', name='Gadget', category=self.category, supplier=self.supplier,
            purchase_price=Decimal('5.00'), selling_price=Decimal('9.00'),
        )
        self.give_stock(20)  # plenty for self.product
        InventoryService.increase_stock(
            product=other_product, quantity=1, movement_type=MovementType.PURCHASE,
            reference_type='TestSetup', reference_id=0, performed_by=self.user,
        )  # only 1 unit of other_product — not enough for the sale below

        with self.assertRaises(InsufficientStockError):
            SaleService.create_sale(
                {},
                [
                    {'product_id': self.product.pk, 'quantity': 5, 'unit_price': Decimal('20.00')},
                    {'product_id': other_product.pk, 'quantity': 5, 'unit_price': Decimal('9.00')},
                ],
                self.user,
            )
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 20, "item 1 must not be deducted when item 2 fails validation")

    def test_create_sale_rejects_inactive_product(self):
        self.give_stock(20)
        self.product.is_active = False
        self.product.save(update_fields=['is_active'])
        with self.assertRaises(ValueError):
            SaleService.create_sale(
                {}, [{'product_id': self.product.pk, 'quantity': 1, 'unit_price': Decimal('20.00')}],
                self.user,
            )

    def test_sale_then_cancel_restores_correct_quantity(self):
        """Proves: cancellation restores exactly the quantity that was
        deducted, no more and no less."""
        self.give_stock(20)
        sale = SaleService.create_sale(
            {}, [{'product_id': self.product.pk, 'quantity': 7, 'unit_price': Decimal('20.00')}],
            self.user,
        )
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 13)

        SaleService.cancel_sale(sale, self.user)
        record.refresh_from_db()
        self.assertEqual(record.current_stock, 20, "cancellation must restore exactly the sold quantity")
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CANCELLED)

        return_movement = InventoryMovement.objects.filter(movement_type=MovementType.RETURN).get()
        self.assertEqual(return_movement.quantity_change, 7)

    def test_cancel_already_cancelled_sale_raises(self):
        self.give_stock(20)
        sale = SaleService.create_sale(
            {}, [{'product_id': self.product.pk, 'quantity': 1, 'unit_price': Decimal('20.00')}],
            self.user,
        )
        SaleService.cancel_sale(sale, self.user)
        with self.assertRaises(ValueError):
            SaleService.cancel_sale(sale, self.user)


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
        self.give_stock(10)
        adjustment = self.make_adjustment(AdjustmentType.INCREASE, 5)
        AdjustmentService.approve(adjustment, self.user)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.APPROVED)
        self.assertEqual(adjustment.approved_by, self.user)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 15)

    def test_approve_decrease_adjustment_decreases_stock(self):
        self.give_stock(10)
        adjustment = self.make_adjustment(AdjustmentType.DECREASE, 4)
        AdjustmentService.approve(adjustment, self.user)
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
            AdjustmentService.approve(adjustment, self.user)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.PENDING)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 3)

    def test_reject_adjustment_does_not_touch_stock(self):
        self.give_stock(10)
        adjustment = self.make_adjustment(AdjustmentType.DECREASE, 4)
        AdjustmentService.reject(adjustment, self.user, 'Count looks wrong, redo it')
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, AdjustmentStatus.REJECTED)
        self.assertEqual(adjustment.rejected_reason, 'Count looks wrong, redo it')
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 10)

    def test_approve_already_approved_adjustment_raises(self):
        self.give_stock(10)
        adjustment = self.make_adjustment(AdjustmentType.INCREASE, 5)
        AdjustmentService.approve(adjustment, self.user)
        with self.assertRaises(ValueError):
            AdjustmentService.approve(adjustment, self.user)


class PurchaseCancelTests(ServiceTestCase):
    """Phase 3.4 / BUG-25: PurchaseService.cancel()."""

    def make_po(self, ordered_qty=10, status=POStatus.DRAFT):
        po = PurchaseOrder.objects.create(supplier=self.supplier, created_by=self.user, status=status)
        item = PurchaseOrderItem.objects.create(
            purchase_order=po, product=self.product, ordered_qty=ordered_qty,
            unit_price=Decimal('10.00'),
        )
        return po, item

    def test_cancel_from_draft_leaves_stock_untouched(self):
        po, _ = self.make_po(status=POStatus.DRAFT)
        PurchaseService.cancel(po, self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.CANCELLED)
        self.assertFalse(InventoryRecord.objects.filter(product=self.product).exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, 0)

    def test_cancel_from_pending_leaves_stock_untouched(self):
        po, _ = self.make_po(status=POStatus.PENDING)
        PurchaseService.cancel(po, self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.CANCELLED)
        self.assertFalse(InventoryRecord.objects.filter(product=self.product).exists())

    def test_cancel_from_approved_leaves_stock_untouched(self):
        po, _ = self.make_po(status=POStatus.APPROVED)
        PurchaseService.cancel(po, self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.CANCELLED)
        self.assertFalse(InventoryRecord.objects.filter(product=self.product).exists())

    def test_cancel_from_partially_received_leaves_already_received_stock_untouched(self):
        """Proves: cancelling a PARTIAL PO does not reverse the quantity
        already received (05_PURCHASES.md: "Cancelled PO does NOT affect
        inventory") — current_stock stays exactly at whatever the partial
        receipt already set it to, no more, no less."""
        po, item = self.make_po(ordered_qty=10, status=POStatus.APPROVED)
        PurchaseService.receive_items(po, [{'item_id': item.pk, 'received_qty': 4}], self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.PARTIAL)
        record = InventoryRecord.objects.get(product=self.product)
        self.assertEqual(record.current_stock, 4)
        movement_count_before = InventoryMovement.objects.filter(product=self.product).count()

        PurchaseService.cancel(po, self.user)

        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.CANCELLED)
        record.refresh_from_db()
        self.assertEqual(record.current_stock, 4, "stock already received must be untouched by cancel")
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, 4)
        self.assertEqual(
            InventoryMovement.objects.filter(product=self.product).count(), movement_count_before,
            "cancel() must not write any new InventoryMovement row",
        )

    def test_cancel_rejects_already_received(self):
        po, item = self.make_po(ordered_qty=10, status=POStatus.APPROVED)
        PurchaseService.receive_items(po, [{'item_id': item.pk, 'received_qty': 10}], self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, POStatus.RECEIVED)
        with self.assertRaises(ValueError):
            PurchaseService.cancel(po, self.user)

    def test_cancel_rejects_already_cancelled(self):
        po, _ = self.make_po(status=POStatus.DRAFT)
        PurchaseService.cancel(po, self.user)
        with self.assertRaises(ValueError):
            PurchaseService.cancel(po, self.user)


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
        """No 'po_cancelled' notification type is documented — see BUG-25."""
        po, _ = self.make_po(status=POStatus.DRAFT)
        notif_count_before = Notification.objects.count()

        PurchaseService.cancel(po, self.user)

        entry = AuditLog.objects.get(action=audit.PO_CANCELLED)
        self.assertEqual(entry.user, self.user)
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
        self.give_stock(20)
        sale = SaleService.create_sale(
            {}, [{'product_id': self.product.pk, 'quantity': 1, 'unit_price': Decimal('20.00')}],
            self.user,
        )
        notif_count_before = Notification.objects.count()

        SaleService.cancel_sale(sale, self.user)

        entry = AuditLog.objects.get(action=audit.SALE_CANCELLED)
        self.assertEqual(entry.user, self.user)
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
        self.assertEqual(entry.details, {'quantity': 5, 'type': AdjustmentType.INCREASE})

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
    notify_supervisors() retrofit, exercised via a realistic sale."""

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
        SaleService.create_sale(
            {}, [{'product_id': self.product.pk, 'quantity': 5, 'unit_price': Decimal('20.00')}],
            self.user,
        )

        low_stock_notifs = Notification.objects.filter(type=NotificationType.LOW_STOCK)
        recipients = set(low_stock_notifs.values_list('recipient_id', flat=True))
        self.assertEqual(recipients, {self.supervisor.pk, second_supervisor.pk},
                          "every active supervisor/admin must be notified, and only active ones")
        self.assertNotIn(inactive_supervisor.pk, recipients)
        self.assertNotIn(self.user.pk, recipients, "the sale's creator is not a supervisor")

    def test_sale_dropping_stock_to_zero_sends_out_of_stock_not_low_stock(self):
        self.give_stock(5)
        SaleService.create_sale(
            {}, [{'product_id': self.product.pk, 'quantity': 5, 'unit_price': Decimal('20.00')}],
            self.user,
        )
        self.assertTrue(Notification.objects.filter(
            recipient=self.supervisor, type=NotificationType.OUT_OF_STOCK,
        ).exists())
        self.assertFalse(Notification.objects.filter(type=NotificationType.LOW_STOCK).exists())

    def test_sale_leaving_stock_above_reorder_level_sends_no_notification(self):
        self.give_stock(20)
        SaleService.create_sale(
            {}, [{'product_id': self.product.pk, 'quantity': 1, 'unit_price': Decimal('20.00')}],
            self.user,
        )
        self.assertFalse(Notification.objects.exists())


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

    def test_password_change_hashes_new_password_logs_and_notifies(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        self.client.post(reverse('frontend:profile'), {
            'full_name': self.user.full_name, 'new_password': 'New-Password9!',
        })

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('New-Password9!'))
        self.assertTrue(AuditLog.objects.filter(user=self.user, action=audit.PASSWORD_CHANGED, status='success').exists())
        self.assertTrue(Notification.objects.filter(recipient=self.user, type=NotificationType.PASSWORD_CHANGED).exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_weak_new_password_rejected_by_strong_password_validator(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        response = self.client.post(reverse('frontend:profile'), {
            'full_name': self.user.full_name, 'new_password': 'alllowercase1',
        })

        self.assertContains(response, 'uppercase')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Correct-Horse1!'), "password must be unchanged")
        self.assertFalse(AuditLog.objects.filter(user=self.user, action=audit.PASSWORD_CHANGED).exists())

    def test_session_stays_alive_after_password_change(self):
        self.client.login(username='jdoe', password='Correct-Horse1!')
        self.client.post(reverse('frontend:profile'), {
            'full_name': self.user.full_name, 'new_password': 'Another-One2!',
        })
        # update_session_auth_hash() should have kept this session valid —
        # a follow-up authenticated request must not be bounced to login.
        dash = self.client.get(reverse('frontend:dashboard'))
        self.assertTrue(dash.wsgi_request.user.is_authenticated)


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
