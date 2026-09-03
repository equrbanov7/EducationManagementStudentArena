"""`group.view`/`group.manage` geriyə-doldurma migrationunun (0027) testləri.

Davranış-qorunma müqaviləsi: qrup qapısı `has_role(org_admin/org_owner)`-dən
permission-əsaslıya keçəndə əvvəl keçən çoxluq (org_admin aliası alan rollar —
ad ADMIN_EQUIVALENT-də və ya level >= 80, exempt-lər xaric) EYNİ imkanla
qalmalı, qalanlar YENİ imkan almamalıdır.
"""

import importlib

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase

from core.constants import OrganizationType, RoleScopeType

from ..models import Organization, Role
from ..signals import create_default_roles

User = get_user_model()

_seed_module = importlib.import_module("apps.organizations.migrations.0028_seed_group_permissions")


class GroupPermissionSeedMigrationTest(TestCase):
    """Migration forward/reverse funksiyalarının real modellər üzərində testi."""

    @classmethod
    def setUpTestData(cls):
        post_save.disconnect(create_default_roles, sender=Organization)
        try:
            cls.owner = User.objects.create_user("gseed_owner", "gseed_owner@example.com", "StrongPass123!")
            cls.org = Organization.objects.create(
                name="Seed Univ",
                slug="seed-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
        finally:
            post_save.connect(create_default_roles, sender=Organization)

        def _role(name, level, permissions, is_system=True):
            return Role.objects.create(
                organization=cls.org,
                name=name,
                display_name=name.replace("_", " ").title(),
                level=level,
                scope_type=RoleScopeType.ORGANIZATION,
                permissions=permissions,
                is_system=is_system,
                is_active=True,
            )

        cls.rector = _role("rector", 100, ["*"])
        cls.dean = _role("dean", 80, ["unit.view", "course.*"])  # ad ADMIN_EQUIVALENT-də
        cls.chair_head = _role("chair_head", 70, ["course.*"])  # → department_head (equiv)
        cls.custom_admin = _role("registrar_boss", 85, ["member.view"], is_system=False)  # level >= 80
        cls.exam_center_head = _role("exam_center_head", 85, ["exam.*"])  # admin-alias EXEMPT
        cls.hr = _role("hr", 65, ["member.*"])  # EXEMPT
        cls.teacher = _role("teacher", 60, ["course.view", "grade.input"])

    def _refresh(self, *roles):
        for role in roles:
            role.refresh_from_db()

    def test_forward_seeds_exactly_the_previous_org_admin_alias_set(self):
        _seed_module.seed_group_permissions(global_apps, None)
        self._refresh(
            self.rector, self.dean, self.chair_head, self.custom_admin, self.exam_center_head, self.hr, self.teacher
        )

        # Əvvəl keçənlər indi açarı alır (custom rol daxil).
        for role in (self.dean, self.chair_head, self.custom_admin):
            self.assertIn("group.view", role.permissions, role.name)
            self.assertIn("group.manage", role.permissions, role.name)

        # `*` rolu dəyişməz qalır (onsuz da əhatələnir).
        self.assertEqual(self.rector.permissions, ["*"])

        # Əvvəl KEÇMƏYƏNLƏR yeni imkan almır (privilege escalation yoxdur).
        for role in (self.exam_center_head, self.hr, self.teacher):
            self.assertNotIn("group.view", role.permissions, role.name)
            self.assertNotIn("group.manage", role.permissions, role.name)

    def test_forward_is_idempotent(self):
        _seed_module.seed_group_permissions(global_apps, None)
        _seed_module.seed_group_permissions(global_apps, None)
        self.dean.refresh_from_db()
        self.assertEqual(self.dean.permissions.count("group.manage"), 1)
        self.assertEqual(self.dean.permissions.count("group.view"), 1)

    def test_reverse_removes_seeded_permissions(self):
        _seed_module.seed_group_permissions(global_apps, None)
        _seed_module.remove_group_permissions(global_apps, None)
        self._refresh(self.dean, self.chair_head, self.custom_admin)
        for role in (self.dean, self.chair_head, self.custom_admin):
            self.assertNotIn("group.view", role.permissions, role.name)
            self.assertNotIn("group.manage", role.permissions, role.name)


class DefaultRoleGroupPermissionTest(TestCase):
    """default_roles.py — yeni təşkilatlarda davranış-qorunma pariteti."""

    def test_admin_equivalent_default_roles_carry_group_permissions(self):
        from ..default_roles import DEFAULT_ROLES

        expected_with = {
            OrganizationType.UNIVERSITY: {"vice_rector", "ikt_rehber", "dean", "chair_head"},
            OrganizationType.SCHOOL: {"deputy_director", "section_head"},
            OrganizationType.COURSE_CENTER: {"branch_manager"},
            OrganizationType.INDIVIDUAL: set(),
        }
        for org_type, roles in DEFAULT_ROLES.items():
            for role in roles:
                perms = role["permissions"]
                has_group = "group.manage" in perms and "group.view" in perms
                if "*" in perms:
                    # Tam-səlahiyyətli rollar açarı ayrıca daşımır.
                    self.assertFalse(has_group, role["name"])
                elif role["name"] in expected_with.get(org_type, set()):
                    self.assertTrue(has_group, f"{org_type}/{role['name']} qrup açarlarını itirib")
                else:
                    self.assertFalse(has_group, f"{org_type}/{role['name']} artıq qrup açarı daşıyır")
