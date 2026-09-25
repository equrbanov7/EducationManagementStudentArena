"""Semestr saatı → həftəlik dərs nümunəsi (həftəlik / iki həftədən bir).

Qayda (sahib 2026-09-21, sillabus həftə planı ilə eyni): bir dərs = 2 saatlıq
cüt; semestrdə ``ceil(saat / 2)`` cüt keçirilir. Effektiv tədris həftəsi
(default 15) üzrə bölünüb yarım-cüt dəqiqliyi ilə yuvarlaqlaşdırılır:

====  =========  ===============================
saat  cüt/sem.   nümunə
====  =========  ===============================
15    8          iki həftədən bir (üst VƏ YA alt)
30    15         hər həftə 1
45    23         hər həftə 1 + iki həftədən bir 1
60    30         hər həftə 2
====  =========  ===============================

Yuvarlaqlaşdırma «yarımdan yuxarı» (banker's rounding YOX) — 1.5 → 2.
"""

from __future__ import annotations

import math

DEFAULT_WEEKS = 15
PAIR_HOURS = 2


def weekly_pattern(hours, *, weeks: int = DEFAULT_WEEKS, pair_hours: int = PAIR_HOURS) -> tuple[int, int]:
    """``(həftəlik, iki_həftədən_bir)`` hadisə sayı; saat yoxdursa ``(0, 0)``."""
    try:
        hours = float(hours or 0)
    except (TypeError, ValueError):
        return (0, 0)
    if hours <= 0:
        return (0, 0)
    weeks = max(1, int(weeks or DEFAULT_WEEKS))
    pairs = math.ceil(hours / max(1, int(pair_hours or PAIR_HOURS)))
    halves = max(1, int(math.floor(pairs * 2 / weeks + 0.5)))
    return halves // 2, halves % 2


def weekly_load(hours, *, weeks: int = DEFAULT_WEEKS) -> float:
    """Həftəlik orta cüt sayı (iki həftədən bir = 0.5) — ilkin yoxlama üçün."""
    weekly, biweekly = weekly_pattern(hours, weeks=weeks)
    return weekly + 0.5 * biweekly


__all__ = ["DEFAULT_WEEKS", "PAIR_HOURS", "weekly_load", "weekly_pattern"]
