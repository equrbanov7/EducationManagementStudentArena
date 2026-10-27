"""Paket B (2026-10-17) — müəllimin imtahan iş sahəsi: detal, statistika, yoxlama səhifələri.

Qıfıllar:
* sorğu sayı sual / cəhd sayından ASILI DEYİL (N+1 qayıtmasın) və büdcə daxilindədir;
* statistikada qrup müqayisəsi qrup başına 1 sorğu artırır (əvvəl 2: `.filter(id=…).first()` + cəhdlər);
* statistika tarixi gg.aa.iiii qəbul edir, köhnə ISO linkləri də işləyir;
* nəticəsiz statistika Chart.js endirmir, izahlı boş vəziyyət göstərir;
* detal səhifəsi sehrbaz paketini (exam_wizard.js …) ilkin yükləmədə QOŞMUR — siyahı JSON-dadır;
* yoxlama səhifəsi sahə adlarını (score_<id>/feedback_<id>) və JS ID-lərini saxlayır.
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
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption, StudentGroup
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

#: Ölçülmüş (2026-10-17, sandbox): detal 22, statistika 20/21, yoxlama 27 — +3 ehtiyat.
#: 2026-10-27: detal +5 — «Tapşırıq təyin olunmuşlar» kartının sayı (PIN çoxluğu, sabit sorğu sayı) → 27 + 3.
DETAIL_BUDGET = 30
STATS_BUDGET = 24


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


class TeacherWorkspaceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("pkb_t", "pkb_t@example.com", "pw", first_name="Müəllim")
        cls.org = Organization.objects.create(
            name="PKB Univ",
            slug="pkb-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.teacher,
            status="active",
            is_active=True,
        )
        _assign(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.students = []
        for index in range(12):
            student = User.objects.create_user(f"pkb_s{index}", f"pkb_s{index}@example.com", "pw")
            _assign(student, cls.org, ProfileRole.STUDENT, "student")
            cls.students.append(student)
        cls.groups = []
        for index in range(3):
            group = StudentGroup.objects.create(teacher=cls.teacher, organization=cls.org, name=f"PKB G{index}")
            group.students.add(*cls.students[index::3])
            cls.groups.append(group)
        cls.small = cls._exam("test", 3, cls.students[:2])
        cls.large = cls._exam("test", 25, cls.students)
        cls.written = cls._exam("written", 4, cls.students[:1])
        cls.empty = cls._exam("test", 2, [])

    @classmethod
    def _exam(cls, exam_type, question_count, students):
        exam = Exam.objects.create(
            author=cls.teacher,
            organization=cls.org,
            title=f"PKB {exam_type} {question_count} {len(students)}",
            exam_type=exam_type,
            is_active=True,
            total_duration_minutes=45,
        )
        questions = [
            ExamQuestion.objects.create(exam=exam, text=f"Sual {i}", order=i + 1, points=5)
            for i in range(question_count)
        ]
        if exam_type == "test":
            for question in questions:
                ExamQuestionOption.objects.bulk_create(
                    [
                        ExamQuestionOption(question=question, label=label, text=f"v {label}", is_correct=label == "A")
                        for label in "ABCD"
                    ]
                )
        now = timezone.now()
        for index, student in enumerate(students):
            attempt = ExamAttempt.objects.create(user=student, exam=exam, status="submitted", attempt_number=1)
            ExamAttempt.objects.filter(pk=attempt.pk).update(
                started_at=datetime.datetime(2026, 10, 6, 9, 0, tzinfo=datetime.timezone.utc),
                finished_at=now,
                correct_count=index % max(question_count, 1),
                wrong_count=question_count - index % max(question_count, 1),
                duration_seconds=600 + index,
            )
            ExamAnswer.objects.bulk_create(
                [
                    ExamAnswer(attempt=attempt, question=q, text_answer="cavab" if exam_type == "written" else "")
                    for q in questions
                ]
            )
        return exam

    def setUp(self):
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _get(self, url, params=None):
        self.client.get(url, params or {})  # isinmə
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url, params or {})
        self.assertEqual(response.status_code, 200, url)
        return response, len(ctx)

    # ── Detal ────────────────────────────────────────────────────────────
    def test_detail_query_count_is_independent_of_question_count(self):
        _, small = self._get(reverse("exams:teacher_exam_detail", args=[self.small.slug]))
        _, large = self._get(reverse("exams:teacher_exam_detail", args=[self.large.slug]))
        self.assertEqual(small, large, f"3 sual: {small}, 25 sual: {large}")
        self.assertLessEqual(large, DETAIL_BUDGET)

    def test_detail_defers_wizard_bundle_and_uses_ems_dialogs(self):
        response, _ = self._get(reverse("exams:teacher_exam_detail", args=[self.small.slug]))
        html = response.content.decode()
        self.assertNotIn('<script src="/static/exams/js/exam_wizard.js', html)
        self.assertNotIn('href="/static/exams/css/exam_wizard.css', html)
        self.assertIn('id="ted-wizard-assets"', html)
        self.assertIn("exams/js/exam_wizard.js", html)  # yalnız JSON siyahısında
        self.assertIn("teacher_exam_detail_lazy.js", html)
        for dialog_id in ("examDetailDeleteConfirmModal", "examDetailTrialRunBlockedModal"):
            self.assertRegex(html, rf'class="ems-overlay ems-overlay--dialog" id="{dialog_id}" hidden')
        self.assertNotIn("🚀", html)
        self.assertIn("js-open-exam-form-modal", html)
        self.assertIn(f"/{self.small.slug}/toggle-active/", html)

    # ── Statistika ───────────────────────────────────────────────────────
    def test_statistics_query_count_is_independent_of_attempt_count(self):
        _, small = self._get(reverse("exams:teacher_exam_statistics", args=[self.small.slug]))
        _, large = self._get(reverse("exams:teacher_exam_statistics", args=[self.large.slug]))
        self.assertEqual(small, large, f"2 cəhd: {small}, 12 cəhd: {large}")
        self.assertLessEqual(large, STATS_BUDGET)

    def test_statistics_group_comparison_costs_one_query_per_group(self):
        url = reverse("exams:teacher_exam_statistics", args=[self.large.slug])
        _, one = self._get(url, {"compare_groups": [str(self.groups[0].id)]})
        response, three = self._get(url, {"compare_groups": [str(g.id) for g in self.groups]})
        self.assertEqual(three - one, 2, f"1 qrup: {one}, 3 qrup: {three}")
        self.assertEqual(len(response.context["compare_groups_data"]), 3)

    def test_statistics_date_filter_accepts_day_first_and_iso(self):
        url = reverse("exams:teacher_exam_statistics", args=[self.large.slug])
        for value in ("06.10.2026", "2026-10-06"):
            with self.subTest(value=value):
                response, _ = self._get(url, {"date_from": value, "date_to": value})
                self.assertEqual(response.context["total_attempts"], 12)
                self.assertEqual(response.context["f_date_from"], "06.10.2026")
        response, _ = self._get(url, {"date_from": "07.10.2026"})
        self.assertEqual(response.context["total_attempts"], 0)
        self.assertContains(response, "fa-filter-circle-xmark")

    def test_statistics_without_attempts_shows_empty_state_and_skips_chartjs(self):
        response, _ = self._get(reverse("exams:teacher_exam_statistics", args=[self.empty.slug]))
        self.assertNotContains(response, "chart.umd.min.js")
        self.assertContains(response, 'class="ems-state"', html=False)
        with_data, _ = self._get(reverse("exams:teacher_exam_statistics", args=[self.small.slug]))
        self.assertContains(with_data, "chart.umd.min.js")
        self.assertContains(with_data, 'id="questionTbody"', html=False)

    # ── Yoxlama ──────────────────────────────────────────────────────────
    def test_grading_page_keeps_field_names_and_hooks(self):
        attempt = ExamAttempt.objects.get(exam=self.written)
        response, _ = self._get(reverse("exams:teacher_check_attempt", args=[self.written.slug, attempt.id]))
        html = response.content.decode()
        for question in self.written.questions.all():
            self.assertIn(f'name="score_{question.id}"', html)
            self.assertIn(f'name="feedback_{question.id}"', html)
            self.assertIn(f'id="hidden_max_points_{question.id}"', html)
            self.assertNotIn(f'name="max_points_{question.id}"', html)
        for hook in ("gradingForm", "mainSaveBtn", "backBtn", "questionModal", "modalSaveBtn", "warningModal"):
            self.assertIn(f'id="{hook}"', html)
        self.assertRegex(html, r'id="mainSaveBtn" disabled')
        self.assertEqual(html.count('data-state="pending"'), 4 * 2)  # kart + xəritə çipi
