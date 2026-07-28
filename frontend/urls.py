from django.urls import path
from . import views

app_name = "frontend"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("login/", views.login, name="login"),
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
]