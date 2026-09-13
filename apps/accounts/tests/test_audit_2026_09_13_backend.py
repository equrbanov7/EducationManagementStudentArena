"""Backend auditi 2026-09-13 — accounts tapıntıları.

* F-02 (P1): legacy «rol təyin et» axını (``manage_roles`` assign/remove) audit
  yazmırdı → ``_sync_user_role_memberships`` rol dəsti dəyişəndə ``AuditLog``
  yazır (köhnə → yeni, aktor, request).
* F-04: superadmin təşkilat approve/reject/suspend/unsuspend və hərf/GPA
  şkalası (set/reset) audit-siz idi → hər budaqda ``AuditLog``.
* F-01: ``superadmin_organizations`` ``organization_id="abc"`` → 500 idi → 404.
* F-07: yuxarıdakı status budaqları ``transaction.atomic`` içindədir.
* F-10: «200 + ok:false» zərfləri düzgün HTTP statusla (403/404/400/502).
* F-05: statistika kartı «ÜOMG (GPA)» → «Orta GPA (4.0)» (100 ballıq transkript
  ÜOMG-si ilə eyni ad daşımasın; düsturlar dəyişmir).
"""

from __future__ import annotations

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.services.statistics_metrics.presenter import present_student
from apps.accounts.services.statistics_metrics.student import student_metrics
from apps.accounts.tests.test_manage_roles_scope import ManageRolesScopeTest
from apps.accounts.tests.test_schedule_editor_ui import ScheduleEditorUIBase
from apps.audit.models import AuditLog
from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class RoleSyncAuditTest(ManageRolesScopeTest):
    """F-02 — legacy assign/remove axını audit yazır (fixture miras alınır, testləri yox)."""

    test_dean_cannot_grant_roles_to_teacher_of_another_faculty = None
    test_exact_role_name_resolves_to_the_matching_org_role = None
    test_superadmin_assigning_exam_center_staff_creates_that_role_not_alumni = None

    def _role_logs(self, target):
        with bypass_rls():
            return list(
                AuditLog.objects.filter(resource_type="Membership", resource_id=str(target.pk)).order_by("created_at")
            )

    def test_assign_writes_audit_with_old_and_new_roles(self):
        client = self._client(self.superuser)
        client.post(
            reverse("accounts:manage_roles"),
            {
                "user_id": self.teacher_b.id,
                "action": "assign",
                "role_names": ["teacher", "exam_center_staff"],
                "reason": "audit F-02",
            },
            follow=True,
        )
        self.assertIn("exam_center_staff", self._roles_of(self.teacher_b))
        logs = self._role_logs(self.teacher_b)
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log.action, "update")
        self.assertEqual(log.user_id, self.superuser.id)
        self.assertEqual(log.organization_id, self.org.id)
        self.assertEqual(log.old_values, {"roles": ["teacher"]})
        self.assertEqual(log.new_values, {"roles": ["exam_center_staff", "teacher"]})
        self.assertEqual(log.changes["action"], "role_sync")
        self.assertEqual(log.changes["added"], ["exam_center_staff"])
        self.assertEqual(log.changes["removed"], [])
        self.assertEqual(log.reason, "audit F-02")
        self.assertTrue(log.ip_address)

    def test_remove_writes_audit_and_unchanged_resync_is_silent(self):
        client = self._client(self.superuser)
        client.post(
            reverse("accounts:manage_roles"),
            {"user_id": self.teacher_b.id, "action": "assign", "role_names": ["teacher", "exam_center_staff"]},
            follow=True,
        )
        # Eyni dəst yenidən → rol dəsti dəyişmir → ikinci qeyd YOXDUR.
        client.post(
            reverse("accounts:manage_roles"),
            {"user_id": self.teacher_b.id, "action": "assign", "role_names": ["teacher", "exam_center_staff"]},
            follow=True,
        )
        self.assertEqual(len(self._role_logs(self.teacher_b)), 1)
        # remove → member-ə düşür; silinən rollar izdə.
        client.post(
            reverse("accounts:manage_roles"),
            {"user_id": self.teacher_b.id, "action": "remove"},
            follow=True,
        )
        logs = self._role_logs(self.teacher_b)
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[-1].changes["action"], "role_sync")
        self.assertIn("exam_center_staff", logs[-1].changes["removed"])
        self.assertIn("teacher", logs[-1].changes["removed"])

    def test_denied_attempt_writes_nothing(self):
        client = self._client(self.dean_a)
        client.post(
            reverse("accounts:manage_roles"),
            {"user_id": self.teacher_b.id, "action": "assign", "role_names": ["teacher", "hr"]},
            follow=True,
        )
        self.assertEqual(self._role_logs(self.teacher_b), [])


