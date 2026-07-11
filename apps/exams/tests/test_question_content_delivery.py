"""Strict vaxtlı suallar üçün server-side content delivery regresiyaları."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.question_snapshot import build_question_snapshot
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class StrictQuestionContentDeliveryTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("delivery_teacher", "delivery-teacher@example.com", "pw")
        self.student = User.objects.create_user("delivery_student", "delivery-student@example.com", "pw")
        self.org = Organization.objects.create(
            name="Delivery Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT)
        self.exam = Exam.objects.create(
            title="Delivery Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            is_public=True,
        )
        _login_with_org(self.client, self.student, self.org)

    def _question(self, *, order=1, time_limit=60, option_count=2):
        question = ExamQuestion.objects.create(
            exam=self.exam,
            order=order,
            text=f"STRICT_QUESTION_{order}_SENTINEL",
            correct_answer=f"NEVER_EXPOSE_CORRECT_{order}_SENTINEL",
            points=1,
            is_active=True,
            answer_mode="single",
            time_limit_seconds=time_limit,
            image=f"exam_questions/private-question-{order}.png",
            video=f"exam_questions/private-question-{order}.mp4",
        )
        for index in range(option_count):
            ExamQuestionOption.objects.create(
                question=question,
                text=f"STRICT_OPTION_{order}_{index}_SENTINEL",
                image=f"exam_options/private-option-{order}-{index}.png",
                is_correct=index == 0,
            )
        return question

    def _attempt(self, *questions, legacy=False):
        attempt_number = ExamAttempt.objects.filter(user=self.student, exam=self.exam).count() + 1
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="in_progress",
            attempt_number=attempt_number,
        )
        if legacy:
            attempt.question_timing = {}
            attempt.save(update_fields=["question_timing"])
        for question in questions:
            options = list(question.options.all())
            ExamAnswer.objects.create(
                attempt=attempt,
                question=question,
                question_snapshot=build_question_snapshot(question, options),
            )
        return attempt

    def _take_url(self, attempt):
        return reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})

    def _delivery_url(self, attempt):
        return reverse("exams:question_seen", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})

    def test_initial_get_hides_strict_timed_question_option_media_and_saved_answer(self):
        question = self._question()
        attempt = self._attempt(question)
        answer = attempt.answers.get(question=question)
        selected = question.options.order_by("id").first()
        answer.selected_options.add(selected)
        answer.selected_option_ids_snapshot = [selected.id]
        answer.save(update_fields=["selected_option_ids_snapshot"])

        response = self.client.get(self._take_url(attempt))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-server-delivery="1"', html)
        self.assertIn(f'data-question-id="{question.id}"', html)
        self.assertNotIn(question.text, html)
        self.assertNotIn("STRICT_OPTION_1_0_SENTINEL", html)
        self.assertNotIn("private-question-1.png", html)
        self.assertNotIn("private-question-1.mp4", html)
        self.assertNotIn("private-option-1-0.png", html)
        self.assertNotIn(f'name="q_present_{question.id}"', html)
        self.assertNotIn(f'value="{selected.id}"', html)

    def test_delivery_starts_timer_returns_only_safe_snapshot_html_and_keeps_first_start(self):
        question = self._question()
        attempt = self._attempt(question)
        answer = attempt.answers.get(question=question)
        selected = question.options.order_by("id").first()
        answer.selected_options.add(selected)
        answer.selected_option_ids_snapshot = [selected.id]
        answer.save(update_fields=["selected_option_ids_snapshot"])
        # Çatdırılan snapshot canlı müəllif redaktəsindən təsirlənməməlidir.
        question.text = "LIVE_MUTATION_MUST_NOT_REACH_STUDENT"
        question.correct_answer = "LIVE_CORRECT_ANSWER_MUST_NOT_LEAK"
        question.save(update_fields=["text", "correct_answer"])

        first = self.client.post(self._delivery_url(attempt), {"question_id": question.id})

        self.assertEqual(first.status_code, 200)
        payload = first.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["limit_seconds"], 60)
        self.assertLessEqual(payload["remaining_seconds"], 60)
        delivered_html = payload["html"]
        self.assertIn("STRICT_QUESTION_1_SENTINEL", delivered_html)
        self.assertIn("STRICT_OPTION_1_0_SENTINEL", delivered_html)
        self.assertIn("private-question-1.png", delivered_html)
        self.assertIn("private-question-1.mp4", delivered_html)
        self.assertIn("private-option-1-0.png", delivered_html)
        self.assertIn(f'name="q_present_{question.id}"', delivered_html)
        self.assertIn("checked", delivered_html)
        self.assertNotIn("LIVE_MUTATION_MUST_NOT_REACH_STUDENT", delivered_html)
        self.assertNotIn("NEVER_EXPOSE_CORRECT_1_SENTINEL", delivered_html)
        self.assertNotIn("LIVE_CORRECT_ANSWER_MUST_NOT_LEAK", delivered_html)
        self.assertNotIn("is_correct", delivered_html)

        attempt.refresh_from_db()
        first_started_at = attempt.question_timing[str(question.id)]
        repeat = self.client.post(self._delivery_url(attempt), {"question_id": question.id})
        self.assertEqual(repeat.status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.question_timing[str(question.id)], first_started_at)

    def test_expired_delivery_returns_zero_without_resetting_start(self):
        question = self._question(time_limit=30)
        attempt = self._attempt(question)
        started_at = (timezone.now() - timedelta(minutes=5)).isoformat()
        attempt.question_timing[str(question.id)] = started_at
        attempt.save(update_fields=["question_timing"])

        response = self.client.post(self._delivery_url(attempt), {"question_id": question.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["remaining_seconds"], 0)
        attempt.refresh_from_db()
        self.assertEqual(attempt.question_timing[str(question.id)], started_at)

    def test_untimed_and_legacy_timed_attempts_keep_full_initial_render(self):
        untimed = self._question(order=1, time_limit=None)
        untimed_attempt = self._attempt(untimed)
        untimed_response = self.client.get(self._take_url(untimed_attempt))
        self.assertContains(untimed_response, untimed.text)
        self.assertContains(untimed_response, "STRICT_OPTION_1_0_SENTINEL")

        untimed_attempt.status = "submitted"
        untimed_attempt.finished_at = timezone.now()
        untimed_attempt.save(update_fields=["status", "finished_at"])
        timed = self._question(order=2, time_limit=60)
        legacy_attempt = self._attempt(timed, legacy=True)
        legacy_response = self.client.get(self._take_url(legacy_attempt))
        self.assertContains(legacy_response, timed.text)
        self.assertContains(legacy_response, "STRICT_OPTION_2_0_SENTINEL")
        self.assertNotContains(legacy_response, 'data-server-delivery="1"')

    def test_delivery_query_count_does_not_grow_with_option_count(self):
        warmup = self._question(order=1, option_count=2)
        small = self._question(order=2, option_count=2)
        large = self._question(order=3, option_count=22)
        attempt = self._attempt(warmup, small, large)

        # İlk sorğu session/auth/content-type keşini qızdırır — ölçmədən əvvəl
        # onu ayrıca warm-up sualı ilə isit ki, ölçmə soyuq-keş küyü verməsin.
        self.client.post(self._delivery_url(attempt), {"question_id": warmup.id})

        with CaptureQueriesContext(connection) as small_queries:
            small_response = self.client.post(self._delivery_url(attempt), {"question_id": small.id})
        with CaptureQueriesContext(connection) as large_queries:
            large_response = self.client.post(self._delivery_url(attempt), {"question_id": large.id})

        self.assertEqual((small_response.status_code, large_response.status_code), (200, 200))
        # Variant sayı 2→22 olsa da sorğu sayı artmır (snapshot-dan render, N+1 yox).
        self.assertLessEqual(abs(len(large_queries) - len(small_queries)), 1)
        self.assertLessEqual(max(len(small_queries), len(large_queries)), 20)
