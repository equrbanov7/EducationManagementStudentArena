"""Only the fixed AppliedMath pair: retain slot IDs and compensate safely."""

from copy import copy

from django.db import transaction

from apps.registrar.public import schedule, schedule_conflicts, schedule_editor_actions, schedule_lock

from . import applied_math_state as state

PAIRS = {state.EMPTY: state.FILLED}
TEACHER = state.TEACHER
CANONICAL_SUBJECT = state.NEW
PARK_FIELDS = {"is_parked", "parked_at", "parked_by_id", "park_reason", "updated_at"}
CONFIG = {
    "registrar.Enrollment",
    "registrar.AssessmentScheme",
    "registrar.AssessmentComponent",
    "registrar.JournalShare",
    "registrar.JournalShare_enrollments",
}


def _pair(source_id, target_id):
    if PAIRS.get(str(source_id)) != str(target_id):
        raise state.DuplicateError("schedule_fixed_reviewed_pair_required")
    offerings = {
        str(o.pk): o
        for o in state.model("registrar.CourseOffering")
        .objects.filter(
            organization_id=state.ORG,
            pk__in=(source_id, target_id),
        )
        .select_related("organization", "period", "subject", "instructor")
    }
    if len(offerings) != 2:
        raise state.DuplicateError("schedule_fixed_pair_missing")
    source, target = offerings[str(source_id)], offerings[str(target_id)]
    if (
        source.instructor_id != TEACHER
        or target.instructor_id != TEACHER
        or source.group_id is None
        or source.group_id != target.group_id
        or source.period_id != target.period_id
        or source.subject.code not in ("QKU-45", "QKU-1797")
        or target.subject.code not in ("QKU-45", "QKU-1797")
        or source.lesson_hours != 45
        or target.lesson_hours != 45
        or source.is_intensive
        or target.is_intensive
    ):
        raise state.DuplicateError("schedule_fixed_pair_identity_changed")
    return source, target


def slot_rows(source_id, target_id):
    _pair(source_id, target_id)
    return state.records(
        state.model("registrar.ScheduleSlot").all_objects.filter(
            organization_id=state.ORG,
            offering_id__in=(source_id, target_id),
        )
    )


def _children(label, ids):
    for relation in state.model(label)._meta.get_fields(include_hidden=True):
        child = relation.related_model
        if not relation.auto_created or relation.concrete or not child:
            continue
        field = relation.field
        lookup = field.name if relation.many_to_many else field.attname
        query = child._base_manager.filter(**{f"{lookup}__in": ids})
        if query.exists():
            yield child._meta.label, query


def validate_empty(source_id, target_id):
    """Only configuration and fully inspected slots may survive on the source.

    All unknown reverse relations, including descendants under configuration,
    fail closed. No ScheduleSlot exception is granted to other retire services.
    """
    source, target = _pair(source_id, target_id)
    schedule_lock.lock_for_offering(source)
    allowed = CONFIG | {"registrar.ScheduleSlot"}
    pending = [("registrar.CourseOffering", [source.pk])]
    seen = set()
    while pending:
        label, ids = pending.pop()
        key = (label, tuple(sorted(map(str, ids))))
        if key in seen:
            continue
        seen.add(key)
        for child, query in _children(label, ids):
            if child not in allowed or (label == "registrar.ScheduleSlot"):
                raise state.DuplicateError("empty_offering_has_content_or_history_" + child.lower().replace(".", "_"))
            values = list(query.select_for_update().values())
            if any(str(r.get("organization_id", state.ORG)) != state.ORG for r in values):
                raise state.DuplicateError("empty_configuration_tenant_changed")
            if child in ("registrar.Enrollment", "registrar.AssessmentComponent", "registrar.JournalShare"):
                if any(str(r["offering_id"]) != str(source.pk) for r in values):
                    raise state.DuplicateError("empty_configuration_cross_offering")
            if child == "registrar.JournalShare_enrollments":
                enrollment_ids = {r["enrollment_id"] for r in values}
                share_ids = {r["journalshare_id"] for r in values}
                if state.model("registrar.Enrollment").objects.filter(
                    pk__in=enrollment_ids, offering=source
                ).count() != len(enrollment_ids) or state.model("registrar.JournalShare").objects.filter(
                    pk__in=share_ids, offering=source
                ).count() != len(
                    share_ids
                ):
                    raise state.DuplicateError("empty_configuration_cross_offering")
            pending.append((child, [r["id"] for r in values]))
    slots = list(
        state.model("registrar.ScheduleSlot")
        .all_objects.select_for_update()
        .filter(
            organization_id=state.ORG,
            offering_id=source_id,
        )
        .select_related("offering")
    )
    if len(slots) > 128:
        raise state.DuplicateError("fixed_schedule_budget_exceeded")
    for slot in slots:
        if (
            schedule.effective_instructor_id(slot) != TEACHER
            or slot.kind not in ("lecture", "seminar")
            or slot.weekday not in range(1, 8)
            or slot.start_time >= slot.end_time
            or slot.week_type not in ("all", "odd", "even")
            or slot.room != slot.room.strip()
        ):
            raise state.DuplicateError("source_schedule_teacher_kind_or_shape_changed")
    return source, target, slots


