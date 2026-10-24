"""«Gec yazılıb» — TƏK qayda, TƏK yer (sahib 2026-10-25).

Sahib: «o "Gec yazılıb"ı hər yerdən sil, çünki datanı inteqrasiya etmişik. Full bazada kimdəsə olmasın o, gələn
həftədən ola bilər.» «Gec» status SAXLANILMIR (model sahəsi / bayraq / cədvəl yoxdur) — hər açılışda
``Lesson.date`` ilə ilk yeni-sistem xanasının ``created_at``-ından hesablanır; ona görə data əmri LAZIM DEYİL:
tənzimləmə tarixi dəyişən kimi nəticə dəyişir.

QAYDA (iki forma, EYNİ cavab):

* dərsin TARİXİ :func:`late_check_from`-dan (``journal.late_check_from``, defolt 2026-10-26) ƏVVƏLDİRSƏ — dərs
  heç vaxt «gec» deyil (nişan, say, KPI, ixrac);
* əks halda mövcud qayda: ilk xananın YERLİ tarixi dərs tarixindən :data:`LATE_AFTER_HOURS` saatdan çox sonradır.

Python forması — :func:`is_late` (``lessons_log.note_state``, sətir/ixrac); SQL forması — :func:`late_q`
(``lessons_log_totals``, KPI aqreqatı). Başqa heç bir yerdə «gec» hesablanmır.
"""

from __future__ import annotations

import datetime as _dt

from django.db.models import F, Q

from core.runtime_settings_journal_late import late_check_from

#: «Gec yazılıb» həddi — dizayn: «dərsdən 48 saat sonra».
LATE_AFTER_HOURS = 48


def is_late(*, lesson_date: _dt.date, written_date: _dt.date, check_from: _dt.date | None = None) -> bool:
    """Dərs ``lesson_date``, ilk yeni-sistem xanası ``written_date`` (yerli tarix) — «gec»dirmi."""
    if lesson_date < (check_from or late_check_from()):
        return False
    return (written_date - lesson_date) > _dt.timedelta(hours=LATE_AFTER_HOURS)


def late_q(*, check_from: _dt.date) -> Q:
    """:func:`is_late`-in SQL forması. Sorğuda ``first_mark`` (``Min``) və ``first_mark_day`` / ``late_from``
    annotasiyaları olmalıdır (bax ``lessons_log_totals._compute_range_totals``)."""
    return Q(first_mark__isnull=False, date__gte=check_from, first_mark_day__gte=F("late_from"))


__all__ = ["LATE_AFTER_HOURS", "is_late", "late_check_from", "late_q"]
