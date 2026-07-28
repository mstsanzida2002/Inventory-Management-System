# 🛒 Module 05 — Purchase Management
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when implementing purchase orders.
> The approval workflow and stock update trigger are the most critical parts.
> Stock ONLY increases after `receive` action — not on approval.

---

## Requirements Coverage
`REQ 5.1 → 5.18`

---

## Business Rules

| Rule | Detail |
|---|---|
| PO number | Auto-generated unique: `PO-YYYYMMDD-XXXX` |
| Who creates | Any authenticated staff (admin, supervisor, staff) |
| Who approves | Supervisor or Admin only |
| Stock update timing | ONLY after successful receive — not on approval |
| Partial delivery | Supported — PO stays `partial` until fully received |
| Cancelled PO | Does NOT affect inventory |
| Max receive qty | Cannot exceed ordered quantity per item |
| Inactive supplier | Cannot create PO for inactive supplier |
| Inactive product | Cannot add inactive product to PO |
| History | Purchase history preserved permanently for AI analysis |

## PO Workflow (State Machine)

```
DRAFT ──(submit)──► PENDING ──(approve)──► APPROVED ──(receive)──► RECEIVED
                        │                      │                       │
                    (reject)              (partial recv)           (full recv)
                        │                      │
                        ▼                      ▼
                    REJECTED               PARTIAL
                        
Any state ──(cancel by admin/supervisor)──► CANCELLED
```

---

## Models (see `database/SCHEMA.md` for full definitions)

Key fields: `PurchaseOrder`, `PurchaseOrderItem`

---

## Service Layer

```python
# apps/purchases/services.py
from django.db import transaction
from django.utils import timezone
from apps.inventory.services import InventoryService
from apps.inventory.models import MovementType
from apps.audit.services import log_action
from apps.notifications.services import notify_user, notify_supervisors

class PurchaseService:

    @classmethod
    @transaction.atomic
    def submit_for_approval(cls, po, submitted_by):
        if po.status != 'draft':
            raise ValueError("Only draft POs can be submitted.")
        po.status = 'pending'
        po.save(update_fields=['status', 'updated_at'])
        notify_supervisors('po_pending', f'PO {po.po_number} Awaiting Approval',
                           f'{submitted_by.full_name} submitted {po.po_number} for approval.',
                           link=f'/purchases/{po.pk}/')
        log_action(submitted_by, 'PO_SUBMITTED', 'purchases', affected_id=po.pk, status='success')
        return po

    @classmethod
    @transaction.atomic
    def approve(cls, po, approved_by):
        if po.status != 'pending':
            raise ValueError("Only pending POs can be approved.")
        po.status = 'approved'
        po.approved_by = approved_by
        po.approved_at = timezone.now()
        po.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        notify_user(po.created_by, 'po_approved', f'PO {po.po_number} Approved',
                    f'Your purchase order {po.po_number} has been approved.',
                    link=f'/purchases/{po.pk}/')
        log_action(approved_by, 'PO_APPROVED', 'purchases', affected_id=po.pk, status='success')
        return po

    @classmethod
    @transaction.atomic
    def reject(cls, po, rejected_by, reason):
        if po.status not in ['pending']:
            raise ValueError("Only pending POs can be rejected.")
        po.status = 'rejected'
        po.rejected_reason = reason
        po.save(update_fields=['status', 'rejected_reason', 'updated_at'])
        notify_user(po.created_by, 'po_rejected', f'PO {po.po_number} Rejected',
                    f'Your PO {po.po_number} was rejected. Reason: {reason}',
                    link=f'/purchases/{po.pk}/')
        log_action(rejected_by, 'PO_REJECTED', 'purchases', affected_id=po.pk, status='success')
        return po

    @classmethod
    @transaction.atomic
    def receive_items(cls, po, receive_data, received_by):
        """
        receive_data: [{'item_id': X, 'received_qty': Y}, ...]
        """
        if po.status not in ['approved', 'partial']:
            raise ValueError("Only approved or partially received POs can be received.")

        for entry in receive_data:
            item = po.items.get(pk=entry['item_id'])
            additional_qty = entry['received_qty']

            # Guard: cannot receive more than ordered
            remaining = item.ordered_qty - item.received_qty
            if additional_qty > remaining:
                raise ValueError(
                    f"Cannot receive {additional_qty} units for {item.product.name}. "
                    f"Only {remaining} remaining."
                )

            # Update inventory via service
            InventoryService.increase_stock(
                product=item.product,
                quantity=additional_qty,
                movement_type=MovementType.PURCHASE,
                reference_type='PurchaseOrder',
                reference_id=po.pk,
                performed_by=received_by,
                notes=f'Received from PO {po.po_number}'
            )
            item.received_qty += additional_qty
            item.save(update_fields=['received_qty'])

        # Update PO status
        all_items = po.items.all()
        if all(i.received_qty >= i.ordered_qty for i in all_items):
            po.status = 'received'
        else:
            po.status = 'partial'
        po.save(update_fields=['status', 'updated_at'])
        log_action(received_by, 'PO_RECEIVED', 'purchases', affected_id=po.pk, status='success',
                   details={'receive_data': receive_data})
        return po
```