def _signature(slot):
    return tuple(getattr(slot, key) for key in ("weekday", "start_time", "end_time", "room", "week_type", "kind")) + (
        schedule.effective_instructor_id(slot),
    )


def _conflicts(slot, offering, *, excluded):
    if schedule_conflicts.detect(
        organization=offering.organization,
        period_id=offering.period_id,
        group_id=offering.group_id,
        subject_id=offering.subject_id,
        offering_id=offering.pk,
        instructor_id=TEACHER,
        weekday=slot.weekday,
        start_time=slot.start_time,
        end_time=slot.end_time,
        week_type=slot.week_type,
        room=slot.room,
        kind=slot.kind,
        exclude_ids=excluded,
    ):
        raise state.DuplicateError("reviewed_schedule_conflict")


def plan(source_id, target_id):
    source, target, slots = validate_empty(source_id, target_id)
    # Modelling's reviewed subject correction happens in the same transaction;
    # its dry-run must check conflicts against that exact resulting identity.
    target = copy(target)
    target.subject_id = CANONICAL_SUBJECT
    if source.period.locked_at or not source.period.is_active:
        raise state.DuplicateError("reviewed_schedule_period_locked")
    active = [slot for slot in slots if not slot.is_deleted and not slot.is_parked]
    targets = list(
        state.model("registrar.ScheduleSlot")
        .all_objects.select_for_update()
        .filter(
            organization_id=state.ORG,
            offering_id=target_id,
        )
        .select_related("offering")
    )
    if len(targets) > 128:
        raise state.DuplicateError("fixed_schedule_budget_exceeded")
    signatures = [_signature(slot) for slot in active]
    if len(signatures) != len(set(signatures)):
        raise state.DuplicateError("ambiguous_source_schedule_signature")
    for index, slot in enumerate(active):
        if any(
            other.weekday == slot.weekday
            and schedule_conflicts.week_types_overlap(slot.week_type, other.week_type)
            and schedule_conflicts.time_ranges_overlap(slot.start_time, slot.end_time, other.start_time, other.end_time)
            for other in active[index + 1 :]
        ):
            raise state.DuplicateError("overlapping_source_schedule_slots")
    pairs = []
    for slot in active:
        exact = [s for s in targets if not s.is_deleted and not s.is_parked and _signature(s) == _signature(slot)]
        if len(exact) > 1:
            raise state.DuplicateError("ambiguous_target_schedule_signature")
        if not exact and any(not s.is_deleted and not s.is_parked and s.kind == slot.kind for s in targets):
            # A different timetable for an existing kind requires review even
            # when its dates/times do not overlap the duplicate's timetable.
            raise state.DuplicateError("reviewed_schedule_competing_kind_timetables")
        for other in targets:
            if other.is_deleted or other.is_parked or other in exact:
                continue
            if (
                other.weekday == slot.weekday
                and schedule_conflicts.week_types_overlap(slot.week_type, other.week_type)
                and schedule_conflicts.time_ranges_overlap(
                    slot.start_time, slot.end_time, other.start_time, other.end_time
                )
            ):
                raise state.DuplicateError("conflicting_target_schedule_slot")
        _conflicts(slot, target, excluded=[s.pk for s in active] + [s.pk for s in exact])
        pairs.append({"source": str(slot.pk), "target": str(exact[0].pk) if exact else None, "created": not exact})
    return pairs


