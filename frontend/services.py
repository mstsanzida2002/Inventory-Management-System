"""
Service layer per docs/05_PURCHASES.md, docs/06_SALES.md, docs/07_INVENTORY.md
(and, for adjustments, this task's own "mirrors Purchase's approval workflow"
instruction — no docs/08_ADJUSTMENTS.md exists, see docs/project_memory.md §12).

This is the ONLY code path allowed to mutate InventoryRecord.current_stock /
Product.current_stock or write InventoryMovement rows — per 07_INVENTORY.md's
own instruction: "All stock quantity changes flow through the service layer."

No views/forms/urls/RBAC wiring yet (that's a later phase) — every method here
assumes the caller is already authorized and passes in the acting user object
directly; nothing here touches request objects (so log_action()'s ip_address
is always None for now).

Every state-changing method here calls frontend.audit.log_action() and, where
a documented notification type exists, frontend.notifications.notify_user()/
notify_supervisors() (Phase 3.5) — matching each doc's own reference code
call-for-call. Where a doc's reference code logs but doesn't notify (or vice
versa), that's matched literally, not an oversight — see the inline comments
at each call site.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from frontend import audit
from frontend.models import (
    AdjustmentStatus,
    AdjustmentType,
    InventoryMovement,
    InventoryRecord,
    InventoryStatus,
    MovementType,
    NotificationType,
    POStatus,
    Product,
    SaleItem,
    SaleStatus,
    SaleTransaction,
)
from frontend.notifications import notify_supervisors, notify_user


class InsufficientStockError(Exception):
    pass


class InventoryService:
    """The only place InventoryRecord/Product stock fields and
    InventoryMovement rows are written. docs/07_INVENTORY.md."""

    @classmethod
    @transaction.atomic
    def increase_stock(cls, product, quantity, movement_type, reference_type,
                        reference_id, performed_by, notes=''):
        """Add stock. Used by: purchase receipt, approved increase-adjustment."""
        record, _ = InventoryRecord.objects.select_for_update().get_or_create(
            product=product,
            defaults={'reorder_level': product.reorder_level},
        )
        stock_before = record.current_stock
        record.current_stock += quantity
        record.total_value = record.current_stock * product.purchase_price
        record.update_status()
        record.save()

        InventoryMovement.objects.create(
            product=product,
            movement_type=movement_type,
            quantity_change=quantity,
            stock_before=stock_before,
            stock_after=record.current_stock,
            reference_type=reference_type,
            reference_id=reference_id,
            performed_by=performed_by,
            notes=notes,
        )
        product.current_stock = record.current_stock
        product.save(update_fields=['current_stock'])
        return record

    @classmethod
    @transaction.atomic
    def decrease_stock(cls, product, quantity, movement_type, reference_type,
                        reference_id, performed_by, notes=''):
        """Remove stock. Used by: sale, approved decrease-adjustment.
        Raises InsufficientStockError if not enough stock — never lets
        current_stock go negative."""
        record = InventoryRecord.objects.select_for_update().get(product=product)

        if record.current_stock < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for '{product.name}'. "
                f"Available: {record.current_stock}, Requested: {quantity}"
            )

        stock_before = record.current_stock
        record.current_stock -= quantity
        record.total_value = record.current_stock * product.purchase_price
        record.update_status()
        record.save()

        InventoryMovement.objects.create(
            product=product,
            movement_type=movement_type,
            quantity_change=-quantity,
            stock_before=stock_before,
            stock_after=record.current_stock,
            reference_type=reference_type,
            reference_id=reference_id,
            performed_by=performed_by,
            notes=notes,
        )
        product.current_stock = record.current_stock
        product.save(update_fields=['current_stock'])

        # 07_INVENTORY.md's own reference code fires this from
        # decrease_stock (never from increase_stock) — check low/out-of-
        # stock and notify.
        if record.status in (InventoryStatus.LOW_STOCK, InventoryStatus.OUT_OF_STOCK):
            cls._send_low_stock_notification(product, record)

        return record

    @classmethod
    def _send_low_stock_notification(cls, product, record):
        if record.status == InventoryStatus.OUT_OF_STOCK:
            notify_supervisors(
                notification_type=NotificationType.OUT_OF_STOCK,
                title=f'Out of Stock: {product.name}',
                message=f'{product.name} [{product.sku}] is now out of stock.',
                link=f'/inventory/{product.id}/',
            )
        else:
            notify_supervisors(
                notification_type=NotificationType.LOW_STOCK,
                title=f'Low Stock Alert: {product.name}',
                message=(
                    f'{product.name} [{product.sku}] has {record.current_stock} '
                    f'units remaining (reorder level: {record.reorder_level}).'
                ),
                link=f'/inventory/{product.id}/',
            )


class PurchaseService:
    """docs/05_PURCHASES.md. submit -> approve/reject -> receive (partial
    delivery supported). Stock increases ONLY on receive, never on approval.
    cancel() (Phase 3.4 / BUG-25) is available from any non-terminal state.

    PO *creation* (and its documented inactive-supplier/inactive-product
    checks) still isn't part of this service per the docs or the original
    Phase 3 scope — creation happens elsewhere, not implemented here."""

    # RECEIVED/CANCELLED/REJECTED are terminal — 05_PURCHASES.md's state
    # machine only draws a cancel arrow out of the in-progress states.
    _CANCELLABLE_STATUSES = (POStatus.DRAFT, POStatus.PENDING, POStatus.APPROVED, POStatus.PARTIAL)

    @classmethod
    @transaction.atomic
    def submit_for_approval(cls, po, submitted_by):
        if po.status != POStatus.DRAFT:
            raise ValueError("Only draft POs can be submitted.")
        po.status = POStatus.PENDING
        po.save(update_fields=['status', 'updated_at'])
        notify_supervisors(
            NotificationType.PO_PENDING, f'PO {po.po_number} Awaiting Approval',
            f'{submitted_by.full_name} submitted {po.po_number} for approval.',
            link=f'/purchases/{po.pk}/',
        )
        audit.log_action(submitted_by, audit.PO_SUBMITTED, 'purchases', affected_id=po.pk, status='success')
        return po

    @classmethod
    @transaction.atomic
    def approve(cls, po, approved_by):
        if po.status != POStatus.PENDING:
            raise ValueError("Only pending POs can be approved.")
        po.status = POStatus.APPROVED
        po.approved_by = approved_by
        po.approved_at = timezone.now()
        po.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        notify_user(
            po.created_by, NotificationType.PO_APPROVED, f'PO {po.po_number} Approved',
            f'Your purchase order {po.po_number} has been approved.',
            link=f'/purchases/{po.pk}/',
        )
        audit.log_action(approved_by, audit.PO_APPROVED, 'purchases', affected_id=po.pk, status='success')
        return po

    @classmethod
    @transaction.atomic
    def reject(cls, po, rejected_by, reason):
        if po.status != POStatus.PENDING:
            raise ValueError("Only pending POs can be rejected.")
        po.status = POStatus.REJECTED
        po.rejected_reason = reason
        po.save(update_fields=['status', 'rejected_reason', 'updated_at'])
        notify_user(
            po.created_by, NotificationType.PO_REJECTED, f'PO {po.po_number} Rejected',
            f'Your PO {po.po_number} was rejected. Reason: {reason}',
            link=f'/purchases/{po.pk}/',
        )
        audit.log_action(rejected_by, audit.PO_REJECTED, 'purchases', affected_id=po.pk, status='success')
        return po

    @classmethod
    @transaction.atomic
    def receive_items(cls, po, receive_data, received_by):
        """receive_data: [{'item_id': X, 'received_qty': Y}, ...]"""
        if po.status not in (POStatus.APPROVED, POStatus.PARTIAL):
            raise ValueError("Only approved or partially received POs can be received.")

        for entry in receive_data:
            item = po.items.get(pk=entry['item_id'])
            additional_qty = entry['received_qty']

            remaining = item.ordered_qty - item.received_qty
            if additional_qty > remaining:
                raise ValueError(
                    f"Cannot receive {additional_qty} units for {item.product.name}. "
                    f"Only {remaining} remaining."
                )

            InventoryService.increase_stock(
                product=item.product,
                quantity=additional_qty,
                movement_type=MovementType.PURCHASE,
                reference_type='PurchaseOrder',
                reference_id=po.pk,
                performed_by=received_by,
                notes=f'Received from PO {po.po_number}',
            )
            item.received_qty += additional_qty
            item.save(update_fields=['received_qty'])

        all_items = po.items.all()
        if all(i.received_qty >= i.ordered_qty for i in all_items):
            po.status = POStatus.RECEIVED
        else:
            po.status = POStatus.PARTIAL
        po.save(update_fields=['status', 'updated_at'])
        # 05_PURCHASES.md's receive_items only calls log_action, no notify —
        # matched literally, not an omission.
        audit.log_action(
            received_by, audit.PO_RECEIVED, 'purchases', affected_id=po.pk, status='success',
            details={'receive_data': receive_data},
        )
        return po

    @classmethod
    @transaction.atomic
    def cancel(cls, po, cancelled_by):
        """05_PURCHASES.md: "Any state -> CANCELLED" / "Cancelled PO does
        NOT affect inventory." Never calls InventoryService — if the PO was
        PARTIAL, whatever was already received via receive_items() stays
        received (those movements already happened and are correctly
        recorded); cancel() only marks the remainder as not coming. Pure
        status change, no stock side effect from any prior state.

        13_AUDIT.md defines a PO_CANCELLED constant (used below), but
        11_NOTIFICATIONS.md has no 'po_cancelled' notification type and no
        cancel() method exists in 05_PURCHASES.md's own reference code to
        begin with (see BUG-25) — so this logs but does not notify,
        matching what's actually documented rather than inventing a type."""
        if po.status not in cls._CANCELLABLE_STATUSES:
            raise ValueError(f"Cannot cancel a PO with status '{po.status}'.")
        po.status = POStatus.CANCELLED
        po.save(update_fields=['status', 'updated_at'])
        audit.log_action(cancelled_by, audit.PO_CANCELLED, 'purchases', affected_id=po.pk, status='success')
        return po


