"""Tapşırıq sətrinin SEMESTRİ (``period``) — tədris ili + fəsildən törəmə (2026-09-25).

KÖK SƏBƏB
---------
Plandan törədilən (``generation.generate_rows_from_plan``) və Excel ilə idxal
olunan sətirlərdə ``period`` HEÇ VAXT yazılmırdı; offering sinxronu isə
«fənn + semestr + qrup» tələb edir → plan kafedraya çatsa da fənn qruplara
DÜŞMÜRDÜ. Bu modul dövrü tapşırığın tədris ilindən və sətrin fəslindən seçir;
generator, təsdiq sinxronu və ``sync_plan_offerings`` backfill-i eyni qaydanı
işlədir.

QAYDA (``AcademicPeriod.academic_year`` = ``TeachingTask.academic_year``, «2026/2027»)
------------------------------------------------------------------------------------
1. ad DƏQİQ uyğun — TAPŞIRIQ kitabçasının adları (``task_workbook_parsing.PERIODS``:
   «Payız», «Yaz»; yay üçün «Yay»);
2. adda fəsil sözü: «payız/güz/fall», «yaz/bahar/spring», «yay/summer»;
3. adı başqa fəsli GÖSTƏRMİRSƏ — başlanğıc ayı (:func:`season_from_period`,
   sətir modalının ay qaydası).

Bərabər namizədlərdən aktiv, sonra ən erkən başlayan seçilir. Dövr tapılmasa
YARADILMIR: semestr təqvimi tədris şöbəsinin qərarıdır («Semestr açılışı» →
dövr yarat). Sətir boş qalır, hesabatda ``period_missing`` görünür; dövr
yarananda növbəti sinxron/backfill onu bağlayır.
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.utils import timezone

from ..constants import Season
from .task_workbook_parsing import PERIODS

#: Fəsil → kitabça adı (dəqiq uyğunluq ən yüksək prioritetdir).
EXACT_NAMES = {Season.FALL: PERIODS["fall"][0], Season.SPRING: PERIODS["spring"][0], Season.SUMMER: "Yay"}

#: Fəsil → addakı söz kökləri (``casefold`` sonrası sözün başlanğıcı ilə müqayisə).
_KEYWORDS = {
    Season.FALL: ("payız", "payiz", "güz", "guz", "fall", "autumn"),
    Season.SPRING: ("yaz", "bahar", "spring"),
    Season.SUMMER: ("yay", "summer"),
}


def season_from_period(period) -> str:
    """AcademicPeriod başlanğıc ayından fəsil: avqust–dekabr → Payız, yanvar–may → Yaz, iyun–iyul → Yay.

    QA 2026-09-05 (P3-20 / WORKLOAD-SCHEDULE-07): sətir modalında dövr seçilib
    ``season`` göndərilməyəndə fəsil buradan törədilir (əvvəl ``tasks.py``-da idi);
    qayda ``accounts`` bölməsindəki ``_season_label`` (ay-əsaslı) ilə EYNİDİR.
    """
    start_date = getattr(period, "start_date", None)
    if start_date is None:
        return Season.FALL
    month = start_date.month
    if month >= 8:
        return Season.FALL
    if month <= 5:
        return Season.SPRING
    return Season.SUMMER


def _named_seasons(name: str) -> set:
    words = re.findall(r"\w+", (name or "").casefold())
    return {season for season, roots in _KEYWORDS.items() if any(w.startswith(r) for w in words for r in roots)}


def _rank(period, season):
    """0 — dəqiq ad, 1 — addakı fəsil sözü, 2 — başlanğıc ayı; uyğun deyilsə ``None``."""
    name = (period.name or "").strip()
    if name.casefold() == EXACT_NAMES[season].casefold():
        return 0
    named = _named_seasons(name)
    if season in named:
        return 1
    if not named and season_from_period(period) == season:
        return 2
    return None


def normalize_year(academic_year: str) -> str:
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return AcademicPeriod.format_year(academic_year)


class PeriodResolver:
    """(tədris ili, fəsil) → ``AcademicPeriod`` — il başına BİR sorğu (keşlə)."""

    def __init__(self, organization):
        self.organization_id = getattr(organization, "pk", organization)
        self._years: dict = {}

    def periods_for(self, academic_year: str) -> list:
        year = normalize_year(academic_year)
        if year not in self._years:
            AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
            candidates = AcademicPeriod.objects.filter(
                organization_id=self.organization_id, academic_year__startswith=year[:4]
            )
            self._years[year] = [p for p in candidates if AcademicPeriod.format_year(p.academic_year) == year]
        return self._years[year]

    def resolve(self, academic_year: str, season: str):
        ranked = []
        for period in self.periods_for(academic_year):
            rank = _rank(period, season)
            if rank is not None:
                ranked.append((rank, not period.is_active, period.start_date, str(period.pk), period))
        return min(ranked)[-1] if ranked else None


def ensure_row_periods(rows, *, task, resolver=None, apply: bool = True) -> dict:
    """``period`` boş sətirlərə tapşırığın ili + sətrin fəsli üzrə dövr bağlayır.

    Yaddaşdakı sətir obyekti də yenilənir (çağıran eyni siyahı ilə davam edir).
    Bazada yazı ``period IS NULL`` şərti ilə gedir — paralel əl düzəlişi əzilmir.
    Qaytarır: ``{"period_set": n, "period_missing": m, "missing_seasons": {fəsil: say}}``.
    """
    from ..models import TeachingTaskRow

    resolver = resolver or PeriodResolver(task.organization_id)
    report = {"period_set": 0, "period_missing": 0, "missing_seasons": {}}
    for row in rows:
        if row.period_id:
            continue
        period = resolver.resolve(task.academic_year, row.season)
        if period is None:
            report["period_missing"] += 1
            report["missing_seasons"][row.season] = report["missing_seasons"].get(row.season, 0) + 1
            continue
        if apply:
            TeachingTaskRow.objects.filter(pk=row.pk, period__isnull=True).update(
                period=period, updated_at=timezone.now()
            )
        row.period = period
        report["period_set"] += 1
    return report


__all__ = [
    "EXACT_NAMES",
    "PeriodResolver",
    "ensure_row_periods",
    "normalize_year",
    "season_from_period",
]
