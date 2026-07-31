"""Sual bankı analizinin məzmun-hash keşi (Faza 7).

Analiz bankın BÜTÜN test suallarını variantları ilə yaddaşa yükləyib
dublikat/struktur/balans yoxlaması aparır. Detal səhifəsinin hər GET-ində
(səhifələmə, filtr, sıralama, dil dəyişmə) təkrar işləyirdi.

İndi nəticə məzmun barmaq izi (sual sayı + ən son ``updated_at``) ilə keşlənir.
Bu testlər iki şeyi qoruyur:

1. **Təkrar çağırış hesablamır** — eyni məzmunda ikinci çağırış keşdən gəlir.
2. **Köhnəlmiş nəticə göstərilmir** — sual əlavə/redaktə olunanda barmaq izi
   dəyişir və analiz yenidən hesablanır. Bu, keşin ən vacib xüsusiyyətidir:
   ayrıca invalidasiya çağırışı yoxdur, ona görə səhv olsa köhnə nəticə
   qalardı.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.exams.models import QuestionBank
from apps.exams.services.bank_analysis import analyze_bank_questions
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


# Test mühiti standart olaraq `DummyCache` işlədir (heç nə saxlanmır) — keşin
# ÖZÜNÜ yoxlamaq üçün yerli yaddaş backend-i lazımdır.
@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "bank-analysis"}}
)
class BankAnalysisCacheTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("ba_teacher", "ba_teacher@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="Bank Analysis Univ",
            slug="bank-analysis-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.teacher,
            status="active",
            is_active=True,
        )
        cls.bank = QuestionBank.objects.create(
            name="Analiz bankı",
            organization=cls.org,
            created_by=cls.teacher,
            is_active=True,
        )

    def setUp(self):
        cache.clear()

    def _add_question(self, text):
        return self.bank.library_questions.create(
            text=text,
            question_type="test",
            language="az",
            is_active=True,
        )

    def test_second_call_with_unchanged_content_is_served_from_cache(self):
        self._add_question("Sual 1")
        analyze_bank_questions(self.bank)

        with patch("apps.exams.services.bank_analysis._run_analysis") as run:
            analyze_bank_questions(self.bank)

        run.assert_not_called()

    def test_adding_a_question_invalidates_the_cached_analysis(self):
        self._add_question("Sual 1")
        first = analyze_bank_questions(self.bank)
        self.assertEqual(first.total_analyzed, 1)

        self._add_question("Sual 2")
        second = analyze_bank_questions(self.bank)

        self.assertEqual(second.total_analyzed, 2)

    def test_editing_a_question_invalidates_the_cached_analysis(self):
        question = self._add_question("Köhnə mətn")
        analyze_bank_questions(self.bank)

        question.text = "Yeni mətn"
        question.save(update_fields=["text", "updated_at"])

        with patch(
            "apps.exams.services.bank_analysis._run_analysis",
            wraps=__import__("apps.exams.services.bank_analysis", fromlist=["_run_analysis"])._run_analysis,
        ) as run:
            analyze_bank_questions(self.bank)

        run.assert_called_once()

    def test_language_scopes_are_cached_separately(self):
        self._add_question("Sual az")
        self.bank.library_questions.create(text="Question en", question_type="test", language="en", is_active=True)

        az_only = analyze_bank_questions(self.bank, language="az")
        all_langs = analyze_bank_questions(self.bank)

        self.assertEqual(az_only.total_analyzed, 1)
        self.assertEqual(all_langs.total_analyzed, 2)
