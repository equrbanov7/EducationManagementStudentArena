"""PERF-1 F-03 (2026-10-17): nəzarət-növbəsi yoxlaması kabinet request-i başına BİR dəfə.

``_role_capabilities`` bölmə render-ində iki dəfə işləyir; əvvəl hər dəfə
``supervision_scope`` 3 sorğu (növbə + 2× köhnə zal/oturum) atırdı. İndi nəticə
istifadəçi obyektində (request ömrü) memo-lanır. Yeni istifadəçi obyekti (yeni
request) isə yenidən yoxlayır — növbə təyin olunanda bənd növbəti request-də görünür.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import ProfileRole, UserProfile
from apps.accounts.views._helpers.membership import _sync_user_role_memberships
from apps.accounts.views._helpers.rbac import _role_capabilities
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

_SUPERVISION_TABLES = ('"exams_invigilatorduty"', '"exams_examroomsession"')


def _supervision_queries(ctx) -> int:
    return sum(1 for q in ctx.captured_queries if any(t in q["sql"] for t in _SUPERVISION_TABLES))


class SupervisionMemoPerRequestTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("perf1_sup_owner", "perf1_sup_owner@example.test", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="PERF1 Supervision Org",
            slug="perf1-supervision-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        cls.teacher = User.objects.create_user("perf1_sup_teacher", "perf1_sup_teacher@example.test", "StrongPass123!")
        UserProfile.objects.filter(user=cls.teacher).update(organization=cls.org)
        _sync_user_role_memberships(cls.teacher, cls.org, {ProfileRole.TEACHER})

    def _fresh_teacher(self):
        user = User.objects.get(pk=self.teacher.pk)
        user.set_active_organization_context(self.org)
        return user

    def test_supervision_scope_runs_once_for_repeated_capability_builds(self):
        user = self._fresh_teacher()
        profile = user.profile
        with CaptureQueriesContext(connection) as first:
            caps = _role_capabilities(user, profile)
        self.assertTrue(caps["is_teacher"])
        self.assertFalse(caps["can_access_final_center"])
        self.assertEqual(_supervision_queries(first), 3)
        with CaptureQueriesContext(connection) as again:
            _role_capabilities(user, profile)
            _role_capabilities(user, profile)
        self.assertEqual(_supervision_queries(again), 0)

    def test_new_user_object_rechecks(self):
        _role_capabilities(self._fresh_teacher(), self.teacher.profile)
        with CaptureQueriesContext(connection) as ctx:
            user = self._fresh_teacher()
            _role_capabilities(user, user.profile)
        self.assertEqual(_supervision_queries(ctx), 3)
