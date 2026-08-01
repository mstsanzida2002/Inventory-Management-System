from django.urls import path
from . import views

app_name = "frontend"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("products/", views.products, name="products"),
    path("categories/", views.categories, name="categories"),
    path("suppliers/", views.suppliers, name="suppliers"),
    path("purchases/", views.purchases, name="purchases"),
    path("sales/", views.sales, name="sales"),
    path("inventory/", views.inventory, name="inventory"),
    path("adjustments/", views.adjustments, name="adjustments"),
    path("ai/forecasting/", views.demand_forecasting, name="forecasting"),
    path("ai/slow-moving/", views.slow_moving_dead_stock, name="slow_moving"),
    path("reports/", views.reports, name="reports"),
    path("notifications/", views.notifications, name="notifications"),
    path("users/", views.users, name="users"),
    path("audit-log/", views.audit_log, name="audit_log"),
    path("settings/", views.settings, name="settings"),
]