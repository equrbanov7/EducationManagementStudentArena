"""«Alt qrupa yerləşdirmə» — OXU tərəfi: fənn nəticələri, cədvəl toqquşması, uyğun jurnallar (2026-10-18).

Yazı YOXDUR (``ensure_assessment_scheme`` kimi yan-təsirli oxu da yox — kilid xəritəsi birbaşa sxem
cədvəlindən oxunur). Hər funksiya sabit sorğu sayı ilə işləyir (siyahı uzunluğundan asılı deyil):

* :func:`subject_outcomes` — tələbənin fənn üzrə keçib/kəsilib vəziyyəti (``analytics`` toplu qiymətləndiricisi
  — ``compute_final_result``-un rəsmi güzgüsü, transkriptlə EYNİ keçmə qaydası);
* :func:`own_schedule` + :func:`clashes` — tələbənin öz cədvəli ilə hədəf jurnalın slotlarının kəsişməsi
  (``schedule`` modulunun üst/alt həftə və vaxt aralığı qaydaları);
* :func:`candidate_offerings` — fənnin bu semestrdə BAŞQA qruplardakı aktiv jurnalları: müəllim, cədvəl,
  tutum, kredit təsiri, toqquşma, siyahı qapısı.
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count, Q

from . import analytics, credit_load, guest_roster, schedule
from .exam_eligibility import _LOCKED_STATUSES
from .models import AssessmentScheme, CourseOffering, Enrollment, ScheduleSlot

_WEEKDAY_LABELS = dict(schedule.WEEKDAYS)


# ── Fənn nəticələri (keçib / kəsilib) ────────────────────────────────────────


def subject_outcomes(*, student, organization, exclude_period_id=None, subject_ids=None) -> dict:
    """``{subject_id: {"passed", "failed", "attempts", "last_period", "code", "name", "ects"}}``.

    ``dropped`` sətirlər (geri götürülmüş / əvəzlənmiş / «Fəndən azad») sayılmır. ``exclude_period_id`` —
    cari semestr (hələ yekunlaşmamış yazılış «kəsilib» sayılmasın deyə nəticədən çıxarılır).
    """
    queryset = (
        Enrollment.objects.filter(organization=organization, student=student)
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("offering__subject", "offering__period")
    )
    if exclude_period_id is not None:
        queryset = queryset.exclude(offering__period_id=exclude_period_id)
    if subject_ids is not None:
        queryset = queryset.filter(offering__subject_id__in=list(subject_ids))
    enrollments = list(queryset)
    if not enrollments:
        return {}
    maps = analytics.build_evaluation_maps(organization, enrollments)
    outcomes: dict = {}
    for enrollment in sorted(enrollments, key=lambda e: e.offering.period.start_date):
        result = analytics.evaluate_enrollment(enrollment, maps)
        subject = enrollment.offering.subject
        entry = outcomes.setdefault(
            subject.pk,
            {
                "subject_id": str(subject.pk),
                "code": subject.code,
                "name": subject.name,
                "ects": int(subject.ects or 0),
                "passed": False,
                "failed": False,
                "attempts": 0,
                "last_period": "",
                "barred": False,
            },
        )
        entry["attempts"] += 1
        entry["last_period"] = f"{enrollment.offering.period.year_display} · {enrollment.offering.period.name}"
        if result.get("passed"):
            entry["passed"] = True
        elif result.get("failed"):
            entry["failed"] = True
            entry["barred"] = bool(result.get("barred"))
    for entry in outcomes.values():
        if entry["passed"]:
            entry["failed"] = False
    return outcomes


def failed_subjects(outcomes: dict) -> list:
    """Kəsilib və sonradan keçilməmiş fənlər (ad üzrə sıralı)."""
    return sorted((row for row in outcomes.values() if row["failed"]), key=lambda row: row["name"].lower())


# ── Cədvəl toqquşması ────────────────────────────────────────────────────────


def _slot_dict(slot) -> dict:
    return {
        "weekday": slot.weekday,
        "weekday_label": str(_WEEKDAY_LABELS.get(slot.weekday, slot.weekday)),
        "start": slot.start_time.strftime("%H:%M"),
        "end": slot.end_time.strftime("%H:%M"),
        "week_type": slot.week_type,
        "kind": slot.kind,
        "kind_label": str(slot.get_kind_display()),
        "room": slot.room or "",
    }


def own_schedule(*, organization, student, record, period, exclude_offering_ids=()) -> list:
    """Tələbənin öz cədvəlinin slotları (qrup + aktiv qeydiyyatlar; «Fəndən azad» xaric)."""
    if period is None:
        return []
    group = getattr(record, "group", None)
    excluded = {str(value) for value in exclude_offering_ids if value}
    return [
        slot
        for slot in schedule.get_student_schedule(organization, student, group, period)
        if str(slot.offering_id) not in excluded
    ]


def clashes(target_slots, own_slots) -> list:
    """Hədəf jurnalın slotları ilə öz cədvəlin kəsişmələri (gün + həftə tipi + vaxt aralığı)."""
    found = []
    for target in target_slots:
        for own in own_slots:
            if own.offering_id == target.offering_id or own.weekday != target.weekday:
                continue
            if not schedule._week_types_overlap(own.week_type, target.week_type):
                continue
            if not schedule._time_ranges_overlap(own.start_time, own.end_time, target.start_time, target.end_time):
                continue
            row = _slot_dict(target)
            row["with_subject"] = own.offering.subject.name
            row["with_group"] = getattr(own.offering.group, "name", "") or ""
            row["with_time"] = f"{own.start_time.strftime('%H:%M')}–{own.end_time.strftime('%H:%M')}"
            found.append(row)
    return found


def offering_slots(offering_ids) -> dict:
    """``{offering_id: [slot, …]}`` — cədvəldə duran slotlar (parklanmış xaric), TƏK sorğu."""
    mapping: dict = defaultdict(list)
    ids = [value for value in offering_ids if value]
    if not ids:
        return mapping
    for slot in ScheduleSlot.objects.filter(offering_id__in=ids, is_parked=False).order_by("weekday", "start_time"):
        mapping[slot.offering_id].append(slot)
    return mapping


# ── Uyğun jurnallar ──────────────────────────────────────────────────────────


def locked_offering_ids(offering_ids) -> set:
    """Bağlı jurnallar (``gradebook.journal_is_locked`` güzgüsü) — yan-təsirsiz, TƏK sorğu."""
    ids = [value for value in offering_ids if value]
    if not ids:
        return set()
    return set(
        AssessmentScheme.objects.filter(offering_id__in=ids)
        .filter(Q(is_published=True) | Q(approval_status__in=_LOCKED_STATUSES))
        .values_list("offering_id", flat=True)
    )


def enrolled_counts(offering_ids) -> dict:
    ids = [value for value in offering_ids if value]
    if not ids:
        return {}
    rows = (
        Enrollment.objects.filter(offering_id__in=ids, status=Enrollment.Status.ENROLLED)
        .values("offering_id")
        .annotate(total=Count("id"))
    )
    return {row["offering_id"]: row["total"] for row in rows}


def _teacher_label(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def candidate_offerings(*, organization, student, record, subject_id, period, capacity=0) -> list:
    """Fənnin *period*-da BAŞQA qruplardakı aktiv jurnalları + hər biri üçün yerləşdirmə önbaxışı."""
    if period is None or record is None:
        return []
    offerings = list(
        CourseOffering.objects.filter(organization=organization, subject_id=subject_id, period=period, is_active=True)
        .exclude(group_id=record.group_id)
        .select_related("subject", "group", "instructor", "period")
        .order_by("group__name")
    )
    if not offerings:
        return []
    ids = [offering.pk for offering in offerings]
    slots = offering_slots(ids)
    counts = enrolled_counts(ids)
    locked = locked_offering_ids(ids)
    enrolled_here = set(
        Enrollment.objects.filter(
            organization=organization, student=student, offering_id__in=ids, status=Enrollment.Status.ENROLLED
        ).values_list("offering_id", flat=True)
    )
    conflicts = Enrollment.objects.filter(
        organization=organization,
        student=student,
        offering__subject_id=subject_id,
        offering__period=period,
        status=Enrollment.Status.ENROLLED,
    ).exclude(offering_id__in=ids)
    conflict_ids = [str(value) for value in conflicts.values_list("offering_id", flat=True)]
    own_slots = own_schedule(
        organization=organization, student=student, record=record, period=period, exclude_offering_ids=conflict_ids
    )
    plan_credits = credit_load.plan_credit_map(record.curriculum_id, [subject_id])
    period_open = guest_roster.period_allows_roster(period)
    rows = []
    for offering in offerings:
        enrolled = counts.get(offering.pk, 0)
        offering_clashes = clashes(slots.get(offering.pk, []), own_slots)
        rows.append(
            {
                "id": str(offering.pk),
                "group_name": getattr(offering.group, "name", "") or "",
                "teacher": _teacher_label(offering.instructor),
                "slots": [_slot_dict(slot) for slot in slots.get(offering.pk, [])],
                "enrolled": enrolled,
                "capacity": int(capacity or 0),
                "free": max(0, int(capacity) - enrolled) if capacity else None,
                "full": bool(capacity) and enrolled >= int(capacity),
                "credits": credit_load.offering_credit(offering, plan_credits),
                "clashes": offering_clashes,
                "locked": offering.pk in locked or not period_open,
                "already_enrolled": offering.pk in enrolled_here,
                "releases_own": bool(conflict_ids),
            }
        )
    return rows


__all__ = [
    "candidate_offerings",
    "clashes",
    "enrolled_counts",
    "failed_subjects",
    "locked_offering_ids",
    "offering_slots",
    "own_schedule",
    "subject_outcomes",
]
