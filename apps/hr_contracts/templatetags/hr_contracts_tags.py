"""«Əmək müqavilələri» şablon tag-ları — kabinet panelləri və şəxs səhifəsinin kartı.

``accounts`` şablonlarından ``{% load hr_contracts_tags %}`` ilə çağırılır (Python importu yoxdur → modul-sərhəd
qrafında ``accounts → hr_contracts`` kənarı şablonlardan yaranmır). Hər tag fail-closed-dur və heç vaxt exception
atmır (panel boş / «icazə yoxdur» vəziyyəti göstərir).
"""

from __future__ import annotations

import logging

from django import template

from ..services.access import resolve_actor
from ..services.panel import employee_panel, hr_panel, person_card

logger = logging.getLogger(__name__)
register = template.Library()


@register.simple_tag(takes_context=True)
def hr_contracts_panel(context):
    request = context.get("request")
    if request is None:
        return {"has_access": False}
    try:
        return hr_panel(request, resolve_actor(request))
    except Exception:  # noqa: BLE001 — bölmə qabığı sınmasın
        logger.exception("hr_contracts panel failed")
        return {"has_access": False, "failed": True}


@register.simple_tag(takes_context=True)
def my_contracts_panel(context):
    request = context.get("request")
    if request is None:
        return {"available": False}
    try:
        return employee_panel(request)
    except Exception:  # noqa: BLE001
        logger.exception("hr_contracts employee panel failed")
        return {"available": False, "failed": True}


@register.simple_tag(takes_context=True)
def hr_contract_person_card(context, user_id):
    """Şəxs səhifəsi: aktor ``hr.contracts_view`` əhatəsindədirsə kart, əks halda ``None`` (kart göstərilmir)."""
    request = context.get("request")
    if request is None or not user_id:
        return None
    try:
        return person_card(resolve_actor(request), int(user_id))
    except Exception:  # noqa: BLE001
        logger.exception("hr_contracts person card failed")
        return None


@register.filter
def hrc_abs(value):
    try:
        return abs(int(value))
    except (TypeError, ValueError):
        return value
