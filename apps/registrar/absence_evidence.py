"""Read-only canonical counter scenarios; no cache writes and no grade values returned."""

from copy import copy

from django.db.models import Count, Q, Sum

from .absence_credit_read import credit_hours_map, effective_hours
from .absence_limit import limit_percent_map_for_students
from .exam_eligibility import exempt_student_ids, frozen_offering_ids, lesson_hours_map
from .exam_eligibility_services import get_exam_eligibility
from .guest_merge import carry_over_map
from .models import Enrollment, ResitRecord


def absence_counter_preview(*, organization_id, added_hours_by_enrollment):
    """Hypothetical raw QB additions, using the same central credit/carry/eligibility policy.

    Existing cached counters are reported, never used as predecessor raw hours.
    The caller must establish the additions' source authority independently.
    """
    if len(added_hours_by_enrollment) > 1000 or any(
        type(value) is not int or value < 0 for value in added_hours_by_enrollment.values()
    ):
        raise ValueError("bounded_nonnegative_counter_scenario_required")
    rows = list(
        Enrollment._base_manager.filter(organization_id=organization_id, pk__in=added_hours_by_enrollment)
        .select_related("offering", "offering__organization")
        .order_by("pk")
    )
    keys = [row.pk for row in rows]
    if len(rows) != len(added_hours_by_enrollment):
        raise ValueError("counter_scenario_enrollment_missing_or_foreign")
    additions = {str(key): value for key, value in added_hours_by_enrollment.items()}
    own = {
        row["pk"]: row
        for row in Enrollment._base_manager.filter(pk__in=keys)
        .annotate(
            raw_hours=Sum("lesson_marks__lesson__hours", filter=Q(lesson_marks__status="absent")),
            raw_count=Count("lesson_marks", filter=Q(lesson_marks__status="absent")),
        )
        .values("pk", "raw_hours", "raw_count")
    }
    credits = credit_hours_map(keys)
    carried = carry_over_map(keys, with_entry_score=False)
    student_ids = {row.student_id for row in rows}
    limits = limit_percent_map_for_students(organization_id=organization_id, student_ids=student_ids)
    exempt = exempt_student_ids(organization_id, student_ids)
    offerings = {row.offering_id for row in rows}
    frozen, denominators = frozen_offering_ids(offerings), lesson_hours_map(offerings)
    resit = set(
        ResitRecord._base_manager.filter(enrollment_id__in=keys, resit_score__isnull=False).values_list(
            "enrollment_id", flat=True
        )
    )
    output = []
    for enrollment in rows:
        raw = int(own[enrollment.pk]["raw_hours"] or 0)
        carry = carried.get(enrollment.pk, {})
        carry_hours = int(carry.get("absence_hours", 0))
        credited = int(credits.get(enrollment.pk, 0))
        before = effective_hours(raw + carry_hours, credited)
        added = additions[str(enrollment.pk)]
        after = effective_hours(raw + carry_hours + added, credited)
        policy = dict(
            limit_percent=limits.get(enrollment.student_id, 25),
            exempt=enrollment.student_id in exempt,
            frozen=enrollment.offering_id in frozen,
            resit_done=enrollment.pk in resit,
            hours_map=denominators,
        )

        def eligibility(hours, *, enrollment=enrollment, policy=policy):
            scenario = copy(enrollment)
            scenario.absence_hours = hours
            result = get_exam_eligibility(enrollment=scenario, **policy)
            # The central resolver also returns attendance scores; evidence needs only policy decisions.
            return {
                key: result[key]
                for key in ("barred", "over_limit", "hours_known", "allowed_hours", "source")
                if key in result
            }

        output.append(
            {
                "enrollment_id": str(enrollment.pk),
                "cached_before": enrollment.absence_hours,
                "own_raw_before": raw,
                "own_raw_count": own[enrollment.pk]["raw_count"],
                "direct_carried_hours": carry_hours,
                "direct_carried_count": carry.get("absence_count", 0),
                "direct_predecessor_ids": sorted(carry.get("enrollment_ids", [])),
                "target_credit": credited,
                "derived_before": before,
                "hypothetical_source_raw_added": added,
                "derived_after": after,
                "source_effect": after - before,
                "cache_reconciliation": before - enrollment.absence_hours,
                "actual_cache_delta_if_applied": after - enrollment.absence_hours,
                "canonical_undo_hours": before,
                "cache_mismatch_alone_is_hold": False,
                "eligibility_before": eligibility(before),
                "eligibility_after": eligibility(after),
                "hypothetical_only_source_authority_not_established": True,
            }
        )
    return output
