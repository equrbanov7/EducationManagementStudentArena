"""«Əcnəbi tələbələrlə iş şöbəsi» (sahib 2026-11-25): YALNIZ əcnəbi qrupları üzrə tam tələbə dövrəsi + «Tarixçə».

Qurğu (``SubgroupFixture``): ``Fakültə → Kafedra → {G1, G2, 01-əcnəbilər2026}`` + ``Uzaq fakültə → GX``; şöbə bölməsi
«Əcnəbi tələbələrlə iş şöbəsi» (department). Şöbə müdiri ``admin_unit_head``, əməkdaşı ``member`` — sinxron onlara
əcnəbi qrupu üçün yeni rolları verir. Hər əməl üçün: əcnəbi qrupunda işləyir, eyni fakültənin ADİ qrupunda (G1) yox.
"""

from __future__ import annotations

import datetime
import importlib
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.organizations import foreign_office_sync
from apps.organizations.default_roles_foreign_office import (
    FOREIGN_STUDENTS_HEAD_ROLE,
    FOREIGN_STUDENTS_PERMISSIONS,
    FOREIGN_STUDENTS_STAFF_ROLE,
    is_foreign_group,
    is_foreign_office_unit,
)
from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import Membership, OrgUnit
from apps.organizations.permissions import get_all_permissions
from apps.organizations.scoping import faculty_read_scope, get_permission_scope
from apps.registrar.models import Enrollment, Lesson, LessonMark, StudentAcademicRecord
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.constants import OrgUnitType
from core.rls import bypass_rls

MIGRATION = importlib.import_module("apps.organizations.migrations.0087_foreign_students_office")


class ForeignOfficeBase(SubgroupFixture, TestCase):
    PREFIX = "fso"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.office = OrgUnit.objects.create(
                organization=cls.org,
                name="Əcnəbi tələbələrlə iş şöbəsi",
                slug="fso-office",
                unit_type=OrgUnitType.DEPARTMENT,
            )
            cls.foreign = OrgUnit.objects.create(
                organization=cls.org,
                name="01-əcnəbilər2026",
                slug="fso-ecn1",
                unit_type=OrgUnitType.GROUP,
                parent=cls.chair,
            )
            cls.foreign_student = cls._student("fso_foreign", cls.foreign)
            cls.head = cls._member("fso_head", cls.org.roles.get(name="admin_unit_head"), cls.office)
            cls.staff = cls._member("fso_staff", cls.org.roles.get(name="member"), cls.office)
            for user in (cls.head, cls.staff, cls.host, cls.student, cls.foreign_student):
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])
            counts, wanted = foreign_office_sync.plan(cls.org)
            foreign_office_sync.apply(cls.org, wanted)

    def record_of(self, student):
        with bypass_rls():
            return StudentAcademicRecord.objects.get(organization=self.org, student=student)

    def get_json(self, user, url):
        with bypass_rls():
            return self.client_for(user).get(url)


class RoleTemplateTest(ForeignOfficeBase):
    def test_template_matches_frozen_migration_and_catalog(self):
        templates = {role["name"]: role for role in UNIVERSITY_ROLES}
        catalog = set(get_all_permissions())
        for name in (FOREIGN_STUDENTS_HEAD_ROLE, FOREIGN_STUDENTS_STAFF_ROLE):
            permissions = set(templates[name]["permissions"])
            self.assertEqual(permissions, set(MIGRATION._PERMISSIONS), name)
            self.assertEqual(templates[name]["scope_type"], "unit")
            self.assertLess(templates[name]["level"], 80)
            for key in permissions:
                self.assertIn(key, catalog, key)
            for key in ("student.movement", "user.import", "journal.view", "people.manage_academic"):
                self.assertIn(key, permissions)
            for key in ("workload.view", "workload.review", "workload.distribute", "role.assign", "*"):
                self.assertNotIn(key, permissions)
        coordinator = set(templates["program_coordinator"]["permissions"])
        missing = coordinator - set(FOREIGN_STUDENTS_PERMISSIONS) - {"application.create"}
        self.assertEqual(missing, {"workload.view", "workload.review", "application.handle"})

    def test_name_rules(self):
        self.assertTrue(is_foreign_group("04-əcnəbilər 2026"))
        self.assertTrue(is_foreign_group("01-ƏCNƏBİLƏR2026"))
        self.assertFalse(is_foreign_group("0055 / 1 (az)"))
        self.assertFalse(is_foreign_group("01-əcnəbilər2026", "specialty"))
        self.assertTrue(is_foreign_office_unit("Əcnəbi tələbələrlə iş şöbəsi", "department"))
        self.assertFalse(is_foreign_office_unit("01-əcnəbilər2026", "group"))


