"""Dalğa 2 (2026-09-14) — audit 2026-09-13 `access` F-06 / hesabat §27: icazə
kataloqu drift-i (13 «ölü» açar).

* Çıxarılanlar (`org.delete`, `role.create`, `role.delete`, `grade.override`, `qa.*`)
  kataloqda və şablonlarda YOXDUR; miqrasiya 0051 saxlanılan rollardan silir.
* Bağlananlar: `org.settings` / `org.edit` (təşkilat ayarları), `role.edit` (icazə
  redaktoru POST-u), `audit.export` (CSV ixracı), `journal.view` (əhatəli yalnız-oxu
  jurnal), `analytics.view_own` (statistika şəxsi profili) — açar götürüləndə qapı
  BAĞLANIR, şablon daşıyıcıları isə əvvəlki kimi keçir (kilidlənmə yoxdur).
"""

from __future__ import annotations

import csv
import io
from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.organizations.default_roles import DEFAULT_ROLES
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.organizations.permissions import get_all_permissions, validate_permissions
from apps.registrar import services as registrar_services
from apps.registrar.models import Enrollment, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
PW = "W2RbacPass123!"
REMOVED = ("org.delete", "role.create", "role.delete", "grade.override", "qa.view", "qa.review", "qa.flag")
_MIGRATION = import_module("apps.organizations.migrations.0051_permission_catalog_drift")


class CatalogAndTemplatesTest(SimpleTestCase):
    def test_removed_keys_are_gone_and_wired_keys_remain(self):
        catalog = set(get_all_permissions())
        for key in REMOVED:
            self.assertNotIn(key, catalog, key)
        for key in ("org.edit", "org.settings", "role.edit", "audit.export", "journal.view", "analytics.view_own"):
            self.assertIn(key, catalog, key)

    def test_templates_carry_no_removed_key_and_stay_valid(self):
        for org_type, roles in DEFAULT_ROLES.items():
            for role in roles:
                permissions = role["permissions"]
                self.assertTrue(validate_permissions(permissions), (org_type, role["name"]))
                for entry in permissions:
                    self.assertFalse(entry.startswith("qa."), (org_type, role["name"], entry))
                    self.assertNotIn(entry, REMOVED, (org_type, role["name"]))

    def test_audit_view_templates_also_carry_export(self):
        """Bu günkü davranış: jurnalı görən hər rol ixrac edə bilirdi — cüt açar."""
        seen = 0
        for roles in DEFAULT_ROLES.values():
            for role in roles:
                if "audit.view" in role["permissions"]:
                    seen += 1
                    self.assertIn("audit.export", role["permissions"], role["name"])
        self.assertGreaterEqual(seen, 8)

    def test_level_90_templates_carry_settings_keys(self):
        for roles in DEFAULT_ROLES.values():
            for role in roles:
                if role["level"] >= 90 and "*" not in role["permissions"]:
                    self.assertIn("org.settings", role["permissions"], role["name"])
                    self.assertIn("org.edit", role["permissions"], role["name"])


def _build_org(tag):
    owner = User.objects.create_user(f"w2rbac_owner_{tag}", f"w2rbac_owner_{tag}@audit.az", PW)
    org = Organization.objects.create(
        name=f"W2 RBAC {tag}",
        slug=f"w2rbac-{tag}",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )
    fac = OrgUnit.objects.create(organization=org, name="Fak", slug=f"w2fak-{tag}", unit_type=OrgUnitType.FACULTY)
    group = OrgUnit.objects.create(
        organization=org, name="Qrup", slug=f"w2grp-{tag}", unit_type=OrgUnitType.GROUP, parent=fac
    )
    fac2 = OrgUnit.objects.create(organization=org, name="Fak2", slug=f"w2fak2-{tag}", unit_type=OrgUnitType.FACULTY)
    users = {}
    for key, role_name, unit in (
        ("rector", "rector", None),
        ("vice_rector", "vice_rector", None),
        ("ikt_rehber", "ikt_rehber", None),
        ("hr", "hr", None),
        ("teacher", "teacher", None),
        ("teacher2", "teacher", None),
        ("trustee", "trustee", None),
        ("dean", "dean", fac),
        ("dean2", "dean", fac2),
        ("student", "student", group),
    ):
        user = User.objects.create_user(f"w2rbac_{key}_{tag}", f"w2rbac_{key}_{tag}@audit.az", PW)
        Membership.objects.create(
            user=user, organization=org, role=org.roles.get(name=role_name), scope_unit=unit, is_primary=True
        )
        users[key] = user
    return {"org": org, "owner": owner, "fac": fac, "fac2": fac2, "group": group, "users": users}


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.A = _build_org("a")
        cls.org = cls.A["org"]

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def user(self, key):
        return self.A["users"][key]

    def role(self, name):
        with bypass_rls():
            return Role.objects.get(organization=self.org, name=name)

    def strip(self, role_name, *keys):
        with bypass_rls():
            role = self.role(role_name)
            role.permissions = [entry for entry in role.permissions if entry not in keys]
            role.save(update_fields=["permissions"])

    def grant(self, role_name, *keys):
        with bypass_rls():
            role = self.role(role_name)
            role.permissions = sorted(set(role.permissions) | set(keys))
            role.save(update_fields=["permissions"])


