"""Avatar URL versiyası — ``{{ profile.updated_at|avatar_version }}`` (PERF-2 H5, 2026-10-17).

``?v=`` əvvəl ``date:'U'`` (saniyə) idi; versiyalı URL indi bir il ``immutable`` keşlənir,
ona görə eyni saniyədə iki dəyişiklik eyni URL-i paylaşmamalıdır — mikrosaniyə dəqiqliyi.
View (``views/profile/avatar.py``) eyni funksiya ilə müqayisə edir.
"""

from django import template

from ..services.avatar_image import avatar_version as _avatar_version

register = template.Library()


@register.filter
def avatar_version(updated_at):
    return _avatar_version(updated_at)
