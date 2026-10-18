"""«Mühasibatlıq» — sərbəst TARİX ARALIĞI rejimi (sahib 2026-10-19): «… -dan … -dək».

ARALIĞIN PLANI (QAYDA)
----------------------
Ay rejimində semestr planı ayların arasında tədris pəncərəsinin iş günlərinə mütənasib bölünür
(``periods.apportion`` — ayların cəmi semestr planına DƏQİQ bərabərdir). Aralıq rejimi HƏMİN aylıq paylardan
çıxır və qismən düşən ayı iş günlərinə görə kəsir::

    aralığın planı = Σ (ayın plan payı × aralığa düşən iş günləri / ayın pəncərədəki iş günləri)

Hər növ (mühazirə / seminar / laboratoriya) ayrıca hesablanır, nəticə 0,1 saata yuvarlaqlaşdırılır.

Niyə bu qayda (alternativ — «semestr planı × aralığın iş günləri / semestrin iş günləri»):
riyazi olaraq eynidir, amma aylıq payların yuvarlaq qalığı son aya yazıldığı üçün birbaşa düstur ay
rejimindən 0,1 saat fərqlənə bilərdi. Bu qaydada TAM düşən ay ay rejimindəki rəqəmi, bütün semestr isə
semestr planını DƏQİQ verir — hesabat rejimləri bir-birini təsdiqləyir.

Pəncərədən kənar günlər (imtahan sessiyası, şənbə-bazar) plan almır; həmin günlərdə keçirilmiş dərs faktda
görünür. Bayram günləri nəzərə alınmır (ay rejimi ilə eyni).

DOĞRULAMA
---------
Aralıq seçilmiş semestrin hüdudlarına (ilk dövrün başlanğıcı — son dövrün sonu) sıxılır; başlanğıc sondan
sonradırsa yerləri dəyişdirilir; tanınmayan tarix defolta düşür. Aralıq semestrlə HEÇ kəsişmirsə (məs. semestr
dəyişdirilib, köhnə tarixlər URL-də qalıb) sıxılmır — bir günlük aralıq yaranardı — defolt aralıq götürülür
(``NOTE_OUTSIDE``). Hər düzəliş istifadəçiyə qeyd kimi göstərilir
(``NOTE_*``). Defolt aralıq: semestrin başlanğıcından bu günədək (semestr bitibsə — sonunadək; hələ başlamayıbsa —
bütün semestr).
"""

from __future__ import annotations

from datetime import date, timedelta

from . import constants as C
from .periods import Semester, apportion, month_key, teaching_day_set

NOTE_CLAMPED = "clamped"
NOTE_SWAPPED = "swapped"
NOTE_INVALID = "invalid"
NOTE_OUTSIDE = "outside"
NOTES = (NOTE_CLAMPED, NOTE_SWAPPED, NOTE_INVALID, NOTE_OUTSIDE)


def parse_iso(raw) -> date | None:
    """«YYYY-MM-DD» (tarix sahəsinin dəyəri) və ya «gg.aa.iiii» → ``date``; pozuq → ``None``."""
    text = str(raw or "").strip()
    if not text or len(text) > 10:
        return None
    try:
        if "." in text:
            day, month, year = (int(part) for part in text.split("."))
            return date(year, month, day)
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def default_range(semester: Semester, *, today: date | None = None) -> tuple[date, date]:
    """Semestrin başlanğıcından min(bu gün, semestrin sonu)-dək; semestr hələ başlamayıbsa — bütün semestr."""
    today = today or date.today()
    if today < semester.start:
        return semester.start, semester.end
    return semester.start, min(today, semester.end)


def normalize_range(raw_from, raw_to, semester: Semester, *, today: date | None = None):
    """(başlanğıc, son, qeydlər) — semestr hüdudlarına sıxılmış, başlanğıc ≤ son."""
    notes: list[str] = []
    default_start, default_end = default_range(semester, today=today)
    start, end = parse_iso(raw_from), parse_iso(raw_to)
    if (raw_from and start is None) or (raw_to and end is None):
        notes.append(NOTE_INVALID)
    start = start or default_start
    end = end or default_end
    if start > end:
        start, end = end, start
        notes.append(NOTE_SWAPPED)
    if end < semester.start or start > semester.end:
        # Semestrlə kəsişmə yoxdur: sıxmaq semestrin kənar gününə bir günlük aralıq verərdi.
        return default_start, default_end, (*notes, NOTE_OUTSIDE)
    clamped_start = min(max(start, semester.start), semester.end)
    clamped_end = min(max(end, semester.start), semester.end)
    if (clamped_start, clamped_end) != (start, end):
        notes.append(NOTE_CLAMPED)
    return clamped_start, clamped_end, tuple(notes)


def range_day_counts(semester: Semester, start: date, end: date) -> dict[str, int]:
    """Ay → pəncərənin [start, end]-ə düşən iş günləri (ay rejimindəki ``teaching_days`` ilə eyni gün dəsti)."""
    counts: dict[str, int] = {}
    for day in teaching_day_set(semester):
        if start <= day <= end:
            key = month_key(day.year, day.month)
            counts[key] = counts.get(key, 0) + 1
    return counts


def month_parts(hours, day_counts: dict[str, int], range_counts: dict[str, int]) -> dict[str, float]:
    """Bir növün aralıqdakı plan payı AYLAR üzrə (yuvarlaqlaşdırılmamış) — modul sənədindəki qayda."""
    shares = apportion(hours, day_counts)
    return {
        key: shares[key] * range_counts[key] / day_counts[key]
        for key in shares
        if day_counts.get(key) and range_counts.get(key)
    }


def range_plan_kinds(planned_kinds: dict, day_counts: dict[str, int], range_counts: dict[str, int]) -> dict:
    """{növ: aralığın planı (0,1 saat)}."""
    return {
        kind: round(float(sum(month_parts(hours, day_counts, range_counts).values())), 1) if hours else 0.0
        for kind, hours in planned_kinds.items()
    }


def range_months(start: date, end: date) -> list[str]:
    """Aralığın kəsişdiyi aylar — «YYYY-MM», xronoloji."""
    keys, cursor = [], date(start.year, start.month, 1)
    while cursor <= end:
        keys.append(month_key(cursor.year, cursor.month))
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return keys


def month_slice(key: str, start: date, end: date) -> tuple[date, date, bool]:
    """(ayın aralığa düşən ilk günü, son günü, qismənmi)."""
    year, month = (int(part) for part in key.split("-"))
    first = date(year, month, 1)
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    lo, hi = max(first, start), min(last, end)
    return lo, hi, (lo, hi) != (first, last)


def fmt_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def range_label(start: date, end: date) -> str:
    return f"{fmt_date(start)} – {fmt_date(end)}"


def kinds_zero() -> dict:
    return dict.fromkeys(C.KIND_KEYS, 0)


__all__ = [
    "NOTES",
    "NOTE_CLAMPED",
    "NOTE_INVALID",
    "NOTE_OUTSIDE",
    "NOTE_SWAPPED",
    "default_range",
    "fmt_date",
    "kinds_zero",
    "month_parts",
    "month_slice",
    "normalize_range",
    "parse_iso",
    "range_day_counts",
    "range_label",
    "range_months",
    "range_plan_kinds",
]
