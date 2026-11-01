"""Encrypted-only read-only full two-case graph, including upstream exams and bodies."""

from django.db.models import Q

from .. import reviewed_two_catalog_schema as schema
from .. import reviewed_two_catalog_spec as spec
from ..reviewed_leyla_catalog_graph import bounded, digest, graph, model
from .reference_metadata import reference_metadata


def collect_two_catalog_references():
    query = Q(pk__in=[])
    offerings = {oid for p in spec.CASES for oid in p["offerings"]}
    for pin in spec.CASES:
        query |= (
            Q(offering_id__in=pin["offerings"])
            | Q(author_id=pin["teacher"], subject_id__in=pin["subjects"], period_id__in=[spec.PERIOD])
            | Q(author_id=pin["teacher"], subject_id__in=pin["subjects"], period_id__isnull=True)
        )
    syllabi = bounded(
        model("syllabus.Syllabus")._base_manager.filter(query, organization_id=spec.ORG), cap=40, lock=False
    )
    rows = graph(
        spec.ORG,
        {
            "registrar.CourseOffering": offerings,
            "workload.TeachingTaskRow": {p["row_id"] for p in spec.CASES},
            "syllabus.Syllabus": {r["id"] for r in syllabi},
        },
        lock=False,
    )
    return {
        "two_catalog_reference_graph": reference_metadata(rows),
        "two_catalog_reference_scope": {
            "source_sha256": digest([p["source"] for p in spec.CASES]),
            "schema_sha256": digest(schema.fingerprints()),
            "schema_matches_reviewed": schema.fingerprints() == spec.SCHEMA,
            "eligible_for_apply": False,
            "source_validation_only_no_copy": True,
            "offerings": sorted(offerings),
            "rows": sorted(p["row_id"] for p in spec.CASES),
        },
    }
