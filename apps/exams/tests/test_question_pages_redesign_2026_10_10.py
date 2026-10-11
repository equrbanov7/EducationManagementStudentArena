"""Sual formu modalı + «Sual bankı» səhifələrinin redizaynı (sahib 2026-10-10).

* «Yeni sual əlavə et» modalı: bölmələr (Sual · Media · Parametrlər · Cavablar), tərcümə olunan
  fayl zonası (native «Choose File» yox), iki nöqtəsiz etiketlər; CSS üç fayla bölünüb.
* «Sual bankı»: TƏK əsas əməl (split), qısa KPI-lar, keyfiyyət süzgəci tək çip zolağında,
  bir sıralı alət zolağı + «Yüklə ▾», təhlükəli əməllər səhifənin sonunda (yazılı təsdiq).
* Kitabxana bankı eyni partialı işlədir: redaktə Bootstrap dialoqu, «Bankı sil» təhlükə zonasında.
* POST müqaviləsi (bulk_action=…) dəyişməyib.
"""

from django.urls import reverse
from django.utils import translation

from apps.exams.models import BankQuestion, ExamQuestion, ExamQuestionOption, QuestionBank

from .test_w4_wizard_units import _login, _UnitFixture

FORM_CSS = ("exams/css/question_form.css", "exams/css/question_form_media.css", "exams/css/question_form_answers.css")
DEAD_CSS = ("question_form_modal.css", "question_form_modal_theme.css", "add_exam_question.css")


class _Base(_UnitFixture):
    def _client(self):
        return _login(self.teacher, self.org)

    def _questions(self, exam, count=2):
        for index in range(count):
            question = ExamQuestion.objects.create(exam=exam, order=index + 1, text=f"Sual {index + 1}")
            ExamQuestionOption.objects.create(question=question, label="A", text=f"düz-{index}", is_correct=True)
            ExamQuestionOption.objects.create(question=question, label="B", text=f"səhv-{index}", is_correct=False)

    def assertNoInlineAssets(self, html):
        self.assertNotIn("<style", html)
        self.assertNotIn(" onclick=", html)
        # Yeni style="" atributu yoxdur (səhifə gövdəsində; base layout bu testin mövzusu deyil).
        body = html.split('class="etp-page', 1)[-1].split('id="questionFormModal"', 1)[0]
        self.assertNotIn(' style="', body)

    def assertFormCss(self, html):
        for path in FORM_CSS:
            self.assertIn(path, html)
        for path in DEAD_CSS:
            self.assertNotIn(path, html)


