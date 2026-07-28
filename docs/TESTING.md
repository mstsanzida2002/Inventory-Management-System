# 🧪 Testing Guide
# AI-Powered Smart Inventory Management System

> **Claude Code:** Read this when writing tests for any module.
> Use factory_boy for test data. Use `TestCase` for DB tests, `APITestCase` for API tests.

---

## Test Structure

```
tests/
├── factories.py            # factory_boy factories for all models
└── fixtures/
    └── initial_settings.json

apps/[module]/tests.py      # or tests/ directory per module
```

---

## Factories

```python
# tests/factories.py
import factory
from factory.django import DjangoModelFactory
from apps.users.models import User, UserRole
from apps.products.models import Product, Category
from apps.suppliers.models import Supplier
from apps.purchases.models import PurchaseOrder, PurchaseOrderItem
from apps.sales.models import SaleTransaction, SaleItem
from apps.inventory.models import InventoryRecord

class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username    = factory.Sequence(lambda n: f'user_{n}')
    email       = factory.Sequence(lambda n: f'user_{n}@test.com')
    employee_id = factory.Sequence(lambda n: f'EMP{n:04d}')
    full_name   = factory.Faker('name')
    role        = UserRole.STAFF
    is_active   = True

    @classmethod
    def admin(cls, **kwargs):
        return cls(role=UserRole.ADMIN, **kwargs)

    @classmethod
    def supervisor(cls, **kwargs):
        return cls(role=UserRole.SUPERVISOR, **kwargs)

class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category
    name = factory.Sequence(lambda n: f'Category {n}')
    is_active = True

class SupplierFactory(DjangoModelFactory):
    class Meta:
        model = Supplier
    supplier_name = factory.Faker('name')
    company_name  = factory.Faker('company')
    email         = factory.Faker('email')
    phone         = factory.Faker('phone_number')
    is_active     = True

class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product
    sku            = factory.Sequence(lambda n: f'SKU-{n:04d}')
    name           = factory.Faker('word')
    category       = factory.SubFactory(CategoryFactory)
    supplier       = factory.SubFactory(SupplierFactory)
    purchase_price = factory.Faker('pydecimal', left_digits=4, right_digits=2, positive=True)
    selling_price  = factory.Faker('pydecimal', left_digits=4, right_digits=2, positive=True)
    reorder_level  = 10
    current_stock  = 100
    is_active      = True

class InventoryRecordFactory(DjangoModelFactory):
    class Meta:
        model = InventoryRecord
    product       = factory.SubFactory(ProductFactory)
    current_stock = 100
    reorder_level = 10
    status        = 'available'
```

---

## Auth Tests

```python
# apps/authentication/tests.py
from django.test import TestCase, Client
from django.urls import reverse
from tests.factories import UserFactory

class LoginViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = UserFactory(username='testuser')
        self.user.set_password('TestPass123!')
        self.user.save()
        self.url = reverse('auth:login')

    def test_login_with_valid_credentials(self):
        response = self.client.post(self.url, {
            'identifier': 'testuser',
            'password': 'TestPass123!'
        })
        self.assertEqual(response.status_code, 302)   # redirect after login

    def test_login_with_email(self):
        response = self.client.post(self.url, {
            'identifier': self.user.email,
            'password': 'TestPass123!'
        })
        self.assertEqual(response.status_code, 302)

    def test_login_invalid_password(self):
        response = self.client.post(self.url, {
            'identifier': 'testuser',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid credentials')

    def test_account_lockout_after_5_failures(self):
        for _ in range(5):
            self.client.post(self.url, {'identifier': 'testuser', 'password': 'wrong'})
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.locked_until)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post(self.url, {
            'identifier': 'testuser', 'password': 'TestPass123!'
        })
        self.assertContains(response, 'inactive')

    def test_unauthenticated_redirect(self):
        response = self.client.get(reverse('dashboard:admin'))
        self.assertRedirects(response, f"{reverse('auth:login')}?next={reverse('dashboard:admin')}")
```

---

## RBAC Tests

```python
# apps/rbac/tests.py
from django.test import TestCase, Client
from django.urls import reverse
from tests.factories import UserFactory

class RBACTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin = UserFactory.admin()
        self.admin.set_password('Pass123!')
        self.admin.save()
        self.staff = UserFactory()
        self.staff.set_password('Pass123!')
        self.staff.save()

    def _login(self, user):
        self.client.post(reverse('auth:login'), {
            'identifier': user.username, 'password': 'Pass123!'
        })

    def test_staff_cannot_access_user_management(self):
        self._login(self.staff)
        response = self.client.get(reverse('users:list'))
        self.assertEqual(response.status_code, 302)   # redirect to dashboard

    def test_admin_can_access_audit_logs(self):
        self._login(self.admin)
        response = self.client.get(reverse('audit:list'))
        self.assertEqual(response.status_code, 200)
```

---

## Inventory Service Tests

