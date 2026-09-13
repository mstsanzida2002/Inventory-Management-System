from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from frontend import audit
from frontend.approvals import can_approve, resolve_adjustment_with_cumulative_cap, resolve_for_transaction
from frontend.classification import classify_product
from frontend.models import (
    AdjustmentStatus,
    AdjustmentType,
    ApprovalOutcome,
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
    SystemSettings,
)
from frontend.notifications import notify_admins, notify_supervisors, notify_user
from frontend.pricing import calculate_line_total

# Rule: reject and cancel use a plain role check; only approve is policy-routed.


class InsufficientStockError(Exception):
    pass


class ApprovalAuthorityError(Exception):
    """Raised in the service layer when frontend.approvals.can_approve()
    or a plain role check denies the acting user."""
    pass


def _notify_pending_audience(required_level, *args, **kwargs):
    # Rule: ADMIN-level notifies admins only; others notify supervisors.
    notify_fn = notify_admins if required_level == ApprovalOutcome.ADMIN else notify_supervisors
    return notify_fn(*args, **kwargs)


class InventoryService:
    """The only place InventoryRecord/Product stock fields and
    InventoryMovement rows are written."""

    @classmethod
    @transaction.atomic
    def initialize_for_product(cls, product):
        """Creates a zero-stock InventoryRecord; writes no movement row."""
        record, _ = InventoryRecord.objects.get_or_create(
            product=product,
            defaults={'current_stock': 0, 'reorder_level': product.reorder_level},
        )
        record.update_status()
        record.save()
        return record

    @classmethod
    @transaction.atomic
    def sync_reorder_level(cls, product):
        """Syncs InventoryRecord.reorder_level from Product; no movement row."""
        try:
            record = InventoryRecord.objects.select_for_update().get(product=product)
        except InventoryRecord.DoesNotExist:
            return None
        record.reorder_level = product.reorder_level
        record.update_status()
        record.save(update_fields=['reorder_level', 'status', 'updated_at'])
        return record

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

        # Rule: low/out-of-stock alerts fire only from decrease_stock.
        if record.status in (InventoryStatus.LOW_STOCK, InventoryStatus.OUT_OF_STOCK):
            cls._send_low_stock_notification(product, record, performed_by)

        return record

    @classmethod
    def _send_low_stock_notification(cls, product, record, performed_by=None):
        # Assumption: performed_by is the real actor, not a system placeholder.
        if record.status == InventoryStatus.OUT_OF_STOCK:
            notify_supervisors(
                notification_type=NotificationType.OUT_OF_STOCK,
                title=f'Out of Stock: {product.name}',
                message=f'{product.name} [{product.sku}] is now out of stock.',
                link=f'/inventory/{product.id}/',
            )
            audit.log_action(
                performed_by, audit.OUT_OF_STOCK_ALERT_SENT, "inventory",
                affected_id=product.pk, status="success",
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
            audit.log_action(
                performed_by, audit.LOW_STOCK_ALERT_SENT, "inventory",
                affected_id=product.pk, status="success",
            )


class PurchaseService:
    """Submit -> approve/reject -> receive; stock moves only on receive."""

    # Rule: only DRAFT/PENDING are cancellable; APPROVED+ is terminal.
    _CANCELLABLE_STATUSES = (POStatus.DRAFT, POStatus.PENDING)

    @classmethod
    @transaction.atomic
    def submit_for_approval(cls, po, submitted_by):
        if po.status != POStatus.DRAFT:
            raise ValueError("Only draft POs can be submitted.")
        po.status = POStatus.PENDING
        po.save(update_fields=['status', 'updated_at'])
        _, required_level, _ = resolve_for_transaction(po)
        _notify_pending_audience(
            required_level,
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

        policy, required_level, _ = resolve_for_transaction(po)
        allowed, reason = can_approve(approved_by, po)
        if not allowed:
            raise ApprovalAuthorityError(reason)

        po.status = POStatus.APPROVED
        po.approved_by = approved_by
        po.approved_at = timezone.now()
        po.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        notify_user(
            po.created_by, NotificationType.PO_APPROVED, f'PO {po.po_number} Approved',
            f'Your purchase order {po.po_number} has been approved.',
            link=f'/purchases/{po.pk}/',
        )
        audit.log_action(
            approved_by, audit.PO_APPROVED, 'purchases', affected_id=po.pk, status='success',
            details={'policy_id': policy.pk if policy else None, 'required_level': required_level},
        )
        return po

    @classmethod
    @transaction.atomic
    def reject(cls, po, rejected_by, reason):
        if po.status != POStatus.PENDING:
            raise ValueError("Only pending POs can be rejected.")

        if not (rejected_by.is_supervisor or rejected_by.is_admin):
            raise ApprovalAuthorityError('Requires supervisor or administrator approval.')

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
        # Rule: receiving logs but never notifies, matching this project's design.
        audit.log_action(
            received_by, audit.PO_RECEIVED, 'purchases', affected_id=po.pk, status='success',
            details={'receive_data': receive_data},
        )
        return po

    @classmethod
    @transaction.atomic
    def cancel(cls, po, cancelled_by, reason):
        """Cancellable only from DRAFT/PENDING; never touches inventory."""
        if po.status not in cls._CANCELLABLE_STATUSES:
            raise ValueError(f"Cannot cancel a PO with status '{po.status}'.")

        if not (cancelled_by.is_supervisor or cancelled_by.is_admin):
            raise ApprovalAuthorityError('Requires supervisor or administrator approval.')

        po.status = POStatus.CANCELLED
        po.cancelled_reason = reason
        po.cancelled_by = cancelled_by
        po.cancelled_at = timezone.now()
        po.save(update_fields=['status', 'cancelled_reason', 'cancelled_by', 'cancelled_at', 'updated_at'])
        audit.log_action(cancelled_by, audit.PO_CANCELLED, 'purchases', affected_id=po.pk, status='success')
        return po


class SaleService:
    """Draft -> submit -> approve; approve_sale() is where stock moves."""

    # Rule: only DRAFT/PENDING are cancellable -- approval moves stock.
    _CANCELLABLE_STATUSES = (SaleStatus.DRAFT, SaleStatus.PENDING)

    @classmethod
    @transaction.atomic
    def create_sale(cls, sale_data, items_data, created_by):
        """Creates a DRAFT sale; no stock effect until approve_sale()."""
        total = 0
        sale = SaleTransaction.objects.create(
            created_by=created_by,
            customer_name=sale_data.get('customer_name', ''),
            notes=sale_data.get('notes', ''),
        )
        for item in items_data:
            product = Product.objects.get(pk=item['product_id'])
            if not product.is_active:
                raise ValueError(f"Product '{product.name}' is inactive and cannot be sold.")
            # Rule: tax always comes from Product.tax_rate, never the caller.
            discount = Decimal(str(item.get('discount', 0)))
            tax = product.tax_rate
            line_total = calculate_line_total(item['unit_price'], item['quantity'], discount, tax)
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

        sale.total_amount = total
        sale.save(update_fields=['total_amount'])
        audit.log_action(created_by, audit.SALE_CREATED, 'sales', affected_id=sale.pk, status='success')
        return sale

    @classmethod
    @transaction.atomic
    def submit_for_approval(cls, sale, submitted_by):
        """Mirrors PurchaseService.submit_for_approval(); notifies supervisors."""
        if sale.status != SaleStatus.DRAFT:
            raise ValueError("Only draft sales can be submitted.")
        sale.status = SaleStatus.PENDING
        sale.save(update_fields=['status', 'updated_at'])
        notify_supervisors(
            NotificationType.SALE_PENDING, f'Sale {sale.invoice_number} Awaiting Approval',
            f'{submitted_by.full_name} submitted {sale.invoice_number} for approval.',
            link=f'/sales/',
        )
        audit.log_action(submitted_by, audit.SALE_SUBMITTED, 'sales', affected_id=sale.pk, status='success')
        return sale

    @classmethod
    @transaction.atomic
    def approve_sale(cls, sale, approved_by):
        """The only place a sale's stock moves; re-validates stock here."""
        if sale.status != SaleStatus.PENDING:
            raise ValueError("Only pending sales can be approved.")
        if not (approved_by.is_supervisor or approved_by.is_admin):
            raise ApprovalAuthorityError('Requires supervisor or administrator approval.')

        items = list(sale.items.select_related('product').all())
        for item in items:
            try:
                record = InventoryRecord.objects.get(product=item.product)
            except InventoryRecord.DoesNotExist:
                raise InsufficientStockError(f"No inventory record for '{item.product.name}'.")
            if record.current_stock < item.quantity:
                raise InsufficientStockError(
                    f"Insufficient stock for '{item.product.name}'. "
                    f"Available: {record.current_stock}, Requested: {item.quantity}"
                )

        for item in items:
            InventoryService.decrease_stock(
                product=item.product,
                quantity=item.quantity,
                movement_type=MovementType.SALE,
                reference_type='SaleTransaction',
                reference_id=sale.pk,
                performed_by=approved_by,
                notes=f'Sale {sale.invoice_number}',
            )

        sale.status = SaleStatus.COMPLETED
        sale.approved_by = approved_by
        sale.approved_at = timezone.now()
        sale.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        notify_user(
            sale.created_by, NotificationType.SALE_COMPLETED, f'Sale {sale.invoice_number} Approved',
            f'Your sale {sale.invoice_number} has been approved and completed.',
            link=f'/sales/',
        )
        audit.log_action(approved_by, audit.SALE_APPROVED, 'sales', affected_id=sale.pk, status='success')

        # Rule: reclassifies synchronously here, not via a model signal.
        classification_settings = SystemSettings.get_settings()
        for item in items:
            classify_product(item.product, settings_obj=classification_settings)
            audit.log_action(
                approved_by, audit.AI_PRODUCT_RECLASSIFIED, 'ai_classification',
                affected_id=item.product.pk, status='success',
                details={'trigger': 'sale_approved', 'sale_id': sale.pk},
            )

        return sale

    @classmethod
    @transaction.atomic
    def reject_sale(cls, sale, rejected_by, reason):
        """Mirrors PurchaseService.reject(); logs but does not notify."""
        if sale.status != SaleStatus.PENDING:
            raise ValueError("Only pending sales can be rejected.")

        if not (rejected_by.is_supervisor or rejected_by.is_admin):
            raise ApprovalAuthorityError('Requires supervisor or administrator approval.')

        sale.status = SaleStatus.REJECTED
        sale.rejected_reason = reason
        sale.save(update_fields=['status', 'rejected_reason', 'updated_at'])
        audit.log_action(rejected_by, audit.SALE_REJECTED, 'sales', affected_id=sale.pk, status='success')
        return sale

    @classmethod
    @transaction.atomic
    def cancel_sale(cls, sale, cancelled_by, reason):
        """Cancellable only pre-approval; corrections go through Adjustment."""
        if sale.status not in cls._CANCELLABLE_STATUSES:
            raise ValueError(f"Cannot cancel a sale with status '{sale.status}'.")

        # Security: cancellation is policy-routed, unlike PO/Adjustment cancel.
        policy, required_level, _ = resolve_for_transaction(sale)
        allowed, denial_reason = can_approve(cancelled_by, sale)
        if not allowed:
            raise ApprovalAuthorityError(denial_reason)

        sale.status = SaleStatus.CANCELLED
        sale.cancelled_reason = reason
        sale.cancelled_by = cancelled_by
        sale.cancelled_at = timezone.now()
        sale.save(update_fields=['status', 'cancelled_reason', 'cancelled_by', 'cancelled_at', 'updated_at'])
        audit.log_action(
            cancelled_by, audit.SALE_CANCELLED, 'sales', affected_id=sale.pk, status='success',
            details={'policy_id': policy.pk if policy else None, 'required_level': required_level},
        )

        # Rule: reclassifies even though currently a no-op for these sales.
        classification_settings = SystemSettings.get_settings()
        for item in sale.items.select_related('product').all():
            classify_product(item.product, settings_obj=classification_settings)
            audit.log_action(
                cancelled_by, audit.AI_PRODUCT_RECLASSIFIED, 'ai_classification',
                affected_id=item.product.pk, status='success',
                details={'trigger': 'sale_cancelled', 'sale_id': sale.pk},
            )

        return sale


class AdjustmentService:
    """Mirrors PurchaseService; AUTO posts immediately, others go PENDING."""

    @classmethod
    @transaction.atomic
    def create(cls, adjustment, requested_by):
        """Resolves policy first; AUTO posts stock immediately, else PENDING."""
        # Rule: an AUTO match can be deflected by the cumulative-value cap.
        adjustment.requested_by = requested_by
        policy, required_level, deflected_from, cumulative_total = resolve_adjustment_with_cumulative_cap(adjustment)
        adjustment.resolved_policy = policy

        if required_level == ApprovalOutcome.AUTO:
            adjustment.status = AdjustmentStatus.APPROVED
            adjustment.approved_by = requested_by
            adjustment.approved_at = timezone.now()
            adjustment.was_auto_posted = True
            adjustment.save()

            movement_kwargs = dict(
                product=adjustment.product,
                quantity=adjustment.quantity,
                movement_type=MovementType.ADJUSTMENT,
                reference_type='InventoryAdjustment',
                reference_id=adjustment.pk,
                performed_by=requested_by,
                notes=f'Auto-approved adjustment ({policy.name}): {adjustment.reason}',
            )
            if adjustment.adjustment_type == AdjustmentType.INCREASE:
                InventoryService.increase_stock(**movement_kwargs)
            else:
                InventoryService.decrease_stock(**movement_kwargs)

            audit.log_action(
                requested_by, audit.ADJUSTMENT_AUTO_POSTED, 'adjustments', affected_id=adjustment.pk,
                status='success', details={
                    'quantity': adjustment.quantity, 'type': adjustment.adjustment_type,
                    'policy_id': policy.pk, 'policy_name': policy.name,
                },
            )
            return adjustment

        adjustment.status = AdjustmentStatus.PENDING
        adjustment.save()
        audit.log_action(
            requested_by, audit.ADJUSTMENT_REQUESTED, 'adjustments',
            affected_id=adjustment.pk, status='success',
        )
        if deflected_from is not None:
            audit.log_action(
                requested_by, audit.ADJUSTMENT_AUTO_DEFLECTED, 'adjustments', affected_id=adjustment.pk,
                status='success', details={
                    'deflected_from_policy_id': deflected_from.pk,
                    'deflected_from_policy_name': deflected_from.name,
                    'cumulative_window_days': deflected_from.cumulative_window_days,
                    'cumulative_cap': str(deflected_from.cumulative_value_cap),
                    'existing_cumulative_total': str(cumulative_total),
                    'this_adjustment_value': str(Decimal(adjustment.quantity) * adjustment.product.purchase_price),
                    'new_policy_id': policy.pk if policy else None,
                    'new_required_level': required_level,
                },
            )
        _notify_pending_audience(
            required_level,
            NotificationType.ADJ_PENDING, f'Adjustment Pending Approval: {adjustment.product.name}',
            f'{requested_by.full_name} requested a '
            f'{adjustment.get_adjustment_type_display().lower()} adjustment for '
            f'{adjustment.product.name}.',
            link='/adjustments/',
        )
        return adjustment

    @classmethod
    @transaction.atomic
    def approve(cls, adjustment, approved_by):
        if adjustment.status != AdjustmentStatus.PENDING:
            raise ValueError("Only pending adjustments can be approved.")

        policy, required_level, _ = resolve_for_transaction(adjustment)
        allowed, reason = can_approve(approved_by, adjustment)
        if not allowed:
            raise ApprovalAuthorityError(reason)

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
        audit.log_action(
            approved_by, audit.ADJUSTMENT_APPROVED, 'adjustments', affected_id=adjustment.pk,
            status='success', details={
                'quantity': adjustment.quantity, 'type': adjustment.adjustment_type,
                'policy_id': policy.pk if policy else None, 'required_level': required_level,
            },
        )
        return adjustment

    @classmethod
    @transaction.atomic
    def reject(cls, adjustment, rejected_by, reason):
        if adjustment.status != AdjustmentStatus.PENDING:
            raise ValueError("Only pending adjustments can be rejected.")

        if not (rejected_by.is_supervisor or rejected_by.is_admin):
            raise ApprovalAuthorityError('Requires supervisor or administrator approval.')

        adjustment.status = AdjustmentStatus.REJECTED
        adjustment.rejected_reason = reason
        adjustment.save(update_fields=['status', 'rejected_reason', 'updated_at'])
        # Rule: logs but does not notify -- no notification type exists for this.
        audit.log_action(
            rejected_by, audit.ADJUSTMENT_REJECTED, 'adjustments', affected_id=adjustment.pk,
            status='success', details={'quantity': adjustment.quantity, 'type': adjustment.adjustment_type},
        )
        return adjustment
