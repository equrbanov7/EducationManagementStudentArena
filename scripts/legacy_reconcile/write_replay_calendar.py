"""Calendar/time classification helpers for the offline write replay."""

from __future__ import annotations

import re

SUBSTEP_DAY_ABSENT = "source_day_absent"
SUBSTEP_DAY_PRESENT_TIME_DIFFERS = "source_day_present_time_differs"
SUBSTEP_IMPOSSIBLE_DATE = "source_slot_impossible_date"
SUBSTEP_LEAP_DEPENDENT_DATE = "source_slot_leap_dependent_date"
SUBSTEP_UNREADABLE_TIME = "source_slot_unreadable_time"
SUBSTEP_SLOT_NOT_MATERIALISED = "source_slot_not_materialised"

READABLE_TIME = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

# Fevral üçün uzun il daxil; il mənbədə olmadığı üçün 29 fevral ayrıca səbətdir.
_MAX_DAY = {
    1: 31,
    2: 29,
    3: 31,
    4: 30,
    5: 31,
    6: 30,
    7: 31,
    8: 31,
    9: 30,
    10: 31,
    11: 30,
    12: 31,
}


def is_readable_time(text: str) -> bool:
    """Saat mətni həqiqi divar saatıdırmı (``80:30`` → xeyr)."""

    return bool(READABLE_TIME.match(text or ""))


def source_slot_reason(month, day, time_text: str) -> str:
    """Mənbədə olub hədəfdə materiallaşmayan slotun dəqiq səbəbi."""

    try:
        month_number, day_number = int(month), int(day)
    except (TypeError, ValueError):
        return SUBSTEP_IMPOSSIBLE_DATE
    limit = _MAX_DAY.get(month_number)
    if limit is None or day_number < 1 or day_number > limit:
        return SUBSTEP_IMPOSSIBLE_DATE
    if month_number == 2 and day_number == 29:
        return SUBSTEP_LEAP_DEPENDENT_DATE
    if not is_readable_time(time_text):
        return SUBSTEP_UNREADABLE_TIME
    return SUBSTEP_SLOT_NOT_MATERIALISED


__all__ = [
    "SUBSTEP_DAY_ABSENT",
    "SUBSTEP_DAY_PRESENT_TIME_DIFFERS",
    "SUBSTEP_IMPOSSIBLE_DATE",
    "SUBSTEP_LEAP_DEPENDENT_DATE",
    "SUBSTEP_SLOT_NOT_MATERIALISED",
    "SUBSTEP_UNREADABLE_TIME",
    "is_readable_time",
    "source_slot_reason",
]
