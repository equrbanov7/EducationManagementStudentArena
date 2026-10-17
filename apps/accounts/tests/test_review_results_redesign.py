"""«Dəyərləndirilmiş nəticələr» + «Bax» yenidən dizaynı (2026-10-17) — kontekst və sorğu büdcəsi.

Ölçülmüş (20 test + 20 yazılı cəhd, kabinet fraqmenti / 20 suallıq baxış):

* siyahı fraqmenti 24 → 26 sorğu: +1 apellyasiya statusu (bütün süzülmüş cəhdlər üçün TƏK
  sorğu), +1 görünən səhifənin yazılı cəhdləri üçün cavab+sual (JOIN) — «bal / maks» + faiz;
* baxış səhifəsi (test 33 / yazılı 28) dəyişməyib — xülasə və sual xəritəsi artıq yüklənmiş
  cavablardan sorğusuz törənir.

Əsas qıfıl: sorğu sayı cəhd / sual sayından ASILI DEYİL (kiçik == böyük), hər iki növ üçün.
"""

from __future__ import annotations

import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.test_review_queue_query_budget import QUESTIONS, _build_teacher_world
from apps.appeals.models import Appeal
from apps.exams.models import ExamAnswer, ExamAttempt, ExamQuestion

FRAGMENT = "accounts:profile_section_fragment"
#: Ölçülmüş 26 (2026-10-17) + ehtiyat.
LIST_FRAGMENT_BUDGET = 28


def _check_written(world, *, score=3, days_ago=2):
    """Yazılı cəhdləri «yoxlanılıb, pəncərə bağlanıb» vəziyyətinə gətirir (nəticələr siyahısına düşsün)."""
    checked = timezone.now() - datetime.timedelta(days=days_ago)
    written = world["exams"]["written"]
    ExamAttempt.objects.filter(exam=written).update(
        checked_by_teacher=True, teacher_checked_at=checked, teacher_score=score
    )
    ExamAnswer.objects.filter(attempt__exam=written).update(teacher_score=1)


class ReviewResultsListTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.small = _build_teacher_world("rrr-small", 4)
        cls.large = _build_teacher_world("rrr-large", 20)
        for world in (cls.small, cls.large):
            _check_written(world)
        test_attempt = ExamAttempt.objects.filter(exam=cls.large["exams"]["test"]).order_by("id").first()
        Appeal.objects.create(
            attempt=test_attempt,
            exam=test_attempt.exam,
            student=test_attempt.user,
            organization=cls.large["org"],
            status="pending",
        )

    def _get(self, world, **params):
        self.client.force_login(world["teacher"])
        session = self.client.session
        session["active_organization"] = world["org"].slug
        session.save()
        url = reverse(FRAGMENT, kwargs={"section": "review-results"})
        self.client.get(url, params, HTTP_X_REQUESTED_WITH="XMLHttpRequest")  # isinmə
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url, params, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        response.html = response.json()["html"]
        return response, ctx

    def test_query_count_is_independent_of_row_count_for_both_exam_types(self):
        for params in ({}, {"evaluated_type": "exam_test"}, {"evaluated_type": "exam_written"}):
            with self.subTest(**params):
                _, small = self._get(self.small, **params)
                _, large = self._get(self.large, **params)
                self.assertEqual(len(small), len(large), f"4 cəhd: {len(small)}, 20 cəhd: {len(large)}")
                self.assertLessEqual(len(large), LIST_FRAGMENT_BUDGET)
                appeal_selects = [
                    q["sql"]
                    for q in large.captured_queries
                    if q["sql"].startswith('SELECT "appeals_appeal"."attempt_id"')
                ]
                self.assertEqual(len(appeal_selects), 1, appeal_selects)

    def test_exam_kind_filter_and_type_badges(self):
        response, _ = self._get(self.large, evaluated_type="exam_written")
        items = response.context["evaluated_review_page_obj"].paginator.object_list
        self.assertEqual(len(items), 20)
        self.assertEqual({item["exam_kind"] for item in items}, {"written"})
        self.assertEqual(response.context["evaluated_review_filter_type"], "exam_written")
        self.assertIn("rr-type--written", response.html)
        self.assertNotIn("rr-type--test", response.html)

        response, _ = self._get(self.large, evaluated_type="exam_test")
        items = response.context["evaluated_review_page_obj"].paginator.object_list
        self.assertEqual({item["exam_kind"] for item in items}, {"test"})
        self.assertIn("rr-type--test", response.html)

    def test_written_score_shows_points_over_delivered_max_with_percent(self):
        response, _ = self._get(self.large, evaluated_type="exam_written")
        row = response.context["evaluated_review_page_obj"].object_list[0]
        # teacher_score=3, 5 sual × 1 bal → «3 / 5», 60 %.
        self.assertEqual(row["score_display"], f"3 / {QUESTIONS}")
        self.assertEqual(row["score_percent_display"], "60%")
        self.assertEqual(row["score_tone"], "success")

    def test_kpis_and_appeal_badge(self):
        response, _ = self._get(self.large)
        ui = response.context["evaluated_review_ui"]
        tiles = {str(tile["label"]): tile for tile in ui["kpi_tiles"]}
        self.assertEqual(tiles["Dəyərləndirilib"]["value"], 40)
        self.assertEqual(tiles["Tələbə"]["value"], 20)
        self.assertEqual(tiles["Apellyasiya"]["value"], 1)
        self.assertEqual(tiles["Apellyasiya"]["tone"], "accent-warning")
        # Test cəhdləri 2–3 saat əvvəl, yazılılar 2 gün əvvəl yoxlanılıb — hamısı son 7 gündə.
        self.assertEqual(tiles["Son 7 gün"]["value"], 40)
        self.assertIn("Apellyasiya: Gözləyir", response.html)
        self.assertEqual(ui["count_label"], "Nəticə: 40")

    def test_period_filter_and_back_link_keep_filters(self):
        ExamAttempt.objects.filter(exam=self.large["exams"]["written"]).update(
            teacher_checked_at=timezone.now() - datetime.timedelta(days=40)
        )
        response, _ = self._get(self.large, evaluated_period="30", er_page="2", evaluated_type="exams")
        self.assertEqual(response.context["evaluated_review_ui"]["period"], "30")
        items = response.context["evaluated_review_page_obj"].paginator.object_list
        self.assertEqual({item["exam_kind"] for item in items}, {"test"})
        action_url = response.context["evaluated_review_page_obj"].object_list[0]["action_url"]
        self.assertIn("evaluated_period%3D30", action_url)
        self.assertIn("er_page%3D2", action_url)
        self.assertIn("evaluated_period=30", response.context["evaluated_review_pagination_query"])

    def test_empty_state_mentions_filters_when_filtered(self):
        response, _ = self._get(self.large, evaluated_search="heç-bir-uyğunluq-yoxdur")
        self.assertEqual(
            str(response.context["evaluated_review_ui"]["empty"]["title"]), "Filtrə uyğun nəticə tapılmadı"
        )
        self.assertIn("Filtrə uyğun nəticə tapılmadı", response.html)


