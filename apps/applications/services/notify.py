"""Bildiriş + audit yan-təsirləri.

Konvensiya (bax ``apps/appeals/services/decisions.py``): bildiriş göndərişi
əməliyyatın ÖZÜNÜ heç vaxt uçurmur — hər çağırış ``try/except`` ilə sarınıb və
``transaction.on_commit`` ilə TRANZAKSİYADAN SONRA icra olunur (rollback olan
əməl üçün bildiriş getməsin).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.urls import NoReverseMatch, reverse

from apps.notifications.models import NotificationType
from apps.notifications.public import create_notification, create_notification_for_users
from apps.organizations.unit_heads import members_covering_unit
from core.audit import log_action
from core.cache import invalidate_profile_badge_counts_cache
from core.constants import AuditAction

logger = logging.getLogger(__name__)

#: Kabinetdəki bölmə açarı — bildiriş linki bunu ``?section=`` ilə açır.
#: DƏYƏR UI ilə EYNİ olmalıdır (``sections_api.SECTION_PARTIALS``,
#: ``AJAX_SAFE_SECTIONS``, ``profile.html`` ``data-ajax-sections``,
#: ``rbac_sections.allowed_sections``) — sahib tələbi ilə açar «applications».
PROFILE_SECTION = "applications"


def application_link(application) -> str:
    try:
        return f"{reverse('accounts:profile')}?section={PROFILE_SECTION}&application={application.pk}"
    except NoReverseMatch:  # pragma: no cover — profil marşrutu həmişə var
        return ""


def _safe(callable_, *args, **kwargs):
    try:
        callable_(*args, **kwargs)
    except Exception:  # noqa: BLE001 — bildiriş nasazlığı əməli uçurmamalıdır
        logger.warning("applications: notification delivery failed", exc_info=True)


def handler_recipients(application):
    """Cari şöbəni əhatə edən emalçı istifadəçilər (təkrarsız)."""
    memberships = members_covering_unit(
        application.organization,
        application.current_scope_unit,
        role_names=application.current_unit.role_names,
    )
    seen = {}
    for membership in memberships:
        seen.setdefault(membership.user_id, membership.user)
    return list(seen.values())


def watcher_recipients(application):
    users = {}
    for watch in application.watches.select_related("unit", "scope_unit"):
        for membership in members_covering_unit(
            application.organization, watch.scope_unit, role_names=watch.unit.role_names
        ):
            users.setdefault(membership.user_id, membership.user)
    users.pop(application.created_by_id, None)
    return list(users.values())


def notify_sender(application, *, title: str, message: str = ""):
    def _send():
        _safe(
            create_notification,
            recipient=application.created_by,
            title=title,
            message=message,
            link=application_link(application),
            notification_type=NotificationType.APPLICATION,
            organization=application.organization,
            metadata={"application_id": str(application.pk), "number": application.number},
        )
        _safe(invalidate_profile_badge_counts_cache, application.created_by_id, application.organization_id)

    transaction.on_commit(_send)


def notify_users(application, recipients, *, title: str, message: str = ""):
    recipient_list = [user for user in recipients if user is not None]
    if not recipient_list:
        return

    def _send():
        _safe(
            create_notification_for_users,
            recipients=recipient_list,
            title=title,
            message=message,
            link=application_link(application),
            notification_type=NotificationType.APPLICATION,
            organization=application.organization,
            metadata={"application_id": str(application.pk), "number": application.number},
        )
        for user in recipient_list:
            _safe(invalidate_profile_badge_counts_cache, user.pk, application.organization_id)

    transaction.on_commit(_send)


def notify_current_unit(application, *, title: str, message: str = ""):
    notify_users(application, handler_recipients(application), title=title, message=message)


def audit(application, *, action: str, actor, event_kind: str, reason: str = "", changes=None, request=None):
    """Audit sətri. ``AuditAction`` mövcud dəstdən seçilir (yeni miqrasiya yox)."""
    try:
        log_action(
            action,
            user=actor,
            organization=application.organization,
            obj=application,
            changes=changes or {},
            reason=(reason or "")[:500],
            request=request,
            resource_type="application",
            resource_id=str(application.pk),
            resource_repr=f"{application.number} · {event_kind}",
        )
    except Exception:  # noqa: BLE001 — audit nasazlığı əməli uçurmamalıdır
        logger.warning("applications: audit write failed for %s", application.pk, exc_info=True)


AUDIT_CREATE = AuditAction.CREATE
AUDIT_UPDATE = AuditAction.UPDATE


__all__ = [
    "AUDIT_CREATE",
    "AUDIT_UPDATE",
    "PROFILE_SECTION",
    "application_link",
    "audit",
    "handler_recipients",
    "notify_current_unit",
    "notify_sender",
    "notify_users",
    "watcher_recipients",
]
