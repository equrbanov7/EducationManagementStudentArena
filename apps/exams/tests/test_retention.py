"""Academic attempt retention and destructive-action regression tests."""

from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.models import Exam, ExamAttempt, ExamGradeEvent, ExamQuestion
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class ExamRetentionTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("retention_teacher", password="pw")
        self.student = User.objects.create_user("retention_student", password="pw")
        self.org = Organization.objects.create(
            name="Retention org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT)
        self.exam = Exam.objects.create(
            title="Retention exam",
            author=self.teacher,
            organization=self.org,
            exam_type="written",
            is_active=False,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, text="Q", order=1, points=10)
        _login_with_org(self.client, self.teacher, self.org)

    def _attempt(self, *, trial=False, status="submitted"):
        # (user, exam, attempt_number) unikaldır — hər cəhdə fərqli nömrə ver
        # ki, eyni testdə bir neçə cəhd yaradanda toqquşma olmasın.
        next_number = ExamAttempt.objects.filter(user=self.student, exam=self.exam).count() + 1
        return ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status=status,
            is_trial=trial,
            attempt_number=next_number,
        )

    def _delete_attempts(self, *attempts):
        return self.client.post(
            reverse("exams:delete_exam_attempts", args=[self.exam.slug]),
            {
                "attempt_ids": [str(attempt.pk) for attempt in attempts],
                "next": reverse("exams:teacher_exam_results", args=[self.exam.slug]),
            },
        )

    def test_submitted_academic_attempt_cannot_be_bulk_deleted(self):
        attempt = self._attempt()

        response = self._delete_attempts(attempt)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ExamAttempt.objects.filter(pk=attempt.pk).exists())

    def test_disposable_trial_attempt_can_be_deleted_and_is_audited(self):
        attempt = self._attempt(trial=True)

        response = self._delete_attempts(attempt)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExamAttempt.objects.filter(pk=attempt.pk).exists())
        self.assertTrue(
            AuditLog.objects.filter(
                reason="trial_exam_attempts_permanently_deleted",
                organization=self.org,
                user=self.teacher,
            ).exists()
        )

    def test_mixed_bulk_delete_preserves_academic_attempt(self):
        academic = self._attempt()
        trial = self._attempt(trial=True)

        self._delete_attempts(academic, trial)

        self.assertTrue(ExamAttempt.objects.filter(pk=academic.pk).exists())
        self.assertFalse(ExamAttempt.objects.filter(pk=trial.pk).exists())

    def test_graded_trial_is_also_retention_protected(self):
        attempt = self._attempt(trial=True)
        ExamGradeEvent.objects.create(
            attempt=attempt,
            question=self.question,
            grader=self.teacher,
            old_score=None,
            new_score=7,
            max_points=10,
        )

        self._delete_attempts(attempt)

        self.assertTrue(ExamAttempt.objects.filter(pk=attempt.pk).exists())

    def test_exam_orm_delete_is_protected_when_attempt_exists(self):
        attempt = self._attempt()

        with self.assertRaises(ProtectedError):
            self.exam.delete()

        self.assertTrue(Exam.objects.filter(pk=self.exam.pk).exists())
        self.assertTrue(ExamAttempt.objects.filter(pk=attempt.pk).exists())

    def test_permanent_delete_view_preserves_exam_with_attempt_history(self):
        attempt = self._attempt()
        self.exam.is_deleted = True
        self.exam.deleted_at = self.exam.created_at
        self.exam.save(update_fields=["is_deleted", "deleted_at"])

        response = self.client.post(reverse("exams:permanent_delete_exam", args=[self.exam.slug]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Exam.objects.filter(pk=self.exam.pk).exists())
        self.assertTrue(ExamAttempt.objects.filter(pk=attempt.pk).exists())

    def test_permanent_delete_view_removes_empty_soft_deleted_exam(self):
        self.exam.is_deleted = True
        self.exam.deleted_at = self.exam.created_at
        self.exam.save(update_fields=["is_deleted", "deleted_at"])

        response = self.client.post(reverse("exams:permanent_delete_exam", args=[self.exam.slug]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Exam.objects.filter(pk=self.exam.pk).exists())
        self.assertTrue(AuditLog.objects.filter(reason="empty_exam_permanently_deleted").exists())
