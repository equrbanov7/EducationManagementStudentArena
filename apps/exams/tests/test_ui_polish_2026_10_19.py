"""UI cilası (sahib 2026-10-19): AI sual generatoru, «Suallar bankından seç» modalı.

* AI paneli bütün yerlərdə ORTAQ partial-dan gəlir (workbench «card» + yazılı imtahan bloku «block»
  + JS-in klonladığı <template>): JS çəngəlləri və form sahə adları dəyişməyib, hər panelin
  `data-extract-url`-u var (əvvəl serverdə render olunan bloklarda yox idi), select layihə komponentidir.
* Picker: rəqəm olmayan `bank` 500 vermir; əhatədən kənar bankla əlavə 404; imtahanda artıq olan
  bank sualı «artıq əlavə olunub» (söndürülmüş) göstərilir və təkrar əlavə olunmur; filtr seçimləri
  tərcümə olunur; content sorğuları sual sayından asılı deyil (N+1 yox).
"""

from django.contrib.messages import get_messages
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.accounts.models import ProfileRole
from apps.exams.models import BankQuestion, BankQuestionOption, QuestionBank
from apps.exams.services.question_bank_attach import attach_bank_questions_to_exam
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org

from .test_w4_wizard_units import User, _login, _UnitFixture


class AiGeneratorPanelTests(_UnitFixture):
    def _client(self):
        return _login(self.teacher, self.org)

    def test_test_bank_uses_shared_panel_with_hooks(self):
        exam = self._exam()
        with translation.override("az"):
            html = self._client().get(reverse("exams:test_question_bank", args=[exam.slug])).content.decode()
        self.assertIn("AI ilə test sualı yarat", html)
        self.assertIn('class="aigen aigen--card"', html)
        for hook in (
            "data-ai-question-form",
            "data-ai-question-submit",
            "data-ai-question-status",
            "data-ai-dropzone",
            "data-ai-file-clear",
            'data-ai-target="#testRawEditor"',
            'id="testAiSourceFile"',
            'name="insert_mode"',
            'name="question_count"',
            'name="difficulty"',
            'name="source_file"',
            "bootstrap-single-select--ems",
            reverse("exams:start_text_extraction"),
            reverse("exams:ai_generate_question_bank", args=[exam.slug]),
        ):
            self.assertIn(hook, html, hook)
        self.assertIn("exams/css/ai_generator_panel.css", html)
        # Köhnə, böyük hərfli «FAYL SEÇ» düyməsi və ikinci markup qalmayıb.
        self.assertNotIn("ai-file-picker", html)
        self.assertNotIn("ai-bank-card", html)
        self.assertNotIn("<style", html)

    def test_written_editor_blocks_and_template_share_the_partial(self):
        exam = self._exam(exam_type="written", exam_type_extended="quiz")
        with translation.override("az"):
            html = self._client().get(reverse("exams:create_question_bank", args=[exam.slug])).content.decode()
        self.assertEqual(html.count('class="aigen aigen--block"'), 2)  # defolt blok + <template>
        self.assertIn('id="qbankAiPanelTemplate"', html)
        self.assertIn('id="writtenAiSourceFile1"', html)
        self.assertIn('name="ai_insert_mode_1"', html)
        self.assertIn('id="writtenAiSourceFile__AIUID__"', html)
        self.assertIn('name="ai_insert_mode___AIUID__"', html)
        self.assertEqual(html.count('data-extract-url="%s"' % reverse("exams:start_text_extraction")), 2)
        self.assertIn("AI ilə bu blok üçün sual yarat", html)
        self.assertNotIn("ai-block-panel", html)
        # Bank seçici yazılı redaktorda əlavədən sonra səhifəni yeniləyir (blok mətni serverdən gəlir).
        self.assertIn('data-picker-after="reload"', html)


