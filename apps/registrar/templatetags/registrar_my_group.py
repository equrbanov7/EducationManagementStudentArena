"""«Starosta» (`my-group`) panelinin datası — ``{% my_group_overview unit as mg %}`` (rol auditi 2026-10-13 B10)
və ``{% my_group_academic unit viewer period as ga %}`` (qrupun akademik mənzərəsi, 2026-10-13 (gecə)).

Tag-lar YALNIZ verilən qrupu göstərir; qrupu accounts-ın ``{% my_group_unit %}`` qapısı həll edir
(``member.view`` əhatəsi + baxan həmin qrupun qeydiyyatlı tələbəsidir). ``None`` gəlsə boş nəticə —
fail-closed. Bax ``group_overview`` / ``group_academic`` / ``group_timetable``.
"""

from __future__ import annotations

from django import template

from apps.registrar.group_academic import exam_unit_ids, group_students, group_subgroups, group_subjects
from apps.registrar.group_overview import group_overview
from apps.registrar.group_timetable import group_timetable, group_upcoming_exams

register = template.Library()

_EMPTY_ACADEMIC = {"subjects": [], "electives": [], "joint": [], "timetable": [], "exams": [], "subgroups": None}


@register.simple_tag
def my_group_overview(unit, viewer=None):
    """``viewer`` — baxan istifadəçi: davamiyyət YALNIZ onun özü üçün (sahib 2026-10-13 «ancaq şəxsi»)."""
    if unit is None:
        return {"group": None, "period": None, "students": [], "me": None, "has_attendance": False}
    return group_overview(unit, viewer_id=getattr(viewer, "pk", None))


@register.simple_tag
def my_group_academic(unit, viewer=None, period=None):
    """Fənlər (seçmə daxil) / birləşmiş dərslər / alt qruplar / cədvəl / yaxın imtahanlar.

    ``period`` — ``my_group_overview`` artıq hesablayıb (təkrar sorğu yoxdur). Yoldaşların balı/qayıbı YOXDUR.
    """
    if unit is None:
        return dict(_EMPTY_ACADEMIC)
    students = group_students(unit)
    subjects = group_subjects(unit, period=period, students=students, viewer_id=getattr(viewer, "pk", None))
    subgroups = group_subgroups(unit)
    return {
        "subjects": subjects["subjects"],
        "electives": subjects["electives"],
        "joint": subjects["joint"],
        "timetable": group_timetable(unit, period=period, subjects=subjects),
        "exams": group_upcoming_exams(unit, period=period, subjects=subjects, unit_ids=exam_unit_ids(unit)),
        "subgroups": subgroups if (subgroups["parent"] or subgroups["children"]) else None,
    }
