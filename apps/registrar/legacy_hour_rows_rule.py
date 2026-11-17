"""Köhnə sistemin «saat-saat» yazdığı dərs sətirlərinin tanınması — təmiz qayda (DB yoxdur).

Köhnə sistem 2023/2024 Yaz semestrində (və başqa semestrlərdə ayrı-ayrı müəllimlərdə) HƏR AKADEMİK SAATI ayrıca
sətir kimi saxlayırdı: eyni gün 15:35 və 16:25 — bir cütün iki saatı. Köçürmə hər sətri 2 saatlıq dərs yazdı
(``Lesson.hours`` defoltu), ona görə həmin jurnallarda «keçirilən saat» və qayıb saatı ikiqat oldu (MR-000482).

Fiziki əsas: bir cüt 80+ dəqiqədir, iki cüt arasında başlanğıc fərqi ən azı ~80 dəqiqə olur. Eyni gün eyni jurnalda
başlanğıcları :data:`WINDOW` dəqiqədən yaxın iki sətir iki AYRI 2 saatlıq cüt ola bilməz — onlar bir cütün içindədir.

Qayda (açılış üzrə, yalnız köçürmə dərsləri — çağıran süzür):

* **saat rejimi** — günlərarası ardıcıl fərqlərdən bir akademik saat aralığında (:data:`HOUR_GAP`) olanlar cüt
  aralığında olanlardan az deyil VƏ «hər sətir 1 saat» cəmi plana (``lesson_hours``) «yalnız yaxın sətirlər 1 saat»
  cəmindən YAXINDIR → jurnal bütövlükdə saat-saat yazılıb, 2 saatlıq bütün sətirlər 1 saat olur (tək sətirli günlər
  də: həmin jurnalda bir sətir = bir saat);
* **pəncərə rejimi** — qalan jurnallarda yalnız eyni gün :data:`WINDOW` dəqiqədən yaxın qonşusu olan sətirlər 1 saat
  olur (bir cütün içində iki-üç sətir); tək sətirli və cüt-cüt yazılmış günlərə toxunulmur;
* başqa hal — dəyişiklik yoxdur.

Saatı 2 olmayan sətir (1, 3, 4 …) hədəf deyil. Xanalar (iştirak/qayıb/bal) dəyişmir — yalnız sətrin saatı.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

#: Bir akademik saat aralığı (dəqiqə, daxil): 45 dəq dərs + 5–10 dəq fasilə; 2023/2024 Yaz-da 50/55/45 üstünlük təşkil edir.
HOUR_GAP = (40, 65)
#: Bu fərqdən (dəqiqə, daxil) yaxın iki sətir eyni cütün içindədir.
WINDOW = 65
#: Endirilən sətrin köhnə / yeni saatı.
OLD_HOURS = 2
NEW_HOURS = 1

HOUR_MODE = "hour"
WINDOW_MODE = "window"
NO_CHANGE = "none"


@dataclass(frozen=True)
class Row:
    """Köçürmə dərsi: ``id``, ``date``, ``start_time`` (boş ola bilər), ``hours``."""

    id: object
    date: object
    start_time: object
    hours: int


@dataclass
class Decision:
    mode: str = NO_CHANGE
    targets: set = field(default_factory=set)
    hour_gaps: int = 0
    pair_gaps: int = 0
    tiny_gap_rows: int = 0
    total_before: int = 0
    total_after: int = 0


def _minutes(value) -> int:
    return value.hour * 60 + value.minute


def _scan(rows) -> tuple:
    """``(hour_gaps, pair_gaps, window_ids, tiny_ids)`` — gün üzrə ardıcıl başlanğıc fərqləri."""
    by_day: dict = defaultdict(list)
    for row in rows:
        if row.start_time is not None:
            by_day[row.date].append(row)
    hour_gaps = pair_gaps = 0
    window: set = set()
    tiny: set = set()
    for day_rows in by_day.values():
        timed = sorted(day_rows, key=lambda row: (row.start_time, str(row.id)))
        for first, second in zip(timed, timed[1:]):
            gap = _minutes(second.start_time) - _minutes(first.start_time)
            if HOUR_GAP[0] <= gap <= HOUR_GAP[1]:
                hour_gaps += 1
            elif gap > WINDOW:
                pair_gaps += 1
            if gap <= WINDOW:
                window.update((first.id, second.id))
                if gap < HOUR_GAP[0]:
                    tiny.update((first.id, second.id))
    return hour_gaps, pair_gaps, window, tiny


def decide(rows, plan_hours) -> Decision:
    """Bir açılışın köçürmə dərsləri üçün qərar (:class:`Decision`)."""
    rows = list(rows)
    hour_gaps, pair_gaps, window, tiny = _scan(rows)
    total = sum(int(row.hours or 0) for row in rows)
    decision = Decision(hour_gaps=hour_gaps, pair_gaps=pair_gaps, total_before=total, total_after=total)
    plan = int(plan_hours or 0)
    all_one = sum(NEW_HOURS if row.hours == OLD_HOURS else int(row.hours or 0) for row in rows)
    windowed = sum(NEW_HOURS if row.id in window and row.hours == OLD_HOURS else int(row.hours or 0) for row in rows)
    if hour_gaps and hour_gaps >= pair_gaps and plan > 0 and abs(all_one - plan) < abs(windowed - plan):
        decision.mode = HOUR_MODE
        decision.targets = {row.id for row in rows if row.hours == OLD_HOURS}
        decision.total_after = all_one
    else:
        targets = {row.id for row in rows if row.id in window and row.hours == OLD_HOURS}
        if targets:
            decision.mode = WINDOW_MODE
            decision.targets = targets
            decision.total_after = windowed
    decision.tiny_gap_rows = len(decision.targets & tiny)
    return decision


__all__ = ["HOUR_GAP", "HOUR_MODE", "NEW_HOURS", "NO_CHANGE", "OLD_HOURS", "WINDOW", "WINDOW_MODE", "Decision", "Row"]
__all__ += ["decide"]
