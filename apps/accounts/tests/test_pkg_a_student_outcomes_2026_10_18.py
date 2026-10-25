"""Paket A (2026-10-18) — tələbə nəticə ekranları: sorğu büdcəsi, bal pariteti, dizayn sistemi müqavilələri.

* «Nəticələrim»: test balı yalnız GÖRÜNƏN səhifə üçün hesablanır (əvvəl bütün tarixçənin cavab +
  sual + variant sətirləri yüklənirdi). Sorğu sayı cəhd sayından asılı deyil və göstərilən bal
  ``calculate_test_attempt_result`` ilə eynidir; status (``graded`` / ``submitted``) dəyişməyib.
* İmtahan nəticəsi və «Mənim cavablarım»: sorğu sayı sual / cəhd sayından asılı deyil.
* Ortaq qat: badge `nowrap` (``text-wrap: pretty`` qısa yazısı onu ləğv edirdi), bal halqasının
  SVG dasharray dəyəri lokalizasiyasızdır, yeni status ailələri kataloqdadır.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.result_calculation import calculate_test_attempt_result
from apps.registrar.tests.test_student_sections_redesign import _build_tenant, _client_for
from core.ui import status_catalog

#: Büdcələr (2026-10-18 ölçmə + ehtiyat). Rəqəm aşılırsa — yeni N+1 və ya tam tarixçə yüklənməsi.
MY_RESULTS_EXAMS_BUDGET = (
    64  # 2026-10-25: +1 sabit; 2026-10-26: +2 sabit (fənn jurnalı ilə imtahan təyinatı) — tarixçə ilə artmır
)
EXAM_RESULT_BUDGET = 38
HISTORY_BUDGET = 26


def _student_profile(user, org):
    profile = user.profile
    profile.organization = org
    profile.organization_type = org.org_type
    profile.role = ProfileRole.STUDENT
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])


def _test_exam(org, teacher, title, n_questions):
    exam = Exam.objects.create(
        author=teacher, organization=org, title=title, exam_type="test", is_active=True, max_attempts_per_user=3
    )
    questions = []
    for index in range(n_questions):
        question = ExamQuestion.objects.create(exam=exam, text=f"Sual {index + 1}?", points=1)
        options = [
            ExamQuestionOption.objects.create(question=question, text=f"V {c}", label=c, is_correct=(c == "A"))
            for c in "ABCD"
        ]
        questions.append((question, options))
    return exam, questions


def _attempt(exam, questions, student, *, number=1, pattern=0):
    attempt = ExamAttempt.objects.create(
        user=student, exam=exam, status="submitted", attempt_number=number, finished_at=timezone.now()
    )
    for index, (question, options) in enumerate(questions):
        answer = ExamAnswer.objects.create(attempt=attempt, question=question)
        if (index + pattern) % 4 != 3:
            answer.selected_options.add(options[0] if (index + pattern) % 3 else options[1])
    return attempt


@override_settings(UNIVERSITY_MODE=True)
class MyResultsScoreDeferralTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t = _build_tenant(slug="pkgabud", subject_count=1)
        cls.org, cls.student, cls.teacher = cls.t["org"], cls.t["student"], cls.t["teacher"]
        _student_profile(cls.student, cls.org)

    def _add_attempts(self, count, n_questions=8):
        attempts = []
        for index in range(count):
            exam, questions = _test_exam(self.org, self.teacher, f"Budget test {index}", n_questions)
            attempts.append(_attempt(exam, questions, self.student, pattern=index))
        return attempts

    def _get(self):
        client = _client_for(self.org, self.student)
        url = reverse("accounts:profile") + "?section=my-results&results_type=exams"
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        return response, ctx

    def test_query_count_does_not_grow_with_history(self):
        self._add_attempts(3)
        self._get()  # isinmə
        _, small = self._get()
        self._add_attempts(12)
        response, large = self._get()
        self.assertEqual(len(large.captured_queries), len(small.captured_queries), "tarixçə uzandıqca sorğu artdı")
        self.assertLessEqual(len(large.captured_queries), MY_RESULTS_EXAMS_BUDGET)
        # Variant sətirləri yalnız görünən səhifənin (6 kart) cəhdləri üçün oxunur.
        option_queries = [q["sql"] for q in large.captured_queries if '"exams_examquestionoption"' in q["sql"]]
        self.assertTrue(option_queries)
        self.assertEqual(len(response.context["my_result_items"].object_list), 6)

    def test_visible_scores_match_canonical_calculation(self):
        attempts = {attempt.id: attempt for attempt in self._add_attempts(4, n_questions=10)}
        response, _ = self._get()
        items = [item for item in response.context["my_result_items"].object_list if item["category"] == "exams"]
        self.assertEqual(len(items), 4)
        for item in items:
            attempt = attempts[item["attempt_id"]]
            expected = calculate_test_attempt_result(attempt)
            self.assertEqual(item["score"], f"{expected.score_display} / {expected.max_score_display}")
            self.assertEqual(item["score_percent"], f"{expected.percentage_display}%")
            self.assertEqual(item["status"], "graded")
            self.assertIsNone(item["pending_score_attempt"])
        html = response.content.decode()
        self.assertIn("ems-ring", html)

    def test_attempt_without_answers_or_counts_stays_ungraded(self):
        exam, _ = _test_exam(self.org, self.teacher, "Boş cəhd", 3)
        ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted", attempt_number=1)
        legacy_exam, _ = _test_exam(self.org, self.teacher, "Köhnə cəhd", 3)
        ExamAttempt.objects.create(
            user=self.student, exam=legacy_exam, status="submitted", attempt_number=1, correct_count=2, wrong_count=1
        )
        response, _ = self._get()
        by_title = {item["title"]: item for item in response.context["my_result_items"].object_list}
        self.assertIsNone(by_title["Boş cəhd"]["score"])
        self.assertEqual(by_title["Boş cəhd"]["status"], "submitted")
        self.assertEqual(by_title["Köhnə cəhd"]["status"], "graded")
        self.assertEqual(by_title["Köhnə cəhd"]["score"], "2 / 3")


@override_settings(UNIVERSITY_MODE=True)
class MyResultsAppealBadgeVisibilityTest(TestCase):
    """Kartdakı apellyasiya nişanı rəyçinin redaktə pəncərəsi bağlanana qədər qərarı GİZLƏDİR."""

    @classmethod
    def setUpTestData(cls):
        cls.t = _build_tenant(slug="pkgaapl", subject_count=1)
        cls.org, cls.student, cls.teacher = cls.t["org"], cls.t["student"], cls.t["teacher"]
        _student_profile(cls.student, cls.org)
        exam, questions = _test_exam(cls.org, cls.teacher, "Apellyasiya testi", 3)
        cls.attempt = _attempt(exam, questions, cls.student)
        from apps.appeals.models import Appeal, AppealItem

        cls.appeal = Appeal.objects.create(
            attempt=cls.attempt, exam=exam, student=cls.student, organization=cls.org, status="accepted"
        )
        cls.item = AppealItem.objects.create(
            appeal=cls.appeal,
            question=questions[0][0],
            appeal_type="wrong_answer_key",
            status="accepted",
            resolved_at=timezone.now(),
        )

    def _card_appeal(self):
        client = _client_for(self.org, self.student)
        response = client.get(reverse("accounts:profile") + "?section=my-results&results_type=exams")
        self.assertEqual(response.status_code, 200)
        item = next(i for i in response.context["my_result_items"].object_list if i.get("attempt_id"))
        return item.get("appeal")

    def test_decision_inside_edit_window_is_shown_as_under_review(self):
        appeal = self._card_appeal()
        self.assertEqual(appeal["status"], "under_review")
        self.assertFalse(appeal["is_final"])
        self.assertEqual(appeal["tone"], "warning")

    def test_decision_after_edit_window_is_shown_as_decided(self):
        from apps.appeals.models import AppealItem

        AppealItem.objects.filter(pk=self.item.pk).update(resolved_at=timezone.now() - timedelta(minutes=30))
        appeal = self._card_appeal()
        self.assertEqual(appeal["status"], "accepted")
        self.assertTrue(appeal["is_final"])

    def test_student_status_lookup_has_constant_query_count(self):
        from apps.appeals.public import student_appeal_status_by_attempt

        with CaptureQueriesContext(connection) as ctx:
            result = student_appeal_status_by_attempt([self.attempt.id, self.attempt.id + 999])
        self.assertEqual(len(ctx.captured_queries), 2)  # apellyasiyalar + bəndlər (prefetch)
        self.assertEqual(result[self.attempt.id]["status"], "under_review")


@override_settings(UNIVERSITY_MODE=True)
class StudentResultPagesBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t = _build_tenant(slug="pkgares", subject_count=1)
        cls.org, cls.student, cls.teacher = cls.t["org"], cls.t["student"], cls.t["teacher"]
        _student_profile(cls.student, cls.org)

    def _result(self, attempt):
        client = _client_for(self.org, self.student)
        url = reverse("exams:exam_result", kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id})
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url + "?from_section=my-results")
        self.assertEqual(response.status_code, 200)
        return response, len(ctx.captured_queries)

    def test_exam_result_queries_do_not_grow_with_questions(self):
        exam_small, questions_small = _test_exam(self.org, self.teacher, "Kiçik", 4)
        exam_large, questions_large = _test_exam(self.org, self.teacher, "Böyük", 24)
        _, small = self._result(_attempt(exam_small, questions_small, self.student))
        response, large = self._result(_attempt(exam_large, questions_large, self.student))
        self.assertEqual(large, small)
        self.assertLessEqual(large, EXAM_RESULT_BUDGET)
        html = response.content.decode()
        self.assertIn("ems-ring", html)
        self.assertIn("result-back-btn", html)
        self.assertNotIn("alert alert-", html)
        self.assertNotIn('class="table ', html)

    def test_written_result_shows_score_over_delivered_max(self):
        exam = Exam.objects.create(
            author=self.teacher, organization=self.org, title="Yazılı", exam_type="written", is_active=True
        )
        q1 = ExamQuestion.objects.create(exam=exam, text="Esse", points=10)
        q2 = ExamQuestion.objects.create(exam=exam, text="Esse 2", points=10)
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=exam,
            status="submitted",
            attempt_number=1,
            finished_at=timezone.now(),
            checked_by_teacher=True,
            teacher_checked_at=timezone.now() - timedelta(days=1),
            teacher_score=14,
        )
        ExamAnswer.objects.create(attempt=attempt, question=q1, text_answer="a", teacher_score=8)
        ExamAnswer.objects.create(attempt=attempt, question=q2, text_answer="b", teacher_score=6)
        response, _ = self._result(attempt)
        self.assertEqual(response.context["written_max_score"], 20)
        self.assertEqual(response.context["written_score_pct"], 70.0)
        self.assertContains(response, "/ 20")

    def test_history_queries_do_not_grow_with_attempts(self):
        client = _client_for(self.org, self.student)
        url = reverse("exams:student_exam_history")
        exam, questions = _test_exam(self.org, self.teacher, "Tarixçə 0", 6)
        _attempt(exam, questions, self.student)
        client.get(url)  # isinmə: sessiya / bir dəfəlik keşlər ölçməyə düşməsin
        with CaptureQueriesContext(connection) as small:
            client.get(url)
        for index in range(1, 10):
            exam, questions = _test_exam(self.org, self.teacher, f"Tarixçə {index}", 6)
            _attempt(exam, questions, self.student)
        with CaptureQueriesContext(connection) as large:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(large.captured_queries), len(small.captured_queries))
        self.assertLessEqual(len(large.captured_queries), HISTORY_BUDGET)
        self.assertContains(response, "ems-table--stack")


class DesignSystemContractTest(SimpleTestCase):
    def _rule(self, path, selector):
        css = Path(settings.BASE_DIR, path).read_text(encoding="utf-8")
        body = css.split(selector + " {", 1)[1].split("}", 1)[0]
        return re.sub(r"/\*.*?\*/", "", body, flags=re.S)  # şərhlər deklarasiya deyil

    def test_badge_wraps_by_default_and_nowrap_is_opt_in(self):
        """Qlobal davranış əvvəlki kimi sarılandır (~345 istifadə); `nowrap` yalnız modifikatorla."""
        body = self._rule("static/css/ems_ui/badge.css", ".ems-badge")
        self.assertNotIn("white-space: nowrap", body)
        self.assertNotIn("text-wrap: ", body, "qısa yazı sarılma rejimini dəyişir — `text-wrap-style` işlədin")
        self.assertIn("text-wrap-style: pretty", body)
        self.assertIn("white-space: nowrap", self._rule("static/css/ems_ui/badge.css", ".ems-badge--nowrap"))
        html = Template('{% load ems_ui %}{% ems_status_badge "task_state" "open" nowrap=True %}').render(Context({}))
        self.assertIn("ems-badge--nowrap", html)

    def test_ring_dasharray_is_unlocalized_and_clamped(self):
        template = Template("{% load ems_ui %}{% ems_ring_dash value %}")
        with translation.override("az"):
            self.assertEqual(template.render(Context({"value": 58.3})), "58.3 100")
            self.assertEqual(template.render(Context({"value": 140})), "100 100")
            self.assertEqual(template.render(Context({"value": None})), "0 100")

    def test_score_ring_partial_has_no_inline_style(self):
        html = Template('{% include "partials/ems_ui/_score_ring.html" with ring_pct=75 ring_label="75%" %}').render(
            Context({})
        )
        self.assertIn('stroke-dasharray="75 100"', html)
        self.assertNotIn("style=", html)

    def test_student_status_families_exist(self):
        for family, keys in {
            "student_result": {"graded", "pending", "submitted", "removed"},
            "exam_attempt": {"submitted", "graded", "checking", "expired", "removed", "hidden", "waiting"},
            "academic_outcome": {"pass", "progress", "fail", "barred", "legacy_no_result"},
            "task_state": {"open", "upcoming", "closed"},
        }.items():
            self.assertEqual(set(status_catalog.keys(family)), keys, family)
