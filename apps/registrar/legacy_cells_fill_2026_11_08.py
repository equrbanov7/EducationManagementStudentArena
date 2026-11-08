"""Köhnə sistemin xanalarını EMS jurnalının BOŞ xanalarına yazmaq (sahib 2026-11-08) — ``fill_legacy_cells_20261108``.

Sahib: «boş xanalar olması yəqin ki köçəndə gəlməyib, onları doldur … köhnə DB-dən dataları çəkib gətir, jurnal
yazılmış olsun, içi boş olmasın». Plan lokal qurulur (köhnə sistem ``journals_dates_points`` ↔ prod jurnalı: dərs
tarix + saat + növ, tələbə jurnalın öz siyahısında ad ilə) və YALNIZ id-lərdir::

    {"format": "legacy-cells/1", "cells": [{"lesson": uuid, "enrollment": uuid, "status": "present"|"absent"|"excused",
      "score": null | ədəd}]}

Qaydalar (hər xana kilid altında yenidən yoxlanılır; uyğun gəlməyən sayılır, yazılmır):

* dərs və qeydiyyat EYNİ açılışdandır, açılış aktivdir və bağlı deyil, qeydiyyat ``enrolled``-dir;
* xana BOŞDUR — müəllimin (və ya əvvəlki köçürmənin) yazdığı xanaya toxunulmur;
* dərs tələbəyə aiddir (lab / seminar alt qrupu — :func:`apps.registrar.lab_groups.applies`);
* bal yalnız bal götürən dərsdə (seminar / lab) və 0..10 aralığında; mühazirədə yalnız davamiyyət;
* dərsin tarixi köhnə datanın son günündən (:data:`LAST_LEGACY_DAY`) sonra deyil.

Yaradılan xanaların id-ləri audit sətrindədir — ``--undo`` YALNIZ onları (sonradan dəyişməyibsə) silir. Qayıb saatı
yenidən hesablanır. İdempotentdir: ikinci qaçışda xana artıq doludur → ``cells_already_filled``.
"""

from __future__ import annotations

import datetime
import json

from django.apps import apps as django_apps
from django.core.management.base import CommandError
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import lab_groups
from .gradebook import lesson_allows_score
from .twin_relocate import closed, recompute_absences

FORMAT = "legacy-cells/1"
REASON = "Sahib 2026-11-08: köhnə sistemin xanaları EMS jurnalının boş xanalarına (yalnız boş xana)"
UNDO_REASON = "Sahib 2026-11-08: köhnə sistemdən doldurulan xanaların geri qaytarılması"
RESOURCE = "registrar.legacy_cells_fill"
LAST_LEGACY_DAY = datetime.date(2026, 10, 21)
STATUSES = ("present", "absent", "excused")
MAX_SCORE = 10


def _model(name):
    return django_apps.get_model("registrar", name)


def load_plan(path) -> list:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise CommandError("legacy_cells_file_unreadable") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise CommandError("legacy_cells_format_unknown")
    return list(data.get("cells") or [])


def run(*, organization, actor, counts, cells) -> None:
    Lesson, Enrollment, LessonMark = _model("Lesson"), _model("Enrollment"), _model("LessonMark")
    lessons = {
        str(row.pk): row
        for row in Lesson.objects.select_related("offering").filter(
            organization=organization, pk__in=[cell.get("lesson") for cell in cells]
        )
    }
    enrollments = {
        str(row.pk): row
        for row in Enrollment.objects.select_for_update(of=("self",)).filter(
            organization=organization, pk__in=[cell.get("enrollment") for cell in cells]
        )
    }
    shut = closed({lesson.offering_id for lesson in lessons.values()})
    filled = set(
        LessonMark.objects.filter(lesson_id__in=list(lessons), enrollment_id__in=list(enrollments)).values_list(
            "lesson_id", "enrollment_id"
        )
    )
    created, touched = [], {}
    for cell in cells:
        lesson, enrollment = lessons.get(str(cell.get("lesson"))), enrollments.get(str(cell.get("enrollment")))
        status, score = cell.get("status"), cell.get("score")
        if lesson is None or enrollment is None or enrollment.offering_id != lesson.offering_id:
            counts["cells_target_mismatch"] += 1
        elif not lesson.offering.is_active or str(lesson.offering_id) in shut or enrollment.status != "enrolled":
            counts["cells_journal_closed_or_inactive"] += 1
        elif (lesson.pk, enrollment.pk) in filled:
            counts["cells_already_filled"] += 1
        elif status not in STATUSES or lesson.date > LAST_LEGACY_DAY:
            counts["cells_invalid"] += 1
        elif not lab_groups.applies(lesson, enrollment):
            counts["cells_other_subgroup"] += 1
        elif score is not None and (not lesson_allows_score(lesson) or not 0 <= float(score) <= MAX_SCORE):
            counts["cells_score_not_allowed"] += 1
        else:
            mark = LessonMark.objects.create(
                organization=organization, lesson=lesson, enrollment=enrollment, status=status, score=score
            )
            filled.add((lesson.pk, enrollment.pk))
            created.append(str(mark.pk))
            touched[enrollment.pk] = enrollment
            counts["cells_filled"] += 1
            counts["cells_filled_scored" if score is not None else "cells_filled_attendance"] += 1
    recompute_absences(list(touched.values()))
    if created:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"cells": len(created)},
            changes={"marks_created": created},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=timezone.now().strftime("%Y%m%d%H%M%S"),
        )


def undo(*, organization, actor, counts) -> None:
    AuditLog, LessonMark = django_apps.get_model("audit", "AuditLog"), _model("LessonMark")
    for row in AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON):
        ids = (row.changes or {}).get("marks_created") or []
        rows = list(LessonMark.objects.select_related("enrollment").filter(pk__in=ids))
        marks = [mark for mark in rows if (mark.updated_at - mark.created_at).total_seconds() < 5]
        counts["undo_cells_changed_kept"] += len(rows) - len(marks)
        enrollments = {mark.enrollment_id: mark.enrollment for mark in marks}
        counts["undo_cells_deleted"] += LessonMark.objects.filter(pk__in=[mark.pk for mark in marks]).delete()[0]
        counts["undo_cells_already_gone"] += len(ids) - len(rows)
        recompute_absences(list(enrollments.values()))
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"cells": len(marks)},
            reason=UNDO_REASON,
            resource_type=RESOURCE,
            resource_id=row.resource_id,
        )


__all__ = ["FORMAT", "load_plan", "run", "undo"]
