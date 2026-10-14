"""Tyutor = proqram koordinatoru — YEKUN açar dəsti eyni (sahib 2026-10-14).

Sahib: «tyutor və proqram koordinatoru eyni roldur demək olar, hər 2-si eyni şeyləri edə bilsin».

Kilidlənən müqavilə:
* şablon: hər iki rolun YEKUN açar dəsti (bütün qrant modullarından sonra) EYNİDİR; `level` (40 / 45),
  ad, göstərilən ad, UNIT əhatəsi dəyişmir (`default_roles_role_audit.apply_role_parity`);
* `0064_tutor_coordinator_parity`: mövcud tenantda tyutora çatışmayan açarlar yazılır, idempotent, `*`
  roluna toxunmur, geri dönüş yalnız verilən açarları götürür; «Proqram koordinatoru» müraciət şöbəsinə
  `tutor` emalçı kimi əlavə olunur;
* ad budaqları: tyutor koordinator aliası alır, koordinatorun view-as hədəfləri öz alt-ağacı ilə məhduddur.
"""

from __future__ import annotations

import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.applications.models import ApplicationUnit
from apps.organizations.default_roles_role_audit import ROLE_PARITY_GROUPS, apply_role_parity
from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls
from core.roles import ProfileRole

User = get_user_model()

MIGRATION = importlib.import_module("apps.organizations.migrations.0064_tutor_coordinator_parity")


def _seed(name):
    return next(row for row in UNIVERSITY_ROLES if row["name"] == name)


class TemplateParityTest(TestCase):
    def test_final_permission_sets_are_identical(self):
        tutor = set(_seed("tutor")["permissions"])
        coordinator = set(_seed("program_coordinator")["permissions"])
        self.assertEqual(tutor, coordinator, sorted(tutor ^ coordinator))
        for key in (
            "unit.group_manage",
            "student.assign_group",
            "plan.view",
            "workload.review",
            "application.handle",
        ):
            self.assertIn(key, tutor, key)
        # 2026-10-14 axşam: «Semestr açılışı» yalnız dekan + kafedra müdiri (paritetdən sonra götürülür, 0065).
        self.assertNotIn("semester.view", tutor)

    def test_levels_names_scope_unchanged(self):
        tutor, coordinator = _seed("tutor"), _seed("program_coordinator")
        self.assertEqual((tutor["level"], coordinator["level"]), (40, 45))
        self.assertEqual((tutor["display_name"], coordinator["display_name"]), ("Tutor", "Program Coordinator"))
        self.assertEqual(tutor["scope_type"], RoleScopeType.UNIT)
        self.assertEqual(coordinator["scope_type"], RoleScopeType.UNIT)

    def test_no_org_wide_or_admin_keys_leak_into_unit_roles(self):
        for key in _seed("tutor")["permissions"]:
            self.assertNotEqual(key, "*")
            self.assertFalse(key.endswith(".*"), key)
            self.assertNotIn(key, {"role.assign", "member.manage", "org.edit", "people.view_contacts"}, key)

    def test_parity_helper_is_idempotent_and_skips_wildcards(self):
        roles = [
            {"name": "tutor", "permissions": ["a.view"]},
            {"name": "program_coordinator", "permissions": ["b.view", "a.*"]},
        ]
        apply_role_parity(roles)
        apply_role_parity(roles)
        self.assertEqual(roles[0]["permissions"], ["a.view", "b.view", "a.*"])
        self.assertEqual(roles[1]["permissions"], ["b.view", "a.*"])  # `a.view` wildcard-la əhatəlidir
        star = [{"name": "tutor", "permissions": ["*"]}, {"name": "program_coordinator", "permissions": ["x.view"]}]
        apply_role_parity(star)
        self.assertEqual(star[0]["permissions"], ["*"])
        self.assertIn(("tutor", "program_coordinator"), ROLE_PARITY_GROUPS)

    def test_tutor_alias_includes_coordinator_and_vice_versa(self):
        self.assertIn("program_coordinator", ProfileRole.aliases_for_membership_role("tutor", level=40))
        self.assertIn("tutor", ProfileRole.aliases_for_membership_role("program_coordinator", level=45))
        self.assertNotIn(ProfileRole.ORG_ADMIN, ProfileRole.aliases_for_membership_role("tutor", level=40))