class SyncTest(ForeignOfficeBase):
    def test_office_people_get_one_membership_per_foreign_group(self):
        with bypass_rls():
            rows = Membership.objects.filter(organization=self.org, scope_unit=self.foreign, is_active=True)
            by_user = {row.user_id: row.role.name for row in rows.select_related("role")}
        self.assertEqual(by_user[self.head.pk], FOREIGN_STUDENTS_HEAD_ROLE)
        self.assertEqual(by_user[self.staff.pk], FOREIGN_STUDENTS_STAFF_ROLE)
        # Şöbə üzvlüyü QALIR.
        with bypass_rls():
            self.assertTrue(Membership.objects.filter(user=self.staff, scope_unit=self.office, is_active=True).exists())

    def test_sync_is_idempotent_and_picks_up_new_group(self):
        with bypass_rls():
            counts, wanted = foreign_office_sync.plan(self.org)
            self.assertEqual((counts["create"], counts["already"], wanted), (0, 2, []))
            second = OrgUnit.objects.create(
                organization=self.org,
                name="02-əcnəbilər2026",
                slug="fso-ecn2",
                unit_type=OrgUnitType.GROUP,
                parent=self.chair,
            )
            counts, wanted = foreign_office_sync.plan(self.org)
            self.assertEqual(counts["create"], 2)
            self.assertEqual(foreign_office_sync.apply(self.org, wanted), 2)
            self.assertEqual(
                Membership.objects.filter(scope_unit=second, role__name=FOREIGN_STUDENTS_STAFF_ROLE).count(), 1
            )

    def test_migration_forward_is_idempotent(self):
        from django.apps import apps as django_apps

        with bypass_rls():
            before = Membership.objects.filter(organization=self.org).count()
            MIGRATION.forward(django_apps, None)
            self.assertEqual(Membership.objects.filter(organization=self.org).count(), before)


class ExactScopeTest(ForeignOfficeBase):
    def test_read_scope_is_not_widened_to_the_faculty(self):
        with bypass_rls():
            for permission in ("unit.view", "people.view_students", "student.registry_view"):
                scope = faculty_read_scope(self.staff, self.org, permission)
                self.assertEqual(set(scope.unit_ids), {self.foreign.pk}, permission)
            write = get_permission_scope(self.staff, self.org, "people.manage_academic")
            self.assertEqual(set(write.unit_ids), {self.foreign.pk})

    def test_tutor_on_a_group_still_widens(self):
        with bypass_rls():
            tutor = self._member("fso_tutor", self.org.roles.get(name="tutor"), self.group1)
            scope = faculty_read_scope(tutor, self.org, "unit.view")
        self.assertEqual(set(scope.unit_ids), {self.faculty.pk})

    def test_group_drawer_only_for_foreign_group(self):
        ok = self.get_json(self.staff, reverse("organizations:group_students", args=[self.org.slug, self.foreign.pk]))
        self.assertEqual(ok.status_code, 200)
        body = ok.json()
        self.assertTrue(body["can_manage"] and body["can_move_students"])
        self.assertEqual([row["username"] for row in body["rows"]], ["fso_foreign"])
        self.assertTrue(body["rows"][0]["history_url"])
        other = self.get_json(self.staff, reverse("organizations:group_students", args=[self.org.slug, self.group1.pk]))
        self.assertEqual(other.status_code, 404)


class MovementTest(ForeignOfficeBase):
    def _freeze(self, user, record):
        with bypass_rls():
            return self.client_for(user).post(
                reverse("accounts:student_registry_action"),
                {
                    "record_id": str(record.pk),
                    "kind": "academic_leave",
                    "order_number": "12/Ə",
                    "order_date": "2025-11-20",
                    "effective_until": "2030-06-30",
                    "leave_reason": "maternity",
                },
            )

    def test_freeze_own_foreign_student(self):
        record = self.record_of(self.foreign_student)
        response = self._freeze(self.staff, record)
        self.assertEqual(response.status_code, 200, response.content)
        record.refresh_from_db()
        self.assertEqual(record.status, "academic_leave")

    def test_cannot_freeze_student_of_ordinary_group(self):
        record = self.record_of(self.host)
        response = self._freeze(self.staff, record)
        self.assertEqual(response.status_code, 404, response.content)
        record.refresh_from_db()
        self.assertEqual(record.status, "enrolled")