class SuperadminOrganizationAuditTest(TestCase):
    """F-04 · F-01 · F-07 — superadmin təşkilat əməlləri."""

    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser("sao_super", "sao_super@example.com", "pw")
        cls.owner = User.objects.create_user("sao_owner", "sao_owner@example.com", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SAO University",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="pending",
                is_active=False,
            )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.superadmin)

    def _post(self, **data):
        payload = {"organization_id": str(self.org.pk)}
        payload.update(data)
        return self.client.post(reverse("accounts:superadmin_organizations"), payload)

    def _logs(self):
        with bypass_rls():
            return list(
                AuditLog.objects.filter(resource_type="Organization", resource_id=str(self.org.pk)).order_by(
                    "created_at"
                )
            )

    def test_non_uuid_organization_id_is_404_not_500(self):
        response = self._post(organization_id="abc", action="approve")
        self.assertEqual(response.status_code, 404)

    def test_approve_reject_suspend_unsuspend_are_audited(self):
        self.assertEqual(self._post(action="approve").status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, "active")
        log = self._logs()[-1]
        self.assertEqual(log.changes["action"], "approve")
        self.assertEqual(log.old_values["status"], "pending")
        self.assertEqual(log.new_values["status"], "active")
        self.assertEqual(log.user_id, self.superadmin.id)

        self.assertEqual(self._post(action="suspend", reason="audit F-04").status_code, 302)
        log = self._logs()[-1]
        self.assertEqual(log.changes["action"], "suspend")
        self.assertEqual(log.old_values["status"], "active")
        self.assertEqual(log.new_values["status"], "suspended")
        self.assertEqual(log.reason, "audit F-04")

        self.assertEqual(self._post(action="unsuspend").status_code, 302)
        log = self._logs()[-1]
        self.assertEqual(log.changes["action"], "unsuspend")
        self.assertEqual(log.new_values["status"], "active")

        self.assertEqual(self._post(action="reject", reason="rədd").status_code, 302)
        log = self._logs()[-1]
        self.assertEqual(log.changes["action"], "reject")
        self.assertEqual(log.new_values["status"], "suspended")
        self.assertEqual(len(self._logs()), 4)

    def test_letter_bands_set_and_reset_are_audited(self):
        from apps.registrar.public import grading_scale

        default_text = grading_scale.bands_text(self.org)
        response = self._post(action="set_letter_bands", letter_bands="90:A:4.00, 80:B:3.00, 0:F:0.00")
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertTrue(grading_scale.is_custom(self.org))
        log = self._logs()[-1]
        self.assertEqual(log.changes["action"], "set_letter_bands")
        self.assertEqual(log.old_values["letter_bands"], default_text)
        self.assertEqual(log.new_values["letter_bands"], grading_scale.bands_text(self.org))
        self.assertNotEqual(log.old_values["letter_bands"], log.new_values["letter_bands"])

        self.assertEqual(self._post(action="reset_letter_bands").status_code, 302)
        self.org.refresh_from_db()
        self.assertFalse(grading_scale.is_custom(self.org))
        log = self._logs()[-1]
        self.assertEqual(log.changes["action"], "reset_letter_bands")
        self.assertEqual(log.new_values["letter_bands"], default_text)

    def test_invalid_letter_bands_write_nothing(self):
        response = self._post(action="set_letter_bands", letter_bands="garbage")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._logs(), [])

    def test_approve_is_atomic_with_its_audit_row(self):
        """F-07: audit yazısı sınarsa status dəyişikliyi də geri alınır."""
        with mock.patch("apps.accounts.views.superadmin.endpoints.log_action", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self._post(action="approve")
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, "pending")
        self.assertFalse(self.org.is_active)
        self.assertEqual(self._logs(), [])


class JsonFailureStatusTest(ScheduleEditorUIBase):
    """F-10 — «200 + ok:false» əvəzinə düzgün status."""

    def test_schedule_editor_check_validation_error_is_400_with_message(self):
        response = self._act(self.coordinator, self._cell(action="check", weekday="", time_slot=""))
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("weekday", payload["errors"])
        # `schedule_editor.js` reject-də `body.message` göstərir — ilk sahə xətası oradadır.
        self.assertEqual(payload["message"], payload["errors"]["weekday"])
        self.assertEqual(payload["conflicts"], [])

    def test_people_analytics_ai_without_access_is_403(self):
        client = self._client(self.student)
        response = client.get(reverse("accounts:people_analytics_ai", args=["students"]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"ok": False, "error": "no_access"})

    def test_people_analytics_ai_generation_failure_is_502(self):
        client = self._client(self.owner)
        with mock.patch(
            "apps.accounts.views.people.analytics.people.generate_analytics_summary", side_effect=RuntimeError("ai")
        ):
            response = client.get(reverse("accounts:people_analytics_ai", args=["students"]))
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "generation_failed")

    def test_statistics_ai_summary_without_data_is_404(self):
        from apps.accounts.views.profile._sections.statistics import _ai_summary_response

        request = RequestFactory().get("/", {"stat_ai_summary": "1"})
        request.user = self.student
        response = _ai_summary_response(request, profile="student", presented={"has_data": False})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(json.loads(response.content)["ok"])


