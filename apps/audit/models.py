"""
Models for the audit app.
"""

import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.constants import AuditAction


class AuditLog(models.Model):
    """
    Model to track all user actions and system events.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=AuditAction.CHOICES)

    # Generic relation to any model
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    object_id = models.CharField(max_length=255, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # Change tracking
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    changes = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)

    # Request metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    request_id = models.UUIDField(null=True, blank=True)

    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["request_id"]),
        ]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        user_str = self.user.username if self.user else "Anonymous"
        action_str = self.get_action_display()
        return f"{user_str} - {action_str} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    def get_resource_display(self):
        """Get a display string for the resource."""
        if self.content_object:
            return str(self.content_object)
        elif self.content_type and self.object_id:
            return f"{self.content_type.model} #{self.object_id}"
        return "Unknown Resource"
