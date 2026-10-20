"""«İstifadəçi adı» kartının vəziyyəti (sahib 2026-10-20) — tam səhifə VƏ AJAX bölmə render-ində eyni mənbə.

Qayda və açarlar ``apps.accounts.services.username_change``-dədir; şablon heç bir rəqəmi «bişirmir».
"""

from django import template

from ..services.username_change import card_state

register = template.Library()


@register.simple_tag(takes_context=True)
def username_change_state(context) -> dict:
    request = context.get("request")
    user = getattr(request, "user", None) or context.get("user")
    return card_state(user)