class StatisticsGpaLabelTest(TestCase):
    """F-05 — 4.0 şkalalı kart 100 ballıq «ÜOMG» adı ilə göstərilmir."""

    def test_gpa_tile_is_labelled_as_4_point_scale(self):
        user = User.objects.create_user("gpa_label_student", "gpa_label@example.com", "pw")
        metrics = student_metrics(user, organization=None)
        metrics["academic"]["gpa"] = 3.5
        metrics["academic"]["graded"] = 2
        metrics["academic"]["has_record"] = True
        presented = present_student(metrics)
        gpa_tile = next(tile for tile in presented["kpis"] if tile["key"] == "gpa")
        self.assertEqual(gpa_tile["label"], "Orta GPA (4.0)")
        self.assertNotIn("ÜOMG", gpa_tile["label"])
        self.assertTrue(gpa_tile["note"].startswith("4.0 şkalası"))
        self.assertIn(gpa_tile["value"], ("3.50", "3,50"))


class LabReviewAtomicTest(TestCase):
    """F-07 — ``pending_review_detail`` lab budağı: yekun bal rədd olunanda sual balları da yazılmır."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import ProfileRole
        from apps.courses.models import Course, CourseMembership
        from apps.labs.models import Lab, LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission
        from apps.labs.tests.test_views import _assign_user_to_org, _login_with_org

        self.teacher = User.objects.create_user("f07_lab_teacher", "f07_lab_t@example.com", "pw")
        self.student = User.objects.create_user("f07_lab_student", "f07_lab_s@example.com", "pw")
        self.organization = Organization.objects.create(
            name="F07 Lab Org", org_type=OrganizationType.SCHOOL, owner=self.teacher, status="active", is_active=True
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)
        course = Course.objects.create(owner=self.teacher, title="F07 Course", status="published")
        CourseMembership.objects.create(course=course, user=self.student, role="student", group_name="A1")
        lab = Lab.objects.create(
            course=course,
            title="F07 Lab",
            description="x",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            created_by=self.teacher,
        )
        assignment = LabAssignment.objects.create(lab=lab, student=self.student)
        self.submission = LabSubmission.objects.create(assignment=assignment, status="submitted", attempt_number=1)
        block = LabBlock.objects.create(lab=lab, title="B", order=1)
        question = LabQuestion.objects.create(block=block, question_text="Q", question_number=1, points=100)
        self.answer = LabAnswer.objects.create(
            lab=lab,
            question=question,
            student=self.student,
            submission=self.submission,
            attempt_number=1,
            answer="cavab",
            is_draft=False,
        )
        _login_with_org(self.client, self.teacher, self.organization)
        self.url = reverse("accounts:pending_review_detail", kwargs={"item_type": "lab", "item_id": self.submission.id})

    def test_out_of_range_total_rolls_back_answer_scores(self):
        response = self.client.post(self.url, {f"answer_score_{self.answer.id}": "50", "score": "999", "feedback": ""})
        self.assertEqual(response.status_code, 302)
        self.answer.refresh_from_db()
        self.submission.refresh_from_db()
        self.assertIsNone(self.answer.score)  # əvvəl 50 yazılmış qalırdı
        self.assertEqual(self.submission.status, "submitted")

    def test_malformed_total_rolls_back_answer_scores(self):
        response = self.client.post(self.url, {f"answer_score_{self.answer.id}": "50", "score": "abc", "feedback": ""})
        self.assertEqual(response.status_code, 302)
        self.answer.refresh_from_db()
        self.assertIsNone(self.answer.score)

    def test_valid_total_still_saves_everything(self):
        response = self.client.post(self.url, {f"answer_score_{self.answer.id}": "50", "score": "50", "feedback": "ok"})
        self.assertEqual(response.status_code, 302)
        self.answer.refresh_from_db()
        self.submission.refresh_from_db()
        self.assertEqual(float(self.answer.score), 50.0)
        self.assertEqual(self.submission.status, "graded")
        self.assertEqual(float(self.submission.score), 50.0)
