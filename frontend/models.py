"""Models per docs/SCHEMA.md, consolidated from SCHEMA.md's multiple apps
into this single `frontend` app; cross-model FKs use direct class
references, not SCHEMA.md's app-label strings."""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from frontend.pricing import calculate_line_total
from frontend.validators import validate_company_logo


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


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
    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)
    employee_id = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=150)
    contact_number = models.CharField(max_length=20, blank=True)
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.STAFF)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # Workaround: PermissionsMixin hardcodes related_name="user_set", which
    # clashes with django.contrib.auth's own User model -- renamed here.
    groups = models.ManyToManyField('auth.Group', related_name='frontend_user_set', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='frontend_user_permissions_set', blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'employee_id', 'full_name']

    class Meta:
        db_table = 'users'
        indexes = [
            # Assumption: no explicit index for email -- unique=True above
            # already creates one (BUG-13).
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

    # Workaround: AbstractBaseUser provides neither get_full_name() nor
    # get_short_name() (unlike AbstractUser) -- the topbar template needs both.
    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(' ')[0] if self.full_name else self.username

    def get_initials(self):
        parts = self.full_name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        if parts:
            return parts[0][:2].upper()
        return self.username[:2].upper()


class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'categories'


class Supplier(TimeStampedModel):
    supplier_name = models.CharField(max_length=150)
    company_name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'suppliers'
        indexes = [models.Index(fields=['supplier_name']), models.Index(fields=['company_name'])]

    def __str__(self):
        return f"{self.company_name} ({self.supplier_name})"


class UnitOfMeasurement(models.TextChoices):
    PIECE = 'pcs', 'Pieces'
    KG = 'kg', 'Kilograms'
    GRAM = 'g', 'Grams'
    LITER = 'L', 'Liters'
    BOX = 'box', 'Box'
    PACK = 'pack', 'Pack'
    DOZEN = 'doz', 'Dozen'


class Product(TimeStampedModel):
    sku = models.CharField(max_length=50, unique=True)
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    brand = models.CharField(max_length=100, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='products')
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    # Rule: tax is a property of the Product, not entered per-transaction --
    # PurchaseOrderItem/SaleItem still carry their own per-line `tax` too.
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reorder_level = models.PositiveIntegerField(default=10)
    current_stock = models.PositiveIntegerField(default=0)  # updated by inventory service
    unit = models.CharField(max_length=10, choices=UnitOfMeasurement.choices, default=UnitOfMeasurement.PIECE)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'products'
        indexes = [
            # Assumption: no explicit index for sku/barcode -- unique=True
            # above already creates one for each (BUG-13).
            models.Index(fields=['category']),
            models.Index(fields=['supplier']),
            models.Index(fields=['is_active']),
        ]

    def save(self, *args, **kwargs):
        # Workaround: retry only an auto-generated SKU collision (BUG-87) --
        # a manually-typed duplicate must still raise a real IntegrityError.
        if getattr(self, "_sku_autogenerated", False):
            _save_with_generated_unique_number(
                lambda: super(Product, self).save(*args, **kwargs),
                lambda: setattr(self, "sku", self._generate_sku()),
            )
        else:
            super().save(*args, **kwargs)

    @staticmethod
    def _generate_sku():
        import random
        return f"PRD-{timezone.localdate().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

    def __str__(self):
        return f"[{self.sku}] {self.name}"


class POStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PENDING = 'pending', 'Pending Approval'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    PARTIAL = 'partial', 'Partially Received'
    RECEIVED = 'received', 'Fully Received'
    CANCELLED = 'cancelled', 'Cancelled'


_NUMBER_GENERATION_MAX_ATTEMPTS = 5


def _save_with_generated_unique_number(save_call, regenerate):
    """Retries save_call() under transaction.atomic() on IntegrityError,
    calling regenerate() between attempts, up to N tries (BUG-87 collision
    guard)."""
    for attempt in range(_NUMBER_GENERATION_MAX_ATTEMPTS):
        try:
            with transaction.atomic():
                save_call()
            return
        except IntegrityError:
            if attempt == _NUMBER_GENERATION_MAX_ATTEMPTS - 1:
                raise
            regenerate()


class PurchaseOrder(TimeStampedModel):
    po_number = models.CharField(max_length=30, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=POStatus.choices, default=POStatus.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='purchase_orders_created')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='purchase_orders_approved', null=True, blank=True)
    # Assumption: Asia/Dhaka calendar date, set explicitly in save() below --
    # DateField.auto_now_add ignores TIME_ZONE entirely (BUG-47).
    order_date = models.DateField()
    expected_delivery = models.DateField(null=True, blank=True)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)
    # Rule: cancellation mirrors rejection's shape (reason + attributable
    # author/time) -- SCHEMA.md has no cancellation-equivalent field.
    cancelled_reason = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='purchase_orders_cancelled', null=True, blank=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'purchase_orders'
        indexes = [models.Index(fields=['po_number']), models.Index(fields=['status'])]

    def save(self, *args, **kwargs):
        if self.order_date is None:
            self.order_date = timezone.localdate()
        if not self.po_number:
            self.po_number = self._generate_po_number()
            _save_with_generated_unique_number(
                lambda: super(PurchaseOrder, self).save(*args, **kwargs),
                lambda: setattr(self, "po_number", self._generate_po_number()),
            )
        else:
            super().save(*args, **kwargs)

    @staticmethod
    def _generate_po_number():
        import random
        # Workaround: timezone.localdate() -- timezone.now().strftime() would
        # silently format the UTC date, not the Dhaka one (BUG-47).
        return f"PO-{timezone.localdate().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

    @property
    def display_reason(self):
        """The one place list tables, the per-record PDF, and Purchase
        Report all read a rejected/cancelled PO's reason from."""
        if self.status == POStatus.CANCELLED:
            return self.cancelled_reason
        if self.status == POStatus.REJECTED:
            return self.rejected_reason
        return ""


