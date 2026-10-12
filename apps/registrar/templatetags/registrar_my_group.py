"""«Qrupum» panelinin datası — ``{% my_group_overview unit as mg %}`` (rol auditi 2026-10-13 B10).

Tag YALNIZ verilən qrupu göstərir; qrupu accounts-ın ``{% my_group_unit %}`` qapısı həll edir
(``member.view`` əhatəsi). ``None`` gəlsə boş nəticə — fail-closed. Bax ``group_overview``.
"""

from __future__ import annotations

from django import template

from apps.registrar.group_overview import group_overview

register = template.Library()


@register.simple_tag
def my_group_overview(unit):
    if unit is None:
        return {"group": None, "period": None, "subjects": [], "students": [], "has_attendance": False}
    return group_overview(unit)