```python
# apps/inventory/tests.py
from django.test import TestCase
from tests.factories import UserFactory, ProductFactory, InventoryRecordFactory
from apps.inventory.services import InventoryService, InsufficientStockError
from apps.inventory.models import InventoryRecord, InventoryMovement

class InventoryServiceTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.product = ProductFactory()
        self.record = InventoryRecordFactory(product=self.product, current_stock=100)

    def test_increase_stock(self):
        InventoryService.increase_stock(
            self.product, 50, 'purchase', 'PurchaseOrder', 1, self.user
        )
        self.record.refresh_from_db()
        self.assertEqual(self.record.current_stock, 150)

    def test_decrease_stock(self):
        InventoryService.decrease_stock(
            self.product, 30, 'sale', 'SaleTransaction', 1, self.user
        )
        self.record.refresh_from_db()
        self.assertEqual(self.record.current_stock, 70)

    def test_stock_never_goes_negative(self):
        with self.assertRaises(InsufficientStockError):
            InventoryService.decrease_stock(
                self.product, 200, 'sale', 'SaleTransaction', 1, self.user
            )

    def test_movement_record_created(self):
        InventoryService.increase_stock(
            self.product, 10, 'purchase', 'PurchaseOrder', 1, self.user
        )
        movement = InventoryMovement.objects.filter(product=self.product).last()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity_change, 10)
        self.assertEqual(movement.stock_before, 100)
        self.assertEqual(movement.stock_after, 110)

    def test_status_updates_to_low_stock(self):
        InventoryService.decrease_stock(
            self.product, 95, 'sale', 'SaleTransaction', 1, self.user
        )
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'low_stock')

    def test_status_updates_to_out_of_stock(self):
        InventoryService.decrease_stock(
            self.product, 100, 'sale', 'SaleTransaction', 1, self.user
        )
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'out_of_stock')
```

---

## Purchase Workflow Tests

```python
# apps/purchases/tests.py
from django.test import TestCase
from tests.factories import UserFactory, ProductFactory, InventoryRecordFactory, SupplierFactory
from apps.purchases.models import PurchaseOrder, PurchaseOrderItem
from apps.purchases.services import PurchaseService

class PurchaseWorkflowTest(TestCase):

    def setUp(self):
        self.staff = UserFactory()
        self.supervisor = UserFactory(role='supervisor')
        self.supplier = SupplierFactory()
        self.product = ProductFactory()
        self.record = InventoryRecordFactory(product=self.product, current_stock=0)

        # Create a PO in draft
        self.po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.staff,
            status='draft'
        )
        self.item = PurchaseOrderItem.objects.create(
            purchase_order=self.po,
            product=self.product,
            ordered_qty=100,
            unit_price='150.00'
        )

    def test_submit_po(self):
        PurchaseService.submit_for_approval(self.po, self.staff)
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, 'pending')

    def test_approve_po(self):
        PurchaseService.submit_for_approval(self.po, self.staff)
        PurchaseService.approve(self.po, self.supervisor)
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, 'approved')
        self.assertEqual(self.po.approved_by, self.supervisor)

    def test_receive_po_updates_inventory(self):
        PurchaseService.submit_for_approval(self.po, self.staff)
        PurchaseService.approve(self.po, self.supervisor)
        PurchaseService.receive_items(
            self.po, [{'item_id': self.item.pk, 'received_qty': 100}], self.staff
        )
        self.record.refresh_from_db()
        self.assertEqual(self.record.current_stock, 100)

    def test_cannot_receive_more_than_ordered(self):
        PurchaseService.submit_for_approval(self.po, self.staff)
        PurchaseService.approve(self.po, self.supervisor)
        with self.assertRaises(ValueError):
            PurchaseService.receive_items(
                self.po, [{'item_id': self.item.pk, 'received_qty': 999}], self.staff
            )
```

---

## API Tests

```python
# apps/sales/tests.py
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from tests.factories import UserFactory, ProductFactory, InventoryRecordFactory

class SaleAPITest(APITestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.product = ProductFactory()
        self.record = InventoryRecordFactory(product=self.product, current_stock=50)

    def test_create_sale_success(self):
        url = reverse('api:sales-list')
        data = {
            "items": [
                {"product_id": self.product.pk, "quantity": 5, "unit_price": "200.00"}
            ]
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.record.refresh_from_db()
        self.assertEqual(self.record.current_stock, 45)

    def test_sale_fails_insufficient_stock(self):
        url = reverse('api:sales-list')
        data = {
            "items": [
                {"product_id": self.product.pk, "quantity": 999, "unit_price": "200.00"}
            ]
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Insufficient stock', response.data['error'])

    def test_unauthenticated_request_rejected(self):
        self.client.logout()
        url = reverse('api:sales-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
```

---

## AI Tests

```python
# apps/ai/forecasting/tests.py
from django.test import TestCase
from tests.factories import ProductFactory
from apps.ai.forecasting.pipeline import get_sales_dataframe, build_features

class ForecastPipelineTest(TestCase):

    def test_returns_empty_df_with_no_sales(self):
        product = ProductFactory()
        df = get_sales_dataframe(product_id=product.pk)
        self.assertTrue(df.empty)

    def test_feature_engineering_produces_lag_columns(self):
        import pandas as pd
        import numpy as np
        # Simulate a small dataframe
        df = pd.DataFrame({
            'product_id': [1] * 10,
            'date': pd.date_range('2024-01-01', periods=10, freq='W'),
            'qty_sold': np.random.randint(5, 50, 10),
            'category_id': [1] * 10
        })
        df.set_index('date', inplace=True)
        features = build_features(df.reset_index(), period='W')
        self.assertIn('lag_1', features.columns)
        self.assertIn('rolling_avg_4', features.columns)
```

---

## Running Tests

```bash
# All tests
python manage.py test

# Specific app
python manage.py test apps.inventory
python manage.py test apps.purchases
python manage.py test apps.ai.forecasting

# With coverage
coverage run --source='.' manage.py test
coverage report --omit='*/migrations/*,*/tests/*'
coverage html  # → htmlcov/index.html

# Parallel (faster)
python manage.py test --parallel
```

---

## Coverage Targets

| Module | Target Coverage |
|---|---|
| `apps/inventory/services.py` | 95%+ |
| `apps/purchases/services.py` | 95%+ |
| `apps/sales/services.py` | 95%+ |
| `apps/authentication/` | 90%+ |
| `apps/rbac/` | 90%+ |
| `apps/ai/` | 80%+ |
| Overall project | 80%+ |