class Migration0051Test(_Base):
    def test_forward_strips_removed_keys_and_seeds_wired_keys(self):
        with bypass_rls():
            custom = Role.objects.create(
                organization=self.org,
                name="w2_custom_90",
                display_name="Custom 90",
                level=90,
                scope_type="organization",
                permissions=["org.view", "qa.*", "grade.override", "grant:role.create", "roles.delete"],
            )
            viewer = Role.objects.create(
                organization=self.org,
                name="w2_viewer",
                display_name="Viewer",
                level=30,
                scope_type="organization",
                permissions=["audit.view", "qa.view"],
            )
            rector_before = list(self.role("rector").permissions)
            _MIGRATION.forward(django_apps, None)
            custom.refresh_from_db()
            viewer.refresh_from_db()
            self.assertEqual(custom.permissions, ["org.view", "org.settings", "org.edit"])
            self.assertEqual(viewer.permissions, ["audit.view", "audit.export"])
            self.assertEqual(list(self.role("rector").permissions), rector_before)
            for role in Role.objects.filter(organization=self.org):
                self.assertTrue(validate_permissions(role.permissions), role.name)

    def test_backward_removes_only_seeded_keys(self):
        with bypass_rls():
            role = Role.objects.create(
                organization=self.org,
                name="w2_back",
                display_name="Back",
                level=95,
                scope_type="organization",
                permissions=["org.view", "org.edit", "org.settings", "audit.view", "audit.export"],
            )
            _MIGRATION.backward(django_apps, None)
            role.refresh_from_db()
            self.assertEqual(role.permissions, ["org.view", "org.edit", "audit.view"])


class OrganizationSettingsGateTest(_Base):
    def url(self):
        return reverse("organizations:settings", kwargs={"slug": self.org.slug})

    def test_template_holders_and_owner_still_pass(self):
        for key in ("vice_rector", "ikt_rehber", "rector"):
            self.assertEqual(self.client_for(self.user(key)).get(self.url()).status_code, 200, key)
        owner_client = self.client_for(self.A["owner"])
        self.assertEqual(owner_client.get(self.url()).status_code, 200)
        response = self.client_for(self.user("vice_rector")).post(self.url(), {"description": "yeni təsvir"})
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            self.org.refresh_from_db()
        self.assertEqual(self.org.description, "yeni təsvir")

    def test_without_org_settings_key_the_page_is_closed(self):
        self.strip("vice_rector", "org.settings")
        response = self.client_for(self.user("vice_rector")).get(self.url())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("organizations:dashboard", kwargs={"slug": self.org.slug}))

    def test_without_org_edit_key_get_is_open_but_post_is_closed(self):
        self.strip("vice_rector", "org.edit")
        client = self.client_for(self.user("vice_rector"))
        self.assertEqual(client.get(self.url()).status_code, 200)
        response = client.post(self.url(), {"description": "dəyişməməlidir"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("organizations:dashboard", kwargs={"slug": self.org.slug}))
        with bypass_rls():
            self.org.refresh_from_db()
        self.assertNotEqual(self.org.description, "dəyişməməlidir")

    def test_level_below_90_with_keys_is_still_closed(self):
        """Səviyyə qapısı qalır — açar tək başına kifayət etmir (dekan 80)."""
        self.grant("dean", "org.settings", "org.edit")
        self.assertEqual(self.client_for(self.user("dean")).get(self.url()).status_code, 302)


class PermissionEditorRoleEditTest(_Base):
    URL = "accounts:permission_editor"

    def _post_add(self, actor, target_role, permission):
        return self.client_for(actor).post(
            reverse(self.URL), {"role_id": str(target_role.id), "action": "add", "permission": permission}
        )

    def test_hr_with_role_assign_only_cannot_change_a_role(self):
        teacher_role = self.role("teacher")
        self.assertNotIn("schedule.view", teacher_role.permissions)
        response = self._post_add(self.user("hr"), teacher_role, "schedule.view")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("schedule.view", self.role("teacher").permissions)

    def test_role_star_holder_changes_a_role(self):
        teacher_role = self.role("teacher")
        response = self._post_add(self.user("ikt_rehber"), teacher_role, "schedule.view")
        self.assertEqual(response.status_code, 302)
        self.assertIn("schedule.view", self.role("teacher").permissions)

    def test_hr_can_still_open_the_editor(self):
        self.assertEqual(self.client_for(self.user("hr")).get(reverse(self.URL)).status_code, 200)


class AuditExportGateTest(_Base):
    RANGE_ALL = {"al_range": "all"}

    def test_template_holder_exports(self):
        response = self.client_for(self.user("trustee")).get(reverse("audit:export"), self.RANGE_ALL)
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode("utf-8").lstrip("﻿")
        self.assertTrue(next(csv.reader(io.StringIO(body))))

    def test_without_export_key_csv_is_403_and_button_hidden(self):
        self.strip("trustee", "audit.export")
        client = self.client_for(self.user("trustee"))
        self.assertEqual(client.get(reverse("audit:export"), self.RANGE_ALL).status_code, 403)
        page = client.get(reverse("audit:list"), self.RANGE_ALL)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["audit_log_section"]["export_url"], "")
        self.assertNotIn("data-al-export", page.content.decode())

    def test_owner_needs_no_key(self):
        response = self.client_for(self.A["owner"]).get(reverse("audit:export"), self.RANGE_ALL)
        self.assertEqual(response.status_code, 200)