class StudentCreateScopeTest(ForeignOfficeBase):
    def test_scope_helpers(self):
        from apps.accounts.services.intake.scope import enforce_group_scope, group_allowed, scope_groups
        from apps.accounts.services.intake.validate import RowPlan

        with bypass_rls():
            self.assertTrue(group_allowed(self.staff, self.org, self.foreign))
            self.assertFalse(group_allowed(self.staff, self.org, self.group1))
            groups = scope_groups(
                OrgUnit.objects.filter(organization=self.org, unit_type="group"), self.staff, self.org
            )
            self.assertEqual(set(groups.values_list("pk", flat=True)), {self.foreign.pk})
            inside, outside, unassigned = RowPlan(row=2), RowPlan(row=3), RowPlan(row=4)
            inside.targets["group"] = self.foreign
            outside.targets["group"] = self.group1
            enforce_group_scope([inside, outside, unassigned], user=self.staff, organization=self.org)
            self.assertEqual((inside.status, outside.status, unassigned.status), ("create", "error", "error"))
            self.assertEqual(outside.code, "group_outside_scope")
            # Org-wide aktor (sahib) — dəyişiklik yoxdur.
            plan = RowPlan(row=5)
            plan.targets["group"] = self.group1
            enforce_group_scope([plan], user=self.owner, organization=self.org)
            self.assertEqual(plan.status, "create")

    def test_rim_catalog_lists_only_foreign_groups(self):
        response = self.get_json(self.staff, reverse("accounts:rim_create_catalog") + "?catalog=group&q=")
        self.assertEqual(response.status_code, 200, response.content)
        names = {item.get("name") or item.get("text") for item in response.json().get("results", [])}
        self.assertIn("01-əcnəbilər2026", " ".join(str(name) for name in names))
        self.assertNotIn("G1", names)


class HistoryTest(ForeignOfficeBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            enrollment = Enrollment.objects.filter(student=cls.foreign_student).select_related("offering").first()
            cls.enrollment = enrollment
            for day, score in ((10, Decimal("8")), (15, Decimal("6")), (25, None)):
                lesson = Lesson.objects.create(
                    organization=cls.org, offering=enrollment.offering, date=datetime.date(2025, 11, day), hours=2
                )
                LessonMark.objects.create(
                    organization=cls.org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status="present" if score is not None else "absent",
                    score=score,
                )

    def url(self, unit, record):
        return reverse("organizations:group_student_history", args=[self.org.slug, unit.pk, record.pk])

    def test_frozen_student_keeps_statistics_before_freeze(self):
        record = self.record_of(self.foreign_student)
        with bypass_rls():
            response = self.client_for(self.staff).post(
                reverse("accounts:student_registry_action"),
                {
                    "record_id": str(record.pk),
                    "kind": "academic_leave",
                    "order_number": "5/Ə",
                    "order_date": "2025-11-20",
                    "effective_until": "2030-06-30",
                    "leave_reason": "maternity",
                },
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.enrollment.refresh_from_db()
            self.assertEqual(self.enrollment.status, "suspended")
        body = self.get_json(self.staff, self.url(self.foreign, record)).json()
        self.assertEqual(body["freeze"]["date"], "20.11.2025")
        row = next(
            r for p in body["periods"] for r in p["rows"] if r["subject"] == self.enrollment.offering.subject.name
        )
        self.assertEqual((row["marks"], row["marks_before_freeze"], row["absent"]), (2, 2, 1))
        self.assertEqual(row["average"], 7.0)
        self.assertEqual(row["status"], "suspended")
        self.assertEqual(body["movements"][0]["kind"], "academic_leave")

    def test_record_outside_group_is_404(self):
        response = self.get_json(self.staff, self.url(self.foreign, self.record_of(self.host)))
        self.assertEqual(response.status_code, 404)

    def test_actor_without_records_view_is_refused(self):
        response = self.get_json(self.plain, self.url(self.foreign, self.record_of(self.foreign_student)))
        self.assertIn(response.status_code, (403, 404))
