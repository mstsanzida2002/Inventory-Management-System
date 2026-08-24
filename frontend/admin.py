from django.contrib import admin
from django.db.utils import DatabaseError

from frontend.models import (
    AuditLog,
    Category,
    DemandForecast,
    InventoryAdjustment,
    InventoryClassification,
    InventoryMovement,
    InventoryRecord,
    Notification,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SaleItem,
    SaleTransaction,
    Supplier,
    SystemSettings,
    User,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'full_name', 'email', 'employee_id', 'role', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'employee_id', 'full_name')
    list_filter = ('role', 'is_active', 'is_staff')
    ordering = ('username',)
    # AbstractBaseUser's `password` field renders as a plain editable CharField
    # under a bare ModelAdmin (no ReadOnlyPasswordHashField), which would let
    # someone overwrite it with cleartext, bypassing set_password() hashing.
    # Read-only here until this model is wired up with a proper auth admin.
    readonly_fields = ('password', 'last_login', 'created_at', 'updated_at')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    search_fields = ('name',)
    list_filter = ('is_active',)
    ordering = ('name',)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'supplier_name', 'contact_person', 'email', 'phone', 'is_active')
    search_fields = ('company_name', 'supplier_name', 'email')
    list_filter = ('is_active',)
    ordering = ('company_name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'category', 'supplier', 'current_stock', 'reorder_level', 'selling_price', 'is_active')
    search_fields = ('sku', 'barcode', 'name', 'brand')
    list_filter = ('category', 'supplier', 'unit', 'is_active')
    ordering = ('sku',)
    list_select_related = ('category', 'supplier')


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'supplier', 'status', 'created_by', 'order_date', 'total_cost')
    search_fields = ('po_number',)
    list_filter = ('status', 'supplier')
    ordering = ('-order_date',)
    list_select_related = ('supplier', 'created_by', 'approved_by')


@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = ('purchase_order', 'product', 'ordered_qty', 'received_qty', 'unit_price', 'line_total')
    search_fields = ('purchase_order__po_number', 'product__sku', 'product__name')
    list_filter = ('purchase_order__status',)
    ordering = ('-created_at',)
    list_select_related = ('purchase_order', 'product')


@admin.register(SaleTransaction)
class SaleTransactionAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer_name', 'created_by', 'status', 'transaction_date', 'total_amount')
    search_fields = ('invoice_number', 'customer_name')
    list_filter = ('status',)
    ordering = ('-transaction_date',)
    list_select_related = ('created_by',)


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'product', 'quantity', 'unit_price', 'line_total')
    search_fields = ('transaction__invoice_number', 'product__sku', 'product__name')
    ordering = ('-created_at',)
    list_select_related = ('transaction', 'product')


@admin.register(InventoryRecord)
class InventoryRecordAdmin(admin.ModelAdmin):
    list_display = ('product', 'current_stock', 'reorder_level', 'status', 'total_value')
    search_fields = ('product__sku', 'product__name')
    list_filter = ('status',)
    ordering = ('product__sku',)
    list_select_related = ('product',)


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    """Read-only in admin: the model's own docstring documents this as an
    immutable ledger ('never update or delete'), but — unlike AuditLog —
    that invariant isn't enforced in code here (see admin_notes below).
    Enforcing it at the admin layer at least keeps this specific view honest."""
    list_display = ('product', 'movement_type', 'quantity_change', 'stock_before', 'stock_after', 'reference_type', 'reference_id', 'performed_by', 'created_at')
    search_fields = ('product__sku', 'product__name', 'reference_type')
    list_filter = ('movement_type',)
    ordering = ('-created_at',)
    list_select_related = ('product', 'performed_by')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InventoryAdjustment)
class InventoryAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('product', 'adjustment_type', 'quantity', 'status', 'requested_by', 'approved_by', 'created_at')
    search_fields = ('product__sku', 'product__name', 'reason')
    list_filter = ('adjustment_type', 'status')
    ordering = ('-created_at',)
    list_select_related = ('product', 'requested_by', 'approved_by')


@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = ('product', 'forecast_period', 'period_start', 'period_end', 'forecasted_demand', 'recommended_reorder_qty', 'confidence_score')
    search_fields = ('product__sku', 'product__name', 'model_version')
    list_filter = ('forecast_period',)
    ordering = ('-period_start',)
    list_select_related = ('product',)


@admin.register(InventoryClassification)
class InventoryClassificationAdmin(admin.ModelAdmin):
    list_display = ('product', 'classification', 'stagnation_index', 'confidence', 'turnover_rate', 'last_sold_date', 'days_since_last_sale', 'classified_at')
    search_fields = ('product__sku', 'product__name')
    list_filter = ('classification',)
    ordering = ('-classified_at',)
    list_select_related = ('product',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'type', 'title', 'is_read', 'is_critical', 'created_at')
    search_fields = ('title', 'message', 'recipient__username')
    list_filter = ('type', 'is_read', 'is_critical')
    ordering = ('-created_at',)
    list_select_related = ('recipient',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only in admin: AuditLog.save()/delete() raise a bare
    PermissionError on update/delete (see admin_notes below) rather than a
    Django-recognized exception, so an admin edit/delete attempt would
    otherwise surface as an unhandled 500 instead of a clean permission
    message. Disabling change/delete here avoids that and matches the
    model's own documented immutability."""
    list_display = ('timestamp', 'user', 'action', 'module', 'status', 'affected_id', 'ip_address')
    search_fields = ('action', 'module')
    list_filter = ('module', 'status', 'action')
    ordering = ('-timestamp',)
    list_select_related = ('user',)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    """Registered as a singleton in the admin: the model itself doesn't
    enforce single-row-only (see admin_notes below) — get_settings() is a
    convention, not a constraint — so `has_add_permission` blocks adding a
    second row once one exists, to at least keep the admin UI honest about
    the intended usage."""
    list_display = ('company_name', 'default_reorder_level', 'slow_moving_threshold_days', 'dead_stock_threshold_days', 'session_timeout_seconds', 'email_notifications_enabled')

    def has_add_permission(self, request):
        # Called on every admin page (index, sidebar app list), not just the
        # add view, so a DB error here would take down the whole admin site.
        # Fail open (defer to the default) rather than let the table lookup
        # crash unrelated pages — e.g. before migrations exist.
        try:
            if SystemSettings.objects.exists():
                return False
        except DatabaseError:
            pass
        return super().has_add_permission(request)
