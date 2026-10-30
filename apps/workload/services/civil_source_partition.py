"""Repartition two legacy mixed-owner rows without changing five journals.

Only the fixed official source rows 36/60/74 are accepted. All writes use the
normal workload services and run inside an all-or-nothing dry-run transaction.
"""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .assignments import assign_teacher, unassign
from .offering_sync import sync_task_offerings
from .people import is_assignable_teacher
from .repair_fingerprints import academic_database_fingerprint
from .reviewed_batch_manifest import ORG, YEAR
from .row_edit import delete_row_amended, save_row_amended
from .sbio235_state import RepairError, digest, model, records
from .scoping import ensure_can_distribute, ensure_can_manage, resolve_actor

FORMAT = "reviewed-civil-partition/1"
RESOURCE = "workload.civil_source_partition"
SOURCE_SHA = "5e5bb05a993956c0519e0b5fc0e72548391de44b110f8460cb2ed7ca9493314d"
TASK = "f9e57565-648f-4365-b533-db04007796d2"
SUBJECT = "6d3ff61d-d2f8-4757-a1e6-28a09009b86f"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
OLD_ROWS = ("48ee4b89-eb3c-4ad5-98a6-ef9dc2df6713", "cba8016e-07ad-437f-b7fe-68b5c521bf0f")
TARGETS = {
    74: {
        "teacher": 8391,
        "groups": ["82ef19c5-ab25-4de6-a73d-4aba9006ce92", "bdcfd65b-92f3-4fbc-9802-c4175fcbf88a"],
        "seminar": 30,
        "sections": 2,
        "row": OLD_ROWS[0],
    },
    60: {
        "teacher": 7723,
        "groups": ["c82fd28e-6d72-43b7-b420-b1659df422af", "0f1d2f23-0ddb-4dbe-8064-c48d85b1c546"],
        "seminar": 15,
        "sections": 1,
        "row": OLD_ROWS[1],
    },
    36: {
        "teacher": 7760,
        "groups": ["e82cc58c-3c95-4502-8065-e283c86da101"],
        "seminar": 15,
        "sections": 1,
        "row": None,
    },
}
JOURNALS = {
    "f7465957-0dba-49f4-8c0a-71abf90009f8": (8391, "82ef19c5-ab25-4de6-a73d-4aba9006ce92"),
    "f800ea37-a2cb-4efa-9760-be8c78d92c00": (8391, "bdcfd65b-92f3-4fbc-9802-c4175fcbf88a"),
    "a269d62c-6107-4ef7-9adb-3f53029d447c": (7723, "c82fd28e-6d72-43b7-b420-b1659df422af"),
    "e2020e08-4fc3-413c-9622-7b0235e914da": (7723, "0f1d2f23-0ddb-4dbe-8064-c48d85b1c546"),
    "38714add-2f55-4ee0-82a9-8293e29458a1": (7760, "e82cc58c-3c95-4502-8065-e283c86da101"),
}


def _validate_manifest(manifest, lines):
    if manifest.get("format") != FORMAT or manifest.get("organization_id") != ORG or sorted(lines) != [36, 60, 74]:
        raise RepairError("civil_partition_fixed_selection_required")
    sources = {e["line"]: e for e in manifest["sources"]}
    if set(sources) != set(TARGETS):
        raise RepairError("civil_partition_source_rows_required")
    for line, target in TARGETS.items():
        source = sources[line]
        if (
            source["sha256"] != SOURCE_SHA
            or source["teacher_id"] != target["teacher"]
            or source["hours"] != {"lecture": 15, "seminar": target["seminar"], "lab": 0}
            or sorted(source["group_ids"]) != sorted(target["groups"])
        ):
            raise RepairError("civil_partition_source_identity_changed")


def _rows():
    base = model("workload.TeachingTaskRow").objects.filter(
        organization_id=ORG, task_id=TASK, subject_id=SUBJECT, period_id=PERIOD
    )
    return base.filter(
        pk__in=base.filter(groups__id__in=[g for target in TARGETS.values() for g in target["groups"]]).values("pk")
    )


