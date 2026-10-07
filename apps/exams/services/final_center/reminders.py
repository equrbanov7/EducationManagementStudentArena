"""final_center paketi — final imtahan xatırlatma bildirişləri.

Final oturumu yaxınlaşan (məcburi vaxt aralığı olan) tələbələrə "gəl imtahanı
ver" tipli xatırlatma göndərir. Dublikatın qarşısı ``FinalExamTicket``-in
``reminder_stage`` sahəsi ilə alınır: hər eşik (gün) üçün yalnız bir dəfə.

Tenant izolyasiyası: hər bildiriş biletin öz ``organization``-ı altında
yaradılır; global sweep bütün təşkilatları gəzir, amma sətir-sətir org-scoped.

Fon işi tutumu 2026-10-07: əvvəl hər bilet üçün ayrıca ``INSERT`` (bildiriş) +
``UPDATE`` (``reminder_stage``) idi — imtahan həftəsində 3 final × 2 000 tələbə
= 6 000 xatırlatma bir saatlıq icrada 12 000 sorğu / ~26 s, hamısı BİR
``rls_worker_atomic`` daxilində (``RLS_TRANSACTION_SCOPED`` açıq olanda 6 000
bilet sətri 26 s kilidli qalırdı — final mərkəzinin PIN/oturum yazıları
gözləyirdi). İndi biletlər (imtahan, təşkilat, eşik) üzrə qruplaşdırılır və
``CHUNK_SIZE``-lıq hissələrlə işlənir: hər hissə öz qısa tranzaksiyasında
``SKIP LOCKED`` ilə iddia olunur → bir toplu ``bulk_create`` + bir ``UPDATE``.
Bildiriş yazılmasa hissə geri qaytarılır (mərhələ yazılmır) — növbəti icra
yenidən cəhd edir (əvvəlki «bilet-bilet» semantikası ilə eyni).
"""

import logging
from collections import defaultdict
from contextlib import nullcontext

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.exams.domain.final_center import TICKET_STATUS_ASSIGNED
from apps.exams.models import FinalExamTicket

logger = logging.getLogger("exams.final_center.reminders")

#: Bir tranzaksiyada iddia olunan bilet sayı (kilid müddəti qısa qalsın).
CHUNK_SIZE = 500


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


def notify_upcoming_final_exams(now=None, *, scope=None) -> int:
    """
    Yaxınlaşan final oturumları üçün təyin olunmuş tələbələrə xatırlatma
    göndərir. Qaytarır: göndərilən bildiriş sayı.

    ``scope`` — hər DB addımını (namizəd sorğusu və hər hissə) saran kontekst
    fabriki; Celery task-ı ``rls_worker_atomic() + bypass_rls()`` ötürür.
    """
    now = now or timezone.now()
    thresholds = _thresholds()
    if not thresholds:
        return 0
    scope = scope or nullcontext
    horizon = now + timezone.timedelta(days=thresholds[0])

    # Oturum sisteminin ləğvindən sonra (2026-07) xatırlatma İMTAHANIN öz
    # cədvəlinə (``exam.start_datetime``) əsaslanır — bilet giriş anına qədər
    # zala qoşulmur. Yalnız hələ imtahana girməmiş (assigned) biletlər, imtahanı
    # aktiv və yaxınlaşan olanlar.
    with scope():
        tickets = list(
            FinalExamTicket.objects.filter(
                status=TICKET_STATUS_ASSIGNED,
                exam__is_active=True,
                exam__start_datetime__gt=now,
                exam__start_datetime__lte=horizon,
            )
            .select_related("exam", "organization")
            .only(
                "pk",
                "student",
                "reminder_stage",
                "exam",
                "exam__title",
                "exam__start_datetime",
                "organization",
                "organization__slug",
            )
            .order_by("pk")
        )

    groups = defaultdict(list)
    for ticket in tickets:
        days_left = (ticket.exam.start_datetime - now).total_seconds() / 86400.0
        threshold = _smallest_applicable(days_left, thresholds)
        if threshold is None:
            continue
        # Bu eşik (və ya daha kiçiyi) üçün artıq göndərilibsə keç.
        if ticket.reminder_stage and threshold >= ticket.reminder_stage:
            continue
        groups[(ticket.exam_id, ticket.organization_id, threshold)].append(ticket)

    sent = 0
    for (_exam_id, _org_id, threshold), rows in groups.items():
        for start in range(0, len(rows), CHUNK_SIZE):
            sent += _send_chunk(rows[start : start + CHUNK_SIZE], threshold, scope)
    return sent


def _send_chunk(rows, threshold, scope) -> int:
    """Bir hissə: ``SKIP LOCKED`` iddia → toplu bildiriş → toplu mərhələ yazısı (bir tranzaksiya)."""
    from apps.notifications.public import create_notification_for_users

    sample = rows[0]
    try:
        with scope(), transaction.atomic():
            # Paralel icra / əl ilə yazı eyni bileti tutubsa ötürülür; mərhələ filtri yenidən
            # tətbiq olunur ki, bu arada göndərilmiş xatırlatma təkrarlanmasın.
            claimed = list(
                FinalExamTicket.objects.select_for_update(skip_locked=True)
                .filter(pk__in=[row.pk for row in rows], status=TICKET_STATUS_ASSIGNED)
                .filter(Q(reminder_stage=0) | Q(reminder_stage__gt=threshold))
                .values_list("pk", "student_id")
            )
            if not claimed:
                return 0
            recipients = list(get_user_model().objects.filter(pk__in=[student for _pk, student in claimed]).only("pk"))
            create_notification_for_users(
                recipients=recipients,
                title=_reminder_title(threshold),
                message=_reminder_message(sample, threshold),
                link="/exams/final/",
                notification_type="exam",
                organization=sample.organization,
            )
            FinalExamTicket.objects.filter(pk__in=[pk for pk, _student in claimed]).update(reminder_stage=threshold)
            return len(recipients)
    except Exception:  # noqa: BLE001 — bir hissənin xətası qalan hissələri dayandırmamalıdır
        logger.warning(
            "final_center reminder hissəsi göndərilmədi: exam=%s tickets=%d", sample.exam_id, len(rows), exc_info=True
        )
        return 0


def _reminder_title(threshold: int) -> str:
    from django.utils.translation import pgettext

    if threshold <= 1:
        return pgettext("exams.final_center.reminder", "Final imtahanınız sabah keçiriləcək")
    return pgettext("exams.final_center.reminder", "Final imtahanınız yaxınlaşır")


def _reminder_message(ticket, threshold: int) -> str:
    from django.utils.translation import pgettext

    start = timezone.localtime(ticket.exam.start_datetime).strftime("%d.%m.%Y %H:%M")
    return pgettext(
        "exams.final_center.reminder",
        "{exam} final imtahanı {start} tarixində keçiriləcək. İmtahan zalındakı "
        "kompüterdən /exams/final/ ünvanından istifadəçi adınız və PIN ilə daxil olun.",
    ).format(exam=ticket.exam.title, start=start)


__all__ = ["notify_upcoming_final_exams"]
