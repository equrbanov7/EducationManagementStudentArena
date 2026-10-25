"""Jurnal hadisələri üçün tələbə bildirişləri.

Müəllim jurnala yazanda tələbəyə in-app bildiriş gedir: q/b qeydi, seminar/lab
balı, kollokvium/midterm balı, kurs işi balı, qayıb limitinə yaxınlaşma və kəsilmə.
Göndəriş ``transaction.on_commit`` ilə çağırılır (yazı uğurla commit olandan
sonra) və eyni save daxilində tələbə-başına TƏK toplu bildiriş yaradılır —
spam yoxdur. q/b bir DƏRS üçün bir dəfə bildirilir (``absent_lessons``); mətnlər push ilə telefona da
gedir (``apps/notifications/push``). Asılılıq istiqaməti: registrar → notifications (dövr yaratmır;
notifications yalnız organizations-a baxır).
"""

from __future__ import annotations

import json

from django.urls import reverse

_CTX = "registrar.notify"
#: ``metadata`` açarı — bildirişdə q/b-si bildirilmiş dərslərin id-ləri (təkrar bildirişin qarşısı).
ABSENT_LESSONS_KEY = "absent_lessons"

# Hadisə növləri (send_journal_events payload-ları).
EVENT_ABSENT = "absent"  # q/b yazıldı
EVENT_SCORE = "score"  # seminar/lab balı
EVENT_KOLLOKVIUM = "kollokvium"  # kollokvium / midterm balı
EVENT_COURSEWORK = "coursework"  # kurs işi balı
EVENT_LIMIT_WARNING = "limit_warning"  # limitin 75%-inə çatdı
EVENT_BARRED = "barred"  # limit keçildi — imtahana buraxılmır
EVENT_CORRECTED = "corrected"  # rəsmi jurnal düzəlişi (admin, sənədli)


def _line_for(event):
    """Hadisənin bildiriş sətri — :class:`LText` (oxuyan / telefon öz dilində görür) və ya ``None``."""
    from apps.notifications.public import LText, ltext_of

    kind = event["kind"]
    if kind == EVENT_ABSENT:
        lesson = event.get("lesson")
        if lesson is not None and getattr(lesson, "date", None):
            return LText("Qayıb (q/b) qeyd edildi: %(date)s", _CTX, date=lesson.date.strftime("%d.%m.%Y"))
        return LText("Qayıb (q/b) qeyd edildi", _CTX)
    if kind == EVENT_SCORE:
        return LText("Dərs balı yazıldı: %(score)s", _CTX, score=event.get("score", ""))
    if kind == EVENT_KOLLOKVIUM:
        # Komponentin adı: «Midterm» (2026/2027-dən) və ya «Kollokvium 2» (keçmiş dövrlər).
        label = event.get("label") or LText("Kollokvium", _CTX)
        if isinstance(label, str):
            label = ltext_of(label)
        return LText("%(label)s balı yazıldı: %(score)s", _CTX, label=label, score=event.get("score", ""))
    if kind == EVENT_COURSEWORK:
        return LText("Kurs işi balı yazıldı: %(score)s", _CTX, score=event.get("score", ""))
    if kind == EVENT_LIMIT_WARNING:
        return LText("Diqqət: qayıb limitinə yaxınlaşırsınız (%(hours)s saat)", _CTX, hours=event.get("hours", ""))
    if kind == EVENT_BARRED:
        return LText("Qayıb limiti keçildi — imtahana buraxılmırsınız", _CTX)
    if kind == EVENT_CORRECTED:
        return LText("Jurnalınızda rəsmi düzəliş edildi — detallar üçün jurnala baxın", _CTX)
    return None


def _absent_lesson_id(event) -> str:
    lesson = event.get("lesson") if event.get("kind") == EVENT_ABSENT else None
    return str(lesson.pk) if lesson is not None and getattr(lesson, "pk", None) else ""


def _already_notified_absences(offering, events) -> dict:
    """``{tələbə_id: {dərs_id, …}}`` — bu açılışda q/b-si ARTIQ bildirilmiş dərslər (təkrar bildiriş olmasın)."""
    from apps.notifications.public import notified_metadata_values

    student_ids = {event["enrollment"].student_id for event in events if _absent_lesson_id(event)}
    if not student_ids:
        return {}
    return notified_metadata_values(
        recipient_ids=student_ids,
        key=ABSENT_LESSONS_KEY,
        match={"event": "journal_update", "offering_id": str(offering.id)},
    )


def send_journal_events(*, offering, events) -> int:
    """Tələbə-başına qruplaşdırılmış jurnal bildirişləri yarat.

    ``events``: list of ``{"enrollment", "kind", ...payload}``. Eyni tələbənin bütün hadisələri bir bildirişdə
    birləşdirilir. q/b hadisəsi ``lesson`` daşıyırsa bir DƏRS üçün bir dəfə bildirilir: dərsin id-si
    ``metadata["absent_lessons"]``-ə yazılır və həmin dərsin q/b-si sonra yenidən yazılsa (q/b → i/e → q/b,
    düzəliş) ikinci bildiriş yaranmır. Mətn :class:`LText`-dir — kabinetdə və telefonda (push) oxuyanın dilində."""
    from apps.notifications.public import LText, create_notifications, lformat

    events = list(events or [])
    notified = _already_notified_absences(offering, events)
    by_student: dict = {}
    for event in events:
        enrollment = event["enrollment"]
        data = by_student.setdefault(enrollment.student_id, {"enrollment": enrollment, "lines": {}, "absent": []})
        lesson_id = _absent_lesson_id(event)
        if lesson_id:
            if lesson_id in notified.get(enrollment.student_id, ()) or lesson_id in data["absent"]:
                continue
            data["absent"].append(lesson_id)
        line = _line_for(event)
        if line is not None:
            # Təkrarları at, sıranı saxla (eyni deskriptor — eyni sətir).
            data["lines"].setdefault(json.dumps(line.descriptor, sort_keys=True, default=str), line)

    subject_name = offering.subject.name
    link = f"{reverse('accounts:profile')}?section=my-journal"
    # Bütün tələbələrin bildirişi TƏK toplu INSERT-də (əvvəl tələbə başına 4 ifadə).
    items = []
    for data in by_student.values():
        lines = list(data["lines"].values())
        if not lines:
            continue
        metadata = {"event": "journal_update", "offering_id": str(offering.id)}
        if data["absent"]:
            metadata[ABSENT_LESSONS_KEY] = data["absent"]
        items.append(
            {
                "recipient": data["enrollment"].student,
                "title": LText("Elektron jurnal — %(subject)s", _CTX, subject=subject_name),
                "message": lformat("\n".join("{%d}" % index for index in range(len(lines))), *lines),
                "link": link,
                "organization": offering.organization,
                "metadata": metadata,
            }
        )
    create_notifications(items)
    return len(items)
