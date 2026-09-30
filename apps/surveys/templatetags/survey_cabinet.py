"""Kabinet bölmələri üçün template tag-lar (bax ``services/cabinet_panels.py``)."""

from django import template

from ..services import cabinet_panels

register = template.Library()


@register.simple_tag(takes_context=True)
def survey_student_panel(context):
    return cabinet_panels.student_panel(context)


@register.simple_tag(takes_context=True)
def survey_campaigns_panel(context):
    return cabinet_panels.campaigns_panel(context)


@register.simple_tag(takes_context=True)
def survey_results_panel(context):
    return cabinet_panels.results_panel(context)


# ── Sorğu qurucusu (2026-09-30) ─────────────────────────────────────────────


@register.simple_tag(takes_context=True)
def survey_builder_panel(context):
    from ..services.builder_panels import builder_panel

    return builder_panel(context)


@register.simple_tag(takes_context=True)
def survey_inbox_panel(context):
    from ..services.builder_panels import inbox_panel

    return inbox_panel(context)


@register.filter
def svb_get(mapping, key):
    """Şablonda lüğətdən açarla oxu (``{{ errors|svb_get:code }}``)."""
    try:
        return mapping.get(key, "")
    except AttributeError:
        return ""
