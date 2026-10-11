"""«Kadr analitikası» kabinet bölməsinin template tag-ı (sahib 2026-10-11).

Bölmə konteksti profil qurucusuna (``context_builder/_stage*``, ölçü büdcəsinə dayanıb) əlavə olunmur —
``journal_hygiene_panel`` naxışı ilə panel kontekstini bu tag-dan alır.
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def hr_analytics_panel(context):
    from ..services.hr_analytics.panel import build_panel

    request = context.get("request")
    if request is None:
        return {"has_access": False, "access_denied_message": ""}
    return build_panel(request, profile_base_url=context.get("profile_base_url") or "")
