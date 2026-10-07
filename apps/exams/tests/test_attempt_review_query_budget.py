"""Müəllimin cəhd yoxlama/baxış səhifələri və yazılı nəticə cədvəli — sorğu büdcəsi (2026-10-07).

Ölçülmüş tapıntılar (5 ↔ 20 sual, 10 ↔ 40 cəhd):

* ``teacher_check_attempt`` / ``teacher_view_attempt`` hər sual üçün ayrıca
  ``exams_exam`` SELECT atırdı (``_build_answer_review_item`` →
  ``answer.question.exam``): 5 sualda 35, 20 sualda 50 sorğu. İndi sual səhifənin
  imtahan instansını paylaşır — 29/33 sabit; baxış səhifəsində cavablar
  apellyasiya balı üçün ikinci dəfə yüklənmir.
* ``teacher_exam_results`` (yazılı imtahan) 12-lik səhifədə hər sətir üçün
  təşkilat SELECT-i atırdı (ad-görünürlüyü ``attempt.exam.organization``-a baxır,
  ``select_related("exam")`` hər sətrə ayrıca imtahan instansı verirdi): 41/43 →
  32 sabit.
* Yoxlama POST-u (``apply_manual_grading``) hər dəyişən cavab üçün ayrıca
  ``UPDATE`` atırdı və yönləndirmədən əvvəl baxış cavablarını boş yerə yükləyirdi:
  5 sualda 38, 20 sualda 52 sorğu → TƏK toplu UPDATE, ~30 sabit.

Render olunan HTML eyni qalıb (müqayisə vaxt/uuid normallaşdırılması ilə aparılıb).
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

#: Ölçülmüş dəyər (2026-10-07) + 3 ehtiyat. Əsas qıfıl isə «kiçik == böyük»dür.
CHECK_BUDGET = 32
VIEW_BUDGET = 36
RESULTS_BUDGET = 35
GRADE_POST_BUDGET = 33


def _assign(user, organization, profile_role, role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": organization.roles.get(name=role_name), "is_primary": True, "is_active": True},
    )


class AttemptReviewQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("arq_teacher", "arq_teacher@example.com", "pw")
        cls.org = Organization.objects.create(
            name="ARQ Univ",
            slug="arq-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.teacher,
            status="active",
            is_active=True,
        )
        _assign(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.students = []
        for index in range(12):
            student = User.objects.create_user(
                f"arq_s{index}", f"arq_s{index}@example.com", "pw", first_name=f"Tələbə{index}"
            )
            _assign(student, cls.org, ProfileRole.STUDENT, "student")
            cls.students.append(student)
        cls.exams = {}
        for exam_type in ("test", "written"):
            for size, questions in (("small", 5), ("large", 20)):
                cls.exams[(exam_type, size)] = cls._exam(exam_type, questions, cls.students[:2])
        # Yazılı nəticə cədvəli: 2 ↔ 12 cəhd (12 = tam səhifə).
        cls.results_small = cls._exam("written", 3, cls.students[:2])
        cls.results_large = cls._exam("written", 3, cls.students)

    @classmethod
    def _exam(cls, exam_type, question_count, students):
        exam = Exam.objects.create(
            author=cls.teacher,
            organization=cls.org,
            title=f"ARQ {exam_type} {question_count} {len(students)}",
            exam_type=exam_type,
            is_active=True,
            total_duration_minutes=60,
        )
        questions = [
            ExamQuestion.objects.create(exam=exam, text=f"Sual {i}", order=i + 1, points=5)
            for i in range(question_count)
        ]
        options = {}
        if exam_type == "test":
            for question in questions:
                ExamQuestionOption.objects.bulk_create(
                    [
                        ExamQuestionOption(question=question, label=label, text=f"v {label}", is_correct=label == "A")
                        for label in "ABCD"
                    ]
                )
                options[question.id] = list(question.options.order_by("label"))
        now = timezone.now()
        attempts = []
        for index, student in enumerate(students):
            attempt = ExamAttempt.objects.create(user=student, exam=exam, status="submitted", attempt_number=1)
            ExamAttempt.objects.filter(pk=attempt.pk).update(
                started_at=now - datetime.timedelta(hours=2, minutes=index),
                finished_at=now - datetime.timedelta(hours=1, minutes=index),
            )
            answers = ExamAnswer.objects.bulk_create(
                [
                    ExamAnswer(
                        attempt=attempt, question=question, text_answer="cavab" if exam_type == "written" else ""
                    )
                    for question in questions
                ]
            )
            if exam_type == "test":
                through = ExamAnswer.selected_options.through
                through.objects.bulk_create(
                    [
                        through(examanswer_id=answer.id, examquestionoption_id=options[answer.question_id][i % 2].id)
                        for i, answer in enumerate(answers)
                    ]
                )
            attempts.append(attempt)
        return exam, attempts

    def setUp(self):
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _get(self, url, **params):
        self.client.get(url, params)  # isinmə (sessiya möhürü, proses keşləri)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200, url)
        return response, ctx

    @staticmethod
    def _exam_selects(ctx):
        return [q["sql"] for q in ctx.captured_queries if q["sql"].startswith('SELECT "exams_exam"."id"')]

    def _attempt_url(self, name, key):
        exam, attempts = self.exams[key]
        return reverse(name, args=[exam.slug, attempts[0].id])

    def test_check_attempt_query_count_is_independent_of_question_count(self):
        for exam_type in ("test", "written"):
            with self.subTest(exam_type=exam_type):
                small_resp, small = self._get(self._attempt_url("exams:teacher_check_attempt", (exam_type, "small")))
                large_resp, large = self._get(self._attempt_url("exams:teacher_check_attempt", (exam_type, "large")))
                self.assertEqual(len(small_resp.context["qa_list"]), 5)
                self.assertEqual(len(large_resp.context["qa_list"]), 20)
                self.assertEqual(len(small), len(large), f"5 sual: {len(small)}, 20 sual: {len(large)}")
                self.assertLessEqual(len(large), CHECK_BUDGET)
                # İmtahan sətri yalnız bir dəfə (tenant-scoped lookup) oxunur — sual başına yox.
                self.assertEqual(len(self._exam_selects(large)), 1, self._exam_selects(large))

    def test_view_attempt_query_count_is_independent_of_question_count(self):
        for exam_type in ("test", "written"):
            with self.subTest(exam_type=exam_type):
                small_resp, small = self._get(self._attempt_url("exams:teacher_view_attempt", (exam_type, "small")))
                large_resp, large = self._get(self._attempt_url("exams:teacher_view_attempt", (exam_type, "large")))
                self.assertEqual(large_resp.context["qa_page"].paginator.count, 20)
                self.assertEqual(len(small), len(large), f"5 sual: {len(small)}, 20 sual: {len(large)}")
                self.assertLessEqual(len(large), VIEW_BUDGET)
                self.assertEqual(len(self._exam_selects(large)), 1, self._exam_selects(large))
                answer_loads = [
                    q["sql"] for q in large.captured_queries if q["sql"].startswith('SELECT "exams_examanswer"."id"')
                ]
                self.assertEqual(len(answer_loads), 1, answer_loads)

    def test_view_attempt_test_score_matches_direct_computation(self):
        from apps.exams import score_adjustments

        exam, attempts = self.exams[("test", "large")]
        response, _ = self._get(self._attempt_url("exams:teacher_view_attempt", ("test", "large")))
        expected = score_adjustments.effective_test_score(ExamAttempt.objects.get(pk=attempts[0].pk))
        actual = response.context["effective_score_info"]
        self.assertEqual(actual["effective_score"], expected["effective_score"])
        self.assertEqual(actual["max_score"], expected["max_score"])
        self.assertEqual(response.context["test_result"].correct_count, 10)

    def test_written_results_page_does_not_query_organization_per_row(self):
        small_exam, _ = self.results_small
        large_exam, _ = self.results_large
        small_resp, small = self._get(reverse("exams:teacher_exam_results", args=[small_exam.slug]))
        large_resp, large = self._get(reverse("exams:teacher_exam_results", args=[large_exam.slug]))
        self.assertEqual(len(small_resp.context["attempts_data"]), 2)
        self.assertEqual(len(large_resp.context["attempts_data"]), 12)
        self.assertEqual(len(small), len(large), f"2 cəhd: {len(small)}, 12 cəhd: {len(large)}")
        self.assertLessEqual(len(large), RESULTS_BUDGET)
        org_selects = [
            q["sql"] for q in large.captured_queries if q["sql"].startswith('SELECT "organizations_organization"')
        ]
        self.assertLessEqual(len(org_selects), 2, org_selects)
        # Yoxlanmamış yazılı cəhd — ad gizlidir (görünürlük qərarı dəyişməyib).
        self.assertTrue(all(not row["can_view_name"] for row in large_resp.context["attempts_data"]))

    def test_grading_post_query_count_is_independent_of_question_count(self):
        from django.contrib.contenttypes.models import ContentType

        from apps.exams.models import ExamGradeEvent

        ContentType.objects.get_for_model(ExamAttempt)  # audit yazısının proses keşi ölçüyə düşməsin
        counts = {}
        for size, question_count in (("small", 5), ("large", 20)):
            exam, attempts = self.exams[("written", size)]
            attempt = attempts[1]
            url = reverse("exams:teacher_check_attempt", args=[exam.slug, attempt.id])
            question_ids = list(exam.questions.order_by("id").values_list("id", flat=True))
            payload = {f"score_{qid}": str(index % 6) for index, qid in enumerate(question_ids)}
            payload.update({f"feedback_{qid}": f"rəy {index}" for index, qid in enumerate(question_ids)})
            self.client.get(url)  # isinmə
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.post(url, payload)
            self.assertEqual(response.status_code, 302)
            counts[size] = len(ctx.captured_queries)
            answer_updates = [
                q["sql"] for q in ctx.captured_queries if q["sql"].startswith('UPDATE "exams_examanswer"')
            ]
            self.assertEqual(len(answer_updates), 1, answer_updates)
            # Yazılan dəyərlər, ledger və cəhd xülasəsi əvvəlki kimi.
            answers = {a.question_id: a for a in ExamAnswer.objects.filter(attempt=attempt)}
            for index, qid in enumerate(question_ids):
                self.assertEqual(answers[qid].teacher_score, index % 6)
                self.assertEqual(answers[qid].teacher_feedback, f"rəy {index}")
            self.assertEqual(ExamGradeEvent.objects.filter(attempt=attempt).count(), question_count)
            attempt.refresh_from_db()
            self.assertTrue(attempt.checked_by_teacher)
            self.assertEqual(attempt.teacher_score, sum(index % 6 for index in range(question_count)))
        self.assertEqual(counts["small"], counts["large"], counts)
        self.assertLessEqual(counts["large"], GRADE_POST_BUDGET, counts)
