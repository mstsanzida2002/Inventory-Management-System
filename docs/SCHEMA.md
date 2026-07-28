# 🗃️ Database Schema
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this before writing any Django model. All fields,
> relationships, constraints, and indexes are defined here.
> The custom User model is in `apps/users/models.py`.

---

## ⚠️ Global Rules

- All primary keys use `BigAutoField` (set as default in AppConfig)
- All models include `created_at` and `updated_at` via abstract base
- Soft-delete pattern used everywhere — never hard-delete business records
- Inventory quantities MUST NEVER go negative (enforced at service layer AND DB constraint)
- Audit logs are IMMUTABLE — no update or delete permitted

---

## Abstract Base Model

```python
# apps/core/models.py  (create this shared module)
from django.db import models

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
```

---

## 1. User Model

```python
# apps/users/models.py
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from apps.core.models import TimeStampedModel

class UserRole(models.TextChoices):
    ADMIN = 'admin', 'System Administrator'
    SUPERVISOR = 'supervisor', 'Inventory Supervisor'
    STAFF = 'staff', 'Inventory Staff'

class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('role', UserRole.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(username, email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    username        = models.CharField(max_length=50, unique=True)
    email           = models.EmailField(unique=True)
    employee_id     = models.CharField(max_length=20, unique=True)
    full_name       = models.CharField(max_length=150)
    contact_number  = models.CharField(max_length=20, blank=True)
    profile_image   = models.ImageField(upload_to='profiles/', blank=True, null=True)
    role            = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.STAFF)
    is_active       = models.BooleanField(default=True)
    is_staff        = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until    = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'employee_id', 'full_name']

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['employee_id']),
            models.Index(fields=['role']),
        ]

    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN

    @property
    def is_supervisor(self):
        return self.role == UserRole.SUPERVISOR

    @property
    def is_staff_member(self):
        return self.role == UserRole.STAFF
```

---

## 2. Category Model

```python
# apps/products/models.py
class Category(TimeStampedModel):
    name        = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'categories'
```

---

## 3. Supplier Model

```python
# apps/suppliers/models.py
class Supplier(TimeStampedModel):
    supplier_name   = models.CharField(max_length=150)
    company_name    = models.CharField(max_length=200)
    contact_person  = models.CharField(max_length=100)
    email           = models.EmailField(unique=True)
    phone           = models.CharField(max_length=20)
    address         = models.TextField()
    is_active       = models.BooleanField(default=True)

    class Meta:
        db_table = 'suppliers'
        indexes = [models.Index(fields=['supplier_name']), models.Index(fields=['company_name'])]

    def __str__(self):
        return f"{self.company_name} ({self.supplier_name})"
```

---

## 4. Product Model

```python
# apps/products/models.py (continued)
class UnitOfMeasurement(models.TextChoices):
    PIECE   = 'pcs', 'Pieces'
    KG      = 'kg', 'Kilograms'
    GRAM    = 'g', 'Grams'
    LITER   = 'L', 'Liters'
    BOX     = 'box', 'Box'
    PACK    = 'pack', 'Pack'
    DOZEN   = 'doz', 'Dozen'

class Product(TimeStampedModel):
    sku             = models.CharField(max_length=50, unique=True)
    barcode         = models.CharField(max_length=100, unique=True, blank=True, null=True)
    name            = models.CharField(max_length=200)
    description     = models.TextField(blank=True)
    brand           = models.CharField(max_length=100, blank=True)
    category        = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    supplier        = models.ForeignKey('suppliers.Supplier', on_delete=models.PROTECT, related_name='products')
    purchase_price  = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price   = models.DecimalField(max_digits=12, decimal_places=2)
    reorder_level   = models.PositiveIntegerField(default=10)
    current_stock   = models.PositiveIntegerField(default=0)   # updated by inventory service
    unit            = models.CharField(max_length=10, choices=UnitOfMeasurement.choices, default=UnitOfMeasurement.PIECE)
    image           = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active       = models.BooleanField(default=True)

    class Meta:
        db_table = 'products'
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['barcode']),
            models.Index(fields=['category']),
            models.Index(fields=['supplier']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"[{self.sku}] {self.name}"
```

---

