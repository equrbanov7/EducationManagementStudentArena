"""HƏMİŞƏ görünən həftəlik cədvəl matrisi (nömrələnmiş dərs saatı × gün).

──────────────────────────────────────────────────────────────────────────────
NİYƏ AYRICA MODUL (sahibin tələbi, 2026-09-09)
──────────────────────────────────────────────────────────────────────────────
Köhnə ``schedule.build_time_grid`` sətirləri MÖVCUD slotların (start, end)
cütlərindən yığırdı: slot yoxdursa grid də yox idi və ekranda «Bu semestr üçün
hələ cədvəl slotu yoxdur» yazısı çıxırdı. Sahib açıq dedi: «Cədvəl olmasa da
burada həmişə, boş da olsa, cədvəl görünsün».

Ona görə burada sətirlər DATA-DAN YOX, KONFİQURASİYADAN gəlir: nömrələnmiş dərs
saatları (1-ci saat, 2-ci saat, …) × həftənin günləri. Slot yoxdursa matris
yenə tam qurulur, sadəcə hər hüceyrə boşdur — və redaktorda boş hüceyrə
«klik → slot yarat» hədəfidir.

──────────────────────────────────────────────────────────────────────────────
DƏRS SAATLARININ MƏNBƏYİ (data-driven, hardcode DEYİL)
──────────────────────────────────────────────────────────────────────────────
1. ``Organization.settings["lesson_times"]`` — tenantın öz zəng cədvəli;
   format: ``[["08:30", "10:00"], ["10:10", "11:40"], …]`` (dəyişkən-struktur
   qaydası: universitetlər arasında zənglər fərqlidir).
2. Yoxdursa/xarabdırsa — ``schedule.STANDARD_LESSON_TIMES`` (layihənin mövcud
   standart 8 saatı; slot formasında onsuz da bu siyahı işlədilir).

Nömrələnmə həmişə 1-dən başlayır və sıralama vaxta görədir.

NÖVBƏ (shift): sahibin «səhər yaxud günorta növbəsi» tələbi üçün hər saat
zolağı bir növbəyə aid edilir — səhər (< 13:30), günorta (13:30–18:00),
axşam (≥ 18:00, magistratura bandı).
"""

from __future__ import annotations

import datetime

from django.utils.translation import pgettext_lazy

from apps.registrar import schedule as schedule_service
from apps.registrar.models import WeekType

_CTX = "registrar.schedule_grid"

#: Növbə sərhədləri — səhər / günorta / axşam.
AFTERNOON_START = datetime.time(13, 30)
EVENING_START = schedule_service.EVENING_START

SHIFT_MORNING = "morning"
SHIFT_AFTERNOON = "afternoon"
SHIFT_EVENING = "evening"

SHIFT_LABELS = {
    SHIFT_MORNING: pgettext_lazy(_CTX, "Səhər növbəsi"),
    SHIFT_AFTERNOON: pgettext_lazy(_CTX, "Günorta növbəsi"),
    SHIFT_EVENING: pgettext_lazy(_CTX, "Axşam (magistratura)"),
}

#: Tenant konfiqurasiyasının açarı (``Organization.settings``).
SETTINGS_KEY = "lesson_times"

_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII"}

#: Cədvəl qurulan günlər — Bazar ertəsi…Şənbə (mövcud davranışla eyni).
TEACHING_WEEKDAYS = schedule_service.WEEKDAYS[:6]


def shift_of(start_time) -> str:
    """Saat zolağının növbəsi (səhər / günorta / axşam)."""
    if start_time >= EVENING_START:
        return SHIFT_EVENING
    if start_time >= AFTERNOON_START:
        return SHIFT_AFTERNOON
    return SHIFT_MORNING


def _parse_pairs(raw):
    """``[["08:30","10:00"], …]`` → ``[(time, time), …]``; xarab giriş atılır."""
    pairs = []
    for item in raw or []:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        try:
            start = datetime.time.fromisoformat(str(item[0]))
            end = datetime.time.fromisoformat(str(item[1]))
        except (TypeError, ValueError):
            continue
        if end > start:
            pairs.append((start, end))
    return pairs


def lesson_periods(organization=None) -> list[dict]:
    """Nömrələnmiş dərs saatları (``no``, ``start``, ``end``, ``key``, ``shift``).

    Tenant öz zəng cədvəlini ``Organization.settings["lesson_times"]``-də
    saxlaya bilər; yoxdursa layihənin standart saatları işlədilir."""
    raw = None
    settings_blob = getattr(organization, "settings", None)
    if isinstance(settings_blob, dict):
        raw = settings_blob.get(SETTINGS_KEY)
    pairs = _parse_pairs(raw)
    if not pairs:
        pairs = [
            (datetime.time.fromisoformat(start), datetime.time.fromisoformat(end))
            for start, end in schedule_service.STANDARD_LESSON_TIMES
        ]
    pairs = sorted(set(pairs))
    return [
        {
            "no": index,
            "roman": _ROMAN.get(index, str(index)),
            "start": start,
            "end": end,
            "start_text": start.strftime("%H:%M"),
            "end_text": end.strftime("%H:%M"),
            "key": "%s|%s" % (start.strftime("%H:%M"), end.strftime("%H:%M")),
            "shift": shift_of(start),
        }
        for index, (start, end) in enumerate(pairs, start=1)
    ]


