"""Dərs cədvəli (timetable) — services (U4).

Həftəlik təkrarlanan ``ScheduleSlot``-lar. Yeni slot yaradılanda konflikt
yoxlanır: eyni gün + vaxt üst-üstə düşməsi + (eyni qrup VƏ YA eyni müəllim VƏ YA
eyni auditoriya) → rədd. Üst/alt həftə (odd/even) bir-biri ilə konflikt etmir.
Görünüş rol-aware: tələbə öz qrupunun, müəllim öz slotlarının cədvəlini görür.
"""

from __future__ import annotations

import datetime

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
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


# ── Konkret həftə: tarixlər + üst/alt həftə (odd/even) + imtahanlar ───────────
#
# Həftəlik grid təkrarlanandır, amma tələbə "bu həftə hansı tarixlərdir, üst
# yoxsa alt həftədir, imtahan nə vaxtdır" bilmək istəyir. Konkret həftənin
# (offset ilə keçmiş/gələcək) real tarixlərini, üst/alt parityini və həmin
# həftədə keçirilən imtahanları hesablayırıq.


def _week_monday(offset: int = 0) -> datetime.date:
    today = timezone.localdate()
    return today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=offset)


def week_parity(period, monday: datetime.date) -> str:
    """Which teaching-week (üst/alt = odd/even) the given Monday falls in.

    Anchored to the period's start week when available so "1-ci həftə = üst"
    stays stable across the semester; otherwise falls back to the ISO week no."""
    start = getattr(period, "start_date", None)
    if isinstance(start, str):
        try:
            start = datetime.date.fromisoformat(start)
        except ValueError:
            start = None
    elif isinstance(start, datetime.datetime):
        start = start.date()
    if start:
        start_monday = start - datetime.timedelta(days=start.weekday())
        week_number = ((monday - start_monday).days // 7) + 1
    else:
        week_number = monday.isocalendar()[1]
    return WeekType.ODD if week_number % 2 == 1 else WeekType.EVEN


def build_week_context(period, *, offset: int = 0, weekdays=_TEACHING_WEEKDAYS) -> dict:
    """Concrete-week context: per-weekday real dates, parity, today, nav offsets."""
    monday = _week_monday(offset)
    today = timezone.localdate()
    dates = {num: monday + datetime.timedelta(days=num - 1) for num, _label in weekdays}
    parity = week_parity(period, monday)
    return {
        "offset": offset,
        "monday": monday,
        "sunday": monday + datetime.timedelta(days=6),
        "dates": dates,
        "parity": parity,
        "is_current": offset == 0,
        "today": today,
        "prev_offset": offset - 1,
        "next_offset": offset + 1,
    }


def get_week_exams(*, organization, course_ids, monday, author=None, weekdays=_TEACHING_WEEKDAYS):
    """Exams scheduled in the given week, grouped by weekday.

    Linked through the offering's LMS course (``course_id__in``) — a student sees
    the exams of the subjects they take; a teacher additionally sees the exams
    they authored. Resolved via the app registry so registrar keeps no static
    import of the exams module (module-boundary safe)."""
    course_ids = [cid for cid in (course_ids or []) if cid]
    if not course_ids and author is None:
        return {}
    saturday = monday + datetime.timedelta(days=(weekdays[-1][0] - 1))
    Exam = django_apps.get_model("exams", "Exam")

    scope = Q(course_id__in=course_ids) if course_ids else Q()
    if author is not None:
        scope = scope | Q(author=author)

    exams = (
        Exam.objects.filter(organization=organization, is_active=True, start_datetime__isnull=False)
        .filter(start_datetime__date__gte=monday, start_datetime__date__lte=saturday)
        .filter(scope)
        .select_related("course")
        .order_by("start_datetime")
    )
    by_day: dict = {}
    valid_days = {num for num, _label in weekdays}
    for exam in exams.distinct():
        local_start = timezone.localtime(exam.start_datetime)
        weekday = local_start.isoweekday()
        if weekday in valid_days:
            by_day.setdefault(weekday, []).append({"exam": exam, "start": local_start})
    return by_day


def build_week_view(slots, *, week_context, exams_by_day=None, weekdays=_TEACHING_WEEKDAYS):
    """Rich weekly view: each day carries its date, today flag, slots (with a
    ``this_week`` flag from üst/alt parity) and any exams that day."""
    exams_by_day = exams_by_day or {}
    parity = week_context["parity"]
    today = week_context["today"]
    dates = week_context["dates"]

    by_day: dict = {}
    for slot in slots:
        by_day.setdefault(slot.weekday, []).append(slot)

    days = []
    for num, label in weekdays:
        date = dates.get(num)
        day_slots = [
            {"slot": slot, "this_week": slot.week_type == WeekType.ALL or slot.week_type == parity}
            for slot in by_day.get(num, [])
        ]
        days.append(
            {
                "weekday": num,
                "label": label,
                "date": date,
                "is_today": date == today,
                "slots": day_slots,
                "exams": exams_by_day.get(num, []),
            }
        )
    return days