class SaleService:
    """docs/06_SALES.md. All stock availability is pre-validated (and
    nothing persisted) before any row is created, so a failed sale never
    partially deducts stock. Cancellation restores stock for every item."""

    @classmethod
    @transaction.atomic
    def create_sale(cls, sale_data, items_data, created_by):
        """
        sale_data: {customer_name, notes}
        items_data: [{product_id, quantity, unit_price, discount, tax}, ...]
        """
        # 1. Pre-validate ALL stock before creating anything.
        for item in items_data:
            product = Product.objects.get(pk=item['product_id'])
            if not product.is_active:
                raise ValueError(f"Product '{product.name}' is inactive and cannot be sold.")
            try:
                record = InventoryRecord.objects.get(product=product)
            except InventoryRecord.DoesNotExist:
                raise InsufficientStockError(f"No inventory record for '{product.name}'.")
            if record.current_stock < item['quantity']:
                raise InsufficientStockError(
                    f"Insufficient stock for '{product.name}'. "
                    f"Available: {record.current_stock}, Requested: {item['quantity']}"
                )

        # 2. Create transaction header.
        sale = SaleTransaction.objects.create(
            created_by=created_by,
            customer_name=sale_data.get('customer_name', ''),
            notes=sale_data.get('notes', ''),
        )

        # 3. Create line items + deduct stock.
        total = 0
        for item in items_data:
            product = Product.objects.get(pk=item['product_id'])
            # 06_SALES.md's reference code divides a plain int default (0)
            # by 100, producing a float — Decimal * float raises TypeError.
            # Coerce to Decimal first so this works whether discount/tax are
            # omitted, passed as int/float, or passed as Decimal already.
            discount = Decimal(str(item.get('discount', 0)))
            tax = Decimal(str(item.get('tax', 0)))
            line_total = (item['unit_price'] * item['quantity']) * (1 - discount / 100) * (1 + tax / 100)
            total += line_total

            SaleItem.objects.create(
                transaction=sale,
                product=product,
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                discount=discount,
                tax=tax,
                line_total=line_total,
            )
            InventoryService.decrease_stock(
                product=product,
                quantity=item['quantity'],
                movement_type=MovementType.SALE,
                reference_type='SaleTransaction',
                reference_id=sale.pk,
                performed_by=created_by,
                notes=f'Sale {sale.invoice_number}',
            )

        sale.total_amount = total
        sale.save(update_fields=['total_amount'])
        # 06_SALES.md's create_sale only calls log_action, no notify — matched
        # literally. (11_NOTIFICATIONS.md lists a 'sale_completed' type but no
        # reference code anywhere actually fires it, and no recipient is
        # documented for it — not invented here.)
        audit.log_action(created_by, audit.SALE_CREATED, 'sales', affected_id=sale.pk, status='success')
        return sale

    @classmethod
    @transaction.atomic
    def cancel_sale(cls, sale, cancelled_by):
        if sale.status == SaleStatus.CANCELLED:
            raise ValueError("Sale is already cancelled.")

        for item in sale.items.all():
            InventoryService.increase_stock(
                product=item.product,
                quantity=item.quantity,
                movement_type=MovementType.RETURN,
                reference_type='SaleTransaction',
                reference_id=sale.pk,
                performed_by=cancelled_by,
                notes=f'Cancellation of {sale.invoice_number}',
            )

        sale.status = SaleStatus.CANCELLED
        sale.save(update_fields=['status', 'updated_at'])
        audit.log_action(cancelled_by, audit.SALE_CANCELLED, 'sales', affected_id=sale.pk, status='success')
        return sale


