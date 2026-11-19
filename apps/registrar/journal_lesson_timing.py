"""Dərsin vaxt məlumatı — YALNIZ əməkdaşa (sahib 2026-11-17).

Laborant / tyutor / kafedra / dekanlıq / RİM jurnalı açanda:

* sütun başlığında tarix ilə «i/e · q/b» arasında dərsin SAAT ARALIĞI (``start_time–end_time``) və neçə saatlıq
  əlavə olunduğu (``hours``; passiv dərs öz «Passiv · N saat» nişanı ilə);
* gün özəti pəncərəsində dərsin BAŞLADILDIĞI an — dərs sətrinin yaradılma vaxtı (``Lesson.created_at``, Bakı vaxtı);
* xlsx ixracında hər dərs üçün eyni sahələr («Dərslər» vərəqi + başlıqda saat);
* dərsin keçirildiyi OTAQ (sahib 2026-11-19) — saat aralığının yanında, eyni üç yerdə (:func:`attach_rooms`).

Jurnalın ÖZ müəllimi (açılışın müəllimi / bölünmüş jurnalın pay sahibi / bu jurnalda dərs keçən / təhvil vermiş köhnə
müəllim) bunu GÖRMÜR — sahib: «qarışıqdır». Qərar HTML-də verilir: müəllimə gedən səhifədə bu data-atributlar yoxdur.
"""

from __future__ import annotations

from django.utils import timezone


def is_journal_teacher(user, offering) -> bool:
    """İstifadəçi bu jurnalın öz müəllimidirmi (rolundan asılı olmayaraq — RİM əməkdaşı da öz jurnalında müəllimdir)."""
    user_id = getattr(user, "pk", None)
    if user_id is None or not getattr(user, "is_authenticated", False):
        return False
    if offering.instructor_id == user_id:
        return True
    from .journal_shares import active_shares

    if any(share.teacher_id == user_id for share in active_shares(offering)):
        return True
    from .handover import is_handover_observer

    if is_handover_observer(user, offering):
        return True
    from .models import Lesson

    return Lesson.objects.filter(offering_id=offering.pk, instructor_id=user_id).exists()


def show_lesson_timing(user, offering) -> bool:
    """Saat aralığı / saat sayı / başladılma vaxtı göstərilsinmi — əməkdaşa bəli, jurnalın müəlliminə yox."""
    return bool(getattr(user, "is_authenticated", False)) and not is_journal_teacher(user, offering)


def time_range(lesson) -> str:
    """``10:10–11:40`` / yalnız başlanğıc ``10:10`` / saat yoxdursa boş."""
    start, end = lesson.start_time, lesson.end_time
    if not start:
        return ""
    text = start.strftime("%H:%M")
    return f"{text}–{end.strftime('%H:%M')}" if end else text


def is_imported(lesson) -> bool:
    """Köhnə sistemdən gələn dərs: bərpa olunmuş (``is_legacy_synthesised``) və ya köçürülmüş — aktoru yoxdur
    (``created_by`` boş; ``lessons_log_totals.is_imported_lesson`` ilə eyni qayda). ``created_at`` köçürmə anıdır."""
    return bool(getattr(lesson, "is_legacy_synthesised", False)) or getattr(lesson, "created_by_id", None) is None


def started_at(lesson):
    """Dərsin başladıldığı an (yerli vaxt). Köhnə sistemdən gələn dərsdə yoxdur (köçürmə anı mənasızdır)."""
    if is_imported(lesson) or not getattr(lesson, "created_at", None):
        return None
    return timezone.localtime(lesson.created_at)


def started_at_text(lesson) -> str:
    moment = started_at(lesson)
    return moment.strftime("%d.%m.%Y %H:%M") if moment else ""


#: Dərs obyektinə yazılan atribut: ``{"name", "label", "from_slot"}`` (otaq tapılmayıbsa atribut ``None``-dur).
ROOM_ATTR = "timing_room"


