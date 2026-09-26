"""Jurnal siyahısı — dərs cədvəlinə görə sıralama (sahib tələbi 2026-09-27).

«Dərs cədvəli varsa, İNDİ keçilən (və ya ən yaxın) dərsin jurnalı siyahının ən
yuxarısında görünsün; sıra gün və saata görə dəyişsin.» Bu modul:

* :func:`next_occurrences` — hər açılış üçün cədvəldəki NÖVBƏTİ (və ya hazırda
  gedən) dərs: tarix + saat + növ + vəziyyət (``now`` / ``today`` / ``tomorrow`` /
  ``later``). Gün qaydası ana səhifə kartı ilə EYNİDİR (``dashboard_data.lessons_on``:
  həftə günü + üst/alt paritet + dövr sərhədi; parklanmış/silinmiş slotlar xaric).
  Bitmiş dərs :data:`GRACE` qədər «bu gün» sayılır — müəllim dərsdən dərhal sonra
  davamiyyəti yazmağa girəndə sətir hələ yuxarıdadır.
* :func:`order_by_schedule` — cədvəldə yaxın dərsi olan açılışları (ən yaxından
  uzağa) BİRİNCİ qoyur, qalanları əvvəlki sırada saxlayır. Sıralama DB tərəfdə
  (``Case``) gedir ki, səhifələmə düzgün qalsın.

Kimin cədvəli: ``reference_user_id`` — adi müəllimdə özü, geniş görünüşdə müəllim
süzgəci seçilibsə HƏMİN müəllim. Slotun effektiv müəllimi ``schedule.effective_instructor_id``
qaydasıdır: slotun öz müəllimi, boşdursa jurnal sahibi (bölünmüş tədrisdə başqasının
seminarı müəllimin siyahısını qarışdırmır).

Sorğu profili: TƏK sorğu (slotlar + açılışın dövrü), hesablama Python-da — müəllimin
açılışları onlarla ölçülür, üfüq 15 gündür.
"""

from __future__ import annotations

import datetime as _dt

from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone
from django.utils.translation import pgettext

from . import dashboard_data

_CTX = "registrar.journal_list_schedule"

#: Axtarış üfüqü (gün) — üst/alt həftəli slot ən gec 14 gündən bir keçir.
HORIZON_DAYS = 15
#: Bitmiş dərs bu müddət ərzində hələ «bu gün» sayılır (davamiyyət yazmaq üçün).
GRACE = _dt.timedelta(minutes=30)


def _weekday_name(day) -> str:
    names = (
        pgettext(_CTX, "Bazar ertəsi"),
        pgettext(_CTX, "Çərşənbə axşamı"),
        pgettext(_CTX, "Çərşənbə"),
        pgettext(_CTX, "Cümə axşamı"),
        pgettext(_CTX, "Cümə"),
        pgettext(_CTX, "Şənbə"),
        pgettext(_CTX, "Bazar"),
    )
    return names[day.weekday()]


def _label(state, day, today) -> str:
    if state == "now":
        return pgettext(_CTX, "İndi")
    if state == "today":
        return pgettext(_CTX, "Bu gün")
    if state == "tomorrow":
        return pgettext(_CTX, "Sabah")
    if (day - today).days < 7:
        return _weekday_name(day)
    return f"{_weekday_name(day)}, {day:%d.%m}"


def _slots_by_offering(offering_qs, reference_user_id, kind=""):
    from .models import ScheduleSlot

    mine = Q(instructor_id=reference_user_id) | Q(instructor_id__isnull=True, offering__instructor_id=reference_user_id)
    slots = (
        ScheduleSlot.objects.filter(offering_id__in=offering_qs.order_by().values("pk"), is_parked=False)
        .filter(mine)
        .select_related("offering__period")
        .order_by("weekday", "start_time")
    )
    if kind:
        slots = slots.filter(kind=kind)
    grouped: dict = {}
    for slot in slots:
        grouped.setdefault(slot.offering_id, []).append(slot)
    return grouped


def _first_occurrence(slots, period, now):
    """Açılışın ``now``-dan sonrakı (və ya hazırda gedən) İLK dərsi → dict / None."""
    tz = timezone.get_current_timezone()
    today = now.date()
    for offset in range(HORIZON_DAYS):
        day = today + _dt.timedelta(days=offset)
        if period is not None and period.end_date and day > period.end_date:
            return None
        for slot in dashboard_data.lessons_on(slots, day, period=period):
            start = timezone.make_aware(_dt.datetime.combine(day, slot.start_time), tz)
            end = timezone.make_aware(_dt.datetime.combine(day, slot.end_time), tz)
            if end + GRACE <= now:
                continue
            if start <= now < end:
                state = "now"
            elif offset == 0:
                state = "today"
            elif offset == 1:
                state = "tomorrow"
            else:
                state = "later"
            return {
                "state": state,
                "start": start,
                "day": day,
                "time": f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}",
                "kind": slot.get_kind_display(),
                "room": (slot.room or "").strip(),
                "label": _label(state, day, today),
            }
    return None


def next_occurrences(offering_qs, reference_user_id, *, kind="", now=None) -> dict:
    """``{offering_id: occurrence}`` — yalnız üfüq daxilində dərsi olan açılışlar."""
    if not reference_user_id:
        return {}
    now = timezone.localtime(now or timezone.now())
    out = {}
    for offering_id, slots in _slots_by_offering(offering_qs, reference_user_id, kind).items():
        occurrence = _first_occurrence(slots, slots[0].offering.period, now)
        if occurrence is not None:
            out[offering_id] = occurrence
    return out


def ranked_ids(occurrences) -> list:
    """Açılış id-ləri cədvəl yaxınlığı sırası ilə: hazırda gedən dərs → ən yaxın başlanğıc."""
    return [
        offering_id
        for offering_id, occ in sorted(
            occurrences.items(), key=lambda item: (item[1]["state"] != "now", item[1]["start"], str(item[0]))
        )
    ]


def order_by_schedule(qs, occurrences, fallback_order):
    """Cədvəldə yaxın dərsi olan açılışlar birinci (yaxından uzağa), qalanı ``fallback_order`` ilə."""
    ids = ranked_ids(occurrences)
    if not ids:
        return qs.order_by(*fallback_order)
    rank = Case(
        *[When(pk=offering_id, then=Value(index)) for index, offering_id in enumerate(ids)],
        default=Value(len(ids)),
        output_field=IntegerField(),
    )
    return qs.annotate(_jl_schedule_rank=rank).order_by("_jl_schedule_rank", *fallback_order)


def attach(offerings, occurrences) -> None:
    """Səhifənin açılışlarına ``next_lesson`` bağlayır (şablon nişanı üçün; yoxdursa ``None``)."""
    for offering in offerings:
        offering.next_lesson = occurrences.get(offering.pk)
