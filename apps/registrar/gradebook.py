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

from apps.registrar import grade_audit, services
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    AttendanceStatus,
    ComponentScore,
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


# Approval-chain statuses that freeze the journal (no mark/score edits) — U7.2.
_APPROVAL_LOCK_STATUSES = frozenset({"submitted", "chair_approved", "approved"})


def journal_is_locked(offering) -> bool:
    """The journal is locked once finalised OR while under grade approval."""
    scheme = ensure_assessment_scheme(offering=offering)
    return scheme.is_published or scheme.approval_status in _APPROVAL_LOCK_STATUSES


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
    score). Blocked entirely when the journal is locked. Returns cells written.
    """
    if journal_is_locked(offering):
        return 0

    lessons = {str(latt.id): latt for latt in offering.lessons.all()}
    enrollments = {str(e.id): e for e in offering.enrollments.filter(status=Enrollment.Status.ENROLLED)}
    existing = {(m.lesson_id, m.enrollment_id): m for m in LessonMark.objects.filter(lesson__offering=offering)}

    written = 0
    touched = set()
    audit_changes = []
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

        old = _mark_repr(mark.status, mark.score) if mark is not None and mark.pk else None
        if mark is None:
            mark = LessonMark(organization=offering.organization, lesson=lesson, enrollment=enrollment)
        new = _mark_repr(status, score)
        mark.status = status
        mark.score = score
        mark.entered_by = by_user
        mark.save()
        if old != new:
            audit_changes.append(
                {
                    "student": grade_audit.student_label(enrollment),
                    "item": f"{lesson.date} · {lesson.get_kind_display()}",
                    "old": old or "—",
                    "new": new,
                }
            )
        touched.add(enrollment)
        written += 1

    # Keep the denormalised Enrollment.absence_hours (used by the "Fənlərim"
    # exam-eligibility badge) in sync with the journal — the single source of truth.
    for enrollment in touched:
        recompute_absence_hours(enrollment=enrollment)

    grade_audit.log_grade_changes(offering=offering, by_user=by_user, kind="mark", changes=audit_changes)
    return written


def _mark_repr(status, score) -> str:
    """Compact attendance+score label for the audit trail (e.g. ``qb`` / ``iə 8``)."""
    att = "qb" if status == AttendanceStatus.ABSENT else "iə"
    return f"{att} {grade_audit.score_repr(score)}" if score is not None else att


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
        for lesson in lessons:
            mark = mark_map.get((enrollment.id, lesson.id))
            if mark is not None and mark.status == AttendanceStatus.ABSENT:
                absence_hours += lesson.hours
            cells.append(
                {
                    "lesson": lesson,
                    "mark": mark,
                    "allows_score": lesson_allows_score(lesson),
                    "locked": mark is not None and not can_edit_mark(mark, now=now),
                }
            )
        # Canonical entry score (component-weighted when defined, else lesson sum).
        entry_score = entry_score_for(enrollment, scheme.entry_score_max)
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
        scheme = getattr(offering, "assessment_scheme", None)
        cap = scheme.entry_score_max if scheme else 50
        entry_score = entry_score_for(enrollment, cap)
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


# ── Çəkili qiymətləndirmə komponentləri (U7.1) ───────────────────────────────


def entry_score_for(enrollment, cap) -> Decimal:
    """Canonical semester entry score, capped at ``cap`` (≈ entry_score_max).

    Component-based (weighted) when the offering defines ``AssessmentComponent``
    rows — each score capped at its own ``max_score``; otherwise the legacy sum of
    per-lesson seminar/lab marks. Single source of truth for both the teacher
    journal and the student summary (finals delegates here)."""
    cap = Decimal(cap)
    components = list(AssessmentComponent.objects.filter(offering=enrollment.offering))
    if components:
        max_by = {c.id: Decimal(c.max_score) for c in components}
        total = sum(
            (
                min(cs.score or Decimal("0"), max_by[cs.component_id])
                for cs in ComponentScore.objects.filter(component_id__in=list(max_by), enrollment=enrollment)
            ),
            Decimal("0"),
        )
        return min(total, cap)

    total = sum(
        (m.score for m in LessonMark.objects.filter(enrollment=enrollment) if m.score is not None),
        Decimal("0"),
    )
    return min(total, cap)


def get_components(offering):
    """Ordered assessment components of an offering."""
    return list(AssessmentComponent.objects.filter(offering=offering).order_by("order", "name"))


@transaction.atomic
def save_components(*, offering, definitions, by_user=None):
    """Upsert/delete an offering's assessment components from ``definitions``.

    ``definitions`` = list of ``{"id"?, "name", "max_score", "rubric_id"?}``.
    Rows with an id not present are deleted. Blocked once the journal is locked."""
    if journal_is_locked(offering):
        return get_components(offering)

    from apps.registrar.models import Rubric

    org_rubrics = {str(r.id): r for r in Rubric.objects.filter(organization=offering.organization, is_active=True)}
    existing = {str(c.id): c for c in AssessmentComponent.objects.filter(offering=offering)}
    existing_by_name = {c.name.strip().lower(): c for c in existing.values()}
    seen: set = set()
    for order, defn in enumerate(definitions):
        name = (defn.get("name") or "").strip()
        if not name:
            continue
        max_score = max(1, min(100, int(_to_decimal(defn.get("max_score")))))
        # Match by explicit id, else by (case-insensitive) name so a re-save
        # without ids upserts instead of colliding with the unique (offering, name).
        rubric = org_rubrics.get(str(defn.get("rubric_id") or ""))  # U22: meyar şablonu (opsional)
        component = existing.get(str(defn.get("id") or "")) or existing_by_name.get(name.lower())
        if component is not None and str(component.id) not in seen:
            component.name = name
            component.max_score = max_score
            component.order = order
            component.rubric = rubric
            component.save(update_fields=["name", "max_score", "order", "rubric"])
            seen.add(str(component.id))
        elif component is None:
            created = AssessmentComponent.objects.create(
                organization=offering.organization,
                offering=offering,
                name=name,
                max_score=max_score,
                order=order,
                rubric=rubric,
            )
            seen.add(str(created.id))
    # Drop components the teacher removed from the form.
    for cid, component in existing.items():
        if cid not in seen:
            component.delete()
    return get_components(offering)


@transaction.atomic
def save_component_scores(*, offering, entries, by_user=None):
    """Persist per-(component, enrollment) scores. ``entries`` = list of
    ``{"component_id", "enrollment_id", "score"}``. Lock-aware + tenant-safe."""
    if journal_is_locked(offering):
        return 0

    valid_components = {str(c.id): c for c in AssessmentComponent.objects.filter(offering=offering)}
    valid_enrollments = {str(e.id): e for e in offering.enrollments.all()}
    written = 0
    audit_changes = []
    for entry in entries:
        component = valid_components.get(str(entry.get("component_id")))
        enrollment = valid_enrollments.get(str(entry.get("enrollment_id")))
        if component is None or enrollment is None:
            continue
        existing = ComponentScore.objects.filter(component=component, enrollment=enrollment).first()
        old_score = existing.score if existing else None
        raw = entry.get("score")
        if raw in (None, ""):
            if existing is not None:
                existing.delete()
                audit_changes.append(_component_change(component, enrollment, old_score, None))
            continue
        score = max(Decimal("0"), min(_to_decimal(raw), Decimal(component.max_score)))
        ComponentScore.objects.update_or_create(
            organization=offering.organization,
            component=component,
            enrollment=enrollment,
            defaults={"score": score, "entered_by": by_user},
        )
        if old_score != score:
            audit_changes.append(_component_change(component, enrollment, old_score, score))
        written += 1
    grade_audit.log_grade_changes(offering=offering, by_user=by_user, kind="component", changes=audit_changes)
    return written


def _component_change(component, enrollment, old_score, new_score):
    return {
        "student": grade_audit.student_label(enrollment),
        "item": component.name,
        "old": grade_audit.score_repr(old_score),
        "new": grade_audit.score_repr(new_score),
    }


def get_component_grid(offering):
    """Teacher grid: components (columns) × enrolled students (rows) + scores."""
    components = get_components(offering)
    enrollments = list(
        offering.enrollments.filter(status=offering.enrollments.model.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    comp_ids = [c.id for c in components]
    score_map: dict = {}
    if comp_ids:
        for cs in ComponentScore.objects.filter(component_id__in=comp_ids, enrollment__offering=offering):
            score_map[(cs.enrollment_id, cs.component_id)] = cs.score
    rows = [
        {
            "enrollment": e,
            "student": e.student,
            "cells": [{"component": c, "score": score_map.get((e.id, c.id))} for c in components],
        }
        for e in enrollments
    ]
    total_max = sum(c.max_score for c in components)
    return {"components": components, "rows": rows, "total_max": total_max}


def get_component_breakdown(enrollment):
    """Student-facing per-component breakdown (name, score, max)."""
    components = get_components(enrollment.offering)
    if not components:
        return []
    comp_ids = [c.id for c in components]
    score_by = {
        cs.component_id: cs.score
        for cs in ComponentScore.objects.filter(component_id__in=comp_ids, enrollment=enrollment)
    }
    return [{"name": c.name, "score": score_by.get(c.id), "max": c.max_score} for c in components]
