"""Encrypted-only exact Leyla reverse references, including hidden through tables.

No guard is relaxed. Full rows are hashed in memory; output contains only IDs,
declared relations, safe lifecycle metadata and counts, never grades or text.
"""

from django.db.models import Q

from .. import reviewed_leyla_catalog_spec as spec
from ..reviewed_leyla_catalog_graph import bounded, digest, graph, model

ALLOWED_NAMED = {
    "registrar.Enrollment",
    "registrar.AssessmentScheme",
    "registrar.AssessmentComponent",
    "registrar.ScheduleSlot",
}
LIFECYCLE = {"is_active", "status", "state", "version_number"}


def _relations(cls):
    return [
        {
            "field": field.attname,
            "target": field.related_model._meta.label,
            "target_field": field.target_field.attname,
            "nullable": field.null,
        }
        for field in cls._meta.concrete_fields
        if field.is_relation and field.related_model is not None
    ]


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
    named_enrollments = {row["id"] for row in rows.get("registrar.Enrollment", []) if row["offering_id"] in spec.EMPTY}
    output = []
    for label, values in rows.items():
        cls = model(label)
        relations = _relations(cls)
        offering_fields = [r["field"] for r in relations if r["target"] == Offering._meta.label]
        identities = []
        for row in values:
            identity = {
                "pk": row[cls._meta.pk.attname],
                "fk": {r["field"]: row[r["field"]] for r in relations},
                "lifecycle": {key: row[key] for key in LIFECYCLE if key in row},
                "row_sha256": digest(row),
                "named_reference_hold": label not in ALLOWED_NAMED
                and any(row.get(field) in spec.EMPTY for field in offering_fields),
                "named_enrollment_content_hold": row.get("enrollment_id") in named_enrollments,
            }
            identities.append(identity)
        reverse = [
            {
                "child": rel.related_model._meta.label,
                "field": rel.field.name if rel.many_to_many else rel.field.attname,
                "hidden": rel.hidden,
                "many_to_many": rel.many_to_many,
            }
            for rel in cls._meta.get_fields(include_hidden=True)
            if rel.auto_created and not rel.concrete and rel.related_model is not None
        ]
        output.append(
            {
                "model": label,
                "count": len(values),
                "sha256": digest(values),
                "relations": relations,
                "reverse_relations": reverse,
                "rows": identities,
            }
        )
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
