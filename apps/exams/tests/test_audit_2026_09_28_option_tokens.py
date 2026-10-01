"""Audit 2026-09-28 EX28-01 (P0) — variant id-ləri düzgün cavabı açmamalıdır.

Əvvəl: tələbə formunda ``value="{{ opt.id }}"`` idi; id-lər ardıcıl və müəllif
sırası ilə (A→E) yaradılırdı, END_QUESTION-da isə düzgün cavab birinci
variantdır — ən kiçik ``value`` 8/8 sualda düzgün cavab idi. İndi:

* tələbə attempt-ə bağlı HMAC tokeni görür, server onu geri xəritələyir;
* hər yaradılma yolu variantları təsadüfi sıra ilə yaradır və A..E yenidən
  hərfləyir (id sırası = hərf sırası, düzgün cavab təsadüfi hərfdə).
"""

import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.language_variants import create_questions_for_variant
from apps.exams.services.option_order import relabel_options_by_creation_order
from apps.exams.services.option_tokens import option_ids_from_tokens, option_token
from apps.exams.services.question_delivery import safe_delivered_question
from apps.exams.tests.option_token_utils import option_value
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    PASSWORD,
    _make_people,
    _make_quiz,
    _student_client,
)
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org

User = get_user_model()

_INPUT_RE = re.compile(r'<input type="(?:radio|checkbox)"\s+name="q_(\d+)"\s+value="([^"]*)"', re.S)
_QUESTION_COUNT = 8


def _end_question_text(count):
    blocks = []
    for index in range(1, count + 1):
        blocks.append(
            "\n".join(
                [
                    f"{index}. Import sualı {index}?",
                    f"Düzgün cavab {index}",
                    f"Səhv cavab {index}",
                    f"Digər cavab {index}",
                    f"Alternativ cavab {index}",
                    f"Əlavə cavab {index}",
                    "END_QUESTION",
                ]
            )
        )
    return "\n\n".join(blocks)


def _rendered_values(html):
    values = {}
    for question_id, value in _INPUT_RE.findall(html):
        values.setdefault(int(question_id), []).append(value)
    return values


