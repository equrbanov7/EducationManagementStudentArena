"""Dövri işlər — «Həll olunub» müraciətlərin avtomatik bağlanması.

Dizayn §3.4: müraciət sahibi nəticəni təsdiqləyir, YOXSA sistem 5 iş günü
sonra özü bağlayır. Bu funksiya çağırış mexanizmindən ASILI DEYİL: repo-da
Celery beat cədvəli yoxdur, ona görə giriş nöqtəsi idarəetmə əmridir
(``manage.py close_stale_resolved``); beat gələndə eyni funksiya çağırılır.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from ..constants import AUTO_CLOSE_WORKING_DAYS, ApplicationStatus, EventKind
from ..models import Application, ApplicationEvent
from ..sla import working_days_between
from . import notify

logger = logging.getLogger(__name__)


def stale_resolved(*, organization=None, today=None, working_days=AUTO_CLOSE_WORKING_DAYS):
    today = today or timezone.localdate()
    queryset = Application.objects.filter(status=ApplicationStatus.RESOLVED, resolved_at__isnull=False)
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    return [app for app in queryset if working_days_between(app.resolved_at.date(), today) >= working_days]


def close_stale_resolved(*, organization=None, today=None, working_days=AUTO_CLOSE_WORKING_DAYS) -> int:
    """Vaxtı keçmiş «Həll olunub» müraciətləri bağlayır; bağlanan sayı qaytarır."""
    closed = 0
    for application in stale_resolved(organization=organization, today=today, working_days=working_days):
        with transaction.atomic():
            fresh = Application.objects.select_for_update().get(pk=application.pk)
            if fresh.status != ApplicationStatus.RESOLVED.value:
                continue
            old = fresh.status
            fresh.status = ApplicationStatus.CLOSED
            fresh.closed_at = timezone.now()
            fresh.last_activity_at = timezone.now()
            fresh.save(update_fields=["status", "closed_at", "last_activity_at", "updated_at"])
            ApplicationEvent.objects.create(
                organization=fresh.organization,
                application=fresh,
                kind=EventKind.CLOSED,
                actor=None,
                actor_name="Sistem",
                actor_role_name="system",
                old_status=old,
                new_status=fresh.status,
                text=f"Cavabdan sonra {working_days} iş günü ərzində etiraz olmadı — avtomatik bağlandı.",
            )
            notify.audit(
                fresh,
                action=notify.AUDIT_UPDATE,
                actor=None,
                event_kind=EventKind.CLOSED,
                reason="auto_close_stale_resolved",
            )
            closed += 1
    if closed:
        logger.info("applications: auto-closed %s resolved applications", closed)
    return closed


__all__ = ["close_stale_resolved", "stale_resolved"]
