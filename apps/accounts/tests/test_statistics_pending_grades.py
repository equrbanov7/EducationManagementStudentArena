"""Unmarked papers must not reduce pass rates or display a failing grade."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.services.statistics_metrics._shared import attempt_outcome, score_pct_expression
from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Organization


class PendingGradesTest(TestCase):
    def test_pending_written_attempt_is_excluded_from_result_denominator(self):
        user = get_user_model().objects.create_user("CODEX_TEST_metrics", password="pw")
        org = Organization.objects.create(name="CODEX_TEST_metrics", slug="codex-test-metrics", owner=user)
        exam = Exam.objects.create(title="CODEX_TEST_written", author=user, organization=org, exam_type="written")
        ExamAttempt.objects.create(user=user, exam=exam, status="submitted", checked_by_teacher=False)
        ExamAttempt.objects.create(
            user=user, exam=exam, status="submitted", attempt_number=2, checked_by_teacher=True, teacher_score=80
        )
        attempts = ExamAttempt.objects.filter(exam=exam)
        outcome = attempt_outcome(attempts)
        self.assertEqual(outcome["finished"], 2)
        self.assertEqual(outcome["grading_queue"], 1)
        self.assertEqual(outcome["avg_score"], 80)
        self.assertEqual(outcome["pass_rate"], 100)
        self.assertIsNone(
            attempts.filter(checked_by_teacher=False)
            .annotate(score_pct=score_pct_expression())
            .values_list("score_pct", flat=True)
            .get()
        )

    def test_room_capacity_is_not_multiplied_by_computer_join(self):
        from apps.accounts.services.statistics_metrics._shared import Window
        from apps.accounts.services.statistics_metrics.exam_center import exam_center_metrics
        from apps.exams.models import ExamRoom, ExamRoomComputer

        user = get_user_model().objects.create_user("CODEX_TEST_rooms", password="pw")
        org = Organization.objects.create(name="CODEX_TEST_rooms", slug="codex-test-rooms", owner=user)
        rooms = [
            ExamRoom.objects.create(organization=org, name=f"Room {i}", code=f"R{i}", capacity=10) for i in range(2)
        ]
        for i, room in enumerate([rooms[0], rooms[0], rooms[1]]):
            ExamRoomComputer.objects.create(
                organization=org, room=room, label=f"PC{i}", mac_address=f"02:00:00:00:00:{i:02d}", seat_number=i + 1
            )
        metrics = exam_center_metrics(organization=org, window=Window(None, None))
        self.assertEqual(metrics["rooms"]["rooms"], 2)
        self.assertEqual(metrics["rooms"]["capacity"], 20)
        self.assertEqual(metrics["rooms"]["computers"], 3)

    def test_serialized_period_dates_are_visible_in_statistics(self):
        from django.template.loader import render_to_string

        html = render_to_string(
            "accounts/profile/sections/_statistics.html",
            {
                "statistics_data": {
                    "profile": "teacher",
                    "has_data": False,
                    "show_filters": False,
                    "window": {
                        "source": "period",
                        "period_name": "CODEX_TEST_period",
                        "date_from": "2024-09-01",
                        "date_to": "2025-01-31",
                    },
                },
            },
        )
        self.assertIn("2024-09-01", html)
        self.assertIn("2025-01-31", html)