def _slot_room_texts(offering, lessons) -> dict:
    """``{dərs.pk: cədvəl slotunun otaq mətni}`` — YALNIZ öz otağı yazılmamış dərslər üçün (əlavə sorğusuz).

    Slot həmin tarixin cədvəlindən (həftə günü + üst/alt həftə + semestr sərhədi — ``journal_activation.slots_on``)
    götürülür və günün dərsləri ilə TƏK-TƏK cütləşdirilir (``match_slots``: eyni saat + eyni növ, sonra eyni saat).
    Slot siyahısı açılış üzrə memolanıb (``offering_slots`` — jurnal səhifəsi onu onsuz da yükləyir)."""
    from .journal_activation import slots_on
    from .lesson_share_scope import match_slots

    by_day: dict = {}
    for lesson in lessons:
        by_day.setdefault(lesson.date, []).append(lesson)
    texts = {}
    for day, day_lessons in by_day.items():
        if all(lesson.room_id or lesson.start_time is None for lesson in day_lessons):
            continue
        slots = slots_on(offering, day)
        if not slots:
            continue
        by_pk = {slot.pk: slot for slot in slots}
        for slot_pk, lesson in match_slots(slots, day_lessons).items():
            text = (by_pk[slot_pk].room or "").strip()
            if text and not lesson.room_id:
                texts[lesson.pk] = text
    return texts


def lesson_room_map(offering, lessons) -> dict:
    """``{dərs.pk: {"name", "label", "from_slot"}}`` — bütün səhifə üçün TƏK otaq sorğusu (N+1 yoxdur).

    Mənbə sırası: (1) dərsin ÖZ otağı (``Lesson.room`` — müəllimin dərs modalında seçdiyi / «Aktivləşdir»in yazdığı),
    (2) həmin tarix + saatın cədvəl slotunun otağı (``from_slot`` — «cədvəl üzrə»), (3) heç nə (açar yoxdur).
    Etiket «Keçilmiş dərslər»lə EYNİDİR: «ad (korpus)». Slotun sərbəst mətni reyestrdə TƏK otağa uyğun gəlirsə
    həmin otağın etiketi, gəlmirsə cədvəldə yazıldığı kimi göstərilir."""
    from django.db.models import Q

    from .lessons_log import _room_label

    lessons = list(lessons)
    slot_texts = _slot_room_texts(offering, lessons)
    room_ids = {lesson.room_id for lesson in lessons if lesson.room_id}
    query = Q(pk__in=room_ids) if room_ids else Q(pk__in=[])
    for text in set(slot_texts.values()):
        query |= Q(is_active=True) & (Q(name__iexact=text) | Q(code__iexact=text))
    rooms = list(offering.organization.exam_rooms.filter(query)) if (room_ids or slot_texts) else []
    by_id = {room.pk: room for room in rooms}

    def _registry_match(text):
        key = text.upper()
        hits = [
            room
            for room in rooms
            if room.is_active and ((room.name or "").upper() == key or (room.code or "").upper() == key)
        ]
        return hits[0] if len(hits) == 1 else None

    found = {}
    for lesson in lessons:
        room = by_id.get(lesson.room_id) if lesson.room_id else None
        if room is not None:
            found[lesson.pk] = {"name": (room.name or "").strip(), "label": _room_label(room), "from_slot": False}
            continue
        text = slot_texts.get(lesson.pk)
        if not text:
            continue
        match = _registry_match(text)
        name = (match.name or "").strip() if match is not None else text
        found[lesson.pk] = {
            "name": name or text,
            "label": (_room_label(match) if match else "") or text,
            "from_slot": True,
        }
    return found


def attach_rooms(offering, lessons) -> None:
    """Hər dərs obyektinə ``timing_room`` yazır (şablon / xlsx oradan oxuyur); otaq yoxdursa ``None`` — boşluq."""
    lessons = list(lessons)
    rooms = lesson_room_map(offering, lessons)
    for lesson in lessons:
        setattr(lesson, ROOM_ATTR, rooms.get(lesson.pk))


def room_text(lesson) -> str:
    """Fayl / mətn üçün otaq: «305 (Baş korpus)»; cədvəldən götürülübsə sonda «(cədvəl üzrə)». Yoxdursa boş."""
    from django.utils.translation import pgettext

    room = getattr(lesson, ROOM_ATTR, None)
    if not room:
        return ""
    if room["from_slot"]:
        return "%s (%s)" % (room["label"], pgettext("registrar.journal", "cədvəl üzrə"))
    return room["label"]


def page_context(user, offering, journal=None) -> dict:
    """``show_lesson_timing`` + (əməkdaş üçün) səhifədəki dərslərə otaq — müəllimin səhifəsində heç biri yoxdur."""
    show = show_lesson_timing(user, offering)
    if show and isinstance(journal, dict):
        attach_rooms(offering, journal.get("lessons") or [])
    return {"show_lesson_timing": show}


__all__ = [
    "ROOM_ATTR",
    "attach_rooms",
    "is_imported",
    "is_journal_teacher",
    "lesson_room_map",
    "page_context",
    "room_text",
    "show_lesson_timing",
    "started_at",
    "started_at_text",
    "time_range",
]
