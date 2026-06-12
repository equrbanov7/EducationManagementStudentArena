from django import template
from django.utils import timezone
from django.utils.translation import pgettext

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
    # QEYD: pgettext çağırışları f-string İÇİNDƏ OLMAMALIDIR — xgettext
    # (makemessages) f-string daxilindəki çağırışları görmür və tərcümələri
    # obsolete edir (bax: "27 unit_minutes" reqressiyası, 2026-06-12).
    unit_hours = pgettext("exams.filter.duration", "unit_hours")
    unit_minutes = pgettext("exams.filter.duration", "unit_minutes")
    unit_seconds = pgettext("exams.filter.duration", "unit_seconds")

    if total <= 0:
        return "0 " + unit_seconds
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    parts = []
    if hours:
        parts.append(f"{hours} {unit_hours}")
    if minutes:
        parts.append(f"{minutes} {unit_minutes}")
    if secs > 0 or not parts:
        parts.append(f"{secs} {unit_seconds}")
    return " ".join(parts)


@register.filter
def format_duration_clock(seconds):
    """Format duration as HH:MM:SS clock string. Empty for None/invalid."""
    if seconds is None:
        return ""
    try:
        total = int(seconds)
    except (ValueError, TypeError):
        return ""
    total = max(total, 0)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
