"""Sidebar «Sistem tənzimləmələri» başlığının alt bəndləri (sahib 2026-10-21).

``{% system_settings_nav as ssnav %}`` → ``{"groups": [...], "active": "<qrup>" | ""}``:

* ``groups`` — ``core.runtime_settings.GROUPS`` sırası ilə, görünən açarı olan hər qrup (key, label, icon, url);
  yeni qrup/modul (``runtime_settings_extensions``) əlavə olunanda bənd ÖZÜ yaranır;
* ``active`` — ``?ss_group=`` dəyəri bilinən qrupdursa onun kodu, əks halda «» (ümumi baxış aktivdir).

Saf hesablamadır (DB-yə getmir). Görünürlük qapısı şablondadır: ``'system-settings' in allowed_sections``
(bölmənin özü ilə EYNİ — ``rbac_sections.py``: RİM rəhbəri / superadmin).
"""

from django import template

from apps.accounts.services import system_settings_pages as pages

register = template.Library()


@register.simple_tag(takes_context=True)
def system_settings_nav(context):
    groups = pages.nav_groups()
    request = context.get("request")
    raw = request.GET.get(pages.GROUP_PARAM) if request is not None and hasattr(request, "GET") else ""
    return {"groups": groups, "active": pages.resolve_group(raw, [group["key"] for group in groups])}
