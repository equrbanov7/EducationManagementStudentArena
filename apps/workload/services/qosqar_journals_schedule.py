"""Project both fixed pairs together; never suppress a third-party timetable conflict."""

from copy import copy

from . import qosqar_journals_state as state
from . import qosqar_schedule as single

SIGNATURES = {
    (3, "16:55:00", "18:25:00", "all", "lecture", ""),
    (5, "13:35:00", "15:05:00", "odd", "lecture", "35"),
    (5, "13:35:00", "15:05:00", "even", "seminar", "35"),
    (5, "15:15:00", "16:45:00", "all", "seminar", "35"),
}


def signature(slot):
    return (slot.weekday, str(slot.start_time), str(slot.end_time), slot.week_type, slot.kind, slot.room)


def _outside(slot, offering, excluded):
    if single.schedule_conflicts.detect(
        organization=offering.organization,
        period_id=offering.period_id,
        group_id=offering.group_id,
        subject_id=offering.subject_id,
        offering_id=offering.pk,
        instructor_id=state.duplicate.TEACHER,
        weekday=slot.weekday,
        start_time=slot.start_time,
        end_time=slot.end_time,
        week_type=slot.week_type,
        room=slot.room,
        kind=slot.kind,
        exclude_ids=excluded,
    ):
        raise state.Error("combined_reviewed_schedule_external_conflict")


def _internal(projected):
    for index, left in enumerate(projected):
        for right in projected[index + 1 :]:
            if (
                left.weekday != right.weekday
                or not single.schedule_conflicts.week_types_overlap(left.week_type, right.week_type)
                or not single.schedule_conflicts.time_ranges_overlap(
                    left.start_time, left.end_time, right.start_time, right.end_time
                )
            ):
                continue
            if left.offering.group_id == right.offering.group_id or not single.schedule.is_joint_lecture(
                kind=left.kind,
                subject_id=left.offering.subject_id,
                teacher_id=state.duplicate.TEACHER,
                room=left.room,
                slot=right,
            ):
                raise state.Error("combined_projected_schedule_conflict")


def plan():
    """Exclude exactly both reviewed source sets; validate all other live DB slots."""
    source_slots, targets = [], {}
    for source_id, target_id in state.pairs().items():
        source, target, slots = single.validate_empty(source_id, target_id)
        if source.period.locked_at or not source.period.is_active:
            raise state.Error("reviewed_schedule_period_locked")
        active = [s for s in slots if not s.is_deleted and not s.is_parked]
        if len(active) != 4 or {signature(s) for s in active} != SIGNATURES:
            raise state.Error("reviewed_source_four_slot_signature_set_changed")
        source_slots.extend(active)
        targets[target_id] = target
    excluded_sources = [s.pk for s in source_slots]
    pairs, projected = [], []
    for source in source_slots:
        target_id = state.pairs()[str(source.offering_id)]
        target = copy(targets[target_id])
        target.subject_id = state.duplicate.SUBJECT
        candidates = list(
            state.model("registrar.ScheduleSlot")
            .all_objects.select_for_update()
            .filter(organization_id=state.duplicate.ORG, offering_id=target_id)
            .select_related("offering")
        )
        active_targets = [s for s in candidates if not s.is_parked and not s.is_deleted]
        if len(candidates) > 128 or any(
            signature(s) not in SIGNATURES or single.schedule.effective_instructor_id(s) != state.duplicate.TEACHER
            for s in active_targets
        ):
            raise state.Error("reviewed_target_schedule_signature_changed")
        exact = [s for s in active_targets if single._signature(s) == single._signature(source)]
        if len(exact) > 1:
            raise state.Error("ambiguous_target_schedule_signature")
        _outside(source, target, excluded_sources + [s.pk for s in exact])
        item = copy(source)
        item.offering = target
        projected.append(item)
        pairs.append(
            {
                "source": str(source.pk),
                "target": str(exact[0].pk) if exact else None,
                "created": not exact,
                "source_offering": str(source.offering_id),
                "target_offering": target_id,
            }
        )
    _internal(projected)
    return pairs


