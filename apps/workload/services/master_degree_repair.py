"""Fixed ten-row degree metadata correction, with live program proof and bounded undo.

No sync services or model saves are called: only TeachingTaskRow.degree_level
is updated. Current hours, pay, assignments and every academic record stay put.
"""

import hashlib
import json
import uuid

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction

from core.audit import log_action
from core.constants import AuditAction

from . import master_degree_spec as fixed
from .group_projection import project_group_settings

RESOURCE = "workload.master_degree10"


class RepairError(ValueError):
    pass


def normal(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def digest(value):
    return hashlib.sha256(json.dumps(normal(value), ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def model(label):
    return apps.get_model(label)


def records(query):
    return normal(list(query.order_by("pk").values()))


def _protected(organization, offering_ids):
    """Only hashes of protected content enter the receipt; full row values stay in DB."""
    scopes = {
        "registrar.CourseOffering": {"pk__in": offering_ids},
        "registrar.Enrollment": {"offering_id__in": offering_ids},
        "registrar.Lesson": {"offering_id__in": offering_ids},
        "registrar.LessonMark": {"lesson__offering_id__in": offering_ids},
        "registrar.ScheduleSlot": {"offering_id__in": offering_ids},
        "registrar.JournalShare": {"offering_id__in": offering_ids},
        "registrar.AssessmentScheme": {"offering_id__in": offering_ids},
        "registrar.AssessmentComponent": {"offering_id__in": offering_ids},
        "syllabus.Syllabus": {"offering_id__in": offering_ids},
        "syllabus.SyllabusVersion": {"syllabus__offering_id__in": offering_ids},
    }
    result = {}
    for label, filters in scopes.items():
        rows = records(model(label)._base_manager.filter(organization=organization, **filters))
        result[label] = {"count": len(rows), "sha256": digest(rows)}
    return result


def snapshot(organization):
    rows = list(
        model("workload.TeachingTaskRow")
        ._base_manager.select_for_update()
        .filter(organization=organization, pk__in=fixed.ROWS)
        .order_by("pk")
    )
    if {str(row.pk) for row in rows} != set(fixed.ROWS):
        raise RepairError("fixed_rows_missing")
    task_ids = {row.task_id for row in rows}
    tasks = model("workload.TeachingTask")._base_manager.select_for_update().filter(pk__in=task_ids)
    task_rows = records(tasks)
    if any(
        str(t["organization_id"]) != fixed.ORG
        or t["academic_year"] != fixed.YEAR
        or t["status"] not in ("approved", "distributed", "amended")
        for t in task_rows
    ):
        raise RepairError("task_identity_changed")
    group_ids = {gid for spec in fixed.ROWS.values() for gid in spec["groups"]}
    groups = {
        str(group.pk): group
        for group in model("organizations.OrgUnit")._base_manager.select_for_update().filter(pk__in=group_ids)
    }
    if set(groups) != group_ids:
        raise RepairError("fixed_groups_missing")
    tenant_group_ids = set(
        model("organizations.OrgUnit")
        ._base_manager.filter(organization=organization, unit_type="group")
        .values_list("pk", flat=True)
    )
    keys = []
    for row in rows:
        spec = fixed.ROWS[str(row.pk)]
        if (
            any(str(getattr(row, name)) != spec[name] for name in ("task_id", "subject_id", "period_id"))
            or row.degree_level not in ("bachelor", "master")
            or row.season != "fall"
            or row.row_kind != "teaching"
            or {str(pk) for pk in row.groups.values_list("pk", flat=True)} != set(spec["groups"])
        ):
            raise RepairError("row_identity_changed")
        for gid, expected in spec["groups"].items():
            group = groups[gid]
            if (
                str(group.organization_id) != fixed.ORG
                or str(group.parent_id) != expected["parent_id"]
                or group.name != expected["name"]
                or project_group_settings(group.settings, canonical_group_ids=tenant_group_ids)
                != project_group_settings(expected["settings"], canonical_group_ids=tenant_group_ids)
                or group.settings.get("degree_level") != "master"
                or group.unit_type != "group"
                or not group.is_active
            ):
                raise RepairError("group_master_identity_changed")
        keys.extend((row.subject_id, row.period_id, gid) for gid in spec["groups"])
    sar = (
        model("registrar.StudentAcademicRecord")
        ._base_manager.select_for_update()
        .filter(organization=organization, group_id__in=group_ids, is_active=True)
    )
    sar_rows = records(sar)
    if {r["group_id"] for r in sar_rows} != group_ids or any(not r["program_id"] for r in sar_rows):
        raise RepairError("active_program_proof_missing")
    program_ids = {r["program_id"] for r in sar_rows}
    programs = records(model("registrar.Program")._base_manager.select_for_update().filter(pk__in=program_ids))
    if {p["id"] for p in programs} != program_ids or any(
        p["organization_id"] != fixed.ORG or p["degree_level"] != "master" or not p["is_active"] for p in programs
    ):
        raise RepairError("active_program_not_master")
    assignments = model("workload.TeacherAssignment")._base_manager.select_for_update().filter(row__in=rows)
    assignment_rows = records(assignments)
    if any(a["organization_id"] != fixed.ORG for a in assignment_rows):
        raise RepairError("assignment_tenant_changed")
    offering_ids = set()
    Offering = model("registrar.CourseOffering")
    for subject_id, period_id, gid in keys:
        offering_ids.update(
            Offering._base_manager.filter(
                organization=organization, subject_id=subject_id, period_id=period_id, group_id=gid
            ).values_list("pk", flat=True)
        )
    return {
        "rows": records(model("workload.TeachingTaskRow")._base_manager.filter(pk__in=fixed.ROWS)),
        "groups": records(model("organizations.OrgUnit")._base_manager.filter(pk__in=group_ids)),
        "tasks": task_rows,
        "assignments": assignment_rows,
        "sar_program_proof": {
            "records": len(sar_rows),
            "sha256": digest(sar_rows),
            "programs_sha256": digest(programs),
        },
        "protected": _protected(organization, offering_ids),
        "source_sha256": fixed.SOURCE_SHA256,
        "proof_sha256": fixed.PROOF_SHA256,
        "selection_sha256": digest(fixed.ROWS),
    }


def _without_degrees(state):
    copy = normal(state)
    for row in copy["rows"]:
        row.pop("degree_level")
    return copy


@transaction.atomic
def run(*, organization, user, apply=False, expected_baseline="", undo=""):
    if (
        str(organization.pk) != fixed.ORG
        or not organization.is_active
        or organization.status != "active"
        or not user.is_active
        or not user.is_superuser
    ):
        raise RepairError("active_tenant_superadmin_required")
    if connection.vendor != "postgresql":
        raise RepairError("postgresql_required")
    before = snapshot(organization)
    baseline = digest(before)
    receipts = model("audit.AuditLog")._base_manager.filter(organization=organization, resource_type=RESOURCE)
    receipt = receipts.filter(resource_id=undo).first() if undo else None
    if undo:
        if receipt is None or receipt.new_values.get("operation") != "apply":
            raise RepairError("apply_receipt_missing")
        desired = receipt.old_values
        if receipt.new_values.get("after") != before:
            if desired == before:
                return {
                    "baseline": baseline,
                    "planned": 0,
                    "applied": False,
                    "receipt": undo,
                    "status": "already_undone",
                }
            raise RepairError("undo_state_changed")
        if _without_degrees(desired) != _without_degrees(before):
            raise RepairError("undo_receipt_scope_changed")
        if any(r["degree_level"] != "bachelor" for r in desired["rows"]):
            raise RepairError("undo_receipt_degree_changed")
        target = "bachelor"
    else:
        target = "master"
        if all(row["degree_level"] == target for row in before["rows"]):
            prior = receipts.filter(new_values__operation="apply").order_by("-created_at").first()
            if prior is not None and prior.new_values.get("after") == before:
                return {
                    "baseline": baseline,
                    "planned": 0,
                    "applied": False,
                    "receipt": prior.resource_id,
                    "status": "already_applied",
                }
            raise RepairError("already_master_without_matching_receipt")
        if any(row["degree_level"] != "bachelor" for row in before["rows"]):
            raise RepairError("partial_degree_state_changed")
    result = {"baseline": baseline, "planned": len(fixed.ROWS), "applied": False, "receipt": None, "status": "dry_run"}
    if not apply:
        return result
    if not expected_baseline or expected_baseline != baseline:
        raise RepairError("baseline_changed")
    model("workload.TeachingTaskRow")._base_manager.filter(organization=organization, pk__in=fixed.ROWS).update(
        degree_level=target
    )
    after = snapshot(organization)
    if _without_degrees(before) != _without_degrees(after):
        raise RepairError("preservation_failed")
    batch = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=batch,
        reason=RESOURCE,
        old_values=before,
        new_values={"operation": "undo" if undo else "apply", "undo_of": undo or None, "after": after},
    )
    return {**result, "applied": True, "receipt": batch, "after_baseline": digest(after), "status": "applied"}
