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
