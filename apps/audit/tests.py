"""
Tests for the audit app.
"""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.test.client import Client

from core.constants import AuditAction

from .models import AuditLog
from .utils import log_action

User = get_user_model()


# ---------------------------------------------------------------------------
# AuditLog model unit tests
# ---------------------------------------------------------------------------


class AuditLogModelTest(TestCase):
    """Basic creation, __str__, and get_resource_display coverage."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="audit_model_user",
            email="audit_model@example.com",
            password="StrongPass123!",
        )
        self.content_type = ContentType.objects.get_for_model(self.user)

    def test_str_includes_username_and_action(self):
        log = AuditLog.objects.create(
            user=self.user,
            action=AuditAction.LOGIN,
        )
        result = str(log)
        self.assertIn(self.user.username, result)
        self.assertIn(AuditAction.LOGIN, result)

    def test_str_with_anonymous_user(self):
        log = AuditLog.objects.create(user=None, action=AuditAction.VIEW)
        self.assertIn("Anonymous", str(log))

    def test_get_resource_display_with_content_object(self):
        log = AuditLog.objects.create(
            user=self.user,
            action=AuditAction.VIEW,
            content_type=self.content_type,
            object_id=str(self.user.pk),
        )
        display = log.get_resource_display()
        self.assertIn(self.user.username, display)

    def test_get_resource_display_falls_back_to_resource_repr(self):
        log = AuditLog.objects.create(
            user=self.user,
            action=AuditAction.VIEW,
            resource_repr="My Resource",
        )
        self.assertEqual(log.get_resource_display(), "My Resource")

    def test_get_resource_display_falls_back_to_resource_type_and_id(self):
        log = AuditLog.objects.create(
            user=self.user,
            action=AuditAction.VIEW,
            resource_type="course",
            resource_id="42",
        )
        display = log.get_resource_display()
        self.assertIn("course", display)
        self.assertIn("42", display)

    def test_get_resource_display_unknown_when_nothing_set(self):
        log = AuditLog.objects.create(user=self.user, action=AuditAction.VIEW)
        self.assertEqual(log.get_resource_display(), "Unknown Resource")

    def test_default_ordering_most_recent_first(self):
        log1 = AuditLog.objects.create(user=self.user, action=AuditAction.CREATE)
        log2 = AuditLog.objects.create(user=self.user, action=AuditAction.UPDATE)
        qs = AuditLog.objects.filter(user=self.user)
        self.assertEqual(qs.first(), log2)
        self.assertEqual(qs.last(), log1)


# ---------------------------------------------------------------------------
# log_action utility tests
# ---------------------------------------------------------------------------


class LogActionUtilityTest(TestCase):
    """Test the log_action() helper."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="log_action_user",
            email="log_action@example.com",
            password="StrongPass123!",
        )
        self.factory = RequestFactory()

    def test_log_action_creates_entry(self):
        initial_count = AuditLog.objects.count()
        log = log_action(action=AuditAction.VIEW, user=self.user)
        self.assertEqual(AuditLog.objects.count(), initial_count + 1)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, AuditAction.VIEW)

    def test_log_action_with_object(self):
        log = log_action(action=AuditAction.UPDATE, user=self.user, obj=self.user)
        ct = ContentType.objects.get_for_model(self.user)
        self.assertEqual(log.content_type, ct)
        self.assertEqual(log.object_id, str(self.user.pk))

    def test_log_action_captures_request_ip_and_user_agent(self):
        request = self.factory.get("/", HTTP_USER_AGENT="TestAgent/1.0", REMOTE_ADDR="192.168.1.100")
        log = log_action(action=AuditAction.VIEW, user=self.user, request=request)
        self.assertEqual(log.user_agent, "TestAgent/1.0")
        self.assertIsNotNone(log.ip_address)

    def test_log_action_with_old_and_new_values(self):
        log = log_action(
            action=AuditAction.UPDATE,
            user=self.user,
            old_values={"title": "Old"},
            new_values={"title": "New"},
            changes={"title": {"old": "Old", "new": "New"}},
        )
        self.assertEqual(log.old_values["title"], "Old")
        self.assertEqual(log.new_values["title"], "New")
        self.assertIn("title", log.changes)

    def test_log_action_with_reason(self):
        log = log_action(action=AuditAction.DELETE, user=self.user, reason="Test deletion")
        self.assertIn("Test deletion", log.reason)

    def test_log_action_without_user_is_allowed(self):
        log = log_action(action=AuditAction.VIEW, user=None)
        self.assertIsNone(log.user)
        self.assertEqual(log.action, AuditAction.VIEW)


# ---------------------------------------------------------------------------
# Login / Logout signal handler tests
# ---------------------------------------------------------------------------


class AuditSignalTest(TestCase):
    """Test that login and logout events create AuditLog entries."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="signal_user",
            email="signal_user@example.com",
            password="StrongPass123!",
        )

    def test_login_creates_audit_log(self):
        initial_count = AuditLog.objects.filter(action=AuditAction.LOGIN, user=self.user).count()
        self.client.login(username="signal_user", password="StrongPass123!")
        self.assertEqual(
            AuditLog.objects.filter(action=AuditAction.LOGIN, user=self.user).count(),
            initial_count + 1,
        )

    def test_logout_creates_audit_log(self):
        self.client.force_login(self.user)
        initial_count = AuditLog.objects.filter(action=AuditAction.LOGOUT, user=self.user).count()
        self.client.logout()
        self.assertEqual(
            AuditLog.objects.filter(action=AuditAction.LOGOUT, user=self.user).count(),
            initial_count + 1,
        )


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
        from apps.audit.utils import log_superadmin_cross_org_action
        from apps.organizations.models import Membership

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
