"""İmtahan sual bankı səhifəsi — sorğu büdcəsi və analiz keşi (P1-6, 2026-09-12).

Audit tapıntısı: ``teacher_questions_bank`` hər GET-də (səhifələmə, filtr,
sıralama, dil keçidi) imtahanın BÜTÜN suallarını variantları ilə yaddaşa
yükləyib keyfiyyət analizini yenidən hesablayırdı; üstəlik Paginator-un öz
COUNT-undan əlavə 3 ayrı ``.count()`` gedirdi.

Bu testlər üç şeyi qoruyur:

1. **Sorğu sayı sual sayından asılı deyil** — 3 sual ilə 15 sual eyni büdcə.
2. **Keş işləyir** — eyni məzmunda ikinci GET analizi yenidən hesablamır
   (sualları yenidən yükləmir).
3. **Keş köhnəlmir** — sual/variant əlavə, silinmə, redaktə (hətta siqnalsız
   ``update()`` / ``bulk_create`` / ``bulk_update`` ilə) və sıra dəyişəndə
   analiz yenidən hesablanır və nəticə dəyişikliyi əks etdirir.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.exams.services import bank_analysis
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

_LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "question-bank-view-budget",
    }
}


def _assign_teacher(user, organization):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = ProfileRole.TEACHER
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": organization.roles.get(name="teacher"), "is_primary": True, "is_active": True},
    )


class _QuestionBankViewBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("qb_budget_teacher", "qb_budget_teacher@example.com", "pw")
        cls.org = Organization.objects.create(
            name="QB Budget Univ",
            slug="qb-budget-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.teacher,
            status="active",
            is_active=True,
        )
        _assign_teacher(cls.teacher, cls.org)
        cls.exam = Exam.objects.create(author=cls.teacher, title="QB Budget Exam", exam_type="test", is_active=True)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.url = reverse("exams:teacher_questions_bank", args=[self.exam.slug])

    def _add_questions(self, count, *, start=1, language="az", option_count=5):
        created = []
        for index in range(start, start + count):
            question = ExamQuestion.objects.create(
                exam=self.exam,
                text=f"Sual mətni nömrə {index}",
                order=index,
                answer_mode="single",
                language=language,
            )
            for label_index in range(option_count):
                label = "ABCDE"[label_index]
                ExamQuestionOption.objects.create(
                    question=question,
                    label=label,
                    text=f"{index}-{label} variantı",
                    is_correct=(label_index == 0),
                )
            created.append(question)
        return created

    def _get(self, **params):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response, ctx

    @staticmethod
    def _exam_queries(ctx):
        """Yalnız imtahan cədvəllərinə gedən sorğular (sessiya/RLS/bildiriş səs-küyü çıxılır)."""
        return [q["sql"] for q in ctx.captured_queries if '"exams_' in q["sql"]]

    @staticmethod
    def _option_row_loads(ctx):
        """Variant SƏTİRLƏRİNİ yükləyən sorğular (digest variant cədvəlinə JOIN edir, amma sətir daşımır)."""
        return [q["sql"] for q in ctx.captured_queries if q["sql"].startswith('SELECT "exams_examquestionoption"."id"')]

    @staticmethod
    def _question_row_loads(ctx):
        return [q["sql"] for q in ctx.captured_queries if q["sql"].startswith('SELECT "exams_examquestion"."id"')]


class QuestionBankViewQueryBudgetTest(_QuestionBankViewBase):
    """Sorğu sayı sual sayına görə böyüməməlidir (DummyCache — həmişə miss)."""

    def test_query_count_is_independent_of_question_count(self):
        # İlk sorğu sessiya/profil isinməsi daşıyır — ölçmədən əvvəl bir dəfə açırıq.
        self.client.get(self.url)
        self._add_questions(3)
        _, small = self._get()

        self._add_questions(12, start=4)
        response, large = self._get()

        self.assertEqual(
            len(small),
            len(large),
            f"3 sual: {len(small)} sorğu, 15 sual: {len(large)} sorğu",
        )
        # Keş miss (DummyCache) büdcəsi — imtahan cədvəlləri üzrə 8 sorğu:
        #   1 imtahan (get_teacher_exam_or_404)
        #   2 məzmun digest-i (barmaq izi; sətir daşımır)
        #   3 analiz üçün sualların yüklənməsi   ┐ yalnız miss-də
        #   4 analiz üçün variantların prefetch-i ┘
        #   5 Paginator COUNT (filtrlənmiş siyahı)
        #   6 səhifə sətirləri (block select_related ilə)
        #   7 səhifə variantlarının prefetch-i
        #   8 stat kartları — tək şərti aqreqat (əvvəl 3 ayrı COUNT idi)
        self.assertEqual(len(self._exam_queries(large)), 8, self._exam_queries(large))
        self.assertEqual(len(self._question_row_loads(large)), 2)
        self.assertEqual(len(self._option_row_loads(large)), 2)
        self.assertEqual(response.context["total_questions"], 15)
        self.assertEqual(response.context["analyzed_total"], 15)

    def test_query_count_is_independent_of_question_count_with_language_filter(self):
        self.client.get(self.url)
        self._add_questions(2, language="az")
        self._add_questions(2, start=3, language="en")
        _, small = self._get(language="az")

        self._add_questions(10, start=5, language="az")
        response, large = self._get(language="az")

        self.assertEqual(len(small), len(large))
        self.assertEqual(response.context["total_questions"], 12)
        self.assertEqual(response.context["all_questions_total"], 14)


@override_settings(CACHES=_LOCMEM)
class QuestionBankAnalysisCacheInvalidationTest(_QuestionBankViewBase):
    """Analiz keşi: təkrar GET hesablamır; hər cür məzmun dəyişikliyi keşi köhnəldir."""

    def _get_with_analysis_spy(self, **params):
        with patch.object(bank_analysis, "_run_analysis", wraps=bank_analysis._run_analysis) as run:
            response, ctx = self._get(**params)
        return response, ctx, run

    def test_second_get_is_served_from_cache_without_reloading_questions(self):
        self._add_questions(4)
        first, first_ctx, first_run = self._get_with_analysis_spy()
        first_run.assert_called_once()

        second, second_ctx, second_run = self._get_with_analysis_spy(page="1", sort="az")
        second_run.assert_not_called()

        # Keş hit büdcəsi — imtahan cədvəlləri üzrə 6 sorğu: imtahan, digest,
        # Paginator COUNT, səhifə sətirləri, səhifə variantları, stat aqreqatı.
        # Bankın tamı yüklənmir: sual/variant sətirlərini yalnız səhifə sorğuları daşıyır.
        self.assertEqual(len(self._exam_queries(second_ctx)), 6, self._exam_queries(second_ctx))
        self.assertEqual(len(self._question_row_loads(second_ctx)), 1)
        self.assertEqual(len(self._option_row_loads(second_ctx)), 1)
        self.assertEqual(len(self._exam_queries(first_ctx)), 8)
        self.assertEqual(first.context["category_counts"], second.context["category_counts"])
        self.assertEqual(second.context["analyzed_total"], 4)

    def test_editing_question_text_via_update_invalidates_cache(self):
        questions = self._add_questions(3)
        self._get_with_analysis_spy()

        # Siqnalsız yazı — post_save işləmir; barmaq izi məzmundan gəlməlidir.
        ExamQuestion.objects.filter(pk=questions[1].pk).update(text=questions[0].text)
        response, _, run = self._get_with_analysis_spy()

        run.assert_called_once()
        self.assertEqual(response.context["category_counts"]["duplicates"], 0)
        # Mətn eyni olsa da variantlar fərqlidir — dublikat yoxdur; variantları da eyniləşdiririk.
        for source, target in zip(questions[0].options.order_by("label"), questions[1].options.order_by("label")):
            ExamQuestionOption.objects.filter(pk=target.pk).update(text=source.text)
        response, _, run = self._get_with_analysis_spy()

        run.assert_called_once()
        self.assertEqual(response.context["category_counts"]["duplicates"], 2)
        self.assertEqual(response.context["duplicate_count"], 2)

    def test_toggling_option_correctness_via_update_invalidates_cache(self):
        (question,) = self._add_questions(1)
        first, _, _ = self._get_with_analysis_spy()
        self.assertEqual(first.context["category_counts"]["errors"], 0)

        ExamQuestionOption.objects.filter(question=question).update(is_correct=False)
        response, _, run = self._get_with_analysis_spy()

        run.assert_called_once()
        self.assertEqual(response.context["analyzed_total"], 1)
        # Keşdəki (Excel hesabatının istifadə etdiyi) struktur da təzədir:
        # düzgün variant qalmayıb. Bu çağırış eyni barmaq izi ilə keşdən gəlir.
        with patch.object(bank_analysis, "_run_analysis") as run_again:
            cached = bank_analysis.analyze_question_bank(self.exam)
        run_again.assert_not_called()
        self.assertEqual(cached.parsed_for_report[0]["correct"], [])

    def test_deleting_an_option_invalidates_cache(self):
        (question,) = self._add_questions(1)
        first, _, _ = self._get_with_analysis_spy()
        self.assertEqual(first.context["category_counts"]["errors"], 0)

        question.options.filter(label="D").delete()
        response, _, run = self._get_with_analysis_spy()

        run.assert_called_once()
        self.assertEqual(response.context["category_counts"]["errors"], 1)

    def test_adding_an_option_via_bulk_create_invalidates_cache(self):
        (question,) = self._add_questions(1, option_count=4)
        first, _, _ = self._get_with_analysis_spy()
        self.assertEqual(first.context["category_counts"]["warnings"], 1)

        ExamQuestionOption.objects.bulk_create([ExamQuestionOption(question=question, label="E", text="E variantı")])
        response, _, run = self._get_with_analysis_spy()

        run.assert_called_once()
        self.assertEqual(response.context["category_counts"]["warnings"], 0)

    def test_adding_and_deleting_questions_invalidates_cache(self):
        questions = self._add_questions(2)
        self._get_with_analysis_spy()

        ExamQuestion.objects.bulk_create(
            [ExamQuestion(exam=self.exam, text="Toplu əlavə", order=3, answer_mode="single", language="az")]
        )
        response, _, run = self._get_with_analysis_spy()
        run.assert_called_once()
        self.assertEqual(response.context["analyzed_total"], 3)

        ExamQuestion.objects.filter(pk=questions[0].pk).delete()
        response, _, run = self._get_with_analysis_spy()
        run.assert_called_once()
        self.assertEqual(response.context["analyzed_total"], 2)

    def test_reordering_via_bulk_update_invalidates_cache(self):
        questions = self._add_questions(2)
        self._get_with_analysis_spy()

        questions[0].order, questions[1].order = 2, 1
        ExamQuestion.objects.bulk_update(questions, ["order"])
        _, _, run = self._get_with_analysis_spy()

        run.assert_called_once()

    def test_language_scopes_are_cached_separately(self):
        self._add_questions(2, language="az")
        self._add_questions(1, start=3, language="en")

        az_only, _, _ = self._get_with_analysis_spy(language="az")
        all_langs, _, run = self._get_with_analysis_spy()

        run.assert_called_once()
        self.assertEqual(az_only.context["analyzed_total"], 2)
        self.assertEqual(all_langs.context["analyzed_total"], 3)


class QuestionBankStatsTest(_QuestionBankViewBase):
    """Stat kartları: 3 ayrı COUNT tək aqreqata yığılsa da rəqəmlər dəyişməməlidir."""

    def test_counts_match_direct_queries_with_and_without_language_filter(self):
        az_questions = self._add_questions(3, language="az")
        self._add_questions(2, start=4, language="en")
        ExamQuestion.objects.filter(pk=az_questions[0].pk).update(is_active=False)

        response, _ = self._get()
        self.assertEqual(response.context["all_questions_total"], 5)
        self.assertEqual(response.context["total_questions"], 5)
        self.assertEqual(response.context["active_questions"], 4)
        self.assertEqual(response.context["inactive_questions"], 1)

        response, _ = self._get(language="az")
        self.assertEqual(response.context["all_questions_total"], 5)
        self.assertEqual(response.context["total_questions"], 3)
        self.assertEqual(response.context["active_questions"], 2)
        self.assertEqual(response.context["inactive_questions"], 1)

    def test_empty_bank_renders_zero_counts(self):
        response, _ = self._get()
        self.assertEqual(response.context["all_questions_total"], 0)
        self.assertEqual(response.context["total_questions"], 0)
        self.assertEqual(response.context["active_questions"], 0)
        self.assertEqual(response.context["inactive_questions"], 0)
        self.assertEqual(response.context["analyzed_total"], 0)
