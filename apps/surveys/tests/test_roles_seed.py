"""Keyfiyyət rolları + ``survey.*`` açarları: şablon, mövcud tenant miqrasiyası, paritet."""

from __future__ import annotations

from importlib import import_module

from django.apps import apps as django_apps
from django.test import SimpleTestCase, TestCase

from apps.organizations.default_roles_quality import QUALITY_CONTROL_ROLES, SURVEY_GRANTS
from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import Role
from apps.organizations.permissions import PERMISSION_LABELS, get_all_permissions, validate_permissions
from core.rls import bypass_rls
from core.roles import ProfileRole

from .factories import build_world, member

_MIGRATION = import_module("apps.organizations.migrations.0054_seed_quality_control_roles")
_QC = ("quality_control_head", "quality_control_staff")


class TemplateTest(SimpleTestCase):
    def test_catalog_has_survey_keys_with_labels(self):
        catalog = set(get_all_permissions())
        for key in ("survey.results.view", "survey.manage"):
            self.assertIn(key, catalog)
            self.assertTrue(str(PERMISSION_LABELS[key]).strip())

    def test_quality_roles_are_valid_and_below_admin_alias(self):
        by_name = {role["name"]: role for role in UNIVERSITY_ROLES}
        for name in _QC:
            role = by_name[name]
            self.assertTrue(validate_permissions(role["permissions"]), name)
            self.assertLess(role["level"], 80, name)
            self.assertNotIn(ProfileRole.ORG_ADMIN, ProfileRole.aliases_for_membership_role(name, level=role["level"]))
        self.assertIn("survey.manage", by_name["quality_control_head"]["permissions"])
        self.assertNotIn("survey.manage", by_name["quality_control_staff"]["permissions"])

    def test_existing_roles_get_results_key(self):
        by_name = {role["name"]: role for role in UNIVERSITY_ROLES}
        for name in ("chair_head", "teaching_office_head", "teaching_office_staff", "vice_rector"):
            self.assertIn("survey.results.view", by_name[name]["permissions"], name)
        self.assertNotIn("survey.results.view", by_name["dean"]["permissions"])  # sahibin siyahısında yoxdur
        self.assertEqual(by_name["rector"]["permissions"], ["*"])
        self.assertEqual(by_name["ikt_rehber"]["permissions"], ["*"])

    def test_migration_spec_matches_live_template(self):
        """Miqrasiya dondurulmuş spesifikasiya işlədir — şablonla EYNİ qalmalıdır."""
        by_name = {role["name"]: role for role in UNIVERSITY_ROLES}
        for spec in _MIGRATION.ROLE_SPECS:
            live = by_name[spec["name"]]
            self.assertEqual(sorted(spec["permissions"]), sorted(live["permissions"]), spec["name"])
            for key in ("display_name", "level", "scope_type", "description"):
                self.assertEqual(spec[key], live[key], (spec["name"], key))
        self.assertEqual(dict(_MIGRATION.GRANTS), dict(SURVEY_GRANTS))
        self.assertEqual({spec["name"] for spec in _MIGRATION.ROLE_SPECS}, {r["name"] for r in QUALITY_CONTROL_ROLES})

    def test_view_as_modes_and_network_zone(self):
        from apps.accounts.services.view_as import MODE_READONLY, ROLE_FILTER_MAP, ROLE_MODE_MAP

        for name in _QC:
            self.assertEqual(ROLE_MODE_MAP[name], MODE_READONLY)
            self.assertIn(name, ROLE_FILTER_MAP["staff"])


class ExistingTenantMigrationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svseed", students=1)
        org = cls.w["org"]
        with bypass_rls():
            # «Köhnə» tenant vəziyyəti: rollar yoxdur, açarlar verilməyib.
            Role.objects.filter(organization=org, name__in=_QC).delete()
            for role in Role.objects.filter(organization=org, name__in=list(SURVEY_GRANTS)):
                role.permissions = [p for p in role.permissions if not p.startswith("survey.")]
                role.save(update_fields=["permissions"])

    def test_forward_seeds_roles_and_grants_idempotently(self):
        org = self.w["org"]
        with bypass_rls():
            _MIGRATION.forward(django_apps, None)
            _MIGRATION.forward(django_apps, None)
            head = Role.objects.get(organization=org, name="quality_control_head")
            self.assertEqual(Role.objects.filter(organization=org, name__in=_QC).count(), 2)
            self.assertIn("survey.manage", head.permissions)
            self.assertEqual(head.level, 70)
            chair = Role.objects.get(organization=org, name="chair_head")
            self.assertEqual(chair.permissions.count("survey.results.view"), 1)
            self.assertEqual(Role.objects.get(organization=org, name="rector").permissions, ["*"])

    def test_backward_keeps_roles_with_members(self):
        org = self.w["org"]
        with bypass_rls():
            _MIGRATION.forward(django_apps, None)
            member(org, "svseed_qc", "quality_control_staff")
            _MIGRATION.backward(django_apps, None)
            self.assertFalse(Role.objects.filter(organization=org, name="quality_control_head").exists())
            self.assertTrue(Role.objects.filter(organization=org, name="quality_control_staff").exists())
            chair = Role.objects.get(organization=org, name="chair_head")
            self.assertNotIn("survey.results.view", chair.permissions)

    def test_new_organization_gets_roles_from_template(self):
        other = build_world("svseed2", students=0)
        with bypass_rls():
            names = set(Role.objects.filter(organization=other["org"], name__in=_QC).values_list("name", flat=True))
        self.assertEqual(names, set(_QC))

    def test_quality_staff_is_staff_for_network_zone(self):
        from django.test import RequestFactory

        from apps.accounts.network_zone import account_kind
        from apps.organizations.models import Membership

        with bypass_rls():
            _MIGRATION.forward(django_apps, None)
            user = member(self.w["org"], "svseed_zone", "quality_control_head")
            request = RequestFactory().get("/")
            request.user = user
            request.organization = self.w["org"]
            request.org_memberships = list(Membership.objects.filter(user=user).select_related("role"))
        self.assertEqual(account_kind(request), "staff")
