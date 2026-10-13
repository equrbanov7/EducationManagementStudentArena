"""2026-10-13 (gecə) — cəhd + apellyasiya tarixçəsi koordinator/dekan üçün (sahibin 2026-09-07 memo-su).

* ``student_exam_history`` final VƏ midterm cəhdlərini, apellyasiya qərarlarını və açar düzəlişini
  qaytarır; rəsmi = qrupda sonuncu cəhd, əvvəlkilər «ləğv olundu»;
* «Akademik qeydlər» çekməcəsinin JSON-u (dekan scope-u) bu izi daşıyır; scope xaricindəki
  tələbə üçün heç nə qaytarılmır.
"""

from __future__ import annotations

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.test_academic_records import _RecordsBase
from apps.appeals.constants import APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.models import Appeal, AppealItem
from apps.appeals.services import accept_appeal_item
from apps.appeals.services.history import student_exam_history
from apps.appeals.tests.test_key_correction_2026_10_13 import _KeyFixSetup
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion
from core.rls import bypass_rls


class StudentExamHistoryTests(_KeyFixSetup):
    def test_history_contains_attempts_appeals_and_key_corrections(self):
        self._apply()
        with self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(self.item, reviewer=self.head, response_text="Haqlıdır.")
        midterm = self._exam(exam_type="written", category="midterm", title="KF Midterm")
        question = ExamQuestion.objects.create(exam=midterm, order=1, text="M1", points=10)
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=midterm,
            status="submitted",
            finished_at=timezone.now(),
            checked_by_teacher=True,
            teacher_checked_at=timezone.now(),
            teacher_score=5,
        )
        ExamAnswer.objects.create(
            attempt=attempt, question=question, teacher_score=5, question_snapshot={"v": 2, "points": 10}
        )

        rows = student_exam_history(student=self.student, organization=self.org)
        by_category = {row["category"]: row for row in rows}
        self.assertEqual(set(by_category), {"final", "midterm"})
        self.assertEqual(by_category["midterm"]["percent"], 50.0)
        final = by_category["final"]
        self.assertTrue(final["is_official"])
        labels = [appeal["status_label"] for appeal in final["appeals"]]
        self.assertIn("Qəbul edildi", labels)
        self.assertTrue(any("Cavab açarı düzəldildi" in label for label in labels), labels)

    def test_retake_marks_previous_attempt_superseded(self):
        retake = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress", attempt_number=2)
        for question in (self.q1, self.q2):
            ExamAnswer.objects.create(attempt=retake, question=question)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            retake.mark_finished(status="submitted")
        rows = [row for row in student_exam_history(student=self.student, organization=self.org)]
        self.assertEqual([row["is_official"] for row in rows], [False, True])
        self.assertEqual([row["number"] for row in rows], [1, 2])


@override_settings(UNIVERSITY_MODE=True)
class AcademicRecordsDrawerHistoryTests(_RecordsBase):
    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_dean_drawer_includes_exam_and_appeal_history(self):
        student = self.students_a[0]
        with bypass_rls():
            exam = Exam.objects.create(
                title="ACR Final",
                author=self.owner,
                organization=self.org,
                subject=self.subject,
                exam_type="written",
                exam_type_extended="final",
                is_active=True,
            )
            question = ExamQuestion.objects.create(exam=exam, order=1, text="Q", points=10)
            attempt = ExamAttempt.objects.create(
                user=student,
                exam=exam,
                status="submitted",
                finished_at=timezone.now(),
                checked_by_teacher=True,
                teacher_checked_at=timezone.now(),
                teacher_score=4,
            )
            answer = ExamAnswer.objects.create(
                attempt=attempt, question=question, teacher_score=4, question_snapshot={"v": 2, "points": 10}
            )
            appeal = Appeal.objects.create(attempt=attempt, exam=exam, student=student, organization=self.org)
            AppealItem.objects.create(
                appeal=appeal,
                question=question,
                answer=answer,
                appeal_type=APPEAL_TYPE_WRONG_ANSWER_KEY,
                comment="x" * 30,
            )

        response = self._client(self.dean).get(reverse("accounts:records_student_detail"), {"student": str(student.id)})
        self.assertEqual(response.status_code, 200)
        history = response.json()["exam_history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["percent"], 40.0)
        self.assertEqual(history[0]["appeals"][0]["status_label"], "Gözləyir")

        outside = self._client(self.dean).get(
            reverse("accounts:records_student_detail"), {"student": str(self.students_b[0].id)}
        )
        self.assertFalse(outside.json()["has_access"])
        self.assertNotIn("exam_history", outside.json())
