"""Kollokvium bal-yazma pəncərəsi dəyişikliyi — offering müəllimlərinə bildiriş.

Pəncərə aktivləşəndə/bağlananda, ya da aktiv ikən tarixləri dəyişəndə (əlavə
gün YOX, birbaşa tarix redaktəsi) həmin dövrün açılışlarının
(``CourseOffering``) müəllimlərinə TOPLU in-app bildiriş gedir.

Modul sərhədi: bu fayl ``apps/registrar/``-dadır — ``accounts → registrar``
idxalına icazə var, ƏKSİNƏ YOX (``registrar`` heç vaxt ``apps.accounts``
idxal etmir). Göndəriş ``transaction.on_commit`` + try/except+logger
konvensiyası ilədir (bax ``apps/registrar/schedule_manage_actions.py``).
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import pgettext

logger = logging.getLogger(__name__)

_CTX = "registrar.kollokvium_notify"

EVENT_OPENED = "kollokvium_window_opened"
EVENT_CLOSED = "kollokvium_window_closed"
EVENT_EXTENDED = "kollokvium_window_extended"


def _teacher_recipients(window) -> list:
    """Bu dövrdə (period) aktiv açılışı olan müəllimlər (distinct)."""
    from apps.registrar.models import CourseOffering

    User = get_user_model()
    instructor_ids = (
        CourseOffering.objects.filter(
            organization=window.organization,
            period=window.period,
            instructor__isnull=False,
        )
        .values_list("instructor_id", flat=True)
        .distinct()
    )
    return list(User.objects.filter(pk__in=list(instructor_ids)))


def _dispatch(event: str, window, title: str) -> None:
    recipients = _teacher_recipients(window)
    if not recipients:
        return

    organization = window.organization
    metadata = {"event": event, "window_id": str(window.pk), "k_index": window.k_index}

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
            logger.exception("kollokvium window notification failed (event=%s)", event)

    transaction.on_commit(_send)


def notify_window_opened(window) -> None:
    """Pəncərə aktivləşdi (yeni yaradılıb aktivləşib və ya toggle ilə açılıb)."""
    title = pgettext(_CTX, "Kollokvium K%(n)s bal-yazma pəncərəsi açıldı: %(opens)s–%(closes)s") % {
        "n": window.k_index + 1,
        "opens": window.opens_on,
        "closes": window.closes_on,
    }
    _dispatch(EVENT_OPENED, window, title)


def notify_window_closed(window) -> None:
    """Pəncərə deaktivləşdirildi (toggle ilə bağlanıb)."""
    title = pgettext(_CTX, "Kollokvium K%(n)s bal-yazma pəncərəsi bağlandı") % {"n": window.k_index + 1}
    _dispatch(EVENT_CLOSED, window, title)


def notify_window_extended(window) -> None:
    """Aktiv pəncərənin tarixləri dəyişdi (uzadıldı/qısaldıldı)."""
    title = pgettext(_CTX, "Kollokvium K%(n)s bal-yazma pəncərəsinin tarixi dəyişdi: %(opens)s–%(closes)s") % {
        "n": window.k_index + 1,
        "opens": window.opens_on,
        "closes": window.closes_on,
    }
    _dispatch(EVENT_EXTENDED, window, title)


__all__ = [
    "EVENT_CLOSED",
    "EVENT_EXTENDED",
    "EVENT_OPENED",
    "notify_window_closed",
    "notify_window_extended",
    "notify_window_opened",
]
