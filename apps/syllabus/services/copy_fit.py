"""«Kopyala və uyğunlaşdır» — mənbənin dərs saatı jurnalın saatından FƏRQLİDİRSƏ (sahib 2026-11-26).

Sahib: «müəllim köhnə sistemdən sillabusu götürəndə dərs saatları uyğun gəlmirsə səssiz tətbiq olunmasın —
dərs saatlarının fərqli olduğu xəbərdarlığı çıxsın, ya da kəsilmiş/uzadılmış tətbiq olunsun».

Qərar (bir yerdə — dialoqun ön baxışı və yazı yolu EYNİ funksiyanı çağırır, müştəriyə etibar edilmir):

* ``same``           — mənbə və hədəf saatı MƏLUM və EYNİDİR → köhnə davranış (``fit_rows_to_hours``; müəllimin
  əlavə sətirləri toxunulmaz);
* ``differ``         — saatlar fərqlidir → qaralama HƏDƏFİN plan saatını alır, həftəlik cədvəl hədəfin sətir sayına
  gətirilir (``week_plan.fit_week_rows``: artıq sətirlər sondan kəsilir, çatışmayan boş sətir əlavə olunur);
* ``source_unknown`` — mənbənin saatı bilinmir (köhnə sistemdən köçürülmüş, versiyada saat yoxdur) → ``differ`` kimi;
* ``target_unknown`` — jurnalın rəsmi saatı tapılmayıb → uyğunlaşdırmaq üçün ölçü yoxdur, cədvəl olduğu kimi
  (müəllim saatı redaktorda seçir — köhnə davranış).

Mənbənin saatı ``sharing.source_hours``-dur (kafedranın düzəlişi → qüvvədə olan versiya → cari versiya → mənbə
jurnalın rəsmi saatı) — paylaşımın saat qaydası ilə eyni.
"""

from __future__ import annotations

from ..constants import SectionKey
from ..models import SyllabusSection
from ..week_plan import expected_week_rows, fit_rows_to_hours, fit_week_rows
from .reuse_rules import normalize_hours
from .sharing import source_hours

SAME = "same"
DIFFER = "differ"
SOURCE_UNKNOWN = "source_unknown"
TARGET_UNKNOWN = "target_unknown"
FITTED_STATES = frozenset({DIFFER, SOURCE_UNKNOWN})


def _rows(data) -> list:
    rows = (data or {}).get("rows") if isinstance(data, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def week_row_counts(versions) -> dict:
    """``{version_id: həftəlik cədvəlin sətir sayı}`` — bütün versiyalar üçün TƏK sorğu."""
    ids = [version.pk for version in versions if version is not None]
    if not ids:
        return {}
    found = SyllabusSection.objects.filter(version_id__in=ids, section_id=SectionKey.WEEK.value)
    return {version_id: len(_rows(data)) for version_id, data in found.values_list("version_id", "data")}


def copy_state(source_hours_value, target_hours) -> str:
    source, target = normalize_hours(source_hours_value), normalize_hours(target_hours)
    if not target:
        return TARGET_UNKNOWN
    if not source:
        return SOURCE_UNKNOWN
    return SAME if source == target else DIFFER


def copy_plan(*, source_hours_value, target_hours, row_count: int) -> dict:
    """Dialoqun ön baxışı: ``{state, fit, source_hours, target_hours, source_rows, target_rows, cut, added}``."""
    state = copy_state(source_hours_value, target_hours)
    target = normalize_hours(target_hours)
    expected = expected_week_rows(target) if state in FITTED_STATES else 0
    row_count = max(int(row_count or 0), 0)
    return {
        "state": state,
        "fit": state in FITTED_STATES,
        "source_hours": sum(normalize_hours(source_hours_value).values()),
        "target_hours": sum(target.values()),
        "source_rows": row_count,
        "target_rows": expected or expected_week_rows(target),
        "cut": max(row_count - expected, 0) if expected else 0,
        "added": max(expected - row_count, 0) if expected else 0,
    }


def fit_copied_week(rows, *, source, target_hours, source_fallback=None) -> tuple:
    """Yazı yolu: kopyalanan cədvəl → ``(sətirlər, dəyişdi, plan)`` — ön baxışla EYNİ qərar."""
    state = copy_state(source_hours(source, source_fallback), target_hours)
    if state in FITTED_STATES:
        fitted, info = fit_week_rows(rows, target_hours)
        changed = bool(info["cut"] or info["added"]) or fitted != [dict(row) for row in _rows({"rows": rows})]
        return fitted, changed, {"state": state, **info}
    fitted, changed = fit_rows_to_hours(rows, target_hours)
    return fitted, changed, {"state": state}


__all__ = [
    "DIFFER",
    "FITTED_STATES",
    "SAME",
    "SOURCE_UNKNOWN",
    "TARGET_UNKNOWN",
    "copy_plan",
    "copy_state",
    "fit_copied_week",
    "week_row_counts",
]
