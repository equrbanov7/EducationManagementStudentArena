"""Dərs cədvəli iCal (.ics) exportu (U19) — RFC 5545.

Həftəlik slotlar təkrarlanan hadisələrə çevrilir:

* ``WeekType.ALL`` → ``RRULE:FREQ=WEEKLY`` (hər həftə);
* ``ODD``/``EVEN`` (üst/alt) → ``INTERVAL=2``, DTSTART slotun parity-sinə uyğun
  həftəyə lövbərlənir (:func:`schedule.week_parity` ilə eyni anchor — semestr
  başlanğıc həftəsi = 1-ci/üst həftə);
* ``UNTIL`` semestrin son günü — kalendar semestr bitəndə susur.

Vaxtlar "floating local time" kimi yazılır (TZID yox): universitet bir şəhərdə
yerləşir və Google/Apple Calendar float vaxtı istifadəçinin yerli vaxtında
göstərir — DST cədvəl sürüşmələrindən qaçırıq.
"""

from __future__ import annotations

import datetime

from django.conf import settings

from apps.registrar.models import WeekType
from apps.registrar.schedule import week_parity


def _escape(text: str) -> str:
    """RFC 5545 TEXT escape: backslash, semicolon, comma, newline."""
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """75-oktet sətir qatlaması (RFC 5545 §3.1) — davam sətirləri boşluqla."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts = []
    while encoded:
        chunk = encoded[:74]
        # Multi-bayt simvolu ortadan kəsmə.
        while chunk and (chunk[-1] & 0xC0) == 0x80:
            chunk = chunk[:-1]
        parts.append(chunk.decode("utf-8"))
        encoded = encoded[len(chunk) :]
    return ("\r\n ").join(parts)


def _dt(date: datetime.date, time: datetime.time) -> str:
    return f"{date:%Y%m%d}T{time:%H%M%S}"


def _first_occurrence(slot, period) -> datetime.date | None:
    """Slotun semestr daxilində ilk real tarixi (parity nəzərə alınmaqla)."""
    start = period.start_date
    if isinstance(start, str):
        start = datetime.date.fromisoformat(start)
    end = period.end_date
    if isinstance(end, str):
        end = datetime.date.fromisoformat(end)
    # weekday: model 1=B.e … 7=bazar; Python date.weekday() 0=B.e.
    first = start + datetime.timedelta(days=(slot.weekday - 1 - start.weekday()) % 7)
    if slot.week_type != WeekType.ALL:
        monday = first - datetime.timedelta(days=first.weekday())
        if week_parity(period, monday) != slot.week_type:
            first += datetime.timedelta(days=7)
    return first if first <= end else None


def _slot_event(slot, period, stamp: str) -> list[str]:
    offering = slot.offering
    subject = getattr(offering, "subject", None)
    summary = f"{subject.code} — {subject.name}" if subject else str(offering)
    instructor = getattr(offering, "instructor", None)
    group = getattr(offering, "group", None)
    desc_bits = []
    if group is not None:
        desc_bits.append(group.name)
    if instructor is not None:
        desc_bits.append(instructor.get_full_name() or instructor.username)

    first = _first_occurrence(slot, period)
    if first is None:
        return []
    end_date = period.end_date
    if isinstance(end_date, str):
        end_date = datetime.date.fromisoformat(end_date)

    interval = 1 if slot.week_type == WeekType.ALL else 2
    rrule = f"RRULE:FREQ=WEEKLY;INTERVAL={interval};UNTIL={end_date:%Y%m%d}T235959"

    lines = [
        "BEGIN:VEVENT",
        f"UID:ems-slot-{slot.pk}@emsarena",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{_dt(first, slot.start_time)}",
        f"DTEND:{_dt(first, slot.end_time)}",
        rrule,
        f"SUMMARY:{_escape(summary)}",
    ]
    if slot.room:
        lines.append(f"LOCATION:{_escape(slot.room)}")
    if desc_bits:
        lines.append(f"DESCRIPTION:{_escape(' · '.join(desc_bits))}")
    lines.append("END:VEVENT")
    return lines


def build_schedule_ics(*, slots, period, calendar_name: str) -> str:
    """Slot siyahısı → tam VCALENDAR mətni (period yoxdursa boş kalendar)."""
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    stamp = f"{datetime.datetime.utcnow():%Y%m%dT%H%M%SZ}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{brand}//Ders cedveli//AZ",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
    ]
    if period is not None:
        for slot in slots:
            lines.extend(_slot_event(slot, period, stamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
