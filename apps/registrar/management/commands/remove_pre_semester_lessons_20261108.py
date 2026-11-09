"""``remove_pre_semester_lessons_20261108`` — cari semestrin başlanğıcından ƏVVƏL tarixli dərslər (sahib 2026-11-08).

Sahib: «ayın 15-dən tez jurnala nə isə yazıla bilməz … bütün sistemə tətbiq et, 15-dən tez nə yazılıbsa o xanalar
silinsin». Cari semestrin (``is_current``) bütün jurnallarında ``date < period.start_date`` olan dərslər xanaları ilə
silinir; rəsmi düzəlişi (``LessonCorrection`` / ``JournalCorrection``) olan dərs toxunulmur və sayılır. Audit seçilmiş
dərs/xana sahələrini və ``created_at``-ı saxlayır. Undo yalnız bu sahələri və ilkin dərs ID-sini bərpa edir;
köhnə xana ID-ləri və ``updated_at`` auditdə yoxdur, onların eyniliyi təmin edilmir. Əvəzləyici dərs, dəyişmiş xana
və ya itmiş qeydiyyat varsa bütün bərpa dayanır. Tam eyni vəziyyətə təkrar undo yazısızdır. Bu geniş undo tarixi
düzəltmir və 33 mənbə balının ayrıca bərpa planını əvəz etmir. Qayıb saatı yenidən hesablanır. Defolt dry-run;
stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import datetime

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ...mexanika_lessons_fix_2026_11_08 import FIELDS, _fields, _snapshot
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


def _mark_snapshot(mark):
    return {
        "enrollment": str(mark.enrollment_id),
        "status": mark.status,
        "score": None if mark.score is None else str(mark.score),
        "entered_by": mark.entered_by_id,
        "created_at": mark.created_at.isoformat(),
    }


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
                "marks": [_mark_snapshot(mark) for mark in marks],
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


def _undo_plan(organization, counts):
    """Validate the complete restoration before creating any lesson or mark."""
    Lesson, Enrollment = _model("Lesson"), _model("Enrollment")
    rows = (
        _model("AuditLog", "audit")
        .objects.select_for_update()
        .filter(organization=organization, resource_type=RESOURCE, reason=REASON)
        .order_by("-created_at", "-pk")
    )
    plan, seen, slots = [], set(), set()
    for row in rows:
        for item in (row.changes or {}).get("items") or []:
            snapshot = item["lesson"]
            if snapshot["id"] in seen:
                # A restored lesson can be removed again; only its latest deletion applies.
                counts["undo_older_snapshot_ignored"] += 1
                continue
            seen.add(snapshot["id"])
            offering = (
                _model("CourseOffering")
                .objects.select_for_update()
                .filter(pk=snapshot["offering"], organization=organization)
                .first()
            )
            if offering is None:
                raise CommandError("pre_semester_undo_offering_missing_or_foreign")
            marks = item.get("marks") or []
            existing = Lesson.objects.select_for_update().filter(pk=snapshot["id"]).first()
            if existing is not None:
                if existing.organization_id != organization.pk:
                    raise CommandError("pre_semester_undo_existing_lesson_changed")
                expected = {**snapshot, **{name: snapshot.get(name) for name in FIELDS}}
                actual_marks = [_mark_snapshot(mark) for mark in existing.marks.select_for_update()]
                if _snapshot(existing) != expected or sorted(actual_marks, key=lambda m: m["enrollment"]) != sorted(
                    marks, key=lambda m: m["enrollment"]
                ):
                    raise CommandError("pre_semester_undo_existing_lesson_changed")
                counts["undo_already"] += 1
                continue
            fields = _fields(snapshot)
            slot = {name: fields[name] for name in ("date", "start_time", "kind", "lab_group", "seminar_group")}
            key = (offering.pk, *slot.values())
            if key in slots or Lesson.objects.filter(organization=organization, offering=offering, **slot).exists():
                raise CommandError("pre_semester_undo_replacement_lesson_requires_review")
            slots.add(key)
            enrollment_ids = {mark["enrollment"] for mark in marks}
            homes = {
                str(e.pk): e
                for e in Enrollment.objects.select_for_update().filter(
                    organization=organization, offering=offering, pk__in=enrollment_ids
                )
            }
            if (
                len(enrollment_ids) != len(marks)
                or set(homes) != enrollment_ids
                or any(home.status != "enrolled" or home.superseded_by_id is not None for home in homes.values())
            ):
                raise CommandError("pre_semester_undo_enrollment_missing_or_moved")
            plan.append((snapshot, fields, marks, homes))
    return plan


@transaction.atomic
def undo(organization, actor, counts) -> None:
    Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
    plan = _undo_plan(organization, counts)
    touched = {}
    for snapshot, fields, marks, homes in plan:
        lesson = Lesson.objects.create(
            id=snapshot["id"], organization=organization, offering_id=snapshot["offering"], **fields
        )
        Lesson.objects.filter(pk=lesson.pk).update(created_at=datetime.datetime.fromisoformat(snapshot["created_at"]))
        for mark in marks:
            home = homes[mark["enrollment"]]
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
