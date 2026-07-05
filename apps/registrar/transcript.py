"""Transkript + GPA (U5) — read-only aggregation over the final results.

A transcript groups a student's enrollments by academic period (semester) and,
for each, reuses :func:`finals.compute_final_result` to get the letter grade +
GPA point. The cumulative GPA is **credit-weighted** (Boloniya/ECTS):

    GPA = Σ(gpa_point × credit) / Σ(credit)   over courses with a definite result

A course counts toward the GPA once its result is definite (``passed`` or
``failed`` — a bar counts as a failed attempt); a still-ungraded course is "in
progress" and excluded until it has an exam/resit score. Earned credits are the
credits of *passed* courses only. This layer is additive and pure-read — it adds
no models and never writes.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from apps.registrar import finals
from apps.registrar.models import Enrollment

_TWO_PLACES = Decimal("0.01")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _credit_for(offering) -> int:
    """ECTS credit of the offering's subject (0 if somehow unset)."""
    return int(getattr(offering.subject, "ects", 0) or 0)


def _grade_point(result) -> Decimal:
    return Decimal(str(result.get("gpa") or "0"))


def _build_row(enrollment, organization=None):
    offering = enrollment.offering
    result = finals.compute_final_result(enrollment=enrollment, organization=organization)
    credit = _credit_for(offering)
    # Definite outcome → contributes to GPA; still-open course is excluded.
    in_gpa = bool(result["passed"] or result["failed"])
    return {
        "enrollment": enrollment,
        "offering": offering,
        "subject": offering.subject,
        "period": offering.period,
        "credit": credit,
        "result": result,
        "in_gpa": in_gpa,
        "quality_points": _grade_point(result) * credit if in_gpa else Decimal("0"),
    }


def _summarize(rows) -> dict:
    """Credit-weighted GPA + credit tallies for a list of transcript rows."""
    gpa_credits = sum((r["credit"] for r in rows if r["in_gpa"]), 0)
    quality_points = sum((r["quality_points"] for r in rows if r["in_gpa"]), Decimal("0"))
    earned_credits = sum((r["credit"] for r in rows if r["result"]["passed"]), 0)
    gpa = _round2(quality_points / gpa_credits) if gpa_credits else Decimal("0.00")
    return {
        "gpa": gpa,
        "quality_points": _round2(quality_points),
        "credits_gpa": gpa_credits,
        "credits_earned": earned_credits,
    }


def build_student_transcript(*, student, organization, program=None):
    """Full transcript for one student: chronological semesters + cumulative GPA.

    Only the requesting student's own enrollments are read; tenant isolation is
    inherited from the active request (RLS). Returns ``has_record=False`` when the
    student has no enrollments yet so the cabinet renders a friendly placeholder.
    """
    enrollments = list(
        Enrollment.objects.filter(organization=organization, student=student)
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("offering", "offering__subject", "offering__period", "offering__assessment_scheme")
        .order_by("offering__period__start_date", "offering__subject__code")
    )
    if not enrollments:
        return {
            "has_record": False,
            "student": student,
            "semesters": [],
            "cumulative_gpa": Decimal("0.00"),
            "total_credits_earned": 0,
            "total_credits_gpa": 0,
            "quality_points": Decimal("0.00"),
            "ects_total": int(getattr(program, "ects_total", 0) or 0) if program else 0,
        }

    rows = [_build_row(e, organization) for e in enrollments]

    # Group into semesters, preserving the chronological (period) order.
    semesters: list[dict] = []
    by_period: dict = {}
    for row in rows:
        period = row["period"]
        bucket = by_period.get(period.id)
        if bucket is None:
            bucket = {"period": period, "rows": []}
            by_period[period.id] = bucket
            semesters.append(bucket)
        bucket["rows"].append(row)

    for bucket in semesters:
        bucket.update(_summarize(bucket["rows"]))

    overall = _summarize(rows)
    return {
        "has_record": True,
        "student": student,
        "semesters": semesters,
        "cumulative_gpa": overall["gpa"],
        "quality_points": overall["quality_points"],
        "total_credits_gpa": overall["credits_gpa"],
        "total_credits_earned": overall["credits_earned"],
        "ects_total": int(getattr(program, "ects_total", 0) or 0) if program else 0,
    }
