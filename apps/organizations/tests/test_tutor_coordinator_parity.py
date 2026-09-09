"""Tyutor = proqram koordinatoru — eyni icazə dəsti (sahib qərarı, 2026-09-09).

SAHİBİN SÖZÜ: «Bu hissə proqram koordinatoru və tyutorda olacaq — onlar 2-si
eyni rol özəlliklərinə malik olmalıdır; elə deyilsə əl et onu».

Nəyi qoruyur
------------
1. Seed xəritəsi (`default_roles_university`) hər iki rola EYNİ BAZA açar
   dəstini (`_COORDINATOR_PERMISSIONS`) verir; fərq yalnız `level` (40 / 45)
   və göstərilən addır.

   ⚠️ ƏHATƏ QEYDİ: koordinatora BAŞQA modullardan da açar əkilir
   (`default_roles_stage2/stage4/student_services/teaching_office` və
   müraciət qrantları). Bu tapşırığın əhatəsi `default_roles_university`
   BAZA dəsti idi — həmin modullar toxunulmayıb, ona görə koordinatorun
   yekun siyahısı hələ də daha uzundur. Test məhz bu sərhədi sabitləyir:
   baza dəsti EYNİ, əlavə modul qrantları isə fərqli qala bilər.
2. Yeni tenantda tyutor `schedule.manage` alır — «Cədvəl idarəetməsi» bölməsi
   ona açılır (əvvəl açılmırdı).
3. `0050_tutor_coordinator_parity` migrasiyası MÖVCUD tenantı da düzəldir və
   İDEMPOTENTDİR: təkrar icra açarları çoxaltmır, `*` (wildcard) rolu və
   `level` toxunulmur.
"""

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.default_roles_university import _COORDINATOR_PERMISSIONS, UNIVERSITY_ROLES
from apps.organizations.models import Organization, Role
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


def _seed(name):
    return next(row for row in UNIVERSITY_ROLES if row["name"] == name)


def _migration():
    import importlib

    return importlib.import_module("apps.organizations.migrations.0050_tutor_coordinator_parity")


class TutorSeedParityTest(TestCase):
    """Seed xəritəsi — YENİ tenant üçün."""

    def test_base_permission_sets_are_identical(self):
        tutor = set(_seed("tutor")["permissions"])
        coordinator = set(_seed("program_coordinator")["permissions"])
        base = set(_COORDINATOR_PERMISSIONS)
        self.assertTrue(base <= tutor, sorted(base - tutor))
        self.assertTrue(base <= coordinator, sorted(base - coordinator))
        # Tyutorun köhnə «yalnız baxış» dəsti geri qayıtmasın.
        for key in ("schedule.manage", "schedule.view", "group.manage", "journal.roster", "people.manage_academic"):
            self.assertIn(key, tutor, key)

    def test_level_and_display_name_stay_different(self):
        tutor = _seed("tutor")
        coordinator = _seed("program_coordinator")
        self.assertEqual(tutor["level"], 40)
        self.assertEqual(coordinator["level"], 45)
        self.assertEqual(tutor["display_name"], "Tutor")
        self.assertEqual(tutor["scope_type"], coordinator["scope_type"])

    def test_new_tenant_tutor_can_manage_the_timetable(self):
        owner = User.objects.create_user("tcp_owner", "tcp_owner@qku.edu.az", "pw")
        with bypass_rls():
            org = Organization.objects.create(
                name="TCP Univ",
                slug="tcp-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            tutor = org.roles.get(name="tutor")
            coordinator = org.roles.get(name="program_coordinator")
        self.assertIn("schedule.manage", tutor.permissions)
        self.assertIn("schedule.view", tutor.permissions)
        self.assertTrue(set(_COORDINATOR_PERMISSIONS) <= set(tutor.permissions))
        self.assertTrue(set(_COORDINATOR_PERMISSIONS) <= set(coordinator.permissions))
        self.assertEqual(tutor.level, 40)


class TutorMigrationTest(TestCase):
    """`0050_tutor_coordinator_parity` — MÖVCUD tenantlar üçün, idempotent."""

    OLD_KEYS = ["member.view", "course.view", "exam.view", "people.view_students", "analytics.view_unit"]

    def setUp(self):
        self.owner = User.objects.create_user("tcpm_owner", "tcpm_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="TCPM Univ",
                slug="tcpm-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
        self.migration = _migration()

    def _tutor(self):
        with bypass_rls():
            return Role.objects.get(organization=self.org, name="tutor")

    def _reset_to_old_state(self):
        with bypass_rls():
            role = self._tutor()
            role.permissions = list(self.OLD_KEYS)
            role.save(update_fields=["permissions"])

    def test_forward_grants_the_missing_keys(self):
        self._reset_to_old_state()
        with bypass_rls():
            self.migration.forward(django_apps, None)
            role = self._tutor()
        self.assertIn("schedule.manage", role.permissions)
        self.assertEqual(sorted(role.permissions), sorted(_COORDINATOR_PERMISSIONS))
        self.assertEqual(role.level, 40)
        self.assertEqual(role.display_name, "Tutor")

    def test_forward_is_idempotent(self):
        self._reset_to_old_state()
        with bypass_rls():
            self.migration.forward(django_apps, None)
            first = list(self._tutor().permissions)
            self.migration.forward(django_apps, None)
            second = list(self._tutor().permissions)
        self.assertEqual(first, second)
        self.assertEqual(len(second), len(set(second)))

    def test_wildcard_roles_are_left_alone(self):
        with bypass_rls():
            role = self._tutor()
            role.permissions = ["*"]
            role.save(update_fields=["permissions"])
            self.migration.forward(django_apps, None)
            role = self._tutor()
        self.assertEqual(role.permissions, ["*"])

    def test_backward_keeps_the_historic_view_keys(self):
        self._reset_to_old_state()
        with bypass_rls():
            self.migration.forward(django_apps, None)
            self.migration.backward(django_apps, None)
            role = self._tutor()
        self.assertEqual(sorted(role.permissions), sorted(self.OLD_KEYS))
