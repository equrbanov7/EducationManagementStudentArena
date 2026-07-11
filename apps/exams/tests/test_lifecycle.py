"""Seq3 (EXAM-P1-01) — atomik publish/unpublish keçidləri + publish qapısı.

Product qaydası: sualsız imtahan canlıya çıxa bilməz; keçidlər şərti-UPDATE
ilə atomikdir (paralel tab double-flip edə bilməz); publish/unpublish audit
loglanır. Köhnə (parametrsiz) formalar üçün flip davranışı geriyə-uyğundur.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion
from apps.exams.services.lifecycle import (
    exam_publish_gate_error,
    publish_exam,
    set_results_hidden,
    unpublish_exam,
)
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LifecycleServiceTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("lc_teacher", "lc_teacher@example.com", "pw")
        self.org = Organization.objects.create(
            name="LC Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )

    def _exam(self, *, is_active=False, with_question=True):
        exam = Exam.objects.create(
            title="LC Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=is_active,
        )
        if with_question:
            ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=1, is_active=True)
        return exam

    def test_publish_gate_blocks_exam_without_questions(self):
        exam = self._exam(with_question=False)
        self.assertNotEqual(exam_publish_gate_error(exam), "")
        changed, error = publish_exam(exam, by_user=self.teacher)
        self.assertFalse(changed)
        self.assertNotEqual(error, "")
        exam.refresh_from_db()
        self.assertFalse(exam.is_active)

    def test_publish_gate_blocks_inactive_only_questions(self):
        exam = self._exam(with_question=False)
        ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=1, is_active=False)
        self.assertNotEqual(exam_publish_gate_error(exam), "")

    def test_publish_gate_blocks_deleted_exam(self):
        exam = self._exam()
        exam.is_deleted = True
        exam.save(update_fields=["is_deleted"])
        changed, error = publish_exam(exam, by_user=self.teacher)
        self.assertFalse(changed)
        self.assertNotEqual(error, "")
        exam.refresh_from_db()
        self.assertFalse(exam.is_active)

    def test_publish_succeeds_and_is_idempotent(self):
        exam = self._exam()
        changed, error = publish_exam(exam, by_user=self.teacher)
        self.assertTrue(changed)
        self.assertEqual(error, "")
        self.assertTrue(exam.is_active)
        # Yarış/double-POST: ikinci publish no-op (changed=False, error yox).
        changed_again, error_again = publish_exam(exam, by_user=self.teacher)
        self.assertFalse(changed_again)
        self.assertEqual(error_again, "")
        self.assertTrue(exam.is_active)

    def test_unpublish_is_atomic_and_idempotent(self):
        exam = self._exam(is_active=True)
        self.assertTrue(unpublish_exam(exam, by_user=self.teacher))
        self.assertFalse(exam.is_active)
        self.assertFalse(unpublish_exam(exam, by_user=self.teacher))
        self.assertFalse(exam.is_active)

    def test_set_results_hidden_conditional(self):
        exam = self._exam()
        self.assertTrue(set_results_hidden(exam, True, by_user=self.teacher))
        self.assertTrue(exam.results_hidden_from_students)
        # Artıq gizlidir — eyni keçid no-op.
        self.assertFalse(set_results_hidden(exam, True, by_user=self.teacher))
        self.assertTrue(set_results_hidden(exam, False, by_user=self.teacher))
        self.assertFalse(exam.results_hidden_from_students)

    def test_publish_writes_audit_log(self):
        from apps.audit.models import AuditLog

        exam = self._exam()
        publish_exam(exam, by_user=self.teacher)
        self.assertTrue(AuditLog.objects.filter(reason="exam_published").exists())
        unpublish_exam(exam, by_user=self.teacher)
        self.assertTrue(AuditLog.objects.filter(reason="exam_unpublished").exists())


class ToggleExamActiveViewTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("lcv_teacher", "lcv_teacher@example.com", "pw")
        self.org = Organization.objects.create(
            name="LCV Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER)
        _login_with_org(self.client, self.teacher, self.org)

    def _exam(self, *, is_active=False, with_question=True):
        exam = Exam.objects.create(
            title="LCV Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=is_active,
        )
        if with_question:
            ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=1, is_active=True)
        return exam

    def _toggle(self, exam, **data):
        return self.client.post(reverse("exams:toggle_exam_active", args=[exam.slug]), data)

    def test_publish_via_view_with_desired_state(self):
        exam = self._exam()
        response = self._toggle(exam, desired_state="1")
        self.assertEqual(response.status_code, 302)
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)

    def test_empty_exam_stays_draft_with_error_message(self):
        exam = self._exam(with_question=False)
        response = self._toggle(exam, desired_state="1", follow=False)
        self.assertEqual(response.status_code, 302)
        exam.refresh_from_db()
        self.assertFalse(exam.is_active)

    def test_stale_tab_does_not_double_flip(self):
        # İki tab da "dərc et" görür; biri basır (dərc olunur), ikincisi basanda
        # köhnə niyyət (desired_state=1) təkrar gəlir — imtahan deaktiv OLMUR.
        exam = self._exam()
        self._toggle(exam, desired_state="1")
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)
        self._toggle(exam, desired_state="1")
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)

    def test_legacy_form_without_param_still_flips(self):
        exam = self._exam()
        self._toggle(exam)
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)
        self._toggle(exam)
        exam.refresh_from_db()
        self.assertFalse(exam.is_active)

    def test_deactivate_via_view(self):
        exam = self._exam(is_active=True)
        self._toggle(exam, desired_state="0")
        exam.refresh_from_db()
        self.assertFalse(exam.is_active)
