from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from . import views

app_name = "frontend"

# Phase 8.99a — the whole password-reset flow lives under this project's
# own `frontend:` namespace, not django.contrib.auth's `accounts:` one
# (now removed from config/urls.py). Matches this project's own established
# precedent: login/logout were already moved off `accounts:` onto
# `frontend:login`/`frontend:logout` back in an earlier bug fix
# (docs/bugsfound.md BUG-01) specifically because this project's real auth
# routes all live under one namespace — `password_reset_confirm` needs a
# real subclass (StockwellPasswordResetConfirmView, below) to fire the
# audit/notify calls change_password_view already does, so relying on
# django.contrib.auth.urls' own unmodifiable routing was never an option
# for that one view anyway; keeping the other 3 under a second namespace
# just for those would be inconsistent for no reason. `success_url`/
# `email_template_name` are all explicitly namespaced (`frontend:...`)
# since Django's own default `success_url`s reverse a bare,
# non-namespaced name that would NoReverseMatch once these routes only
# exist inside a namespaced include.
urlpatterns = [
    path("", views.landing, name="landing"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/change-password/", views.change_password_view, name="change_password"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
            success_url=reverse_lazy("frontend:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        views.StockwellPasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy("frontend:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("products/", views.ProductListCreateView.as_view(), name="products"),
    path("products/export/", views.ProductExportView.as_view(), name="product_export"),
    path("products/<int:pk>/update/", views.ProductUpdateView.as_view(), name="product_update"),
    path("products/<int:pk>/deactivate/", views.ProductDeactivateView.as_view(), name="product_deactivate"),
    path("products/<int:pk>/reactivate/", views.ProductReactivateView.as_view(), name="product_reactivate"),
    path("products/<int:pk>/delete/", views.ProductDeleteView.as_view(), name="product_delete"),
    path("categories/", views.CategoryListCreateView.as_view(), name="categories"),
    path("categories/<int:pk>/update/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("categories/<int:pk>/deactivate/", views.CategoryDeactivateView.as_view(), name="category_deactivate"),
    path("categories/<int:pk>/reactivate/", views.CategoryReactivateView.as_view(), name="category_reactivate"),
    path("categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),
    path("suppliers/", views.SupplierListCreateView.as_view(), name="suppliers"),
    path("suppliers/export/", views.SupplierExportView.as_view(), name="supplier_export"),
    path("suppliers/<int:pk>/update/", views.SupplierUpdateView.as_view(), name="supplier_update"),
    path("suppliers/<int:pk>/deactivate/", views.SupplierDeactivateView.as_view(), name="supplier_deactivate"),
    path("suppliers/<int:pk>/reactivate/", views.SupplierReactivateView.as_view(), name="supplier_reactivate"),
    path("suppliers/<int:pk>/delete/", views.SupplierDeleteView.as_view(), name="supplier_delete"),
    path("purchases/", views.PurchaseListCreateView.as_view(), name="purchases"),
    path("purchases/<int:pk>/submit/", views.PurchaseSubmitView.as_view(), name="purchase_submit"),
    path("purchases/<int:pk>/approve/", views.PurchaseApproveView.as_view(), name="purchase_approve"),
    path("purchases/<int:pk>/reject/", views.PurchaseRejectView.as_view(), name="purchase_reject"),
    path("purchases/<int:pk>/receive/", views.PurchaseReceiveView.as_view(), name="purchase_receive"),
    path("purchases/<int:pk>/cancel/", views.PurchaseCancelView.as_view(), name="purchase_cancel"),
    path("purchases/<int:pk>/pdf/", views.PurchaseOrderPDFView.as_view(), name="purchase_pdf"),
    path("sales/", views.SaleListCreateView.as_view(), name="sales"),
    path("sales/<int:pk>/submit/", views.SaleSubmitView.as_view(), name="sale_submit"),
    path("sales/<int:pk>/approve/", views.SaleApproveView.as_view(), name="sale_approve"),
    path("sales/<int:pk>/reject/", views.SaleRejectView.as_view(), name="sale_reject"),
    path("sales/<int:pk>/cancel/", views.SaleCancelView.as_view(), name="sale_cancel"),
    path("sales/<int:pk>/pdf/", views.SaleTransactionPDFView.as_view(), name="sale_pdf"),
    path("inventory/", views.InventoryListView.as_view(), name="inventory"),
    path("inventory/movements/", views.MovementHistoryListView.as_view(), name="movement_history"),
    path("inventory/movements/export/", views.MovementHistoryExportView.as_view(), name="movement_history_export"),
    path("adjustments/", views.AdjustmentListCreateView.as_view(), name="adjustments"),
    path("adjustments/<int:pk>/approve/", views.AdjustmentApproveView.as_view(), name="adjustment_approve"),
    path("adjustments/<int:pk>/reject/", views.AdjustmentRejectView.as_view(), name="adjustment_reject"),
    path("ai/forecasting/", views.DemandForecastingView.as_view(), name="forecasting"),
    path("ai/slow-moving/", views.SlowMovingDeadStockView.as_view(), name="slow_moving"),
    path("reports/", views.ReportsView.as_view(), name="reports"),
    path("reports/export/<slug:report_type>/", views.ReportExportView.as_view(), name="report_export"),
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path("notifications/<int:pk>/read/", views.NotificationMarkReadView.as_view(), name="notification_read"),
    path("notifications/read-all/", views.NotificationMarkAllReadView.as_view(), name="notification_read_all"),
    path("notifications/unread-count/", views.NotificationUnreadCountView.as_view(), name="notification_unread_count"),
    path("users/", views.UserListCreateView.as_view(), name="users"),
    path("users/<int:pk>/deactivate/", views.UserDeactivateView.as_view(), name="user_deactivate"),
    path("users/<int:pk>/reactivate/", views.UserReactivateView.as_view(), name="user_reactivate"),
    path("users/<int:pk>/delete/", views.UserDeleteView.as_view(), name="user_delete"),
    path("users/<int:pk>/resend-credentials/", views.UserResendCredentialsView.as_view(), name="user_resend_credentials"),
    path("audit-log/", views.AuditLogListView.as_view(), name="audit_log"),
    path("audit-log/export/", views.AuditLogExportView.as_view(), name="audit_log_export"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
]