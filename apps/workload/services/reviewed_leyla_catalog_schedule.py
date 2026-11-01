"""Current six-slot handover: park original IDs, create canonical copies, never guess a timetable."""

from django.db import transaction

from apps.registrar.public import schedule, schedule_conflicts, schedule_editor_actions, schedule_lock

from . import reviewed_leyla_catalog_spec as spec
from .reviewed_leyla_catalog_graph import bounded, digest, model, require

PARK_FIELDS = {"is_parked", "parked_at", "parked_by_id", "park_reason", "updated_at"}
SLOT_FIELDS = ("weekday", "start_time", "end_time", "room", "week_type", "kind")


def lock_scope(org):
    schedule_lock.lock_schedule(org.pk, spec.PERIOD)


def capture(org):
    lock_scope(org)
    rows = bounded(
        model("registrar.ScheduleSlot")._base_manager.filter(organization=org, offering_id__in=spec.OFFERINGS), cap=24
    )
    source = [r for r in rows if r["offering_id"] in spec.EMPTY]
    require(len(source) == spec.SCHEDULE_SOURCE_COUNT, "leyla_exact_six_source_slots_required")
    for oid in spec.EMPTY:
        slots = [r for r in source if r["offering_id"] == oid]
        require(
            len(slots) == 2 and {r["kind"] for r in slots} == {"lecture", "seminar"},
            "leyla_source_whole_kind_schedule_changed",
        )
    require(
        all(
            1 <= r["weekday"] <= 7 and r["week_type"] in ("all", "odd", "even") and r["start_time"] < r["end_time"]
            for r in source
        ),
        "leyla_source_schedule_shape_changed",
    )
    require(
        all(
            not r["is_deleted"] and r.get("deleted_at") is None and r["instructor_id"] in (None, spec.TEACHER)
            for r in source
        ),
        "leyla_source_schedule_teacher_or_delete_changed",
    )
    return {"rows": rows, "source_sha256": digest(source)}


def _children(slot):
    for rel in slot._meta.get_fields(include_hidden=True):
        child = rel.related_model
        if rel.auto_created and not rel.concrete and child is not None:
            lookup = rel.field.name if rel.many_to_many else rel.field.attname
            require(bool(lookup), "leyla_slot_reverse_relation_not_supported")
            require(not child._base_manager.filter(**{lookup: slot.pk}).exists(), "leyla_slot_has_actual_links")


def _objects(org):
    return {
        str(o.pk): o
        for o in model("registrar.CourseOffering")
        .objects.filter(organization=org, pk__in=spec.OFFERINGS)
        .select_related("organization", "period", "subject", "instructor")
    }


def plan(org, value):
    objects = _objects(org)
    Slot = model("registrar.ScheduleSlot")
    source_ids = [r["id"] for r in value["rows"] if r["offering_id"] in spec.EMPTY]
    require(all(not r["is_parked"] for r in value["rows"] if r["id"] in source_ids), "leyla_source_schedule_parked")
    require(not any(r["offering_id"] in spec.FILLED for r in value["rows"]), "leyla_canonical_schedule_already_present")
    source_rows = [r for r in value["rows"] if r["id"] in source_ids]
    for index, first in enumerate(source_rows):
        for second in source_rows[index + 1 :]:
            overlaps = (
                first["weekday"] == second["weekday"]
                and schedule_conflicts.week_types_overlap(first["week_type"], second["week_type"])
                and schedule_conflicts.time_ranges_overlap(
                    first["start_time"], first["end_time"], second["start_time"], second["end_time"]
                )
            )
            if not overlaps:
                continue
            a, b = objects[spec.PAIRS[first["offering_id"]]], objects[spec.PAIRS[second["offering_id"]]]
            same_row = any(
                str(a.group_id) in pin["groups"] and str(b.group_id) in pin["groups"] for pin in spec.ROWS.values()
            )
            require(
                a.group_id != b.group_id
                and a.subject_id == b.subject_id
                and same_row
                and all(first[k] == second[k] for k in SLOT_FIELDS),
                "leyla_proposed_schedule_overlap_requires_review",
            )
    pairs = []
    for row in value["rows"]:
        if row["id"] not in source_ids:
            continue
        slot = Slot.all_objects.select_for_update().get(pk=row["id"], organization=org)
        _children(slot)
        target = objects[spec.PAIRS[row["offering_id"]]]
        require(not target.period.locked_at and target.period.is_active, "leyla_planning_period_locked")
        conflicts = schedule_conflicts.detect(
            organization=org,
            period_id=spec.PERIOD,
            group_id=target.group_id,
            subject_id=target.subject_id,
            offering_id=target.pk,
            instructor_id=spec.TEACHER,
            exclude_ids=source_ids,
            **{k: getattr(slot, k) for k in SLOT_FIELDS},
        )
        require(not conflicts, "leyla_current_schedule_conflict")
        pairs.append({"source": row["id"], "target_offering": str(target.pk)})
    return pairs


