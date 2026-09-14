"""2026-09-13 təhlükəsizlik auditi, F-11 (P3) — imtahan cavab balı ``AuditLog``-a da düşür.

Əvvəl bal dəyişikliyi yalnız ``ExamGradeEvent`` ledger-inə yazılırdı (audit
ekranında görünmürdü). İndi hər üç servis yolu (tək cavab, cəhd-səviyyə, toplu)
``ExamGradeEvent``-i SAXLAYIR və eyni dəyişikliyi cəhd üzrə tək ``update``
qeydi kimi ``AuditLog``-a əlavə edir; dəyişiklik olmayan (no-op) çağırış
audit qeydi yaratmır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamGradeEvent, ExamQuestion
from apps.exams.services.manual_grading import (
    apply_attempt_grade,
    apply_manual_grading,
    apply_single_answer_grade,
)
from apps.organizations.models import Organization
from core.constants import AuditAction, OrganizationType
from core.rls import bypass_rls


class ManualGradingAuditLogTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.teacher = user_model.objects.create_user("mg_teacher", password="pw")
        self.student = user_model.objects.create_user("mg_student", password="pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="MG organization",
                org_type=OrganizationType.SCHOOL,
                owner=self.teacher,
                status="active",
                is_active=True,
            )
            self.exam = Exam.objects.create(
                organization=self.org, author=self.teacher, title="MG exam", exam_type="written"
            )
            self.q1 = ExamQuestion.objects.create(exam=self.exam, text="Q1", order=1, points=10)
            self.q2 = ExamQuestion.objects.create(exam=self.exam, text="Q2", order=2, points=5)
            self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted")
            self.a1 = ExamAnswer.objects.create(attempt=self.attempt, question=self.q1, text_answer="c1")
            self.a2 = ExamAnswer.objects.create(attempt=self.attempt, question=self.q2, text_answer="c2")

    def _audit_rows(self):
        return list(
            AuditLog.objects.filter(
                action=AuditAction.UPDATE, resource_type="ExamAttempt", object_id=str(self.attempt.pk)
            ).order_by("created_at")
        )

    def test_single_answer_grade_writes_audit_row(self):
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_single_answer_grade(answer_id=self.a1.id, score=7, grader=self.teacher)
        rows = self._audit_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.user_id, self.teacher.id)
        self.assertEqual(row.organization_id, self.org.id)
        self.assertEqual(row.reason, "exam_answer_score_change")
        self.assertEqual(row.changes, {str(self.q1.id): {"old": None, "new": 7, "max": 10}})
        self.assertEqual(ExamGradeEvent.objects.filter(attempt=self.attempt).count(), 1)

    def test_noop_regrade_writes_nothing(self):
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_single_answer_grade(answer_id=self.a1.id, score=7, grader=self.teacher)
            apply_single_answer_grade(answer_id=self.a1.id, score=7, grader=self.teacher)
        self.assertEqual(len(self._audit_rows()), 1)

    def test_bulk_grading_writes_one_audit_row_with_every_question(self):
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_manual_grading(
                attempt_id=self.attempt.id,
                grader=self.teacher,
                payload={f"score_{self.q1.id}": "9", f"score_{self.q2.id}": "3"},
            )
        rows = self._audit_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0].changes,
            {
                str(self.q1.id): {"old": None, "new": 9, "max": 10},
                str(self.q2.id): {"old": None, "new": 3, "max": 5},
            },
        )
        self.assertEqual(ExamGradeEvent.objects.filter(attempt=self.attempt).count(), 2)

    def test_attempt_level_grade_writes_audit_row(self):
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_attempt_grade(
                attempt_id=self.attempt.id, score=55, feedback="ok", grader=self.teacher, max_points=100
            )
        rows = self._audit_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].changes, {"attempt": {"old": None, "new": 55, "max": 100}})
