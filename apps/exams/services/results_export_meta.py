"""Nəticə ixracının cəhd meta-məlumatı — «Yoxlayan» və «Zal / Kompüter» (sahib 2026-10-27).

Hər iki funksiya cəhd SİYAHISI üçün sabit sayda sorğu edir (sətir başına sorğu yoxdur) və həm
«Dəyərləndirilmiş nəticələr» ekranı (görünən səhifə), həm də vahid Excel ixracı tərəfindən çağırılır.

«Yoxlayan» qaydası
------------------
Əvvəl test imtahanında «Yoxlayan» sütunu imtahanın MÜƏLLİFİNİ göstərirdi (məs. «Elvin Qurbanov»),
halbuki balı sistem hesablamışdı. İndi:

* insan bal qoyub / dəyişibsə (``ExamAttempt.graded_by`` — ilk manual qiymətləndirən, və
  ``ExamGradeEvent.grader`` — hər manual / apellyasiya bal dəyişikliyi) — həmin şəxs(lər), xronoloji;
* heç bir insan izi yoxdursa, test və kodlaşdırma (test keysləri) cəhdi — «Avtomatik (sistem)»;
* yazılı cəhddə insan izi yoxdursa (köhnə idxal) — boş: kimin yoxladığı məlum deyil, təxmin edilmir.

«Zal / Kompüter»
----------------
Cəhdin fiziki yeri girişdə qeydli zal kompüterindən yazılır (``ExamAttempt.room`` /
``room_computer``). Bunlar boşdursa final biletindən (``FinalExamTicket``: sessiyanın zalı + yer
nömrəsi; yer nömrəsi həmin zalın kompüterinə uyğunlaşdırılır) götürülür.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import prefetch_related_objects
from django.utils.translation import pgettext

#: İnsan izi olmadıqda balı sistemin hesabladığı imtahan növləri.
AUTO_GRADED_EXAM_TYPES = frozenset({"test", "coding"})


def auto_checker_label() -> str:
    return pgettext("exams.results_export", "Avtomatik (sistem)")


def _person(user) -> str:
    return (user.get_full_name() or user.username) if user is not None else ""


def checked_by_map(attempts) -> dict[int, str]:
    """``attempt_id`` → «Yoxlayan» mətni (2 sorğu: bal tarixçəsi + ilk qiymətləndirənlər)."""
    from apps.exams.models import ExamGradeEvent

    attempts = [attempt for attempt in attempts if attempt.pk]
    if not attempts:
        return {}
    event_graders: dict[int, list] = {}
    events = (
        ExamGradeEvent.objects.filter(attempt_id__in=[attempt.pk for attempt in attempts], grader__isnull=False)
        .select_related("grader")
        .order_by("attempt_id", "created_at", "id")
    )
    for event in events:
        event_graders.setdefault(event.attempt_id, []).append(event.grader)
    first_ids = {attempt.graded_by_id for attempt in attempts if attempt.graded_by_id}
    first_graders = {user.pk: user for user in get_user_model().objects.filter(pk__in=first_ids)} if first_ids else {}

    labels: dict[int, str] = {}
    auto_label = auto_checker_label()
    for attempt in attempts:
        people = []
        if attempt.graded_by_id in first_graders:
            people.append(first_graders[attempt.graded_by_id])
        people.extend(event_graders.get(attempt.pk, ()))
        names: list[str] = []
        for person in people:
            name = _person(person)
            if name and name not in names:
                names.append(name)
        if names:
            labels[attempt.pk] = ", ".join(names)
        elif attempt.exam.exam_type in AUTO_GRADED_EXAM_TYPES:
            labels[attempt.pk] = auto_label
        else:
            labels[attempt.pk] = ""
    return labels


def _computer_display(computer, seat_number=None) -> str:
    if computer is not None:
        return computer.label or (f"#{computer.seat_number}" if computer.seat_number else "")
    return f"#{seat_number}" if seat_number else ""


def location_map(attempts) -> dict[int, tuple[str, str]]:
    """``attempt_id`` → (zal, kompüter) — boş dəyər «məlum deyil» deməkdir (≤ 4 sorğu)."""
    from apps.exams.models import ExamRoomComputer, FinalExamTicket

    attempts = [attempt for attempt in attempts if attempt.pk]
    placed = [attempt for attempt in attempts if attempt.room_id or attempt.room_computer_id]
    if placed:
        # select_related olunubsa Django təkrar sorğu etmir.
        prefetch_related_objects(placed, "room", "room_computer__room")
    result: dict[int, tuple[str, str]] = {}
    missing: list[int] = []
    for attempt in attempts:
        computer = attempt.room_computer if attempt.room_computer_id else None
        room = attempt.room if attempt.room_id else (computer.room if computer is not None else None)
        hall = room.name if room is not None else ""
        result[attempt.pk] = (hall, _computer_display(computer))
        if not hall or computer is None:
            missing.append(attempt.pk)
    if not missing:
        return result

    tickets = FinalExamTicket.objects.filter(attempt_id__in=missing).select_related("session__room")
    by_attempt = {ticket.attempt_id: ticket for ticket in tickets}
    seat_keys = {
        (ticket.session.room_id, ticket.seat_number)
        for ticket in by_attempt.values()
        if ticket.session_id and ticket.seat_number
    }
    computers = {}
    if seat_keys:
        rows = ExamRoomComputer.objects.filter(
            room_id__in={room_id for room_id, _ in seat_keys},
            seat_number__in={seat for _, seat in seat_keys},
        )
        computers = {(computer.room_id, computer.seat_number): computer for computer in rows}
    for attempt_id, ticket in by_attempt.items():
        hall, computer_text = result[attempt_id]
        room = ticket.session.room if ticket.session_id else None
        if not hall and room is not None:
            hall = room.name
        if not computer_text and ticket.seat_number:
            computer = computers.get((room.pk if room is not None else None, ticket.seat_number))
            computer_text = _computer_display(computer, ticket.seat_number)
        result[attempt_id] = (hall, computer_text)
    return result


__all__ = ["AUTO_GRADED_EXAM_TYPES", "auto_checker_label", "checked_by_map", "location_map"]