class JournalViewKeyTest(_Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            subject = Subject.objects.create(organization=cls.org, code="W2101", name="Dalğa 2")
            cls.offering = registrar_services.get_or_create_offering(
                organization=cls.org, subject=subject, period=cls.period, group=cls.A["group"]
            )
            cls.offering.instructor = cls.A["users"]["teacher"]
            cls.offering.save(update_fields=["instructor"])
            Enrollment.objects.create(organization=cls.org, student=cls.A["users"]["student"], offering=cls.offering)

    def detail(self):
        return reverse("registrar:journal_detail", args=[self.offering.id])

    def test_dean_without_key_cannot_open_foreign_teacher_journal(self):
        # Dekan şablonu `journal.roster` daşıyır → jurnalı onsuz da açır; müqayisə üçün
        # `journal.view`-suz sırf oxu rolu: müəllim2 (instruktor deyil).
        self.assertEqual(self.client_for(self.user("teacher2")).get(self.detail()).status_code, 404)

    def test_unit_scoped_key_opens_journal_read_only_inside_scope(self):
        self.grant("dean", "journal.view")
        self.strip("dean", "journal.roster")
        in_scope = self.client_for(self.user("dean"))
        self.assertEqual(in_scope.get(self.detail()).status_code, 200)
        listing = in_scope.get(reverse("registrar:journal_list"))
        self.assertContains(listing, self.detail())
        # Yazı yolu bağlı qalır (birbaşa redaktor deyil).
        self.assertEqual(in_scope.post(self.detail(), {"action": "add_lesson"}).status_code, 404)
        # Alt-ağacı örtməyən dekan (Fak2) — 404, siyahıda da yoxdur.
        out_of_scope = self.client_for(self.user("dean2"))
        self.assertEqual(out_of_scope.get(self.detail()).status_code, 404)
        self.assertNotContains(out_of_scope.get(reverse("registrar:journal_list")), self.detail())

    def test_org_wide_key_opens_journal(self):
        """ORGANIZATION rolu (qəyyum, 78) — açarla bütün təşkilatın jurnalını oxuyur, onsuz 404."""
        trustee = self.client_for(self.user("trustee"))
        self.assertEqual(trustee.get(self.detail()).status_code, 404)
        self.grant("trustee", "journal.view")
        self.assertEqual(trustee.get(self.detail()).status_code, 200)
        self.assertEqual(trustee.post(self.detail(), {"action": "add_lesson"}).status_code, 404)


class AnalyticsViewOwnTest(_Base):
    def _profile(self, user):
        response = self.client_for(user).get(reverse("accounts:profile"), {"section": "statistics"})
        self.assertEqual(response.status_code, 200)
        return response.context["statistics_data"]["profile"]

    def test_teacher_and_student_profiles_need_the_key(self):
        self.assertEqual(self._profile(self.user("teacher")), "teacher")
        self.assertEqual(self._profile(self.user("student")), "student")
        self.strip("teacher", "analytics.view_own")
        self.strip("student", "analytics.view_own")
        self.assertEqual(self._profile(self.user("teacher")), "restricted")
        self.assertEqual(self._profile(self.user("student")), "restricted")

    def test_org_admin_profile_is_unaffected(self):
        self.assertEqual(self._profile(self.user("rector")), "org_admin")
