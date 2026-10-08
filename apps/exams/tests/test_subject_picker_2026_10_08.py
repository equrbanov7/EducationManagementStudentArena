"""Sual bankı «Bankı redaktə et» fənn seçicisi (müəllim rəyi Q1, 2026-10-08).

Bug: seçicidə «QKU-1234 — …» kodu əvvəl gəlirdi (müəllimə heç nə demir); axtarış
alt-sətir idi — «vo» «bihevorial» və «Devops»-u da tapırdı. İndi: AD əvvəl, kod
solğun meta; SÖZ BAŞLANĞICI + az/ing hərfə dözümlü; prefiks uyğunluqları birinci.
Dublikat fənnlər üçün YALNIZ-OXU hesabat komandası.
"""

import io
import json

from django.core.management import call_command
from django.test import SimpleTestCase
from django.urls import reverse

from apps.exams.models import QuestionBank
from apps.exams.tests.test_question_submission import _Base
from apps.registrar.models import Subject
from apps.registrar.subject_duplicates import normalized_subject_key
from core.search_text import word_prefix_match


class WordPrefixMatchTests(SimpleTestCase):
    def test_prefix_of_any_word(self):
        self.assertTrue(word_prefix_match("vo", "VoIP sistemlərinin əsasları"))
        self.assertTrue(word_prefix_match("vo", "Verilənlər bazası və VoIP"))
        self.assertFalse(word_prefix_match("vo", "Bihevorial iqtisadiyyat"))
        self.assertFalse(word_prefix_match("vo", "Devops mühəndisliyi"))

    def test_diacritic_and_case_tolerant(self):
        self.assertTrue(word_prefix_match("sebeke", "Kompüter şəbəkələri"))
        self.assertTrue(word_prefix_match("inf", "İnformatika"))
        self.assertTrue(word_prefix_match("kom seb", "Kompüter şəbəkələri"))
        self.assertFalse(word_prefix_match("kom xyz", "Kompüter şəbəkələri"))

    def test_word_start_after_punctuation(self):
        self.assertTrue(word_prefix_match("ip", "Vo-IP texnologiyası"))
        self.assertTrue(word_prefix_match("web", "(Web) proqramlaşdırma"))


class NormalizedSubjectKeyTests(SimpleTestCase):
    def test_spacing_and_letters_fold_to_same_key(self):
        self.assertEqual(
            normalized_subject_key("VoIP sistemlərinin layihələndirilməsi"),
            normalized_subject_key("Vo İP sistemlərinin  layihələndirilməsi"),
        )
        self.assertEqual(normalized_subject_key("Şəbəkə-1"), normalized_subject_key("sebeke 1"))
        self.assertNotEqual(normalized_subject_key("Şəbəkə 1"), normalized_subject_key("Şəbəkə 2"))


class SubjectSearchEndpointTests(_Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for code, name in (
            ("QKU-1001", "Bihevorial iqtisadiyyat"),
            ("QKU-1002", "Devops mühəndisliyi"),
            ("QKU-1003", "Verilənlər bazası və VoIP"),
            ("QKU-1004", "VoIP sistemlərinin layihələndirilməsi"),
            ("QKU-1005", "Kompüter şəbəkələri"),
        ):
            Subject.objects.create(organization=cls.org, code=code, name=name)

    def _search(self, q):
        response = self._client_for(self.teacher).get(reverse("exams:subject_search"), {"q": q})
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def test_vo_matches_word_prefixes_only_and_ranks_prefix_first(self):
        results = self._search("vo")
        self.assertEqual(
            [item["label"] for item in results],
            ["VoIP sistemlərinin layihələndirilməsi", "Verilənlər bazası və VoIP"],
        )

    def test_label_is_name_first_with_code_as_meta(self):
        item = self._search("kompüter")[0]
        self.assertEqual(item["text"], "Kompüter şəbəkələri (QKU-1005)")
        self.assertEqual(item["meta"], "QKU-1005")

    def test_diacritic_tolerant_and_code_search(self):
        self.assertEqual([i["meta"] for i in self._search("sebeke")], ["QKU-1005"])
        self.assertEqual([i["meta"] for i in self._search("1004")], ["QKU-1004"])

    def test_empty_query_lists_by_name(self):
        labels = [item["label"] for item in self._search("")]
        self.assertEqual(labels[0], "Bihevorial iqtisadiyyat")  # kodla yox, adla sıralanır
        self.assertEqual(len(labels), 5)

    def test_bank_subject_label_is_name_first(self):
        subject = Subject.objects.get(code="QKU-1005")
        bank = QuestionBank(name="Bank", subject_ref=subject, subject=subject.name)
        self.assertEqual(bank.subject_label, "Kompüter şəbəkələri (QKU-1005)")


class DuplicateSubjectReportTests(_Base):
    def test_report_lists_probable_duplicates_without_writing(self):
        first = Subject.objects.create(organization=self.org, code="QKU-2001", name="VoIP sistemlərinin əsasları")
        second = Subject.objects.create(organization=self.org, code="QKU-2002", name="Vo İP sistemlərinin  əsasları")
        Subject.objects.create(organization=self.org, code="QKU-2003", name="Kompüter şəbəkələri")
        before = list(Subject.objects.order_by("code").values_list("code", "name", "is_active"))

        out = io.StringIO()
        call_command("report_duplicate_subjects", organization=self.org.slug, format="json", stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(len(payload), 1)
        self.assertEqual({s["id"] for s in payload[0]["subjects"]}, {str(first.pk), str(second.pk)})
        self.assertEqual(list(Subject.objects.order_by("code").values_list("code", "name", "is_active")), before)

        text = io.StringIO()
        call_command("report_duplicate_subjects", organization=self.org.slug, stdout=text)
        self.assertIn("QKU-2001", text.getvalue())
        self.assertIn("heç nə dəyişmədi", text.getvalue())
