"""Perf auditi 2026-09-13 — `exams` tapıntılarının reqressiya testləri.

* **F-02** `StudentGroupForm` prefetch-i `teacher_id`-siz `.only()` ilə hər qrup
  üçün `refresh_from_db` atırdı → namizəd endpoint-inin sorğu sayı qrup
  sayından asılı olmamalıdır.
* **F-05** finish/autosave döngüsündə hər dəyişən cavab 3 sorğu idi
  (SELECT + through INSERT + UPDATE) → sorğu sayı SUAL SAYINDAN asılı
  olmamalıdır, nəticə (seçim, `is_correct`, `correct_count`) isə eyni qalmalıdır.
* F-10 (`/exams/groups/` tam səhifəsi) BU DALĞADA DÜZƏLDİLMƏDİ — kabinet «Qruplar» bölməsi
  sahibin 2026-09-08 qərarı ilə silindiyi üçün yönləndirmə mümkün deyil; hesabatda açıq P2.
* (köhnə qeyd) `/exams/groups/` tam səhifəsi bütün tələbə `<option>`-larını render
  edirdi (2.5 MB) → kabinet bölməsinə yönləndirilir; qapılar (tələbə 403) qalır.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt, ExamQuestion, ExamQuestionOption, StudentGroup
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
PASSWORD = "StrongPass123!"


class _OrgBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pf13_owner", "pf13_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="PF13 University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(cls.owner, cls.org, ProfileRole.ORG_OWNER)
        cls.teacher = User.objects.create_user("pf13_teacher", "pf13_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER)
        cls.student = User.objects.create_user("pf13_student", "pf13_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT)

    def _client(self, user):
        client = Client()
        _login_with_org(client, user, self.org)
        return client


class GroupCandidatesPrefetchTest(_OrgBase):
    """F-02 — qrup sayı 2 → 8: namizəd JSON-unun sorğu sayı dəyişmir."""

    def _make_groups(self, count: int, prefix: str):
        for index in range(count):
            group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name=f"{prefix}-{index}")
            group.teachers.add(self.teacher)
            group.students.add(self.student)

    def test_candidate_endpoint_query_count_is_independent_of_group_count(self):
        client = self._client(self.owner)
        url = reverse("exams:teacher_group_candidates")
        self._make_groups(2, "a")
        client.get(url)  # isinmə
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(client.get(url).status_code, 200)
        self._make_groups(6, "b")
        with CaptureQueriesContext(connection) as large:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        refresh_queries = [
            q["sql"]
            for q in large.captured_queries
            if '"exams_studentgroup"."teacher_id" FROM "exams_studentgroup"' in q["sql"] and "LIMIT 21" in q["sql"]
        ]
        self.assertEqual(refresh_queries, [], "prefetch `.only()` `teacher_id`-siz — hər qrup üçün refresh_from_db")
        self.assertEqual(len(small.captured_queries), len(large.captured_queries))
        # Məzmun dəyişməyib: tələbənin 8 qrup üzvlüyü də `data-user-group-labels`-də.
        payload = response.json()
        for index in range(6):
            self.assertIn(f"b-{index}", payload["students"])


class FinishAnswerWriteBatchTest(_OrgBase):
    """F-05 — finish sorğu sayı sual sayından asılı deyil; nəticə eynidir."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        now = timezone.now()
        cls.exams = {}
        for n in (5, 25):
            exam = Exam.objects.create(
                title=f"PF13 Quiz {n}",
                author=cls.teacher,
                organization=cls.org,
                exam_type="test",
                exam_type_extended="quiz",
                is_active=True,
                is_public=True,
                total_duration_minutes=60,
                random_question_count=n,
                start_datetime=now - timedelta(minutes=5),
                end_datetime=now + timedelta(hours=2),
            )
            for i in range(n):
                q = ExamQuestion.objects.create(exam=exam, order=i + 1, text=f"Sual {i}")
                ExamQuestionOption.objects.create(question=q, label="A", text="a", is_correct=True)
                ExamQuestionOption.objects.create(question=q, label="B", text="b", is_correct=False)
                ExamQuestionOption.objects.create(question=q, label="C", text="c", is_correct=False)
            cls.exams[n] = exam

    def _start(self, exam):
        client = self._client(self.student)
        self.assertEqual(client.get(reverse("exams:start_exam", kwargs={"slug": exam.slug})).status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, user=self.student)
        take_url = reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id})
        self.assertEqual(client.get(take_url).status_code, 200)
        return client, attempt, take_url

    def _finish(self, n, *, correct_first: int):
        """İlk `correct_first` sual düzgün (A), qalanı səhv (B) cavablanır."""
        exam = self.exams[n]
        client, attempt, take_url = self._start(exam)
        questions = list(exam.questions.order_by("order"))
        payload = {"submit_action": "finish"}
        for index, q in enumerate(questions):
            option = q.options.get(label="A" if index < correct_first else "B")
            payload[f"q_{q.id}"] = str(option.id)
            payload[f"q_present_{q.id}"] = "1"
        with CaptureQueriesContext(connection) as ctx:
            response = client.post(take_url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["finished"])
        attempt.refresh_from_db()
        return attempt, len(ctx.captured_queries)

    def test_finish_query_count_does_not_grow_with_question_count(self):
        attempt_5, queries_5 = self._finish(5, correct_first=3)
        attempt_25, queries_25 = self._finish(25, correct_first=20)
        self.assertEqual(queries_5, queries_25, f"finish: 5 sual={queries_5}, 25 sual={queries_25} — sual başına sorğu")

        # Nəticə dəyişməyib: seçimlər, `is_correct` və cəhdin balı.
        self.assertEqual(attempt_5.correct_count, 3)
        self.assertEqual(attempt_5.wrong_count, 2)
        self.assertEqual(attempt_25.correct_count, 20)
        self.assertEqual(attempt_25.wrong_count, 5)
        for attempt, correct_first in ((attempt_5, 3), (attempt_25, 20)):
            answers = list(attempt.answers.select_related("question").order_by("question__order"))
            self.assertEqual(len(answers), attempt.exam.random_question_count)
            for index, answer in enumerate(answers):
                labels = sorted(answer.selected_options.values_list("label", flat=True))
                self.assertEqual(labels, ["A"] if index < correct_first else ["B"])
                self.assertEqual(answer.is_correct, index < correct_first)
                self.assertEqual(answer.selected_option_ids_snapshot, [answer.selected_options.get().id])

    def test_changed_selection_replaces_the_previous_option(self):
        exam = self.exams[5]
        client, attempt, take_url = self._start(exam)
        q0 = exam.questions.order_by("order").first()
        option_a = q0.options.get(label="A")
        option_b = q0.options.get(label="B")

        def autosave(option, revision):
            response = client.post(
                take_url,
                {
                    "submit_action": "autosave",
                    "changed_questions[]": [str(q0.id)],
                    f"q_{q0.id}": str(option.id),
                    "autosave_revision": str(revision),
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(response.status_code, 200, response.content[:300])
            return response.json()["server_revision"]

        revision = autosave(option_a, 0)
        answer = attempt.answers.get(question=q0)
        self.assertEqual(set(answer.selected_options.values_list("id", flat=True)), {option_a.id})
        self.assertTrue(answer.is_correct)
        first_touch = answer.updated_at

        autosave(option_b, revision)
        answer.refresh_from_db()
        self.assertEqual(set(answer.selected_options.values_list("id", flat=True)), {option_b.id})
        self.assertFalse(answer.is_correct)
        self.assertEqual(answer.selected_option_ids_snapshot, [option_b.id])
        self.assertGreater(answer.updated_at, first_touch)
