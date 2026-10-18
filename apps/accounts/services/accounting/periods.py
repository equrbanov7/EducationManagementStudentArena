"""«Mühasibatlıq» — semestr təqvimi və planın AYLARA bölünməsi (saf funksiyalar, sorğu yoxdur).

SEMESTR
-------
Semestr = (tədris ili, fəsil) cütü. Fəsil dövrün başlanğıc ayından gəlir — dərs yükü modulunun qaydası ilə
EYNİ (``workload.services.plan_calendar.season_from_period``): avqust–dekabr → payız, yanvar–may → yaz,
iyun–iyul → yay. Eyni ilin eyni fəslində bir neçə ``AcademicPeriod`` ola bilər (ayrı proqram təqvimləri) —
hamısı bir semestrdə birləşir: başlanğıc = ən erkən ``start_date``, son = ən gec ``end_date``.

TƏDRİS PƏNCƏRƏSİ
----------------
Hər dövr üçün dərs günləri ``start_date``-dən imtahan sessiyasının əvvəlinə qədərdir
(``exam_session_start - 1 gün``; sessiya qeyd olunmayıbsa və ya dövrdən kənardırsa — ``end_date``).
Semestrin pəncərəsi = dövrlərin pəncərələrinin birləşməsi.

PLANIN AYLARA BÖLGÜSÜ (QAYDA)
-----------------------------
Müəllimin semestr planı (lecture + seminar + lab, ``TeacherAssignment.hours``) tədris pəncərəsinin İŞ
GÜNLƏRİNƏ (bazar ertəsi – cümə, ``TEACHING_WEEKDAYS``) mütənasib bölünür::

    ayın planı = semestr planı × (pəncərənin həmin aya düşən iş günləri / pəncərənin bütün iş günləri)

Nəticə 0,1 saata yuvarlaqlaşdırılır; yuvarlaq qalığı pəncərənin SON ayına yazılır ki, aylıq planların cəmi
semestr planına DƏQİQ bərabər olsun. İmtahan sessiyası ayları (pəncərədən sonra) plan almır, amma həmin
aylarda keçirilmiş dərs (məs. kompensasiya) faktda görünür. Bayram günləri nəzərə alınmır (sahib qərarı
gözlənilir — təqvim reyestri yoxdur).

Sərbəst tarix aralığı («… -dan … -dək») eyni aylıq paylardan iş günlərinə görə kəsilir — bax ``ranges.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from . import constants as C


@dataclass(frozen=True)
class Semester:
    key: str
    year: str
    season: str
    period_ids: tuple
    start: date
    end: date
    windows: tuple  # ((başlanğıc, son), …) — dərs günləri
    is_current: bool

    @property
    def label(self) -> str:
        return f"{self.year} · {C.SEASON_LABELS.get(self.season, self.season)}"


def season_of(start_date) -> str:
    """Dövrün fəsli — ``workload.services.plan_calendar.season_from_period`` ilə eyni qayda."""
    if start_date is None:
        return C.SEASON_FALL
    if start_date.month >= 8:
        return C.SEASON_FALL
    if start_date.month <= 5:
        return C.SEASON_SPRING
    return C.SEASON_SUMMER


def _teaching_window(period) -> tuple[date, date]:
    start, end = period.start_date, period.end_date
    exam = getattr(period, "exam_session_start", None)
    if exam and start < exam <= end:
        end = exam - timedelta(days=1)
    return start, max(start, end)


def semesters(periods, *, today: date | None = None) -> list[Semester]:
    """Dövrlərdən semestr siyahısı — yenidən köhnəyə."""
    today = today or date.today()
    groups: dict[tuple[str, str], list] = {}
    for period in periods:
        if not period.academic_year or not period.start_date or not period.end_date:
            continue
        groups.setdefault((period.academic_year, season_of(period.start_date)), []).append(period)
    out = []
    for (year, season), items in groups.items():
        out.append(
            Semester(
                key=f"{year}|{season}",
                year=year,
                season=season,
                period_ids=tuple(str(item.pk) for item in items),
                start=min(item.start_date for item in items),
                end=max(item.end_date for item in items),
                windows=tuple(sorted(_teaching_window(item) for item in items)),
                is_current=any(item.is_current for item in items),
            )
        )
    out.sort(key=lambda item: item.start, reverse=True)
    return out


def default_semester(items: list[Semester], *, today: date | None = None) -> Semester | None:
    """Cari dövrün semestri; yoxdursa bu günü əhatə edən; o da yoxdursa ən sonuncu başlamış."""
    today = today or date.today()
    for item in items:
        if item.is_current:
            return item
    for item in items:
        if item.start <= today <= item.end:
            return item
    started = [item for item in items if item.start <= today]
    return started[0] if started else (items[-1] if items else None)


def month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def month_bounds(key: str) -> tuple[date, date]:
    year, month = (int(part) for part in key.split("-"))
    first = date(year, month, 1)
    following = date(year + (month == 12), month % 12 + 1, 1)
    return first, following - timedelta(days=1)


def month_label(key: str) -> str:
    year, month = (int(part) for part in key.split("-"))
    return f"{C.MONTH_NAMES[month]} {year}"


def months(semester: Semester) -> list[str]:
    """Semestrin ayları (başlanğıcdan sona, imtahan ayları daxil) — «YYYY-MM»."""
    keys, cursor = [], date(semester.start.year, semester.start.month, 1)
    while cursor <= semester.end:
        keys.append(month_key(cursor.year, cursor.month))
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return keys


def default_month(semester: Semester, *, today: date | None = None) -> str:
    """Bu günün ayı (semestr daxilindədirsə); semestr bitibsə son ay; başlamayıbsa ilk ay."""
    today = today or date.today()
    keys = months(semester)
    if not keys:
        return ""
    current = month_key(today.year, today.month)
    if current in keys:
        return current
    return keys[-1] if today > semester.end else keys[0]


def teaching_day_set(semester: Semester) -> set[date]:
    """Pəncərənin iş günləri (dövr pəncərələri üst-üstə düşsə də gün bir dəfə sayılır)."""
    days: set[date] = set()
    for start, end in semester.windows:
        cursor = start
        while cursor <= end:
            if cursor.weekday() in C.TEACHING_WEEKDAYS:
                days.add(cursor)
            cursor += timedelta(days=1)
    return days


def teaching_days(semester: Semester) -> dict[str, int]:
    """Ay → pəncərənin həmin aya düşən iş günləri."""
    counts: dict[str, int] = {}
    for day in teaching_day_set(semester):
        key = month_key(day.year, day.month)
        counts[key] = counts.get(key, 0) + 1
    return counts


def apportion(total_hours, day_counts: dict[str, int]) -> dict[str, float]:
    """Semestr planını aylara bölür (modul sənədindəki qayda) — cəm DƏQİQ ``total_hours``-dır."""
    total_days = sum(day_counts.values())
    if not total_days:
        return {}
    tenths = int(round(float(total_hours or 0) * 10))
    keys = sorted(day_counts)
    shares, used = {}, 0
    for key in keys[:-1]:
        share = tenths * day_counts[key] // total_days
        shares[key] = share / 10
        used += share
    shares[keys[-1]] = (tenths - used) / 10
    return shares


__all__ = [
    "Semester",
    "apportion",
    "default_month",
    "default_semester",
    "month_bounds",
    "month_key",
    "month_label",
    "months",
    "season_of",
    "semesters",
    "teaching_day_set",
    "teaching_days",
]
