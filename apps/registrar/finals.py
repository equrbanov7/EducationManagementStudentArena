"""Yekun qiymət + təkrar imtahan (finals/resit) — services (U3+).

Yekun bal = jurnaldan "giriş balı" (semestr fəaliyyəti, ≈50) + yekun imtahan
balı (≈50). Tələbə kəsilir (qayıb limitini keçib, VƏ YA ümumi bal < keçid həddi,
VƏ YA imtahan < minimum) → ``ResitRecord`` (təkrar imtahan hüququ). Təkrar
imtahan balı daxil ediləndə yekun yenidən hesablanır (resit balı imtahan balını
əvəz edir və qayıb bloku aradan qalxır). Jurnal finalizasiyası (``is_published``)
audit-ə yazılır.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.registrar import gradebook, services
from apps.registrar.models import FinalGrade, ResitReason, ResitRecord, ResitStatus

# 0..100 ümumi bal → hərf + GPA nöqtəsi (AZ Boloniya default).
_LETTER_BANDS = (
    (91, "A", Decimal("4.00")),
    (81, "B", Decimal("3.50")),
    (71, "C", Decimal("3.00")),
    (61, "D", Decimal("2.50")),
    (51, "E", Decimal("2.00")),
    (0, "F", Decimal("0.00")),
)


def score_to_letter(total) -> tuple[str, Decimal]:
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


def _clamp(raw, ceiling) -> Decimal:
    value = _to_decimal(raw)
    top = Decimal(int(ceiling))
    if value < 0:
        return Decimal("0")
    return top if value > top else value


def entry_score_for(enrollment, cap) -> Decimal:
    """Semester entry score — delegates to the canonical component-aware
    computation in :func:`gradebook.entry_score_for` (weighted components when
    defined, otherwise the legacy per-lesson mark sum)."""
    return gradebook.entry_score_for(enrollment, cap)


def exam_score_max(scheme) -> int:
    return max(0, 100 - scheme.entry_score_max)


def compute_final_result(*, enrollment, scheme=None):
    """Full result for one enrollment: entry + exam → total → letter → pass/fail.

    A completed resit supersedes the original exam score and lifts the absence
    bar. Until an exam (or resit) score exists the result is "not graded yet"."""
    scheme = scheme or getattr(enrollment.offering, "assessment_scheme", None)
    if scheme is None:
        scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)

    entry_score = entry_score_for(enrollment, scheme.entry_score_max)
    # Query fresh (avoid a stale cached reverse-O2O after an update in the same request).
    final_grade = FinalGrade.objects.filter(enrollment=enrollment).first()
    exam_score = final_grade.exam_score if (final_grade and final_grade.exam_score is not None) else None
    resit = ResitRecord.objects.filter(enrollment=enrollment).first()
    resit_done = bool(resit and resit.resit_score is not None)
    effective_exam = resit.resit_score if resit_done else exam_score

    limit_percent = gradebook.absence_limit_percent_for(enrollment.offering)
    eligibility = services.get_exam_eligibility(enrollment=enrollment, limit_percent=limit_percent)
    barred = eligibility["barred"] and not resit_done  # a completed resit lifts the bar

    graded = effective_exam is not None
    total = entry_score + (effective_exam or Decimal("0"))
    letter, gpa = score_to_letter(total)
    exam_ok = graded and effective_exam >= scheme.min_final_exam_score
    passed = graded and not barred and total >= scheme.pass_threshold and exam_ok
    # Failed once we can judge it: barred (no exam needed) or graded-but-not-passed.
    failed = barred or (graded and not passed)

    return {
        "entry_score": entry_score,
        "exam_score": exam_score,
        "effective_exam": effective_exam,
        "total": total,
        "letter": letter,
        "gpa": gpa,
        "barred": barred,
        "graded": graded,
        "exam_ok": exam_ok,
        "passed": passed,
        "failed": failed,
        "resit": resit,
        "resit_done": resit_done,
        "pass_threshold": scheme.pass_threshold,
        "min_final_exam_score": scheme.min_final_exam_score,
        "exam_score_max": exam_score_max(scheme),
        "is_published": scheme.is_published,
    }


def _resit_reason(result) -> str:
    if result["barred"]:
        return ResitReason.ABSENCE
    if result["graded"] and not result["exam_ok"]:
        return ResitReason.EXAM
    return ResitReason.TOTAL


@transaction.atomic
def evaluate_resit(*, enrollment, by_user=None):
    """Sync the enrollment's ResitRecord with the current result.

    Creates/keeps an ``eligible`` resit when the student is failing; removes a
    still-unused eligible resit once they pass."""
    result = compute_final_result(enrollment=enrollment)
    existing = enrollment.resit_records.first()

    if result["failed"]:
        reason = _resit_reason(result)
        if existing is None:
            return ResitRecord.objects.create(
                organization=enrollment.organization,
                enrollment=enrollment,
                reason=reason,
                status=ResitStatus.ELIGIBLE,
                decided_by=by_user,
            )
        if existing.status == ResitStatus.ELIGIBLE and existing.reason != reason:
            existing.reason = reason
            existing.save(update_fields=["reason"])
        return existing

    # Passed → an untouched eligibility is no longer needed.
    if existing and existing.status == ResitStatus.ELIGIBLE and existing.resit_score is None:
        existing.delete()
        return None
    return existing


@transaction.atomic
def set_exam_score(*, enrollment, score, by_user=None):
    """Record the final-exam score (teacher/exam centre), then re-evaluate resit.

    Blocked when the offering's scheme is published (finalised)."""
    scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)
    if scheme.is_published:
        return None
    final_grade, _created = FinalGrade.objects.get_or_create(
        organization=enrollment.organization, enrollment=enrollment
    )
    final_grade.exam_score = _clamp(score, exam_score_max(scheme)) if score not in (None, "") else None
    final_grade.entered_by = by_user
    final_grade.save()
    evaluate_resit(enrollment=enrollment, by_user=by_user)
    return final_grade


