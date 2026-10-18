"""«Mühasibatlıq» kabinet bölməsinin template tag-ı (sahib 2026-10-18) — ``hr_analytics_panel`` naxışı."""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def accounting_panel(context):
    from ..services.accounting.panel import build_panel

    request = context.get("request")
    if request is None:
        return {"has_access": False, "access_denied_message": ""}
    return build_panel(request, profile_base_url=context.get("profile_base_url") or "")
