"""Atomic fixed source restoration and exact metadata repair; dry by default."""

import uuid

from django.db import connection, transaction
from django.utils import timezone

from apps.audit.public import log_action
from apps.registrar.public import subject_merge_apply
from apps.syllabus.public import import_migrated_version, link_legacy_share, resolve_actor, section_data_map, services
from apps.workload.public import resolve_actor as resolve_workload_actor
from apps.workload.public import reviewed_catalog_graph as e
from apps.workload.public import unassign
from core.constants import AuditAction

from . import reviewed_solmaz_spec as spec
from . import reviewed_solmaz_state as state
from .reviewed_solmaz_source import load


def _write_metadata(org, actor, corrected, excess=None):
    Assignment = e.model("workload.TeacherAssignment")
    if corrected:
        assignment = Assignment.objects.select_for_update().get(organization=org, pk=spec.ASSIGNMENT)
        unassign(assignment=assignment, actor=resolve_workload_actor(actor, org), sync_offerings=False)
    row_target = spec.ROW_CHANGE if corrected else {k: spec.PINS["rows"][spec.ROW][k] for k in spec.ROW_CHANGE}
    e.require(
        e.model("workload.TeachingTaskRow").objects.filter(organization=org, pk=spec.ROW).update(**row_target) == 1,
        "solmaz_exact_row_write_conflict",
    )
    if not corrected:
        e.require(
            excess
            and excess["id"] == spec.ASSIGNMENT
            and not Assignment._base_manager.filter(pk=spec.ASSIGNMENT).exists(),
            "solmaz_exact_assignment_undo_conflict",
        )
        Assignment.objects.create(**excess)
        Assignment.objects.filter(pk=spec.ASSIGNMENT).update(**{k: v for k, v in excess.items() if k != "id"})
    subject = spec.CORRECT_SUBJECT if corrected else spec.PINS["courses"][spec.COURSE]["subject_id"]
    original = spec.PINS["courses"][spec.COURSE]["subject_id"] if corrected else spec.CORRECT_SUBJECT
    subject_merge_apply.allow_offering_subject_change([original], subject)
    try:
        e.require(
            e.model("registrar.CourseOffering")
            ._base_manager.filter(organization=org, pk=spec.COURSE, subject_id=original)
            .update(subject_id=subject)
            == 1,
            "solmaz_exact_course_write_conflict",
        )
    finally:
        subject_merge_apply.clear_offering_subject_change()


def _preserved(before, after):
    for key in ("protected", "authority", "credits", "official_context"):
        e.require(before[key] == after[key], "solmaz_protected_" + key + "_changed")


def _result(status, before, receipt=None, after=None):
    return {
        "status": status,
        "baseline": e.digest(before),
        "after_baseline": e.digest(after or before),
        "receipt": receipt,
        "applied": status in ("applied", "undone"),
        "new_source_versions": 1 if status == "applied" else 0,
        "new_shares": 2 if status == "applied" else 0,
        "teacher_hours": 165 if (after or before)["corrected"] else 180,
        "source_sha256": spec.PINS["source_packet_sha256"],
        "protected_models": len(before["protected"]),
        "protected_rows": sum(r["count"] for r in before["protected"].values()),
    }


def _receipt_source(receipt, kind):
    values = receipt.new_values
    e.require(
        set(values) == {"kind", "undo_of", "after", "source_sha256", "legacy_approval_asserted", "conversion_codes"}
        and values["kind"] == kind
        and values["source_sha256"] == spec.PINS["source_packet_sha256"]
        and values["legacy_approval_asserted"] is False
        and isinstance(values["conversion_codes"], list),
        "solmaz_receipt_source_scope_changed",
    )


