from django.urls import path
from . import views

app_name = "frontend"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("products/", views.ProductListCreateView.as_view(), name="products"),
    path("categories/", views.CategoryListCreateView.as_view(), name="categories"),
    path("suppliers/", views.SupplierListCreateView.as_view(), name="suppliers"),
    path("purchases/", views.PurchaseListCreateView.as_view(), name="purchases"),
    path("purchases/<int:pk>/submit/", views.PurchaseSubmitView.as_view(), name="purchase_submit"),
    path("purchases/<int:pk>/approve/", views.PurchaseApproveView.as_view(), name="purchase_approve"),
    path("purchases/<int:pk>/reject/", views.PurchaseRejectView.as_view(), name="purchase_reject"),
    path("purchases/<int:pk>/receive/", views.PurchaseReceiveView.as_view(), name="purchase_receive"),
    path("purchases/<int:pk>/cancel/", views.PurchaseCancelView.as_view(), name="purchase_cancel"),
    path("sales/", views.SaleListCreateView.as_view(), name="sales"),
    path("sales/<int:pk>/cancel/", views.SaleCancelView.as_view(), name="sale_cancel"),
    path("inventory/", views.inventory, name="inventory"),
    path("adjustments/", views.AdjustmentListCreateView.as_view(), name="adjustments"),
    path("adjustments/<int:pk>/approve/", views.AdjustmentApproveView.as_view(), name="adjustment_approve"),
    path("adjustments/<int:pk>/reject/", views.AdjustmentRejectView.as_view(), name="adjustment_reject"),
    path("ai/forecasting/", views.demand_forecasting, name="forecasting"),
    path("ai/slow-moving/", views.slow_moving_dead_stock, name="slow_moving"),
    path("reports/", views.reports, name="reports"),
    path("notifications/", views.notifications, name="notifications"),
    path("users/", views.users, name="users"),
    path("audit-log/", views.audit_log, name="audit_log"),
    path("settings/", views.settings, name="settings"),
]