"""Ekran 21 «Keçilmiş dərslər» — dövr, tədris ili / semestr fəsli və aralıq həlli.

``lessons_log.py``-dan ayrılıb (modul-ölçü qapısı, 2026-09-21): ``SEASON_*`` /
``RANGE_*`` sabitləri, ``resolve_range``, ``season_of``, ``period_catalog``,
``year_options``, ``select_periods``, ``window_for_periods`` və bölmə + CSV üçün
TƏK dövr mənbəyi olan ``resolve_selection``. ``lessons_log`` eyni adları yenidən
ixrac edir (``service.RANGE_LABELS`` və s. dəyişmir).
"""

from __future__ import annotations

import datetime as _dt

from django.utils import timezone
from django.utils.translation import pgettext_lazy

# i18n skaneri kontekst sabitini MODUL daxilində axtarır — yerli təyin.
_CTX = "registrar.lessons_log"


#: Semestr fəsli — `schedule.season_label` ilə EYNİ ay qaydası (tək mənbə
#: olmalıdır, amma registrar→schedule idxalı dövr yaradardı; qayda sadədir).
SEASON_AUTUMN = "autumn"
SEASON_SPRING = "spring"
SEASON_SUMMER = "summer"
SEASON_LABELS = (
    (SEASON_AUTUMN, pgettext_lazy(_CTX, "Payız")),
    (SEASON_SPRING, pgettext_lazy(_CTX, "Yaz")),
    (SEASON_SUMMER, pgettext_lazy(_CTX, "Yay")),
)

#: Filtr seçicilərində «hamısı» — BOŞ dəyər DEYİL: boş dəyər «default (cari
#: semestr)» deməkdir, `filter_bar.js` boş parametri URL-ə yazmır.
ALL = "all"


#: Dövr çipləri (dizayn `RANGES`).
RANGE_TODAY = "today"
RANGE_WEEK = "week"
RANGE_MONTH = "month"
RANGE_SEMESTER = "semester"
RANGE_YEAR = "year"
RANGE_CUSTOM = "custom"

RANGE_LABELS = (
    (RANGE_TODAY, pgettext_lazy(_CTX, "Bu gün")),
    (RANGE_WEEK, pgettext_lazy(_CTX, "Bu həftə")),
    (RANGE_MONTH, pgettext_lazy(_CTX, "Bu ay")),
    (RANGE_SEMESTER, pgettext_lazy(_CTX, "Semestr")),
    (RANGE_YEAR, pgettext_lazy(_CTX, "İl")),
    (RANGE_CUSTOM, pgettext_lazy(_CTX, "Seçilmiş aralıq")),
)


# --------------------------------------------------------------------------- #
# Dövr
# --------------------------------------------------------------------------- #


def _parse_date(value):
    try:
        return _dt.date.fromisoformat((value or "").strip())
    except (TypeError, ValueError):
        return None


def resolve_range(*, key: str, start_raw: str = "", end_raw: str = "", period=None, today=None) -> dict:
    """Seçilmiş dövr → ``{"key", "start", "end"}`` (hər ikisi daxil olmaqla)."""
    today = today or timezone.localdate()
    key = key if key in dict(RANGE_LABELS) else RANGE_SEMESTER
    if key == RANGE_CUSTOM:
        start = _parse_date(start_raw) or today - _dt.timedelta(days=30)
        end = _parse_date(end_raw) or today
        if end < start:
            start, end = end, start
        return {"key": key, "start": start, "end": end}
    if key == RANGE_TODAY:
        return {"key": key, "start": today, "end": today}
    if key == RANGE_WEEK:
        monday = today - _dt.timedelta(days=today.weekday())
        return {"key": key, "start": monday, "end": monday + _dt.timedelta(days=6)}
    if key == RANGE_MONTH:
        first = today.replace(day=1)
        return {"key": key, "start": first, "end": today}
    if key == RANGE_YEAR:
        # Akademik il: sentyabrdan başlayır (payız semestri) — təqvim ili deyil.
        year = today.year if today.month >= 9 else today.year - 1
        return {"key": key, "start": _dt.date(year, 9, 1), "end": _dt.date(year + 1, 8, 31)}
    start = getattr(period, "start_date", None) or today - _dt.timedelta(days=120)
    end = getattr(period, "end_date", None) or today
    return {"key": key, "start": start, "end": max(end, start)}


# --------------------------------------------------------------------------- #
# Tədris ili · semestr fəsli · dövr seçimi
# --------------------------------------------------------------------------- #


def season_of(period) -> str:
    """Dövrün fəsli — başlanğıc ayına görə (`schedule.season_label` qaydası)."""
    month = period.start_date.month if getattr(period, "start_date", None) else 9
    if month >= 8 or month == 12:
        return SEASON_AUTUMN
    if month <= 5:
        return SEASON_SPRING
    return SEASON_SUMMER


