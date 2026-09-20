"""Həftəlik cədvəlin PLAN SAATINDAN çıxarılan forması (sahib 2026-09-21).

Qayda
-----
* Bir dərs = ``WEEK_SESSION_HOURS`` (2) akademik saat.  Sətirdə saat seçimi
  «—», 1 (yalnız qalıq üçün) və 2-dir — 3/4 seçilə bilməz.
* Sətir sayı özü tənzimlənir: hər dərs növü üzrə ``ceil(plan / 2)``, cədvəl
  bunların ən böyüyü qədərdir (15/15 → 8 sətir; 30/15 → 15 sətir).  Müəllim
  «+ Sətir əlavə et» ilə artıra bilər; artıq sətirlər «əlavə» damğası ilə
  qalır, xəbərdarlıq deyil.
* Planda saatı OLMAYAN növ (məs. laboratoriya 0) cədvəldə GÖRÜNMÜR — boş
  sütun doluluq yaratmasın.  Sətirlərdən birində həmin növün saatı varsa
  (köçürülmüş data) sütun yenə göstərilir ki, dəyər gizli qalmasın.
* Standart bölgü: növün saatı yuxarıdan aşağı 2-2-…-qalıq düzülür; yalnız
  həmin növün cəmi 0 olanda (təzə qaralama) tətbiq olunur — müəllimin yazdığı
  bölgüyə toxunulmur.

Plan yoxdursa (``plan_hours == {}``) heç bir qayda işləmir: 16 sətir, üç
sütun, köhnə davranış.
"""

from __future__ import annotations

from math import ceil

from .constants import LESSON_HOUR_KINDS, MAX_WEEK_ROWS, WEEK_SESSION_HOURS


def _int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _planned(plan_hours) -> dict:
    return {kind: _int((plan_hours or {}).get(kind)) for kind in LESSON_HOUR_KINDS}


def rows_for_hours(hours: int) -> int:
    """Növün saatı üçün lazım olan sətir sayı — ``ceil(saat / 2)``."""
    hours = _int(hours)
    return ceil(hours / WEEK_SESSION_HOURS) if hours else 0


def expected_week_rows(plan_hours) -> int:
    """Plandan çıxarılan sətir sayı; plan yoxdursa ``0`` (çağıran 16-ya düşür)."""
    planned = _planned(plan_hours)
    needed = max((rows_for_hours(hours) for hours in planned.values()), default=0)
    return min(needed, MAX_WEEK_ROWS)


def hour_choices(plan_hours=None) -> tuple:
    """Sətirdəki saat seçimləri: «—», qalıq (1) və dərs (2)."""
    return tuple(range(0, WEEK_SESSION_HOURS + 1))


def visible_hour_kinds(plan_hours, rows=()) -> tuple:
    """Cədvəldə göstərilən dərs növləri.

    Plan yoxdursa hamısı; varsa planda saatı olan növlər + sətirlərdə saatı
    olan növlər (köçürülmüş dəyər gizlənməsin).
    """
    planned = _planned(plan_hours)
    if not any(planned.values()):
        return tuple(LESSON_HOUR_KINDS)
    used = {kind for row in rows if isinstance(row, dict) for kind in LESSON_HOUR_KINDS if _int(row.get(kind))}
    return tuple(kind for kind in LESSON_HOUR_KINDS if planned[kind] or kind in used)


def default_distribution(hours: int) -> list:
    """Növün saatını sətirlərə düzür: ``[2, 2, …, qalıq]``."""
    hours = _int(hours)
    full, rest = divmod(hours, WEEK_SESSION_HOURS)
    out = [WEEK_SESSION_HOURS] * full
    if rest:
        out.append(rest)
    return out


def seed_missing_hours(rows, plan_hours) -> tuple:
    """Cəmi 0 olan növlərə standart bölgünü yazır → ``(yeni_sətirlər, dəyişdi)``.

    Sətir siyahısı lazım gələrsə UZADILIR (boş sətirlərlə); mövcud sətirlərin
    digər açarları (mövzu, nəticə, ``practical`` …) toxunulmaz qalır.
    """
    planned = _planned(plan_hours)
    rows = [dict(row) for row in (rows or []) if isinstance(row, dict)]
    changed = False
    for kind, hours in planned.items():
        if not hours:
            continue
        if any(_int(row.get(kind)) for row in rows):
            continue
        for index, value in enumerate(default_distribution(hours)):
            if index >= MAX_WEEK_ROWS:
                break
            while index >= len(rows):
                rows.append({"topic": "", "outcome": "", **{k: 0 for k in LESSON_HOUR_KINDS}})
            rows[index][kind] = value
            changed = True
    return rows, changed


__all__ = [
    "default_distribution",
    "expected_week_rows",
    "hour_choices",
    "rows_for_hours",
    "seed_missing_hours",
    "visible_hour_kinds",
]