## 5. Purchase Order Models

```python
# apps/purchases/models.py
class POStatus(models.TextChoices):
    DRAFT       = 'draft', 'Draft'
    PENDING     = 'pending', 'Pending Approval'
    APPROVED    = 'approved', 'Approved'
    REJECTED    = 'rejected', 'Rejected'
    PARTIAL     = 'partial', 'Partially Received'
    RECEIVED    = 'received', 'Fully Received'
    CANCELLED   = 'cancelled', 'Cancelled'

class PurchaseOrder(TimeStampedModel):
    po_number           = models.CharField(max_length=30, unique=True)
    supplier            = models.ForeignKey('suppliers.Supplier', on_delete=models.PROTECT)
    status              = models.CharField(max_length=20, choices=POStatus.choices, default=POStatus.DRAFT)
    created_by          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='purchase_orders_created')
    approved_by         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='purchase_orders_approved', null=True, blank=True)
    order_date          = models.DateField(auto_now_add=True)
    expected_delivery   = models.DateField(null=True, blank=True)
    total_cost          = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes               = models.TextField(blank=True)
    approved_at         = models.DateTimeField(null=True, blank=True)
    rejected_reason     = models.TextField(blank=True)

    class Meta:
        db_table = 'purchase_orders'
        indexes = [models.Index(fields=['po_number']), models.Index(fields=['status'])]

    def save(self, *args, **kwargs):
        if not self.po_number:
            self.po_number = self._generate_po_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_po_number():
        from django.utils import timezone
        import random
        return f"PO-{timezone.now().strftime('%Y%m%d')}-{random.randint(1000,9999)}"

class PurchaseOrderItem(TimeStampedModel):
    purchase_order  = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product         = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    ordered_qty     = models.PositiveIntegerField()
    received_qty    = models.PositiveIntegerField(default=0)
    unit_price      = models.DecimalField(max_digits=12, decimal_places=2)
    discount        = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax             = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total      = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = 'purchase_order_items'

    def save(self, *args, **kwargs):
        self.line_total = (self.unit_price * self.ordered_qty) * (1 - self.discount/100) * (1 + self.tax/100)
        super().save(*args, **kwargs)
```

---

## 6. Sales Models

```python
# apps/sales/models.py
class SaleStatus(models.TextChoices):
    COMPLETED   = 'completed', 'Completed'
    CANCELLED   = 'cancelled', 'Cancelled'

class SaleTransaction(TimeStampedModel):
    invoice_number  = models.CharField(max_length=30, unique=True)
    created_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    customer_name   = models.CharField(max_length=150, blank=True)
    transaction_date= models.DateField(auto_now_add=True)
    status          = models.CharField(max_length=20, choices=SaleStatus.choices, default=SaleStatus.COMPLETED)
    total_amount    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes           = models.TextField(blank=True)

    class Meta:
        db_table = 'sale_transactions'
        indexes = [models.Index(fields=['invoice_number']), models.Index(fields=['transaction_date'])]

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_invoice_number():
        from django.utils import timezone
        import random
        return f"INV-{timezone.now().strftime('%Y%m%d')}-{random.randint(1000,9999)}"

class SaleItem(TimeStampedModel):
    transaction     = models.ForeignKey(SaleTransaction, on_delete=models.CASCADE, related_name='items')
    product         = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    quantity        = models.PositiveIntegerField()
    unit_price      = models.DecimalField(max_digits=12, decimal_places=2)
    discount        = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax             = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total      = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = 'sale_items'
```

---

## 7. Inventory Models

