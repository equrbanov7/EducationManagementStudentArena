"""Avtomatik dərs cədvəli modulunun PUBLIC fasadı (başqa modullar yalnız buradan istifadə edir).

* ``PERMISSION`` — kanonik icazə açarı (``schedule.manage``; registrar ilə eyni);
* ``home_url(period=None)`` — generatorun ana səhifəsi (kabinet keçidləri üçün);
* ``weekly_pattern(hours, weeks=15)`` — semestr saatı → (həftəlik, iki həftədən bir) cüt sayı.
"""

from __future__ import annotations

from django.urls import reverse

from .constants import PERMISSION
from .engine.patterns import weekly_pattern


def home_url(period=None) -> str:
    url = reverse("timetable:home")
    period_id = getattr(period, "pk", period)
    return f"{url}?period={period_id}" if period_id else url


__all__ = ["PERMISSION", "home_url", "weekly_pattern"]
