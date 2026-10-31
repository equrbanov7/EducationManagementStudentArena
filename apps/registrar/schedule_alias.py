"""Tarixi slotun FK-sini dəyişmədən canonical açılışa cədvəl bərpası."""

from django.core.exceptions import ValidationError
from django.db import transaction

from . import schedule, schedule_editor_actions, schedule_lock, schedule_manage
from .models import ScheduleSlot

SLOT_FIELDS = ("weekday", "start_time", "end_time", "room", "week_type", "kind", "instructor_id")


def _guard(actor, organization, offering):
    if offering.organization_id != organization.pk or not schedule_manage.can_manage_offering(
        actor, organization, offering
    ):
        raise ValidationError("schedule_alias_permission_denied")
    if offering.period is None or offering.period.locked_at or not offering.period.is_active:
        raise ValidationError("schedule_alias_period_locked")
    schedule_lock.lock_for_offering(offering)


@transaction.atomic
def replace_alias_slot(*, actor, organization, slot, target, reason):
    """Mənbəni parkla; yalnız bütün tədris sahələri eyni target slotunu təkrar istifadə et."""
    _guard(actor, organization, slot.offering)
    _guard(actor, organization, target)
    if slot.organization_id != organization.pk or slot.is_parked or slot.is_deleted or not target.is_active:
        raise ValidationError("schedule_alias_slot_inactive")
    source = slot.offering
    if (source.subject_id, source.period_id, source.instructor_id) != (
        target.subject_id,
        target.period_id,
        target.instructor_id,
    ) or source.group_id == target.group_id:
        raise ValidationError("schedule_alias_identity_mismatch")
    exact = list(
        ScheduleSlot.objects.select_for_update().filter(
            organization=organization,
            offering=target,
            is_parked=False,
            **{field: getattr(slot, field) for field in SLOT_FIELDS},
        )
    )
    if len(exact) > 1:
        raise ValidationError("schedule_alias_ambiguous_target")
    schedule_editor_actions.park_slot(actor=actor, organization=organization, slot=slot, reason=reason)
    if exact:
        conflict = schedule.find_conflict(
            organization=organization,
            offering=target,
            exclude_id=exact[0].pk,
            **{field: getattr(slot, field) for field in SLOT_FIELDS},
        )
        if conflict is not None:
            raise schedule.ScheduleConflict(conflict)
        return exact[0], False
    replacement = schedule.create_slot(
        offering=target,
        created_by=actor,
        instructor=slot.instructor,
        **{field: getattr(slot, field) for field in SLOT_FIELDS if field != "instructor_id"},
    )
    schedule_editor_actions._audit(
        "create",
        actor=actor,
        organization=organization,
        slot=replacement,
        request=None,
        reason=reason,
        new={"replaces_slot_id": str(slot.pk)},
    )
    return replacement, True


@transaction.atomic
def restore_alias_slot(*, actor, organization, slot, reason):
    """Yalnız original FK-də, adi konflikt yoxlamasından sonra parkdan qaytar."""
    _guard(actor, organization, slot.offering)
    if not slot.is_parked or slot.is_deleted:
        raise ValidationError("schedule_alias_not_parked")
    conflict = schedule.find_conflict(
        organization=organization,
        offering=slot.offering,
        exclude_id=slot.pk,
        **{field: getattr(slot, field) for field in SLOT_FIELDS},
    )
    if conflict is not None:
        raise schedule.ScheduleConflict(conflict)
    slot.is_parked, slot.parked_at, slot.parked_by, slot.park_reason = False, None, None, ""
    slot.save(update_fields=["is_parked", "parked_at", "parked_by", "park_reason", "updated_at"])
    schedule_editor_actions._audit(
        "update",
        actor=actor,
        organization=organization,
        slot=slot,
        request=None,
        reason=reason,
        new={"restored_alias_slot": str(slot.pk)},
    )
