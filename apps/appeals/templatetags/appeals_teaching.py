"""«Fənnimə aid apellyasiyalar» kabinet bölməsinin DATA tag-ı (sahib 2026-10-27).

Accounts şablonu ``{% load appeals_teaching %}`` ilə bölmə datasını render vaxtı alır — accounts-dan Python importu
yoxdur (``registrar_recognition`` naxışı). Əhatə tag-ın içində YENİDƏN hesablanır (fail-closed).
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def teaching_appeals_panel(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    if request is None or not getattr(user, "is_authenticated", False):
        return {"state": "no_org"}
    from apps.appeals.views.teacher.teaching_panel import build_teaching_panel

    return build_teaching_panel(request)