@transaction.atomic
def apply(*, source_id, target_id, organization, user):
    pairs = plan(source_id, target_id)
    source, target = _pair(source_id, target_id)
    if str(target.subject_id) != CANONICAL_SUBJECT:
        raise state.DuplicateError("canonical_schedule_target_subject_required")
    Slot = state.model("registrar.ScheduleSlot")
    reason = f"AppliedMath reviewed duplicate schedule {source_id} → {target_id}"
    for pair in pairs:
        slot = Slot.objects.get(pk=pair["source"], organization=organization, offering=source)
        schedule_editor_actions.park_slot(actor=user, organization=organization, slot=slot, reason=reason)
    for pair in pairs:
        if not pair["created"]:
            continue
        slot = Slot.objects.get(pk=pair["source"], organization=organization, offering=source)
        replacement = schedule.create_slot(
            offering=target,
            created_by=user,
            instructor=target.instructor,
            **{
                field: getattr(slot, field)
                for field in ("weekday", "start_time", "end_time", "room", "week_type", "kind")
            },
        )
        pair["target"] = str(replacement.pk)
    return pairs


def preserved(*, before, after, pairs):
    old = {str(row["id"]): row for row in before}
    new = {str(row["id"]): row for row in after}
    created = {p["target"] for p in pairs if p["created"]}
    parked = {p["source"] for p in pairs}
    expected_sources = {
        pk
        for pk, row in old.items()
        if str(row["offering_id"]) in PAIRS and not row["is_parked"] and not row["is_deleted"]
    }
    if parked != expected_sources or len(parked) != len(pairs) or len({p["target"] for p in pairs}) != len(pairs):
        raise state.DuplicateError("schedule_receipt_pair_set_changed")
    if set(new) != set(old) | created:
        raise state.DuplicateError("unexpected_schedule_identity_change")
    for pk, row in old.items():
        allowed = PARK_FIELDS if pk in parked else set()
        if any(str(new[pk][key]) != str(value) for key, value in row.items() if key not in allowed):
            raise state.DuplicateError("existing_schedule_content_changed")
    Slot = state.model("registrar.ScheduleSlot")
    for pair in pairs:
        source, target = Slot.all_objects.select_related("offering").get(
            pk=pair["source"]
        ), Slot.all_objects.select_related("offering").get(pk=pair["target"])
        if (
            PAIRS.get(str(source.offering_id)) != str(target.offering_id)
            or pair["created"] != (pair["target"] not in old)
            or not source.is_parked
            or target.is_parked
            or target.is_deleted
            or _signature(source) != _signature(target)
        ):
            raise state.DuplicateError("schedule_replacement_not_exact")


def check_undo(*, source_id, target_id, before, pairs):
    source, _target, _slots = validate_empty(source_id, target_id)
    if pairs and (source.period.locked_at or not source.period.is_active):
        raise state.DuplicateError("reviewed_schedule_period_locked")
    preserved(before=before, after=slot_rows(source_id, target_id), pairs=pairs)
    excluded = [pair[key] for pair in pairs for key in ("source", "target")]
    for pair in pairs:
        slot = state.model("registrar.ScheduleSlot").objects.get(pk=pair["source"], offering=source)
        _conflicts(slot, source, excluded=excluded)


@transaction.atomic
def undo(*, source_id, target_id, before, pairs, organization, user):
    check_undo(source_id=source_id, target_id=target_id, before=before, pairs=pairs)
    source, _target = _pair(source_id, target_id)
    Slot = state.model("registrar.ScheduleSlot")
    reason = "AppliedMath reviewed duplicate schedule undo"
    for pair in pairs:
        if pair["created"]:
            slot = Slot.objects.get(pk=pair["target"], organization=organization, offering_id=target_id)
            if any(_children("registrar.ScheduleSlot", [slot.pk])):
                raise state.DuplicateError("undo_created_slot_has_history")
            schedule_editor_actions.park_slot(actor=user, organization=organization, slot=slot, reason=reason)
    originals = {str(row["id"]): row for row in before}
    # Pre-existing exact duplicate target slots are allowed ONLY because they
    # are immutable receipt rows. Other conflicts still prevent restoration.
    excluded = [p[key] for p in pairs for key in ("source", "target")]
    for pair in pairs:
        slot = Slot.objects.get(pk=pair["source"], organization=organization, offering=source)
        _conflicts(slot, source, excluded=excluded)
        row = originals[pair["source"]]
        values = {
            key: Slot._meta.get_field(key.removesuffix("_id") if key.endswith("_id") else key).to_python(row[key])
            for key in PARK_FIELDS
        }
        Slot.objects.filter(pk=slot.pk, organization=organization, offering=source).update(**values)
    current = {str(row["id"]): row for row in slot_rows(source_id, target_id)}
    for pk, row in originals.items():
        if state.digest(current[pk]) != state.digest(row):
            raise state.DuplicateError("undo_original_schedule_not_exact")
    if any(not current[p["target"]]["is_parked"] for p in pairs if p["created"]):
        raise state.DuplicateError("undo_created_schedule_still_active")
