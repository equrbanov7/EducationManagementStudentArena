"""Ekran 21 «Keçilmiş dərslər» — dövr üzrə KPI aqreqatı (`range_totals`).

Perf auditi 2026-09-13 F-13: `lessons_log.range_totals` dövrün BÜTÜN dərslərini
(rektorda 35 159 sətir) `values_list` ilə Python-a çəkib `note_state` ilə
təsnif edirdi (141 ms + döngü), xana aqreqatı (509 833 qeyd, 513 ms) isə hər
açılışda təkrarlanırdı — səhifə 1 038 ms. İndi «boş» / «gec» təsnifatı SQL-dədir
(`note_state` ilə EYNİ qayda) və nəticə sorğu-hash açarı ilə 300 s keşlənir.

Ayrıca modul: `lessons_log.py` modul-ölçü qapısında dondurulub (634 sətir) —
yeni kod ora əlavə edilmir; `lessons_log` bu adları geri-uyğunluq üçün
re-export edir (`service.range_totals` çağıranları dəyişmir).
"""

from __future__ import annotations

import datetime as _dt
import hashlib

from django.core.cache import cache
from django.db.models import Count, DateField, ExpressionWrapper, F, Min, Q, Sum, Value
from django.db.models.functions import TruncDate

from apps.registrar.models import AttendanceStatus, LessonMark

#: «Gec yazılıb» həddi — dizayn: «dərsdən 48 saat sonra».
LATE_AFTER_HOURS = 48

#: `range_totals` keşinin müddəti (saniyə) — `analytics_cache` ilə eyni siyasət:
#: hesabat səthidir, bir neçə dəqiqəlik köhnəlmə qəbul olunur.
TOTALS_CACHE_TTL = 300


def totals_cache_key(lessons_qs) -> str:
    """Dövr KPI-larının keş açarı — sorğunun ÖZÜ (əhatə + tarix aralığı +
    bütün filtrlər parametrlərlə birlikdə) hash-lənir, yəni fərqli əhatəli iki
    aktor heç vaxt eyni açarı paylaşmır (tenant/scope sızması yoxdur)."""
    raw = str(lessons_qs.order_by().values("id").query)
    return "registrar:lessons_log_totals:" + hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def range_totals(lessons_qs) -> dict:
    """Dövr üzrə KPI-lar — İKİ aqreqat sorğu (dərslər + xanalar), 300 s keş.

    Perf auditi 2026-09-13 F-13: əvvəl dövrün BÜTÜN dərsləri (rektorda
    35 159 sətir) `values_list` ilə Python-a çəkilib `note_state` ilə
    təsnif olunurdu (141 ms + döngü), xana aqreqatı (509 833 qeyd, 513 ms)
    isə hər açılışda təkrarlanırdı — səhifə 1 038 ms. İndi «boş» / «gec»
    təsnifatı SQL-dədir (`note_state` ilə EYNİ qayda: ilk xananın YERLİ
    tarixi dərs tarixindən 48 saatdan çox sonradırsa gec) və nəticə
    sorğu-hash açarı ilə keşlənir.
    """
    key = totals_cache_key(lessons_qs)
    cached = cache.get(key)
    if cached is not None:
        return dict(cached)
    totals = _compute_range_totals(lessons_qs)
    cache.set(key, totals, TOTALS_CACHE_TTL)
    return totals


def _compute_range_totals(lessons_qs) -> dict:
    # `note_state`: `(written - lesson_date) > 48 saat`, `written` tam TARİXDİR
    # (`localtime(first_mark).date()`) → fərq ≥ 3 gün ⇔ `written >= date + 3 gün`.
    # `TruncDate` cari saat qurşağında kəsir — `timezone.localtime` ilə eyni.
    late_from = ExpressionWrapper(
        F("date") + Value(_dt.timedelta(hours=LATE_AFTER_HOURS + 24)), output_field=DateField()
    )
    lesson_totals = (
        lessons_qs.order_by()
        .annotate(first_mark=Min("marks__created_at"))
        .annotate(first_mark_day=TruncDate("first_mark"), late_from=late_from)
        .aggregate(
            lessons=Count("id"),
            hours=Sum("hours"),
            empty=Count("id", filter=Q(first_mark__isnull=True)),
            late=Count("id", filter=Q(first_mark__isnull=False, first_mark_day__gte=F("late_from"))),
        )
    )
    total = int(lesson_totals["lessons"] or 0)
    hours = int(lesson_totals["hours"] or 0)
    empty = int(lesson_totals["empty"] or 0)
    late = int(lesson_totals["late"] or 0)

    attendance = LessonMark.objects.filter(lesson__in=lessons_qs.values("id")).aggregate(
        present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
        absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        excused=Count("id", filter=Q(status=AttendanceStatus.EXCUSED)),
        graded=Count("id", filter=Q(score__isnull=False)),
    )
    marked = int(attendance["present"] or 0) + int(attendance["absent"] or 0) + int(attendance["excused"] or 0)
    rate = int(round(int(attendance["present"] or 0) * 100 / marked)) if marked else 0
    return {
        "lessons": total,
        "hours": hours,
        "empty": empty,
        "late": late,
        "present": int(attendance["present"] or 0),
        "absent": int(attendance["absent"] or 0),
        "excused": int(attendance["excused"] or 0),
        "graded": int(attendance["graded"] or 0),
        "attendance_rate": rate,
    }


__all__ = ["LATE_AFTER_HOURS", "TOTALS_CACHE_TTL", "range_totals", "totals_cache_key"]
