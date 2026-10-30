"""Only two newly reviewed catalogue subjects lacking a legacy subject map."""

from django.apps import apps

from .reviewed_content_contract import ContentError
from .reviewed_content_spec import ORG

MANIFEST = "54e8c2c5bddf7f9841b4610251a7031990293c9656b9827e5f5372c3020b5d61"
OFFICIAL_WORKBOOK = "3c87f7f625b57360522c0f3eb31a29dc464dea52edba0e0dc8b9137c5019f32f"
TASK = "0bcee890-62ff-46cf-bd05-f589218dbe67"
CHAIR = "9375b388-7945-464b-949c-aa5134e4eca4"
BRIDGES = {
    "2bcf2c6e-817e-4ac0-a54b-9c78820f60b2": (2671, 22, "QKU-SRC-5ABD462502C4", "Maliyyə auditi"),
    "1206a0f5-1483-4b67-b820-9f976f335231": (
        2669,
        51,
        "QKU-SRC-B3A1847A50A6",
        "Beynəlxalq mühasibat uçotunun əsasları",
    ),
}


def reviewed_catalog_bridge(offering, spec, original_maps):
    """No fuzzy bridge, writes, or remapping; reject any new conflicting ledger."""
    expected = BRIDGES.get(str(offering.pk))
    if expected is None:
        return False
    legacy, line, code, name = expected
    subject = offering.subject
    if (
        original_maps  # Source2671/2669 had no legacy target in the reviewed source snapshot.
        or spec["legacy_subject_id"] != legacy
        or spec["selection_id"] != line
        or (subject.code, subject.name, subject.ects, subject.kind, str(subject.chair_unit_id))
        != (code, name, 6, "core", CHAIR)
        or not subject.is_active
        or offering.lesson_hours != 45
    ):
        raise ContentError("reviewed_catalog_bridge_identity_changed")
    logs = apps.get_model("audit.AuditLog").objects.filter(
        organization_id=ORG,
        resource_type="workload.reviewed_source_batch",
        reason="workload.reviewed_source_batch",
        new_values__kind="apply",
        new_values__manifest_sha256=MANIFEST,
    )
    receipts = [
        log
        for log in logs
        if str(subject.pk) in log.new_values.get("details", {}).get("created_subject_ids", [])
        and str(offering.pk) in log.new_values.get("details", {}).get("created_offering_ids", [])
    ]
    if len(receipts) != 1:
        raise ContentError("reviewed_catalog_original_receipt_required")
    if (
        apps.get_model("audit.AuditLog")
        .objects.filter(
            organization_id=ORG,
            resource_type="workload.reviewed_source_batch",
            resource_id=receipts[0].resource_id,
            new_values__kind="undo",
        )
        .exists()
    ):
        raise ContentError("reviewed_catalog_receipt_undone")
    rows = (
        apps.get_model("workload.TeachingTaskRow")
        .objects.filter(
            organization_id=ORG,
            task_id=TASK,
            subject_id=subject.pk,
            period_id=offering.period_id,
            groups__pk=offering.group_id,
        )
        .distinct()
    )
    if rows.count() != 1:
        raise ContentError("reviewed_catalog_workload_missing_or_ambiguous")
    row = rows.get()
    if (
        set(map(str, row.groups.values_list("pk", flat=True))) != {str(offering.group_id)}
        or (row.lecture_plan, row.lecture_total, row.seminar_plan, row.seminar_total, row.lab_plan, row.lab_total)
        != (30, 30, 15, 15, 0, 0)
        or sorted(
            row.assignments.filter(activity__in=("lecture", "seminar", "lab")).values_list(
                "teacher_id", "activity", "hours"
            )
        )
        != [(spec["teacher_id"], "lecture", 30), (spec["teacher_id"], "seminar", 15)]
    ):
        raise ContentError("reviewed_catalog_source_workload_changed")
    return True