class PurchaseOrderItem(TimeStampedModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    ordered_qty = models.PositiveIntegerField()
    received_qty = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Rule: set once at creation from Product.tax_rate (never trusted from
    # the client) -- a historical snapshot, not recomputed if tax_rate changes.
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = 'purchase_order_items'

    def save(self, *args, **kwargs):
        # Rule: shared formula -- SaleService.create_sale() uses the same one.
        self.line_total = calculate_line_total(self.unit_price, self.ordered_qty, self.discount, self.tax)
        super().save(*args, **kwargs)


class SaleStatus(models.TextChoices):
    # Rule: no separate APPROVED status -- for a Sale, approval IS the moment
    # stock moves, so COMPLETED already means "approved and stock moved."
    DRAFT = 'draft', 'Draft'
    PENDING = 'pending', 'Pending Approval'
    COMPLETED = 'completed', 'Completed'
    REJECTED = 'rejected', 'Rejected'
    CANCELLED = 'cancelled', 'Cancelled'


class SaleTransaction(TimeStampedModel):
    invoice_number = models.CharField(max_length=30, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    customer_name = models.CharField(max_length=150, blank=True)
    # Assumption: Asia/Dhaka calendar date, set explicitly in save() (BUG-47,
    # same fix as PurchaseOrder.order_date).
    transaction_date = models.DateField()
    # Rule: defaults to DRAFT, mirroring PurchaseOrder.status -- a sale is
    # created, then explicitly submitted for approval.
    status = models.CharField(max_length=20, choices=SaleStatus.choices, default=SaleStatus.DRAFT)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    # Rule: mirrors PurchaseOrder.approved_by/approved_at -- not every sale
    # reaches this state.
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='sales_approved', null=True, blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    # Rule: mirrors PurchaseOrder.rejected_reason.
    rejected_reason = models.TextField(blank=True)
    # Rule: mirrors PurchaseOrder.cancelled_reason/cancelled_by/cancelled_at.
    cancelled_reason = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='sales_cancelled', null=True, blank=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sale_transactions'
        indexes = [models.Index(fields=['invoice_number']), models.Index(fields=['transaction_date'])]

    def save(self, *args, **kwargs):
        if self.transaction_date is None:
            self.transaction_date = timezone.localdate()
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()
            # Workaround: same collision retry as PurchaseOrder.save() (BUG-87).
            _save_with_generated_unique_number(
                lambda: super(SaleTransaction, self).save(*args, **kwargs),
                lambda: setattr(self, "invoice_number", self._generate_invoice_number()),
            )
        else:
            super().save(*args, **kwargs)

    @property
    def display_reason(self):
        """Mirrors PurchaseOrder.display_reason."""
        if self.status == SaleStatus.CANCELLED:
            return self.cancelled_reason
        if self.status == SaleStatus.REJECTED:
            return self.rejected_reason
        return ""

    @staticmethod
    def _generate_invoice_number():
        import random
        # Workaround: timezone.localdate(), not timezone.now().strftime()
        # (BUG-47, same fix as PurchaseOrder._generate_po_number()).
        return f"INV-{timezone.localdate().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


class SaleItem(TimeStampedModel):
    transaction = models.ForeignKey(SaleTransaction, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Rule: same as PurchaseOrderItem.tax -- set once from Product.tax_rate,
    # a historical snapshot.
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = 'sale_items'


class InventoryStatus(models.TextChoices):
    AVAILABLE = 'available', 'Available'
    LOW_STOCK = 'low_stock', 'Low Stock'
    OUT_OF_STOCK = 'out_of_stock', 'Out of Stock'


class InventoryRecord(TimeStampedModel):
    """One record per product — updated in real-time."""
    product = models.OneToOneField(Product, on_delete=models.PROTECT, related_name='inventory')
    current_stock = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=10)
    status = models.CharField(max_length=20, choices=InventoryStatus.choices, default=InventoryStatus.OUT_OF_STOCK)
    total_value = models.DecimalField(max_digits=16, decimal_places=2, default=0)  # current_stock × purchase_price

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
    PURCHASE = 'purchase', 'Purchase Receipt'
    SALE = 'sale', 'Sale'
    ADJUSTMENT = 'adjustment', 'Adjustment'
    RETURN = 'return', 'Return'


class InventoryMovement(TimeStampedModel):
    """Immutable ledger — never update or delete."""
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity_change = models.IntegerField()  # positive = in, negative = out
    stock_before = models.PositiveIntegerField()
    stock_after = models.PositiveIntegerField()
    reference_type = models.CharField(max_length=50)  # 'PurchaseOrder', 'SaleTransaction', etc.
    reference_id = models.PositiveIntegerField()
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'inventory_movements'
        indexes = [
            models.Index(fields=['product', 'created_at']),
            models.Index(fields=['movement_type']),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("InventoryMovement records are immutable and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("InventoryMovement records cannot be deleted.")


class AdjustmentType(models.TextChoices):
    INCREASE = 'increase', 'Stock Increase'
    DECREASE = 'decrease', 'Stock Decrease'


class AdjustmentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending Approval'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class AdjustmentReason(models.TextChoices):
    """Structured code alongside the free-text `reason` field, for
    ApprovalPolicy routing -- not a replacement for the narrative."""
    DAMAGE = 'damage', 'Damaged / Broken'
    EXPIRY = 'expiry', 'Expired / Obsolete'
    COUNT_CORRECTION = 'count_correction', 'Physical Count Correction'
    RECEIVING_ERROR = 'receiving_error', 'Receiving Error Correction'
    SHRINKAGE_UNKNOWN = 'shrinkage_unknown', 'Unexplained Loss / Shrinkage'
    OTHER = 'other', 'Other'


class InventoryAdjustment(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    adjustment_type = models.CharField(max_length=10, choices=AdjustmentType.choices)
    quantity = models.PositiveIntegerField()
    # Assumption: default=OTHER only backfills pre-existing rows -- the real
    # form always requires an explicit value (no blank option).
    reason_code = models.CharField(max_length=20, choices=AdjustmentReason.choices, default=AdjustmentReason.OTHER)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=AdjustmentStatus.choices, default=AdjustmentStatus.PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='adjustments_requested')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='adjustments_approved', null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)
    # Rule: SET_NULL, not CASCADE/PROTECT -- deactivating/deleting a policy
    # must never corrupt or block deletion of adjustment history under it.
    resolved_policy = models.ForeignKey(
        'ApprovalPolicy', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resolved_adjustments',
    )
    was_auto_posted = models.BooleanField(default=False)

    class Meta:
        db_table = 'inventory_adjustments'


class ForecastPeriod(models.TextChoices):
    WEEKLY = 'weekly', 'Weekly'
    MONTHLY = 'monthly', 'Monthly'


class DemandForecast(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='forecasts')
    forecast_period = models.CharField(max_length=10, choices=ForecastPeriod.choices)
    period_start = models.DateField()
    period_end = models.DateField()
    forecasted_demand = models.DecimalField(max_digits=10, decimal_places=2)
    recommended_reorder_qty = models.PositiveIntegerField()
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2)  # 0.00 - 1.00
    actual_demand = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # filled later
    model_version = models.CharField(max_length=50)

    class Meta:
        db_table = 'demand_forecasts'
        indexes = [models.Index(fields=['product', 'period_start'])]


class StockClassification(models.TextChoices):
    FAST = 'fast', 'Fast-Moving'
    SLOW = 'slow', 'Slow-Moving'
    DEAD = 'dead', 'Dead Stock'
    # Rule: too young/thinly-observed to trust the other three -- never
    # counted in total_flagged, never notified (see classification.py).
    INSUFFICIENT_DATA = 'insufficient_data', 'Insufficient Data'


class InventoryClassification(TimeStampedModel):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='classification')
    classification = models.CharField(max_length=20, choices=StockClassification.choices)
    turnover_rate = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    last_sold_date = models.DateField(null=True, blank=True)
    # Workaround: nullable, never a numeric stand-in for "never sold" (BUG-72)
    # -- classify_product() stores None when last_sold_date is None.
    days_since_last_sale = models.PositiveIntegerField(null=True, blank=True)
    recommendation = models.TextField(blank=True)
    classified_at = models.DateTimeField(auto_now=True)
    # Assumption: nullable -- a row never run through classify_product()
    # carries no score until the next run recomputes it.
    stagnation_index = models.PositiveSmallIntegerField(null=True, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # 0.00 - 1.00
    recency_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    turnover_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    coverage_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    frequency_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    # Rule: set only when an override rule (not the weighted index) decided
    # the classification -- blank for the ordinary index path.
    flagged_by_rule = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        db_table = 'inventory_classifications'


class NotificationType(models.TextChoices):
    LOW_STOCK = 'low_stock', 'Low Stock Alert'
    OUT_OF_STOCK = 'out_of_stock', 'Out of Stock'
    PO_PENDING = 'po_pending', 'Purchase Order Pending Approval'
    PO_APPROVED = 'po_approved', 'Purchase Order Approved'
    PO_REJECTED = 'po_rejected', 'Purchase Order Rejected'
    ADJ_PENDING = 'adj_pending', 'Adjustment Pending Approval'
    ADJ_APPROVED = 'adj_approved', 'Adjustment Approved'
    AI_REPLENISH = 'ai_replenish', 'AI Replenishment Recommendation'
    AI_SLOW_STOCK = 'ai_slow', 'AI Slow-Moving Stock Alert'
    AI_DEAD_STOCK = 'ai_dead', 'AI Dead Stock Alert'
    PASSWORD_CHANGED = 'password_changed', 'Password Changed'
    SALE_COMPLETED = 'sale_completed', 'Sale Completed'
    # Rule: load-bearing, not informational -- without it, a Supervisor/Admin
    # has no way to learn a sale is awaiting their approval.
    SALE_PENDING = 'sale_pending', 'Sale Pending Approval'


class Notification(TimeStampedModel):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=30, choices=NotificationType.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    is_critical = models.BooleanField(default=False)  # critical stays visible until acknowledged
    link = models.CharField(max_length=300, blank=True)  # optional deep-link URL

    class Meta:
        db_table = 'notifications'
        indexes = [models.Index(fields=['recipient', 'is_read']), models.Index(fields=['created_at'])]


class AuditLog(models.Model):
    """IMMUTABLE — never allow update or delete on this model."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)  # e.g. "PURCHASE_APPROVED"
    module = models.CharField(max_length=50)  # e.g. "purchases"
    affected_id = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20)  # "success" | "failure"
    details = models.JSONField(default=dict)  # extra context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

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


class SystemSettings(TimeStampedModel):
    """Singleton — only one row should ever exist."""
    company_name = models.CharField(max_length=200, default='My Company')
    # Workaround: FileField, not ImageField -- Pillow (ImageField's check)
    # cannot open SVG; validate_company_logo() does the type/size check instead.
    company_logo = models.FileField(upload_to='company/', blank=True, null=True, validators=[validate_company_logo])
    company_address = models.TextField(blank=True)
    company_email = models.EmailField(blank=True)
    company_phone = models.CharField(max_length=20, blank=True)
    company_tax_number = models.CharField(max_length=50, blank=True, verbose_name='Tax / BIN number')
    company_website = models.URLField(blank=True)
    default_reorder_level = models.PositiveIntegerField(default=10)
    forecast_period_weeks = models.PositiveIntegerField(default=4)
    forecast_retrain_days = models.PositiveIntegerField(default=7)
    slow_moving_threshold_days = models.PositiveIntegerField(default=60)
    dead_stock_threshold_days = models.PositiveIntegerField(default=180)
    # Assumption: admin-editable weights/thresholds for the four stagnation-
    # index factors (see classification.py); see clean() for validation.
    weight_recency = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.40'))
    weight_turnover = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.30'))
    weight_coverage = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.20'))
    weight_frequency = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.10'))
    slow_index_threshold = models.PositiveSmallIntegerField(default=40)
    dead_index_threshold = models.PositiveSmallIntegerField(default=70)
    target_days_of_cover = models.PositiveIntegerField(default=90)
    min_observation_days = models.PositiveIntegerField(default=30)
    # Rule: feeds confidence only, not insufficient_data gating (that
    # conflated "unproven" with "dormant" -- see classification.py).
    min_sale_events = models.PositiveIntegerField(default=2)
    # Rule: ceiling for the Coverage factor and the Force-SLOW override --
    # at/above this many days of cover, a product is slow regardless of recency.
    extreme_coverage_days = models.PositiveIntegerField(default=730)
    session_timeout_seconds = models.PositiveIntegerField(default=3600)
    email_notifications_enabled = models.BooleanField(default=True)
    low_stock_email_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = 'system_settings'
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'

    def save(self, *args, **kwargs):
        # Rule: singleton, enforced not just by convention (BUG-21) -- pk=1
        # forces every save onto row 1; a forced INSERT elsewhere raises.
        self.pk = 1
        super().save(*args, **kwargs)

    def clean(self):
        # Rule: weights must sum to exactly 1.00, rejected not silently
        # normalised -- a quiet rescale would desync stored vs. real weights.
        super().clean()
        total = (self.weight_recency or Decimal('0')) + (self.weight_turnover or Decimal('0')) \
            + (self.weight_coverage or Decimal('0')) + (self.weight_frequency or Decimal('0'))
        if total != Decimal('1.00'):
            raise ValidationError(
                f"Classification weights (Recency + Turnover + Coverage + Frequency) "
                f"must sum to exactly 1.00 — currently {total}."
            )

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def get_company_profile(cls):
        """The one accessor every PDF reads company identity through --
        every value is a plain string, never None."""
        obj = cls.get_settings()
        logo_path = ''
        logo_is_svg = False
        if obj.company_logo:
            try:
                logo_path = obj.company_logo.path
                logo_is_svg = logo_path.lower().endswith('.svg')
            except (ValueError, NotImplementedError):
                # Edge: no local path for this storage backend -- same as no
                # logo at all, not an error.
                logo_path = ''
        return {
            'name': obj.company_name or '',
            'logo_path': logo_path,
            'logo_is_svg': logo_is_svg,
            'logo_url': obj.company_logo.url if obj.company_logo else '',
            'address': obj.company_address or '',
            'email': obj.company_email or '',
            'phone': obj.company_phone or '',
            'tax_number': obj.company_tax_number or '',
            'website': obj.company_website or '',
        }


class ApprovalTxType(models.TextChoices):
    PURCHASE_ORDER = 'purchase_order', 'Purchase Order'
    ADJUSTMENT = 'adjustment', 'Inventory Adjustment'
    SALE_CANCEL = 'sale_cancel', 'Sale Cancellation'


class ApprovalOutcome(models.TextChoices):
    AUTO = 'auto', 'Auto-approve (no human approval)'
    SUPERVISOR = 'supervisor', 'Supervisor or Admin'
    ADMIN = 'admin', 'Admin only'


class ApprovalPolicy(TimeStampedModel):
    """Rule: generalises a static role check into a policy engine -- an
    admin defines which transactions a supervisor may approve, by type/
    value/reason, not just by role. Lower `priority` wins within a
    transaction_type; first active match short-circuits
    (frontend.approvals.resolve_required_level()).

    Security: no match -> caller fails closed to ADMIN, never to
    SUPERVISOR/AUTO."""
    name = models.CharField(max_length=120)
    transaction_type = models.CharField(max_length=30, choices=ApprovalTxType.choices)

    # Rule: blank/null on these fields means "matches anything."
    reason_code = models.CharField(max_length=40, blank=True)
    min_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    max_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    max_variance_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    required_level = models.CharField(max_length=20, choices=ApprovalOutcome.choices)
    block_self_approval = models.BooleanField(default=True)

    # Rule: caps cumulative AUTO-approved value over a window (both null =
    # no cap) -- closes a salami-slicing hole; only used for adjustments.
    cumulative_window_days = models.PositiveSmallIntegerField(null=True, blank=True)
    cumulative_value_cap = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    priority = models.PositiveSmallIntegerField(db_index=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'approval_policies'
        ordering = ['transaction_type', 'priority']
        constraints = [
            models.UniqueConstraint(
                fields=['transaction_type', 'priority'],
                condition=models.Q(is_active=True),
                name='uniq_active_policy_priority_per_type',
            ),
        ]

    def __str__(self):
        return f"[{self.transaction_type}#{self.priority}] {self.name} -> {self.required_level}"
