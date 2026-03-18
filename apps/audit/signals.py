"""
Signal handlers for the audit app.
Placeholder for future signal receivers.
"""

import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.contenttypes.models import ContentType
from django.dispatch import receiver

from core.constants import AuditAction
from core.utils import get_client_ip

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log user login events."""
    from .models import AuditLog

    try:
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
