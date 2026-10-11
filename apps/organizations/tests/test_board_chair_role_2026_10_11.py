"""«Qəyyumlar Şurasının sədri» (`board_chair`) — sahib 2026-10-11.

Rektor kimi təşkilat daxilində hər şeyə çıxış (`*`), superadmin DEYİL, üzv reyestrinin başında; miqrasiya
Hüseynqulu Bağırovun qəyyum üzvlüyünü bu rola keçirir (ikinci sətir yaratmadan) və geri qaytarılır.
"""

from __future__ import annotations

import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import Membership, Organization, OrgUnit
from apps.organizations.structure_views.members import build_members_section
from apps.organizations.tests.test_p1_11_permission_scope import _request
from core.constants import OrganizationType, OrgUnitType
from core.permissions import has_permission

User = get_user_model()
_MIGRATION = importlib.import_module("apps.organizations.migrations.0059_board_chair_role")


class BoardChairRoleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("bc_owner", "bc_owner@bc.test", "pw")
        cls.org = Organization.objects.create(
            name="BC Univ", slug="bc-univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        cls.board = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.RECTORATE, name="Qəyyumlar şurası"
        )
        cls.chair = User.objects.create_user("huseynqulu.bagirov", "bagirov_h@bc.test", "pw", first_name="Hüseynqulu")
        cls.trustee = User.objects.create_user("bc_trustee", "bc_trustee@bc.test", "pw", first_name="Adi")
        cls.rector = User.objects.create_user("bc_rector", "bc_rector@bc.test", "pw", first_name="Aaa")
        cls.hr = User.objects.create_user("bc_hr", "bc_hr@bc.test", "pw")
        for user, role, unit in (
            (cls.chair, "trustee", cls.board),
            (cls.trustee, "trustee", cls.board),
            (cls.rector, "rector", None),
            (cls.hr, "hr", None),
        ):
            Membership.objects.create(
                user=user, organization=cls.org, role=cls.org.roles.get(name=role), scope_unit=unit, is_active=True
            )

    def _run(self, fn):
        fn(django_apps, None)

    def test_role_template_is_rector_like_and_above_it(self):
        role = self.org.roles.get(name="board_chair")  # şablondan yeni təşkilata əkilir
        rector = self.org.roles.get(name="rector")
        self.assertEqual(role.permissions, ["*"])
        self.assertGreater(role.level, rector.level)
        self.assertEqual(role.display_name, "Qəyyumlar Şurasının sədri")

    def test_migration_moves_only_bagirov_and_lists_him_first(self):
        self._run(_MIGRATION.forward)
        self._run(_MIGRATION.forward)  # idempotent
        memberships = Membership.objects.filter(user=self.chair, organization=self.org)
        self.assertEqual([m.role.name for m in memberships], ["board_chair"])  # ikinci sətir yoxdur
        self.assertEqual(memberships.get().scope_unit_id, self.board.pk)
        self.assertEqual(Membership.objects.get(user=self.trustee).role.name, "trustee")
        self.assertTrue(has_permission(memberships.get().role.permissions, "grade.view"))
        self.assertFalse(User.objects.get(pk=self.chair.pk).is_superuser)

        section = build_members_section(_request(self.hr, self.org, data={"om_sort": "role"}), self.org)
        self.assertEqual(section["rows"][0]["user_id"], self.chair.pk)
        self.assertEqual(section["rows"][0]["role_label"], "Qəyyumlar Şurasının sədri")
        self.assertTrue(section["rows"][0]["is_leader"])

        self._run(_MIGRATION.backward)
        self.assertEqual(Membership.objects.get(user=self.chair).role.name, "trustee")
