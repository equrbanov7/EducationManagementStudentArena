"""Own authored history as a read-only journal grid (owner 2026-11-26).

«Müəllim yazdığı jurnal tarixçəsinə baxa bilsin — sətrə klikləyəndə ÖZ yazdığı hissə jurnal kimi cədvəldə görünsün:
nə vaxt, harada, nə yazıb.» The caller (:func:`apps.registrar.journal_own_history.detail`) has already decided WHO
the subject teacher is and that the viewer may see it; this module only shapes the already-narrow data:

* columns = the subject's recorded lessons (``recorded_lessons``: instructor / created_by / own mark);
* cells = only marks the subject entered, or NULL-author marks on lessons the subject actually taught;
* rows = only students that have at least one such visible cell in the shown lessons (no roster beyond that).

Everything is read in a bounded number of queries (lessons + one marks prefetch + rooms/section names), independent
of the number of lessons or students.
"""

from __future__ import annotations

from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.translation import pgettext

from . import journal_lesson_timing, lab_groups, seminar_groups
from .journal_names import journal_student_name
from .models import Enrollment, LessonMark
from .practical_label import kind_label, offering_is_practical

_CTX = "registrar.own_history"
KINDS = ("lecture", "seminar", "lab")


def visible_marks(offering, subject):
    """Cells the subject may be shown: own entered marks, or unknown-author marks on lessons the subject taught."""
    return (
        LessonMark.objects.filter(
            organization_id=offering.organization_id,
            lesson__organization_id=offering.organization_id,
            enrollment__organization_id=offering.organization_id,
        )
        .filter(Q(entered_by=subject) | Q(entered_by__isnull=True, lesson__instructor=subject))
        .select_related("enrollment__student__profile")
    )


def load_lessons(lessons, offering, subject) -> list:
    """Recorded lessons (date order) with ``author_marks`` prefetched — two queries in total."""
    rows = list(
        lessons.order_by("date", "start_time", "created_at", "pk").prefetch_related(
            Prefetch("marks", queryset=visible_marks(offering, subject), to_attr="author_marks")
        )
    )
    for lesson in rows:
        lesson.offering = offering  # kind display / section labels read the cached offering, no query per lesson
    return rows


def _short_kind(kind, practical) -> str:
    if kind == "lecture":
        return pgettext(_CTX, "Müh.")
    if kind == "lab":
        return pgettext(_CTX, "Lab.")
    return pgettext(_CTX, "Prak.") if practical else pgettext(_CTX, "Sem.")


def _section(lesson, offering) -> str:
    if lesson.kind == "lab" and lesson.lab_group:
        return lab_groups.label(lesson.lab_group, offering)
    if lesson.kind == "seminar" and lesson.seminar_group:
        return seminar_groups.label(lesson.seminar_group, offering)
    return ""


def _stamp(value) -> str:
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M") if value else ""


def _role(lesson, subject_id) -> str:
    if lesson.instructor_id == subject_id:
        return pgettext(_CTX, "Keçirib")
    if lesson.created_by_id == subject_id:
        return pgettext(_CTX, "Dərsi yaradıb")
    return pgettext(_CTX, "Yalnız qeyd daxil edib")


def _summary(lessons, subject_id, labels, timing) -> dict:
    """Lesson count + taught hours by kind. Hours = explicit ``Lesson.instructor`` only, passive excluded
    (created_by / mark-only lessons are history, never the subject's taught hours)."""
    by_kind = []
    for kind in KINDS:
        rows = [lesson for lesson in lessons if lesson.kind == kind]
        if not rows:
            continue
        hours = sum(
            lesson.hours or 0 for lesson in rows if lesson.instructor_id == subject_id and not lesson.is_passive
        )
        by_kind.append({"kind": kind, "label": labels[kind], "lessons": len(rows), "hours": hours if timing else None})
    return {
        "lessons": len(lessons),
        "hours": sum(item["hours"] for item in by_kind) if timing else None,
        "by_kind": by_kind,
        "first": lessons[0].date if lessons else None,
        "last": lessons[-1].date if lessons else None,
    }


