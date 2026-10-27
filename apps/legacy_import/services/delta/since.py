"""``--lessons-since`` — paketdən yalnız bu tarixdən (daxil) SONRAKI dərs/xana/mövzu sətirləri (RİM 2026-10-27).

Səbəb: 21.10 ~13:00 dump-ı 21.10 günortadan 23.10-a qədər köhnə sistemə yazılan ~1 150 dərsi daşımadı. Təzə dump
gələndə bütün paketi yenidən tətbiq etmək köhnə tarixlərdə artıq təmizlənmiş sütunlara («yalnız qb», köçürülmüş
tələbənin fantom sütunları) yenidən toxunardı. Bu süzgəc paketin ``points`` / ``lesson_dates`` / ``lesson_topics``
bölmələrini tarixə görə kəsir; qalan fazalar (fill-only, yeni sistem qalibdir) dəyişmir.

Tarix legacy jurnalın semestrindən (``period_for``) + ay/gün ilə ``lesson_date`` qaydası üzrə qurulur — dərs fazası ilə
eyni. Ay sütunu təqvim ayı olmayan xana (``im``/``im2``/``k1``… — yekun/təkrar/komponent) TARİXSİZDİR və atılır: bu
rejim yalnız dərs + xana üçündür. Paketin özü dəyişmir — süzülmüş surət qaytarılır.
"""

from __future__ import annotations

import datetime
from collections import Counter

from .resolve import Catalog, lesson_date

CALENDAR = {f"{month:02d}" for month in range(1, 13)} | {str(month) for month in range(1, 13)}


def _int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


class _Dates:
    def __init__(self, organization, bundle: dict):
        self.catalog = Catalog(organization)
        self.legacy_periods = {row["id"]: row for row in bundle.get("periods") or []}
        self.semestr_by_id = {row["id"]: row.get("semestr") for row in bundle.get("journals") or []}
        self.semestr_by_uniqid = {row["uniqid"]: row.get("semestr") for row in bundle.get("journals") or []}
        self._periods: dict = {}

    def _period(self, semestr):
        if semestr not in self._periods:
            legacy = self.legacy_periods.get(semestr)
            self._periods[semestr] = self.catalog.period_for(legacy) if legacy else None
        return self._periods[semestr]

    def date(self, semestr, month, day):
        period = self._period(semestr)
        if period is None or not month or not day:
            return None
        return lesson_date(period, month, day)


def restrict_to_since(bundle: dict, organization, since: datetime.date) -> tuple[dict, Counter]:
    """``(süzülmüş paket, saylar)`` — ``since``-dən əvvəlki və tarixsiz dərs/xana/mövzu sətirləri atılır."""
    dates = _Dates(organization, bundle)
    counts: Counter = Counter()

    def keep(prefix, date) -> bool:
        if date is None:
            counts[f"since.{prefix}_undated_dropped"] += 1
            return False
        if date < since:
            counts[f"since.{prefix}_before_dropped"] += 1
            return False
        counts[f"since.{prefix}_kept"] += 1
        return True

    points = []
    for row in bundle.get("points") or []:
        month = str(row.get("month_id") or "")
        date = None
        if month in CALENDAR:
            date = dates.date(
                dates.semestr_by_uniqid.get(row.get("journal_uniqid")), _int(month), _int(row.get("day_number"))
            )
        if keep("points", date):
            points.append(row)
    lesson_dates = [
        row
        for row in bundle.get("lesson_dates") or []
        if keep(
            "lesson_dates",
            dates.date(dates.semestr_by_id.get(row.get("journal_id")), _int(row.get("month")), _int(row.get("day"))),
        )
    ]
    lesson_topics = [
        row
        for row in bundle.get("lesson_topics") or []
        if keep(
            "lesson_topics",
            dates.date(
                dates.semestr_by_uniqid.get(row.get("journal_uniqid")), _int(row.get("month")), _int(row.get("day"))
            ),
        )
    ]
    restricted = dict(bundle)
    restricted.update(points=points, lesson_dates=lesson_dates, lesson_topics=lesson_topics)
    return restricted, counts


__all__ = ["restrict_to_since"]
