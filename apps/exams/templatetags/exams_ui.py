"""
Müəllim paneli üçün UI köməkçi tag-ları.

İmtahan növü / status / kateqoriya üçün vizual tokenləri (rəng, ikon)
`apps/exams/constants.py`-dən şablona təhlükəsiz şəkildə ötürür ki, şablonlarda
heç bir hardcoded rəng olmasın və mənbə tək yerdə qalsın.
"""

from django import template

from apps.exams.constants import (
    EXAM_CATEGORY_META,
    EXAM_STATUS_META,
    EXAM_TYPE_META,
)

register = template.Library()

# Naməlum keylər üçün neytral fallback — şablon heç vaxt qırılmasın.
_FALLBACK_META = {"color": "#64748B", "soft": "#F1F4F9", "deep": "#475569", "icon": "fa-file-alt"}


@register.simple_tag
def exam_type_meta(type_key):
    """İmtahan növü üçün {color, soft, deep, icon} qaytarır."""
    return EXAM_TYPE_META.get(type_key, _FALLBACK_META)


@register.simple_tag
def exam_status_meta(status_key):
    """Lifecycle status üçün {color, soft, deep, icon} qaytarır."""
    return EXAM_STATUS_META.get(status_key, _FALLBACK_META)


@register.simple_tag
def exam_category_meta(category_key):
    """Kateqoriya (exam_type_extended) üçün {color, soft, deep} qaytarır."""
    return EXAM_CATEGORY_META.get(category_key, _FALLBACK_META)


@register.filter
def dict_key(mapping, key):
    """Lüğətdən dəyişən key ilə dəyər götür (şablonda d[key] mümkün deyil)."""
    if not hasattr(mapping, "get"):
        return None
    return mapping.get(key)
