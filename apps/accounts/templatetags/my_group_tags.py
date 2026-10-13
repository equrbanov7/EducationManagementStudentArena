"""«Starosta» (`my-group`, əvvəl «Qrupum») bölməsinin DATA qapısı — rol auditi 2026-10-13 B10.

``{% my_group_unit as unit %}`` render vaxtı sidebar qapısının EYNİ funksiyasını
(``rbac_my_group.my_group_unit``) yenidən çağırır: menyu ilə panel bir-birindən geniş ola bilməz və
``allowed_sections`` köhnəlsə belə (eyni request-də rol dəyişikliyi) qrup yalnız cari əhatədən gəlir.
Qrupun datası registrar-ın ``{% my_group_overview unit %}`` tag-ındadır — şablon zəncirində
birləşir, Python importu yoxdur (modul-sərhəd qrafında ``accounts → registrar`` kənarı yaranmır).
"""

from __future__ import annotations

from django import template

from apps.accounts.views._helpers.rbac_my_group import my_group_unit as _resolve_my_group_unit

register = template.Library()


@register.simple_tag(takes_context=True)
def my_group_unit(context):
    """Aktorun ``member.view`` əhatəsindəki akademik qrup və ya ``None`` (fail-closed)."""
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    organization = getattr(user, "active_organization", None) or getattr(request, "organization", None)
    return _resolve_my_group_unit(user, organization)


@register.simple_tag
def my_group_announcements(unit, limit=5):
    """Qrupa (və ya əcdadına) ünvanlanmış tələbə elanları — «Starosta» bölməsi (2026-10-13 (gecə)).

    ``unit`` YALNIZ ``my_group_unit`` qapısından gəlir; ``None`` → boş siyahı (fail-closed).
    """
    if unit is None:
        return []
    from apps.announcements.public import group_announcements

    return group_announcements(unit.organization, unit, limit=limit)
