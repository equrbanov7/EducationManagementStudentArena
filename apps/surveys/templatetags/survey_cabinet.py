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
