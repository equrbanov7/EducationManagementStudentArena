"""«Bu gün / növbəti dərslər» kartının ORTAQ qurucusu (tələbə + müəllim).

Köhnə kart iki səhv edirdi (sahib, 2026-09-25):

* «Növbəti» yalnız CARİ həftənin qalan günlərinə baxırdı — cümə günü «yoxdur»
  yazırdı, halbuki bazar ertəsi dərs var;
* müəllimin «Həftədə» rəqəmi bütün slotları sayırdı — üst/alt həftə slotları
  iki dəfə düşürdü.

İndi tarix hesabı ``apps.registrar.public.dashboard_data``-dadır (``lessons_on``,
``next_lesson_day``, ``week_lesson_count`` — paritet + dövr sərhədi); bu modul
yalnız GÖRÜNÜŞÜ qurur.  Qayda: bu gün dərs QALIBSA bu günün bütün dərsləri
(keçənlər solğun, gedən «indi» nişanı ilə), qalmayıbsa növbəti dərs gününün
dərsləri göstərilir.  ƏLAVƏ SORĞU YOXDUR — çağıran slot siyahısını ötürür.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

from .dashboard_widgets import day_label, stat, time_range

_CTX = "accounts.dashboard"

#: Bir gündə göstərilən dərs sətirlərinin həddi (gündə adətən 3–4 cüt olur).
LESSON_ROW_LIMIT = 6


def parity_label(parity) -> str:
    """Üst/alt həftə — ``WeekType`` dəyərləri (``odd``/``even``) mətn kimi müqayisə olunur."""
    if parity == "odd":
        return pgettext(_CTX, "üst həftə")
    if parity == "even":
        return pgettext(_CTX, "alt həftə")
    return ""


def _journal_url(slot, viewer_id=None) -> str:
    """«Jurnalı aç» ünvanı; BAŞQASININ jurnalındakı slotu aparan müəllimə boş (sorğusuz).

    Bölünmüş tədris (2026-09-25): seminarı jurnal sahibindən başqa müəllim aparırsa
    (``ScheduleSlot.instructor``) jurnal yenə sahibinindir — giriş qaydası dəyişmir, ona görə
    baxan jurnal sahibi deyilsə keçid verilmir. ``viewer_id`` verilməyibsə siyahı baxanın ÖZ
    cədvəlidir (``schedule.get_teacher_schedule``) — baxan slotun effektiv müəllimidir."""
    offering_id = getattr(slot, "offering_id", None)
    if not offering_id:
        return ""
    override = getattr(slot, "instructor_id", None)
    if override:
        viewer = override if viewer_id is None else viewer_id
        if str(getattr(slot.offering, "instructor_id", None)) != str(viewer):
            return ""
    return reverse("registrar:journal_detail", args=[offering_id])


def _lesson_row(slot, *, with_group: bool, now=None, journal_link: bool = False, viewer_id=None) -> dict:
    offering = slot.offering
    subject = getattr(offering, "subject", None)
    meta = [str(slot.get_kind_display() or "")]
    if slot.room:
        meta.append(pgettext(_CTX, "aud. %(room)s") % {"room": slot.room})
    group = getattr(offering, "group", None) if with_group else None
    if group is not None:
        meta.append(group.name)
    is_now = now is not None and slot.start_time <= now < slot.end_time
    row = {
        "time": time_range(slot),
        "title": getattr(subject, "name", "") or "—",
        "meta": " · ".join(part for part in meta if part),
        "is_past": now is not None and slot.end_time <= now,
        "is_now": is_now,
    }
    # «Jurnalı aç» (UNEC müqayisəsi P1-1, 2026-09-25) — müəllim sətrindən həmin açılışın
    # jurnalına; jurnalın üstündə bu günün slotu «Aktivləşdir» ilə açılır. Sorğu YOXDUR.
    url = _journal_url(slot, viewer_id) if journal_link else ""
    if url:
        row["url"] = url
    return row


def build(slots, *, period, today, now, with_group: bool, journal_links: bool = False, viewer_id=None) -> dict:
    """Kartın rəqəmləri + sətirləri.

    Qaytarır: ``stats`` (bu gün / növbəti / bu həftə), ``rows``, ``caption``
    («Bu gün · …» və ya «Növbəti dərs günü · …»), ``empty`` (sətir yoxdursa
    səbəbi izah edən mətn). ``viewer_id`` — «Jurnalı aç» keçidi üçün baxan (bax :func:`_journal_url`).
    """
    from apps.registrar.public import dashboard_data

    today_slots = dashboard_data.lessons_on(slots, today, period=period)
    # `now` verilməyibsə (məs. sırf tarix üzrə çağırış) bu günün bütün dərsləri «qalıb» sayılır.
    remaining = [slot for slot in today_slots if now is None or slot.end_time > now]
    next_day, next_slots = dashboard_data.next_lesson_day(slots, period=period, today=today)

    if remaining:
        shown, caption = today_slots, pgettext(_CTX, "Bu gün · %(day)s") % {"day": day_label(today)}
        rows = [
            _lesson_row(slot, with_group=with_group, now=now, journal_link=journal_links, viewer_id=viewer_id)
            for slot in shown[:LESSON_ROW_LIMIT]
        ]
        upcoming = remaining[0]
        next_value = time_range(upcoming).split("–")[0]
        ongoing = now is not None and upcoming.start_time <= now
        next_note = pgettext(_CTX, "indi gedir") if ongoing else pgettext(_CTX, "bu gün")
    elif next_slots:
        caption = pgettext(_CTX, "Növbəti dərs günü · %(day)s") % {"day": day_label(next_day)}
        rows = [
            _lesson_row(slot, with_group=with_group, journal_link=journal_links, viewer_id=viewer_id)
            for slot in next_slots[:LESSON_ROW_LIMIT]
        ]
        next_value = time_range(next_slots[0]).split("–")[0]
        next_note = day_label(next_day)
    else:
        caption, rows = "", []
        next_value, next_note = pgettext(_CTX, "yoxdur"), ""

    week_count = dashboard_data.week_lesson_count(slots, period=period, today=today)
    parity = dashboard_data.week_parity(period, today) if dashboard_data.period_contains(period, today) else ""
    if not slots:
        empty = ""
    elif today_slots and not remaining and not next_slots:
        empty = pgettext(_CTX, "Bu günün dərsləri bitib, bu semestrdə qarşıda dərs qalmayıb.")
    else:
        empty = pgettext(_CTX, "Bu semestrdə qarşıda dərs qalmayıb.")
    return {
        "stats": [
            stat(pgettext(_CTX, "Bu gün"), len(today_slots), pgettext(_CTX, "dərs")),
            stat(pgettext(_CTX, "Növbəti"), next_value, next_note),
            stat(pgettext(_CTX, "Bu həftə"), week_count, parity_label(parity) or pgettext(_CTX, "dərs")),
        ],
        "rows": rows,
        "caption": caption,
        "empty": empty,
        "has_slots": bool(slots),
    }


__all__ = ["LESSON_ROW_LIMIT", "build", "parity_label"]
