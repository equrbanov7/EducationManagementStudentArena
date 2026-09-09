"""Cədvəl konflikt mühərriki + boş hüceyrə tövsiyəsi (SERVER AVTORİTETDİR).

──────────────────────────────────────────────────────────────────────────────
NƏYİ HƏLL EDİR (sahibin tələbi, 2026-09-09)
──────────────────────────────────────────────────────────────────────────────
«Əgər həmin vaxtda müəllimin başqa yerdə dərsi varsa yazsın ki, müəllimin filan
saatda filan qrupa dərsi var və göstərsin» + «proqram tövsiyə versin ki səhər
yaxud günorta növbəsinə uyğun hara boşdursa orada ola bilər».

Köhnə ``schedule.find_conflict`` yalnız BİRİNCİ toqquşan slotu qaytarırdı və
səbəbi sonradan təxmin edirdi (``conflict_reason``). Redaktorun ehtiyacı fərqli:
bir hərəkət eyni anda müəllimi DƏ, otağı DA tuta bilər, və istifadəçi hər ikisini
görməlidir. Ona görə burada BÜTÜN toqquşmalar növü ilə birlikdə qaytarılır və
UI yalnız serverin dediyini göstərir (klient heç nə hesablamır).

QAYDALAR
--------
* vaxt ARALIĞI kəsişməsi (yalnız eyni `start_time` deyil);
* üst/alt həftə: ``ALL`` hər ikisi ilə, ``ODD``/``EVEN`` yalnız özü və ``ALL``
  ilə toqquşur (``odd`` və ``even`` bir-birinə mane olmur);
* PARKLANMIŞ (``is_parked``) və yumşaq silinmiş slotlar heç bir hesabatda
  iştirak etmir — onlar cədvəldə deyil;
* müəllim/otaq yoxlaması TENANT genişliyindədir (başqa fakültənin dərsi də
  müəllimi tutur), qrup yoxlaması isə təbii olaraq qrupun özündədir.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from apps.registrar.models import ScheduleSlot, WeekType

_CTX = "registrar.schedule_conflicts"

KIND_TEACHER = "teacher"
KIND_GROUP = "group"
KIND_ROOM = "room"

#: Göstəriş sırası — müəllim ən vacibdir (sahibin nümunəsi məhz odur).
KIND_ORDER = (KIND_TEACHER, KIND_GROUP, KIND_ROOM)


def week_types_overlap(a, b) -> bool:
    """Üst və alt həftə bir-birinə mane OLMUR; qalan hər cütlük toqquşur."""
    return not ({a, b} == {WeekType.ODD, WeekType.EVEN})


def time_ranges_overlap(start_a, end_a, start_b, end_b) -> bool:
    return start_a < end_b and start_b < end_a


def _weekday_label(weekday) -> str:
    from apps.registrar import schedule as schedule_service

    for num, label in schedule_service.WEEKDAYS:
        if num == weekday:
            return str(label)
    return str(weekday)


def _week_type_label(week_type) -> str:
    if week_type == WeekType.ODD:
        return pgettext(_CTX, "üst həftə")
    if week_type == WeekType.EVEN:
        return pgettext(_CTX, "alt həftə")
    return pgettext(_CTX, "hər həftə")


def _person_name(user) -> str:
    if user is None:
        return ""
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or str(getattr(user, "username", "") or "")


def _message(kind, slot) -> str:
    """İstifadəçiyə göstərilən açıq cümlə (sahibin nümunəsi ilə eyni forma)."""
    offering = slot.offering
    params = {
        "day": _weekday_label(slot.weekday),
        "time": slot.start_time.strftime("%H:%M"),
        "group": getattr(offering.group, "name", "") or pgettext(_CTX, "təyin edilməmiş qrup"),
        "subject": getattr(offering.subject, "code", "") or getattr(offering.subject, "name", "") or "",
        "teacher": _person_name(offering.instructor) or pgettext(_CTX, "müəllim təyin edilməyib"),
        "room": slot.room or "",
    }
    if kind == KIND_TEACHER:
        return pgettext(_CTX, "Müəllimin %(day)s %(time)s-da %(group)s qrupunda dərsi var (%(subject)s).") % params
    if kind == KIND_GROUP:
        return pgettext(_CTX, "Qrupun %(day)s %(time)s-da artıq dərsi var (%(subject)s).") % params
    return pgettext(_CTX, "%(room)s auditoriyası %(day)s %(time)s-da %(group)s qrupu tərəfindən tutulub.") % params


def kind_label(kind) -> str:
    """Növ açarının İSTİFADƏÇİ etiketi — UI-da xam «teacher/group/room» görünməsin."""
    if kind == KIND_TEACHER:
        return pgettext(_CTX, "müəllim")
    if kind == KIND_GROUP:
        return pgettext(_CTX, "qrup")
    return pgettext(_CTX, "auditoriya")


def describe(slot, kind) -> dict:
    """Konflikt slotunun JSON müqaviləsi — UI açar adları DƏYİŞMƏZ."""
    offering = slot.offering
    return {
        "kind": kind,
        "kind_label": kind_label(kind),
        "slot_id": str(slot.pk),
        "message": _message(kind, slot),
        "subject_code": getattr(offering.subject, "code", "") or "",
        "subject_name": getattr(offering.subject, "name", "") or "",
        "group": getattr(offering.group, "name", "") or "",
        "instructor": _person_name(offering.instructor),
        "room": slot.room or "",
        "weekday": slot.weekday,
        "weekday_label": _weekday_label(slot.weekday),
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "week_type": slot.week_type,
        "week_type_label": _week_type_label(slot.week_type),
    }


def live_slots(organization, *, weekday=None):
    """Cədvəldə HƏQİQƏTƏN duran slotlar (silinməmiş + parklanmamış)."""
    queryset = ScheduleSlot.objects.filter(organization=organization, is_parked=False)
    if weekday is not None:
        queryset = queryset.filter(weekday=weekday)
    return queryset.select_related("offering", "offering__subject", "offering__group", "offering__instructor")


def detect(
    *,
    organization,
    weekday,
    start_time,
    end_time,
    week_type,
    room="",
    group_id=None,
    instructor_id=None,
    exclude_ids=(),
    candidates=None,
) -> list[dict]:
    """Bu yerləşdirmənin BÜTÜN toqquşmaları — növ + açıq mətn ilə.

    ``candidates`` verilsə baza sorğusu təkrarlanmır (tövsiyə mühərriki eyni
    slot dəstini onlarla hüceyrə üçün yenidən istifadə edir).
    """
    excluded = {str(value) for value in (exclude_ids or ()) if value}
    room_norm = (room or "").strip().lower()
    rows = candidates if candidates is not None else live_slots(organization, weekday=weekday)

    found: dict = {}
    for slot in rows:
        if slot.weekday != weekday or str(slot.pk) in excluded:
            continue
        if not time_ranges_overlap(start_time, end_time, slot.start_time, slot.end_time):
            continue
        if not week_types_overlap(week_type, slot.week_type):
            continue
        offering = slot.offering
        if instructor_id and offering.instructor_id == instructor_id:
            found.setdefault(KIND_TEACHER, slot)
        if group_id and offering.group_id == group_id:
            found.setdefault(KIND_GROUP, slot)
        if room_norm and room_norm == (slot.room or "").strip().lower():
            found.setdefault(KIND_ROOM, slot)
    return [describe(found[kind], kind) for kind in KIND_ORDER if kind in found]


# ── Tövsiyə: hara boşdur ─────────────────────────────────────────────────────


def _day_load(rows, weekday, group_id, instructor_id):
    """Həmin gün qrupun/müəllimin neçə dərsi var (sıxlıq üçün)."""
    total = 0
    for slot in rows:
        if slot.weekday != weekday:
            continue
        offering = slot.offering
        if (group_id and offering.group_id == group_id) or (instructor_id and offering.instructor_id == instructor_id):
            total += 1
    return total


def suggest(
    *,
    organization,
    group_id=None,
    instructor_id=None,
    week_type=WeekType.ALL,
    room="",
    shift="",
    exclude_ids=(),
    weekdays=None,
    limit=8,
) -> list[dict]:
    """Həm müəllimin, həm qrupun BOŞ olduğu hüceyrələr — sıralanmış.

    Sahibin tələbi: «proqram tövsiyə versin ki səhər yaxud günorta növbəsinə
    uyğun hara boşdursa orada ola bilər». ``shift`` verilibsə yalnız həmin
    növbənin saatlarına baxılır.

    Sıralama (kiçik bal = yaxşı): əvvəlcə HƏMİN GÜN artıq dərsi olan günlər
    (tələbə üçün «bir dərs üçün gəlmək» pisdir), sonra günün erkən saatları.
    """
    from apps.registrar import schedule_grid

    weekdays = weekdays or schedule_grid.TEACHING_WEEKDAYS
    rows = list(live_slots(organization))
    periods = [row for row in schedule_grid.lesson_periods(organization) if not shift or row["shift"] == shift]

    out = []
    for weekday, day_label in weekdays:
        load = _day_load(rows, weekday, group_id, instructor_id)
        for period in periods:
            clashes = detect(
                organization=organization,
                weekday=weekday,
                start_time=period["start"],
                end_time=period["end"],
                week_type=week_type,
                room=room,
                group_id=group_id,
                instructor_id=instructor_id,
                exclude_ids=exclude_ids,
                candidates=rows,
            )
            if clashes:
                continue
            out.append(
                {
                    "weekday": weekday,
                    "weekday_label": str(day_label),
                    "lesson_no": period["no"],
                    "time_slot": period["key"],
                    "start_time": period["start_text"],
                    "end_time": period["end_text"],
                    "shift": period["shift"],
                    "shift_label": str(schedule_grid.SHIFT_LABELS.get(period["shift"], "")),
                    "day_load": load,
                    "score": (0 if load else 1, period["no"], weekday),
                }
            )
    out.sort(key=lambda row: row["score"])
    for row in out:
        row.pop("score", None)
    return out[: max(1, int(limit or 8))]


__all__ = [
    "KIND_GROUP",
    "kind_label",
    "KIND_ORDER",
    "KIND_ROOM",
    "KIND_TEACHER",
    "describe",
    "detect",
    "live_slots",
    "suggest",
    "time_ranges_overlap",
    "week_types_overlap",
]
