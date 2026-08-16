"""
Models per docs/SCHEMA.md. SCHEMA.md documents these across separate apps
(apps/users, apps/products, apps/suppliers, ...); consolidated here into the
single `frontend` app per current project structure. Cross-model references
that SCHEMA.md writes as app-label strings (e.g. 'suppliers.Supplier') are
written as direct class references instead, since there is only one app.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from frontend.pricing import calculate_line_total


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# --------------------------------------------------------------------- 1. User

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

    # Not in SCHEMA.md's User code block — PermissionsMixin hardcodes
    # related_name="user_set" for both fields, which clashes with
    # django.contrib.auth's own User model (still present/active in
    # INSTALLED_APPS until AUTH_USER_MODEL is switched in a later phase).
    # Overriding related_name only renames the reverse accessor; it does not
    # change the documented schema shape.
    groups = models.ManyToManyField('auth.Group', related_name='frontend_user_set', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='frontend_user_permissions_set', blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'employee_id', 'full_name']

    class Meta:
        db_table = 'users'
        indexes = [
            # email's index removed (BUG-13): unique=True above already
            # creates a DB-level unique index on this column.
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

    # Not in SCHEMA.md's User code block. AbstractBaseUser (unlike
    # AbstractUser) provides neither get_full_name() nor get_short_name()
    # — Phase 3.6's dashboard topbar template already calls both
    # (`request.user.get_full_name`, `request.user.get_initials`) against
    # mock/anonymous data, silently falling through to its `|default`
    # values. Added now (Phase 4) so those calls resolve to the real,
    # logged-in user instead of always showing the placeholder name.
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


# ----------------------------------------------------------------- 2. Category

class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'categories'


# ----------------------------------------------------------------- 3. Supplier

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


# ------------------------------------------------------------------ 4. Product

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
    # Phase 8.98c — undocumented in SCHEMA.md (which instead documents `tax`
    # as a per-line field on PurchaseOrderItem/SaleItem, still true — see
    # those models below). Disclosed architecture decision, matching this
    # project's SKU-format precedent (project_memory.md §13): tax is a
    # property of the product, not something entered per-transaction.
    # Default 0% — no jurisdiction/tax-regime assumption is baked in; every
    # existing product needs this set explicitly to charge real tax.
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reorder_level = models.PositiveIntegerField(default=10)
    current_stock = models.PositiveIntegerField(default=0)  # updated by inventory service
    unit = models.CharField(max_length=10, choices=UnitOfMeasurement.choices, default=UnitOfMeasurement.PIECE)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'products'
        indexes = [
            # sku's and barcode's indexes removed (BUG-13): both are
            # unique=True above, which already creates a DB-level unique
            # index on each column.
            models.Index(fields=['category']),
            models.Index(fields=['supplier']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"[{self.sku}] {self.name}"


# ---------------------------------------------------------- 5. Purchase Orders

class POStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PENDING = 'pending', 'Pending Approval'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    PARTIAL = 'partial', 'Partially Received'
    RECEIVED = 'received', 'Fully Received'
    CANCELLED = 'cancelled', 'Cancelled'


class PurchaseOrder(TimeStampedModel):
    po_number = models.CharField(max_length=30, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=POStatus.choices, default=POStatus.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='purchase_orders_created')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='purchase_orders_approved', null=True, blank=True)
    # Phase 8.99 — was `auto_now_add=True`. Django's DateField (unlike
    # DateTimeField) ignores TIME_ZONE/USE_TZ entirely for auto_now/
    # auto_now_add: DateField.pre_save() calls plain `datetime.date.
    # today()`, the OS clock's local calendar date, not
    # `timezone.localdate()`. Invisible on this dev machine (OS clock is
    # already set to Bangladesh time) but wrong on any UTC production
    # server: an order raised at, say, 2 AM Dhaka is 20:00 UTC the
    # previous day, so `date.today()` there returns yesterday. Set
    # explicitly in save() below via `timezone.localdate()` instead, the
    # same Asia/Dhaka-aware helper used everywhere else since Phase 8.6.
    order_date = models.DateField()
    expected_delivery = models.DateField(null=True, blank=True)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)
    # Phase 8.99c — SCHEMA.md §5 has no cancellation-equivalent field (only
    # rejected_reason); a new field rather than overloading rejected_reason,
    # matching that field's own shape (TextField, blank=True, no null=True).
    # cancelled_by/cancelled_at mirror approved_by/approved_at — a reason
    # with no attributable author/time isn't an audit record.
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
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_po_number():
        import random
        # Phase 8.99: was `timezone.now().strftime(...)` — timezone.now()
        # is UTC-aware, and .strftime() on an aware datetime formats it in
        # whatever tzinfo it already carries (UTC), not TIME_ZONE. The
        # embedded date in this identifier was silently UTC-dated, not
        # Dhaka-dated. timezone.localdate() already returns the correct
        # local calendar date, so no further conversion is needed here.
        return f"PO-{timezone.localdate().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

    @property
    def display_reason(self):
        """Phase 8.99c — one place both the list tables, per-record PDF,
        and Purchase Report read from, so a rejected or cancelled PO's
        reason is visible wherever the record is reported (Objective #3)."""
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
    # Phase 8.98c: no longer a form input — set once, at creation, from
    # frontend.forms.parse_line_items() reading the product's own
    # tax_rate (never trusted from the client). Kept as a real column
    # (not derived at read-time) so this line's tax is a historical
    # snapshot: if the product's tax_rate changes later, this row still
    # reflects what was actually charged when the PO was created.
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = 'purchase_order_items'

    def save(self, *args, **kwargs):
        # frontend.pricing.calculate_line_total() — the one shared formula
        # SaleService.create_sale() also uses (Phase 8.98c), instead of
        # each duplicating it.
        self.line_total = calculate_line_total(self.unit_price, self.ordered_qty, self.discount, self.tax)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------- 6. Sales

class SaleStatus(models.TextChoices):
    # Phase 8.99b — extends SCHEMA.md §6's original two-status
    # (`completed`/`cancelled`) shape to mirror PurchaseOrder's approval
    # workflow; disclosed as its own architecture decision (§13), same
    # treatment as `Product.tax_rate`. Deliberately no separate
    # `APPROVED` status: for a Purchase, approval and receipt are
    # genuinely different moments (approval commits to the order; stock
    # only moves later, on receive — and can move partially, over
    # multiple receipts). For a Sale, approval *is* the moment stock
    # moves — there is no second, later event a distinct `APPROVED`
    # status would ever describe. Inventing one would create a status
    # with no real-world meaning of its own; `COMPLETED` (the pre-existing
    # value, reused rather than renamed) already means exactly "approved
    # and stock has moved," so it does double duty as both.
    DRAFT = 'draft', 'Draft'
    PENDING = 'pending', 'Pending Approval'
    COMPLETED = 'completed', 'Completed'
    REJECTED = 'rejected', 'Rejected'
    CANCELLED = 'cancelled', 'Cancelled'


class SaleTransaction(TimeStampedModel):
    invoice_number = models.CharField(max_length=30, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    customer_name = models.CharField(max_length=150, blank=True)
    # Phase 8.99 — same fix as PurchaseOrder.order_date above (was
    # `auto_now_add=True`, silently OS-clock-dated rather than
    # Asia/Dhaka-dated on a UTC production server). Set explicitly in
    # save() via `timezone.localdate()`.
    transaction_date = models.DateField()
    # Phase 8.99b — was `default=SaleStatus.COMPLETED` (a sale used to
    # complete immediately on creation). Now defaults to DRAFT, mirroring
    # PurchaseOrder.status's own default — a sale is created, then
    # explicitly submitted for approval, same shape as a PO.
    status = models.CharField(max_length=20, choices=SaleStatus.choices, default=SaleStatus.DRAFT)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    # Phase 8.99b — mirrors PurchaseOrder.approved_by/approved_at exactly
    # (same FK shape, same null=True/blank=True — not every sale reaches
    # this state).
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='sales_approved', null=True, blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    # Phase 8.99b — mirrors PurchaseOrder.rejected_reason; SaleTransaction
    # never had a rejection concept before this phase.
    rejected_reason = models.TextField(blank=True)
    # Phase 8.99c — mirrors PurchaseOrder.cancelled_reason/cancelled_by/
    # cancelled_at exactly; see that field's own comment for the reasoning.
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
        super().save(*args, **kwargs)

    @property
    def display_reason(self):
        """Phase 8.99c — mirrors PurchaseOrder.display_reason exactly."""
        if self.status == SaleStatus.CANCELLED:
            return self.cancelled_reason
        if self.status == SaleStatus.REJECTED:
            return self.rejected_reason
        return ""

    @staticmethod
    def _generate_invoice_number():
        import random
        # Phase 8.99 — same fix as PurchaseOrder._generate_po_number()
        # above: timezone.localdate() instead of timezone.now().strftime(),
        # which silently formatted the UTC date, not the Dhaka date.
        return f"INV-{timezone.localdate().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


class SaleItem(TimeStampedModel):
    transaction = models.ForeignKey(SaleTransaction, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Phase 8.98c: same treatment as PurchaseOrderItem.tax above — sourced
    # from the product's tax_rate at creation (frontend.forms.
    # parse_line_items()), never a form field; a historical snapshot, not
    # recomputed if the product's tax_rate changes later.
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = 'sale_items'


# ------------------------------------------------------------- 7. Inventory

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
    quantity_change = models.IntegerField()  # positive = stock in, negative = stock out
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


# --------------------------------------------------------- 8. Inventory Adjustment

class AdjustmentType(models.TextChoices):
    INCREASE = 'increase', 'Stock Increase'
    DECREASE = 'decrease', 'Stock Decrease'


class AdjustmentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending Approval'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class InventoryAdjustment(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    adjustment_type = models.CharField(max_length=10, choices=AdjustmentType.choices)
    quantity = models.PositiveIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=AdjustmentStatus.choices, default=AdjustmentStatus.PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='adjustments_requested')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='adjustments_approved', null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)

    class Meta:
        db_table = 'inventory_adjustments'


# ----------------------------------------------------- 9. AI Demand Forecast

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


# --------------------------------------------- 10. AI Inventory Classification

class StockClassification(models.TextChoices):
    FAST = 'fast', 'Fast-Moving'
    SLOW = 'slow', 'Slow-Moving'
    DEAD = 'dead', 'Dead Stock'


class InventoryClassification(TimeStampedModel):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='classification')
    classification = models.CharField(max_length=10, choices=StockClassification.choices)
    turnover_rate = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    last_sold_date = models.DateField(null=True, blank=True)
    days_since_last_sale = models.PositiveIntegerField(default=0)
    recommendation = models.TextField(blank=True)
    classified_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_classifications'


