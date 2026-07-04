"""Elektron jurnal (electronic journal) — assessment/grade services (U3).

AZ Boloniya modeli: hər ``CourseOffering`` üçün tenant-konfiqurasiya olunan
``AssessmentScheme`` + çəkili komponentlər (seminar / laboratoriya / sərbəst iş /
kollokvium / yekun imtahan; adətən 50 semestr + 50 imtahan = 100). Müəllim hər
tələbə üçün komponent balı (``ComponentScore``) daxil edir; ümumi bal, hərf,
GPA nöqtəsi və keçid/imtahana-buraxılma burada hesablanır — bal xanalarından
başqa heç nə denormallaşdırılmır.

Qayıb (qb) saatı ayrıca ``Enrollment.absence_hours``-dadır; imtahana buraxılma
qaydası ``services.get_exam_eligibility`` ilə (proqramın ``absence_limit_percent``
faizi). Kəsilmə: ümumi bal < ``pass_threshold`` VƏ YA imtahan balı
< ``min_final_exam_score`` VƏ YA qayıb limiti keçilib.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.registrar import services
from apps.registrar.models import (
    AssessmentScheme,
    ComponentKind,
    ComponentScore,
    Enrollment,
    GradeComponent,
    StudentAcademicRecord,
)

# Default AZ Boloniya sxemi: 50 semestr fəaliyyəti + 50 yekun imtahan = 100.
# (name, kind, max_score, is_final_exam) — offering başına tenant redaktə edir.
DEFAULT_COMPONENTS = (
    ("Seminar", ComponentKind.SEMINAR, 10, False),
    ("Laboratoriya", ComponentKind.LAB, 10, False),
    ("Sərbəst iş", ComponentKind.INDEPENDENT, 10, False),
    ("Kollokvium", ComponentKind.COLLOQUIUM, 20, False),
    ("Yekun imtahan", ComponentKind.FINAL_EXAM, 50, True),
)

# 100-ballıq ümumi bal → hərf + GPA nöqtəsi (AZ Boloniya default; sonradan
# tenant-konfiqurasiya oluna bilər). Yüksəkdən aşağıya yoxlanır.
_LETTER_BANDS = (
    (91, "A", Decimal("4.00")),
    (81, "B", Decimal("3.50")),
    (71, "C", Decimal("3.00")),
    (61, "D", Decimal("2.50")),
    (51, "E", Decimal("2.00")),
    (0, "F", Decimal("0.00")),
)

_DEFAULT_ABSENCE_LIMIT = 25


def score_to_letter(total) -> tuple[str, Decimal]:
    """Map a 0..100 total to (letter, gpa_point)."""
    value = Decimal(str(total or 0))
    for threshold, letter, gpa in _LETTER_BANDS:
        if value >= threshold:
            return letter, gpa
    return "F", Decimal("0.00")


def _to_decimal(raw) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _clamp_score(raw, max_score) -> Decimal:
    """Clamp *raw* into [0, max_score] (defensive: never trust client input)."""
    value = _to_decimal(raw)
    ceiling = Decimal(int(max_score))
    if value < 0:
        return Decimal("0")
    if value > ceiling:
        return ceiling
    return value


@transaction.atomic
def ensure_assessment_scheme(*, offering, blueprint=None):
    """Idempotently create the offering's scheme + its default components."""
    scheme, _created = AssessmentScheme.objects.get_or_create(organization=offering.organization, offering=offering)
    if not scheme.components.exists():
        for order, (name, kind, max_score, is_exam) in enumerate(blueprint or DEFAULT_COMPONENTS):
            GradeComponent.objects.create(
                organization=offering.organization,
                scheme=scheme,
                name=name,
                kind=kind,
                max_score=max_score,
                is_final_exam=is_exam,
                order=order,
            )
    return scheme


def absence_limit_for_offering(offering) -> int:
    """Resolve the absence-limit % from the section's program (default 25%)."""
    record = (
        StudentAcademicRecord.objects.filter(organization=offering.organization, group=offering.group)
        .select_related("program")
        .first()
    )
    if record and record.program:
        return record.program.absence_limit_percent
    return _DEFAULT_ABSENCE_LIMIT


def compute_enrollment_result(*, enrollment, scheme, components, scores_by_component, absence_limit_percent):
    """Pure computation for one enrollment (no queries — caller prefetches).

    Returns component rows + total/semester/exam scores, letter, GPA, and the
    pass / absence-barred / exam-threshold flags."""
    total = Decimal("0")
    exam_score = Decimal("0")
    max_total = 0
    rows = []
    for comp in components:
        score = _clamp_score(scores_by_component.get(comp.id, 0), comp.max_score)
        total += score
        max_total += comp.max_score
        if comp.is_final_exam:
            exam_score += score
        rows.append({"component": comp, "score": score})

    semester_total = total - exam_score
    letter, gpa = score_to_letter(total)
    eligibility = services.get_exam_eligibility(enrollment=enrollment, limit_percent=absence_limit_percent)
    barred = eligibility["barred"]
    exam_ok = exam_score >= scheme.min_final_exam_score
    passed = (not barred) and total >= scheme.pass_threshold and exam_ok
    return {
        "rows": rows,
        "total": total,
        "semester_total": semester_total,
        "exam_score": exam_score,
        "max_total": max_total,
        "letter": letter,
        "gpa": gpa,
        "passed": passed,
        "barred": barred,
        "exam_ok": exam_ok,
        "eligibility": eligibility,
        "pass_threshold": scheme.pass_threshold,
        "min_final_exam_score": scheme.min_final_exam_score,
        "is_published": scheme.is_published,
    }


