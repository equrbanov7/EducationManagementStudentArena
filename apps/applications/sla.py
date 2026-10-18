"""Cavab müddəti — İŞ GÜNÜ hesabı (Bazar ertəsi–Cümə, bayramlar çıxılır).

Dizayn §6: «SLA / overdue is computed in working days». ``holidays`` arqumenti:

* təşkilatın iş təqvimi (``organizations.public.work_calendar(org)``, 2026-10-19) — bayram və qeyri-iş
  günləri iş günü DEYİL, «iş günü köçürməsi» (iş günü elan olunmuş şənbə/bazar) iş günüdür;
* və ya sadə tarix çoxluğu (köhnə imza, testlər) — yalnız çıxılan günlər.

Təqvimi qurmaq üçün :func:`calendar_for` — ``organization`` yoxdursa ``None`` (yalnız həftə sonu çıxılır).
"""

from __future__ import annotations

from datetime import date, timedelta

#: 0 = Bazar ertəsi … 4 = Cümə (``date.weekday()``).
_WEEKEND = {5, 6}


def calendar_for(organization):
    """Təşkilatın iş təqvimi (keşli, bir obyekt daxilində hər il bir oxu); təşkilat yoxdursa ``None``."""
    if organization is None:
        return None
    from apps.organizations.public import work_calendar

    return work_calendar(organization)


def is_working_day(day: date, holidays=None) -> bool:
    if holidays is not None and hasattr(holidays, "is_working_day"):
        return holidays.is_working_day(day)
    if day.weekday() in _WEEKEND:
        return False
    return day not in (holidays or ())


def add_working_days(start: date, days: int, holidays=None) -> date:
    """``start``-dan sonrakı ``days``-ci İŞ GÜNÜ.

    ``days <= 0`` üçün ``start``-ın özü qaytarılır. Başlanğıc günün özü
    sayılmır — «3 iş günü müddət» = start-dan sonrakı 3-cü iş günü.
    """
    if days <= 0:
        return start
    current = start
    remaining = int(days)
    while remaining > 0:
        current += timedelta(days=1)
        if is_working_day(current, holidays):
            remaining -= 1
    return current


def working_days_between(start: date, end: date, holidays=None) -> int:
    """``start`` (daxil deyil) ilə ``end`` (daxil) arasındakı iş günü sayı.

    ``end < start`` olarsa MƏNFİ dəyər qaytarılır (nə qədər gecikib/qalıb
    hesablamaları üçün simmetrik davranış).
    """
    if end == start:
        return 0
    step = 1 if end > start else -1
    lower, upper = (start, end) if end > start else (end, start)
    count = 0
    current = lower
    while current < upper:
        current += timedelta(days=1)
        if is_working_day(current, holidays):
            count += 1
    return count * step


def sla_banner(*, due_on: date, sla_days: int, today: date, is_open: bool, status_label: str, holidays=None) -> dict:
    """Detal panelinin SLA zolağı üçün hazır məlumat (dizayn §4.7).

    ``tone``: ``ontime`` | ``overdue`` | ``closed``; ``days`` müsbət ədəddir.
    """
    if not is_open:
        return {
            "tone": "closed",
            "days": 0,
            "sla_days": int(sla_days or 0),
            "status_label": status_label,
        }
    if due_on is None:
        return {"tone": "ontime", "days": 0, "sla_days": int(sla_days or 0), "status_label": status_label}
    remaining = working_days_between(today, due_on, holidays)
    if remaining >= 0:
        return {"tone": "ontime", "days": remaining, "sla_days": int(sla_days or 0), "status_label": status_label}
    return {"tone": "overdue", "days": abs(remaining), "sla_days": int(sla_days or 0), "status_label": status_label}


__all__ = ["add_working_days", "calendar_for", "is_working_day", "sla_banner", "working_days_between"]
