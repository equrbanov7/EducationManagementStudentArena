"""Sual şablonunun Word (.docx) variantı (sahib 2026-09-21): imtahan test-bankı və
müstəqil bank üçün `?format=docx` real .docx qaytarır (PK zip imzası, düzgün
content-type), TXT davranışı dəyişmir; workbench şablon düymələrində DOCX birinci,
başlıq keçidlərində izah mətni var."""

from django.urls import reverse

from apps.exams.services.question_template_docx import DOCX_CONTENT_TYPE, build_template_docx

from .test_w4_wizard_units import _login, _UnitFixture


class TemplateDocxTest(_UnitFixture):
    def test_build_template_docx_is_a_word_document(self):
        payload = build_template_docx("# izah\n\n1. Sual?\nA) a\n*B) b\n", title="Şablon")
        self.assertTrue(payload.startswith(b"PK"))
        self.assertGreater(len(payload), 2000)

    def test_exam_test_bank_template_download_docx_and_txt(self):
        exam = self._exam()
        client = _login(self.teacher, self.org)
        url = reverse("exams:test_question_bank_template_download", kwargs={"slug": exam.slug})
        response = client.get(url, {"format": "docx"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], DOCX_CONTENT_TYPE)
        self.assertIn('filename="sual_sablonu.docx"', response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"PK"))
        response = client.get(url, {"format": "txt"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertIn("Cavab: A", response.content.decode())

    def test_workbench_page_lists_docx_first_and_explains_links(self):
        exam = self._exam()
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:test_question_bank", kwargs={"slug": exam.slug}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertLess(html.index("template-download__btn--docx"), html.index("template-download__btn--txt"))
        self.assertIn("page-header-link__hint", html)
        self.assertIn("Kafedranın qəbul olunmuş sual bankından", html)
