"""Sorğu qurucusu (2026-09-30) — sorğu açılanda auditoriyaya in-app bildiriş (e-poçt YOX).

Hər sorğu üçün BİR DƏFƏ: ``Survey.notified_at`` atomik bayraqdır (``UPDATE … WHERE notified_at IS
NULL``) — paralel çağırış ikinci bildiriş göndərmir. Tetiklər: dərc anı (açılış bu gün və ya
keçmişdədirsə), qurucu siyahısının açılışı və ``surveys_notify_due`` əmri / Celery tapşırığı
(``surveys.notify_due_surveys`` — gələcək tarixli açılışlar üçün).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import pgettext

from ..constants import EVENT_SURVEY_OPENED, SurveyKind, SurveyStatus
from .audience import audience_user_ids

logger = logging.getLogger(__name__)
_CTX = "surveys.notify"
BATCH_SIZE = 1000


def _claim(survey) -> bool:
    from ..models import Survey

    return bool(Survey.objects.filter(pk=survey.pk, notified_at__isnull=True).update(notified_at=timezone.now()))


def notify_if_due(survey) -> int:
    """Açılış günü gəlibsə bildirişi planlaşdırır (``on_commit``); alıcı sayını qaytarır."""
    today = timezone.localdate()
    if survey.is_teacher_evaluation or survey.status != SurveyStatus.PUBLISHED or survey.notified_at:
        return 0
    if not survey.is_active_on(today) or not _claim(survey):
        return 0
    recipients = sorted(audience_user_ids(survey))
    if not recipients:
        return 0
    survey_id, organization = survey.pk, survey.organization
    title_value, mandatory, closes_on = survey.title, survey.mandatory, survey.closes_on
    link = reverse("surveys:take", args=[survey_id])

    def _send():
        try:
            from apps.notifications.models import NotificationType
            from apps.notifications.public import create_notification_for_users

            User = get_user_model()
            with translation.override(settings.LANGUAGE_CODE):
                title = pgettext(_CTX, "Yeni sorğu: %(title)s") % {"title": title_value[:120]}
                if mandatory:
                    message = pgettext(_CTX, "Məcburi sorğu — son tarix %(day)s. Kabinetdə «Sorğular» bölməsinə keçin.")
                else:
                    message = pgettext(_CTX, "Könüllü sorğu — son tarix %(day)s. Fikriniz bizim üçün vacibdir.")
                message = message % {"day": closes_on.strftime("%d.%m.%Y") if closes_on else "—"}
            for start in range(0, len(recipients), BATCH_SIZE):
                chunk = recipients[start : start + BATCH_SIZE]
                create_notification_for_users(
                    recipients=list(User.objects.filter(pk__in=chunk).only("pk")),
                    title=title,
                    message=message,
                    link=link,
                    notification_type=NotificationType.SYSTEM,
                    organization=organization,
                    metadata={"event": EVENT_SURVEY_OPENED, "survey_id": str(survey_id)},
                )
        except Exception:  # pragma: no cover — bildiriş əməli bloklamır
            logger.exception("survey opened notification failed (survey=%s)", survey_id)

    transaction.on_commit(_send)
    return len(recipients)


def notify_due(organization=None) -> int:
    """Açılış günü gəlmiş, hələ bildirilməmiş bütün dərc olunmuş sorğular."""
    from ..models import Survey

    queryset = (
        Survey.objects.filter(status=SurveyStatus.PUBLISHED, notified_at__isnull=True)
        .exclude(kind=SurveyKind.TEACHER_EVALUATION)
        .filter(opens_on__lte=timezone.localdate())
        .select_related("organization")
    )
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    total = 0
    for survey in queryset[:50]:
        total += notify_if_due(survey)
    return total
