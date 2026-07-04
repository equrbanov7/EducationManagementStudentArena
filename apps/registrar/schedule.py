"""Dərs cədvəli (timetable) — services (U4).

Həftəlik təkrarlanan ``ScheduleSlot``-lar. Yeni slot yaradılanda konflikt
yoxlanır: eyni gün + vaxt üst-üstə düşməsi + (eyni qrup VƏ YA eyni müəllim VƏ YA
eyni auditoriya) → rədd. Üst/alt həftə (odd/even) bir-biri ilə konflikt etmir.
Görünüş rol-aware: tələbə öz qrupunun, müəllim öz slotlarının cədvəlini görür.
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import pgettext_lazy

from apps.registrar.models import ScheduleSlot, WeekType

# 1=Bazar ertəsi … 7=Bazar (ISO). Şablon üçün ad + qısa ad servisdən gəlir.
WEEKDAYS = (
    (1, pgettext_lazy("registrar.weekday", "Monday")),
    (2, pgettext_lazy("registrar.weekday", "Tuesday")),
    (3, pgettext_lazy("registrar.weekday", "Wednesday")),
    (4, pgettext_lazy("registrar.weekday", "Thursday")),
    (5, pgettext_lazy("registrar.weekday", "Friday")),
    (6, pgettext_lazy("registrar.weekday", "Saturday")),
    (7, pgettext_lazy("registrar.weekday", "Sunday")),
)
_TEACHING_WEEKDAYS = WEEKDAYS[:6]  # Bazar ertəsi–Şənbə (default görünüş)


def _week_types_overlap(a, b) -> bool:
    """Odd and even weeks never clash; anything else (incl. 'all') does."""
    return not ({a, b} == {WeekType.ODD, WeekType.EVEN})


def _time_ranges_overlap(start_a, end_a, start_b, end_b) -> bool:
    return start_a < end_b and start_b < end_a


class ScheduleConflict(Exception):
    """Raised when a new/updated slot clashes with an existing one."""

    def __init__(self, conflict):
        self.conflict = conflict
        super().__init__("schedule slot conflict")


@transaction.atomic
def create_slot(*, offering, weekday, start_time, end_time, room="", week_type=WeekType.ALL, created_by=None):
    """Create a timetable slot, rejecting group/instructor/room clashes."""
    room = (room or "").strip()
    conflict = find_conflict(
        organization=offering.organization,
        offering=offering,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        week_type=week_type,
        room=room,
    )
    if conflict is not None:
        raise ScheduleConflict(conflict)
    return ScheduleSlot.objects.create(
        organization=offering.organization,
        offering=offering,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        room=room,
        week_type=week_type,
        created_by=created_by,
    )


def find_conflict(*, organization, offering, weekday, start_time, end_time, week_type, room, exclude_id=None):
    """Return the first clashing slot (same group / instructor / room), or None."""
    room_norm = (room or "").strip().lower()
    candidates = (
        ScheduleSlot.objects.filter(organization=organization, weekday=weekday)
        .exclude(pk=exclude_id)
        .select_related("offering")
    )
    for slot in candidates:
        if not _time_ranges_overlap(start_time, end_time, slot.start_time, slot.end_time):
            continue
        if not _week_types_overlap(week_type, slot.week_type):
            continue
        same_group = offering.group_id and slot.offering.group_id == offering.group_id
        same_instructor = offering.instructor_id and slot.offering.instructor_id == offering.instructor_id
        same_room = room_norm and room_norm == (slot.room or "").strip().lower()
        if same_group or same_instructor or same_room:
            return slot
    return None


def _slots_for(queryset):
    return list(
        queryset.select_related("offering", "offering__subject", "offering__group", "offering__instructor").order_by(
            "weekday", "start_time"
        )
    )


def get_group_schedule(*, organization, group, period):
    """All slots for a group's offerings in a period (student view)."""
    return _slots_for(
        ScheduleSlot.objects.filter(organization=organization, offering__group=group, offering__period=period)
    )


def get_teacher_schedule(*, organization, teacher, period):
    """All slots the teacher teaches in a period (teacher view)."""
    return _slots_for(
        ScheduleSlot.objects.filter(organization=organization, offering__instructor=teacher, offering__period=period)
    )


def build_week_grid(slots, *, weekdays=_TEACHING_WEEKDAYS):
    """Group slots by weekday for the weekly-grid template."""
    by_day = {num: [] for num, _label in weekdays}
    for slot in slots:
        by_day.setdefault(slot.weekday, []).append(slot)
    return [{"weekday": num, "label": label, "slots": by_day.get(num, [])} for num, label in weekdays]
