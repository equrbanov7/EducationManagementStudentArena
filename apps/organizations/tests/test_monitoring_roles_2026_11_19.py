"""Monitorinq şöbəsi rolları — şablon, miqrasiya 0085 (rollar + üzvlük köçürməsi), əhatə (sahib 2026-11-19).

Sahib: «Monitorinq şöbəsinə jurnallara, sillabuslara, fənn qovluqlarına FULL baxmaq icazəsi ver … Dərs cədvəlinə,
cədvəl idarəetməsinə baxmaq icazəsi olsun … Keçilmiş dərslərə və s.» — YALNIZ OXU, bütün təşkilat üzrə.
Səthlərin həqiqətən açılması: ``apps/accounts/tests/test_monitoring_readonly_2026_11_19.py``.
"""

from __future__ import annotations

from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.organizations.default_roles_monitoring import MONITORING_READ_PERMISSIONS, MONITORING_ROLES
from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.organizations.permissions import get_all_permissions, validate_permissions
from apps.organizations.public import get_permission_scope
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.permissions import has_permission
from core.rls import bypass_rls
from core.roles import ProfileRole

User = get_user_model()

_MIGRATION = import_module("apps.organizations.migrations.0085_monitoring_roles")
_ROLES = ("monitoring_head", "monitoring_staff")

#: Yeganə icazəli «yazma» açarı — hər heyət roluna avtomatik verilən öz ərizəsini göndərmək («Müraciətlərim»).
_SELF_SERVICE = {"application.create"}
#: Oxu açarının son hissəsi — bunlardan başqa heç nə dəstdə ola bilməz.
_READ_ACTIONS = {
    "view",
    "view_all",
    "view_unit",
    "view_teachers",
    "view_students",
    "report",
    "lessons_unit",
    "records_view",
    "registry_view",
}


def _by_name():
    return {role["name"]: role for role in UNIVERSITY_ROLES}


class TemplateTest(SimpleTestCase):
    def test_roles_are_in_the_university_set_below_the_admin_alias(self):
        by_name = _by_name()
        self.assertEqual({role["name"] for role in MONITORING_ROLES}, set(_ROLES))
        self.assertEqual(by_name["monitoring_head"]["level"], 70)
        self.assertEqual(by_name["monitoring_staff"]["level"], 60)
        for name in _ROLES:
            role = by_name[name]
            self.assertEqual(role["scope_type"], RoleScopeType.ORGANIZATION, name)
            self.assertLess(role["level"], 80, name)
            self.assertNotIn(ProfileRole.ORG_ADMIN, ProfileRole.aliases_for_membership_role(name, level=role["level"]))
            self.assertTrue(validate_permissions(role["permissions"]), name)

    def test_both_roles_carry_the_same_read_only_set(self):
        by_name = _by_name()
        head, staff = by_name["monitoring_head"]["permissions"], by_name["monitoring_staff"]["permissions"]
        self.assertEqual(sorted(head), sorted(staff))
        self.assertEqual(set(head), set(MONITORING_READ_PERMISSIONS) | _SELF_SERVICE)

    def test_not_a_single_write_key(self):
        permissions = _by_name()["monitoring_head"]["permissions"]
        self.assertNotIn("*", permissions)
        for key in permissions:
            self.assertFalse(key.endswith(".*"), key)
            if key in _SELF_SERVICE:
                continue
            self.assertIn(key.split(".", 1)[1], _READ_ACTIONS, key)
        # Kataloqdakı HƏR yazma açarı (oxu sonluğu olmayan) rədd edilir — yeni açar əlavə olunsa da test tutur.
        write_keys = [
            key for key in get_all_permissions() if key.split(".", 1)[-1] not in _READ_ACTIONS | {"view_own", "search"}
        ]
        self.assertGreater(len(write_keys), 80)
        granted = [key for key in write_keys if has_permission(permissions, key) and key not in _SELF_SERVICE]
        self.assertEqual(granted, [])

    def test_surface_keys_are_present_and_dropped_keys_are_absent(self):
        permissions = _by_name()["monitoring_staff"]["permissions"]
        for key in (
            "journal.view",  # jurnal siyahısı + istənilən jurnal + xlsx
            "journal.lessons_unit",  # «Keçilmiş dərslər»
            "syllabus.view",
            "subject_folder.view_unit",
            "schedule.view",  # «Cədvəl idarəetməsi» yalnız-oxu
            "people.view_teachers",
            "people.view_students",
            "unit.view",
            "plan.view",
            "semester.view",
            "workload.report",
            "analytics.view_all",
        ):
            self.assertIn(key, permissions, key)
        for key in (
            "audit.view",
            "audit.export",
            "accounting.view",
            "application.view_all",
            "people.hr_analytics",
            "people.view_demographics",
            "people.view_contacts",
            "role.view",
            "survey.results.view",
            "user.search",
            "exam.view",
            "appeal.create",
            "system.monitoring.view",
        ):
            self.assertFalse(has_permission(permissions, key), key)

    def test_migration_spec_matches_live_template(self):
        """Miqrasiya dondurulmuş spesifikasiya işlədir — şablonla EYNİ qalmalıdır."""
        by_name = _by_name()
        self.assertEqual({spec["name"] for spec in _MIGRATION.ROLE_SPECS}, set(_ROLES))
        for spec in _MIGRATION.ROLE_SPECS:
            live = by_name[spec["name"]]
            self.assertEqual(sorted(spec["permissions"]), sorted(live["permissions"]), spec["name"])
            for key in ("display_name", "level", "scope_type", "description"):
                self.assertEqual(spec[key], live[key], (spec["name"], key))

    def test_staff_roster_maps_the_department_and_nothing_else(self):
        from apps.accounts.services.staff_roster import role_for

        self.assertEqual(role_for("Monitorinq şöbəsi", "Müdir"), ("monitoring_head", True))
        self.assertEqual(role_for("MONİTORİNQ ŞÖBƏSİ", "Müdir əvəzi"), ("monitoring_head", True))
        self.assertEqual(role_for("Monitorinq şöbəsi", "Baş mütəxəssis"), ("monitoring_staff", True))
        self.assertEqual(role_for("Monitorinq şöbəsi", "Müdir müavini"), ("monitoring_staff", True))
        # Kölgə yoxdur: akademik bölmə və əvvəlki açar sözlər öz rolunda qalır.
        self.assertEqual(role_for("Ekoloji monitorinq kafedrası", "Müdir"), ("chair_head", True))
        self.assertEqual(role_for("Ekoloji monitorinq kafedrası", "Operator"), ("member", False))
        self.assertEqual(role_for("Tədrisin təşkili və monitorinq şöbəsi", "Müdir"), ("teaching_office_head", True))
        self.assertEqual(role_for("Arxiv şöbəsi", "Müdir"), ("admin_unit_head", True))

    def test_view_as_target_but_not_actor(self):
        from apps.accounts.services.view_as import ROLE_FILTER_MAP, ROLE_MODE_MAP

        for name in _ROLES:
            self.assertIn(name, ROLE_FILTER_MAP["staff"])  # «Əməkdaşlar» süzgəcində görünür
            self.assertNotIn(name, ROLE_MODE_MAP)  # org-wide «başqasının gözü ilə bax» verilmir