def _state():
    rows = list(_rows().order_by("pk"))
    return {
        "rows": records(_rows()),
        "groups": {str(r.pk): sorted(str(g.pk) for g in r.groups.all()) for r in rows},
        "assignments": records(model("workload.TeacherAssignment").objects.filter(row__in=rows)),
        "journals": records(model("registrar.CourseOffering").objects.filter(organization_id=ORG, pk__in=JOURNALS)),
    }


def _validate_current(manifest):
    rows = {str(r.pk): r for r in _rows().select_for_update()}
    if set(rows) != set(OLD_ROWS):
        raise RepairError("civil_partition_row_set_changed")
    expected_groups = {
        OLD_ROWS[0]: [TARGETS[74]["groups"][0], TARGETS[60]["groups"][0]],
        OLD_ROWS[1]: [TARGETS[74]["groups"][1], TARGETS[60]["groups"][1], TARGETS[36]["groups"][0]],
    }
    if {k: sorted(v) for k, v in manifest["old_row_groups"].items()} != {
        k: sorted(v) for k, v in expected_groups.items()
    }:
        raise RepairError("civil_partition_old_layout_changed")
    for rid, row in rows.items():
        if sorted(str(g.pk) for g in row.groups.all()) != sorted(expected_groups[rid]):
            raise RepairError("civil_partition_original_groups_changed")
        assignments = list(row.assignments.all())
        if (
            {a.activity for a in assignments} != {"lecture", "seminar"}
            or len(assignments) != 2
            or any(a.teacher_id is not None for a in assignments)
        ):
            raise RepairError("civil_partition_existing_assignment_changed")
    offerings = list(
        model("registrar.CourseOffering").objects.select_for_update().filter(organization_id=ORG, pk__in=JOURNALS)
    )
    if len(offerings) != len(JOURNALS):
        raise RepairError("civil_partition_journal_missing")
    for o in offerings:
        if (
            (o.instructor_id, str(o.group_id)) != JOURNALS[str(o.pk)]
            or str(o.subject_id) != SUBJECT
            or str(o.period_id) != PERIOD
            or not o.is_active
            or o.lesson_hours != 30
        ):
            raise RepairError("civil_partition_journal_identity_changed")
    return rows, offerings


def _protected(offerings, row_ids):
    return {
        "academic": academic_database_fingerprint(organization_id=ORG, offerings=offerings, exclude=("journal_share",)),
        "outside_rows": digest(
            records(model("workload.TeachingTaskRow").objects.filter(organization_id=ORG).exclude(pk__in=row_ids))
        ),
        "outside_assignments": digest(
            records(model("workload.TeacherAssignment").objects.filter(organization_id=ORG).exclude(row_id__in=row_ids))
        ),
        "manual_shares": digest(
            records(model("registrar.JournalShare").objects.filter(organization_id=ORG).exclude(source="workload"))
        ),
    }


