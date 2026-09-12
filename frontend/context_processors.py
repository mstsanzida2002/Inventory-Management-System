"""
Template context processors — registered in config/settings.py's
TEMPLATES['OPTIONS']['context_processors'], applied to every template
render across the whole site (dashboard shell, login, landing, password
reset), not just one page's own view.
"""
from django.utils import timezone


def current_year(request):
    """{{ current_year }} for copyright lines (footer, etc.) — Asia/Dhaka
    calendar year via timezone.localdate(), never hardcoded (would be
    wrong every January). Was previously referenced by
    frontend/templates/includes/footer.html with nothing providing it —
    silently rendered blank on the one page that already used it
    (landing/index.html); this closes that gap too, not just the new
    authenticated-page footer this was built for."""
    return {"current_year": timezone.localdate().year}
