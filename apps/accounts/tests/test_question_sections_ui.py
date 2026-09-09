"""«Sual Bankı» və «Sual göndərişləri» kabinet bölmələrinin UI müqaviləsi.

2026-09-09 redizaynı (sahib: «yerini səliqəyə sal … modern UX/UI»): hər iki
ekran ORTAQ `ems_ui` komponentləri üzərində qurulub.  Bu testlər həmin
müqaviləni kilidləyir:

* qabıq tək başlıq verir — bölmənin içində ikinci `<h1>`/`<h2>` YOXDUR
  (dialoq/çekmecə başlıqları istisnadır);
* CSP: bölmə markup-ında inline `style="…"` yoxdur;
* yaratma axını POZULMUR — eyni sahə adları, eyni POST hədəfi, eyni JS
  çəngəlləri (`js-qb-create-card` / `js-qb-create-form`);
* göndərişlərdə KPI kartları status filtridir, filtrlər ortaq paneldədir və
  boş vəziyyət izahlı `_empty.html`-dir.
"""

from __future__ import annotations

import re

from django.urls import reverse

from apps.exams.models import QuestionBank
from apps.exams.tests.test_question_submission import _Base

#: Bölmə panelini bütöv çıxarmaq üçün — testlər YALNIZ panelin içinə baxır
#: (qabıqdakı `<h1 class="profile-title">` bölməyə aid deyil).
_PANEL_RE = r'<section class="profile-section-panel profile-section--%s.*?\n</section>'


def _panel(html: str, section: str) -> str:
    match = re.search(_PANEL_RE % section, html, re.S)
    assert match, f"{section} paneli render olunmayıb"
    return match.group(0)


class QuestionSectionsSharedContractTest(_Base):
    """Hər iki bölmə üçün eyni qaydalar (başlıq · inline üslub)."""

    def _section_html(self, user, section: str) -> str:
        response = self._client_for(user).get(f"{reverse('accounts:profile')}?section={section}")
        self.assertEqual(response.status_code, 200)
        return _panel(response.content.decode(), section)

    def _assert_single_title(self, html: str, section: str):
        self.assertNotIn("<h1", html, f"{section}: bölmə daxilində ikinci <h1> var")
        self.assertNotIn("ems-header__title", html, f"{section}: content header başlığı da yazılıb")
        for match in re.finditer(r"<h2[^>]*>", html):
            self.assertRegex(
                match.group(0),
                r'class="ems-(dialog|drawer)__title"',
                f"{section}: dialoq/çekmecədən kənar <h2> başlıq var",
            )

    def _assert_no_inline_style(self, html: str, section: str):
        self.assertNotIn('style="', html, f"{section}: inline style atributu var (CSP)")
        self.assertNotIn("<style", html, f"{section}: internal <style> bloku var (CSP)")

    def test_question_bank_section_has_one_title_and_no_inline_style(self):
        html = self._section_html(self.exam_center, "question-bank")
        self._assert_single_title(html, "question-bank")
        self._assert_no_inline_style(html, "question-bank")

    def test_question_submissions_section_has_one_title_and_no_inline_style(self):
        self._to_center(self._submission(title="Başlıq testi"))
        html = self._section_html(self.exam_center, "question-submissions")
        self._assert_single_title(html, "question-submissions")
        self._assert_no_inline_style(html, "question-submissions")

    def test_both_sections_use_the_shared_component_layer(self):
        for user, section in ((self.exam_center, "question-bank"), (self.teacher, "question-submissions")):
            html = self._section_html(user, section)
            for marker in ("ems-header__subtitle", "ems-kpis", "data-ems-filters", "ems-tablewrap"):
                self.assertIn(marker, html, f"{section}: {marker} yoxdur — ortaq komponent qatı işlənmir")


