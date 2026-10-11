"""«Jurnal təmizliyi» kabinet bölməsinin template tag-ı (sahib 2026-10-10).

Bölmə konteksti profil qurucusuna (``context_builder/_stage*``, ölçü büdcəsinə dayanıb) əlavə olunmur —
``password_reset_admin`` naxışı ilə panel çərçivəsini bu tag-dan alır.
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def journal_hygiene_panel(context):
    from ..views.journal_hygiene import build_panel_context

    request = context.get("request")
    if request is None:
        return {"has_access": False, "access_denied_message": ""}
    return build_panel_context(request)