# ----------------------------------------------------------- 11. Notification

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
    # Phase 8.99b — the 13th type, added deliberately against this
    # project's own Phase 8.98e precedent of skipping a notification
    # rather than inventing an undocumented type. That precedent covered
    # a merely-informational case (an admin being told a password
    # changed); this one is load-bearing — without a real notification,
    # a Supervisor/Admin has no way to learn a sale is even awaiting
    # them, and the entire approval gate this phase builds has no
    # trigger. See §13 for the full reasoning.
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


# ------------------------------------------------------------- 12. Audit Log

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


# --------------------------------------------------- 13. System Settings

class SystemSettings(TimeStampedModel):
    """Singleton — only one row should ever exist."""
    company_name = models.CharField(max_length=200, default='My Company')
    company_logo = models.ImageField(upload_to='company/', blank=True, null=True)
    company_address = models.TextField(blank=True)
    company_email = models.EmailField(blank=True)
    company_phone = models.CharField(max_length=20, blank=True)
    # Inventory thresholds
    default_reorder_level = models.PositiveIntegerField(default=10)
    # AI settings
    forecast_period_weeks = models.PositiveIntegerField(default=4)
    forecast_retrain_days = models.PositiveIntegerField(default=7)
    slow_moving_threshold_days = models.PositiveIntegerField(default=60)
    dead_stock_threshold_days = models.PositiveIntegerField(default=180)
    # Session
    session_timeout_seconds = models.PositiveIntegerField(default=3600)
    # Notifications
    email_notifications_enabled = models.BooleanField(default=True)
    low_stock_email_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = 'system_settings'
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'

    def save(self, *args, **kwargs):
        # Force every save onto the same row so a second row can never be
        # produced regardless of caller (was previously convention-only —
        # see BUG-21). A plain instantiate+save() converges onto row 1
        # (Django UPDATEs when pk is set and the row exists); a second
        # .objects.create() (which forces an INSERT) raises IntegrityError
        # instead of silently duplicating — either way, never a 2nd row.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