class QuestionBankSectionUiTest(_Base):
    def _html(self, user=None) -> str:
        response = self._client_for(user or self.exam_center).get(
            f"{reverse('accounts:profile')}?section=question-bank"
        )
        self.assertEqual(response.status_code, 200)
        return _panel(response.content.decode(), "question-bank")

    def test_create_dialog_keeps_the_form_contract(self):
        """Forma dialoqa köçdü, amma sahə adları / POST hədəfi / çəngəllər eynidir."""
        html = self._html()
        self.assertIn('data-ems-overlay-open="qbCreateDialog"', html)
        self.assertIn("js-qb-create-card", html)
        self.assertIn("js-qb-create-form", html)
        self.assertIn(f'action="{reverse("exams:question_bank_list")}"', html)
        self.assertIn('name="action" value="create_bank"', html)
        for field in ('name="name"', 'name="subject_id"', 'name="exam_kind"', 'name="default_question_type"'):
            self.assertIn(field, html, f"{field} sahəsi itib")
        self.assertIn('name="language"', html)
        # Mərkəz üçün mənbə müəllim sahəsi (əvvəl context-ə çatmırdı).
        self.assertIn('name="source_teacher_id"', html)

    def test_no_bare_native_select_in_the_section(self):
        """Layihə qaydası: hər `<select>` Bootstrap seçici sarğısındadır."""
        html = self._html()
        for match in re.finditer(r"<select[^>]*>", html):
            self.assertIn("bootstrap-single-select__native", match.group(0))
            self.assertIn("data-bootstrap-select", match.group(0))

    def test_list_renders_as_table_with_kpi_and_filters(self):
        QuestionBank.objects.create(
            name="Cədvəl bankı QBX", organization=self.org, created_by=self.exam_center, exam_kind="final"
        )
        html = self._html()
        self.assertIn("Cədvəl bankı QBX", html)
        self.assertIn('name="bank_search"', html)
        self.assertIn('name="bank_kind"', html)
        self.assertIn('name="bank_lang"', html)
        self.assertIn('name="bank_format"', html)
        self.assertIn("ems-table", html)

    def test_language_and_format_filters_narrow_the_list(self):
        QuestionBank.objects.create(
            name="AZ test bankı QBX",
            organization=self.org,
            created_by=self.exam_center,
            language="az",
            default_question_type="test",
        )
        QuestionBank.objects.create(
            name="EN yazılı bankı QBX",
            organization=self.org,
            created_by=self.exam_center,
            language="en",
            default_question_type="written",
        )
        client = self._client_for(self.exam_center)
        response = client.get(f"{reverse('accounts:profile')}?section=question-bank&bank_lang=en")
        self.assertContains(response, "EN yazılı bankı QBX")
        self.assertNotContains(response, "AZ test bankı QBX")
        response = client.get(f"{reverse('accounts:profile')}?section=question-bank&bank_format=test")
        self.assertContains(response, "AZ test bankı QBX")
        self.assertNotContains(response, "EN yazılı bankı QBX")

    def test_empty_state_explains_the_next_step(self):
        html = self._html()
        self.assertIn("ems-state", html)
        self.assertIn("Yeni bank", html)

    def test_standalone_bank_url_still_works(self):
        """`exams:question_bank_list` GET-i kabinet bölməsinə yönləndirir."""
        response = self._client_for(self.exam_center).get(reverse("exams:question_bank_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("section=question-bank", response["Location"])

    def test_create_post_from_the_dialog_still_creates_a_bank(self):
        response = self._client_for(self.exam_center).post(
            reverse("exams:question_bank_list"),
            {
                "action": "create_bank",
                "next": f"{reverse('accounts:profile')}?section=question-bank",
                "name": "Dialoq bankı QBX",
                "subject_id": "",
                "source_teacher_id": "",
                "exam_kind": "final",
                "default_question_type": "test",
                "language": "az",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(QuestionBank.objects.filter(name="Dialoq bankı QBX", exam_kind="final").exists())


class QuestionSubmissionsSectionUiTest(_Base):
    def _html(self, user, query: str = "") -> str:
        response = self._client_for(user).get(f"{reverse('accounts:profile')}?section=question-submissions{query}")
        self.assertEqual(response.status_code, 200)
        return _panel(response.content.decode(), "question-submissions")

    def test_kpi_tiles_are_clickable_status_filters(self):
        self._submission(title="KPI testi")
        html = self._html(self.teacher)
        self.assertIn('data-ems-kpi-filter="all"', html)
        self.assertIn('data-ems-kpi-filter="at_chair"', html)
        self.assertIn('data-ems-kpi-filter="accepted"', html)
        self.assertIn('data-ems-kpi-filter="returned"', html)

    def test_filter_bar_carries_every_reviewer_filter(self):
        self._to_center(self._submission(title="Filtr testi"))
        html = self._html(self.exam_center)
        for name in ("qsub_q", "qsub_status", "qsub_faculty", "qsub_kafedra", "qsub_teacher", "qsub_year", "qsub_lang"):
            self.assertIn(f'name="{name}"', html, f"{name} filtri paneldə yoxdur")
        self.assertIn('data-param-prefix="qsub_"', html)

    def test_rows_render_in_a_table_with_status_badge_and_drawer(self):
        self._to_center(self._submission(title="Cədvəl testi"))
        html = self._html(self.exam_center)
        self.assertIn("Cədvəl testi", html)
        self.assertIn("ems-table", html)
        self.assertIn("ems-badge", html)
        self.assertIn("data-qsub-drawer=", html)
        self.assertIn('id="qsubDrawer"', html)
        self.assertIn('id="qsubDrawerData"', html)

    def test_empty_state_tells_where_submissions_come_from(self):
        html = self._html(self.teacher)
        self.assertIn("ems-state", html)
        self.assertIn("Yeni göndəriş", html)

    def test_status_filter_still_narrows_the_list(self):
        self._submission(title="Gözləyən toplu")
        accepted = self._to_center(self._submission(title="Qəbul olunan toplu"))
        from apps.exams.services.question_submission import accept_submission

        accept_submission(accepted, reviewer=self.exam_center, new_bank_name="Status bankı")
        client = self._client_for(self.teacher)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions&qsub_status=accepted")
        self.assertContains(response, "Qəbul olunan toplu")
        self.assertNotContains(response, "Gözləyən toplu")