def _write(task, actor, rows, *, batch):
    changed = []
    amend = {
        "reason": "correction",
        "note": f"Rəsmi source36/60/74: qarışmış qruplar müəllimə görə ayrılır [batch:{batch}]",
    }
    for line, target in TARGETS.items():
        row = rows.get(target["row"])
        teacher = model("auth.User").objects.get(pk=target["teacher"], is_active=True)
        if not is_assignable_teacher(task.organization, task.chair, teacher):
            raise RepairError("civil_partition_teacher_scope_changed")
        if row:
            row = save_row_amended(task=task, row=row, actor=actor, data={}, amend=amend, sync_offerings=False)
            for old in row.assignments.all():
                hours = 15 if old.activity == "lecture" else target["seminar"]
                assign_teacher(
                    row=row,
                    actor=actor,
                    assignment=old,
                    activity=old.activity,
                    teacher_id=teacher.pk,
                    hours=min(hours, old.hours),
                    is_hourly_paid=(line == 74),
                    groups_note=old.groups_note,
                    note=old.note,
                    sync_offerings=False,
                )
        data = {
            "subject_id": SUBJECT,
            "period_id": PERIOD,
            "season": "fall",
            "row_kind": "teaching",
            "degree_level": "bachelor",
            "education_form": "eyani",
            "group_ids": target["groups"],
            "groups_text": "\n".join(
                model("organizations.OrgUnit").objects.get(pk=g, organization_id=ORG).name for g in target["groups"]
            ),
            "subject_text": "Mülki müdafiə",
            "lecture_plan": 15,
            "lecture_total": 15,
            "seminar_plan": 15,
            "seminar_total": target["seminar"],
            "lab_plan": 0,
            "lab_total": 0,
            "union_count": 1,
            "subgroup_count": target["sections"],
            "credits": "3",
            "credits_value": 3,
        }
        row = save_row_amended(task=task, row=row, actor=actor, data=data, amend=amend, sync_offerings=False)
        for activity, hours in (("lecture", 15), ("seminar", target["seminar"])):
            old = row.assignments.filter(activity=activity).first()
            assign_teacher(
                row=row,
                actor=actor,
                assignment=old,
                activity=activity,
                teacher_id=teacher.pk,
                hours=hours,
                is_hourly_paid=(line == 74),
                groups_note=old.groups_note if old else "",
                note=old.note if old else "Rəsmi mənbə sətri " + str(line),
                sync_offerings=False,
            )
        changed.append(row)
    report = sync_task_offerings(task, actor=actor, rows=changed, create=False)
    if any(
        report.get(k)
        for k in (
            "created",
            "blocked",
            "inactive_skipped",
            "elective_pending",
            "elective_choice_failed",
            "elective_choice_conflict",
            "period_locked",
        )
    ):
        raise RepairError("civil_partition_sync_rejected")
    return changed


@transaction.atomic
def run(*, manifest, manifest_sha, lines, organization, user, expected_baseline="", apply=False, undo=""):
    _validate_manifest(manifest, lines)
    if apply and not re.fullmatch(r"[a-f0-9]{64}", expected_baseline):
        raise RepairError("fresh_expected_baseline_required")
    actor = resolve_actor(user, organization)
    task = (
        model("workload.TeachingTask")
        .objects.select_for_update()
        .get(pk=TASK, organization=organization, academic_year=YEAR)
    )
    ensure_can_manage(actor, task.chair_id)
    ensure_can_distribute(actor, task.chair_id)
    before = _state()
    baseline = digest(before)
    if undo:
        return _undo(
            manifest_sha,
            undo,
            actor=actor,
            task=task,
            user=user,
            organization=organization,
            before=before,
            baseline=baseline,
            expected_baseline=expected_baseline,
            apply=apply,
        )
    receipt = (
        model("audit.AuditLog")
        .objects.filter(organization=organization, resource_type=RESOURCE)
        .order_by("-created_at", "-pk")
        .first()
    )
    if (
        receipt
        and receipt.new_values.get("kind", "apply") == "apply"
        and receipt.new_values.get("manifest_sha256") == manifest_sha
        and receipt.new_values.get("after_baseline") == baseline
    ):
        return {"baseline": baseline, "batch": receipt.resource_id, "already_done": 1}
    if expected_baseline and baseline != expected_baseline:
        raise RepairError("baseline_conflict")
    rows, offerings = _validate_current(manifest)
    protected = _protected(offerings, OLD_ROWS)
    batch = f"source-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    changed = _write(task, actor, rows, batch=batch)
    after = _state()
    if before["journals"] != after["journals"]:
        raise RepairError("civil_partition_changed_journal_identity_or_capacity")
    if _protected(offerings, [r.pk for r in changed]) != protected:
        raise RepairError("civil_partition_changed_academic_or_outside_scope")
    for _line, target in TARGETS.items():
        matches = [r for r in changed if sorted(str(g.pk) for g in r.groups.all()) == sorted(target["groups"])]
        if len(matches) != 1 or {(a.teacher_id, a.activity, a.hours) for a in matches[0].assignments.all()} != {
            (target["teacher"], "lecture", 15),
            (target["teacher"], "seminar", target["seminar"]),
        }:
            raise RepairError("civil_partition_postcondition_failed")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=batch,
        reason=RESOURCE,
        new_values={
            "kind": "apply",
            "before": before,
            "manifest_sha256": manifest_sha,
            "after_baseline": digest(after),
            "before_baseline": baseline,
            "source_lines": lines,
        },
    )
    if not apply:
        transaction.set_rollback(True)
    return {"baseline": baseline, "batch": batch, "patched_rows": 2, "created_rows": 1, "created_journals": 0}