class BankPickerModalTests(_UnitFixture):
    def _client(self):
        return _login(self.teacher, self.org)

    def _bank(self, **kwargs):
        defaults = {"name": "Riyaziyyat bankı", "organization": self.org, "created_by": self.teacher}
        defaults.update(kwargs)
        return QuestionBank.objects.create(**defaults)

    def _question(self, bank, text, **kwargs):
        defaults = {"question_type": "test", "language": "az"}
        defaults.update(kwargs)
        question = BankQuestion.objects.create(bank=bank, text=text, **defaults)
        for label, correct in (("A", True), ("B", False), ("C", False), ("D", False)):
            BankQuestionOption.objects.create(
                question=question, label=label, text=f"{text}-{label}", is_correct=correct
            )
        return question

    def _url(self, exam):
        return reverse("exams:exam_bank_picker", kwargs={"slug": exam.slug})

    def test_modal_body_has_aligned_toolbar_and_guided_state(self):
        exam = self._exam()
        self._bank()
        with translation.override("az"):
            html = self._client().get(self._url(exam), {"modal": "1"}).content.decode()
        self.assertIn("bankpicker-toolbar", html)
        self.assertEqual(html.count("bootstrap-single-select--ems"), 3)  # bank + dil + çətinlik
        self.assertIn('class="ems-input ems-search__input" data-picker-control="q"', html)
        self.assertIn("Əvvəl bank seçin", html)
        self.assertIn("data-picker-attach disabled", html)
        self.assertNotIn("<style", html)
        self.assertNotIn('style="', html)

    def test_non_numeric_bank_param_does_not_crash(self):
        exam = self._exam()
        response = self._client().get(self._url(exam), {"modal": "1", "content": "1", "bank": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selected_bank"])

    def test_difficulty_choices_are_translated_model_choices(self):
        exam = self._exam()
        response = self._client().get(self._url(exam), {"modal": "1"})
        self.assertEqual(response.context["difficulty_choices"], BankQuestion.DIFFICULTY_CHOICES)

    def test_attached_questions_are_marked_and_excluded_from_select_all_total(self):
        exam = self._exam()
        bank = self._bank()
        first = self._question(bank, "def f(x):\n    return x * 2")
        second = self._question(bank, "2 + 2 = ?")
        attach_bank_questions_to_exam(exam, [first.id], created_by=self.teacher)
        with translation.override("az"):
            response = self._client().get(self._url(exam), {"modal": "1", "content": "1", "bank": bank.id})
        html = response.content.decode()
        self.assertEqual(response.context["attached_count"], 1)
        self.assertEqual(response.context["selectable_count"], 1)
        self.assertIn('data-picker-total="1"', html)
        self.assertIn("Artıq əlavə olunub", html)
        self.assertIn('id="bpq%s" value="%s" data-picker-checkbox' % (first.id, first.id), html)
        self.assertRegex(html, r'id="bpq%s"[^>]*disabled' % first.id)
        self.assertNotRegex(html, r'id="bpq%s"[^>]*disabled' % second.id)
        # Koddakı sətir sonu önizləmədə qalır (CSS pre-wrap göstərir).
        self.assertIn("def f(x):\n    return x * 2", html)

    def test_attach_skips_questions_already_in_exam(self):
        exam = self._exam()
        bank = self._bank()
        first = self._question(bank, "Sual 1")
        second = self._question(bank, "Sual 2")
        attach_bank_questions_to_exam(exam, [first.id], created_by=self.teacher)
        response = self._client().post(
            self._url(exam),
            {"modal": "1", "action": "attach", "bank": bank.id, "question_ids": [first.id, second.id]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual((payload["count"], payload["skipped"]), (1, 1))
        self.assertEqual(exam.questions.filter(source_bank_question=first).count(), 1)
        self.assertEqual(exam.questions.count(), 2)
        # Modal səhifədə qalırsa (stay) server mesajı flash etmir — JS toast göstərir.
        self.assertEqual(list(get_messages(response.wsgi_request)), [])

    def test_select_all_mode_skips_attached_and_excluded(self):
        exam = self._exam()
        bank = self._bank()
        questions = [self._question(bank, f"Toplu {i}") for i in range(4)]
        attach_bank_questions_to_exam(exam, [questions[0].id], created_by=self.teacher)
        response = self._client().post(
            self._url(exam),
            {"modal": "1", "action": "attach", "bank": bank.id, "select_all": "1", "excluded_ids": [questions[1].id]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.json()["count"], 2)
        self.assertEqual(exam.questions.count(), 3)

    def test_all_duplicates_returns_warning_message(self):
        exam = self._exam()
        bank = self._bank()
        question = self._question(bank, "Təkrar")
        attach_bank_questions_to_exam(exam, [question.id], created_by=self.teacher)
        with translation.override("az"):
            response = self._client().post(
                self._url(exam),
                {"modal": "1", "action": "attach", "bank": bank.id, "question_ids": [question.id], "after": "reload"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        payload = response.json()
        self.assertEqual(payload["count"], 0)
        self.assertIn("artıq imtahanda var", payload["message"])
        # after=reload → mesaj növbəti səhifədə toast kimi görünsün.
        flashed = [(m.level_tag, str(m)) for m in get_messages(response.wsgi_request)]
        self.assertEqual(flashed, [("warning", payload["message"])])

    def test_attach_with_out_of_scope_bank_is_404(self):
        exam = self._exam()
        foreign = QuestionBank.objects.create(name="Yad bank", organization=self.org_b, created_by=self.owner_b)
        question = self._question(foreign, "Yad sual")
        response = self._client().post(
            self._url(exam),
            {"modal": "1", "action": "attach", "bank": foreign.id, "question_ids": [question.id]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(exam.questions.count(), 0)

    def test_incompatible_bank_type_is_404_on_attach(self):
        exam = self._exam()  # test imtahanı
        written_bank = self._bank(name="Yazılı bank", default_question_type="written")
        question = self._question(written_bank, "Esse", question_type="written")
        response = self._client().post(
            self._url(exam),
            {"modal": "1", "action": "attach", "bank": written_bank.id, "question_ids": [question.id]},
        )
        self.assertEqual(response.status_code, 404)

    def test_missing_bank_on_attach_stays_400(self):
        exam = self._exam()
        response = self._client().post(
            self._url(exam), {"modal": "1", "action": "attach", "bank": ""}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_other_teachers_exam_is_404(self):
        other = User.objects.create_user("uip_teacher2", "uip_teacher2@test.az", PASSWORD)
        _assign_user_to_org(other, self.org, ProfileRole.TEACHER, "teacher")
        exam = self._exam()
        response = _login(other, self.org).get(self._url(exam), {"modal": "1"})
        self.assertEqual(response.status_code, 404)

    def test_items_page_has_load_more_sentinel(self):
        exam = self._exam()
        bank = self._bank()
        for i in range(41):  # _PICKER_PAGE_SIZE = 40
            BankQuestion.objects.create(bank=bank, text=f"Q{i}", question_type="test", language="az")
        html = self._client().get(self._url(exam), {"modal": "1", "content": "1", "bank": bank.id}).content.decode()
        self.assertIn("data-picker-sentinel", html)
        self.assertIn("data-picker-more", html)
        self.assertIn('data-next-page="2"', html)
        page2 = self._client().get(self._url(exam), {"modal": "1", "items": "1", "bank": bank.id, "page": 2})
        self.assertEqual(page2.content.decode().count("data-picker-checkbox"), 1)
        self.assertNotIn("data-picker-sentinel", page2.content.decode())

    def test_filtered_empty_state_offers_reset(self):
        exam = self._exam()
        bank = self._bank()
        self._question(bank, "Mövcud sual")
        with translation.override("az"):
            html = (
                self._client()
                .get(self._url(exam), {"modal": "1", "content": "1", "bank": bank.id, "q": "yoxdur-xyz"})
                .content.decode()
            )
        self.assertIn("Filtrlərə uyğun sual tapılmadı", html)
        self.assertIn("data-picker-reset", html)

    def test_content_query_count_does_not_grow_with_questions(self):
        exam = self._exam()
        bank = self._bank()
        self._question(bank, "Başlanğıc")

        def _count():
            client = self._client()
            params = {"modal": "1", "content": "1", "bank": bank.id}
            client.get(self._url(exam), params)  # sessiya/kontekst keşləri isinsin
            with CaptureQueriesContext(connection) as ctx:
                client.get(self._url(exam), params)
            return len(ctx.captured_queries)

        small = _count()
        for i in range(6):
            self._question(bank, f"Əlavə {i}")
        self.assertEqual(_count(), small)
