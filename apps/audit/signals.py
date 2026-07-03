"""
Signal handlers for the audit app.
Placeholder for future signal receivers.
"""

import logging

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.constants import AuditAction
from core.rls_pooling import rls_worker_atomic
from core.utils import get_client_ip

logger = logging.getLogger(__name__)

# Map Django admin action flags to AuditAction constants.
_ADMIN_ACTION_MAP = {
    ADDITION: AuditAction.CREATE,
    CHANGE: AuditAction.UPDATE,
    DELETION: AuditAction.DELETE,
}


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log user login events."""
    from .models import AuditLog

    try:
        with rls_worker_atomic():
            AuditLog.objects.create(
                user=user,
                action=AuditAction.LOGIN,
                content_type=ContentType.objects.get_for_model(user),
                object_id=str(user.pk),
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            )
    except Exception:
        logger.exception("Failed to create login audit log for user %s", getattr(user, "pk", "<unknown>"))


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log user logout events."""
    if user:
        from .models import AuditLog

        try:
            with rls_worker_atomic():
                AuditLog.objects.create(
                    user=user,
                    action=AuditAction.LOGOUT,
                    content_type=ContentType.objects.get_for_model(user),
                    object_id=str(user.pk),
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                )
        except Exception:
            logger.exception("Failed to create logout audit log for user %s", getattr(user, "pk", "<unknown>"))


@receiver(post_save, sender=LogEntry)
def log_admin_action(sender, instance, created, **kwargs):
    """Mirror Django admin LogEntry events into the AuditLog.

    This captures every add, change, and delete performed through the Django
    admin interface, providing a unified audit trail alongside application-level
    events.  The entry is only created once (``created=True``) because admin
    log entries are immutable after creation.
    """
    if not created:
        return

    from .models import AuditLog

    action = _ADMIN_ACTION_MAP.get(instance.action_flag, AuditAction.UPDATE)
    try:
        with rls_worker_atomic():
            AuditLog.objects.create(
                user_id=instance.user_id,
                action=action,
                content_type=instance.content_type,
                object_id=str(instance.object_id) if instance.object_id else "",
                resource_type=instance.content_type.model if instance.content_type else "",
                resource_id=str(instance.object_id) if instance.object_id else "",
                resource_repr=(instance.object_repr or "")[:500],
                reason=f"Admin: {instance.get_change_message()}"[:500],
            )
    except Exception:
        logger.exception(
            "Failed to mirror admin LogEntry %s to AuditLog",
            getattr(instance, "pk", "<unknown>"),
        )
