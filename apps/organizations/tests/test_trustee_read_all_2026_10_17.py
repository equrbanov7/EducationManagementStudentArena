"""Qəyyumlar Şurası üzvü — hər şeyi GÖRÜR, heç nəyi DƏYİŞMİR (sahib 2026-10-17: «hər şeyi açıq edə bilərsən»)."""

from __future__ import annotations

import importlib

from django.apps import apps as django_apps
from django.test import SimpleTestCase, TestCase

from apps.organizations.default_roles_oversight import OVERSIGHT_ROLES, TRUSTEE_READ_ALL_2026_10_17
from apps.organizations.permissions import PERMISSION_LABELS
from apps.organizations.public import holds_student_key
from core.permissions import has_permission

_READ_SUFFIXES = (".view", ".view_all", ".view_unit", ".view_own", ".report", ".export", "_view", ".search")


def _trustee_permissions():
    return next(role for role in OVERSIGHT_ROLES if role["name"] == "trustee")["permissions"]


class TrusteeTemplateTest(SimpleTestCase):
    def test_every_read_key_except_system_monitoring(self):
        permissions = _trustee_permissions()
        read_keys = [
            key
            for key in PERMISSION_LABELS
            if (key.endswith(_READ_SUFFIXES) or key.startswith("people.view") or key == "people.hr_analytics")
            and key not in ("system.monitoring.view", "analytics.view_own")
        ]
        missing = [key for key in read_keys if not has_permission(permissions, key)]
        self.assertEqual(missing, [])
        self.assertFalse(has_permission(permissions, "system.monitoring.view"))
        self.assertTrue(holds_student_key(permissions))  # tələbə kataloqu da açıqdır

    def test_no_write_keys(self):
        for key in (
            "grade.input",
            "journal.correct",
            "member.edit",
            "role.assign",
            "user.edit",
            "plan.edit",
            "schedule.manage",
            "exam.create",
            "workload.manage",
            "semester.open",
            "user.block",
        ):
            self.assertFalse(has_permission(_trustee_permissions(), key), key)
        self.assertNotIn("*", _trustee_permissions())

    def test_migration_keys_match_template(self):
        migration = importlib.import_module("apps.organizations.migrations.0066_trustee_read_all")
        self.assertEqual(set(migration._KEYS), set(TRUSTEE_READ_ALL_2026_10_17))


class TrusteeMigrationTest(TestCase):
    def test_forward_adds_read_keys_idempotently_and_backward_removes_them(self):
        from django.contrib.auth import get_user_model

        from apps.organizations.models import Organization, Role
        from core.constants import OrganizationType

        owner = get_user_model().objects.create_user("tr_owner", "tr_owner@tr.test", "pw")
        org = Organization.objects.create(
            name="TR", slug="tr-org", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        role = Role.objects.get(organization=org, name="trustee")
        role.permissions = ["unit.view", "audit.view"]
        role.save(update_fields=["permissions"])
        migration = importlib.import_module("apps.organizations.migrations.0066_trustee_read_all")
        migration.forward(django_apps, None)
        migration.forward(django_apps, None)
        role.refresh_from_db()
        self.assertTrue(has_permission(role.permissions, "grade.view"))
        self.assertEqual(len(role.permissions), len(set(role.permissions)))
        migration.backward(django_apps, None)
        role.refresh_from_db()
        self.assertEqual(role.permissions, ["unit.view", "audit.view"])
