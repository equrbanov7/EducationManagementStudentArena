"""Read-only native journal comparison; never ensure components or write scores."""

from . import exam_bridge, finals, gradebook, interim_assessment, language_level_grading
from .exam_score_precedence import has_later_authoritative_entry
from .midterm_bridge import _overridden
from .models import AssessmentComponent, AssessmentScheme, ComponentScore, Enrollment, FinalGrade, ResitRecord


def _comparison(actual, expected):
    if actual is None:
        return "missing"
    if actual == expected:
        return "equal"
    return "current_above" if actual > expected else "current_below"


def inspect_reaudit_exam_target(*, attempt, identity, percent, period_id):
    """Compare one already-selected official attempt, without returning any grade or student identifier."""
    kind, enrollment_id = identity
    enrollment = Enrollment.objects.select_related(
        "offering__subject", "offering__period", "offering__organization"
    ).get(pk=enrollment_id, organization_id=attempt.exam.organization_id)
    result = {"enrollment_id": str(enrollment.pk), "offering_id": str(enrollment.offering_id), "target_kind": kind}
    if str(enrollment.offering.period_id) != str(period_id):
        return {**result, "status": "outside_current_period"}
    result["active_enrolled"] = enrollment.status == "enrolled" and enrollment.offering.is_active
    scheme = AssessmentScheme.objects.filter(
        offering=enrollment.offering, organization_id=enrollment.organization_id
    ).first()
    if scheme is None:
        return {**result, "status": "unknown_missing_scheme"}
    if attempt.exam.exam_type_extended == "midterm":
        if not interim_assessment.is_midterm_offering(enrollment.offering):
            return {**result, "status": "not_midterm_period"}
        components = list(
            AssessmentComponent.objects.filter(
                offering=enrollment.offering,
                organization_id=enrollment.organization_id,
                name__iexact=interim_assessment.MIDTERM_COMPONENT_NAME,
            )[:2]
        )
        if len(components) != 1 or components[0].kind != "kollokvium":
            return {**result, "status": "unknown_midterm_component"}
        component = components[0]
        row = ComponentScore.objects.filter(component=component, enrollment=enrollment).first()
        if _overridden(component, enrollment, attempt.finished_at, row):
            return {**result, "status": "protected_documentary_result"}
        if gradebook.journal_is_locked(enrollment.offering):
            return {**result, "status": "protected_closed_journal"}
        cap = (
            language_level_grading.MIDTERM_MAX
            if language_level_grading.is_level(enrollment.offering)
            else component.max_score
        )
        actual = row.score if row else None
        source = row.exam_source if row and isinstance(row.exam_source, dict) else {}
        source_id = source.get("attempt_id")
        result["source_attempt_matches"] = str(source_id) == str(attempt.pk) if source_id is not None else None
        # The language writer deliberately preserves un-attributed old-scale scores.
        if language_level_grading.is_level(enrollment.offering) and actual is not None and actual > cap and not source:
            return {**result, "status": "protected_legacy_language_scale"}
    else:
        cap = finals.exam_score_max(scheme)
        if kind == "retake":
            row = ResitRecord.objects.filter(enrollment=enrollment).first()
            if row and row.status != "completed":
                return {
                    **result,
                    "status": "unknown_retake_not_completed",
                    "stored_score_present": row.resit_score is not None,
                }
            actual = row.resit_score if row else None
        else:
            if has_later_authoritative_entry(enrollment, attempt):
                return {**result, "status": "protected_documentary_result"}
            row = FinalGrade.objects.filter(enrollment=enrollment).first()
            actual = row.exam_score if row else None
    expected = exam_bridge.scale_percent(percent, cap)
    return {
        **result,
        "status": "compared",
        "comparison": _comparison(actual, expected),
        "stored_zero": actual == 0,
        "expected_zero": expected == 0,
        "stored_out_of_bounds": actual is not None and (actual < 0 or actual > cap),
    }