def get_offering_journal(*, offering):
    """Full journal for the teacher grid: scheme + components + per-student rows.

    One prefetch of scores + one absence-limit lookup; no per-student N+1."""
    scheme = ensure_assessment_scheme(offering=offering)
    components = list(scheme.components.all())
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    scores = ComponentScore.objects.filter(enrollment__in=enrollments)
    by_enrollment: dict = {}
    for score in scores:
        by_enrollment.setdefault(score.enrollment_id, {})[score.component_id] = score.score
    absence_limit = absence_limit_for_offering(offering)

    rows = []
    for enrollment in enrollments:
        result = compute_enrollment_result(
            enrollment=enrollment,
            scheme=scheme,
            components=components,
            scores_by_component=by_enrollment.get(enrollment.id, {}),
            absence_limit_percent=absence_limit,
        )
        rows.append({"enrollment": enrollment, "student": enrollment.student, "result": result})

    return {
        "offering": offering,
        "scheme": scheme,
        "components": components,
        "rows": rows,
        "absence_limit_percent": absence_limit,
    }


def get_student_grade_summary(*, record, period, semester_number):
    """Per-subject grade breakdown for the student "Qiymətlərim" view.

    Reuses the student's semester plan (enrollments) and computes each subject's
    component scores + total/letter using its offering scheme (only schemes that
    already exist — no auto-creation on the student path)."""
    plan = services.get_student_semester_plan(record=record, period=period, semester_number=semester_number)
    absence_limit = record.program.absence_limit_percent if record.program else _DEFAULT_ABSENCE_LIMIT
    subjects = []
    for enrollment in plan["enrollments"]:
        offering = enrollment.offering
        scheme = getattr(offering, "assessment_scheme", None)
        result = None
        if scheme is not None:
            components = list(scheme.components.all())
            scores_by_component = {
                s.component_id: s.score for s in ComponentScore.objects.filter(enrollment=enrollment)
            }
            result = compute_enrollment_result(
                enrollment=enrollment,
                scheme=scheme,
                components=components,
                scores_by_component=scores_by_component,
                absence_limit_percent=absence_limit,
            )
        subjects.append(
            {
                "enrollment": enrollment,
                "subject": offering.subject,
                "ects": offering.subject.ects,
                "kind": enrollment.kind,
                "result": result,
            }
        )
    return {"subjects": subjects}


@transaction.atomic
def save_journal_scores(*, offering, cell_values, absence_values=None, by_user=None):
    """Persist teacher-entered scores + absence hours for an offering (bulk).

    ``cell_values``: {(enrollment_id, component_id): raw_score}.
    ``absence_values``: {enrollment_id: raw_hours}. Values are validated against
    the offering's own scheme/enrollments (cross-offering/tenant injection is
    rejected) and clamped. Returns the number of score cells written.

    Blocked when the scheme is published (finalised)."""
    scheme = getattr(offering, "assessment_scheme", None)
    if scheme is None:
        scheme = ensure_assessment_scheme(offering=offering)
    if scheme.is_published:
        return 0

    # Key by ``str(id)`` so UUID objects and form-posted UUID strings both match.
    valid_components = {str(c.id): c for c in scheme.components.all()}
    valid_enrollments = {str(e.id): e for e in offering.enrollments.filter(status=Enrollment.Status.ENROLLED)}

    written = 0
    for (enrollment_id, component_id), raw in (cell_values or {}).items():
        component = valid_components.get(str(component_id))
        enrollment = valid_enrollments.get(str(enrollment_id))
        if component is None or enrollment is None:
            continue  # ignore anything not belonging to this offering
        score = _clamp_score(raw, component.max_score)
        ComponentScore.objects.update_or_create(
            organization=offering.organization,
            enrollment=enrollment,
            component=component,
            defaults={"score": score, "entered_by": by_user},
        )
        written += 1

    for enrollment_id, raw_hours in (absence_values or {}).items():
        enrollment = valid_enrollments.get(str(enrollment_id))
        if enrollment is None:
            continue
        hours = _to_decimal(raw_hours)
        enrollment.absence_hours = max(0, int(hours))
        enrollment.save(update_fields=["absence_hours"])

    return written
