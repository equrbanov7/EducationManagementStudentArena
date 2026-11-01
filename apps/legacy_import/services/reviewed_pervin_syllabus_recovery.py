"""Atomic fill-only original60 approvals; official45 and every academic outcome stay fixed."""

import uuid

from django.db import transaction
from django.utils import timezone

from apps.audit.public import log_action
from apps.syllabus.public import import_migrated_version, resolve_actor, section_data_map, services
from core.constants import AuditAction

from . import exact_syllabus_recovery as core
from . import reviewed_pervin_syllabus_spec as spec
from . import reviewed_pervin_syllabus_state as state
from .reviewed_pervin_syllabus_source import load  # noqa: F401


def _result(status, before, baseline, receipt):
    graph = before["protected"]
    return {
        "status": status,
        "baseline": baseline,
        "receipt": receipt,
        "cases": 2,
        "versions_created": 2 if status == "applied" else 0,
        "versions_archived": 2 if status == "undone" else 0,
        "source_hours": 60,
        "official_hours": 45,
        "graph": core.digest(graph),
    }


def _audit(org, actor, receipt, values):
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=spec.RESOURCE,
        resource_id=receipt,
        resource_repr=receipt,
        reason="Exact own8573 source60 preserved beside distinct official45 workload",
        new_values=values,
    )


@transaction.atomic
def run(*, organization, actor, loaded=None, apply=False, expected_baseline="", undo=""):
    org = organization
    state.actor_scope(org, actor)
    records = core.model("audit.AuditLog").objects.filter(organization=org, resource_type=spec.RESOURCE)
    previous = records.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    if undo:
        try:
            state.require(str(uuid.UUID(undo)) == undo, "pervin_exact_receipt_required")
        except (ValueError, AttributeError):
            raise core.RestoreError("pervin_exact_receipt_required") from None
        state.require(previous is not None and previous.resource_id == undo, "pervin_exact_receipt_required")
    receipt = str(previous.resource_id) if previous else None
    values = previous.new_values if previous else None
    if values:
        state.require(values["source_sha256"] == spec.SOURCE_SHA, "pervin_receipt_source_changed")
    undone = (
        records.filter(new_values__operation="undo", new_values__undo_of=receipt).order_by("-created_at", "pk").first()
        if receipt
        else None
    )
    before, objects = state.snapshot(org, actor, children=values["children"] if values else None, archived=bool(undone))
    baseline = core.digest(before)
    if expected_baseline:
        state.require(expected_baseline == baseline, "pervin_fresh_baseline_required")
    if apply:
        state.require(bool(expected_baseline), "pervin_fresh_baseline_required")
    if previous:
        state.require(
            before == (undone.new_values["after"] if undone else values["after"]), "pervin_post_restore_graph_changed"
        )
        if undone:
            state.require(bool(undo), "pervin_previous_undo_requires_review")
            return _result("already_undone", before, baseline, receipt)
        if not undo:
            return _result("already_present", before, baseline, receipt)
    if not apply:
        return _result("dry_run", before, baseline, receipt)
    if undo:
        for child in values["children"]:
            syllabus = (
                core.model("syllabus.Syllabus").objects.select_for_update().get(pk=child["syllabus"], organization=org)
            )
            version = (
                core.model("syllabus.SyllabusVersion")
                .objects.select_for_update()
                .get(pk=child["version"], organization=org, syllabus=syllabus)
            )
            services.archive(version=version, actor=resolve_actor(actor, org))
            syllabus.is_active = False
            syllabus.save(update_fields=["is_active", "updated_at"])
        after, _ = state.snapshot(org, actor, children=values["children"], archived=True)
        state.require(before["protected"] == after["protected"], "pervin_full_graph_preservation_failed")
        _audit(org, actor, receipt, dict(operation="undo", undo_of=receipt, after=after, source_sha256=spec.SOURCE_SHA))
        return _result("undone", before, baseline, receipt)
    state.require(loaded is not None, "pervin_exact_loaded_source_required")
    sections, codes = loaded
    load_sections_check(sections)
    children = []
    for offering in objects:
        syllabus, version = import_migrated_version(
            organization=org,
            subject=offering.subject,
            offering=offering,
            period=offering.period,
            author=offering.restoration_author,
            chair_unit=offering.subject.chair_unit,
            approved_at=timezone.now(),
            plan_hours={"lecture": 30, "seminar": 30, "practical": 0, "lab": 0},
            section_data=sections,
            note=spec.NOTE,
        )
        state.require(section_data_map(version) == sections, "pervin_source_import_changed")
        children.append({"offering": str(offering.pk), "syllabus": str(syllabus.pk), "version": str(version.pk)})
    after, _ = state.snapshot(org, actor, children=children)
    state.require(before["protected"] == after["protected"], "pervin_full_graph_preservation_failed")
    receipt = str(uuid.uuid4())
    _audit(
        org,
        actor,
        receipt,
        dict(
            operation="apply",
            source_sha256=spec.SOURCE_SHA,
            before=before,
            after=after,
            children=children,
            conversion_codes=list(codes),
            legacy_approval_asserted=False,
            source_hours=60,
            official_hours=45,
            hours_changed=0,
            topics_trimmed=0,
        ),
    )
    return _result("applied", before, baseline, receipt)


def load_sections_check(sections):
    from apps.syllabus.public import content_fingerprints

    state.require(
        content_fingerprints(sections)["canonical_body_sha256"] == spec.BODY_SHA, "pervin_loaded_source_body_changed"
    )
    return sections