def park_sources(*, pairs, organization, user):
    Slot = state.model("registrar.ScheduleSlot")
    for pair in pairs:
        slot = Slot.objects.get(pk=pair["source"], organization=organization, offering_id=pair["source_offering"])
        single.schedule_editor_actions.park_slot(
            actor=user,
            organization=organization,
            slot=slot,
            reason="Qoşqar two reviewed journals: preserve original timetable",
        )


def copy_targets(*, pairs, organization, user):
    Slot = state.model("registrar.ScheduleSlot")
    # All8 original slots are already parked. Both targets are now canonical868.
    for pair in pairs:
        target = state.model("registrar.CourseOffering").objects.get(
            pk=pair["target_offering"], organization=organization, subject_id=state.duplicate.SUBJECT
        )
        source = Slot.objects.get(pk=pair["source"], organization=organization, offering_id=pair["source_offering"])
        excluded = [pair["target"]] if not pair["created"] else []
        _outside(source, target, excluded)
        if pair["created"]:
            replacement = single.schedule.create_slot(
                offering=target,
                created_by=user,
                instructor=target.instructor,
                **{
                    key: getattr(source, key)
                    for key in ("weekday", "start_time", "end_time", "room", "week_type", "kind")
                },
            )
            pair["target"] = str(replacement.pk)
    return pairs


def preserved(*, before, after, pairs):
    # Canonical primitive checks every original concrete field and any added ID.
    single.preserved(before=before, after=after, pairs=pairs)


def check_undo(*, before, current, pairs):
    preserved(before=before, after=current, pairs=pairs)
    originals = {str(r["id"]): r for r in before}
    Slot = state.model("registrar.ScheduleSlot")
    excluded = [p[k] for p in pairs for k in ("source", "target")]
    projected = []
    if len(pairs) != 8 or {p["source_offering"] for p in pairs} != set(state.pairs()):
        raise state.Error("undo_fixed_eight_slot_receipt_changed")
    for pair in pairs:
        if state.pairs().get(pair["source_offering"]) != pair["target_offering"]:
            raise state.Error("undo_fixed_pair_changed")
        source, _target, _slots = single.validate_empty(pair["source_offering"], pair["target_offering"])
        if source.period.locked_at or not source.period.is_active:
            raise state.Error("reviewed_schedule_period_locked")
        row = originals[pair["source"]]
        slot = Slot.objects.get(pk=pair["source"], organization_id=state.duplicate.ORG, offering=source)
        _outside(slot, source, excluded)
        item = copy(slot)
        for key in single.PARK_FIELDS:
            setattr(item, key, row[key])
        projected.append(item)
        if pair["created"] and any(single._children("registrar.ScheduleSlot", [pair["target"]])):
            raise state.Error("undo_created_slot_has_history")
    _internal(projected)


def undo(*, before, pairs, organization, user):
    Slot = state.model("registrar.ScheduleSlot")
    current = state.schedule_rows(state.capture())
    check_undo(before=before, current=current, pairs=pairs)
    for pair in pairs:
        if pair["created"]:
            target = Slot.objects.get(pk=pair["target"], organization=organization, offering_id=pair["target_offering"])
            single.schedule_editor_actions.park_slot(
                actor=user,
                organization=organization,
                slot=target,
                reason="Qoşqar combined correction undo: retained target slot",
            )
    originals = {str(r["id"]): r for r in before}
    for pair in pairs:
        row = originals[pair["source"]]
        values = {
            key: Slot._meta.get_field(key.removesuffix("_id") if key.endswith("_id") else key).to_python(row[key])
            for key in single.PARK_FIELDS
        }
        Slot.objects.filter(pk=pair["source"], organization=organization, offering_id=pair["source_offering"]).update(
            **values
        )
    restored = {str(r["id"]): r for r in state.schedule_rows(state.capture())}
    if any(state.digest(restored[pk]) != state.digest(row) for pk, row in originals.items()):
        raise state.Error("undo_original_schedule_not_exact")
    if any(not restored[p["target"]]["is_parked"] for p in pairs if p["created"]):
        raise state.Error("undo_created_schedule_not_parked")