@override_settings(CACHES=LOCMEM_CACHE)
class EndQuestionImportOptionTokenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("ex2801")
        cls.student2 = User.objects.create_user("ex2801_student2", "ex2801_student2@test.az", PASSWORD)
        _assign_user_to_org(cls.student2, cls.org, ProfileRole.STUDENT)
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=0, title="EX28-01 import")

    def _import_end_questions(self):
        client = Client()
        _login_with_org(client, self.teacher, self.org)
        with patch("apps.exams.services.difficulty.schedule_ai_question_difficulty_warmup"):
            response = client.post(
                reverse("exams:test_question_bank", args=[self.exam.slug]),
                {
                    "action": "save",
                    "raw_text": _end_question_text(_QUESTION_COUNT),
                    "random_question_count": str(_QUESTION_COUNT),
                    "default_points": "1",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.exam.questions.count(), _QUESTION_COUNT)

    def _open(self, user):
        client = _student_client(user.username, self.org)
        client.post(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        attempt = ExamAttempt.objects.get(exam=self.exam, user=user)
        take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        response = client.get(take_url)
        self.assertEqual(response.status_code, 200)
        return client, attempt, take_url, _rendered_values(response.content.decode())

    def test_import_then_take_exam_values_do_not_reveal_correct_option(self):
        self._import_end_questions()
        _client, attempt, _url, values = self._open(self.student)
        self.assertEqual(len(values), _QUESTION_COUNT)

        correct_is_min_value = correct_is_min_id = correct_is_label_a = 0
        for question in self.exam.questions.prefetch_related("options"):
            options = list(question.options.all())
            correct = next(option for option in options if option.is_correct)
            rendered = values[question.id]
            # Xam id heç yerdə göndərilmir; dəyərlər attempt tokenləridir.
            self.assertTrue(set(rendered).isdisjoint({str(option.id) for option in options}))
            self.assertEqual(set(rendered), {option_token(attempt.id, option.id) for option in options})
            for value in rendered:
                self.assertRegex(value, r"^[0-9a-f]{16}$")
            # Müəllim UI-si ardıcıl qalır: id sırası = A..E.
            self.assertEqual([option.label for option in sorted(options, key=lambda o: o.id)], list("ABCDE"))
            self.assertEqual(correct.text, f"Düzgün cavab {question.text.split()[-1].rstrip('?')}")

            correct_is_min_value += min(rendered) == option_token(attempt.id, correct.id)
            correct_is_min_id += min(option.id for option in options) == correct.id
            correct_is_label_a += correct.label == "A"

        # Təsadüfi halda hamısının üst-üstə düşmə ehtimalı (1/5)^8 ≈ 2.6e-6.
        self.assertLess(correct_is_min_value, _QUESTION_COUNT)
        self.assertLess(correct_is_min_id, _QUESTION_COUNT)
        self.assertLess(correct_is_label_a, _QUESTION_COUNT)

    def test_tokens_differ_between_attempts(self):
        self._import_end_questions()
        _c1, _a1, _u1, first = self._open(self.student)
        _c2, _a2, _u2, second = self._open(self.student2)
        for question_id, tokens in first.items():
            self.assertTrue(set(tokens).isdisjoint(second[question_id]))


@override_settings(CACHES=LOCMEM_CACHE)
class OptionTokenSubmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("ex2801s")
        cls.other = User.objects.create_user("ex2801s_other", "ex2801s_other@test.az", PASSWORD)
        _assign_user_to_org(cls.other, cls.org, ProfileRole.STUDENT)
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=2, title="EX28-01 submit")
        cls.single = cls.exam.questions.get(order=1)
        cls.multi = cls.exam.questions.get(order=2)
        ExamQuestion.objects.filter(pk=cls.multi.pk).update(answer_mode="multiple")
        cls.multi.refresh_from_db()
        ExamQuestionOption.objects.create(question=cls.multi, label="C", text="ikinci düzgün", is_correct=True)

    def _open(self, user=None):
        user = user or self.student
        client = _student_client(user.username, self.org)
        client.post(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        attempt = ExamAttempt.objects.get(exam=self.exam, user=user)
        take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        self.assertEqual(client.get(take_url).status_code, 200)
        return client, attempt, take_url

    def _selected(self, attempt, question):
        answer = ExamAnswer.objects.get(attempt=attempt, question=question)
        return set(answer.selected_options.values_list("id", flat=True)), answer

    def test_finish_with_tokens_scores_single_and_multiple_choice(self):
        client, attempt, take_url = self._open()
        single_correct = self.single.options.get(is_correct=True)
        multi_correct = list(self.multi.options.filter(is_correct=True))
        response = client.post(
            take_url,
            {
                "submit_action": "finish",
                f"q_{self.single.id}": option_value(attempt, single_correct),
                f"q_present_{self.single.id}": "1",
                f"q_{self.multi.id}": [option_value(attempt, option) for option in multi_correct],
                f"q_present_{self.multi.id}": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_finished)
        self.assertEqual(attempt.correct_count, 2)
        selected, answer = self._selected(attempt, self.single)
        self.assertEqual(selected, {single_correct.id})
        self.assertTrue(answer.is_correct)
        selected, answer = self._selected(attempt, self.multi)
        self.assertEqual(selected, {option.id for option in multi_correct})
        self.assertEqual(answer.selected_option_ids_snapshot, sorted(option.id for option in multi_correct))
        self.assertTrue(answer.is_correct)

    def test_autosave_with_token_saves_and_changes_selection(self):
        client, attempt, take_url = self._open()
        wrong = self.single.options.get(is_correct=False)
        correct = self.single.options.get(is_correct=True)
        for option, expected_correct in ((wrong, False), (correct, True)):
            response = client.post(
                take_url,
                {
                    "submit_action": "autosave",
                    "changed_questions[]": [str(self.single.id)],
                    f"q_{self.single.id}": option_value(attempt, option),
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(response.status_code, 200, response.content[:300])
            selected, answer = self._selected(attempt, self.single)
            self.assertEqual(selected, {option.id})
            self.assertEqual(answer.is_correct, expected_correct)

    def _autosave_raw(self, client, take_url, question, value):
        return client.post(
            take_url,
            {"submit_action": "autosave", "changed_questions[]": [str(question.id)], f"q_{question.id}": value},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_garbage_raw_id_and_foreign_tokens_are_ignored(self):
        client, attempt, take_url = self._open()
        _other_client, other_attempt, _other_url = self._open(self.other)
        wrong = self.single.options.get(is_correct=False)
        correct = self.single.options.get(is_correct=True)
        self.assertEqual(
            self._autosave_raw(client, take_url, self.single, option_value(attempt, wrong)).status_code,
            200,
        )

        for bogus in ("not-a-token", "0" * 16, str(correct.id), option_value(other_attempt, correct), "<script>"):
            response = self._autosave_raw(client, take_url, self.single, bogus)
            self.assertEqual(response.status_code, 200, (bogus, response.content[:300]))
            selected, answer = self._selected(attempt, self.single)
            # Tanınmayan dəyər mövcud seçimi nə dəyişir, nə silir.
            self.assertEqual(selected, {wrong.id}, bogus)
            self.assertFalse(answer.is_correct)

        # Multi: tanınan + saxta qarışığında yalnız tanınan saxlanır.
        multi_correct = self.multi.options.filter(is_correct=True).first()
        response = self._autosave_raw(
            client, take_url, self.multi, [option_value(attempt, multi_correct), "garbage", str(multi_correct.id)]
        )
        self.assertEqual(response.status_code, 200)
        selected, _answer = self._selected(attempt, self.multi)
        self.assertEqual(selected, {multi_correct.id})

    def test_raw_ids_accepted_only_behind_explicit_setting(self):
        client, attempt, take_url = self._open()
        correct = self.single.options.get(is_correct=True)
        with override_settings(EXAM_OPTION_TOKENS_ACCEPT_RAW_IDS=True):
            response = self._autosave_raw(client, take_url, self.single, str(correct.id))
        self.assertEqual(response.status_code, 200)
        selected, _answer = self._selected(attempt, self.single)
        self.assertEqual(selected, {correct.id})

    def test_delivered_question_options_carry_tokens_not_ids(self):
        _client, attempt, _take_url = self._open()
        answer = ExamAnswer.objects.get(attempt=attempt, question=self.single)
        delivered = safe_delivered_question(answer)
        self.assertTrue(delivered.options)
        for option in delivered.options:
            self.assertEqual(option.token, option_token(attempt.id, option.id))
            self.assertNotEqual(option.token, str(option.id))


class OptionTokenUnitTests(TestCase):
    def test_mapping_semantics(self):
        ids = [11, 12, 13]
        self.assertEqual(option_ids_from_tokens(5, ids, []), set())
        self.assertEqual(option_ids_from_tokens(5, ids, [""]), set())
        self.assertIsNone(option_ids_from_tokens(5, ids, ["x"]))
        self.assertIsNone(option_ids_from_tokens(5, ids, ["12"]))
        self.assertEqual(option_ids_from_tokens(5, ids, [option_token(5, 12), "x"]), {12})
        self.assertIsNone(option_ids_from_tokens(6, ids, [option_token(5, 12)]))


class OptionCreationOrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, _student = _make_people("ex2801c")
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=0, title="EX28-01 create")

    def test_language_variant_import_shuffles_and_reletters(self):
        parsed = [
            {
                "text": f"Sual {index}",
                "options": {"A": f"düz {index}", "B": "b", "C": "c", "D": "d", "E": "e"},
                "correct": ["A"],
                "answer_mode": "single",
            }
            for index in range(12)
        ]
        created = create_questions_for_variant(self.exam, "az", parsed)
        correct_labels = []
        for question in created:
            options = list(ExamQuestionOption.objects.filter(question=question).order_by("id"))
            self.assertEqual([option.label for option in options], list("ABCDE"))
            correct = [option for option in options if option.is_correct]
            self.assertEqual([option.text for option in correct], [question.text.replace("Sual", "düz")])
            correct_labels.append(correct[0].label)
        self.assertNotEqual(set(correct_labels), {"A"})

    def test_relabel_after_media_follows_creation_order(self):
        question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Media sualı")
        for label in ("C", "A", "D", "B"):
            ExamQuestionOption.objects.create(
                question=question, label=label, text=label.lower(), is_correct=label == "A"
            )
        self.assertEqual(relabel_options_by_creation_order(ExamQuestionOption, [question.pk]), 4)
        options = list(question.options.order_by("id"))
        self.assertEqual(
            [(option.label, option.text) for option in options], [("A", "c"), ("B", "a"), ("C", "d"), ("D", "b")]
        )
        self.assertTrue(options[1].is_correct)