@transaction.atomic
def _undo(manifest_sha, batch, *, actor, task, user, organization, before, baseline, expected_baseline, apply):
    if not re.fullmatch(r"source-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", batch):
        raise RepairError("undo_batch_invalid")
    receipt = (
        model("audit.AuditLog")
        .objects.filter(organization=organization, resource_type=RESOURCE, resource_id=batch)
        .order_by("-created_at", "-pk")
        .first()
    )
    values = receipt.new_values if receipt else {}
    if (
        values.get("manifest_sha256") != manifest_sha
        or values.get("after_baseline") != baseline
        or (expected_baseline and expected_baseline != baseline)
    ):
        raise RepairError("civil_partition_undo_requires_unchanged_receipt")
    if values.get("kind") == "undo":
        return {"baseline": baseline, "batch": batch, "already_done": 1}
    old = values["before"]
    offerings = list(model("registrar.CourseOffering").objects.filter(organization=organization, pk__in=JOURNALS))
    protected = _protected(offerings, [r["id"] for r in before["rows"]])
    amend = {"reason": "correction", "note": f"Mənbə bölgüsünün geri qaytarılması [batch:{batch}]"}
    for row in list(_rows()):
        if str(row.pk) not in OLD_ROWS:
            for assignment in list(row.assignments.all()):
                unassign(assignment=assignment, actor=actor, sync_offerings=False)
            delete_row_amended(task=task, row=row, actor=actor, amend=amend)
    fields = (
        "lecture_plan",
        "lecture_total",
        "seminar_plan",
        "seminar_total",
        "lab_plan",
        "lab_total",
        "union_count",
        "subgroup_count",
        "groups_text",
        "subject_text",
        "degree_level",
        "education_form",
        "credits",
        "total_hours",
    )
    for saved in old["rows"]:
        row = _rows().get(pk=saved["id"])
        data = {k: saved[k] for k in fields}
        data["group_ids"] = old["groups"][saved["id"]]
        row = save_row_amended(task=task, row=row, actor=actor, data=data, amend=amend, sync_offerings=False)
        for saved_assignment in old["assignments"]:
            if saved_assignment["row_id"] != saved["id"]:
                continue
            assignment = row.assignments.get(pk=saved_assignment["id"])
            assign_teacher(
                row=row,
                actor=actor,
                assignment=assignment,
                activity=saved_assignment["activity"],
                teacher_id=saved_assignment["teacher_id"],
                hours=saved_assignment["hours"],
                is_hourly_paid=saved_assignment["is_hourly_paid"],
                groups_note=saved_assignment["groups_note"],
                note=saved_assignment["note"],
                sync_offerings=False,
            )
    if _protected(offerings, OLD_ROWS) != protected or _state()["journals"] != before["journals"]:
        raise RepairError("civil_partition_undo_changed_protected_data")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=batch,
        reason=RESOURCE,
        new_values={"kind": "undo", "manifest_sha256": manifest_sha, "after_baseline": digest(_state()), "before": old},
    )
    if not apply:
        transaction.set_rollback(True)
    return {"baseline": baseline, "batch": batch, "restored_rows": 2, "removed_created_rows": 1}
