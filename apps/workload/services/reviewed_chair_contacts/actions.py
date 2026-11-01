"""Canonical amendments, exact activity sharing and approved plan metadata only."""

import uuid
from collections import defaultdict

from apps.registrar.public import sync_workload_journal_shares
from apps.syllabus.public import resolve_actor as resolve_syllabus_actor
from apps.syllabus.public import set_plan_hours_override

from ...constants import AmendmentReason
from ..assignments import assign_teacher, unassign
from ..offering_shares import plan_for_rows
from ..offering_sync import sync_task_offerings
from ..row_edit import save_row_amended
from ..sbio235_state import RepairError, model
from ..scoping import resolve_actor
from . import state


def _amend(batch):
    return {
        "reason": AmendmentReason.CORRECTION,
        "note": f"Baxılmış rəsmi kafedra mənbəsinə görə saat və fəaliyyət düzəlişi [batch:{batch}]",
    }


def _assign(row, saved, desired, actor):
    note, groups_note = saved.note, saved.groups_note
    result = assign_teacher(
        row=row,
        actor=actor,
        assignment=saved,
        activity=desired["activity"],
        teacher_id=desired["teacher_id"],
        hours=desired["hours"],
        is_hourly_paid=desired["is_hourly_paid"],
        groups_note=saved.groups_note,
        note=saved.note,
        sync_offerings=False,
    )
    model("workload.TeacherAssignment").objects.filter(pk=result.pk).update(note=note, groups_note=groups_note)
    return result


def apply(cases, before, *, organization, user, batch):
    actor = resolve_actor(user, organization)
    selected = []
    for pin in state.flat(cases, "rows").values():
        row = model("workload.TeachingTaskRow").objects.select_related("task").get(pk=pin["id"])
        row = save_row_amended(task=row.task, actor=actor, row=row, data={}, amend=_amend(batch), sync_offerings=False)
        for assignment in pin["assignments"]:
            old = model("workload.TeacherAssignment").objects.get(pk=assignment["id"], row=row)
            if assignment["new"] is None:
                unassign(assignment=old, actor=actor, sync_offerings=False)
            elif any(getattr(old, key) != value for key, value in assignment["new"].items()):
                _assign(row, old, assignment["new"], actor)
        row = save_row_amended(
            task=row.task, actor=actor, row=row, data=pin["new"], amend=_amend(batch), sync_offerings=False
        )
        selected.append(row)
    previous = {
        (uuid.UUID(pin["subject_id"]), uuid.UUID(pin["period_id"]), uuid.UUID(pin["group_id"])): pin["old_owner"]
        for pin in state.flat(cases, "offerings").values()
    }
    grouped = defaultdict(list)
    for row in selected:
        grouped[row.task_id].append(row)
    for rows in grouped.values():
        report = sync_task_offerings(rows[0].task, actor=actor, rows=rows, create=False, previous=previous)
        if any(report.get(key) for key in ("created", "blocked", "period_locked", "inactive_skipped")):
            raise RepairError("bounded_course_sync_rejected")
    # A logical course spans legacy task documents. Derive its final kind shares
    # once from the complete reviewed contributor set, never the last task alone.
    for case in cases.values():
        rows = list(
            model("workload.TeachingTaskRow")
            .objects.filter(pk__in=[r["id"] for r in case["rows"]])
            .select_related("task")
            .prefetch_related("groups", "assignments")
        )
        plans = {}
        for pk, pin in case["offerings"].items():
            offering = model("registrar.CourseOffering").objects.select_related("group").get(pk=pk)
            if offering.instructor_id != pin["new_owner"] or offering.lesson_hours != pin["new_hours"]:
                raise RepairError("canonical_source_owner_or_hours_not_reached")
            plan = plan_for_rows(rows, group=offering.group)
            if plan["owner_id"] != offering.instructor_id or plan["ambiguous"]:
                raise RepairError("source_contributor_plan_ambiguous")
            plans[(offering.subject_id, offering.period_id, offering.group_id)] = plan
        report = sync_workload_journal_shares(
            organization_id=organization.pk,
            offering_ids=list(case["offerings"]),
            plans=plans,
            by_user=user,
        )
        if report.get("ambiguous") or report.get("skipped"):
            raise RepairError("exact_source_kind_shares_rejected")
        for syllabus in model("syllabus.Syllabus").objects.filter(
            pk__in=before["selected_syllabus_ids"], offering_id__in=case["offerings"]
        ):
            set_plan_hours_override(
                syllabus=syllabus, hours=case["plan_hours"], actor=resolve_syllabus_actor(user, organization)
            )
    return {}


def undo(cases, before, *, organization, user, batch, details):
    actor = resolve_actor(user, organization)
    row_ids = list(state.flat(cases, "rows"))
    for assignment in list(
        model("workload.TeacherAssignment").objects.filter(row_id__in=row_ids).select_related("row__task")
    ):
        unassign(assignment=assignment, actor=actor, sync_offerings=False)
    for saved in before["rows"]:
        row = model("workload.TeachingTaskRow").objects.select_related("task").get(pk=saved["id"])
        fields = {key: saved[key] for key in state.flat(cases, "rows")[saved["id"]]["old"]}
        save_row_amended(task=row.task, actor=actor, row=row, data=fields, amend=_amend(batch), sync_offerings=False)
        for previous in (a for a in before["assignments"] if a["row_id"] == saved["id"]):
            assignment = model("workload.TeacherAssignment")(
                pk=previous["id"],
                organization=organization,
                row=row,
                groups_note=previous["groups_note"],
                note=previous["note"],
            )
            _assign(row, assignment, previous, actor)
            model("workload.TeacherAssignment").objects.filter(pk=assignment.pk).update(
                **{key: value for key, value in previous.items() if key != "id"}
            )
    offering_ids = list(state.flat(cases, "offerings"))
    model("registrar.JournalShare").objects.filter(
        organization=organization, offering_id__in=offering_ids, source="workload"
    ).delete()
    for previous in before["offerings"]:
        model("registrar.CourseOffering").objects.filter(pk=previous["id"]).update(
            lesson_hours=previous["lesson_hours"], instructor_id=previous["instructor_id"]
        )
    for previous in before["shares"]:
        if previous["source"] == "workload":
            share = model("registrar.JournalShare")(**previous)
            share.save(force_insert=True)
            model("registrar.JournalShare").objects.filter(pk=share.pk).update(
                **{key: value for key, value in previous.items() if key != "id"}
            )
    versions = {v["id"]: v for v in before["versions"]}
    for previous in before["syllabi"]:
        if previous["id"] not in before["selected_syllabus_ids"]:
            continue
        syllabus = model("syllabus.Syllabus").objects.get(pk=previous["id"])
        set_plan_hours_override(
            syllabus=syllabus,
            hours=previous["plan_hours_override"],
            auto_hours=versions[previous["approved_version_id"]]["plan_hours"],
            actor=resolve_syllabus_actor(user, organization),
        )
