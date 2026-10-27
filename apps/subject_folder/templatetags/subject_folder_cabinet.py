"""Kabinet bölmələri üçün template tag-lar (bax ``apps.subject_folder.cabinet``).

``{% sf_teacher_panel as sp %}`` / ``{% sf_review_panel as rp %}`` / ``{% sf_student_panel as sp %}`` /
``{% sf_unit_panel as up %}`` (kafedra materialları, yalnız-oxu — 2026-10-27) —
kontekst yalnız bölmə AKTİV olanda (panel render olunanda) qurulur; icazə və
təşkilat konteksti fail-closed yoxlanılır.
"""

from django import template

from ..cabinet.review import review_panel
from ..cabinet.student import student_panel
from ..cabinet.teacher import teacher_panel
from ..cabinet.unit import unit_panel

register = template.Library()


@register.simple_tag(takes_context=True)
def sf_teacher_panel(context):
    return teacher_panel(context)


@register.simple_tag(takes_context=True)
def sf_review_panel(context):
    return review_panel(context)


@register.simple_tag(takes_context=True)
def sf_student_panel(context):
    return student_panel(context)


@register.simple_tag(takes_context=True)
def sf_unit_panel(context):
    return unit_panel(context)
