"""Təhlükəsizlik dizaynı 2026-10-08 — vaxtlı YAZILI sualın məzmunu səhifə mənbəyinə düşmür.

Audit 2026-10-07 «Dizayn riskləri»: strict delivery (EXAM-P1-04) yalnız TEST suallarına
tətbiq olunurdu; vaxtlı yazılı sualın mətni/şəkli/videosu ilk GET-də HTML-də idi — tələbə
taymer başlamadan «Mənbəyə bax» ilə bütün sualları oxuya bilirdi. İndi yazılı sual da yer
tutucu kimi gəlir; məzmun (və cavab sahəsi) tələbə sualı açanda ``question-seen`` ilə,
taymer serverdə başlayandan sonra göndərilir.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamSupervisionConfig
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    PASSWORD,
    User,
    _assign_user_to_org,
    _make_people,
    _student_client,
)

SECRET = "WRITTEN-TIMED-SECRET-1008"
IDEAL = "WRITTEN-IDEAL-ANSWER-1008"
#: Ölçü (config.settings.test, 3 suallıq vaxtlı yazılı imtahan, ~9 middleware sorğusu daxil):
#: ``question-seen`` (yazılı gövdə + cavab sahəsi) 23; test sualı üçün mövcud hədd 35-dir.
WRITTEN_DELIVERY_BUDGET = 23
#: Suallar səhifəsi GET: 18 (yer tutucular — mövcud yazılı/test büdcəsi 25).
QUESTIONS_PAGE_BUDGET = 18


def _written_exam(org, teacher, *, title="WD1008", timed=True, n_questions=3, **extra):
    now = timezone.now()
    exam = Exam.objects.create(
        title=title,
        author=teacher,
        organization=org,
        exam_type="written",
        exam_type_extended="quiz",
        is_active=True,
        is_public=True,
        total_duration_minutes=30,
        random_question_count=n_questions,
        start_datetime=now - timedelta(minutes=5),
        end_datetime=now + timedelta(hours=2),
        **extra,
    )
    for index in range(n_questions):
        ExamQuestion.objects.create(
            exam=exam,
            order=index + 1,
            text=f"{SECRET}-{index}",
            correct_answer=f"{IDEAL}-{index}",
            image=f"exam_questions/written-secret-{index}.png",
            video=f"exam_questions/written-secret-{index}.mp4",
            time_limit_seconds=90 if timed else None,
        )
    return exam


@override_settings(CACHES=LOCMEM_CACHE, EXAM_SUPERVISION_ENABLED=True)
class TimedWrittenQuestionDeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("wd1008")

    def setUp(self):
        self.client = _student_client("wd1008_student", self.org)

    def _start(self, exam):
        self.assertEqual(self.client.post(reverse("exams:start_exam", kwargs={"slug": exam.slug})).status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, user=self.student)
        take_url = reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id})
        seen_url = reverse("exams:question_seen", kwargs={"slug": exam.slug, "attempt_id": attempt.id})
        question_ids = list(attempt.answers.order_by("id").values_list("question_id", flat=True))
        return attempt, take_url, seen_url, question_ids

    def test_initial_page_has_only_placeholders_for_timed_written_questions(self):
        exam = _written_exam(self.org, self.teacher)
        _attempt, take_url, _seen_url, question_ids = self._start(exam)

        html = self.client.get(take_url).content.decode()

        self.assertEqual(html.count('data-server-delivery="1"'), len(question_ids))
        for question_id in question_ids:
            self.assertIn(f'data-question-id="{question_id}"', html)
            self.assertNotIn(f'name="q_{question_id}"', html)
            self.assertNotIn(f'name="q_present_{question_id}"', html)
        self.assertNotIn(SECRET, html)
        self.assertNotIn("written-secret-", html)
        self.assertNotIn(IDEAL, html)

    def test_untimed_written_questions_keep_the_full_initial_render(self):
        exam = _written_exam(self.org, self.teacher, title="WD1008 untimed", timed=False)
        _attempt, take_url, _seen_url, question_ids = self._start(exam)

        html = self.client.get(take_url).content.decode()

        self.assertNotIn('data-server-delivery="1"', html)
        self.assertIn(SECRET, html)
        self.assertIn(f'name="q_{question_ids[0]}"', html)

    def test_opening_the_question_starts_the_timer_and_delivers_body_and_answer_area(self):
        exam = _written_exam(self.org, self.teacher)
        attempt, _take_url, seen_url, question_ids = self._start(exam)
        first = question_ids[0]

        response = self.client.post(seen_url, {"question_id": str(first)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["limit_seconds"], 90)
        body = payload["html"]
        index = ExamQuestion.objects.get(pk=first).order - 1
        self.assertIn(f"{SECRET}-{index}", body)
        self.assertIn(f"written-secret-{index}.png", body)
        self.assertIn(f'name="q_present_{first}"', body)
        self.assertIn(f'name="q_{first}"', body)
        self.assertIn('class="written-answer"', body)
        self.assertIn(f'data-exam-dropzone-qid="{first}"', body)
        self.assertNotIn(IDEAL, body)
        # Yalnız açılan sual: digərlərinin məzmunu və taymeri yoxdur.
        for other in question_ids[1:]:
            self.assertNotIn(f'name="q_{other}"', body)
        attempt.refresh_from_db()
        self.assertIn(str(first), attempt.question_timing)
        self.assertNotIn(str(question_ids[1]), attempt.question_timing)

    def test_delivered_body_keeps_the_saved_text_and_reload_renders_started_question_inline(self):
        exam = _written_exam(self.org, self.teacher)
        attempt, take_url, seen_url, question_ids = self._start(exam)
        first = question_ids[0]
        self.client.post(seen_url, {"question_id": str(first)})
        autosave = self.client.post(
            take_url,
            {
                "submit_action": "autosave",
                "changed_questions[]": [str(first)],
                f"q_{first}": "mənim cavabım 1008",
                "marked_question_ids": "[]",
                "autosave_revision": "0",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(autosave.status_code, 200, autosave.content[:300])
        self.assertEqual(ExamAnswer.objects.get(attempt=attempt, question_id=first).text_answer, "mənim cavabım 1008")

        repeat = self.client.post(seen_url, {"question_id": str(first)}).json()
        self.assertIn("mənim cavabım 1008", repeat["html"])
        # Reload: başlanmış sual adi qaydada (cavabla) render olunur, başlanmamışlar yer tutucudur.
        html = self.client.get(take_url).content.decode()
        self.assertIn("mənim cavabım 1008", html)
        self.assertEqual(html.count('data-server-delivery="1"'), len(question_ids) - 1)

    def test_unstarted_written_answer_is_still_refused_by_the_timer_guard(self):
        exam = _written_exam(self.org, self.teacher)
        _attempt, take_url, _seen_url, question_ids = self._start(exam)
        response = self.client.post(
            take_url,
            {
                "submit_action": "autosave",
                "changed_questions[]": [str(question_ids[0])],
                f"q_{question_ids[0]}": "taymersiz cavab",
                "autosave_revision": "0",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "question_timer_not_started")

    def test_no_content_after_time_is_up_or_under_proctor_lock(self):
        exam = _written_exam(self.org, self.teacher)
        ExamSupervisionConfig.objects.create(exam=exam, enabled=True)
        attempt, _take_url, seen_url, question_ids = self._start(exam)

        ExamAttempt.objects.filter(pk=attempt.pk).update(
            supervision_status="locked", supervision_locked_at=timezone.now(), supervision_manual_lock=True
        )
        locked = self.client.post(seen_url, {"question_id": str(question_ids[0])})
        self.assertEqual(locked.status_code, 423)
        self.assertNotIn("html", locked.json())

        ExamAttempt.objects.filter(pk=attempt.pk).update(
            supervision_status="active",
            supervision_manual_lock=False,
            started_at=timezone.now() - timedelta(hours=1),
        )
        overdue = self.client.post(seen_url, {"question_id": str(question_ids[0])})
        self.assertEqual(overdue.status_code, 409)
        self.assertNotIn("html", overdue.json())
        attempt.refresh_from_db()
        self.assertEqual(attempt.question_timing.get(str(question_ids[0])), None)

    def test_other_students_attempt_is_not_delivered(self):
        exam = _written_exam(self.org, self.teacher)
        _attempt, _take_url, seen_url, question_ids = self._start(exam)
        other = User.objects.create_user("wd1008_other", "wd1008_other@test.az", PASSWORD)
        _assign_user_to_org(other, self.org, ProfileRole.STUDENT)
        client = _student_client("wd1008_other", self.org)
        response = client.post(seen_url, {"question_id": str(question_ids[0])})
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(SECRET, response.content.decode())

    def test_delivery_query_budget(self):
        exam = _written_exam(self.org, self.teacher)
        _attempt, _take_url, seen_url, question_ids = self._start(exam)
        self.client.post(seen_url, {"question_id": str(question_ids[0])})  # isinmə

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.post(seen_url, {"question_id": str(question_ids[1])})

        self.assertEqual(response.status_code, 200)
        self.assertIn("html", response.json())
        sqls = [query["sql"] for query in ctx.captured_queries]
        self.assertLessEqual(len(sqls), WRITTEN_DELIVERY_BUDGET, "\n".join(sqls))

    def test_take_page_budget_with_timed_written_questions(self):
        exam = _written_exam(self.org, self.teacher)
        _attempt, take_url, _seen_url, _question_ids = self._start(exam)
        self.client.get(take_url)  # isinmə

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(take_url)

        self.assertEqual(response.status_code, 200)
        sqls = [query["sql"] for query in ctx.captured_queries]
        self.assertLessEqual(len(sqls), QUESTIONS_PAGE_BUDGET, "\n".join(sqls))
