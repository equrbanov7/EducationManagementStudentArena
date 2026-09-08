"""Kataloq — sahib istəkləri (2026-09-07).

* TƏLƏBƏYƏ müəllim statusu verilmir: detal kartında düymə çıxmır, POST 409;
* müəllimi kafedraya təyin et / kafedrasını dəyiş (`assign_unit`) — scope-lu,
  auditli; sahədən kənar kafedra 404;
* tələbə sətri `record_id` daşıyır (sətirdən birbaşa qrup köçürməsi üçün),
  müəllim sətri `unit_id` daşıyır (dialoqda cari kafedra seçili gəlsin).
"""

from __future__ import annotations

from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.services import people
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, OrgUnit
from core.constants import OrgUnitType
from core.rls import bypass_rls

from .people_fixture import PeopleFixture


def _request(user, organization):
    request = RequestFactory().get("/accounts/profile/")
    request.user = user
    request.organization = organization
    return request


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()
        with bypass_rls():
            cls.kafedra_a2 = OrgUnit.objects.create(
                organization=cls.fx.org,
                name="Kafedra A2",
                slug="kaf-a2",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.fx.faculty_a,
            )

    def setUp(self):
        self.client = Client()

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization_id"] = str(self.fx.org.pk)
        session.save()

    def _post(self, payload):
        with bypass_rls():
            return self.client.post(reverse("accounts:people_action"), data=payload, content_type="application/json")


class GrantTeacherToStudentTest(_Base):
    def test_post_is_rejected_with_409(self):
        self._login(self.fx.dean_a)
        response = self._post(
            {"action": "grant_teacher", "user_id": self.fx.student_a.pk, "unit_id": str(self.fx.kafedra_a1.pk)}
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "target_is_student")
        self.assertFalse(
            Membership.objects.filter(
                organization=self.fx.org, user=self.fx.student_a, role=self.fx.role_teacher, is_active=True
            ).exists()
        )

    def test_detail_hides_grant_for_student_and_offers_assign_unit_for_teacher(self):
        actor = people.resolve_actor(_request(self.fx.dean_a, self.fx.org))
        with bypass_rls():
            student = people.build_detail(actor=actor, user_id=self.fx.student_a.pk)["person"]["actions"]
            teacher = people.build_detail(actor=actor, user_id=self.fx.teacher_a.pk)["person"]["actions"]
        self.assertFalse(student["grant_teacher"])
        self.assertFalse(student["assign_unit"])
        self.assertTrue(teacher["assign_unit"])
        self.assertFalse(teacher["grant_teacher"])


class AssignUnitTest(_Base):
    def test_moves_membership_and_audits(self):
        self._login(self.fx.dean_a)
        response = self._post(
            {
                "action": "assign_unit",
                "user_id": self.fx.teacher_a.pk,
                "unit_id": str(self.kafedra_a2.pk),
                "reason": "Kafedra yenidən təşkil olundu",
            }
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["result"]["unit_name"], "Kafedra A2")
        self.assertEqual(body["result"]["memberships_changed"], 1)
        membership = Membership.objects.get(organization=self.fx.org, user=self.fx.teacher_a, role=self.fx.role_teacher)
        self.assertEqual(membership.scope_unit_id, self.kafedra_a2.pk)
        self.assertTrue(membership.is_active)
        self.assertTrue(
            AuditLog.objects.filter(organization=self.fx.org, changes__action="people.teacher_unit_assigned").exists()
        )

    def test_same_unit_is_409(self):
        self._login(self.fx.dean_a)
        response = self._post(
            {"action": "assign_unit", "user_id": self.fx.teacher_a.pk, "unit_id": str(self.fx.kafedra_a1.pk)}
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "unit_unchanged")

    def test_unit_outside_scope_is_404(self):
        self._login(self.fx.dean_a)
        response = self._post(
            {"action": "assign_unit", "user_id": self.fx.teacher_a.pk, "unit_id": str(self.fx.kafedra_b1.pk)}
        )
        self.assertEqual(response.status_code, 404, response.content)

    def test_requires_unit(self):
        self._login(self.fx.dean_a)
        response = self._post({"action": "assign_unit", "user_id": self.fx.teacher_a.pk})
        self.assertEqual(response.status_code, 400, response.content)

    def test_without_permission_is_denied(self):
        self._login(self.fx.chair_a1)  # yalnız oxu icazələri
        response = self._post(
            {"action": "assign_unit", "user_id": self.fx.teacher_a.pk, "unit_id": str(self.kafedra_a2.pk)}
        )
        self.assertEqual(response.status_code, 403, response.content)


class RowIdentifiersTest(_Base):
    def test_student_rows_carry_record_id_and_teacher_rows_unit_id(self):
        self._login(self.fx.dean_a)
        with bypass_rls():
            students = self.client.get(reverse("accounts:people_list", kwargs={"kind": "students"})).json()
            teachers = self.client.get(reverse("accounts:people_list", kwargs={"kind": "teachers"})).json()
        student_row = next(row for row in students["results"] if row["username"] == "ppl_student_a")
        self.assertTrue(student_row["record_id"])
        teacher_row = next(row for row in teachers["results"] if row["username"] == "ppl_teacher_a")
        self.assertEqual(teacher_row["unit_id"], str(self.fx.kafedra_a1.pk))

    def test_directory_renders_bulk_bar_and_dialogs(self):
        self._login(self.fx.dean_a)
        with bypass_rls():
            teachers = self.client.get("/accounts/profile/?section=people-teachers", follow=True)
            students = self.client.get("/accounts/profile/?section=people-students", follow=True)
        html_t = teachers.content.decode("utf-8")
        html_s = students.content.decode("utf-8")
        self.assertIn('data-people-bulk="assign_unit"', html_t)
        self.assertIn('id="people-unit-dialog-teachers"', html_t)
        self.assertIn("data-people-select-all", html_t)
        self.assertIn('id="people-reason-dialog-students"', html_s)
        # Tələbə kataloqunda qrup dialoqu YALNIZ manage_academic ilə (dekan A-da yoxdur).
        self.assertNotIn('id="people-group-dialog-students"', html_s)
        self.assertNotIn("window.prompt", html_s)