class _World(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("mon_owner", "mon_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="MON Univ", slug="mon-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active"
            )
            cls.monitoring = OrgUnit.objects.create(
                organization=cls.org, name="Monitorinq şöbəsi", slug="mon-dep", unit_type=OrgUnitType.DEPARTMENT
            )
            cls.archive = OrgUnit.objects.create(
                organization=cls.org, name="Arxiv şöbəsi", slug="mon-arch", unit_type=OrgUnitType.DEPARTMENT
            )
            faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="mon-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.eco_chair = OrgUnit.objects.create(
                organization=cls.org,
                name="Ekoloji monitorinq kafedrası",
                slug="mon-eco",
                unit_type=OrgUnitType.CHAIR,
                parent=faculty,
            )

    @classmethod
    def _member(cls, username, role_name, unit, *, is_active=True):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        return Membership.objects.create(
            user=user,
            organization=cls.org,
            role=cls.org.roles.get(name=role_name),
            scope_unit=unit,
            is_primary=True,
            is_active=is_active,
        )

    def _role_name(self, membership):
        membership.refresh_from_db()
        return membership.role.name


class SeedTest(_World):
    def test_new_university_gets_both_roles_from_the_template(self):
        with bypass_rls():
            for name in _ROLES:
                role = Role.objects.get(organization=self.org, name=name)
                self.assertEqual(role.scope_type, RoleScopeType.ORGANIZATION)
                self.assertEqual(set(role.permissions), set(MONITORING_READ_PERMISSIONS) | _SELF_SERVICE)

    def test_scope_unit_on_the_membership_does_not_narrow_the_scope(self):
        """ORGANIZATION rolunda ``scope_unit`` («Monitorinq şöbəsi») qalır, amma əhatə BÜTÜN təşkilatdır."""
        with bypass_rls():
            membership = self._member("mon_scope", "monitoring_head", self.monitoring)
            for key in ("journal.view", "syllabus.view", "subject_folder.view_unit", "schedule.view"):
                scope = get_permission_scope(membership.user, self.org, key)
                self.assertTrue(scope.is_org_wide, key)
            # Yazma açarı üçün əhatə YOXDUR (fail-closed).
            for key in ("schedule.manage", "journal.roster", "journal.correct", "grade.input", "syllabus.edit"):
                self.assertFalse(get_permission_scope(membership.user, self.org, key).has_structure_access, key)


