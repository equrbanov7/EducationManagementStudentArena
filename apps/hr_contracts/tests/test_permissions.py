"""İcazə kataloqu, rol şablonları və mövcud tenantlar üçün miqrasiya (0069)."""

from __future__ import annotations

import importlib

from django.apps import apps as django_apps
from django.test import SimpleTestCase, TestCase

from apps.hr_contracts.public import hr_section_visible
from apps.organizations.default_roles import get_default_roles_for_org_type as get_default_roles
from apps.organizations.permissions import PERMISSION_CATEGORIES, PERMISSION_LABELS
from apps.organizations.permissions_hr_contracts import HR_CONTRACT_GRANTS
from core.constants import OrganizationType
from core.permissions import has_permission

VIEW, MANAGE = "hr.contracts_view", "hr.contracts_manage"


def _template(name):
    return next(role for role in get_default_roles(OrganizationType.UNIVERSITY) if role["name"] == name)["permissions"]


class CatalogTest(SimpleTestCase):
    def test_keys_are_in_catalog_with_labels(self):
        self.assertIn(VIEW, PERMISSION_CATEGORIES["hr"])
        self.assertIn(MANAGE, PERMISSION_CATEGORIES["hr"])
        self.assertIn(VIEW, PERMISSION_LABELS)
        self.assertIn(MANAGE, PERMISSION_LABELS)

    def test_role_templates(self):
        for name in ("hr", "ikt_rehber"):
            self.assertTrue(has_permission(_template(name), VIEW), name)
            self.assertTrue(has_permission(_template(name), MANAGE), name)
        self.assertTrue(has_permission(_template("trustee"), VIEW))
        self.assertFalse(has_permission(_template("trustee"), MANAGE))  # qəyyum yalnız oxu
        for name in ("rector", "board_chair"):
            self.assertTrue(has_permission(_template(name), MANAGE), name)  # `*`
        for name in ("dean", "teacher", "student", "accountant", "chair_head"):
            self.assertFalse(has_permission(_template(name), VIEW), name)

    def test_section_visibility_from_keys(self):
        self.assertTrue(hr_section_visible([VIEW]))
        self.assertTrue(hr_section_visible([MANAGE]))
        self.assertTrue(hr_section_visible(["hr.*"]))
        self.assertFalse(hr_section_visible(["people.hr_analytics"]))
        self.assertTrue(hr_section_visible([], privileged=True))

    def test_migration_matches_template(self):
        migration = importlib.import_module("apps.organizations.migrations.0069_hr_contract_permissions")
        self.assertEqual(migration._GRANTS, HR_CONTRACT_GRANTS)


class MigrationTest(TestCase):
    def test_forward_is_idempotent_and_backward_removes(self):
        from django.contrib.auth import get_user_model

        from apps.organizations.models import Organization, Role

        owner = get_user_model().objects.create_user("hrcmig_owner", "hrcmig@qku.edu.az", "pw")
        org = Organization.objects.create(
            name="HRC Mig", slug="hrc-mig", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        hr = Role.objects.get(organization=org, name="hr")
        hr.permissions = ["member.view"]
        hr.save(update_fields=["permissions"])
        wildcard = Role.objects.get(organization=org, name="ikt_rehber")
        before_wildcard = list(wildcard.permissions)
        migration = importlib.import_module("apps.organizations.migrations.0069_hr_contract_permissions")
        migration.forward(django_apps, None)
        migration.forward(django_apps, None)
        hr.refresh_from_db()
        self.assertEqual(hr.permissions, ["member.view", VIEW, MANAGE])
        migration.backward(django_apps, None)
        hr.refresh_from_db()
        self.assertEqual(hr.permissions, ["member.view"])
        wildcard.refresh_from_db()
        if "*" in before_wildcard:
            self.assertNotIn(MANAGE, wildcard.permissions)  # `*` daşıyana toxunulmur