@transaction.atomic
def apply(org, actor, before):
    pairs = plan(org, before)
    Slot = model("registrar.ScheduleSlot")
    for pair in pairs:
        slot = Slot.all_objects.get(pk=pair["source"], organization=org)
        schedule_editor_actions.park_slot(
            actor=actor,
            organization=org,
            slot=slot,
            reason="Reviewed workload catalog relink; original planning evidence retained.",
        )
    objects = _objects(org)
    for pair in pairs:
        slot = Slot.all_objects.get(pk=pair["source"], organization=org)
        target = objects[pair["target_offering"]]
        # The canonical schedule API retains conflict/RBAC/semester locking semantics.
        replacement = schedule.create_slot(
            offering=target,
            created_by=actor,
            instructor=target.instructor,
            **{k: getattr(slot, k) for k in SLOT_FIELDS},
        )
        pair["target"] = str(replacement.pk)
    return pairs


def preserved(before, after, pairs):
    old = {r["id"]: r for r in before["rows"]}
    new = {r["id"]: r for r in after["rows"]}
    created = {p["target"] for p in pairs}
    require(
        set(new) == set(old) | created and len(created) == spec.SCHEDULE_SOURCE_COUNT, "leyla_schedule_scope_changed"
    )
    for pair in pairs:
        source, target = new[pair["source"]], new[pair["target"]]
        require(
            source["is_parked"] and not target["is_parked"] and not target["is_deleted"],
            "leyla_schedule_parking_failed",
        )
        require(
            {k: v for k, v in old[source["id"]].items() if k not in PARK_FIELDS}
            == {k: v for k, v in source.items() if k not in PARK_FIELDS},
            "leyla_original_schedule_changed",
        )
        require(
            all(source[k] == target[k] for k in SLOT_FIELDS)
            and target["offering_id"] == pair["target_offering"]
            and target["organization_id"] == spec.ORG
            and target["instructor_id"] in (None, spec.TEACHER),
            "leyla_canonical_schedule_copy_changed",
        )


@transaction.atomic
def undo(org, actor, original, pairs):
    Slot = model("registrar.ScheduleSlot")
    originals = {r["id"]: r for r in original["rows"]}
    objects = _objects(org)
    excluded = [p[k] for p in pairs for k in ("source", "target")]
    for pair in pairs:
        source = Slot.all_objects.select_for_update().get(pk=pair["source"], organization=org)
        offering = objects[str(source.offering_id)]
        require(
            not schedule_conflicts.detect(
                organization=org,
                period_id=spec.PERIOD,
                group_id=offering.group_id,
                subject_id=offering.subject_id,
                offering_id=offering.pk,
                instructor_id=spec.TEACHER,
                exclude_ids=excluded,
                **{k: getattr(source, k) for k in SLOT_FIELDS},
            ),
            "leyla_undo_schedule_conflict",
        )
    for pair in pairs:
        target = Slot.all_objects.select_for_update().get(pk=pair["target"], organization=org)
        _children(target)
        schedule_editor_actions.park_slot(
            actor=actor,
            organization=org,
            slot=target,
            reason="Undo reviewed catalog relink; new planning evidence retained.",
        )
    for pair in pairs:
        row = originals[pair["source"]]
        values = {
            k: Slot._meta.get_field(k.removesuffix("_id") if k.endswith("_id") else k).to_python(row[k])
            for k in PARK_FIELDS
        }
        require(
            Slot.all_objects.filter(pk=row["id"], organization=org).update(**values) == 1,
            "leyla_schedule_undo_conflict",
        )
    current = {r["id"]: r for r in capture(org)["rows"]}
    require(all(current[pk] == row for pk, row in originals.items()), "leyla_original_schedule_restore_failed")
    require(all(current[p["target"]]["is_parked"] for p in pairs), "leyla_undo_canonical_schedule_active")
