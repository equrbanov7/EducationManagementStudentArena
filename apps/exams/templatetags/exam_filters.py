from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def minutes_since(value):
    """Verilən tarixdən bu ana qədər neçə dəqiqə keçib?"""
    if not value:
        return None

    now = timezone.now()
    diff = now - value
    return int(diff.total_seconds() / 60)


@register.filter
def subtract(value, arg):
    """Çıxma əməliyyatı"""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def format_duration(seconds):
    """Format duration_seconds as human-readable string, e.g. '5 dəq 23 san'."""
    if seconds is None:
        return ""
    try:
        total = int(seconds)
    except (ValueError, TypeError):
        return ""
    if total <= 0:
        return "0 san"
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    parts = []
    if hours:
        parts.append(f"{hours} saat")
    if minutes:
        parts.append(f"{minutes} dəq")
    if secs or not parts:
        parts.append(f"{secs} san")
    return " ".join(parts)
