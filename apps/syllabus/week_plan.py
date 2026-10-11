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

    Plan (yük) yoxdursa hamısı; varsa YALNIZ yükdə saatı olan növlər — sahib 2026-10-12: «seminar və ya lab
    yoxdursa göstərmə, yazmaq olmasın; yükdə nə gəlibsə o görünsün». Köçürülmüş sətirlərdə qalan artıq
    dəyər sütunu geri qaytarmır (saxlananda ``drop_unplanned_hours`` onu sıfırlayır). ``rows`` uyğunluq üçün qalır.
    """
    planned = _planned(plan_hours)
    if not any(planned.values()):
        return tuple(LESSON_HOUR_KINDS)
    if _strict():
        return tuple(kind for kind in LESSON_HOUR_KINDS if planned[kind])
    # Açar söndürülüdə əvvəlki qayda: sətirlərdə saatı olan növ də görünür (köçürülmüş dəyər gizlənməsin).
    used = {kind for row in rows if isinstance(row, dict) for kind in LESSON_HOUR_KINDS if _int(row.get(kind))}
    return tuple(kind for kind in LESSON_HOUR_KINDS if planned[kind] or kind in used)


def _strict() -> bool:
    from core.academic_rules import syllabus_hours_from_load

    return syllabus_hours_from_load()


def drop_unplanned_hours(rows, plan_hours) -> tuple:
    """Yükdə saatı OLMAYAN növlərin sətir saatlarını sıfırlayır → ``(sətirlər, dəyişdi)``.

    Plan boşdursa (yük/plan tapılmayıb — müəllim saatı özü seçir) və ya RİM açarı `syllabus.hours_from_load`
    söndürülübsə heç nə dəyişmir.
    """
    planned = _planned(plan_hours)
    if not any(planned.values()) or not _strict():
        return list(rows or []), False
    changed = False
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            out.append(row)
            continue
        row = dict(row)
        for kind in LESSON_HOUR_KINDS:
            if not planned[kind] and _int(row.get(kind)):
                row[kind] = 0
                changed = True
        out.append(row)
    return out, changed


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


def fit_rows_to_hours(rows, plan_hours) -> tuple:
    """Kopyalanmış həftəlik cədvəli HƏDƏFİN saatına uyğunlaşdırır → ``(sətirlər, dəyişdi)``.

    «Kopyala və uyğunlaşdır» (2026-10-08) üçündür:

    * cəmi hədəfin plan saatına BƏRABƏR olan növə toxunulmur (müəllimin bölgüsü qalır);
    * fərqli növ standart bölgü ilə (2-2-…-qalıq) yuxarıdan aşağı yenidən düzülür,
      lazım olsa boş sətir əlavə edilir (sətir sayı ``ceil(saat / 2)``);
    * hədəfdə saatı OLMAYAN növün sətir saatları sıfırlanır.

    Mövzu, nəticə və digər açarlar toxunulmaz qalır — artıq mövzu sətirləri SİLİNMİR
    (müəllim özü birləşdirir; tamamlanma qaydası onları göstərir).  Plan boşdursa heç
    nə dəyişmir.
    """
    planned = _planned(plan_hours)
    rows = [dict(row) for row in (rows or []) if isinstance(row, dict)]
    if not any(planned.values()):
        return rows, False
    changed = False
    for kind, hours in planned.items():
        if sum(_int(row.get(kind)) for row in rows) == hours:
            continue
        changed = True
        spread = default_distribution(hours)[:MAX_WEEK_ROWS]
        while len(rows) < len(spread):
            rows.append({"topic": "", "outcome": "", **{k: 0 for k in LESSON_HOUR_KINDS}})
        for index, row in enumerate(rows):
            row[kind] = spread[index] if index < len(spread) else 0
    return rows, changed


__all__ = [
    "default_distribution",
    "drop_unplanned_hours",
    "expected_week_rows",
    "fit_rows_to_hours",
    "hour_choices",
    "rows_for_hours",
    "seed_missing_hours",
    "visible_hour_kinds",
]
