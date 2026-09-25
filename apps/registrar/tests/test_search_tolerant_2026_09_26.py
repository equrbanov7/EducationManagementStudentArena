"""Dözümlü axtarış — fənn kataloqu, kataloq konsolu, jurnal siyahısı, dərs müəllimi (sahib 2026-09-26).

«Verilenler» → «Verilənlər», «Aliyev» → «Əliyev», fənn kodu ayırıcıya dözümlü
(«QKU12» → «QKU-12»). Kanonik API: ``core.search_text.tolerant_q`` / ``tolerant_match``.
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.accounts.tests.test_teaching_office_stage2 import Stage2BaseTest
from apps.registrar import catalog_console
from apps.registrar.catalog_registry import build_subject_catalog
from apps.registrar.journal_list_query import apply_text_query
from apps.registrar.models import CourseOffering, Subject

User = get_user_model()


class _TolerantBase(Stage2BaseTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.db_subject = Subject.objects.create(
            organization=cls.org, code="QKU-12", name="Verilənlər bazası", ects=5, chair_unit=cls.chair
        )
        cls.teacher = cls.users["teacher"]
        cls.teacher.first_name, cls.teacher.last_name = "Şahzad", "Əliyev"
        cls.teacher.save(update_fields=["first_name", "last_name"])
        cls.offering = CourseOffering.objects.create(
            organization=cls.org, subject=cls.db_subject, period=cls.period, group=cls.group, instructor=cls.teacher
        )

    def _catalog_names(self, query):
        request = RequestFactory().get("/", {"sb_q": query})
        request.user = self.owner
        request.org_permissions = ["catalog.view"]
        section = build_subject_catalog(request, self.org)
        self.assertTrue(section.get("has_access", True))
        return {row["name"] for row in section["rows"]}


class SubjectCatalogTolerantSearchTest(_TolerantBase):
    def test_english_keyboard_finds_the_azerbaijani_subject_name(self):
        for query in ("Verilenler", "verilenler bazasi", "VERİLƏNLƏR", "bazası"):
            with self.subTest(query=query):
                self.assertEqual(self._catalog_names(query), {"Verilənlər bazası"})

    def test_subject_code_is_compact(self):
        for query in ("QKU12", "qku 12", "QKU-12"):
            with self.subTest(query=query):
                self.assertEqual(self._catalog_names(query), {"Verilənlər bazası"})

    def test_unrelated_query_and_blank_query(self):
        self.assertEqual(self._catalog_names("Kimya"), set())
        self.assertIn("Verilənlər bazası", self._catalog_names(""))
        self.assertIn(self.subject.name, self._catalog_names(""))

    def test_catalog_console_rows_use_the_same_folding(self):
        rows = catalog_console.rows(self.org, tab="subjects", query="Verilenler")
        self.assertEqual([row["title"] for row in rows], ["Verilənlər bazası"])
        rows = catalog_console.rows(self.org, tab="subjects", query="qku12")
        self.assertEqual([row["title"] for row in rows], ["Verilənlər bazası"])
        self.assertEqual(catalog_console.rows(self.org, tab="subjects", query="Kimya"), [])


class JournalListTolerantSearchTest(_TolerantBase):
    def _found(self, query):
        queryset = CourseOffering.objects.filter(organization=self.org)
        return set(apply_text_query(queryset, query).values_list("pk", flat=True))

    def test_teacher_and_subject_fold_azerbaijani_letters(self):
        for query in ("Aliyev", "Eliyev", "Sahzad", "shahzad aliyev", "verilenler", "QKU12"):
            with self.subTest(query=query):
                self.assertEqual(self._found(query), {self.offering.pk})

    def test_unrelated_query_matches_nothing(self):
        self.assertEqual(self._found("Məmmədzadə"), set())


def test_exam_score_roster_search_is_tolerant():
    """İmtahan balı siyahısı: «Aliyev» → «Əliyev», FİN kod rejimində (boşluq/tire yox)."""
    from types import SimpleNamespace

    from apps.registrar.exam_score_roster import filter_roster_rows

    student = SimpleNamespace(
        get_full_name=lambda: "Leylaxanım Əliyeva",
        username="leylaxanim.eliyeva.234king",
        profile=SimpleNamespace(fin="7AB12CD", institutional_identifier="QKU-4925"),
    )
    rows = [{"student": student, "has_score": False, "is_changed": False}]
    for query in ("aliyeva", "Eliyeva leylaxanim", "7ab 12cd", "qku4925", "LEYLAXANIM"):
        assert filter_roster_rows(rows, search=query) == rows, query
    assert filter_roster_rows(rows, search="qasimova") == []
