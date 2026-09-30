"""«Parol sıfırlama» kabinet bölməsinin template tag-ı (sahib, 2026-09-30).

Bölmə konteksti profil context qurucusuna (``context_builder/_stage*``) əlavə
olunmur — `survey_cabinet` naxışı ilə panel öz çərçivəsini bu tag-dan alır, yəni
ölçü büdcəsinə dayanmış mərhələ modullarına toxunulmur.
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def account_password_reset_panel(context):
    from ..views.account_password_reset import build_panel_context

    request = context.get("request")
    if request is None:
        return {"has_access": False, "denied_message": ""}
    return build_panel_context(request)
