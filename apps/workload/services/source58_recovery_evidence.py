"""Fixed Source58 current SELECT evidence for a separately guarded recovery transaction."""

from copy import deepcopy

from django.apps import apps

from .offering_rules import plan_reached_chair
from .scoped_snapshot import source58_evidence as evidence
from .scoped_snapshot import source58_evidence_spec as fixed
from .scoped_snapshot.source58_evidence_rows import Rows, budget, project, require_context


def _capture(actor_id):
    result = evidence._capture(actor=actor_id)
    workload = next(
        entry["rows"] for entry in result["source58_reference_graph"] if entry["model"] == "workload.TeachingTaskRow"
    )
    result["source58_runtime_released_rows"] = [
        str(row.pk)
        for row in apps.get_model("workload.TeachingTaskRow")
        .objects.filter(pk__in=[row["id"] for row in workload])
        .select_related("task")
        .order_by("pk")
        if plan_reached_chair(row.task)
    ]
    offerings = next(
        entry["rows"] for entry in result["source58_reference_graph"] if entry["model"] == "registrar.CourseOffering"
    )
    reader = Rows()
    result["source58_runtime_parents"] = project(
        {
            label: reader.read(apps.get_model(label)._base_manager.filter(pk__in=ids))
            for label, ids in (
                ("registrar.Subject", {row["subject_id"] for row in offerings}),
                ("organizations.OrgUnit", {row["group_id"] for row in offerings}),
                ("organizations.AcademicPeriod", {row["period_id"] for row in offerings}),
            )
        }
    )
    return result


def fixed_source58_source_scope():
    """One compiled scope; no caller-provided IDs, substitutions, or mutable globals."""
    return deepcopy(
        dict(
            organization_id=fixed.ORG,
            source_sha256=fixed.SOURCE_SHA256,
            offerings=fixed.OFFERINGS,
            cases=fixed.CASES,
            slots=fixed.SLOTS,
        )
    )


def _lock_rows(current):
    graph = {entry["model"]: list(entry["rows"]) for entry in current["source58_reference_graph"]}
    for key in ("source58_authority_context", "source58_runtime_parents"):
        for entry in current[key]:
            graph.setdefault(entry["model"], []).extend(entry["rows"])
    offerings = graph.get("registrar.CourseOffering", [])
    # Parent locks also serialize new family offerings; existing writers lock
    # offering -> enrollment -> mark. Every other captured row is locked after.
    first = [
        ("registrar.Subject", {row["subject_id"] for row in offerings}),
        ("organizations.AcademicPeriod", {row["period_id"] for row in offerings}),
        ("organizations.OrgUnit", {row["group_id"] for row in offerings}),
        ("registrar.CourseOffering", {row["id"] for row in offerings}),
        ("registrar.Enrollment", {row["id"] for row in graph.get("registrar.Enrollment", [])}),
        ("registrar.Lesson", {row["id"] for row in graph.get("registrar.Lesson", [])}),
        ("registrar.LessonMark", {row["id"] for row in graph.get("registrar.LessonMark", [])}),
    ]
    handled = {label for label, _ in first}
    ordered = first + [
        (label, {row[apps.get_model(label)._meta.pk.attname] for row in rows})
        for label, rows in sorted(graph.items())
        if label not in handled
    ]
    for label, ids in ordered:
        cls = apps.get_model(label)
        list(cls._base_manager.filter(pk__in=ids).order_by("pk").select_for_update().values_list("pk", flat=True))


def fixed_source58_recovery_evidence(*, actor, organization, lock=False):
    """No scope selector, no cache writes; export entry point remains strictly READ ONLY."""
    actor_id = require_context(read_only_required=False)
    if (
        actor_id != actor.pk
        or str(organization.pk) != fixed.ORG
        or not actor.is_active
        or not actor.is_superuser
        or not apps.get_model("organizations.Organization")
        .objects.filter(pk=fixed.ORG, is_active=True, status="active")
        .exists()
    ):
        raise ValueError("source58_current_scoped_actor_required")
    with budget():
        current = _capture(actor_id)
    if lock:
        with budget():
            _lock_rows(current)
        with budget():
            locked = _capture(actor_id)
        if current != locked:
            raise ValueError("source58_current_evidence_changed_during_lock")
        return locked
    return current
