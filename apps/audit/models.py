"""
Models for the audit app.
"""

import logging
import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import connections, models

from core.constants import AuditAction

logger = logging.getLogger(__name__)


class AuditLogManager(models.Manager):
    """
    Keep audit log reads and writes working during schema drift windows.

    Some environments may still have the `audit.0003` table shape during a
    rolling deploy, which means the legacy resource columns are absent even
    though the model expects them. When that happens, defer those fields on
    reads and omit them from inserts until the repair migration is applied.
    """

    _LEGACY_RESOURCE_FIELDS = frozenset({"resource_type", "resource_id", "resource_repr"})
    _compat_warning_emitted = False

    def _missing_field_names(self, using: str) -> set[str]:
        connection = connections[using]
        table_name = self.model._meta.db_table
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, table_name)
        normalize = connection.introspection.identifier_converter
        existing_columns = {normalize(column.name) for column in description}
        return {
            field.name
            for field in self.model._meta.local_concrete_fields
            if not field.generated and normalize(field.column) not in existing_columns
        }

    def get_queryset(self):
        queryset = super().get_queryset()
        missing_legacy_fields = self._missing_field_names(queryset.db) & self._LEGACY_RESOURCE_FIELDS
        if missing_legacy_fields:
            return queryset.defer(*sorted(missing_legacy_fields))
        return queryset

    def create(self, **kwargs):
        using = self.db
        missing_field_names = self._missing_field_names(using)
        if not missing_field_names:
            return super().create(**kwargs)

        obj = self.model(**kwargs)
        fields = [
            field
            for field in self.model._meta.local_concrete_fields
            if not field.generated
            and field.name not in missing_field_names
            and (obj.pk is not None or field is not self.model._meta.auto_field)
        ]
        returning_fields = [
            field for field in self.model._meta.db_returning_fields if field.name not in missing_field_names
        ]
        results = super().get_queryset()._insert(
            [obj],
            fields=fields,
            returning_fields=returning_fields,
            using=using,
            raw=False,
        )
        if results:
            for value, field in zip(results[0], returning_fields):
                setattr(obj, field.attname, value)
        obj._state.adding = False
        obj._state.db = using

        if not self._compat_warning_emitted and missing_field_names & self._LEGACY_RESOURCE_FIELDS:
            logger.warning(
                "AuditLog table is missing legacy resource columns; compatibility mode is active until migrations repair the schema."
            )
            self._compat_warning_emitted = True
        return obj


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

    # Legacy resource fields remain available because large parts of the app
    # and audit queries still filter by this denormalized metadata.
    resource_type = models.CharField(max_length=100, blank=True)
    resource_id = models.CharField(max_length=255, blank=True)
    resource_repr = models.CharField(max_length=500, blank=True)

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

    objects = AuditLogManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["resource_type", "resource_id"]),
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
        elif self.resource_repr:
            return self.resource_repr
        elif self.resource_type and self.resource_id:
            return f"{self.resource_type} #{self.resource_id}"
        elif self.content_type and self.object_id:
            return f"{self.content_type.model} #{self.object_id}"
        return "Unknown Resource"
