"""Yalnız uyğunluğu birmənalı və görünən jurnal sütununa keçid ver."""

from django.utils.translation import pgettext

from . import lesson_rooms
from .journal_shares import journal_scope
from .lesson_share_scope import scoped_lessons


def matching_slot_lesson(
    lessons,
    *,
    start_time,
    end_time,
    kind,
    instructor_id,
    default_instructor_id,
    hours,
    room_id=None,
    lab_group=None,
    seminar_group=None,
    passive=False,
):
    """Eyni gün və jurnalda görünən sütunlar arasından göndərilən dərsi birmənalı seç."""
    matches = [
        lesson
        for lesson in lessons
        if lesson.start_time == start_time
        and lesson.end_time == end_time
        and lesson.kind == kind
        and lesson.hours == hours
        and lesson.is_passive == passive
        and lesson.lab_group == lab_group
        and lesson.seminar_group == seminar_group
        and (lesson.instructor_id or default_instructor_id) == instructor_id
        and (room_id is None or lesson.room_id is None or str(lesson.room_id) == str(room_id))
    ]
    return matches[0] if len(matches) == 1 else None


def creation_collision(offering, user, *, date, start_time, slot=None, **fields):
    if user is None:
        return None, slot_choice_message()
    candidates = offering.lessons.filter(organization_id=offering.organization_id, date=date, start_time=start_time)
    scope = journal_scope(user, offering)
    visible = list(scoped_lessons(offering, candidates, scope))
    lesson = matching_slot_lesson(
        visible, start_time=start_time, default_instructor_id=offering.instructor_id, **fields
    )
    if lesson is None:
        if slot is None and len(visible) == 1 and visible[0].kind != fields["kind"]:
            return None, _other_kind_slot_message(visible[0])
        return None, slot_choice_message()
    if slot is None:
        return lesson, None
    # Lesson nə vaxtsa hansı ScheduleSlot-dan açıldığını saxlamır. Eyni vaxt və növdə iki cədvəl sətri
    # varsa, uyğun sütunun konkret seçilmiş slota aidliyi də birmənalı olmalıdır.
    from .journal_activation import lesson_facts, slot_kind, slots_on

    peers = [
        s
        for s in slots_on(offering, date)
        if (s.start_time, s.end_time, slot_kind(s)) == (start_time, fields["end_time"], fields["kind"])
    ]
    if len(peers) == 1:
        return lesson, None
    _, last_instructor, _ = lesson_facts(offering, date)
    lesson = matching_schedule_slots(offering, peers, [lesson], last_instructor, scope).get(slot.pk)
    return lesson, None if lesson is not None else slot_choice_message()


def _other_kind_slot_message(lesson) -> str:
    label = lesson.get_kind_display() + (f" — {lesson.topic}" if (lesson.topic or "").strip() else "")
    return pgettext(
        "registrar.journal",
        "Bu jurnalda %(date)s, saat %(time)s üçün artıq «%(lesson)s» dərsi var. Yeni dərs mövcud dərsi dəyişmir — "
        "yeni dərs üçün başqa dərs saatı seçin.",
    ) % {"date": lesson.date.strftime("%d.%m.%Y"), "time": lesson.start_time.strftime("%H:%M"), "lesson": label}


def slot_choice_message():
    return pgettext(
        "registrar.journal_lessons",
        "Bu dərs saatı tutulub. Jurnalda uyğun sütunu özünüz seçin və ya başqa dərs saatı seçin.",
    )


def activation_slot_facts(offering, slots, day, *, scope=None, memo=False):
    from .journal_activation import lesson_facts

    covered, last_instructor, lessons = lesson_facts(offering, day, memo=memo)
    visible = scoped_lessons(offering, lessons, scope)
    matches = matching_schedule_slots(offering, slots, visible, last_instructor, scope)
    return covered, last_instructor, visible, matches


def matching_schedule_slots(offering, slots, lessons, last_instructor, scope, *, rooms=None):
    """Cədvəl slotuna keçid üçün həm sütun, həm də slot birmənalı olmalıdır."""
    from .journal_activation import current_last_instructor, lesson_hours_for_slot, slot_kind

    if rooms is None:
        rooms = lesson_rooms.slot_room_ids(offering.organization, [slot.room for slot in slots])
    found = {}
    used = set()
    ambiguous = set()
    for slot in slots:
        kind = slot_kind(slot)
        if scope and not scope.allows_kind(kind):
            continue
        teacher_id = slot.instructor_id
        if teacher_id is None:
            teacher = current_last_instructor(offering, kind, last_instructor)
            teacher_id = getattr(teacher, "pk", None) or offering.instructor_id
        if scope and not scope.full and (not scope.is_owner or scope.enrollment_ids is not None):
            teacher_id = scope.teacher_id
        lesson = matching_slot_lesson(
            lessons,
            start_time=slot.start_time,
            end_time=slot.end_time,
            kind=kind,
            instructor_id=teacher_id,
            default_instructor_id=offering.instructor_id,
            hours=lesson_hours_for_slot(slot),
            room_id=rooms.get((slot.room or "").strip()),
        )
        if lesson is not None:
            found[slot.pk] = lesson
            if lesson.pk in used:
                ambiguous.add(lesson.pk)
            used.add(lesson.pk)
    return {slot_id: lesson for slot_id, lesson in found.items() if lesson.pk not in ambiguous}