```python
# apps/inventory/models.py
class InventoryStatus(models.TextChoices):
    AVAILABLE   = 'available', 'Available'
    LOW_STOCK   = 'low_stock', 'Low Stock'
    OUT_OF_STOCK= 'out_of_stock', 'Out of Stock'

class InventoryRecord(TimeStampedModel):
    """One record per product — updated in real-time."""
    product         = models.OneToOneField('products.Product', on_delete=models.PROTECT, related_name='inventory')
    current_stock   = models.PositiveIntegerField(default=0)
    reorder_level   = models.PositiveIntegerField(default=10)
    status          = models.CharField(max_length=20, choices=InventoryStatus.choices, default=InventoryStatus.OUT_OF_STOCK)
    total_value     = models.DecimalField(max_digits=16, decimal_places=2, default=0)    # current_stock × purchase_price

    class Meta:
        db_table = 'inventory_records'

    def update_status(self):
        if self.current_stock == 0:
            self.status = InventoryStatus.OUT_OF_STOCK
        elif self.current_stock <= self.reorder_level:
            self.status = InventoryStatus.LOW_STOCK
        else:
            self.status = InventoryStatus.AVAILABLE

class MovementType(models.TextChoices):
    PURCHASE    = 'purchase', 'Purchase Receipt'
    SALE        = 'sale', 'Sale'
    ADJUSTMENT  = 'adjustment', 'Adjustment'
    RETURN      = 'return', 'Return'

class InventoryMovement(TimeStampedModel):
    """Immutable ledger — never update or delete."""
    product         = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='movements')
    movement_type   = models.CharField(max_length=20, choices=MovementType.choices)
    quantity_change = models.IntegerField()     # positive = stock in, negative = stock out
    stock_before    = models.PositiveIntegerField()
    stock_after     = models.PositiveIntegerField()
    reference_type  = models.CharField(max_length=50)   # 'PurchaseOrder', 'SaleTransaction', etc.
    reference_id    = models.PositiveIntegerField()
    performed_by    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    notes           = models.TextField(blank=True)

    class Meta:
        db_table = 'inventory_movements'
        indexes = [
            models.Index(fields=['product', 'created_at']),
            models.Index(fields=['movement_type']),
        ]
```

---

## 8. Inventory Adjustment Model

```python
# apps/adjustments/models.py
class AdjustmentType(models.TextChoices):
    INCREASE = 'increase', 'Stock Increase'
    DECREASE = 'decrease', 'Stock Decrease'

class AdjustmentStatus(models.TextChoices):
    PENDING  = 'pending', 'Pending Approval'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'

class InventoryAdjustment(TimeStampedModel):
    product         = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    adjustment_type = models.CharField(max_length=10, choices=AdjustmentType.choices)
    quantity        = models.PositiveIntegerField()
    reason          = models.TextField()
    status          = models.CharField(max_length=10, choices=AdjustmentStatus.choices, default=AdjustmentStatus.PENDING)
    requested_by    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='adjustments_requested')
    approved_by     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='adjustments_approved', null=True, blank=True)
    approved_at     = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)

    class Meta:
        db_table = 'inventory_adjustments'
```

---

## 9. AI Demand Forecast Model

```python
# apps/ai/forecasting/models.py
class ForecastPeriod(models.TextChoices):
    WEEKLY  = 'weekly', 'Weekly'
    MONTHLY = 'monthly', 'Monthly'

class DemandForecast(TimeStampedModel):
    product                 = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='forecasts')
    forecast_period         = models.CharField(max_length=10, choices=ForecastPeriod.choices)
    period_start            = models.DateField()
    period_end              = models.DateField()
    forecasted_demand       = models.DecimalField(max_digits=10, decimal_places=2)
    recommended_reorder_qty = models.PositiveIntegerField()
    confidence_score        = models.DecimalField(max_digits=5, decimal_places=2)   # 0.00 - 1.00
    actual_demand           = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)   # filled later
    model_version           = models.CharField(max_length=50)

    class Meta:
        db_table = 'demand_forecasts'
        indexes = [models.Index(fields=['product', 'period_start'])]
```

---

## 10. AI Inventory Classification Model

```python
# apps/ai/classification/models.py
class StockClassification(models.TextChoices):
    FAST    = 'fast', 'Fast-Moving'
    SLOW    = 'slow', 'Slow-Moving'
    DEAD    = 'dead', 'Dead Stock'

class InventoryClassification(TimeStampedModel):
    product             = models.OneToOneField('products.Product', on_delete=models.CASCADE, related_name='classification')
    classification      = models.CharField(max_length=10, choices=StockClassification.choices)
    turnover_rate       = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    last_sold_date      = models.DateField(null=True, blank=True)
    days_since_last_sale= models.PositiveIntegerField(default=0)
    recommendation      = models.TextField(blank=True)
    classified_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_classifications'
```

