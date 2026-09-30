"""Sorğu qurucusu (2026-09-30) — sual redaktoru: növlər, seçimlər, sıra, bölmələr, XHR, kilid."""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.surveys.constants import QuestionKind, SurveyKind
from apps.surveys.models import SurveyPage, SurveyParticipation, SurveyQuestion
from apps.surveys.services import questions as editor
from apps.surveys.services import survey_builder as builder
from core.rls import bypass_rls

from .builder_world import make_survey, manager, questions_of
from .factories import build_world, client_for


class QuestionEditorTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svbq", students=1)
        cls.qc_head = manager(cls.w)

    def setUp(self):
        self.survey = make_survey(self.w, publish=False)
        self.client = client_for(self.w["org"], self.qc_head)
        self.url = reverse("surveys:builder_questions", args=[self.survey.pk])

    def _xhr(self, **data):
        return self.client.post(self.url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json")

    def test_every_generic_kind_is_stored_with_options(self):
        rows = {q.kind: q for q in questions_of(self.survey)}
        self.assertEqual(set(rows), {k for k in QuestionKind.values if k != QuestionKind.SCALE10})
        choices = rows[QuestionKind.SINGLE].options["choices"]
        self.assertEqual([c["label"] for c in choices], ["Mərkəzi", "Fakültə", "Onlayn"])
        self.assertEqual(len({c["key"] for c in choices}), 3)
        self.assertEqual((rows[QuestionKind.MULTI].options["min"], rows[QuestionKind.MULTI].options["max"]), (1, 2))

    def test_xhr_add_returns_rerendered_editor(self):
        response = self._xhr(op="add_question", kind="single", text="Yeni seçim sualı")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("data-svb-editor", payload["html"])
        self.assertIn("Yeni seçim sualı", payload["html"])
        question = SurveyQuestion.objects.get(template=self.survey.template, text="Yeni seçim sualı")
        self.assertEqual(len(question.options["choices"]), 2)  # nümunə variantlar

    def test_invalid_input_is_reported_not_written(self):
        count = len(questions_of(self.survey))
        for data in (
            {"op": "add_question", "kind": "scale10", "text": "Ümumi sorğuda 1–10"},
            {"op": "add_question", "kind": "likert5", "text": ""},
        ):
            response = self._xhr(**data)
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.json()["ok"])
        single = next(q for q in questions_of(self.survey) if q.kind == QuestionKind.SINGLE)
        response = self._xhr(
            op="update_question", question=str(single.pk), kind="single", text="x", choices_text="A\nA"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(questions_of(self.survey)), count)

    def test_multi_min_cannot_exceed_max(self):
        multi = next(q for q in questions_of(self.survey) if q.kind == QuestionKind.MULTI)
        response = self._xhr(
            op="update_question",
            question=str(multi.pk),
            kind="multi",
            text=multi.text,
            choices_text="A\nB\nC",
            min_choices="3",
            max_choices="2",
        )
        self.assertEqual(response.status_code, 400)

    def test_reorder_and_move(self):
        page = SurveyPage.objects.get(template=self.survey.template)
        ids = [str(q.pk) for q in questions_of(self.survey)]
        response = self._xhr(op="reorder", group=str(page.pk), order=list(reversed(ids)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([str(q.pk) for q in questions_of(self.survey)], list(reversed(ids)))
        stale = self._xhr(op="reorder", group=str(page.pk), order=ids[:2])
        self.assertEqual(stale.status_code, 400)
        first = questions_of(self.survey)[0]
        self._xhr(op="move_question", question=str(first.pk), direction="down")
        self.assertEqual(questions_of(self.survey)[1].pk, first.pk)

    def test_pages_add_rename_move_delete_keep_questions(self):
        self._xhr(op="add_page", title="İkinci bölmə")
        pages = list(SurveyPage.objects.filter(template=self.survey.template).order_by("order"))
        self.assertEqual(len(pages), 2)
        question = questions_of(self.survey)[0]
        self._xhr(
            op="update_question",
            question=str(question.pk),
            kind=question.kind,
            text=question.text,
            required="1",
            page=str(pages[1].pk),
            label_0="Heç",
        )
        question.refresh_from_db()
        self.assertEqual(question.page_id, pages[1].pk)
        self._xhr(op="update_page", page_id=str(pages[1].pk), title="Təkliflər", description="İzah")
        self._xhr(op="move_page", page_id=str(pages[1].pk), direction="up")
        self.assertEqual(
            SurveyPage.objects.filter(template=self.survey.template).order_by("order").first().title, "Təkliflər"
        )
        total = len(questions_of(self.survey))
        self._xhr(op="delete_page", page_id=str(pages[1].pk))
        self.assertEqual(SurveyPage.objects.filter(template=self.survey.template).count(), 1)
        self.assertEqual(len(questions_of(self.survey)), total)
        last = SurveyPage.objects.get(template=self.survey.template)
        self.assertEqual(self._xhr(op="delete_page", page_id=str(last.pk)).status_code, 400)

    def test_non_xhr_post_redirects_back_to_editor(self):
        response = self.client.post(self.url, {"op": "add_question", "kind": "yesno", "text": "Bəli/xeyr?"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("tab=questions", response["Location"])


class LockedSurveyTest(TestCase):
    """Cavab gələndən sonra struktur kilidlidir, yalnız yazı səhvi düzəlişi (versiyalı)."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svblock", students=1)

    def setUp(self):
        self.survey = make_survey(self.w)
        with bypass_rls():
            SurveyParticipation.objects.create(
                organization=self.w["org"],
                survey=self.survey,
                user=self.w["students"][0],
                completed_on=timezone.localdate(),
            )
        self.questions = questions_of(self.survey)

    def test_structure_is_locked(self):
        with bypass_rls():
            self.assertTrue(editor.is_locked(self.survey))
            with self.assertRaises(builder.BuilderError):
                editor.add_question(self.survey, {"kind": "likert5", "text": "Yeni"})
            with self.assertRaises(builder.BuilderError):
                editor.delete_question(self.survey, self.questions[0])
            with self.assertRaises(builder.BuilderError):
                editor.move(self.survey, self.questions[0], "down")
            with self.assertRaises(builder.BuilderError):
                editor.add_page(self.survey, {"title": "x"})

    def test_typo_fix_is_versioned_but_meaning_change_is_rejected(self):
        question = next(q for q in self.questions if q.kind == QuestionKind.LIKERT5)
        with bypass_rls():
            editor.update_question(
                self.survey, question, {"text": "Xidmətdən razıyam.", "kind": "text", "required": ""}
            )
        question.refresh_from_db()
        self.assertEqual(question.text, "Xidmətdən razıyam.")
        self.assertEqual(question.kind, QuestionKind.LIKERT5)  # struktur sahələri nəzərə alınmır
        self.assertTrue(question.required)
        self.assertEqual(question.history[-1]["text"], "Xidmətdən razıyam")
        with bypass_rls(), self.assertRaises(builder.BuilderError):
            editor.update_question(self.survey, question, {"text": "Yeməkxananın qiymətləri baha deyil"})

    def test_option_count_is_locked_labels_allow_typos(self):
        single = next(q for q in self.questions if q.kind == QuestionKind.SINGLE)
        keys = [c["key"] for c in single.options["choices"]]
        with bypass_rls():
            with self.assertRaises(builder.BuilderError):
                editor.update_question(self.survey, single, {"text": single.text, "choices_text": "Mərkəzi\nFakültə"})
            editor.update_question(
                self.survey, single, {"text": single.text, "choices_text": "Mərkəzi\nFakülte\nOnlayn"}
            )
        single.refresh_from_db()
        self.assertEqual([c["key"] for c in single.options["choices"]], keys)  # açarlar sabit
        self.assertEqual(single.options["choices"][1]["label"], "Fakülte")


class TeacherEvaluationKindsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svbtek", students=1)

    def test_only_scored_and_text_kinds_and_fixed_sections(self):
        with bypass_rls():
            survey = builder.create_survey(self.w["org"], kind=SurveyKind.TEACHER_EVALUATION, title="Dəst")
            with self.assertRaises(builder.BuilderError):
                editor.add_question(survey, {"kind": "single", "text": "Seçim"})
            question = editor.add_question(
                survey, {"kind": "likert5", "text": "Yeni bənd", "section": "general", "in_index": "1"}
            )
            with self.assertRaises(builder.BuilderError):
                editor.add_page(survey, {"title": "x"})
        self.assertEqual((question.section, question.in_index, question.page_id), ("general", True, None))