def _rows(shown, subject_id) -> list:
    students: dict = {}
    for index, lesson in enumerate(shown):
        for mark in lesson.author_marks:
            enrollment = mark.enrollment
            row = students.get(enrollment.pk)
            if row is None:
                student = enrollment.student
                row = students[enrollment.pk] = {
                    "name": journal_student_name(student),
                    "sort": ((student.last_name or "").casefold(), (student.username or "").casefold()),
                    "marks": {},
                }
            row["marks"][index] = mark
    # Journal order (``read_memo.enrolled_roster``): the database collation of surname, then login — one query.
    rank = {
        pk: index
        for index, pk in enumerate(
            Enrollment.objects.filter(pk__in=list(students))
            .order_by("student__last_name", "student__username", "pk")
            .values_list("pk", flat=True)
        )
    }
    ordered = [students[pk] for pk in sorted(students, key=lambda pk: (rank.get(pk, len(rank)), students[pk]["sort"]))]
    for row in ordered:
        marks = row.pop("marks")
        row["cells"] = [
            {"mark": marks.get(index), "own": bool(marks.get(index)) and marks[index].entered_by_id == subject_id}
            for index in range(len(shown))
        ]
    return ordered


def build(offering, subject, lessons, *, kind="", timing=False) -> dict:
    """Template context for the grid, the kind tabs and the «Nə vaxt, harada yazılıb» table.

    ``timing`` — start–end time, per-lesson hours, room and the «Yazılıb» moments. Owner 2026-11-17/19: staff only,
    never the teacher's own view (``journal_lesson_timing.show_lesson_timing``); when ``False`` none of it leaves this
    module (templates must not read ``lesson.hours`` / ``lesson.room`` either)."""
    practical = offering_is_practical(offering)
    labels = {value: kind_label(value, practical=practical) for value in KINDS}
    kinds_present = [value for value in KINDS if any(lesson.kind == value for lesson in lessons)]
    kind = kind if kind in kinds_present else ""
    shown = [lesson for lesson in lessons if not kind or lesson.kind == kind]
    if timing:
        journal_lesson_timing.attach_rooms(offering, shown)
    from .journal_topics import attach_syllabus_topics

    attach_syllabus_topics(shown, offering=offering)
    subject_id = subject.pk
    columns = []
    for lesson in shown:
        own_stamps = [mark.updated_at for mark in lesson.author_marks if mark.entered_by_id == subject_id]
        own_stamps = own_stamps if timing else []
        columns.append(
            {
                "lesson": lesson,
                "short": _short_kind(lesson.kind, practical),
                "label": labels.get(lesson.kind, lesson.kind),
                "section": _section(lesson, offering),
                "time": journal_lesson_timing.time_range(lesson) if timing else "",
                "room": journal_lesson_timing.room_text(lesson) if timing else "",
                "role": _role(lesson, subject_id),
                "lesson_recorded": _stamp(lesson.created_at) if timing and lesson.created_by_id == subject_id else "",
                "marks_recorded": _stamp(max(own_stamps)) if own_stamps else "",
                "imported": journal_lesson_timing.is_imported(lesson),
                "cells": sum(1 for _mark in lesson.author_marks),
            }
        )
    return {
        "summary": _summary(lessons, subject_id, labels, timing),
        "kind_tabs": [{"value": value, "label": labels[value]} for value in kinds_present],
        "selected_kind": kind,
        "columns": columns,
        "rows": _rows(shown, subject_id),
        "show_timing": timing,
        "has_unknown_cells": any(mark.entered_by_id is None for lesson in shown for mark in lesson.author_marks),
    }


__all__ = ["KINDS", "build", "load_lessons", "visible_marks"]
