"""Fixed209/336T1 source535-vs536 discovery only; never rebinds academic data."""

from uuid import UUID

from django.db.models import Q

from ..reviewed_leyla_catalog_graph import bounded, digest, graph, model
from .data import ORG
from .reference_metadata import reference_metadata

TEACHER = 7776
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
ROW = "d835f4a8-6b30-4776-b998-6480960cadd1"
OFFERING = "caad2073-173d-48e1-89fd-3c4405c4b87d"
SUBJECTS = ("a33a790f-2f40-4645-a666-cea5f6fb82f9", "4befd3c3-40f0-4276-b90d-d450bd5effc1")
GROUPS = ("10e6920c-a69d-4117-acc9-8b4c8b033962", "0967e0e5-9911-432e-a26e-bc88a76772af")
SIBLING = "f1882bc7-c5d0-43ac-ba3f-7ce8c30f4e76"
# Namespace is part of identity: the same numeric PK in another entity is irrelevant.
MAPS = (
    ("worker", "209", "auth.user", str(TEACHER)),
    ("worker_materialisation", "209", "auth.user", str(TEACHER)),
    ("group_unit", "934", "organizations.orgunit", GROUPS[0]),
    ("group_unit", "935", "organizations.orgunit", GROUPS[1]),
    ("lesson_subject", "535", "registrar.subject", SUBJECTS[0]),
    ("lesson_subject", "536", "registrar.subject", SUBJECTS[1]),
    ("course_offering", "15047", "registrar.courseoffering", OFFERING),
    ("course_offering", "15051", "registrar.courseoffering", SIBLING),
    # Source70 SHA1a1b24629be432e4e81ca19ebfa357353cd2856d031aa83ea2dd7773b5a0ee88:
    # import identities are exact case-sensitive uniqid:group, never journal numbers.
    ("course_offering", "rWlLLOIQn0:934", "registrar.courseoffering", OFFERING),
    ("course_offering", "ujYj5scjwh:935", "registrar.courseoffering", SIBLING),
    ("syllabus_document", "8668", "syllabus.syllabus", None),
    ("syllabus_document", "6117", "syllabus.syllabus", None),
)


def _uuid(value):
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _target_present(row, label, target):
    if row["target_model_label"] != label or (target is not None and row["target_pk"] != target):
        return False
    if target is None and _uuid(row["target_pk"]) is None:
        return False
    cls = model(label)
    query = cls._base_manager.filter(pk=row["target_pk"])
    if any(field.name == "organization" for field in cls._meta.concrete_fields):
        query = query.filter(organization_id=ORG)
    return query.exists()


def _typed_maps():
    query = Q(pk__in=[])
    for entity, legacy, _, _ in MAPS:
        query |= Q(entity_type=entity, legacy_pk=legacy)
    rows = bounded(
        model("legacy_import.LegacyEntityMap")._base_manager.filter(
            query, organization_id=ORG, source_system="myedu_mariadb"
        ),
        cap=30,
        lock=False,
    )
    output = []
    for entity, legacy, label, target in MAPS:
        matches = [r for r in rows if r["entity_type"] == entity and r["legacy_pk"] == legacy]
        present = [_target_present(row, label, target) for row in matches]
        output.append(
            {
                "entity_type": entity,
                "legacy_pk": legacy,
                "expected_model": label,
                "expected_target": target,
                "required_for_coverage": not (entity == "course_offering" and legacy in {"15047", "15051"}),
                "numeric_journal_id_not_import_identity": entity == "course_offering" and legacy in {"15047", "15051"},
                "count": len(matches),
                "absent": not matches,
                "target_present": all(present) if matches else None,
                "conflict": any(
                    r["target_model_label"] != label
                    or (target is not None and r["target_pk"] != target)
                    or (target is None and _uuid(r["target_pk"]) is None)
                    or r["state"] != "migrated"
                    for r in matches
                )
                or any(not value for value in present),
                "sha256": digest(matches),
                "rows": [
                    {
                        key: row[key]
                        for key in (
                            "id",
                            "source_system",
                            "entity_type",
                            "legacy_pk",
                            "target_model_label",
                            "target_pk",
                            "state",
                            "source_row_hash",
                            "transform_version",
                            "created_run_id",
                            "reconciliation_status",
                        )
                    }
                    for row in matches
                ],
            }
        )
    return output, rows


def collect_ilahe_references():
    Offering = model("registrar.CourseOffering")
    cohorts = bounded(
        Offering._base_manager.filter(organization_id=ORG).filter(
            Q(pk__in=(OFFERING, SIBLING)) | Q(subject_id__in=SUBJECTS, period_id=PERIOD)
        ),
        cap=100,
        lock=False,
    )
    offering_ids = {row["id"] for row in cohorts}
    tasks = bounded(
        model("workload.TeachingTaskRow")
        ._base_manager.filter(organization_id=ORG)
        .filter(Q(pk=ROW) | Q(subject_id__in=SUBJECTS, period_id=PERIOD)),
        cap=100,
        lock=False,
    )
    typed, maps = _typed_maps()
    mapped_syllabi = {
        row["target_pk"]
        for row in maps
        if row["entity_type"] == "syllabus_document"
        and row["target_model_label"] == "syllabus.syllabus"
        and row["state"] == "migrated"
    }
    shares = bounded(
        model("syllabus.SyllabusShare")._base_manager.filter(organization_id=ORG, offering_id__in=offering_ids),
        cap=100,
        lock=False,
    )
    # Invalid mapped targets remain visible as conflicts without invalid UUID queries.
    valid = {pk for value in mapped_syllabi if (pk := _uuid(value)) is not None}
    syllabi = bounded(
        model("syllabus.Syllabus")
        ._base_manager.filter(organization_id=ORG)
        .filter(
            Q(pk__in=valid | {row["syllabus_id"] for row in shares})
            | Q(offering_id__in=offering_ids)
            | Q(author_id=TEACHER, subject_id__in=SUBJECTS, period_id__in=(PERIOD,))
            | Q(author_id=TEACHER, subject_id__in=SUBJECTS, period_id__isnull=True)
        ),
        cap=100,
        lock=False,
    )
    roots = {
        "registrar.CourseOffering": offering_ids,
        "workload.TeachingTaskRow": {row["id"] for row in tasks},
        "syllabus.Syllabus": {row["id"] for row in syllabi},
    }
    return {
        "ilahe_reference_graph": reference_metadata(graph(ORG, roots, lock=False)),
        "ilahe_subject_cohorts": [
            {
                **{
                    key: row[key]
                    for key in (
                        "id",
                        "subject_id",
                        "period_id",
                        "instructor_id",
                        "group_id",
                        "is_active",
                        "lesson_hours",
                    )
                },
                "fixed_primary": row["id"] == OFFERING,
                "expected_sibling": row["id"] == SIBLING,
                "outside_expected_groups": row["group_id"] not in GROUPS,
                "different_instructor": row["instructor_id"] != TEACHER,
            }
            for row in cohorts
        ],
        "ilahe_typed_maps": typed,
    }