class MigrationParityTest(TestCase):
    OLD_TUTOR = [
        "member.view",
        "course.view",
        "exam.view",
        "people.view_students",
        "people.manage_academic",
        "group.manage",
        "unit.view",
        "journal.roster",
        "schedule.view",
        "schedule.manage",
        "analytics.view_unit",
        "application.create",
        "appeal.create",
    ]

    def setUp(self):
        self.owner = User.objects.create_user("tcp14_owner", "tcp14_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="TCP14 Univ",
                slug="tcp14-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            role = Role.objects.get(organization=self.org, name="tutor")
            role.permissions = list(self.OLD_TUTOR)
            role.save(update_fields=["permissions"])
            self.unit, _created = ApplicationUnit.objects.update_or_create(
                organization=self.org,
                code="koordinator",
                defaults={"name": "Proqram koordinatoru", "handler_role_names": ["program_coordinator"]},
            )

    def _role(self, name):
        with bypass_rls():
            return Role.objects.get(organization=self.org, name=name)

    def test_forward_makes_sets_equal_and_is_idempotent(self):
        with bypass_rls():
            MIGRATION.forward(django_apps, None)
            first = list(self._role("tutor").permissions)
            MIGRATION.forward(django_apps, None)
        second = list(self._role("tutor").permissions)
        self.assertEqual(first, second)
        self.assertEqual(len(second), len(set(second)))
        self.assertEqual(set(second), set(self._role("program_coordinator").permissions))
        tutor = self._role("tutor")
        self.assertEqual((tutor.level, tutor.display_name, tutor.scope_type), (40, "Tutor", RoleScopeType.UNIT))
        with bypass_rls():
            self.unit.refresh_from_db()
        self.assertEqual(self.unit.handler_role_names, ["program_coordinator", "tutor"])

    def test_wildcard_role_untouched(self):
        with bypass_rls():
            role = self._role("tutor")
            role.permissions = ["*"]
            role.save(update_fields=["permissions"])
            MIGRATION.forward(django_apps, None)
        self.assertEqual(self._role("tutor").permissions, ["*"])

    def test_tenant_without_coordinator_handler_is_left_alone(self):
        with bypass_rls():
            self.unit.handler_role_names = ["dean"]
            self.unit.save(update_fields=["handler_role_names"])
            MIGRATION.forward(django_apps, None)
            self.unit.refresh_from_db()
        self.assertEqual(self.unit.handler_role_names, ["dean"])

    def test_backward_restores_old_tutor_set(self):
        with bypass_rls():
            MIGRATION.forward(django_apps, None)
            MIGRATION.backward(django_apps, None)
            self.unit.refresh_from_db()
        self.assertEqual(sorted(self._role("tutor").permissions), sorted(self.OLD_TUTOR))
        self.assertEqual(self.unit.handler_role_names, ["program_coordinator"])


class CoordinatorViewAsScopeTest(TestCase):
    """Koordinator READONLY view-as-da yalnız öz alt-ağacının üzvlərini hədəf alır (tyutor kimi)."""

    def test_coordinator_targets_are_unit_scoped(self):
        from apps.accounts.services.view_as import UNIT_SCOPED_ROLE_NAMES, _unit_scope_user_ids

        self.assertIn("program_coordinator", UNIT_SCOPED_ROLE_NAMES)
        owner = User.objects.create_user("tcpv_owner", "tcpv_owner@qku.edu.az", "pw")
        with bypass_rls():
            org = Organization.objects.create(
                name="TCPV Univ",
                slug="tcpv-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            mine = OrgUnit.objects.create(organization=org, name="A", slug="tcpv-a", unit_type=OrgUnitType.SPECIALTY)
            other = OrgUnit.objects.create(organization=org, name="B", slug="tcpv-b", unit_type=OrgUnitType.SPECIALTY)
            coordinator = User.objects.create_user("tcpv_coord", "tcpv_c@qku.edu.az", "pw")
            membership = Membership.objects.create(
                user=coordinator,
                organization=org,
                role=Role.objects.get(organization=org, name="program_coordinator"),
                scope_unit=mine,
                is_active=True,
            )
            inside = User.objects.create_user("tcpv_in", "tcpv_in@qku.edu.az", "pw")
            outside = User.objects.create_user("tcpv_out", "tcpv_out@qku.edu.az", "pw")
            student = Role.objects.get(organization=org, name="student")
            Membership.objects.create(user=inside, organization=org, role=student, scope_unit=mine, is_active=True)
            Membership.objects.create(user=outside, organization=org, role=student, scope_unit=other, is_active=True)
            ids = {row["user_id"] for row in _unit_scope_user_ids(coordinator, org, [membership])}
        self.assertIn(inside.pk, ids)
        self.assertNotIn(outside.pk, ids)
