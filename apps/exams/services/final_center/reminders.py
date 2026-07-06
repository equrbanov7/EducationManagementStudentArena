"""final_center paketi — final imtahan xatırlatma bildirişləri.

Final oturumu yaxınlaşan (məcburi vaxt aralığı olan) tələbələrə "gəl imtahanı
ver" tipli xatırlatma göndərir. Dublikatın qarşısı ``FinalExamTicket``-in
``reminder_stage`` sahəsi ilə alınır: hər eşik (gün) üçün yalnız bir dəfə.

Tenant izolyasiyası: hər bildiriş biletin öz ``organization``-ı altında
yaradılır; global sweep bütün təşkilatları gəzir, amma sətir-sətir org-scoped.
"""

import logging

from django.conf import settings
from django.utils import timezone

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ENTRY_OPEN,
    ROOM_SESSION_STATE_PREPARED,
    TICKET_STATUS_ASSIGNED,
)
from apps.exams.models import FinalExamTicket

logger = logging.getLogger("exams.final_center.reminders")


def _thresholds():
    """Xatırlatma eşikləri (gün), azalan sırada. Konfiqurasiya olunandır."""
    raw = getattr(settings, "FINAL_EXAM_REMINDER_DAYS", (3, 1))
    return sorted({int(v) for v in raw if int(v) > 0}, reverse=True)


def _smallest_applicable(days_left, thresholds):
    """days_left <= eşik olan ƏN KİÇİK eşiyi qaytarır (yoxdursa None)."""
    applicable = None
    for threshold in thresholds:  # azalan sıra
        if days_left <= threshold:
            applicable = threshold
    return applicable


def notify_upcoming_final_exams(now=None) -> int:
    """
    Yaxınlaşan final oturumları üçün təyin olunmuş tələbələrə xatırlatma
    göndərir. Qaytarır: göndərilən bildiriş sayı.
    """
    from apps.notifications.public import create_notification

    now = now or timezone.now()
    thresholds = _thresholds()
    if not thresholds:
        return 0
    max_threshold = thresholds[0]
    horizon = now + timezone.timedelta(days=max_threshold)

    # Yalnız hələ başlamamış, giriş/hazırlıq fazasındakı oturumların, hələ
    # imtahana girməmiş (assigned) biletləri — və artıq ən kiçik eşik üçün
    # xatırlanmamış olanlar.
    tickets = FinalExamTicket.objects.filter(
        status=TICKET_STATUS_ASSIGNED,
        session__state__in=(ROOM_SESSION_STATE_PREPARED, ROOM_SESSION_STATE_ENTRY_OPEN),
        session__scheduled_start__gt=now,
        session__scheduled_start__lte=horizon,
    ).select_related("session", "session__room", "exam", "student", "organization")

    sent = 0
    for ticket in tickets.iterator():
        session = ticket.session
        days_left = (session.scheduled_start - now).total_seconds() / 86400.0
        threshold = _smallest_applicable(days_left, thresholds)
        if threshold is None:
            continue
        # Bu eşik (və ya daha kiçiyi) üçün artıq göndərilibsə keç.
        if ticket.reminder_stage and threshold >= ticket.reminder_stage:
            continue

        try:
            create_notification(
                recipient=ticket.student,
                title=_reminder_title(threshold),
                message=_reminder_message(ticket, threshold),
                link="/exams/final/",
                notification_type="exam",
                organization=ticket.organization,
            )
        except Exception:  # noqa: BLE001 — bir bildiriş xətası sweep-i dayandırmamalıdır
            logger.warning("final_center reminder göndərilmədi: ticket=%s", ticket.pk, exc_info=True)
            continue

        FinalExamTicket.objects.filter(pk=ticket.pk).update(reminder_stage=threshold)
        sent += 1

    return sent


def _reminder_title(threshold: int) -> str:
    from django.utils.translation import pgettext

    if threshold <= 1:
        return pgettext("exams.final_center.reminder", "Final imtahanınız sabah keçiriləcək")
    return pgettext("exams.final_center.reminder", "Final imtahanınız yaxınlaşır")


def _reminder_message(ticket, threshold: int) -> str:
    from django.utils.translation import pgettext

    session = ticket.session
    start = timezone.localtime(session.scheduled_start).strftime("%d.%m.%Y %H:%M")
    return pgettext(
        "exams.final_center.reminder",
        "{exam} final imtahanı {start} tarixində {room} zalında keçiriləcək. "
        "İmtahana təyin olunmuş vaxtda /exams/final/ ünvanından istifadəçi adınız və PIN ilə daxil olun.",
    ).format(exam=ticket.exam.title, start=start, room=session.room.name)


__all__ = ["notify_upcoming_final_exams"]
