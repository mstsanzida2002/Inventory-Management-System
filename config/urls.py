from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include(("django.contrib.auth.urls", "accounts"), namespace="accounts")),
    path("", include(("frontend.urls", "frontend"), namespace="frontend")),
]

if settings.DEBUG:
    # Dev-only media serving (Phase 5) — production would use a real web
    # server/WhiteNoise-equivalent for this, neither of which exist yet
    # (see docs/project_memory.md §1's tech-stack gap table).
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)