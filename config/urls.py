from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Phase 8.99a — the `accounts:` django.contrib.auth.urls include (dead
    # since login/logout moved to frontend:login/frontend:logout, see
    # docs/bugsfound.md BUG-01) removed outright, not left dead: the
    # password-reset flow it also carried is now real and fully wired
    # under frontend: (frontend/urls.py), the last thing that include was
    # for. Nothing referenced the accounts: namespace before this removal
    # (verified via a full-repo grep — only a code comment in views.py
    # mentioned it), so nothing breaks.
    path("", include(("frontend.urls", "frontend"), namespace="frontend")),
]

if settings.DEBUG or settings.SERVE_MEDIA_IN_PRODUCTION:
    # Dev media serving (Phase 5), extended in production (Phase 8.99)
    # behind an explicit opt-in env var — see settings.py's
    # SERVE_MEDIA_IN_PRODUCTION comment for why this isn't unconditional:
    # serving media Django-side only makes sense once a persistent disk
    # is actually mounted at MEDIA_ROOT, and that's a deliberate deploy
    # decision, not something DEBUG=False should silently determine.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)