---

## Views

```python
# apps/purchases/views.py
from django.shortcuts import render, redirect, get_object_or_404
from apps.rbac.decorators import staff_required, supervisor_required
from apps.purchases.models import PurchaseOrder
from apps.purchases.services import PurchaseService

@staff_required
def purchase_list_view(request):
    orders = PurchaseOrder.objects.select_related('supplier', 'created_by').order_by('-created_at')
    # Filter by status
    status = request.GET.get('status')
    if status:
        orders = orders.filter(status=status)
    return render(request, 'purchases/list.html', {'orders': orders})

@staff_required
def purchase_create_view(request):
    if request.method == 'POST':
        # Build PO from POST data, save as draft
        ...
    return render(request, 'purchases/form.html')

@staff_required
def purchase_detail_view(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    return render(request, 'purchases/detail.html', {'po': po})

@supervisor_required
def purchase_approve_view(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    PurchaseService.approve(po, request.user)
    return redirect('purchases:detail', pk=pk)

@supervisor_required
def purchase_reject_view(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    reason = request.POST.get('reason', '')
    PurchaseService.reject(po, request.user, reason)
    return redirect('purchases:detail', pk=pk)

@staff_required
def purchase_receive_view(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        receive_data = []  # Parse from POST
        PurchaseService.receive_items(po, receive_data, request.user)
        return redirect('purchases:detail', pk=pk)
    return render(request, 'purchases/receive.html', {'po': po})
```

---

## DRF API Views

```python
# apps/purchases/api_views.py
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView, RetrieveAPIView
from rest_framework.response import Response
from apps.rbac.permissions import IsAnyStaff, IsSupervisorOrAbove

class PurchaseOrderListCreateView(ListCreateAPIView):
    permission_classes = [IsAnyStaff]
    serializer_class = PurchaseOrderSerializer
    queryset = PurchaseOrder.objects.select_related('supplier', 'created_by').order_by('-created_at')

class PurchaseOrderApproveView(APIView):
    permission_classes = [IsSupervisorOrAbove]

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            PurchaseService.approve(po, request.user)
            return Response({'status': 'approved'})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PurchaseOrderRejectView(APIView):
    permission_classes = [IsSupervisorOrAbove]

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        reason = request.data.get('reason', '')
        try:
            PurchaseService.reject(po, request.user, reason)
            return Response({'status': 'rejected'})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PurchaseOrderReceiveView(APIView):
    permission_classes = [IsAnyStaff]

    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        receive_data = request.data.get('items', [])
        try:
            PurchaseService.receive_items(po, receive_data, request.user)
            return Response({'status': 'received'})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
```

---

## URL Configuration

```python
# apps/purchases/urls.py
urlpatterns = [
    path('', views.purchase_list_view, name='list'),
    path('create/', views.purchase_create_view, name='create'),
    path('<int:pk>/', views.purchase_detail_view, name='detail'),
    path('<int:pk>/approve/', views.purchase_approve_view, name='approve'),
    path('<int:pk>/reject/', views.purchase_reject_view, name='reject'),
    path('<int:pk>/receive/', views.purchase_receive_view, name='receive'),
]
```

---

## Audit Actions

| Action Constant | Triggered When |
|---|---|
| `PO_CREATED` | Purchase order created |
| `PO_SUBMITTED` | PO submitted for approval |
| `PO_APPROVED` | PO approved by supervisor |
| `PO_REJECTED` | PO rejected by supervisor |
| `PO_RECEIVED` | Items received against PO |
| `PO_CANCELLED` | PO cancelled |
