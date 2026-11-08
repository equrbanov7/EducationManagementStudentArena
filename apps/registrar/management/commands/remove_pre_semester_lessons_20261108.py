"""``remove_pre_semester_lessons_20261108`` — cari semestrin başlanğıcından ƏVVƏL tarixli dərslər (sahib 2026-11-08).

Sahib: «ayın 15-dən tez jurnala nə isə yazıla bilməz … bütün sistemə tətbiq et, 15-dən tez nə yazılıbsa o xanalar
silinsin». Cari semestrin (``is_current``) bütün jurnallarında ``date < period.start_date`` olan dərslər xanaları ilə
silinir; rəsmi düzəlişi (``LessonCorrection`` / ``JournalCorrection``) olan dərs toxunulmur və sayılır. Silinən hər
dərs və xana (bütün sahələri, ``created_at`` daxil) audit sətrindədir — ``--undo`` onları eynilə yenidən yaradır.
Qayıb saatı yenidən hesablanır. Defolt dry-run; stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import datetime

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ...mexanika_lessons_fix_2026_11_08 import _fields, _snapshot
from ...twin_relocate import corrected_lesson_ids, corrected_mark_ids, recompute_absences
from .relocate_twin_enrollment import run_plan

PREFIX = "pre_semester:"
RESOURCE = "registrar.pre_semester_lessons"
REASON = "Sahib 2026-11-08: semestrin başlanğıcından əvvəl tarixli dərslər silindi"


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def _period(organization):
    return (
        _model("AcademicPeriod", "organizations")
        .objects.filter(organization=organization, is_current=True, is_active=True)
        .order_by("-start_date")
        .first()
    )


def remove(organization, actor, counts) -> None:
    Lesson = _model("Lesson")
    period = _period(organization)
    if period is None or not period.start_date:
        counts["period_missing"] += 1
        return
    lessons = list(
        Lesson.objects.select_for_update()
        .filter(organization=organization, offering__period=period, date__lt=period.start_date)
        .prefetch_related("marks")
        .order_by("offering_id", "date", "start_time")
    )
    counts["lessons_found"] = len(lessons)
    corrected = corrected_lesson_ids([lesson.pk for lesson in lessons])
    items, touched, offerings = [], {}, set()
    for lesson in lessons:
        marks = list(lesson.marks.select_related("enrollment"))
        if str(lesson.pk) in corrected or corrected_mark_ids([mark.pk for mark in marks]):
            counts["lessons_corrected_kept"] += 1
            continue
        items.append(
            {
                "lesson": _snapshot(lesson),
                "marks": [
                    {
                        "enrollment": str(mark.enrollment_id),
                        "status": mark.status,
                        "score": None if mark.score is None else str(mark.score),
                        "entered_by": mark.entered_by_id,
                        "created_at": mark.created_at.isoformat(),
                    }
                    for mark in marks
                ],
            }
        )
        touched.update((mark.enrollment_id, mark.enrollment) for mark in marks)
        offerings.add(lesson.offering_id)
        counts["marks_deleted"] += len(marks)
        counts["lessons_deleted"] += 1
        lesson.delete()
    counts["journals_touched"] = len(offerings)
    recompute_absences(list(touched.values()))
    if items:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            changes={"items": items},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=timezone.now().strftime("%Y%m%d%H%M%S%f"),
        )


def undo(organization, actor, counts) -> None:
    Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
    rows = _model("AuditLog", "audit").objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON)
    touched = {}
    for row in rows.order_by("-created_at"):
        for item in (row.changes or {}).get("items") or []:
            snapshot = item["lesson"]
            if Lesson.objects.filter(pk=snapshot["id"]).exists():
                counts["undo_already"] += 1
                continue
            homes = {
                str(e.pk): e
                for e in Enrollment.objects.filter(pk__in=[m["enrollment"] for m in item.get("marks") or []])
            }
            lesson = Lesson.objects.create(
                organization=organization, offering_id=snapshot["offering"], **_fields(snapshot)
            )
            Lesson.objects.filter(pk=lesson.pk).update(
                created_at=datetime.datetime.fromisoformat(snapshot["created_at"])
            )
            for mark in item.get("marks") or []:
                home = homes.get(mark["enrollment"])
                if home is None:
                    counts["undo_enrollment_missing"] += 1
                    continue
                created = LessonMark.objects.create(
                    organization=organization,
                    lesson=lesson,
                    enrollment=home,
                    status=mark["status"],
                    score=mark["score"],
                    entered_by_id=mark.get("entered_by"),
                )
                LessonMark.objects.filter(pk=created.pk).update(
                    created_at=datetime.datetime.fromisoformat(mark["created_at"])
                )
                touched[home.pk] = home
            counts["undo_lessons_restored"] += 1
    recompute_absences(list(touched.values()))


class Command(BaseCommand):
    help = "Sahib 2026-11-08: semestrin başlanğıcından əvvəl tarixli dərslər (xanaları ilə) silinir (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--undo", action="store_true", help="Silinən dərsləri geri qaytar")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        def runner(organization, actor, counts):
            (undo if options["undo"] else remove)(organization, actor, counts)

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
