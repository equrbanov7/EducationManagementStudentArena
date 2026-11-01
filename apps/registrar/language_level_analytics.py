"""Use canonical finals for the level subset without duplicating its grading rules."""

from . import exam_eligibility, finals, finals_batch, language_level_grading
from .models import Enrollment


def results_for(queryset, *, organization, offering_ids=None):
    """Call only when a caller has identified level courses in its own scope."""
    queryset = queryset.filter(organization=organization)
    if offering_ids is not None:
        queryset = queryset.filter(offering_id__in=offering_ids)
    candidates = queryset.select_related(
        "offering__subject", "offering__period", "offering__organization", "offering__assessment_scheme"
    )
    enrollments = [e for e in candidates if language_level_grading.is_level_name(e.offering.subject.name)]
    if not enrollments:
        return {}
    batch = finals_batch.build(enrollments, organization=organization)
    result = {}
    for enrollment in enrollments:
        row = finals.compute_final_result(enrollment=enrollment, organization=organization, batch=batch)
        row["absence_hours"] = enrollment.absence_hours or 0
        row["lesson_hours"] = exam_eligibility.lesson_hours_for(enrollment.offering, hours_map=batch.hours_map)
        result[str(enrollment.pk)] = row
    return result


def evaluation_override(enrollment, maps):
    if not language_level_grading.is_level_name(enrollment.offering.subject.name):
        return None
    if "language_results" not in maps:
        maps["language_results"] = results_for(
            Enrollment.objects.filter(pk__in=maps["language_enrollment_ids"]), organization=maps["organization"]
        )
    row = dict(maps["language_results"][str(enrollment.pk)])
    row["credit"] = (
        maps["credits"].for_enrollment(enrollment)
        if maps.get("credits") is not None
        else int(enrollment.offering.subject.ects or 0)
    )
    return row
