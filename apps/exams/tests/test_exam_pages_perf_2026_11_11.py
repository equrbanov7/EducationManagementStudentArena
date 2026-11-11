"""Müəllim imtahan səhifələri — sorğu büdcələri (sahib 2026-11-11: «burada da ləngdir hər şey»).

Ölçülən səhifələr: imtahan detalı, «İştirakçı nəticələri», sual bankı, yarat / redaktə sehrbazı və onun
müəllim / fənn axtarışları. Profil (700 sual × 5 variant, 408 cəhd × 30 cavab, 17 qrup) göstərdi ki, bu
səhifələrdə N+1 yoxdur (əvvəlki auditlərdə təmizlənib); qalan yük bunlar idi və burada qorunur:

* sual bankı — hər süzgəc / səhifə / toplu əməl TAM səhifəni yenidən yükləyirdi → ``X-QB-Partial`` fraqmenti;
  süzgəcsiz siyahıda Paginator-un ayrıca COUNT-u gedirdi → stat aqreqatından götürülür;
* nəticələr — hər sətir üçün cavabların ağır sütunları (yazılı cavab mətni, müəllim rəyi, rəsmin base64
  data-URL-i) yüklənirdi → təxirə salınıb;
* detal — sual sayı üçün iki ayrı COUNT → tək şərti aqreqat;
* sehrbazın müəllim axtarışı — üzvlük JOIN-u + bütün istifadəçi sütunları üzərində DISTINCT → yarım-birləşmə.

Büdcələr sətir sayından ASILI OLMAMALIDIR (kiçik və böyük fikstur eyni sorğu sayı).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.tests.exam_pages_scale_fixture import AJAX, ExamPagesScaleFixture
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.registrar.models import Subject
from core.rls import bypass_rls

User = get_user_model()
PARTIAL = {"HTTP_X_QB_PARTIAL": "1"}


def _sql(ctx, needle):
    return [query["sql"] for query in ctx.captured_queries if needle in query["sql"]]


class _PerfBase(ExamPagesScaleFixture):
    def setUp(self):
        super().setUp()
        cache.clear()

    def _count(self, url, **extra):
        client = self._client()
        client.get(url, **extra)  # isinmə (sessiya, icazə keşi)
        ctx, response = self._measure(lambda: client.get(url, **extra))
        self.assertEqual(response.status_code, 200)
        return ctx, response


class QuestionBankBudgetTests(_PerfBase):
    def _url(self, exam, **params):
        from urllib.parse import urlencode

        url = reverse("exams:teacher_questions_bank", kwargs={"slug": exam.slug})
        return f"{url}?{urlencode(params)}" if params else url

    def test_queries_do_not_grow_with_question_count(self):
        small, _, _, _ = self._build(questions=14, title="BankSmall", is_active=False)
        big, _, _, _ = self._build(questions=240, title="BankBig", is_active=False)
        small_ctx, _ = self._count(self._url(small))
        big_ctx, response = self._count(self._url(big))
        self.assertEqual(response.context["page_obj"].paginator.count, 240)
        self.assertEqual(len(big_ctx), len(small_ctx), (len(small_ctx), len(big_ctx)))
        self.assertLessEqual(len(big_ctx), 26)

    def test_unfiltered_list_needs_no_separate_count_query(self):
        exam, _, _, _ = self._build(questions=40, title="BankCount", is_active=False)
        ctx, response = self._count(self._url(exam, status="active", language="az"))
        self.assertEqual(response.context["page_obj"].paginator.count, 40)
        self.assertEqual(_sql(ctx, 'SELECT COUNT(*) AS "__count" FROM "exams_examquestion"'), [])

    def test_partial_fragment_is_smaller_and_not_more_expensive(self):
        exam, _, _, _ = self._build(questions=60, title="BankPartial", is_active=False)
        full_ctx, full = self._count(self._url(exam))
        part_ctx, part = self._count(self._url(exam), **PARTIAL)
        self.assertLessEqual(len(part_ctx), len(full_ctx))
        self.assertLess(len(part.content), len(full.content) * 0.7)

    def test_all_matching_mutation_cost_is_independent_of_selection_size(self):
        small, _, _, _ = self._build(questions=6, title="BankMutSmall", is_active=False)
        big, _, _, _ = self._build(questions=300, title="BankMutBig", is_active=False)
        client = self._client()
        data = {"bulk_action": "deactivate", "select_scope": "all_matching"}
        client.post(self._url(small), {"bulk_action": "activate_all"}, **AJAX)  # isinmə
        small_ctx, _ = self._measure(lambda: client.post(self._url(small), data, **AJAX))
        big_ctx, response = self._measure(lambda: client.post(self._url(big), data, **AJAX))
        self.assertEqual(response.status_code, 200)
        with bypass_rls():
            self.assertFalse(big.questions.filter(is_active=True).exists())
        self.assertLessEqual(len(big_ctx), len(small_ctx) + 1, (len(small_ctx), len(big_ctx)))


class ResultsBudgetTests(_PerfBase):
    def _url(self, exam, **params):
        from urllib.parse import urlencode

        url = reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug})
        return f"{url}?{urlencode(params)}" if params else url

    def test_queries_do_not_grow_with_attempts_or_groups(self):
        small, _, _, _ = self._build(questions=12, groups=1, students_each=3, answers_each=5, title="ResSmall")
        big, _, users, _ = self._build(questions=40, groups=6, students_each=10, answers_each=12, title="ResBig")
        small_ctx, _ = self._count(self._url(small, per_page="100"))
        big_ctx, response = self._count(self._url(big, per_page="100"))
        self.assertEqual(len(response.context["attempts_data"]), len(users))
        self.assertLessEqual(len(big_ctx), len(small_ctx) + 1, (len(small_ctx), len(big_ctx)))
        self.assertLessEqual(len(big_ctx), 40)

    def test_answer_rows_are_loaded_without_heavy_text_columns(self):
        exam, _, _, _ = self._build(questions=6, groups=1, students_each=3, answers_each=4, title="ResSlim")
        ctx, response = self._count(self._url(exam))
        answer_loads = [
            sql for sql in _sql(ctx, 'FROM "exams_examanswer"') if '"exams_examanswer"."attempt_id" IN' in sql
        ]
        self.assertEqual(len(answer_loads), 1)
        for column in ("text_answer", "teacher_feedback", "paint_data_url"):
            self.assertNotIn(f'"exams_examanswer"."{column}"', answer_loads[0])
        # Bal hesabı üçün lazım olan sütunlar yerindədir — nəticə dəyişmir.
        self.assertIn('"exams_examanswer"."question_snapshot"', answer_loads[0])
        first = response.context["attempts_data"][0]
        self.assertEqual(first["test_result"].delivered_count, 4)


class ExamDetailBudgetTests(_PerfBase):
    def test_question_counts_are_one_aggregate_and_page_is_flat(self):
        small, _, _, _ = self._build(questions=5, groups=1, students_each=2, answers_each=2, title="DetailSmall")
        big, _, _, _ = self._build(questions=260, groups=5, students_each=6, answers_each=3, title="DetailBig")
        small_ctx, _ = self._count(reverse("exams:teacher_exam_detail", kwargs={"slug": small.slug}))
        big_ctx, response = self._count(reverse("exams:teacher_exam_detail", kwargs={"slug": big.slug}))
        self.assertEqual(response.context["questions_total_count"], 260)
        self.assertEqual(response.context["active_questions_count"], 260)
        self.assertLessEqual(len(response.context["questions"]), 25)  # detal bütün bankı yükləmir
        counts = [sql for sql in _sql(big_ctx, 'FROM "exams_examquestion"') if "COUNT(" in sql]
        self.assertEqual(len(counts), 1, counts)
        self.assertLessEqual(len(big_ctx), len(small_ctx) + 2, (len(small_ctx), len(big_ctx)))
        self.assertLessEqual(len(big_ctx), 36)


class WizardBudgetTests(_PerfBase):
    """Sehrbaz müəllim / fənn siyahısını ƏVVƏLCƏDƏN yükləmir — hər ikisi serverdə axtarılır (LIMIT ilə)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.extra_teachers = []
        for index in range(30):
            user = User.objects.create_user(
                f"wz_teacher_{index}",
                f"wz_teacher_{index}@test.az",
                PASSWORD,
                first_name="Zərifə",
                last_name=f"T{index}",
            )
            _assign_user_to_org(user, cls.org, ProfileRole.TEACHER, "teacher")
            cls.extra_teachers.append(user)
        with bypass_rls():
            Subject.objects.bulk_create(
                [Subject(organization=cls.org, code=f"WZ-{index}", name=f"Wizard fənni {index}") for index in range(60)]
            )

    def test_wizard_form_does_not_embed_teacher_or_subject_lists(self):
        ctx, response = self._count(reverse("exams:create_exam") + "?modal=1", **AJAX)
        html = response.content.decode()
        self.assertNotIn("Zərifə", html)
        self.assertNotIn("Wizard fənni", html)
        self.assertIn(reverse("exams:subject_search"), html)
        self.assertIn(reverse("exams:bank_teacher_search"), html)
        self.assertEqual(_sql(ctx, 'FROM "registrar_subject"'), [])
        self.assertLessEqual(len(ctx), 16)

    def test_teacher_search_is_limited_and_uses_a_semijoin(self):
        ctx, response = self._count(reverse("exams:bank_teacher_search") + "?q=zərifə", **AJAX)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 10)
        self.assertTrue(payload["has_more"])
        user_queries = [sql for sql in _sql(ctx, 'FROM "auth_user"') if "organizations_membership" in sql]
        self.assertEqual(len(user_queries), 1)
        self.assertIn("LIMIT 11", user_queries[0])
        self.assertNotIn("SELECT DISTINCT", user_queries[0][:20])  # geniş sətir üzərində DISTINCT yoxdur
        self.assertNotIn('"auth_user"."password"', user_queries[0])
        self.assertLessEqual(len(ctx), 9)

    def test_subject_search_is_limited(self):
        ctx, response = self._count(reverse("exams:subject_search") + "?q=wizard", **AJAX)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 10)
        self.assertTrue(payload["has_more"])
        subject_queries = _sql(ctx, 'FROM "registrar_subject"')
        self.assertTrue(any("LIMIT 11" in sql for sql in subject_queries), subject_queries)
        self.assertLessEqual(len(ctx), 12)