def period_by_key(organization=None) -> dict:
    """``"HH:MM|HH:MM"`` → nömrələnmiş saat sətri (sürətli axtarış üçün)."""
    return {row["key"]: row for row in lesson_periods(organization)}


def _slot_key(slot) -> str:
    return "%s|%s" % (slot.start_time.strftime("%H:%M"), slot.end_time.strftime("%H:%M"))


def _day_headers(weekdays, week_context, exams_by_day=None):
    dates = (week_context or {}).get("dates") or {}
    today = (week_context or {}).get("today")
    exams_by_day = exams_by_day or {}
    return [
        {
            "weekday": num,
            "label": label,
            "roman": _ROMAN.get(num, str(num)),
            "date": dates.get(num),
            "is_today": bool(today) and dates.get(num) == today,
            "exams": exams_by_day.get(num, []),
        }
        for num, label in weekdays
    ]


def _item(slot, parity):
    """Hüceyrə elementi — slot + «bu həftə keçirilirmi» bayrağı."""
    return {
        "slot": slot,
        "this_week": slot.week_type == WeekType.ALL or slot.week_type == parity,
    }


_WEEK_ORDER = {WeekType.ALL: 0, WeekType.ODD: 1, WeekType.EVEN: 2}


def build_matrix(*, slots, organization=None, week_context=None, exams_by_day=None, weekdays=TEACHING_WEEKDAYS) -> dict:
    """Nömrələnmiş saat × gün matrisi — slot OLMASA DA tam qurulur.

    Sətirlər konfiqurasiyadan gəlir; konfiqurasiyaya uyğun GƏLMƏYƏN vaxtı olan
    slotlar (məs. köhnə idxaldan qalma 09:00–10:30) itmir — onlar üçün sonda
    əlavə «konfiqurasiyadan kənar» sətirlər yaradılır.
    """
    parity = (week_context or {}).get("parity")
    dates = (week_context or {}).get("dates") or {}
    today = (week_context or {}).get("today")
    day_numbers = [num for num, _label in weekdays]

    buckets: dict = {}
    extra_keys: dict = {}
    for slot in slots:
        key = _slot_key(slot)
        buckets.setdefault(key, {}).setdefault(slot.weekday, []).append(_item(slot, parity))
        extra_keys.setdefault(key, (slot.start_time, slot.end_time))

    periods = lesson_periods(organization)
    rows = []
    for row in periods:
        extra_keys.pop(row["key"], None)
        rows.append(_row(row, buckets.get(row["key"], {}), day_numbers, dates, today))

    extra_rows = []
    for index, (key, (start, end)) in enumerate(sorted(extra_keys.items(), key=lambda kv: kv[1]), start=1):
        meta = {
            "no": len(periods) + index,
            "roman": "—",
            "start": start,
            "end": end,
            "start_text": start.strftime("%H:%M"),
            "end_text": end.strftime("%H:%M"),
            "key": key,
            "shift": shift_of(start),
            "is_extra": True,
        }
        extra_rows.append(_row(meta, buckets.get(key, {}), day_numbers, dates, today))

    return {
        "day_headers": _day_headers(weekdays, week_context, exams_by_day),
        "rows": rows,
        "extra_rows": extra_rows,
        "slot_count": len(slots),
        "has_slots": bool(slots),
    }


def _row(meta, by_day, day_numbers, dates, today):
    cells = []
    for num in day_numbers:
        items = sorted(by_day.get(num, []), key=lambda it: _WEEK_ORDER.get(it["slot"].week_type, 9))
        cells.append(
            {
                "weekday": num,
                "date": dates.get(num),
                "is_today": bool(today) and dates.get(num) == today,
                "items": items,
                "is_empty": not items,
            }
        )
    return {**meta, "cells": cells}


def attach_slot_extras(grid, *, stats_map=None, counts_map=None):
    """Matris elementlərinə rol-spesifik əlavələr bağlayır (detal modalı üçün):
    tələbəyə öz jurnal statusu (qayıb/giriş balı), müəllimə qrupun tələbə sayı.

    Matris (`build_matrix`) və köhnə `schedule.build_time_grid` fərqli açar
    adları işlədir (`items`/`extra_rows` vs `slots`/`evening_rows`) — hər ikisi
    dəstəklənir ki, çağıran tərəf seçim edə bilsin."""
    for rows in (grid.get("rows") or [], grid.get("extra_rows") or grid.get("evening_rows") or []):
        for row in rows:
            for cell in row["cells"]:
                for item in cell.get("items", cell.get("slots", [])):
                    offering_id = item["slot"].offering_id
                    if stats_map is not None:
                        item["stats"] = stats_map.get(offering_id)
                    if counts_map is not None:
                        item["student_count"] = counts_map.get(offering_id, 0)


__all__ = [
    "attach_slot_extras",
    "AFTERNOON_START",
    "EVENING_START",
    "SETTINGS_KEY",
    "SHIFT_AFTERNOON",
    "SHIFT_EVENING",
    "SHIFT_LABELS",
    "SHIFT_MORNING",
    "TEACHING_WEEKDAYS",
    "build_matrix",
    "lesson_periods",
    "period_by_key",
    "shift_of",
]
