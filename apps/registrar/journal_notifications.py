"""Jurnal hadisələri üçün tələbə bildirişləri.

Müəllim jurnala yazanda tələbəyə in-app bildiriş gedir: q/b qeydi, seminar/lab
balı, kollokvium balı, kurs işi balı, qayıb limitinə yaxınlaşma və kəsilmə.
Göndəriş ``transaction.on_commit`` ilə çağırılır (yazı uğurla commit olandan
sonra) və eyni save daxilində tələbə-başına TƏK toplu bildiriş yaradılır —
spam yoxdur. Asılılıq istiqaməti: registrar → notifications (dövr yaratmır;
notifications yalnız organizations-a baxır).
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

# Hadisə növləri (send_journal_events payload-ları).
EVENT_ABSENT = "absent"  # q/b yazıldı
EVENT_SCORE = "score"  # seminar/lab balı
EVENT_KOLLOKVIUM = "kollokvium"  # kollokvium balı
EVENT_COURSEWORK = "coursework"  # kurs işi balı
EVENT_LIMIT_WARNING = "limit_warning"  # limitin 75%-inə çatdı
EVENT_BARRED = "barred"  # limit keçildi — imtahana buraxılmır
EVENT_CORRECTED = "corrected"  # rəsmi jurnal düzəlişi (admin, sənədli)


def _line_for(event) -> str:
    kind = event["kind"]
    if kind == EVENT_ABSENT:
        return pgettext("registrar.notify", "Qayıb (q/b) qeyd edildi")
    if kind == EVENT_SCORE:
        return pgettext("registrar.notify", "Dərs balı yazıldı: %(score)s") % {"score": event.get("score", "")}
    if kind == EVENT_KOLLOKVIUM:
        return pgettext("registrar.notify", "Kollokvium balı yazıldı: %(score)s") % {"score": event.get("score", "")}
    if kind == EVENT_COURSEWORK:
        return pgettext("registrar.notify", "Kurs işi balı yazıldı: %(score)s") % {"score": event.get("score", "")}
    if kind == EVENT_LIMIT_WARNING:
        return pgettext("registrar.notify", "Diqqət: qayıb limitinə yaxınlaşırsınız (%(hours)s saat)") % {
            "hours": event.get("hours", "")
        }
    if kind == EVENT_BARRED:
        return pgettext("registrar.notify", "Qayıb limiti keçildi — imtahana buraxılmırsınız")
    if kind == EVENT_CORRECTED:
        return pgettext("registrar.notify", "Jurnalınızda rəsmi düzəliş edildi — detallar üçün jurnala baxın")
    return ""


def send_journal_events(*, offering, events) -> int:
    """Tələbə-başına qruplaşdırılmış jurnal bildirişləri yarat.

    ``events``: list of ``{"enrollment", "kind", ...payload}``. Eyni tələbənin
    bütün hadisələri bir bildirişdə birləşdirilir."""
    from apps.notifications.services.crud import create_notification

    by_student: dict = {}
    for event in events or []:
        enrollment = event["enrollment"]
        by_student.setdefault(enrollment.student_id, {"enrollment": enrollment, "lines": []})
        line = _line_for(event)
        if line:
            by_student[enrollment.student_id]["lines"].append(line)

    sent = 0
    subject_name = offering.subject.name
    link = f"{reverse('accounts:profile')}?section=my-journal"
    for data in by_student.values():
        lines = data["lines"]
        if not lines:
            continue
        title = pgettext("registrar.notify", "Elektron jurnal — %(subject)s") % {"subject": subject_name}
        create_notification(
            recipient=data["enrollment"].student,
            title=title,
            message="\n".join(dict.fromkeys(lines)),  # təkrarları at, sıranı saxla
            link=link,
            organization=offering.organization,
            metadata={"event": "journal_update", "offering_id": str(offering.id)},
        )
        sent += 1
    return sent
