from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.accounts.views._helpers.rbac import _collect_actor_permissions
from apps.applications.services.access import active_memberships
from apps.exams.export_registry import run_export
from apps.organizations.middleware import OrganizationMiddleware
from apps.organizations.models import Membership, Role
from apps.organizations.scoping import get_permission_scope
from apps.organizations.services import get_active_memberships
from apps.organizations.tests.test_request_membership_snapshot import _org, _run_middleware
from core.permissions import request_has_permission
from core.tenancy import restore_request_organization_from_profile

User = get_user_model()


class DisabledRoleAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("role_fixture_owner")
        cls.user = User.objects.create_user("role_fixture_member")
        cls.org = _org("role-fixture", owner)
        cls.other = _org("role-fixture-other", owner)
        cls.center = cls.org.roles.get(name="exam_center_head")
        cls.center.permissions = ["exam.configure"]
        cls.center.save(update_fields=["permissions"])
        cls.other_center = cls.other.roles.get(name="exam_center_head")
        cls.teacher = cls.org.roles.get(name="teacher")
        cls.teacher.permissions = ["journal.view"]
        cls.teacher.save(update_fields=["permissions"])
        for org, role in ((cls.org, cls.center), (cls.org, cls.teacher), (cls.other, cls.other_center)):
            Membership.objects.create(organization=org, role=role, user=cls.user, is_active=True)

    def test_role_toggle_refreshes_user_request_scope_snapshot_and_navbar(self):
        request = _run_middleware(self.user, self.org.slug)
        self.assertTrue(request_has_permission(request, "exam.configure"))
        self.assertIn("exam.configure", _collect_actor_permissions(self.user, self.org)[0])
        self.assertTrue(self.user.is_exam_center)
        self.assertTrue(get_permission_scope(self.user, self.org, "exam.configure", request=request).is_org_wide)
        self.assertIn(self.center.pk, {m.role_id for m in active_memberships(self.user, self.org)})
        # Fill the shared navbar cache before the administrator's bulk toggle.
        cache.clear()
        OrganizationMiddleware._cached_active_memberships(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            Role.objects.filter(pk=self.center.pk).update(is_active=False)
        self.assertFalse(request_has_permission(request, "exam.configure"))
        self.assertTrue(request_has_permission(request, "journal.view"))
        self.assertFalse(self.user.is_exam_center)
        self.assertNotIn("exam.configure", _collect_actor_permissions(self.user, self.org)[0])
        self.assertFalse(get_permission_scope(self.user, self.org, "exam.configure", request=request).is_org_wide)
        self.assertEqual([m.role_id for m in active_memberships(self.user, self.org)], [self.teacher.pk])
        self.assertEqual([m.role_id for m in get_active_memberships(self.user, self.org)], [self.teacher.pk])
        switched = {m.role_id for m in OrganizationMiddleware._cached_active_memberships(self.user)}
        self.assertEqual(switched, {self.teacher.pk, self.other_center.pk})
        self.assertEqual(
            [m.role_id for m in _run_middleware(self.user, self.org.slug).org_memberships], [self.teacher.pk]
        )
        self.center.is_active = True
        self.center.save(update_fields=["is_active"])
        self.assertTrue(request_has_permission(request, "exam.configure"))

    def test_profile_fallback_and_worker_use_only_current_enabled_roles(self):
        request = _run_middleware(self.user, self.org.slug)
        with patch("apps.exams.views.exam_center.statistics_export.build_stats_xlsx", return_value="ok") as build:
            self.assertEqual(
                run_export("exam_center_stats_xlsx", user=self.user, organization=self.org, params={}), "ok"
            )
            self.center.is_active = False
            self.center.save(update_fields=["is_active"])
            with self.assertRaises(ValueError):
                run_export("exam_center_stats_xlsx", user=self.user, organization=self.org, params={})
            self.assertEqual(build.call_count, 1)
        request.organization = None
        self.user.profile.organization = self.org
        self.assertTrue(
            restore_request_organization_from_profile(request, profile=self.user.profile, allow_multi_org_restore=True)
        )
        self.assertEqual([m.role_id for m in request.org_memberships], [self.teacher.pk])
        self.assertNotIn("exam.configure", request.org_permissions)

    def test_last_disabled_role_removes_selected_org_and_cannot_be_rebound(self):
        person = User.objects.create_user("role_fixture_single")
        Membership.objects.create(organization=self.org, role=self.center, user=person)
        original = _run_middleware(person, self.org.slug)
        self.assertTrue(request_has_permission(original, "exam.configure"))
        self.center.is_active = False
        self.center.save(update_fields=["is_active"])
        person.set_active_organization_context(self.org, memberships=original.org_memberships)
        self.assertFalse(person.is_exam_center)
        self.assertFalse(request_has_permission(original, "exam.configure"))
        self.assertIsNone(_run_middleware(person, self.org.slug).organization)
