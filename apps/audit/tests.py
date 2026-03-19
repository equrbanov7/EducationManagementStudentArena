"""
Tests for the audit app.
"""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models
from django.test import TransactionTestCase

from core.constants import AuditAction

from .models import AuditLog

User = get_user_model()


class AuditLogSchemaCompatibilityTest(TransactionTestCase):
    """Verify AuditLog survives legacy-column schema drift."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="audit_schema_user",
            email="audit-schema@example.com",
            password="StrongPass123!",
        )
        self.content_type = ContentType.objects.get_for_model(self.user)

    def _legacy_resource_index(self):
        return models.Index(fields=["resource_type", "resource_id"], name="audit_audit_resourc_2a3aef_idx")

    def _legacy_resource_index_exists(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, AuditLog._meta.db_table)
        return self._legacy_resource_index().name in constraints

    def _remove_legacy_resource_fields(self):
        with connection.schema_editor() as schema_editor:
            if self._legacy_resource_index_exists():
                schema_editor.remove_index(AuditLog, self._legacy_resource_index())
            for field_name in ("resource_repr", "resource_id", "resource_type"):
                schema_editor.remove_field(AuditLog, AuditLog._meta.get_field(field_name))

    def _restore_legacy_resource_fields(self):
        with connection.schema_editor() as schema_editor:
            for field_name in ("resource_type", "resource_id", "resource_repr"):
                field = AuditLog._meta.get_field(field_name).clone()
                field.default = ""
                field.set_attributes_from_name(field_name)
                schema_editor.add_field(AuditLog, field)
            if not self._legacy_resource_index_exists():
                schema_editor.add_index(AuditLog, self._legacy_resource_index())

    def test_create_succeeds_when_legacy_columns_are_missing(self):
        self._remove_legacy_resource_fields()
        try:
            log = AuditLog.objects.create(
                user=self.user,
                action=AuditAction.LOGIN,
                organization=None,
                content_type=self.content_type,
                object_id=str(self.user.pk),
                resource_type="membership",
                resource_id="123",
                resource_repr="Membership #123",
            )
            self.assertEqual(log.action, AuditAction.LOGIN)
            self.assertTrue(AuditLog.objects.filter(pk=log.pk).exists())
        finally:
            self._restore_legacy_resource_fields()

    def test_basic_reads_defer_missing_legacy_columns(self):
        self._remove_legacy_resource_fields()
        try:
            log = AuditLog.objects.create(
                user=self.user,
                action=AuditAction.LOGOUT,
                organization=None,
                content_type=self.content_type,
                object_id=str(self.user.pk),
            )
            fetched = AuditLog.objects.get(pk=log.pk)
            self.assertEqual(fetched.pk, log.pk)
            self.assertEqual(fetched.action, AuditAction.LOGOUT)
            self.assertEqual(fetched.user_id, self.user.id)
        finally:
            self._restore_legacy_resource_fields()
