"""Kampaniya açılanda tələbələrə in-app bildiriş — toplu, ``on_commit``.

Hər tələbə kampaniya üzrə BİR DƏFƏ xəbərdar edilir: ilk dəfə hədəfi yarananda
(ilk jurnal bağlanması). Sonrakı bağlanmalarda yalnız YENİ uyğun tələbələr
(əvvəl bağlanmış açılışlarda qeydiyyatı olmayanlar) bildiriş alır — bax
:func:`newly_eligible_students`.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import translation
from django.utils.translation import pgettext

from .. import registrar_bridge as bridge
from ..constants import EVENT_CAMPAIGN_OPENED

logger = logging.getLogger(__name__)

_CTX = "surveys.notify"
BATCH_SIZE = 1000


def eligible_student_ids(organization, period_id) -> set:
    """Dövrün bağlı jurnallarında qeydiyyatı olan bütün tələbələr."""
    return set(bridge.closed_enrollments(organization, period_id).values_list("student_id", flat=True).distinct())


def newly_eligible_students(organization, period_id, offering_ids) -> set:
    """Yeni bağlanan açılışların tələbələrindən ƏVVƏL heç bir bağlı açılışı olmayanlar."""
    offering_ids = list(offering_ids or [])
    if not offering_ids:
        return set()
    fresh = bridge.student_ids_in_offerings(organization, offering_ids)
    if not fresh:
        return set()
    earlier = set(
        bridge.closed_enrollments(organization, period_id)
        .exclude(offering_id__in=offering_ids)
        .filter(student_id__in=fresh)
        .values_list("student_id", flat=True)
        .distinct()
    )
    return fresh - earlier


def notify_campaign_opened(organization, campaign, student_ids) -> None:
    """Toplu bildiriş (``BATCH_SIZE``-lik paketlərlə, tranzaksiya commit-dən sonra)."""
    student_ids = sorted(pk for pk in set(student_ids) if pk)
    if not student_ids:
        return
    metadata = {"event": EVENT_CAMPAIGN_OPENED, "campaign_id": str(campaign.pk)}
    link = reverse("surveys:home")

    def _send():
        try:
            from apps.notifications.models import NotificationType
            from apps.notifications.public import create_notification_for_users

            User = get_user_model()
            with translation.override(settings.LANGUAGE_CODE):
                title = pgettext(_CTX, "Müəllim qiymətləndirmə sorğusu açıldı")
                message = pgettext(
                    _CTX,
                    "Semestr sonu anonim sorğusunu doldurun: müəllimlərinizi qiymətləndirin və "
                    "tədrisin yaxşılaşması üçün təklif yazın. Cavablarınız anonimdir.",
                )
            for start in range(0, len(student_ids), BATCH_SIZE):
                chunk = student_ids[start : start + BATCH_SIZE]
                create_notification_for_users(
                    recipients=list(User.objects.filter(pk__in=chunk).only("pk")),
                    title=title,
                    message=message,
                    link=link,
                    notification_type=NotificationType.SYSTEM,
                    organization=organization,
                    metadata=metadata,
                )
        except Exception:  # pragma: no cover — bildiriş əməli bloklamır
            logger.exception("survey campaign notification failed (campaign=%s)", campaign.pk)

    transaction.on_commit(_send)
