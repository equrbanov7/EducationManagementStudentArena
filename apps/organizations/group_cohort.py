"""Akademik qrupun QƏBUL İLİ (kohortu) — qrup ``OrgUnit``-in adından / ayarından (2026-10-19).

Əvvəl bu köməkçi ``apps.accounts.services.student_groups``-da idi; semestr açılışı (registrar), dərs yükü
(workload) və sillabus saatı da qrupun ÖZ kohort planını seçməli olduğu üçün (sahib qaydası 2026-10-19)
aşağı qata — ``organizations``-a köçürüldü (``registrar`` / ``workload`` ``accounts``-ı import edə bilməz,
``scripts/module_deps.py``). ``student_groups.group_admission_year`` buradan RE-EXPORT olunur — davranış eynidir.

İki funksiya:

* :func:`group_admission_year` — ADDAN (QKU şablonu), şablonsuz addan isə yalnız etibarlı ayar;
* :func:`group_cohort_year` — semestr açılışının qaydası: əvvəl ``settings.admission_year`` (reyestrdə açıq
  yazılmış dəyər), yoxdursa addan. Köçürülmüş («legacy» damğalı) qrupun ayarı İDXAL ilidir, kohort deyil
  (2026-09-19 tapıntısı) — ona görə həmin qrupda ayar nəzərə alınmır, ad işləyir.
"""

from __future__ import annotations

import re
from datetime import date

_GROUP_YEAR_RE = re.compile(r"^(?:\d/)?(\d{3,4})")


def _settings_of(unit) -> dict:
    settings = getattr(unit, "settings", None)
    return settings if isinstance(settings, dict) else {}


def _int_year(raw) -> int | None:
    try:
        value = int(str(raw).strip()) if raw not in (None, "") else 0
    except (TypeError, ValueError):
        return None
    return value if 1900 < value < 2200 else None


def group_admission_year(unit) -> int | None:
    """Qrupun qəbul ili: ad şablonundan; şablonsuz addan yalnız etibarlı ayar.

    QKU şablonu: «236 K» / «536 Bİ» / «2236 M» / «3/336 F» — rəqəm blokunun SON
    rəqəmi ilin son rəqəmidir (233 → 2023 … 236 → 2026). Onilliyi cari ildən
    götürürük (on ildən köhnə qruplar reyestrdə qalmır).
    """
    settings = _settings_of(unit)
    match = _GROUP_YEAR_RE.match(str(getattr(unit, "name", "") or "").strip())
    if not match:
        # Ad şablonsuz qrup: ayar YALNIZ köçürmə («legacy») damğası yoxdursa etibarlıdır —
        # köçürülmüş qruplarda `admission_year` idxal ili ilə doldurulub (2026-09-19 tapıntısı).
        raw = settings.get("admission_year") if "legacy" not in settings else None
        try:
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None
    digit = int(match.group(1)[-1])
    today = date.today()
    decade = today.year // 10 * 10
    year = decade + digit
    return year if year <= today.year + 1 else year - 10


def group_cohort_year(unit) -> int | None:
    """Kohort planının açarı: ``settings.admission_year`` (legacy olmayan), yoxdursa addan; bilinmirsə ``None``."""
    settings = _settings_of(unit)
    if "legacy" not in settings:
        explicit = _int_year(settings.get("admission_year"))
        if explicit:
            return explicit
    return group_admission_year(unit)


__all__ = ["group_admission_year", "group_cohort_year"]