def period_catalog(organization) -> list:
    """Təşkilatın bütün akademik dövrləri — ən yenidən köhnəyə (TƏK sorğu)."""
    from django.apps import apps as django_apps

    academic_period = django_apps.get_model("organizations", "AcademicPeriod")
    return list(academic_period.objects.filter(organization=organization).order_by("-start_date", "-created_at"))


def year_options(periods) -> list:
    """`{"value": "2025/2026", "label": "2025/2026"}` — təkrarsız, yenidən köhnəyə."""
    from django.apps import apps as django_apps

    academic_period = django_apps.get_model("organizations", "AcademicPeriod")
    seen: list = []
    for period in periods:
        if period.academic_year and period.academic_year not in seen:
            seen.append(period.academic_year)
    return [{"value": year, "label": academic_period.format_year(year)} for year in seen]


def select_periods(periods, *, year: str, season: str, current) -> dict:
    """İl + fəsil seçimindən dövr dəstini qurur.

    Semantika (filtr panelinin «boş = default» qaydası ilə uyğun):
      * ``year``/``season`` BOŞ → cari dövrün ili/fəsli (default);
      * :data:`ALL` → həmin ox üzrə süzgəc yoxdur;
      * konkret dəyər → yalnız uyğun dövrlər.
    Qaytarır: ``{"periods": [...] | None, "year": <effektiv>, "season": <effektiv>}``.
    ``periods`` ``None`` olduqda dövr filtri tətbiq olunmur.
    """
    current_year = getattr(current, "academic_year", "") or ""
    current_season = season_of(current) if current is not None else ""
    year = (year or "").strip()
    season = (season or "").strip()
    known_seasons = {key for key, _label in SEASON_LABELS}
    if not year:
        year = current_year or ALL
    if not season or season not in known_seasons | {ALL}:
        season = current_season or ALL
    if year == ALL and season == ALL:
        return {"periods": None, "year": year, "season": season}
    selected = [
        period
        for period in periods
        if (year == ALL or period.academic_year == year) and (season == ALL or season_of(period) == season)
    ]
    return {"periods": selected, "year": year, "season": season}


def window_for_periods(periods) -> tuple:
    """Dövr dəstinin ümumi aralığı — (ilk başlanğıc, son bitmə) və ya (None, None)."""
    if not periods:
        return (None, None)
    return (min(p.start_date for p in periods), max(p.end_date for p in periods))


def resolve_selection(
    organization,
    *,
    current,
    year: str = "",
    season: str = "",
    legacy_period: str = "",
    range_key: str = "",
    start_raw: str = "",
    end_raw: str = "",
    periods=None,
    today=None,
) -> dict:
    """Bölmə VƏ CSV üçün EYNİ dövr/aralıq həlli (tək mənbə).

    Qaytarır::

        {"periods": [...] | None,   # dövr filtri (None → tətbiq olunmur)
         "year": …, "season": …,    # effektiv seçimlər (filtr paneli göstərir)
         "window": {"key","start","end"},
         "apply_period_filter": bool}

    Dövr filtri YALNIZ (a) il/fəsil/köhnə `period` açıq istənildikdə və ya
    (b) aralıq «Semestr» olduqda tətbiq olunur — «Bu ay»/«İl»/«Seçilmiş aralıq»
    TARİX aralığıdır (canlı QA: gizli dövr filtri boş ekran verirdi).
    """
    periods = period_catalog(organization) if periods is None else periods
    legacy = next((p for p in periods if legacy_period and str(p.id) == legacy_period), None)
    if legacy is not None:
        chosen = {"periods": [legacy], "year": legacy.academic_year, "season": season_of(legacy)}
    else:
        chosen = select_periods(periods, year=year, season=season, current=current)
    key = range_key if range_key in dict(RANGE_LABELS) else RANGE_SEMESTER
    if key == RANGE_SEMESTER:
        start, end = window_for_periods(chosen["periods"] or [])
        if start is None:
            fallback = resolve_range(key=RANGE_SEMESTER, period=current, today=today)
            start, end = fallback["start"], fallback["end"]
        window = {"key": key, "start": start, "end": max(end, start)}
    else:
        window = resolve_range(key=key, start_raw=start_raw, end_raw=end_raw, period=current, today=today)
    explicit = bool((year or "").strip() or (season or "").strip() or legacy is not None)
    return {
        "periods": chosen["periods"],
        "year": chosen["year"],
        "season": chosen["season"],
        "window": window,
        "apply_period_filter": chosen["periods"] is not None and (explicit or key == RANGE_SEMESTER),
        "catalog": periods,
        "explicit": explicit,
    }
