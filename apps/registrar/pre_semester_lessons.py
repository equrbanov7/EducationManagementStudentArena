"""Semestrin başlanğıcından ƏVVƏL tarixli dərslərin silinməsi + undo (sahib 2026-11-08 / 2026-11-14).

Ortaq gövdə ``remove_pre_semester_lessons_20261108`` və ``remove_pre_semester_lessons_20261114`` əmrləri üçün.
Hər əmr öz ``reason`` mətni ilə audit yazır və ``undo`` yalnız həmin mətnli audit sətirlərini geri qaytarır — beləliklə
iki qaçışın bərpası bir-birinə qarışmır. Qaydalar (11-08 qaçışından dəyişmədən):

* cari semestrin (``is_current``) bütün jurnallarında ``date < period.start_date`` olan dərslər xanaları ilə silinir;
* rəsmi düzəlişi (``LessonCorrection`` / ``JournalCorrection``) olan dərs toxunulmur və sayılır;
* audit seçilmiş dərs/xana sahələrini və ``created_at``-ı saxlayır; undo yalnız bu sahələri və ilkin dərs ID-sini
  bərpa edir; əvəzləyici dərs, dəyişmiş xana və ya itmiş qeydiyyat varsa bütün bərpa dayanır;
* qayıb saatı yenidən hesablanır.

Sahib 2026-11-14: silinən dərslərin müəllimlərinə (dərsin müəllimi → jurnalın müəllimi → dərsi yaradan) hərəsinə BİR
daxili bildiriş (:func:`notify_teachers`) — silmə ilə EYNİ tranzaksiyada yazılır, yəni yalnız silmə commit olunanda
görünür (push da commit-dən sonra gedir); dry-run-da ikisi də geri qaytarılır.
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .mexanika_lessons_fix_2026_11_08 import FIELDS, _fields, _snapshot
from .twin_relocate import corrected_lesson_ids, corrected_mark_ids, recompute_absences

RESOURCE = "registrar.pre_semester_lessons"
#: Bir bildirişdə ən çox bu qədər jurnal / jurnal başına tarix sadalanır (mətn 2000 simvoldan qısa qalsın).
MAX_JOURNALS_LISTED = 12
MAX_DATES_LISTED = 12


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def current_period(organization):
    return (
        _model("AcademicPeriod", "organizations")
        .objects.filter(organization=organization, is_current=True, is_active=True)
        .order_by("-start_date")
        .first()
    )


def mark_snapshot(mark):
    return {
        "enrollment": str(mark.enrollment_id),
        "status": mark.status,
        "score": None if mark.score is None else str(mark.score),
        "entered_by": mark.entered_by_id,
        "created_at": mark.created_at.isoformat(),
    }


def remove(organization, actor, counts, *, reason) -> list:
    """Silir və auditə yazır; qaytarır: silinən hər dərs üçün ``{"lesson", "offering", "teacher_id"}`` (bildiriş üçün)."""
    Lesson = _model("Lesson")
    period = current_period(organization)
    if period is None or not period.start_date:
        counts["period_missing"] += 1
        return []
    lessons = list(
        Lesson.objects.select_for_update(of=("self",))
        .filter(organization=organization, offering__period=period, date__lt=period.start_date)
        .select_related("offering", "offering__subject", "offering__group", "offering__period")
        .prefetch_related("marks")
        .order_by("offering_id", "date", "start_time")
    )
    counts["lessons_found"] = len(lessons)
    corrected = corrected_lesson_ids([lesson.pk for lesson in lessons])
    items, touched, offerings, removed = [], {}, set(), []
    for lesson in lessons:
        marks = list(lesson.marks.select_related("enrollment"))
        if str(lesson.pk) in corrected or corrected_mark_ids([mark.pk for mark in marks]):
            counts["lessons_corrected_kept"] += 1
            continue
        items.append({"lesson": _snapshot(lesson), "marks": [mark_snapshot(mark) for mark in marks]})
        removed.append(
            {
                "date": lesson.date,
                "offering": lesson.offering,
                "teacher_id": lesson.instructor_id or lesson.offering.instructor_id or lesson.created_by_id,
            }
        )
        touched.update((mark.enrollment_id, mark.enrollment) for mark in marks)
        offerings.add(lesson.offering_id)
        counts["marks_deleted"] += len(marks)
        counts["lessons_deleted"] += 1
        lesson.delete()
    counts["journals_touched"] = len(offerings)
    counts["teachers_affected"] = len({row["teacher_id"] for row in removed if row["teacher_id"]})
    recompute_absences(list(touched.values()))
    if items:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            changes={"items": items},
            reason=reason,
            resource_type=RESOURCE,
            resource_id=timezone.now().strftime("%Y%m%d%H%M%S%f"),
        )
    return removed


def _journal_label(offering) -> str:
    subject = getattr(offering.subject, "name", "") or "—"
    group = getattr(offering.group, "name", "") or ""
    return f"{subject} · {group}" if group else subject


def _message(start, journals) -> str:
    """``journals``: ``[(etiket, [tarix, …]), …]`` — nəzakətli, qısa, Azərbaycan dilində."""
    lines = []
    for label, dates in journals[:MAX_JOURNALS_LISTED]:
        shown = ", ".join(f"{day:%d.%m.%Y}" for day in dates[:MAX_DATES_LISTED])
        extra = f" və daha {len(dates) - MAX_DATES_LISTED} dərs" if len(dates) > MAX_DATES_LISTED else ""
        lines.append(f"• «{label}»: {shown}{extra}")
    if len(journals) > MAX_JOURNALS_LISTED:
        lines.append(f"• və daha {len(journals) - MAX_JOURNALS_LISTED} jurnal")
    return (
        f"Hörmətli müəllim, semestr {start:%d.%m.%Y} tarixində başlayıb və bu tarixdən əvvəlki günlərə jurnalda dərs "
        "yazmaq olmaz. Ona görə aşağıdakı dərslər jurnaldan silindi:\n"
        + "\n".join(lines)
        + "\nDərs həqiqətən daha gec keçirilibsə, onu düzgün tarixlə yenidən daxil edin. Anlayışınız üçün təşəkkür edirik."
    )


def notify_teachers(organization, removed, counts) -> int:
    """Hər müəllimə BİR daxili bildiriş (e-poçt yox). Aktiv jurnal və aktiv istifadəçi şərtdir; stdout-a yalnız saylar."""
    from apps.notifications.public import create_notifications

    period = current_period(organization)
    by_teacher: dict = defaultdict(lambda: defaultdict(list))
    for row in removed:
        offering = row["offering"]
        if not offering.is_active:
            counts["notify_skipped_inactive_journal"] += 1  # passiv (məs. Kollec) jurnal — müəllimə göstərilmir
            continue
        if not row["teacher_id"]:
            counts["notify_skipped_no_teacher"] += 1
            continue
        by_teacher[row["teacher_id"]][offering].append(row["date"])
    users = {user.pk: user for user in get_user_model().objects.filter(pk__in=list(by_teacher), is_active=True)}
    items = []
    for teacher_id, journals in by_teacher.items():
        user = users.get(teacher_id)
        if user is None:
            counts["notify_skipped_inactive_teacher"] += 1
            continue
        ordered = sorted(journals.items(), key=lambda pair: _journal_label(pair[0]))
        link = (
            reverse("registrar:journal_detail", args=[ordered[0][0].pk])
            if len(ordered) == 1
            else reverse("registrar:journal_list")
        )
        items.append(
            {
                "recipient": user,
                "title": "Semestrin başlanğıcından əvvəlki dərslər silindi",
                "message": _message(period.start_date, [(_journal_label(o), sorted(d)) for o, d in ordered]),
                "link": link,
                "organization": organization,
                "metadata": {
                    "kind": "pre_semester_lessons_removed",
                    "offering_ids": [str(offering.pk) for offering, _dates in ordered],
                    "lessons": sum(len(dates) for _offering, dates in ordered),
                },
            }
        )
    create_notifications(items)
    counts["teachers_notified"] = len(items)
    return len(items)


def _undo_plan(organization, counts, *, reason):
    """Validate the complete restoration before creating any lesson or mark."""
    Lesson, Enrollment = _model("Lesson"), _model("Enrollment")
    rows = (
        _model("AuditLog", "audit")
        .objects.select_for_update()
        .filter(organization=organization, resource_type=RESOURCE, reason=reason)
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
                actual_marks = [mark_snapshot(mark) for mark in existing.marks.select_for_update()]
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
def undo(organization, actor, counts, *, reason) -> None:
    """Yalnız ``reason`` mətnli audit sətirlərinin sildiklərini qaytarır (bildirişlər geri götürülmür)."""
    Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
    plan = _undo_plan(organization, counts, reason=reason)
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


__all__ = ["RESOURCE", "current_period", "mark_snapshot", "notify_teachers", "remove", "undo"]
