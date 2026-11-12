"""RİM əməkdaşının (``rim_staff``) gündəlik girişi — sahib 2026-11-12.

Sahib: «yük bölgüsü, fənn təhvili, qruplar, RİM mərkəzi … parol sıfırlanması. Gündəlik olaraq ən çox lazım olan nə
varsa hamısına access-i olsun. Gün əlavə etmək, çıxarmaq, silmək və s., alt qrup əlavə etmək». Köhnə şablonda
əməkdaş bu bölmələrin heç birini görmürdü (yalnız-oxu rolu idi) və başqa müəllimin jurnalında dərs günü yarada
bilmirdi. Testlər: bölmələr rim_staff-a açılır, müəllim / tələbə üçün bağlı qalır; rəhbərə məxsus səthlər
(Sistem tənzimləmələri, rol redaktoru, jurnal təmizliyi) əməkdaşa açılmır; ``journal.direct_edit`` yalnız DƏQİQ
açarla işləyir (rektorun ``*`` şablonu jurnal redaktoru olmur).
"""

import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.organizations.default_roles import get_default_roles_for_org_type
from apps.organizations.models import Membership, Role
from apps.organizations.permissions import get_all_permissions
from apps.organizations.permissions_rim_staff import PERM_JOURNAL_DIRECT_EDIT, RIM_STAFF_DAILY_PERMISSIONS
from apps.registrar import journal_access, journal_full_edit
from apps.syllabus.tests.factories import make_academic_stack, make_offering, make_org
from core.rls import bypass_rls

User = get_user_model()

#: Sahibin sadaladığı gündəlik bölmələr (kabinet bölmə açarları).
DAILY_SECTIONS = (
    "rim-center",
    "account-password-reset",
    "workload-distribution",
    "workload-center",
    "teaching-handover",
    "groups-registry",
    "student-registry",
    "subgroup-placement",
    "subgroup-students",
    "lessons-log",
    "schedule-manage",
)

#: RİM RƏHBƏRİNƏ (və superadmin) məxsus qalan səthlər.
HEAD_ONLY_SECTIONS = ("system-settings", "journal-hygiene", "journal-removals", "org-roles", "permission-editor")


class TemplateTest(SimpleTestCase):
    def test_every_daily_key_is_in_the_catalog_and_the_template(self):
        catalog = set(get_all_permissions())
        roles = {role["name"]: role["permissions"] for role in get_default_roles_for_org_type("university")}
        for key in RIM_STAFF_DAILY_PERMISSIONS:
            self.assertIn(key, catalog, key)
            self.assertIn(key, roles["rim_staff"], key)

    def test_head_only_keys_stay_out(self):
        permissions = set(
            next(r for r in get_default_roles_for_org_type("university") if r["name"] == "rim_staff")["permissions"]
        )
        for key in ("*", "role.*", "role.assign", "role.edit", "user.soft_delete", "user.import", "journal.correct"):
            self.assertNotIn(key, permissions, key)


@override_settings(RATELIMIT_ENABLE=False)
class DailyAccessTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("rimday-univ")
            cls.stack = make_academic_stack(cls.org, code="RIMD101")
            cls.teacher = User.objects.create_user("rimday_teacher", "rimday_teacher@qku.edu.az", "pw")
            cls.staff = User.objects.create_user("rimday_staff", "rimday_staff@qku.edu.az", "pw")
            cls.student = User.objects.create_user("rimday_student", "rimday_student@qku.edu.az", "pw")
            cls.rector = User.objects.create_user("rimday_rector", "rimday_rector@qku.edu.az", "pw")
            for user, role_name in (
                (cls.teacher, "teacher"),
                (cls.staff, "rim_staff"),
                (cls.student, "student"),
                (cls.rector, "rector"),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role_name),
                    is_primary=True,
                    is_active=True,
                )
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])
            cls.offering = make_offering(cls.org, cls.stack, cls.teacher)

    def _sections(self, user):
        client = Client()
        client.force_login(user)
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return set(response.context["allowed_sections"])

    def test_rim_staff_sees_daily_sections(self):
        sections = self._sections(self.staff)
        for section in DAILY_SECTIONS:
            self.assertIn(section, sections, section)
        for section in HEAD_ONLY_SECTIONS:
            self.assertNotIn(section, sections, section)

    def test_teacher_and_student_stay_closed(self):
        for user in (self.teacher, self.student):
            sections = self._sections(user)
            for section in DAILY_SECTIONS:
                self.assertNotIn(section, sections, (user.username, section))

    def test_daily_sections_render_for_rim_staff(self):
        client = Client()
        client.force_login(self.staff)
        for section in DAILY_SECTIONS:
            response = client.get(reverse("accounts:profile") + f"?section={section}")
            self.assertEqual(response.status_code, 200, section)
            self.assertEqual(response.context.get("active_section"), section, section)

    def test_rim_staff_edits_another_teachers_journal(self):
        self.assertTrue(journal_access.can_edit_journal(self.staff, self.offering))
        self.assertTrue(journal_access.is_direct_editor(self.staff, self.offering))

    def test_wildcard_and_other_roles_do_not_become_journal_editors(self):
        for user in (self.rector, self.student):
            fresh = User.objects.get(pk=user.pk)
            self.assertFalse(journal_access.is_direct_editor(fresh, self.offering), user.username)

    def test_direct_edit_follows_the_role_key(self):
        role = self.org.roles.get(name="rim_staff")
        with bypass_rls():
            Role.objects.filter(pk=role.pk).update(
                permissions=[key for key in role.permissions if key != PERM_JOURNAL_DIRECT_EDIT]
            )
        fresh = User.objects.get(pk=self.staff.pk)
        self.assertFalse(journal_access.is_direct_editor(fresh, self.offering))
        self.assertFalse(journal_full_edit.active_for(fresh, self.offering))


class MigrationTest(TestCase):
    """``organizations/0082`` mövcud tenantın rim_staff roluna açarları idempotent əlavə edir."""

    def test_forward_is_idempotent_and_backward_restores(self):
        migration = importlib.import_module("apps.organizations.migrations.0082_rim_staff_daily_access")
        with bypass_rls():
            org = make_org("rimday-mig")
            role = org.roles.get(name="rim_staff")
            Role.objects.filter(pk=role.pk).update(permissions=["unit.view", "user.search"])

            from django.db import connection

            with connection.schema_editor() as editor:
                migration.forward(django_apps, editor)
                migration.forward(django_apps, editor)
            role.refresh_from_db()
            for key in migration._KEYS:
                self.assertEqual(role.permissions.count(key), 1, key)
            self.assertIn("unit.view", role.permissions)

            with connection.schema_editor() as editor:
                migration.backward(django_apps, editor)
            role.refresh_from_db()
            self.assertEqual(role.permissions, ["unit.view"])