class AttemptReviewSummaryTest(TestCase):
    """«Bax» səhifəsi: vəziyyətlər, xülasə, sual xəritəsi — hər iki növ, sorğu sayı sual sayından asılı deyil."""

    @classmethod
    def setUpTestData(cls):
        cls.world = _build_teacher_world("rrs", 2)
        _check_written(cls.world)
        written = cls.world["exams"]["written"]
        cls.written_attempt = ExamAttempt.objects.filter(exam=written).order_by("id").first()
        answers = list(cls.written_attempt.answers.order_by("id"))
        # 5 sual × 1 bal: tam / tam / sıfır / qiymətsiz / tam.
        ExamAnswer.objects.filter(pk=answers[2].pk).update(teacher_score=0)
        ExamAnswer.objects.filter(pk=answers[3].pk).update(teacher_score=None)
        cls.test_attempt = ExamAttempt.objects.filter(exam=cls.world["exams"]["test"]).order_by("id").first()

    def setUp(self):
        self.client.force_login(self.world["teacher"])
        session = self.client.session
        session["active_organization"] = self.world["org"].slug
        session.save()

    def _url(self, attempt):
        return reverse("exams:teacher_view_attempt", args=[attempt.exam.slug, attempt.id])

    def _get(self, attempt, **params):
        self.client.get(self._url(attempt), params)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self._url(attempt), params)
        self.assertEqual(response.status_code, 200)
        return response, ctx

    def test_written_states_and_summary(self):
        response, _ = self._get(self.written_attempt)
        summary = response.context["review_summary"]
        self.assertFalse(summary["is_test"])
        self.assertEqual(summary["score_text"], f"3 / {QUESTIONS}")
        self.assertEqual(summary["percent"], 60.0)
        counts = {seg["key"]: seg["count"] for seg in summary["segments"]}
        self.assertEqual(counts, {"correct": 3, "wrong": 1, "ungraded": 1})
        self.assertEqual(
            [row["tone"] for row in response.context["question_map"]],
            ["success", "success", "danger", "info", "success"],
        )
        self.assertContains(response, "Tam bal")
        self.assertContains(response, "rv-eval")

    def test_test_states_and_correct_option_marking(self):
        response, _ = self._get(self.test_attempt)
        summary = response.context["review_summary"]
        self.assertTrue(summary["is_test"])
        counts = {seg["key"]: seg["count"] for seg in summary["segments"]}
        # Fikstur: cavablar növbə ilə A (düzgün) / B seçir → 3 düzgün, 2 səhv.
        self.assertEqual(counts, {"correct": 3, "wrong": 2})
        self.assertContains(response, "rv-opt is-selected is-correct")
        self.assertContains(response, "is-selected is-wrong")
        self.assertContains(response, "Tələbənin seçimi")

    def test_back_link_returns_to_filtered_results_list(self):
        return_to = "/accounts/profile/?section=review-results&evaluated_type=exam_written&er_page=2"
        response, _ = self._get(self.written_attempt, from_section="review-results", return_to=return_to)
        self.assertEqual(response.context["profile_return_url"], return_to)
        self.assertContains(response, "İmtahanın bütün nəticələri")

    def test_query_count_does_not_grow_with_question_count(self):
        for attempt in (self.written_attempt, self.test_attempt):
            with self.subTest(exam_type=attempt.exam.exam_type):
                _, before = self._get(attempt)
                for index in range(15):
                    question = ExamQuestion.objects.create(
                        exam=attempt.exam, text=f"Əlavə {index}", order=50 + index, points=1
                    )
                    ExamAnswer.objects.create(attempt=attempt, question=question, text_answer="x")
                response, after = self._get(attempt)
                self.assertEqual(len(response.context["question_map"]), QUESTIONS + 15)
                self.assertEqual(len(before), len(after), f"{QUESTIONS} sual: {len(before)}, 20 sual: {len(after)}")


class ReviewResultDetailPageTest(TestCase):
    """Qeyri-imtahan «Bax» (tapşırıq) — eyni baxış vərəqi qabığı, yoxlayan, geri linki filtrlərlə."""

    def test_assignment_detail_uses_review_sheet_layout(self):
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course

        world = _build_teacher_world("rrd", 1)
        teacher, student = world["teacher"], world["students"][0]
        course = Course.objects.create(owner=teacher, title="Detal kursu", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Detal tapşırığı",
            start_date=timezone.now() - datetime.timedelta(days=1),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment, user=student, content="Cavab mətni", status="graded", grade=90, graded_by=teacher
        )
        self.client.force_login(teacher)
        session = self.client.session
        session["active_organization"] = world["org"].slug
        session.save()
        return_to = "/accounts/profile/?section=review-results&evaluated_type=assignments"
        response = self.client.get(
            reverse("accounts:review_result_detail", kwargs={"item_type": "assignment", "item_id": submission.id}),
            {"return_to": return_to},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["back_url"], return_to)
        self.assertEqual(response.context["reviewer_display"], teacher.get_full_name() or teacher.username)
        self.assertContains(response, 'class="container rv-page"')
        self.assertContains(response, "Detal tapşırığı")
        self.assertContains(response, "rv-scorecard__big")
