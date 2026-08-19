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
from frontend.classification import classify_product
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
    SystemSettings,
)
from frontend.notifications import notify_supervisors, notify_user
from frontend.pricing import calculate_line_total


class InsufficientStockError(Exception):
    pass


class InventoryService:
    """The only place InventoryRecord/Product stock fields and
    InventoryMovement rows are written. docs/07_INVENTORY.md."""

    @classmethod
    @transaction.atomic
    def initialize_for_product(cls, product):
        """Create the InventoryRecord for a newly-catalogued product, at
        zero stock, with NO InventoryMovement row (Phase 5.5 — see
        docs/bugsfound.md's Phase 5.5 entry). Creating a product means a
        catalog entry now exists, not that stock arrived — that only
        happens for real when a Purchase Order is received (increase_stock(),
        called from PurchaseService.receive_items()). A zero-to-zero change
        is not a movement, so unlike increase_stock()/decrease_stock() this
        deliberately writes nothing to the immutable ledger — their whole
        contract ("log a real movement with a real cause") doesn't apply to
        "nothing happened yet." Matches 03_PRODUCTS.md's own
        product_create_view, which creates InventoryRecord with the implied
        current_stock=0 default and nothing else, and
        docs/project_memory.md §13's existing architecture decision that
        InventoryMovement rows are only ever an internal side effect of
        purchase-receive/sale/adjustment-approval."""
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
        """Phase 8.99e — ProductUpdateView editing a product's
        reorder_level must keep InventoryRecord.reorder_level (an
        undocumented duplicate of Product.reorder_level, see
        docs/project_memory.md §6) in sync, without writing a ledger row:
        a reorder-threshold change isn't a stock movement, the same
        reasoning initialize_for_product() above already applies to
        product creation. Also recomputes status via update_status() —
        moving the threshold can flip LOW_STOCK/AVAILABLE on its own, even
        with current_stock unchanged. Kept here, not in the view, since
        this class's own docstring already claims sole ownership of
        writing InventoryRecord fields; a no-op if no InventoryRecord
        exists yet (shouldn't happen in practice — every product gets one
        at creation — but this method has no reason to assume it does)."""
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

    Phase 8.99c narrowed cancel() to draft/pending only — see
    docs/project_memory.md §13 for the full disclosure of why this
    overrides 05_PURCHASES.md's own "any state -> CANCELLED" state
    machine (originally implemented as such in Phase 3.4 / BUG-25).

    PO *creation* (and its documented inactive-supplier/inactive-product
    checks) still isn't part of this service per the docs or the original
    Phase 3 scope — creation happens elsewhere, not implemented here."""

    # Phase 8.99c — narrowed from (DRAFT, PENDING, APPROVED, PARTIAL) to
    # just the two pre-approval states. An approved PO is a commitment
    # already made to the supplier; APPROVED/PARTIAL/RECEIVED/CANCELLED
    # are now all terminal to cancel() (see §13). RECEIVED/CANCELLED/
    # REJECTED were already terminal.
    _CANCELLABLE_STATUSES = (POStatus.DRAFT, POStatus.PENDING)

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
    def cancel(cls, po, cancelled_by, reason):
        """Phase 8.99c: cancellable only from DRAFT/PENDING (see §13 — this
        overrides 05_PURCHASES.md's original "any state -> CANCELLED").
        Never calls InventoryService — a draft/pending PO has never had
        anything received against it (receive_items() only runs from
        APPROVED/PARTIAL, both now cancel-ineligible), so there is no stock
        to leave untouched or restore; "Cancelled PO does NOT affect
        inventory" still holds, just more simply than before. `reason` is
        now required (ReasonForm, same as reject()) and stored alongside
        who/when, mirroring rejected_reason's own shape.

        13_AUDIT.md defines a PO_CANCELLED constant (used below), but
        11_NOTIFICATIONS.md has no 'po_cancelled' notification type — so
        this logs but does not notify, matching what's actually documented
        rather than inventing a type (unchanged from Phase 3.4 / BUG-25)."""
        if po.status not in cls._CANCELLABLE_STATUSES:
            raise ValueError(f"Cannot cancel a PO with status '{po.status}'.")
        po.status = POStatus.CANCELLED
        po.cancelled_reason = reason
        po.cancelled_by = cancelled_by
        po.cancelled_at = timezone.now()
        po.save(update_fields=['status', 'cancelled_reason', 'cancelled_by', 'cancelled_at', 'updated_at'])
        audit.log_action(cancelled_by, audit.PO_CANCELLED, 'purchases', affected_id=po.pk, status='success')
        return po


class SaleService:
    """docs/06_SALES.md, extended by Phase 8.99b to mirror
    PurchaseService's approval workflow — see docs/project_memory.md §13
    for the full disclosure of why this diverges from 06_SALES.md's
    original one-step create-and-deduct model. create_sale() now creates
    a DRAFT with no stock effect at all; submit_for_approval() moves it to
    PENDING; approve_sale() is the ONLY place a sale's stock actually
    moves (mirrors PurchaseService.receive_items() being the only place a
    PO's stock moves — never on approval, there). reject_sale() and
    cancel_sale() are both pre-approval-only; a COMPLETED sale can never
    be cancelled or rejected by this service — Phase 8.99c confirmed and
    locked this rule in (see §13)."""

    # Phase 8.99b — mirrors PurchaseService._CANCELLABLE_STATUSES, but
    # deliberately narrower: a PO can still be cancelled from APPROVED
    # (stock hasn't moved yet either, at that point) — a Sale has no
    # analogous post-approval-but-pre-stock-movement state at all, since
    # approval and stock movement are the same instant here (see
    # SaleStatus's own docstring). So the only cancellable states are the
    # two that exist before that instant.
    _CANCELLABLE_STATUSES = (SaleStatus.DRAFT, SaleStatus.PENDING)

    @classmethod
    @transaction.atomic
    def create_sale(cls, sale_data, items_data, created_by):
        """
        sale_data: {customer_name, notes}
        items_data: [{product_id, quantity, unit_price, discount, tax}, ...]

        Phase 8.99b: creates a DRAFT only — no stock check, no
        InventoryService call, no InventoryMovement row. The
        inactive-product check stays here (a create-time concern: a
        product shouldn't be addable to a new sale at all once inactive)
        — availability, by contrast, moves to approve_sale(), since only
        approval actually commits stock (see Step 3's own
        `docs/project_memory.md` §13/§15 finding on why draft sales can't
        meaningfully reserve stock).
        """
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
            # Phase 8.98c: tax is never trusted from items_data even if a
            # caller happens to pass one — always the product's own
            # tax_rate, the single real source. discount stays a genuine
            # per-line/per-transaction value (unlike tax, this one really
            # is a per-sale negotiation, not a product property).
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
        """Phase 8.99b — mirrors PurchaseService.submit_for_approval()
        exactly, including firing the notification a Supervisor/Admin
        needs to ever learn this sale exists (NotificationType.
        SALE_PENDING, added this phase specifically because without it
        the approval gate has no trigger — see §13)."""
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
        """Phase 8.99b — the ONLY place a sale's stock actually moves.
        Re-validates availability here rather than trusting whatever was
        true at draft/submit time — two drafts against the same limited
        stock can each look satisfiable at creation and only one can
        actually succeed here; this is the documented, deliberate
        consequence, not a bug (see docs/project_memory.md §13/§15's
        "stock-at-approval" finding). Pre-validates ALL items first
        (same pattern the old one-step create_sale() used, moved here
        wholesale) so a failure never partially deducts stock — this
        whole method is wrapped in one transaction, but the pre-check
        also gives a clean, single, specific error instead of an
        arbitrary mid-loop one."""
        if sale.status != SaleStatus.PENDING:
            raise ValueError("Only pending sales can be approved.")

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
        # SALE_COMPLETED (11_NOTIFICATIONS.md, pre-existing) previously had
        # no reference code anywhere that actually fired it and no
        # documented recipient — this approval step is the first genuine
        # use of it, with the obvious recipient: the person who created
        # the sale, mirroring PO_APPROVED's notify_user(po.created_by, ...).
        notify_user(
            sale.created_by, NotificationType.SALE_COMPLETED, f'Sale {sale.invoice_number} Approved',
            f'Your sale {sale.invoice_number} has been approved and completed.',
            link=f'/sales/',
        )
        audit.log_action(approved_by, audit.SALE_APPROVED, 'sales', affected_id=sale.pk, status='success')

        # Phase 10 — explicit synchronous call, not the documented
        # post_save(SaleTransaction) signal (docs/project_memory.md §13
        # has the full rejection reasoning). This is the one real moment a
        # sale changes a product's classification-relevant history: items
        # already exist (fetched above) and stock has already moved
        # (decrease_stock() already ran, above). One settings fetch shared
        # across every line item, not one per item.
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
        """Phase 8.99b — mirrors PurchaseService.reject(). No
        notification type exists for "sale rejected" (11_NOTIFICATIONS.md
        lists sale_completed but nothing for rejection) — logs but does
        not notify, matching this project's own established precedent for
        exactly this shape of gap (AdjustmentService.reject()'s identical
        reasoning) rather than inventing a second undocumented type this
        same phase, on top of the one (SALE_PENDING) already disclosed as
        load-bearing. SALE_PENDING was the load-bearing exception; this
        one is purely informational, same as the precedent it follows."""
        if sale.status != SaleStatus.PENDING:
            raise ValueError("Only pending sales can be rejected.")
        sale.status = SaleStatus.REJECTED
        sale.rejected_reason = reason
        sale.save(update_fields=['status', 'rejected_reason', 'updated_at'])
        audit.log_action(rejected_by, audit.SALE_REJECTED, 'sales', affected_id=sale.pk, status='success')
        return sale

    @classmethod
    @transaction.atomic
    def cancel_sale(cls, sale, cancelled_by, reason):
        """Phase 8.99b restricted this to pre-approval states only (DRAFT/
        PENDING); Phase 8.99c locks that rule in for good (see this
        class's own docstring and §13) — a COMPLETED sale can never be
        cancelled by this method. 06_SALES.md's original "cancellation
        restores stock via increase_stock()" no longer applies to what
        this method actually does: a draft/pending sale has deducted no
        stock at all (that only happens in approve_sale() now), so there
        is nothing to restore. Post-completion corrections (returns,
        mis-keyed quantities, damaged goods) go through an Inventory
        Adjustment instead — see §13, "post-completion correction path."

        `reason` is now required (ReasonForm, same as reject_sale()) and
        stored alongside who/when, mirroring rejected_reason's own shape."""
        if sale.status not in cls._CANCELLABLE_STATUSES:
            raise ValueError(f"Cannot cancel a sale with status '{sale.status}'.")
        sale.status = SaleStatus.CANCELLED
        sale.cancelled_reason = reason
        sale.cancelled_by = cancelled_by
        sale.cancelled_at = timezone.now()
        sale.save(update_fields=['status', 'cancelled_reason', 'cancelled_by', 'cancelled_at', 'updated_at'])
        audit.log_action(cancelled_by, audit.SALE_CANCELLED, 'sales', affected_id=sale.pk, status='success')

        # Phase 10 — reclassify here too, per instruction. Functionally a
        # no-op today: cancel_sale() only ever runs on DRAFT/PENDING sales
        # (the docstring above), which never reached approve_sale(), so
        # no stock has moved and no SaleItem here has ever counted toward
        # get_last_sold_date()/calculate_turnover_rate() (both filter
        # status=COMPLETED) — classify_product() will recompute the exact
        # same result it already has. Included anyway: keeps classified_at
        # a genuine "last touched" timestamp, costs one cheap query per
        # line item, and needs no future code change if a classification
        # signal ever does start reading non-completed sales.
        classification_settings = SystemSettings.get_settings()
        for item in sale.items.select_related('product').all():
            classify_product(item.product, settings_obj=classification_settings)

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
