"""Toplu jurnal bağlama/açma bildirişi — əhatədəki müəllimlərə (distinct).

``close_journals``/``reopen_journals`` (bax ``journal_close.py``) uğurla
tamamlananda, HƏQİQƏTƏN dəyişən (``changed``) ``AssessmentScheme`` sətirlərinin
sahib olduğu açılışların müəllimlərinə TOPLU in-app bildiriş gedir — artıq
bağlı/açıq olub toxunulmayan sxemlərin müəllimi TƏKRAR xəbərdar edilmir.

``transaction.on_commit`` + try/except+logger konvensiyası (bax
``apps/registrar/schedule_manage_actions.py``).
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import pgettext

from .journal_close import scope_label

logger = logging.getLogger(__name__)

_CTX = "registrar.journal_close_notify"

EVENT_CLOSED = "journal_closed"
EVENT_REOPENED = "journal_reopened"


def _dispatch(event: str, *, organization, period, unit, instructor_ids, title: str) -> None:
    instructor_ids = [pk for pk in dict.fromkeys(instructor_ids) if pk]
    if not instructor_ids:
        return

    User = get_user_model()
    recipients = list(User.objects.filter(pk__in=instructor_ids))
    if not recipients:
        return

    metadata = {
        "event": event,
        "period_id": str(getattr(period, "pk", "")),
        "scope_unit_id": str(unit.pk) if unit is not None else "",
    }

    def _send() -> None:
        try:
            from apps.notifications.models import NotificationType
            from apps.notifications.public import create_notification_for_users

            create_notification_for_users(
                recipients=recipients,
                title=title,
                message="",
                link="",
                notification_type=NotificationType.APPROVAL,
                organization=organization,
                metadata=metadata,
            )
        except Exception:  # pragma: no cover — bildiriş əməli bloklamır
            logger.exception("journal close notification failed (event=%s)", event)

    transaction.on_commit(_send)


def notify_closed(*, organization, period, unit, instructor_ids) -> None:
    title = pgettext(_CTX, "Jurnal bağlandı: %(period)s (%(scope)s)") % {
        "period": getattr(period, "name", ""),
        "scope": scope_label(unit),
    }
    _dispatch(
        EVENT_CLOSED, organization=organization, period=period, unit=unit, instructor_ids=instructor_ids, title=title
    )


def notify_reopened(*, organization, period, unit, instructor_ids) -> None:
    title = pgettext(_CTX, "Jurnal yenidən açıldı: %(period)s (%(scope)s)") % {
        "period": getattr(period, "name", ""),
        "scope": scope_label(unit),
    }
    _dispatch(
        EVENT_REOPENED, organization=organization, period=period, unit=unit, instructor_ids=instructor_ids, title=title
    )


__all__ = ["EVENT_CLOSED", "EVENT_REOPENED", "notify_closed", "notify_reopened"]
