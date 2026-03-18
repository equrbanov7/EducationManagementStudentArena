"""
Helper functions for the audit app.
"""

from django.contrib.contenttypes.models import ContentType

from core.constants import AuditAction
from core.utils import get_client_ip

from .models import AuditLog


def log_action(
    action,
    user=None,
    organization=None,
    obj=None,
    old_values=None,
    new_values=None,
    changes=None,
    reason="",
    request=None,
):
    """
    Create an audit log entry.

    Args:
        action: Action constant from AuditAction
        user: User performing the action
        organization: Organization context
        obj: Object being acted upon
        old_values: Dictionary of old values (for updates)
        new_values: Dictionary of new values (for updates/creates)
        changes: Dictionary of specific changes
        reason: Reason for the action
        request: HTTP request object (for IP and user agent)

    Returns:
        Created AuditLog instance
    """
    log_data = {
        "action": action,
        "user": user,
        "organization": organization,
        "old_values": old_values,
        "new_values": new_values,
        "changes": changes,
        "reason": reason,
    }

    # Add object information if provided
    if obj:
        log_data["content_type"] = ContentType.objects.get_for_model(obj)
        log_data["object_id"] = str(obj.pk)

    # Add request information if provided
    if request:
        log_data["ip_address"] = get_client_ip(request)
        log_data["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:500]

    return AuditLog.objects.create(**log_data)


class AuditLogMixin:
    """
    Mixin for models to automatically log save and delete actions.
    Add this mixin to models that should be audited.
    """

    def save(self, *args, **kwargs):
        """Override save to create audit log entries."""
        # Determine if this is a create or update
        is_new = self.pk is None

        # For updates, capture old values
        old_values = None
        if not is_new:
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
                old_values = self._get_field_values(old_instance)
            except self.__class__.DoesNotExist:
                pass

        # Save the instance
        super().save(*args, **kwargs)

        # Create audit log
        action = AuditAction.CREATE if is_new else AuditAction.UPDATE
        new_values = self._get_field_values(self)

        # Calculate changes if updating
        changes = None
        if old_values and new_values:
            changes = {}
            for key, new_val in new_values.items():
                old_val = old_values.get(key)
                if old_val != new_val:
                    changes[key] = {"old": old_val, "new": new_val}

        log_action(
            action=action,
            obj=self,
            old_values=old_values,
            new_values=new_values,
            changes=changes,
        )

    def delete(self, *args, **kwargs):
        """Override delete to create audit log entry."""
        old_values = self._get_field_values(self)

        # Delete the instance
        result = super().delete(*args, **kwargs)

        # Create audit log
        log_action(
            action=AuditAction.DELETE,
            obj=self,
            old_values=old_values,
        )

        return result

    def _get_field_values(self, instance):
        """Get dictionary of field values for an instance."""
        values = {}
        for field in instance._meta.fields:
            field_name = field.name
            try:
                value = getattr(instance, field_name)
                # Convert to string for JSON serialization
                if value is not None:
                    values[field_name] = str(value)
                else:
                    values[field_name] = None
            except Exception:
                # Skip fields that can't be accessed
                pass
        return values
