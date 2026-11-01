"""Encrypted-only exact Leyla reverse references, including hidden through tables.

No guard is relaxed. Full rows are hashed in memory; output contains only IDs,
declared relations, safe lifecycle metadata and counts, never grades or text.
"""

from django.db.models import Q

from .. import reviewed_leyla_catalog_spec as spec
from ..reviewed_leyla_catalog_graph import bounded, graph, model
from .reference_metadata import reference_metadata

ALLOWED_NAMED = {
    "registrar.Enrollment",
    "registrar.AssessmentScheme",
    "registrar.AssessmentComponent",
    "registrar.ScheduleSlot",
}


def collect_leyla_references():
    Offering = model("registrar.CourseOffering")
    syllabi = bounded(
        model("syllabus.Syllabus")
        ._base_manager.filter(organization_id=spec.ORG)
        .filter(
            Q(offering_id__in=spec.OFFERINGS)
            | Q(author_id=spec.TEACHER, subject_id__in=spec.SUBJECTS, period_id=spec.PERIOD)
        ),
        cap=40,
        lock=False,
    )
    roots = {
        "registrar.CourseOffering": set(spec.OFFERINGS),
        "workload.TeachingTaskRow": set(spec.ROWS),
        "syllabus.Syllabus": {row["id"] for row in syllabi},
    }
    rows = graph(spec.ORG, roots, lock=False)
    output = reference_metadata(rows, named_offerings=spec.EMPTY, allowed_named=ALLOWED_NAMED)
    cohorts = bounded(
        Offering._base_manager.filter(
            organization_id=spec.ORG,
            subject_id__in=spec.SUBJECTS,
            period_id=spec.PERIOD,
            instructor_id=spec.TEACHER,
        ),
        cap=100,
        lock=False,
    )
    return {
        "leyla_reference_graph": output,
        "leyla_subject_cohorts": [
            {key: row[key] for key in ("id", "subject_id", "period_id", "instructor_id", "group_id", "is_active")}
            for row in cohorts
        ],
    }
