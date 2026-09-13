from django.utils import timezone


def current_year(request):
    """{{ current_year }} for copyright lines -- Asia/Dhaka calendar year."""
    return {"current_year": timezone.localdate().year}
