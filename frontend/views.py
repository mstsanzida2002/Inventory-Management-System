from django.shortcuts import render

def landing(request):
    return render(request, "landing/index.html")

def login(request):
    return render(request, "accounts/login.html")

def dashboard(request):
    return render(request, "dashboard/dashboard.html")

def products(request):
    return render(request, "products/products.html", {"active_nav": "products"})

def categories(request):
    return render(request, "categories/categories.html", {"active_nav": "categories"})

def suppliers(request):
    return render(request, "suppliers/suppliers.html", {"active_nav": "suppliers"})

def purchases(request):
    return render(request, "purchases/purchases.html", {"active_nav": "purchases"})

def sales(request):
    return render(request, "sales/sales.html", {"active_nav": "sales"})

def inventory(request):
    return render(request, "inventory/inventory.html", {"active_nav": "inventory"})

def adjustments(request):
    return render(request, "adjustments/adjustments.html", {"active_nav": "adjustments"})

def demand_forecasting(request):
    return render(request, "intelligence/forecasting.html", {"active_nav": "forecasting"})

def slow_moving_dead_stock(request):
    return render(request, "intelligence/slow_moving.html", {"active_nav": "slow-moving"})

def reports(request):
    return render(request, "reports/reports.html", {"active_nav": "reports"})

def notifications(request):
    return render(request, "notifications/notifications.html", {"active_nav": "notifications"})

def users(request):
    return render(request, "users/users.html", {"active_nav": "users"})

def audit_log(request):
    return render(request, "audit/audit_log.html", {"active_nav": "audit-log"})

def settings(request):
    return render(request, "settings/settings.html", {"active_nav": "settings"})