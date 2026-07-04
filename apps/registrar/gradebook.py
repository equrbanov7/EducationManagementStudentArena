"""Elektron jurnal (davamiyyət/qiymət jurnalı) — services (U3, UNEC modeli).

Müəllim hər dərs (``Lesson``) günü tələbələrin iştirak/qayıbını (iə/qb), seminar
və laboratoriya dərslərində isə balını (``LessonMark``) yazır — mühazirədə yalnız
iə/qb. Sistem keçirilmiş dərsləri, qayıb saatını və "giriş balı"nı (seminar/lab
ballarının cəmi) AVTOMATİK hesablayır. Yekun imtahan burada yoxdur.

Kilid qaydaları (geriyə-dönük dəyişiklik olmasın):
* dərs tarixi yaranışdan sonra yalnız qısa müddət (``DATE_EDIT_WINDOW``) dəyişilir;
* iştirak/bal xanası yazıldıqdan ``MARK_EDIT_WINDOW`` sonra kilidlənir.

Status (görünüş): qayıb saatı proqramın ``absence_limit_percent``-i × fənnin tam
saatını keçirsə → tələbə "kəsilir" (imtahana buraxılmır, sətir qırmızı); limitə
yaxınlaşırsa → xəbərdarlıq (sətir bozarır).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.registrar import services
from apps.registrar.models import (
    AssessmentScheme,
    AttendanceStatus,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    StudentAcademicRecord,
)

# Redaktə pəncərələri.
DATE_EDIT_WINDOW = timedelta(minutes=5)  # dərs tarixi yaranışdan sonra
MARK_EDIT_WINDOW = timedelta(days=1)  # iştirak/bal yazıldıqdan sonra

DEFAULT_LESSON_HOURS = 2
_DEFAULT_ABSENCE_LIMIT = 25
_WARN_RATIO = Decimal("0.75")  # limitin bu payına çatanda xəbərdarlıq (bozarır)

SCORE_LESSON_KINDS = frozenset({LessonKind.SEMINAR, LessonKind.LAB})


def _to_decimal(raw) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def ensure_assessment_scheme(*, offering):
    """Idempotently return the offering's journal config."""
    scheme, _created = AssessmentScheme.objects.get_or_create(organization=offering.organization, offering=offering)
    return scheme


def lesson_allows_score(lesson) -> bool:
    """Only seminar / lab lessons carry a score; lectures are attendance-only."""
    return lesson.kind in SCORE_LESSON_KINDS


def can_edit_lesson_date(lesson, *, now=None) -> bool:
    now = now or timezone.now()
    return (now - lesson.created_at) <= DATE_EDIT_WINDOW


def can_edit_mark(mark, *, now=None) -> bool:
    """A missing mark is always writable; an existing one only within the window."""
    if mark is None:
        return True
    now = now or timezone.now()
    return (now - mark.created_at) <= MARK_EDIT_WINDOW


def absence_limit_percent_for(offering) -> int:
    record = (
        StudentAcademicRecord.objects.filter(organization=offering.organization, group=offering.group)
        .select_related("program")
        .first()
    )
    if record and record.program:
        return record.program.absence_limit_percent
    return _DEFAULT_ABSENCE_LIMIT


# ── Lesson (dərs) CRUD ───────────────────────────────────────────────────────


@transaction.atomic
def create_lesson(*, offering, date, kind=LessonKind.LECTURE, topic="", hours=None, created_by=None):
    """Add a held session (a new journal column)."""
    ensure_assessment_scheme(offering=offering)
    return Lesson.objects.create(
        organization=offering.organization,
        offering=offering,
        date=date,
        kind=kind,
        topic=topic or "",
        hours=hours or DEFAULT_LESSON_HOURS,
        created_by=created_by,
    )


@transaction.atomic
def update_lesson_date(*, lesson, date) -> bool:
    """Fix a wrong lesson date — only within the short post-creation window."""
    if not can_edit_lesson_date(lesson):
        return False
    lesson.date = date
    lesson.save(update_fields=["date"])
    return True


# ── Mark (iştirak/bal) yazma ─────────────────────────────────────────────────


@transaction.atomic
def save_marks(*, offering, entries, by_user=None):
    """Persist attendance/score cells for an offering (bulk, from the grid).

    ``entries``: iterable of ``{"lesson_id", "enrollment_id", "status", "score"}``.
    Each cell is validated against the offering's own lessons/enrollments
    (cross-offering/tenant injection rejected), honours the per-mark edit window
    (locked cells are skipped) and the lesson type (lecture cells never store a
    score). Blocked entirely when the scheme is published. Returns cells written.
    """
    scheme = ensure_assessment_scheme(offering=offering)
    if scheme.is_published:
        return 0

    lessons = {str(latt.id): latt for latt in offering.lessons.all()}
    enrollments = {str(e.id): e for e in offering.enrollments.filter(status=Enrollment.Status.ENROLLED)}
    existing = {(m.lesson_id, m.enrollment_id): m for m in LessonMark.objects.filter(lesson__offering=offering)}

    written = 0
    touched = set()
    now = timezone.now()
    for entry in entries or []:
        lesson = lessons.get(str(entry.get("lesson_id")))
        enrollment = enrollments.get(str(entry.get("enrollment_id")))
        if lesson is None or enrollment is None:
            continue
        mark = existing.get((lesson.id, enrollment.id))
        if not can_edit_mark(mark, now=now):
            continue  # locked — no back-dated tampering

        status = entry.get("status")
        if status not in (AttendanceStatus.PRESENT, AttendanceStatus.ABSENT):
            status = AttendanceStatus.PRESENT
        score = None
        if lesson_allows_score(lesson) and entry.get("score") not in (None, ""):
            score = max(Decimal("0"), _to_decimal(entry.get("score")))

        if mark is None:
            mark = LessonMark(organization=offering.organization, lesson=lesson, enrollment=enrollment)
        mark.status = status
        mark.score = score
        mark.entered_by = by_user
        mark.save()
        touched.add(enrollment)
        written += 1

    # Keep the denormalised Enrollment.absence_hours (used by the "Fənlərim"
    # exam-eligibility badge) in sync with the journal — the single source of truth.
    for enrollment in touched:
        recompute_absence_hours(enrollment=enrollment)

    return written


