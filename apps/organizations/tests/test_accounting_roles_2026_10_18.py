"""«Mühasib» rolu + `accounting.view` / `retake.*` açarları (sahib 2026-10-18) — kataloq, şablon, miqrasiya 0067."""

from __future__ import annotations

import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.accounts.services.role_catalog import assignable_roles
from apps.organizations.default_roles_accounting import ACCOUNTANT_PERMISSIONS, ACCOUNTING_GRANTS
from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.permissions import PERMISSION_CATEGORY_LABELS, PERMISSION_LABELS, get_all_permissions
from apps.organizations.student_privacy import holds_student_key
from core.constants import OrganizationType, RoleScopeType
from core.permissions import has_permission
from core.roles import ProfileRole

_MIGRATION = "apps.organizations.migrations.0067_accounting_retake_permissions"
_RETAKE_MANAGERS = ("dean", "vice_dean", "teaching_office_head", "teaching_office_staff", "ikt_rehber")


def _template(name):
    return next(role for role in UNIVERSITY_ROLES if role["name"] == name)


class AccountingCatalogTest(SimpleTestCase):
    def test_keys_have_az_labels_and_categories(self):
        catalog = set(get_all_permissions())
        for key in ("accounting.view", "retake.payment_verify", "retake.manage"):
            self.assertIn(key, catalog)
            self.assertTrue(str(PERMISSION_LABELS[key]))
        self.assertEqual(PERMISSION_CATEGORY_LABELS["accounting"], "Mühasibatlıq")

    def test_accountant_template(self):
        role = _template("accountant")
        self.assertEqual(role["display_name"], "Mühasib")
        self.assertEqual(role["scope_type"], RoleScopeType.ORGANIZATION)
        self.assertLess(role["level"], 60)  # nə org_admin aliası (≥80), nə də «teacher or above» (≥60)
        self.assertNotIn(role["name"], ProfileRole.ADMIN_EQUIVALENT_ROLE_NAMES)
        for key in ("accounting.view", "retake.payment_verify"):
            self.assertIn(key, role["permissions"])
        self.assertFalse(holds_student_key(role["permissions"]))  # tələbə şəxsi məlumatı açarı yoxdur
        self.assertEqual(
            set(role["permissions"]) - {"application.create"},
            {"accounting.view", "retake.payment_verify", "accounting.manage_fees"},
        )
        for key in ("retake.manage", "unit.view", "people.view_teachers", "member.view", "grade.view", "role.assign"):
            self.assertFalse(has_permission(role["permissions"], key), key)

    def test_grants_on_templates(self):
        for name in ("trustee", "rector", "board_chair", "ikt_rehber"):
            self.assertTrue(has_permission(_template(name)["permissions"], "accounting.view"), name)
        for name in _RETAKE_MANAGERS:
            self.assertTrue(has_permission(_template(name)["permissions"], "retake.manage"), name)
        for name in ("teacher", "dean", "hr", "student", "chair_head", "vice_rector"):
            self.assertFalse(has_permission(_template(name)["permissions"], "accounting.view"), name)
        self.assertFalse(has_permission(_template("trustee")["permissions"], "retake.manage"))
        # «Təhsil haqqı cədvəli» (2026-10-19): mühasib + RİM; dekanlıq və qəyyum yox.
        for name in ("accountant", "ikt_rehber"):
            self.assertTrue(has_permission(_template(name)["permissions"], "accounting.manage_fees"), name)
        for name in ("dean", "trustee", "teaching_office_head", "teacher", "student"):
            self.assertFalse(has_permission(_template(name)["permissions"], "accounting.manage_fees"), name)

    def test_migration_copies_match_templates(self):
        migration = importlib.import_module(_MIGRATION)
        fees = importlib.import_module("apps.organizations.migrations.0068_accounting_manage_fees")
        # 0067 + 0068 birlikdə şablonu verir (0068 yalnız `accounting.manage_fees` əlavə edir).
        with_fees = set(migration._ROLE_SPEC["permissions"]) | {fees._KEY}
        self.assertEqual(with_fees, set(_template("accountant")["permissions"]))
        self.assertEqual(migration._ROLE_SPEC["level"], _template("accountant")["level"])
        grants = {name: set(keys) for name, keys in migration._GRANTS.items()}
        for name in fees._ROLES:
            if name in grants:
                grants[name].add(fees._KEY)
        self.assertEqual(grants, {name: set(keys) for name, keys in ACCOUNTING_GRANTS.items()})
        self.assertLessEqual(set(ACCOUNTANT_PERMISSIONS), with_fees)


class AccountingMigrationTest(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user("acm_owner", "acm_owner@acm.test", "pw")
        self.org = Organization.objects.create(
            name="ACM", slug="acm-org", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        self.migration = importlib.import_module(_MIGRATION)

    def test_new_org_is_seeded_with_accountant(self):
        role = Role.objects.get(organization=self.org, name="accountant")
        self.assertIn("accounting.view", role.permissions)

    def test_forward_seeds_role_and_keys_idempotently_and_backward_reverts(self):
        Role.objects.filter(organization=self.org, name="accountant").delete()
        before = {}
        for name in (*_RETAKE_MANAGERS, "trustee"):
            role = Role.objects.get(organization=self.org, name=name)
            permissions = [p for p in role.permissions if p not in ("accounting.view", "retake.manage")]
            if name == "ikt_rehber":
                permissions = ["unit.view"]  # tenantda `*` daraldılıb
            role.permissions = permissions
            role.save(update_fields=["permissions"])
            before[name] = list(permissions)

        self.migration.forward(django_apps, None)
        self.migration.forward(django_apps, None)  # idempotent
        self.assertEqual(Role.objects.filter(organization=self.org, name="accountant").count(), 1)
        accountant = Role.objects.get(organization=self.org, name="accountant")
        self.assertEqual((accountant.level, accountant.scope_type), (58, RoleScopeType.ORGANIZATION))
        for name in _RETAKE_MANAGERS:
            permissions = Role.objects.get(organization=self.org, name=name).permissions
            self.assertEqual(permissions.count("retake.manage"), 1, name)
        for name in ("trustee", "ikt_rehber"):
            self.assertEqual(Role.objects.get(organization=self.org, name=name).permissions.count("accounting.view"), 1)

        self.migration.backward(django_apps, None)
        self.assertFalse(Role.objects.filter(organization=self.org, name="accountant").exists())
        for name, permissions in before.items():
            self.assertEqual(Role.objects.get(organization=self.org, name=name).permissions, permissions, name)

    def test_backward_keeps_accountant_role_with_members(self):
        user = get_user_model().objects.create_user("acm_acc", "acm_acc@acm.test", "pw")
        role = Role.objects.get(organization=self.org, name="accountant")
        Membership.objects.create(user=user, organization=self.org, role=role, is_active=True)
        self.migration.backward(django_apps, None)
        self.assertTrue(Role.objects.filter(pk=role.pk).exists())

    def test_wildcard_roles_are_untouched(self):
        rector = Role.objects.get(organization=self.org, name="rector")
        self.migration.forward(django_apps, None)
        rector.refresh_from_db()
        self.assertEqual(rector.permissions, ["*"])

    def test_rim_head_can_assign_accountant(self):
        names = {role.name for role in assignable_roles(self.org, actor_level=95, is_superadmin=False)}
        self.assertIn("accountant", names)
