"""Student read surfaces share query-free level caps and prepared QB counts."""

from . import exam_eligibility, language_level_grading


def entry_cap(offering, scheme):
    return language_level_grading.entry_cap(offering.subject.name, scheme.entry_score_max if scheme else 50)


def eligibility(enrollment, *, absence_count=None, **inputs):
    if not language_level_grading.is_level(enrollment.offering):
        return exam_eligibility.resolve(**inputs)
    return language_level_grading.eligibility(
        enrollment,
        absence_count=absence_count,
        absence_hours=inputs.get("absence_hours"),
        lesson_hours=inputs.get("lesson_hours"),
        exempt=inputs.get("exempt", False),
        resit_done=inputs.get("resit_done", False),
        frozen=inputs.get("frozen", False),
    )


def detail_eligibility(enrollment, prior_row, record, lesson_hours, limit_percent):
    # The summary already used the complete count, including superseded rows.
    # Reuse it instead of re-counting just the visible historical marks.
    if language_level_grading.is_level(enrollment.offering) and prior_row:
        return prior_row["journal"]["eligibility"]
    return eligibility(
        enrollment,
        absence_hours=enrollment.absence_hours,
        lesson_hours=lesson_hours,
        limit_percent=limit_percent,
        exempt=bool(record.national_athlete_exemption),
        frozen=exam_eligibility.is_frozen(enrollment.offering),
    )


def midterm_display_total(offering, standard, entered):
    from decimal import Decimal

    if language_level_grading.is_level(offering) and standard is not None:
        return standard.midterm
    return sum(entered, Decimal("0"))


def absence_usage(result):
    """Comparable numerator/denominator; QB counts must never divide hour totals."""
    from decimal import Decimal

    result = result or {}
    if result.get("limit_unit") == "qb_count":
        values = result.get("absence_count"), result.get("limit_count")
    else:
        values = result.get("absence_hours"), result.get("allowed_hours")
    return tuple(Decimal(str(value or 0)) for value in values)