---

## 11. Notification Model

```python
# apps/notifications/models.py
class NotificationType(models.TextChoices):
    LOW_STOCK       = 'low_stock', 'Low Stock Alert'
    OUT_OF_STOCK    = 'out_of_stock', 'Out of Stock'
    PO_PENDING      = 'po_pending', 'Purchase Order Pending Approval'
    PO_APPROVED     = 'po_approved', 'Purchase Order Approved'
    PO_REJECTED     = 'po_rejected', 'Purchase Order Rejected'
    ADJ_PENDING     = 'adj_pending', 'Adjustment Pending Approval'
    ADJ_APPROVED    = 'adj_approved', 'Adjustment Approved'
    AI_REPLENISH    = 'ai_replenish', 'AI Replenishment Recommendation'
    AI_SLOW_STOCK   = 'ai_slow', 'AI Slow-Moving Stock Alert'
    AI_DEAD_STOCK   = 'ai_dead', 'AI Dead Stock Alert'
    PASSWORD_CHANGED= 'password_changed', 'Password Changed'
    SALE_COMPLETED  = 'sale_completed', 'Sale Completed'

class Notification(TimeStampedModel):
    recipient   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    type        = models.CharField(max_length=30, choices=NotificationType.choices)
    title       = models.CharField(max_length=200)
    message     = models.TextField()
    is_read     = models.BooleanField(default=False)
    is_critical = models.BooleanField(default=False)    # critical stays visible until acknowledged
    link        = models.CharField(max_length=300, blank=True)   # optional deep-link URL

    class Meta:
        db_table = 'notifications'
        indexes = [models.Index(fields=['recipient', 'is_read']), models.Index(fields=['created_at'])]
```

---

## 12. Audit Log Model

```python
# apps/audit/models.py
class AuditLog(models.Model):
    """IMMUTABLE — never allow update or delete on this model."""
    user            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action          = models.CharField(max_length=100)       # e.g. "PURCHASE_APPROVED"
    module          = models.CharField(max_length=50)        # e.g. "purchases"
    affected_id     = models.PositiveIntegerField(null=True, blank=True)
    status          = models.CharField(max_length=20)        # "success" | "failure"
    details         = models.JSONField(default=dict)         # extra context
    ip_address      = models.GenericIPAddressField(null=True, blank=True)
    timestamp       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['module', 'timestamp']),
            models.Index(fields=['action']),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("AuditLog records are immutable and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("AuditLog records cannot be deleted.")
```

---

## 13. System Settings Model (Singleton)

```python
# apps/settings_manager/models.py
class SystemSettings(TimeStampedModel):
    """Singleton — only one row should ever exist."""
    company_name        = models.CharField(max_length=200, default='My Company')
    company_logo        = models.ImageField(upload_to='company/', blank=True, null=True)
    company_address     = models.TextField(blank=True)
    company_email       = models.EmailField(blank=True)
    company_phone       = models.CharField(max_length=20, blank=True)
    # Inventory thresholds
    default_reorder_level   = models.PositiveIntegerField(default=10)
    # AI settings
    forecast_period_weeks   = models.PositiveIntegerField(default=4)
    forecast_retrain_days   = models.PositiveIntegerField(default=7)
    slow_moving_threshold_days  = models.PositiveIntegerField(default=60)
    dead_stock_threshold_days   = models.PositiveIntegerField(default=180)
    # Session
    session_timeout_seconds = models.PositiveIntegerField(default=3600)
    # Notifications
    email_notifications_enabled = models.BooleanField(default=True)
    low_stock_email_enabled     = models.BooleanField(default=True)

    class Meta:
        db_table = 'system_settings'

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
```

---

## Migration Order

```bash
python manage.py makemigrations users
python manage.py makemigrations products
python manage.py makemigrations suppliers
python manage.py makemigrations purchases
python manage.py makemigrations sales
python manage.py makemigrations inventory
python manage.py makemigrations adjustments
python manage.py makemigrations notifications
python manage.py makemigrations audit
python manage.py makemigrations settings_manager
python manage.py makemigrations ai_forecasting
python manage.py makemigrations ai_classification
python manage.py migrate
```
