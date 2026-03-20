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


# ---------------------------------------------------------------------------
# Task 7 (P1): Superadmin cross-org audit logging
# ---------------------------------------------------------------------------


class SuperadminCrossOrgAuditTest(TransactionTestCase):
    """
    Verify that ``log_superadmin_cross_org_action`` creates audit log entries
    when a superadmin operates in an organization they are not a member of.
    """

    def setUp(self):
        from apps.organizations.models import Organization
        from core.constants import OrganizationType

        self.superadmin = User.objects.create_superuser(
            username="superadmin_audit",
            email="superadmin_audit@example.com",
            password="StrongPass123!",
        )
        self.regular_user = User.objects.create_user(
            username="regular_audit",
            email="regular_audit@example.com",
            password="StrongPass123!",
        )
        self.target_org = Organization.objects.create(
            name="Cross-Org Target",
            org_type=OrganizationType.SCHOOL,
            owner=self.regular_user,
            status="active",
            is_active=True,
        )

    def _make_request(self, user, org=None, memberships=None):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        request.organization = org
        request.org_memberships = memberships or []
        return request

    def test_cross_org_action_creates_audit_log(self):
        """Cross-org access by a superadmin must generate an AuditLog entry."""
        from apps.audit.utils import log_superadmin_cross_org_action

        request = self._make_request(self.superadmin, org=self.target_org, memberships=[])
        initial_count = AuditLog.objects.count()

        log_superadmin_cross_org_action(request, action=AuditAction.VIEW)

        self.assertEqual(AuditLog.objects.count(), initial_count + 1)
        log = AuditLog.objects.latest("created_at")
        self.assertEqual(log.user_id, self.superadmin.id)
        self.assertEqual(log.organization_id, self.target_org.id)
        self.assertEqual(log.action, AuditAction.VIEW)

    def test_non_superadmin_does_not_log(self):
        """log_superadmin_cross_org_action must be a no-op for non-superadmin users."""
        from apps.audit.utils import log_superadmin_cross_org_action

        request = self._make_request(self.regular_user, org=self.target_org, memberships=[])
        initial_count = AuditLog.objects.count()

        log_superadmin_cross_org_action(request, action=AuditAction.VIEW)

        self.assertEqual(AuditLog.objects.count(), initial_count)

    def test_same_org_member_superadmin_does_not_log(self):
        """No cross-org log entry when the superadmin has membership in the org."""
        from apps.organizations.models import Membership
        from apps.audit.utils import log_superadmin_cross_org_action

        student_role = self.target_org.roles.get(name="student")
        membership = Membership.objects.create(
            user=self.superadmin,
            organization=self.target_org,
            role=student_role,
            is_active=True,
        )
        request = self._make_request(self.superadmin, org=self.target_org, memberships=[membership])
        initial_count = AuditLog.objects.count()

        log_superadmin_cross_org_action(request, action=AuditAction.VIEW)

        self.assertEqual(AuditLog.objects.count(), initial_count)

    def test_no_org_context_does_not_log(self):
        """No log entry when there is no organization context on the request."""
        from apps.audit.utils import log_superadmin_cross_org_action

        request = self._make_request(self.superadmin, org=None, memberships=[])
        initial_count = AuditLog.objects.count()

        log_superadmin_cross_org_action(request, action=AuditAction.VIEW)

        self.assertEqual(AuditLog.objects.count(), initial_count)

    def test_audit_log_captures_required_fields(self):
        """
        AuditLog entry must capture user_id, target_org_id, action, and
        be associated with a timestamp (created_at auto-set).
        """
        from apps.audit.utils import log_superadmin_cross_org_action

        request = self._make_request(self.superadmin, org=self.target_org, memberships=[])
        log_superadmin_cross_org_action(request, action=AuditAction.UPDATE, reason="Custom reason")

        log = AuditLog.objects.latest("created_at")
        self.assertEqual(log.user_id, self.superadmin.id)
        self.assertEqual(log.organization_id, self.target_org.id)
        self.assertEqual(log.action, AuditAction.UPDATE)
        self.assertIsNotNone(log.created_at)
        self.assertIn("Custom reason", log.reason)
