"""Müəllim «Yoxlanılacaq işlər» / «Yoxlanılmış işlər» bölmələri — sorğu/sətir büdcəsi (2026-10-07).

Ölçülmüş tapıntılar (8 ↔ 32 tələbə, kabinet fraqmenti):

* **pending-review** — ad-görünürlüyü qərarı (``attempt.exam.organization``) hər
  gözləyən yazılı cəhd üçün ayrıca təşkilat SELECT-i atırdı: 28 → 52 sorğu
  (fraqment), 42 → 66 (tam səhifə). Prefetch ilə distinct təşkilatlar TƏK
  sorğuda — 35 sabit (tam səhifə).
* **review-results** — sorğu SAYI sabit idi, amma müəllimin BÜTÜN test
  tarixçəsinin cavab + variant sətirləri hər açılışda yüklənirdi (20 cəhd ×
  5 sual = 100 cavab), cədvəl isə 15 sətir göstərir. İndi bal yalnız görünən
  səhifənin sətirləri üçün hesablanır (1-ci səhifə 75, 2-ci səhifə 25 cavab).

HTML eyni qalıb (vaxt/uuid/slug normallaşdırılmış müqayisə).
"""

from __future__ import annotations

import datetime
from collections import Counter

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models.signals import post_init
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.public import calculate_test_attempt_result
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

FRAGMENT = "accounts:profile_section_fragment"
QUESTIONS = 5


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


class _RowCounter:
    def __init__(self, *models):
        self.models = models
        self.counts = Counter()

    def _receiver(self, sender, **kwargs):
        if sender in self.models:
            self.counts[sender.__name__] += 1

    def __enter__(self):
        post_init.connect(self._receiver, weak=False)
        return self

    def __exit__(self, *exc):
        post_init.disconnect(self._receiver)
        return False


def _build_teacher_world(slug, student_count):
    teacher = User.objects.create_user(f"{slug}_teacher", f"{slug}_teacher@example.com", "pw")
    org = Organization.objects.create(
        name=f"{slug} Univ",
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=teacher,
        status="active",
        is_active=True,
    )
    _assign(teacher, org, ProfileRole.TEACHER, "teacher")
    students = []
    for index in range(student_count):
        student = User.objects.create_user(f"{slug}_s{index}", f"{slug}_s{index}@example.com", "pw", first_name="T")
        _assign(student, org, ProfileRole.STUDENT, "student")
        students.append(student)
    now = timezone.now()
    exams = {}
    for exam_type in ("test", "written"):
        exam = Exam.objects.create(
            author=teacher,
            organization=org,
            title=f"{slug} {exam_type}",
            exam_type=exam_type,
            is_active=True,
            total_duration_minutes=60,
        )
        questions = [
            ExamQuestion.objects.create(exam=exam, text=f"Sual {i}", order=i + 1, points=1) for i in range(QUESTIONS)
        ]
        options = {}
        if exam_type == "test":
            for question in questions:
                ExamQuestionOption.objects.bulk_create(
                    [
                        ExamQuestionOption(question=question, label=label, text=label, is_correct=label == "A")
                        for label in "ABCD"
                    ]
                )
                options[question.id] = list(question.options.order_by("label"))
        for index, student in enumerate(students):
            attempt = ExamAttempt.objects.create(user=student, exam=exam, status="submitted", attempt_number=1)
            ExamAttempt.objects.filter(pk=attempt.pk).update(
                started_at=now - datetime.timedelta(hours=3, minutes=index),
                finished_at=now - datetime.timedelta(hours=2, minutes=index),
            )
            answers = ExamAnswer.objects.bulk_create(
                [ExamAnswer(attempt=attempt, question=q, text_answer="cavab") for q in questions]
            )
            if exam_type == "test":
                through = ExamAnswer.selected_options.through
                through.objects.bulk_create(
                    [
                        through(examanswer_id=answer.id, examquestionoption_id=options[answer.question_id][i % 2].id)
                        for i, answer in enumerate(answers)
                    ]
                )
        exams[exam_type] = exam
    return {"org": org, "teacher": teacher, "students": students, "exams": exams}


class ReviewQueueQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.small = _build_teacher_world("rqb-small", 4)
        cls.large = _build_teacher_world("rqb-large", 20)

    def _get(self, world, section, **params):
        self.client.force_login(world["teacher"])
        session = self.client.session
        session["active_organization"] = world["org"].slug
        session.save()
        url = reverse(FRAGMENT, kwargs={"section": section})
        self.client.get(url, params, HTTP_X_REQUESTED_WITH="XMLHttpRequest")  # isinmə
        with _RowCounter(ExamAnswer) as rows, CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url, params, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        return response, ctx, rows.counts

    @staticmethod
    def _org_selects(ctx):
        return [q["sql"] for q in ctx.captured_queries if q["sql"].startswith('SELECT "organizations_organization"')]

    def test_pending_review_query_count_is_independent_of_pending_attempts(self):
        _, small, _ = self._get(self.small, "pending-review")
        _, large, _ = self._get(self.large, "pending-review")
        self.assertEqual(len(small), len(large), f"4 cəhd: {len(small)}, 20 cəhd: {len(large)}")
        self.assertEqual(len(self._org_selects(small)), len(self._org_selects(large)), self._org_selects(large))

    def test_review_results_scores_only_the_visible_page(self):
        _, small, small_rows = self._get(self.small, "review-results")
        response, large, large_rows = self._get(self.large, "review-results")
        self.assertEqual(len(small), len(large), f"4 cəhd: {len(small)}, 20 cəhd: {len(large)}")
        # 20 qiymətləndirilmiş test cəhdi, səhifə 15 sətir: yalnız 15 × 5 cavab yüklənir (əvvəl 100).
        self.assertEqual(large_rows["ExamAnswer"], 15 * QUESTIONS)
        self.assertEqual(small_rows["ExamAnswer"], 4 * QUESTIONS)
        page = response.context["evaluated_review_page_obj"]
        self.assertEqual(page.paginator.count, 20)
        self.assertTrue(all(item["score_display"] for item in page.object_list))

        second, _, second_rows = self._get(self.large, "review-results", er_page=2)
        self.assertEqual(second_rows["ExamAnswer"], 5 * QUESTIONS)
        items = second.context["evaluated_review_page_obj"].object_list
        self.assertEqual(len(items), 5)
        attempts = {
            a.user_id: a for a in ExamAttempt.objects.filter(exam=self.large["exams"]["test"]).select_related("exam")
        }
        for item in items:
            expected = calculate_test_attempt_result(attempts[item["student"].id])
            self.assertEqual(item["score_display"], f"{expected.score_display} / {expected.max_score_display}")
            self.assertEqual(item["score_percent_display"], f"{expected.percentage_display}%")