@transaction.atomic
def set_resit_score(*, enrollment, score, by_user=None):
    """Record a resit exam score → mark the resit completed + recompute."""
    scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)
    if scheme.is_published:
        return None
    resit = enrollment.resit_records.first()
    if resit is None:
        return None  # not eligible for a resit
    resit.resit_score = _clamp(score, exam_score_max(scheme)) if score not in (None, "") else None
    resit.status = ResitStatus.COMPLETED if resit.resit_score is not None else ResitStatus.ELIGIBLE
    resit.decided_by = by_user
    resit.save()
    return resit


def _audit_publish(offering, by_user):
    """Best-effort audit entry for journal finalisation (never breaks publish)."""
    try:
        from django.apps import apps as django_apps

        from core.constants import AuditAction

        AuditLog = django_apps.get_model("audit", "AuditLog")
        AuditLog.objects.create(
            user=by_user if getattr(by_user, "pk", None) else None,
            organization=offering.organization,
            action=AuditAction.UPDATE,
            resource_type="registrar.journal",
            resource_id=str(offering.pk),
            resource_repr=f"{offering.subject.code} jurnalı",
            reason="Jurnal yekunlaşdırıldı (finalised).",
        )
    except Exception:  # noqa: BLE001 — audit must never block the domain action
        pass


@transaction.atomic
def publish_offering(*, offering, by_user=None):
    """Finalise (lock) the offering's journal + write an audit entry."""
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    if not scheme.is_published:
        scheme.is_published = True
        scheme.save(update_fields=["is_published"])
        _audit_publish(offering, by_user)
    return scheme


def get_offering_results(*, offering):
    """Per-student final result rows for the teacher's "Yekun/Nəticə" grid."""
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    enrollments = list(
        offering.enrollments.filter(status=offering.enrollments.model.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    rows = [
        {"enrollment": e, "student": e.student, "result": compute_final_result(enrollment=e, scheme=scheme)}
        for e in enrollments
    ]
    return {"offering": offering, "scheme": scheme, "rows": rows}
