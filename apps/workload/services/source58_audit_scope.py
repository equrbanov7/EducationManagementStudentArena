"""Fixed Source58 locator mirrors native bounded academic/credit closure."""

from django.db.models import Q

from .scoped_snapshot import source58_evidence as source
from .scoped_snapshot import source58_evidence_spec as fixed
from .scoped_snapshot.source58_evidence_rows import MAX_DEPTH, EvidenceLimit, Rows, model


def reference_ids():
    reader = Rows()
    offerings = source._family(reader)
    family_ids = {row["id"] for row in offerings}
    if set(fixed.OFFERINGS) - family_ids:
        raise EvidenceLimit("source58_fixed_courses_missing")
    initial = reader.read(model("registrar.Enrollment")._base_manager.filter(offering_id__in=family_ids), cap=1000)
    target_ids = {case["enrollment_id"] for case in fixed.CASES.values()}
    enrollments = source._closure(
        reader, "registrar.Enrollment", {row["id"] for row in initial} | target_ids, "superseded_by_id"
    )
    if target_ids - enrollments.keys():
        raise EvidenceLimit("source58_fixed_enrollments_missing")
    credits = {}
    for _depth in range(MAX_DEPTH):
        current = reader.read(
            model("registrar.AbsenceCredit")._base_manager.filter(enrollment_id__in=enrollments), cap=1000
        )
        credits = source._closure(reader, "registrar.AbsenceCredit", {row["id"] for row in current}, "reverses_id")
        extra_enrollments = {row["enrollment_id"] for row in credits.values()} - enrollments.keys()
        if not extra_enrollments:
            break
        enrollments = source._closure(
            reader, "registrar.Enrollment", set(enrollments) | extra_enrollments, "superseded_by_id"
        )
    else:
        raise EvidenceLimit("source58_credit_enrollment_closure_depth")
    all_offering_ids = family_ids | {row["offering_id"] for row in enrollments.values()}
    offerings = reader.read(model("registrar.CourseOffering")._base_manager.filter(pk__in=all_offering_ids), cap=500)
    lessons = reader.read(model("registrar.Lesson")._base_manager.filter(offering_id__in=all_offering_ids), cap=5000)
    extra = source._extra_evidence(reader, enrollments, {row["id"] for row in lessons})
    allocations = reader.read(
        model("workload.TeachingTaskRow")
        ._base_manager.filter(organization_id=fixed.ORG)
        .filter(
            Q(pk__in=[])
            | Q(
                subject_id__in={row["subject_id"] for row in offerings},
                period_id__in={row["period_id"] for row in offerings},
            )
        ),
        cap=1000,
    )
    roots = {
        "registrar.CourseOffering": all_offering_ids,
        "registrar.Enrollment": set(enrollments),
        "registrar.AbsenceCredit": set(credits),
        "workload.TeachingTaskRow": {row["id"] for row in allocations},
    }
    roots.update({label: {row["id"] for row in rows} for label, rows in extra.items()})
    academic = reader.graph(roots)
    return {
        str(row["id"])
        for label, rows in academic.items()
        for row in rows
        if label
        in {
            "registrar.CourseOffering",
            "registrar.Enrollment",
            "registrar.Lesson",
            "registrar.LessonMark",
            "registrar.AbsenceCredit",
            "workload.TeachingTaskRow",
        }
    }
