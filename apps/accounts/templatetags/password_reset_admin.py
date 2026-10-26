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


@register.simple_tag(takes_context=True)
def account_password_reset_link(context, username):
    """Şəxs səhifəsindəki «Parolu sıfırla» keçidi (sahib 2026-10-26) — icazə yoxdursa boş sətir.

    Yalnız GÖRÜNÜŞ: keçid bölməni ``?pwr_q=<istifadəçi adı>`` ilə açır, sıfırlamanın özü
    yenə səbəb dialoqu + server qapılarından (`services/password_reset_admin.py`) keçir.
    """
    from urllib.parse import urlencode

    from django.urls import reverse

    from ..services.password_reset_admin import PasswordResetError, operator_for

    request = context.get("request")
    if request is None or not username:
        return ""
    try:
        operator_for(request)
    except PasswordResetError:
        return ""
    query = urlencode({"section": "account-password-reset", "pwr_q": str(username)[:120]})
    return f"{reverse('accounts:profile')}?{query}"
