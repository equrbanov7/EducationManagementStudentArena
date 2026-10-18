"""«İmtahan şansı ver» — rəsmi səbəb, «25% müraciəti» qapısı və 25% izi (sahib 2026-10-18)."""

from __future__ import annotations

from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, StudentExamAttemptGrant
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.registrar import exam_attempt_history, retake_decisions, retake_services
from apps.registrar.models import ExamChanceGrant, RetakeStatus
from apps.registrar.tests.retake_fixture import RetakeBase, User, pdf
from core.rls import bypass_rls


@override_settings(UNIVERSITY_MODE=True)
class ExamChanceRetakeReasonTest(RetakeBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.center = User.objects.create_user("rt_center", "rt_center@qku.edu.az", "pw")
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        now = timezone.now()
        cls.exam = Exam.objects.create(
            title="INF101 yekun",
            author=cls.center,
            organization=cls.org,
            subject=cls.subject,
            exam_type="written",
            exam_type_extended="final",
            is_active=True,
            is_public=False,
            max_attempts_per_user=1,
            total_duration_minutes=60,
            start_datetime=now - timedelta(hours=1),
            end_datetime=now + timedelta(hours=3),
        )
        cls.exam.allowed_users.add(cls.student, cls.other)

    def _post(self, **data):
        payload = {"exam_id": str(self.exam.pk), "extra_attempts": "1", **data}
        return self.client_for(self.center).post(reverse("accounts:exam_chance"), payload)

    def _admit(self):
        self.fail_exam()
        with bypass_rls():
            app = retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                receipt=pdf(),
            )
            retake_decisions.verify_payment(actor=self.accountant, organization=self.org, application_id=app.id)
            return retake_decisions.admit(actor=self.dean, organization=self.org, application_id=app.id)

    def test_retake_reason_requires_admitted_application(self):
        response = self._post(student_ids=[str(self.other.pk)], reason="retake_25")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(StudentExamAttemptGrant.objects.filter(exam=self.exam).exists())
        self.assertFalse(ExamChanceGrant.objects.exists())

    def test_retake_reason_grants_and_moves_application(self):
        app = self._admit()
        response = self._post(student_ids=[str(self.student.pk)], reason="retake_25")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(StudentExamAttemptGrant.objects.filter(exam=self.exam, student=self.student).exists())
        with bypass_rls():
            app.refresh_from_db()
            log = ExamChanceGrant.objects.get(student=self.student)
        self.assertEqual(app.status, RetakeStatus.EXAM_GRANTED)
        self.assertEqual((log.application_id, log.reason, log.exam_type), (app.id, "retake_25", "written"))

    def test_university_concession_needs_order(self):
        self._post(student_ids=[str(self.other.pk)], reason="university", note="Rektorun güzəşti")
        self.assertFalse(ExamChanceGrant.objects.exists())
        self._post(
            student_ids=[str(self.other.pk)],
            reason="university",
            note="Rektorun güzəşti",
            reference_number="45/Ə",
            reference_date="2026-10-15",
        )
        log = ExamChanceGrant.objects.get(student=self.other)
        self.assertEqual((log.reference_number, str(log.reference_date)), ("45/Ə", "2026-10-15"))

    def test_section_lists_application_and_blocks_students_without_one(self):
        self._admit()
        page = (
            self.client_for(self.center)
            .get(f"{reverse('accounts:profile')}?section=exam-chance&chance_reason=retake_25&chance_student_q=rt_")
            .content.decode()
        )
        self.assertIn("25% · Proqramlaşdırma", page)
        self.assertIn("25% müraciəti yoxdur", page)
        self.assertIn(f'value="{self.student.pk}"', page)
        self.assertNotIn(f'name="student_ids" value="{self.other.pk}"', page)

    def test_attempt_after_grant_is_labelled_retake(self):
        from apps.exams.models import ExamAttempt

        self._admit()
        self._post(student_ids=[str(self.student.pk)], reason="retake_25")
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="submitted", started_at=timezone.now(), finished_at=timezone.now()
        )
        with bypass_rls():
            self.assertEqual(exam_attempt_history.retake_attempt_ids([attempt]), {attempt.id})
