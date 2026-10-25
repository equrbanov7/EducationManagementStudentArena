"""«Xarici nəticələrin tanınması» kabinet bölməsinin DATA tag-ı (sahib 2026-10-25).

Accounts şablonu ``{% load registrar_recognition %}`` ilə bölmə datasını render vaxtı alır — Python importu yoxdur
(``registrar_retake`` naxışı). Tag öz qapısını yoxlayır: açar + struktur əhatəsi (fail-closed).
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def credit_recognition_desk(context):
    """Axtarış, seçilmiş tələbənin tanınmaları və forma datası — ``credit_recognition_read.build``."""
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return {"has_access": False}
    from core.tenancy import get_request_organization

    organization = get_request_organization(request)
    if organization is None:
        return {"has_access": False}
    from apps.registrar.credit_recognition_read import build

    return build(request, organization)
