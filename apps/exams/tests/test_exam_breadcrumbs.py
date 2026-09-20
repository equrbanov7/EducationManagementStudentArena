"""Breadcrumb zənciri + nəticələr filtri (sahib 2026-09-21).

* Detal / nəticələr / statistika / sual bankı / toplu əlavə / canlı nəticələr —
  hamısı `exam_crumbs` render edir: kabinet bölməsi → imtahan → cari.
* `?from_section=` etibarlı bölməyə görə ilk kramb dəyişir; etibarsız → «İmtahanlarım».
* Nəticələr səhifəsində iç-içə form və «Tətbiq et» düyməsi YOXDUR; qrupa ikinci
  şans forması ayrıcadır; nəticə kartı skeleton hədəfidir.
"""

from django.urls import reverse

from apps.exams.views.shared.breadcrumbs import exam_breadcrumbs

from .test_w4_wizard_units import _login, _UnitFixture


class BreadcrumbHelperTest(_UnitFixture):
    def test_chain_and_section_fallback(self):
        from django.test import RequestFactory

        exam = self._exam()
        request = RequestFactory().get("/", {"from_section": "courses"})
        crumbs = exam_breadcrumbs(request, exam, current="Nəticələr", navigation_query="a=1")
        self.assertEqual([c["label"] for c in crumbs][1:], [exam.title, "Nəticələr"])
        self.assertIn("section=courses", crumbs[0]["url"])
        self.assertTrue(crumbs[1]["url"].endswith("?a=1"))
        self.assertEqual(crumbs[-1]["url"], "")
        request = RequestFactory().get("/", {"from_section": "hacked"})
        self.assertIn("section=my-exams", exam_breadcrumbs(request, exam)[0]["url"])


class BreadcrumbPagesTest(_UnitFixture):
    def test_all_exam_pages_render_the_chain(self):
        exam = self._exam()
        client = _login(self.teacher, self.org)
        pages = (
            reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
            reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}),
            reverse("exams:teacher_exam_statistics", kwargs={"slug": exam.slug}),
            reverse("exams:teacher_questions_bank", kwargs={"slug": exam.slug}),
            reverse("exams:test_question_bank", kwargs={"slug": exam.slug}),
            reverse("liveExam:teacher_live_results", kwargs={"slug": exam.slug}),
        )
        for url in pages:
            with self.subTest(url=url):
                response = client.get(url + "?from_section=my-exams")
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assertIn('class="ems-crumbs"', html)
                self.assertIn(exam.title, html)
                self.assertIn("section=my-exams", html)


class ResultsFilterLayoutTest(_UnitFixture):
    def test_results_page_has_auto_filters_without_apply_button_or_nested_form(self):
        exam = self._exam()
        exam.allowed_units.add(self.group)
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn("action_apply_filter", html)
        self.assertNotIn('id="loadingOverlay"', html)
        self.assertIn("data-results-skeleton-target", html)
        self.assertIn("ter-grant-card", html)
        # İç-içə form yoxdur: filtr formasının bağlanışı grant formasından ƏVVƏL gəlir.
        filters_form = html.index('id="resultsFiltersForm"')
        filters_close = html.index("</form>", filters_form)
        grant_form = html.index("ter-group-grant-form")
        self.assertLess(filters_close, grant_form)


class BackButtonNeverSticksTest(_UnitFixture):
    """«Geri» həmişə əvvəlki krambdır — referer və imtahan-daxili `return_to` ilişməsi yoxdur."""

    def test_detail_back_ignores_self_referer_and_internal_return_to(self):
        exam = self._exam()
        client = _login(self.teacher, self.org)
        detail = reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug})
        response = client.get(detail, HTTP_REFERER=f"http://testserver{detail}")
        self.assertIn("section=my-exams", response.context["profile_return_url"])
        self.assertNotEqual(response.context["profile_return_url"].split("?")[0], detail)
        results = reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug})
        response = client.get(detail, {"return_to": results})
        self.assertIn("section=my-exams", response.context["profile_return_url"])
        # Kabinetdən kənar, imtahan olmayan səhifə isə hörmətlə saxlanır.
        response = client.get(detail, {"return_to": "/accounts/profile/?section=courses"})
        self.assertEqual(response.context["profile_return_url"], "/accounts/profile/?section=courses")

    def test_results_back_is_exam_detail_even_after_filter_reloads(self):
        exam = self._exam()
        client = _login(self.teacher, self.org)
        results = reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug})
        detail = reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug})
        response = client.get(
            results, {"status": "submitted", "return_to": results}, HTTP_REFERER=f"http://testserver{results}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["profile_return_url"].startswith(detail))
        html = response.content.decode()
        self.assertIn(f'href="{detail}?', html.split('class="ter-back-btn"')[0][-400:])
