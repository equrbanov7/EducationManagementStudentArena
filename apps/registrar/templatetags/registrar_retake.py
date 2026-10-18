"""«25% və alt qrup» kabinet bölmələrinin DATA tag-ları (sahib 2026-10-18).

Accounts şablonu ``{% load registrar_retake %}`` ilə bölmə datasını render vaxtı alır — Python importu
yoxdur (``accounts → registrar`` kənarı yaranmır, ``my_group`` naxışı). Hər tag öz qapısını yoxlayır:
tələbə paneli yalnız baxanın ÖZ datası; heyət növbəsi açar + struktur əhatəsi ilə (fail-closed).
"""

from __future__ import annotations

from django import template

register = template.Library()


def _request_parts(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return request, None, None
    from core.tenancy import get_request_organization

    return request, user, get_request_organization(request)


@register.simple_tag(takes_context=True)
def retake_student_panel(context):
    """Baxanın kəsr fənləri + müraciətləri + cəhd tarixçəsi (``retake_queries.student_panel``)."""
    _request, user, organization = _request_parts(context)
    if user is None or organization is None:
        return None
    from apps.registrar.retake_queries import student_panel

    return student_panel(student=user, organization=organization)


@register.simple_tag(takes_context=True)
def retake_desk(context):
    """Heyət növbəsi (Mühasibatlıq / dekanlıq) + iz — ``retake_desk.build``; açar yoxdursa ``has_access=False``."""
    request, user, organization = _request_parts(context)
    if user is None or organization is None:
        return {"has_access": False}
    from apps.registrar.retake_desk import build

    return build(request, organization)


@register.filter
def retake_tone(status):
    from apps.registrar.retake_rules import tone_for

    return tone_for(status)


@register.filter
def retake_status_label(status):
    from apps.registrar.models import RetakeStatus

    try:
        return RetakeStatus(status).label
    except ValueError:
        return status


@register.filter
def retake_score(value):
    from apps.registrar.retake_queries import fmt

    return fmt(value)


@register.filter
def retake_reason_label(reason):
    from apps.registrar.retake_queries import grant_reason_label

    return grant_reason_label(reason)


@register.filter
def retake_filesize(value):
    try:
        size = int(value or 0)
    except (TypeError, ValueError):
        return ""
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{max(1, size // 1024)} KB"