@transaction.atomic
def run(org, actor, source_path, source_sha256, *, apply=False, expected_baseline="", undo=""):
    e.require(connection.vendor == "postgresql", "solmaz_postgresql_required")
    state.actor_scope(org, actor)
    sections, codes = load(source_path, source_sha256)
    receipts = (
        e.model("audit.AuditLog").objects.select_for_update().filter(organization=org, resource_type=spec.RESOURCE)
    )
    previous = receipts.filter(new_values__kind="apply").order_by("-created_at", "-pk").first()
    undone = (
        receipts.filter(new_values__kind="undo", new_values__undo_of=previous.resource_id)
        .order_by("-created_at", "-pk")
        .first()
        if previous
        else None
    )
    if previous:
        _receipt_source(previous, "apply")
    if undone:
        _receipt_source(undone, "undo")
    if undo:
        try:
            e.require(
                str(uuid.UUID(undo)) == undo and previous is not None and previous.resource_id == undo,
                "solmaz_exact_receipt_required",
            )
        except (ValueError, TypeError):
            e.require(False, "solmaz_exact_receipt_required")
    created = previous.new_values["after"]["created"] if previous else {}
    before = state.snapshot(org, actor, created=created, corrected=bool(previous and not undone), archived=bool(undone))
    if previous:
        expected = undone.new_values["after"] if undone else previous.new_values["after"]
        e.require(before == expected, "solmaz_receipt_current_graph_drift")
        if undone or not undo:
            return _result("already_undone" if undone else "already_applied", before, previous.resource_id)
    baseline = e.digest(before)
    if expected_baseline:
        e.require(expected_baseline == baseline, "solmaz_fresh_baseline_required")
    if not apply:
        return _result("dry_run", before, previous.resource_id if previous else None)
    e.require(expected_baseline == baseline, "solmaz_fresh_baseline_required")
    receipt_id = undo or str(uuid.uuid4())
    if undo:
        for share_id in created["syllabus.SyllabusShare"]:
            share = e.model("syllabus.SyllabusShare")._base_manager.get(pk=share_id, organization=org)
            count, _ = share.delete()
            e.require(count == 1, "solmaz_share_undo_has_new_dependents")
        version = e.model("syllabus.SyllabusVersion")._base_manager.get(
            pk=created["syllabus.SyllabusVersion"][0], organization=org
        )
        services.archive(version=version, actor=resolve_actor(actor, org))
        _write_metadata(org, actor, False, previous.old_values["excess_allocation"])
        after = state.snapshot(org, actor, created=created, archived=True)
        _preserved(before, after)
        original = previous.old_values
        for key in ("rows", "assignments", "courses", "pointers", "excess_allocation"):
            e.require(after[key] == original[key], "solmaz_exact_undo_restore_failed")
    else:
        _write_metadata(org, actor, True)
        syllabus = e.model("syllabus.Syllabus")._base_manager.get(pk=spec.SOURCE_SYLLABUS, organization=org)
        draft = e.model("syllabus.SyllabusVersion")._base_manager.get(
            pk=spec.DRAFT, syllabus=syllabus, organization=org
        )
        e.require(
            draft.status == "draft" and not syllabus.versions.filter(major=draft.major, minor=draft.minor + 1).exists(),
            "solmaz_source_version_slot_changed",
        )
        _, version = import_migrated_version(
            organization=org,
            subject=syllabus.subject,
            offering=syllabus.offering,
            period=syllabus.period,
            author=syllabus.author,
            chair_unit=syllabus.chair_unit,
            program=syllabus.program,
            major=draft.major,
            minor=draft.minor + 1,
            approved_at=timezone.now(),
            plan_hours={"lecture": 30, "seminar": 30, "practical": 0, "lab": 0},
            section_data=sections,
            note="Reviewed current migration approval of own source8355 and explicit187→2078 ancient-literature alias; legacy approval is not asserted. Original human draft retained.",
        )
        e.require(
            section_data_map(version) == sections
            and version.approved_by_id is None
            and version.approval_source == "migration",
            "solmaz_import_content_changed",
        )
        shares = []
        for course_id, syllabus_id in spec.SHARES.items():
            source = e.model("syllabus.Syllabus")._base_manager.get(pk=syllabus_id, organization=org)
            course = e.model("registrar.CourseOffering")._base_manager.get(pk=course_id, organization=org)
            e.require(
                link_legacy_share(syllabus=source, offering=course, user=actor) == "linked",
                "solmaz_own_source_share_refused",
            )
            shares.append(
                str(e.model("syllabus.SyllabusShare")._base_manager.get(organization=org, offering=course).pk)
            )
        created = {
            "syllabus.SyllabusVersion": [str(version.pk)],
            "syllabus.SyllabusSection": sorted(map(str, version.sections.values_list("pk", flat=True))),
            "syllabus.SyllabusShare": sorted(shares),
        }
        e.require(len(created["syllabus.SyllabusSection"]) == 10, "solmaz_complete_source_sections_required")
        after = state.snapshot(org, actor, created=created, corrected=True)
        _preserved(before, after)
    e.model("workload.WorkloadAmendment").objects.create(
        organization=org,
        task_id=spec.PINS["task"]["id"],
        target_kind="row",
        target_id=spec.ROW,
        reason="correction",
        made_by=actor,
        note="Exact official165h World-literature patok; source workbook and retained full original journals.",
        old_values=before["rows"][spec.ROW],
        new_values={**after["rows"][spec.ROW], "source_sha256": spec.PINS["source_official_sha256"]},
    )
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=spec.RESOURCE,
        resource_id=receipt_id,
        reason="One reviewed own-source version, two same-author shares and one official165h patok correction; all original academic records retained.",
        old_values=before,
        new_values={
            "kind": "undo" if undo else "apply",
            "undo_of": undo or None,
            "after": after,
            "source_sha256": source_sha256,
            "legacy_approval_asserted": False,
            "conversion_codes": codes,
        },
    )
    return _result("undone" if undo else "applied", before, receipt_id, after)
