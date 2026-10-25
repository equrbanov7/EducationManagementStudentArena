"""Dərs mövzuları — köhnə sistemdə hər dərs tarixi sillabusun mövzu sətrinə bağlı idi (sahib 2026-10-25).

Mənbə ``journals_dates_rooms`` (jurnal, ay, gün, saat) → ``sillabus_sem_muh.movzu``. Jurnalın açılışları
«offerings» fazasının dilimlərindəndir; dərs: eyni ay + gün + saat; saat tutmursa və həmin gün açılışda TƏK
dərs varsa o. YALNIZ BOŞ mövzu və BOŞ otaq (``rooms.id`` → ``ExamRoom.code``) doldurulur (müəllimin yazdığına toxunulmur); bağlı /
deaktiv açılışlar ötürülür (sayılır). Sillabus sətrinə bağlantı (``syllabus_week``) ayrıca, mövzu mətninin
sillabus planı ilə DƏQİQ tutuşdurulması ilə qurulur — burada yalnız mətn yazılır.
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from django.apps import apps as django_apps

from ..legacy_text import clean_text

TOPIC_MAX_LENGTH = 255
#: Köçürülmüş otaq reyestrinin kodu (``repair_rooms`` / J10: ``myedu-room-<legacy id>``).
ROOM_CODE_PREFIX = "myedu-room-"
CHUNK = 2000


def _int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _time(value):
    text = str(value or "").strip()[:5]
    try:
        return datetime.time.fromisoformat(text) if len(text) == 5 else None
    except ValueError:
        return None


def pick_lesson(candidates, start):
    """Eyni gün dərsləri arasından: dəqiq saat (tək) → günün TƏK dərsi → ``None``."""

    exact = [lesson for lesson in candidates if lesson[1] == start]
    if len(exact) == 1:
        return exact[0]
    if not exact and len(candidates) == 1:
        return candidates[0]
    return None


def apply_topics(run, slices: dict) -> None:
    rows = run.bundle.get("lesson_topics") or []
    if not rows:
        return
    Lesson = django_apps.get_model("registrar", "Lesson")
    ExamRoom = django_apps.get_model("exams", "ExamRoom")
    rooms = dict(
        ExamRoom.objects.filter(organization=run.organization, code__startswith=ROOM_CODE_PREFIX).values_list(
            "code", "pk"
        )
    )
    writable = {str(pk) for entry in slices.values() for pk in entry.writable}
    day_index: dict = defaultdict(list)
    for pk, offering_id, date, start, topic, room_id in Lesson.objects.filter(
        organization=run.organization, offering_id__in=sorted(writable)
    ).values_list("pk", "offering_id", "date", "start_time", "topic", "room_id"):
        day_index[(str(offering_id), date.month, date.day)].append((pk, start, topic, room_id))
    chosen: dict = {}
    chosen_rooms: dict = {}
    for row in sorted(rows, key=lambda item: item["id"]):
        topic, truncated = clean_text(row.get("movzu"), max_length=TOPIC_MAX_LENGTH)
        room = rooms.get(f"{ROOM_CODE_PREFIX}{_int(row.get('room'))}") if _int(row.get("room")) else None
        if not topic:
            run.count("topic.source_blank")
        if row.get("room") and room is None:
            run.count("room.unresolved")
        if not topic and room is None:
            continue
        entry = slices.get(row["journal_uniqid"])
        if entry is None or not entry.offerings:
            run.count("topic.offering_unresolved")
            continue
        start = _time(row.get("times"))
        for offering_id in sorted(str(offering.pk) for offering in entry.offerings):
            if offering_id not in writable:
                run.count("topic.offering_closed")
                continue
            lesson = pick_lesson(day_index.get((offering_id, _int(row["month"]), _int(row["day"])), ()), start)
            if lesson is None:
                run.count("topic.lesson_unmatched")
                continue
            if room is not None and lesson[3] is None:
                chosen_rooms[lesson[0]] = room
            if not topic:
                continue
            if lesson[2]:
                run.count("topic.kept_existing")
                continue
            if lesson[0] in chosen and chosen[lesson[0]] != topic:
                run.count("topic.source_conflict_last_wins")
            chosen[lesson[0]] = topic
            if truncated:
                run.count("topic.truncated")
    pks = sorted(set(chosen) | set(chosen_rooms))
    for start in range(0, len(pks), CHUNK):
        objects = []
        for lesson in Lesson.objects.filter(pk__in=pks[start : start + CHUNK]).only("pk", "topic", "room_id"):
            fields = []
            if lesson.pk in chosen:
                lesson.topic = chosen[lesson.pk]
                fields.append("topic")
            if lesson.pk in chosen_rooms:
                lesson.room_id = chosen_rooms[lesson.pk]
                fields.append("room")
            objects.append(lesson)
            run.touched("lessons", lesson.pk, fields)
        Lesson.objects.bulk_update(objects, ["topic", "room"])
    run.count("topic.filled", len(chosen))
    run.count("room.filled", len(chosen_rooms))


__all__ = ["apply_topics", "pick_lesson"]