def recompute_absence_hours(*, enrollment):
    """Recompute Enrollment.absence_hours from the student's lesson marks (qb)."""
    hours = sum(
        m.lesson.hours
        for m in LessonMark.objects.filter(enrollment=enrollment, status=AttendanceStatus.ABSENT).select_related(
            "lesson"
        )
    )
    if enrollment.absence_hours != hours:
        enrollment.absence_hours = hours
        enrollment.save(update_fields=["absence_hours"])
    return hours


# ── Jurnal görünüşü (müəllim grid) ───────────────────────────────────────────


def _allowed_absence_hours(offering, lessons):
    total_hours = offering.lesson_hours or sum(latt.hours for latt in lessons)
    return Decimal(total_hours) * Decimal(absence_limit_percent_for(offering)) / Decimal(100)


def get_offering_journal(*, offering):
    """Full journal grid: lessons (columns) × enrolled students (rows) + summary.

    One pass over the marks (no per-cell query). Each row carries the running
    absence hours, the accumulated entry score (giriş balı, capped) and the
    barred / warning status used to grey or redden the row."""
    scheme = ensure_assessment_scheme(offering=offering)
    lessons = list(offering.lessons.all())
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    mark_map = {(m.enrollment_id, m.lesson_id): m for m in LessonMark.objects.filter(lesson__offering=offering)}

    now = timezone.now()
    allowed_absence = _allowed_absence_hours(offering, lessons)
    warn_at = allowed_absence * _WARN_RATIO

    rows = []
    for enrollment in enrollments:
        cells = []
        absence_hours = 0
        entry_score = Decimal("0")
        for lesson in lessons:
            mark = mark_map.get((enrollment.id, lesson.id))
            if mark is not None and mark.status == AttendanceStatus.ABSENT:
                absence_hours += lesson.hours
            if mark is not None and mark.score is not None:
                entry_score += mark.score
            cells.append(
                {
                    "lesson": lesson,
                    "mark": mark,
                    "allows_score": lesson_allows_score(lesson),
                    "locked": mark is not None and not can_edit_mark(mark, now=now),
                }
            )
        entry_score = min(entry_score, Decimal(scheme.entry_score_max))
        barred = allowed_absence > 0 and Decimal(absence_hours) > allowed_absence
        warning = (not barred) and allowed_absence > 0 and Decimal(absence_hours) >= warn_at
        rows.append(
            {
                "enrollment": enrollment,
                "student": enrollment.student,
                "cells": cells,
                "absence_hours": absence_hours,
                "entry_score": entry_score,
                "barred": barred,
                "warning": warning,
            }
        )

    return {
        "offering": offering,
        "scheme": scheme,
        "lessons": lessons,
        "rows": rows,
        "limit_percent": absence_limit_percent_for(offering),
        "allowed_absence": allowed_absence,
        "entry_score_max": scheme.entry_score_max,
    }


# ── Tələbə görünüşü ("Qiymətlərim") ──────────────────────────────────────────


def get_student_journal_summary(*, record, period, semester_number):
    """Per-subject entry score + attendance for the student view.

    Computes each enrolled subject's absence hours and accumulated entry score
    from this student's own lesson marks (only their row — never the roster)."""
    plan = services.get_student_semester_plan(record=record, period=period, semester_number=semester_number)
    limit_percent = record.program.absence_limit_percent if record.program else _DEFAULT_ABSENCE_LIMIT
    subjects = []
    for enrollment in plan["enrollments"]:
        offering = enrollment.offering
        marks = list(LessonMark.objects.filter(enrollment=enrollment).select_related("lesson"))
        absence_hours = sum(m.lesson.hours for m in marks if m.status == AttendanceStatus.ABSENT)
        entry_score = sum((m.score for m in marks if m.score is not None), Decimal("0"))
        scheme = getattr(offering, "assessment_scheme", None)
        cap = scheme.entry_score_max if scheme else 50
        entry_score = min(entry_score, Decimal(cap))
        lessons_held = offering.lessons.count()
        total_hours = offering.lesson_hours or 0
        allowed = Decimal(total_hours) * Decimal(limit_percent) / Decimal(100)
        barred = allowed > 0 and Decimal(absence_hours) > allowed
        subjects.append(
            {
                "enrollment": enrollment,
                "subject": offering.subject,
                "ects": offering.subject.ects,
                "kind": enrollment.kind,
                "journal": {
                    "lessons_held": lessons_held,
                    "absence_hours": absence_hours,
                    "allowed_absence": allowed,
                    "entry_score": entry_score,
                    "entry_score_max": cap,
                    "barred": barred,
                },
            }
        )
    return {"subjects": subjects}
