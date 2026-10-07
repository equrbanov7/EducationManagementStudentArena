"""Təhlükəsizlik auditi 2026-10-07 — «Statistika» bölməsi gizli imtahan nəticəsini göstərirdi.

Tələbənin öz statistikasında («son imtahan nəticələri», orta bal, keçid) müəllimin
``results_hidden_from_students`` ilə gizlətdiyi imtahanın faiz balı və müəllimin 5 dəqiqəlik
redaktə pəncərəsi (``REVIEW_EDIT_LOCK_WINDOW``) hələ bağlanmamış yazılı qiymət görünürdü —
«Nəticələrim» və nəticə səhifəsi isə hər ikisini gizlədir. CSV ixracının köhnə qurucusu
(``get_student_statistics``) da eyni qaydanı pozurdu.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.services.statistics_metrics import student_metrics
from apps.accounts.services.statistics_selectors import get_student_statistics
from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class StudentStatisticsResultVisibilityTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("sv_teacher", "sv_t@example.com", "pw")
        self.student = User.objects.create_user("sv_student", "sv_s@example.com", "pw")
        self.org = Organization.objects.create(
            name="SV Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )

    def _attempt(self, title, *, exam_type="test", hidden=False, **fields):
        exam = Exam.objects.create(
            title=title,
            author=self.teacher,
            organization=self.org,
            exam_type=exam_type,
            is_active=True,
            results_hidden_from_students=hidden,
        )
        return ExamAttempt.objects.create(
            user=self.student,
            exam=exam,
            status="submitted",
            started_at=timezone.now() - timedelta(hours=1),
            finished_at=timezone.now() - timedelta(minutes=30),
            **fields,
        )

    def test_hidden_and_unreleased_scores_are_not_in_student_metrics(self):
        self._attempt("Visible quiz", correct_count=1, wrong_count=1)  # 50 %
        self._attempt("Hidden quiz", hidden=True, correct_count=4, wrong_count=0)  # 100 %
        self._attempt(
            "Fresh written",
            exam_type="written",
            checked_by_teacher=True,
            teacher_checked_at=timezone.now() - timedelta(minutes=1),
            teacher_score=95,
        )

        metrics = student_metrics(self.student, organization=self.org)

        rows = {row["title"]: row["score_pct"] for row in metrics["recent_attempts"]}
        self.assertEqual(rows.get("Visible quiz"), 50.0)
        self.assertNotIn("Hidden quiz", rows)
        self.assertIsNone(rows.get("Fresh written"))
        self.assertEqual(metrics["exams"]["avg_score"], 50.0)

    def test_released_written_grade_is_shown(self):
        self._attempt(
            "Old written",
            exam_type="written",
            checked_by_teacher=True,
            teacher_checked_at=timezone.now() - timedelta(hours=1),
            teacher_score=80,
        )
        rows = {
            row["title"]: row["score_pct"]
            for row in student_metrics(self.student, organization=self.org)["recent_attempts"]
        }
        self.assertEqual(rows.get("Old written"), 80.0)

    def test_csv_summary_ignores_hidden_and_unreleased_scores(self):
        self._attempt("Visible quiz", correct_count=1, wrong_count=1)
        self._attempt("Hidden quiz", hidden=True, correct_count=4, wrong_count=0)
        self._attempt(
            "Fresh written",
            exam_type="written",
            checked_by_teacher=True,
            teacher_checked_at=timezone.now() - timedelta(minutes=1),
            teacher_score=95,
        )
        stats = get_student_statistics(self.student, organization=self.org)
        self.assertEqual(stats["score_breakdown"]["exam_avg"], 50.0)
        titles = [row.get("exam__title") for row in stats["recent_activity"]]
        self.assertNotIn("Hidden quiz", titles)
        self.assertNotIn("Fresh written", titles)
