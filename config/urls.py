from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include(("django.contrib.auth.urls", "accounts"), namespace="accounts")),
    path("", include(("frontend.urls", "frontend"), namespace="frontend")),
]