class MigrationTest(_World):
    def test_moves_monitoring_memberships_and_keeps_the_unit(self):
        with bypass_rls():
            head = self._member("mon_head", "admin_unit_head", self.monitoring)
            staff = self._member("mon_staff", "member", self.monitoring)
            other_head = self._member("mon_arch_head", "admin_unit_head", self.archive)
            other_staff = self._member("mon_arch_staff", "member", self.archive)
            eco_member = self._member("mon_eco_member", "member", self.eco_chair)  # akademik bölmə — düşmür
            inactive = self._member("mon_inactive", "admin_unit_head", self.monitoring, is_active=False)
            unscoped = self._member("mon_unscoped", "member", None)

            _MIGRATION.forward(django_apps, None)
            _MIGRATION.forward(django_apps, None)  # idempotent

            self.assertEqual(self._role_name(head), "monitoring_head")
            self.assertEqual(self._role_name(staff), "monitoring_staff")
            self.assertEqual(head.scope_unit_id, self.monitoring.pk)  # şöbəsi üzvlükdə qalır
            self.assertEqual(staff.scope_unit_id, self.monitoring.pk)
            self.assertTrue(head.is_active and head.is_primary)
            self.assertEqual(self._role_name(other_head), "admin_unit_head")
            self.assertEqual(self._role_name(other_staff), "member")
            self.assertEqual(self._role_name(eco_member), "member")
            self.assertEqual(self._role_name(inactive), "admin_unit_head")
            self.assertEqual(self._role_name(unscoped), "member")
            # Köçürülən müdir bütün təşkilatın jurnallarını OXUYUR; köçürülməyən yox.
            self.assertTrue(get_permission_scope(head.user, self.org, "journal.view").is_org_wide)
            self.assertFalse(get_permission_scope(other_head.user, self.org, "journal.view").has_structure_access)

            _MIGRATION.backward(django_apps, None)
            self.assertEqual(self._role_name(head), "admin_unit_head")
            self.assertEqual(self._role_name(staff), "member")
            self.assertEqual(head.scope_unit_id, self.monitoring.pk)
            # Rol sətirləri yerində qalır.
            self.assertEqual(Role.objects.filter(organization=self.org, name__in=_ROLES).count(), 2)

    def test_creates_missing_roles_and_tops_up_existing_ones(self):
        with bypass_rls():
            Role.objects.filter(organization=self.org, name="monitoring_staff").delete()
            head_role = Role.objects.get(organization=self.org, name="monitoring_head")
            head_role.permissions = ["unit.view", "audit.view"]  # tenant redaktordan dəyişib
            head_role.save(update_fields=["permissions"])

            _MIGRATION.forward(django_apps, None)

            staff_role = Role.objects.get(organization=self.org, name="monitoring_staff")
            self.assertEqual(staff_role.level, 60)
            self.assertEqual(staff_role.scope_type, RoleScopeType.ORGANIZATION)
            self.assertTrue(staff_role.is_system and staff_role.is_active)
            self.assertEqual(set(staff_role.permissions), set(MONITORING_READ_PERMISSIONS) | _SELF_SERVICE)
            head_role.refresh_from_db()
            self.assertEqual(head_role.permissions[:2], ["unit.view", "audit.view"])  # mövcud açarlar silinmir
            self.assertTrue(set(MONITORING_READ_PERMISSIONS) <= set(head_role.permissions))
            self.assertEqual(len(head_role.permissions), len(set(head_role.permissions)))

    def test_existing_target_membership_is_not_duplicated(self):
        with bypass_rls():
            old = self._member("mon_dup", "admin_unit_head", self.monitoring)
            Membership.objects.filter(pk=old.pk).update(is_primary=False)
            already = Membership.objects.create(
                user=old.user,
                organization=self.org,
                role=self.org.roles.get(name="monitoring_head"),
                scope_unit=self.monitoring,
                is_active=True,
            )
            _MIGRATION.forward(django_apps, None)
            self.assertEqual(self._role_name(old), "admin_unit_head")  # unikal məhdudiyyət — köhnə sətir toxunulmur
            self.assertEqual(self._role_name(already), "monitoring_head")

    def test_unit_name_match_is_case_and_dotted_i_insensitive(self):
        self.assertTrue(_MIGRATION.is_monitoring_unit("MONİTORİNQ ŞÖBƏSİ", "department"))
        self.assertTrue(_MIGRATION.is_monitoring_unit("Keyfiyyət və Monitorinq mərkəzi", "center"))
        self.assertFalse(_MIGRATION.is_monitoring_unit("Ekoloji monitorinq kafedrası", "chair"))
        self.assertFalse(_MIGRATION.is_monitoring_unit("Arxiv şöbəsi", "department"))
        self.assertFalse(_MIGRATION.is_monitoring_unit("", ""))