class AdjustmentService:
    """No dedicated doc exists — docs/08_ADJUSTMENTS.md is referenced by
    INDEX.md but missing from disk (see docs/project_memory.md §12).
    Mirrors PurchaseService's approve/reject pattern per this task's own
    instruction. Unlike PurchaseOrder, InventoryAdjustment has no draft
    state (SCHEMA.md defaults status to PENDING on creation) — so there's
    no submit_for_approval equivalent, only approve/reject applied
    directly to an already-pending row."""

    @classmethod
    @transaction.atomic
    def approve(cls, adjustment, approved_by):
        if adjustment.status != AdjustmentStatus.PENDING:
            raise ValueError("Only pending adjustments can be approved.")

        movement_kwargs = dict(
            product=adjustment.product,
            quantity=adjustment.quantity,
            movement_type=MovementType.ADJUSTMENT,
            reference_type='InventoryAdjustment',
            reference_id=adjustment.pk,
            performed_by=approved_by,
            notes=f'Adjustment approved: {adjustment.reason}',
        )
        if adjustment.adjustment_type == AdjustmentType.INCREASE:
            InventoryService.increase_stock(**movement_kwargs)
        else:
            InventoryService.decrease_stock(**movement_kwargs)

        adjustment.status = AdjustmentStatus.APPROVED
        adjustment.approved_by = approved_by
        adjustment.approved_at = timezone.now()
        adjustment.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        notify_user(
            adjustment.requested_by, NotificationType.ADJ_APPROVED,
            f'Adjustment Approved: {adjustment.product.name}',
            f'Your {adjustment.get_adjustment_type_display().lower()} adjustment for '
            f'{adjustment.product.name} has been approved.',
            link=f'/adjustments/{adjustment.pk}/',
        )
        # 13_AUDIT.md's own usage example shows exactly this call shape.
        audit.log_action(
            approved_by, audit.ADJUSTMENT_APPROVED, 'adjustments', affected_id=adjustment.pk,
            status='success', details={'quantity': adjustment.quantity, 'type': adjustment.adjustment_type},
        )
        return adjustment

    @classmethod
    @transaction.atomic
    def reject(cls, adjustment, rejected_by, reason):
        if adjustment.status != AdjustmentStatus.PENDING:
            raise ValueError("Only pending adjustments can be rejected.")
        adjustment.status = AdjustmentStatus.REJECTED
        adjustment.rejected_reason = reason
        adjustment.save(update_fields=['status', 'rejected_reason', 'updated_at'])
        # No 'adj_rejected' notification type exists in 11_NOTIFICATIONS.md's
        # type table (only adj_pending/adj_approved are listed) — logs but
        # does not notify, matching what's documented rather than inventing
        # a type, same reasoning as PurchaseService.cancel() above.
        audit.log_action(
            rejected_by, audit.ADJUSTMENT_REJECTED, 'adjustments', affected_id=adjustment.pk,
            status='success', details={'quantity': adjustment.quantity, 'type': adjustment.adjustment_type},
        )
        return adjustment