class QuestionFormModalTests(_Base):
    def test_modal_form_has_sections_and_translated_file_picker(self):
        exam = self._exam()
        with translation.override("az"):
            response = self._client().get(
                reverse("exams:add_exam_question", kwargs={"slug": exam.slug}),
                {"modal": "1"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for section in ("qfSecQuestion", "qfSecMedia", "qfSecSettings", "qfSecAnswers"):
            self.assertIn(f'id="{section}"', html)
        self.assertIn('class="qf qf--modal js-exam-question-form-root"', html)
        self.assertIn('data-qf-drop="image"', html)
        self.assertIn('data-qf-drop="video"', html)
        self.assertIn("Şəkil seçin", html)
        self.assertIn("ən çox 10 MB", html)
        # Sahə müqaviləsi dəyişməyib: fayl adları + ClearableFileInput, variant sahələri.
        self.assertIn('name="image"', html)
        self.assertIn('name="video"', html)
        self.assertIn('name="option1_text"', html)
        self.assertIn('name="modal" value="1"', html)
        # Cümlə registrli etiketlər — iki nöqtə ilə bitən etiket yoxdur.
        self.assertNotIn(":</label>", html)
        self.assertNotIn("question-form-modal-actions", html)
        self.assertNoInlineAssets(html)

    def test_standalone_fallback_page_uses_shell_and_split_css(self):
        """GET modalı açır (detala yönləndirir); ehtiyat səhifə JS-siz xətalı göndərişdə görünür."""
        exam = self._exam()
        url = reverse("exams:add_exam_question", kwargs={"slug": exam.slug})
        self.assertEqual(self._client().get(url).status_code, 302)
        response = self._client().post(url, {"text": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "exams/teacher/add_exam_question.html")
        html = response.content.decode()
        self.assertIn('class="qf-error" role="alert"', html)
        self.assertIn('class="etp-back"', html)
        self.assertIn('class="ems-header__title"', html)
        self.assertIn("qf--page", html)
        self.assertIn("exams/js/question_form.js", html)
        self.assertFormCss(html)
        self.assertNoInlineAssets(html)

    def test_edit_modal_renders_existing_question(self):
        exam = self._exam()
        self._questions(exam, count=1)
        question = exam.questions.get()
        response = self._client().get(
            reverse("exams:edit_exam_question", kwargs={"slug": exam.slug, "question_id": question.id}),
            {"modal": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Sual 1", html)
        self.assertIn('value="düz-0"', html)
        self.assertIn("data-option-card-template", html)

    def test_exam_detail_hosts_the_modal_shell(self):
        exam = self._exam()
        response = self._client().get(reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('class="modal fade qf-modal" id="questionFormModal"', html)
        self.assertFormCss(html)


class ExamQuestionBankPageTests(_Base):
    def _get(self, exam, **params):
        with translation.override("az"):
            return self._client().get(reverse("exams:teacher_questions_bank", kwargs={"slug": exam.slug}), params)

    def test_header_has_one_primary_action_and_no_destructive_button(self):
        exam = self._exam(title="İnformatika final")
        self._questions(exam)
        response = self._get(exam)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('class="ems-crumbs"', html)
        actions = html.split('class="ems-header__actions"')[1].split("</header>")[0]
        self.assertEqual(actions.count("ems-btn--primary"), 2)  # split: əsas hissə + açılan ox
        self.assertIn("etp-split", actions)
        self.assertIn(reverse("exams:test_question_bank", kwargs={"slug": exam.slug}), actions)
        self.assertNotIn("js-delete-all-questions", actions)
        self.assertNoInlineAssets(html)
        self.assertFormCss(html)

    def test_short_kpis_single_quality_filter_and_toolbar_row(self):
        exam = self._exam()
        self._questions(exam)
        html = self._get(exam).content.decode()
        kpis = html.split('class="etp-kpis eqb-kpis"')[1].split("</section>")[0]
        for label in ("Cəmi", "Aktiv", "Deaktiv"):
            self.assertIn(f'<span class="etp-kpi__label">{label}</span>', kpis)
        self.assertNotIn("flag=", kpis)  # KPI-lar süzgəc deyil — süzgəc yalnız çip zolağıdır
        self.assertEqual(html.count("flag=has-error"), 1)
        self.assertNotIn("qb-stat-card--clickable", html)
        toolbar = html.split('id="questionSearchForm"')[1].split("</form>")[0]
        for name in ('name="q"', 'name="status"', 'name="language"', 'name="sort"'):
            self.assertIn(name, toolbar)
        self.assertEqual(toolbar.count("bootstrap-single-select--ems"), 3)
        self.assertIn(reverse("exams:exam_questions_word_export", kwargs={"slug": exam.slug}), toolbar)
        self.assertIn("export=report", toolbar)

    def test_danger_zone_typed_confirmation_and_js_hooks(self):
        exam = self._exam(title="İnformatika final")
        self._questions(exam, count=3)
        html = self._get(exam).content.decode()
        self.assertIn('data-qm-context="exam"', html)  # guarded_submit.js qarmağı
        self.assertIn("js-delete-all-questions", html.split('id="qmDangerTitle"')[1])
        self.assertIn('data-count="3"', html)
        self.assertIn('data-qb-typed-form data-phrase="İnformatika final"', html)
        self.assertIn("data-qb-typed-input", html)
        self.assertIn("data-qb-typed-ok disabled", html)
        for form_id in ("bulkForm", "singleDeleteForm", "singleQuestionActionForm", "questionBankDeleteAllForm"):
            self.assertIn(f'id="{form_id}"', html)
        self.assertNotIn("qbConfirmModal", html)
        self.assertIn("exams/js/teacher_questions_bank/guarded_submit.js", html)
        self.assertIn("exams/js/teacher_questions_bank.js", html)

    def test_language_filter_offers_language_delete_in_danger_zone(self):
        exam = self._exam()
        self._questions(exam)
        html = self._get(exam, language="az").content.decode()
        danger = html.split('id="qmDangerTitle"')[1]
        self.assertIn('data-language="az"', danger)
        self.assertIn('id="questionLangDeleteForm"', html)

    def test_delete_all_post_contract_unchanged(self):
        exam = self._exam(is_active=False)
        self._questions(exam)
        url = reverse("exams:teacher_questions_bank", kwargs={"slug": exam.slug})
        response = self._client().post(url, {"bulk_action": "delete_all"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(exam.questions.exists())

    def test_bulk_deactivate_post_contract_unchanged(self):
        exam = self._exam(is_active=False)
        self._questions(exam)
        first = exam.questions.order_by("order").first()
        url = reverse("exams:teacher_questions_bank", kwargs={"slug": exam.slug})
        response = self._client().post(url, {"bulk_action": "deactivate", "selected_question_ids": [first.id]})
        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        self.assertFalse(first.is_active)


class LibraryBankDetailPageTests(_Base):
    def _bank(self, **kwargs):
        defaults = {"name": "Riyaziyyat bankı", "organization": self.org, "created_by": self.teacher}
        defaults.update(kwargs)
        bank = QuestionBank.objects.create(**defaults)
        BankQuestion.objects.create(bank=bank, text="2 + 2 = ?", question_type="test", language="az")
        return bank

    def test_owner_gets_dialog_edit_and_bank_delete_in_danger_zone(self):
        bank = self._bank()
        with translation.override("az"):
            response = self._client().get(reverse("exams:question_bank_detail", kwargs={"bank_id": bank.id}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-qm-context="bank"', html)
        self.assertIn('class="modal fade etp-modal" id="bankEditModal"', html)
        self.assertIn('data-bs-target="#bankEditModal"', html)
        self.assertIn(reverse("exams:question_bank_update", kwargs={"bank_id": bank.id}), html)
        danger = html.split('id="qmDangerTitle"')[1]
        self.assertIn("js-delete-bank", danger)
        self.assertIn('id="bankDeleteForm"', html)
        self.assertIn("exams/js/bankManagement.js", html)
        self.assertNotIn("js-delete-all-questions", html)
        self.assertNotIn("qbTypedConfirmModal", html)
        self.assertNoInlineAssets(html)
        self.assertFormCss(html)

    def test_shared_bank_viewer_gets_no_owner_actions(self):
        bank = self._bank(created_by=self.owner, is_shared=True)
        response = self._client().get(reverse("exams:question_bank_detail", kwargs={"bank_id": bank.id}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn('id="bankEditModal"', html)
        self.assertNotIn("js-delete-bank", html)
        self.assertIn("2 + 2 = ?", html)
