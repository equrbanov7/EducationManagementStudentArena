"""LX-SEC — yazılı cavab (typed answer) və nəticə ixracı (Audit 2026-09-28, əlavə əhatə).

* nəticə səhifəsi / JSON / CSV ixracı yazılı mətni təhlükəsiz göstərir:
  bidi / nəzarət simvolları atılır, CSV-də ``= + - @ \\t`` prefiksləri neytrallaşır;
* ixrac nəticə səhifəsi ilə eyni giriş qaydasındadır (LXS-01) və yalnız GET-dir;
* reveal-dən ƏVVƏL heç bir HTTP endpoint (state, api/v1 state, cavab POST-u,
  oyunçu səhifələri) başqasının mətnini və ya qəbul olunan cavabları açmır;
* xam NUL simvollu yazılı cavab 500 verməməlidir (LX-BE ``parse_answer_submission``
  → ``text_safety.sanitize_player_text``; LX-BE düzəldib, xfail götürülüb).
"""

from __future__ import annotations

import csv
import io
import json

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import ExamQuestion, ExamQuestionOption
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession

from .lx_sec_support import (
    login_client,
    make_exam,
    make_org,
    make_session,
    make_teacher,
    player_client,
    reset_rate_limits,
)

_SECRET = "Xəzər-Gizli-Cavab"


class _TypedBase(TestCase):
    def setUp(self):
        reset_rate_limits()
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user("lxs_ty_owner", "lxs_ty_owner@example.com", "StrongPass123!")
        self.org = make_org("LXS Typed Org", owner)
        self.author = make_teacher("lxs_ty_author", self.org)
        self.colleague = make_teacher("lxs_ty_colleague", self.org)
        self.exam = make_exam(self.author, self.org, "lxs-typed-exam", questions=1)
        self.choice_q = self.exam.questions.get()
        self.typed_q = ExamQuestion.objects.create(exam=self.exam, text="Paytaxt?", order=2)
        ExamQuestionOption.objects.create(question=self.typed_q, text=_SECRET, is_correct=True)
        ExamQuestionOption.objects.create(question=self.typed_q, text="Gəncə", is_correct=False)

    def _typed_session(self, **fields):
        settings = {"typed_questions": {str(self.typed_q.id): {"accepted": [_SECRET]}}}
        return make_session(self.exam, self.author, host_settings=settings, **fields)


class ResultsExportTest(_TypedBase):
    def setUp(self):
        super().setUp()
        self.session = self._typed_session(
            state=LiveSession.STATE_FINISHED, selected_question_ids=[self.choice_q.id, self.typed_q.id]
        )
        self.formula_player = LivePlayer.objects.create(
            session=self.session, nickname='=HYPERLINK("http://x")', client_id="lxs-ty-1", score=900
        )
        self.typed_player = LivePlayer.objects.create(session=self.session, nickname="Nigar", client_id="lxs-ty-2")
        correct = self.choice_q.options.get(is_correct=True)
        LiveAnswer.objects.create(
            session=self.session,
            player=self.formula_player,
            question_id=self.choice_q.id,
            choice_id=correct.id,
            choice_ids=[correct.id],
            is_correct=True,
            awarded_points=900,
        )
        for player, text in ((self.formula_player, "+SUM(A1)"), (self.typed_player, "‮=1+1<script>")):
            LiveAnswer.objects.create(
                session=self.session, player=player, question_id=self.typed_q.id, text_answer=text
            )
        self.url = reverse(
            "liveExam:teacher_live_session_export", kwargs={"slug": self.exam.slug, "pin": self.session.pin}
        )

    def test_export_neutralises_formulas_and_strips_bidi(self):
        response = login_client(self.author, self.org).get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        body = rows[1:]
        self.assertEqual(len(body), 3)
        cells = [cell for row in body for cell in row]
        self.assertIn('\'=HYPERLINK("http://x")', cells)
        self.assertIn("'+SUM(A1)", cells)
        self.assertIn("'=1+1<script>", cells)
        self.assertFalse(any("‮" in cell for cell in cells))
        self.assertFalse(any(cell.startswith(("=", "+", "@")) for cell in cells))

    def test_export_follows_results_access_rules(self):
        self.assertEqual(login_client(self.colleague, self.org).get(self.url).status_code, 404)
        self.assertEqual(Client().get(self.url).status_code, 302)
        self.assertEqual(login_client(self.author, self.org).post(self.url).status_code, 405)

    def test_detail_json_and_context_carry_sanitised_typed_groups(self):
        client = login_client(self.author, self.org)
        detail = reverse(
            "liveExam:teacher_live_session_detail", kwargs={"slug": self.exam.slug, "pin": self.session.pin}
        )
        page = client.get(detail)
        self.assertEqual(page.status_code, 200)
        typed_stats = [row for row in page.context["question_stats"] if row["question"].id == self.typed_q.id][0]
        texts = {group["text"] for group in typed_stats["typed_answers"]}
        self.assertEqual(texts, {"+SUM(A1)", "=1+1<script>"})
        self.assertNotIn("<script>", page.content.decode().replace("&lt;script&gt;", ""))
        data = client.get(detail, HTTP_ACCEPT="application/json").json()
        typed_json = [row for row in data["question_stats"] if row["question_id"] == self.typed_q.id][0]
        self.assertFalse(any("‮" in group["text"] for group in typed_json["typed_answers"]))


class TypedPreRevealLeakTest(_TypedBase):
    def setUp(self):
        super().setUp()
        started_at = timezone.now() - timezone.timedelta(seconds=12)
        self.session = self._typed_session(
            state=LiveSession.STATE_QUESTION,
            selected_question_ids=[self.typed_q.id],
            current_index=0,
            current_question_id=self.typed_q.id,
            question_started_at=started_at,
            question_ends_at=started_at + timezone.timedelta(seconds=60),
        )
        self.alice, self.alice_client = player_client(self.session, "Alice", "lxs-ty-alice")
        self.bob, self.bob_client = player_client(self.session, "Bob", "lxs-ty-bob")

    def _submit(self, client, text):
        return client.post(
            reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin}),
            data=json.dumps({"question_id": self.typed_q.id, "text": text, "answer_ms": 900}),
            content_type="application/json",
        )

    def test_state_endpoints_do_not_leak_texts_or_accepted_answers(self):
        submitted = self._submit(self.alice_client, "Alice-Mətn-123")
        self.assertEqual(submitted.status_code, 200, submitted.content)
        own = submitted.content.decode()
        for secret in (_SECRET, "accepted_answers", "typed_summary", '"is_correct"'):
            self.assertNotIn(secret, own)

        urls = (
            reverse("liveExam:state_json", kwargs={"pin": self.session.pin}),
            reverse("live_exam_api_v1:state_json", kwargs={"pin": self.session.pin}),
        )
        for url in urls:
            reset_rate_limits()
            with self.subTest(url=url):
                body = self.bob_client.get(url).content.decode()
                for secret in ("Alice-Mətn-123", _SECRET, "accepted_answers", "typed_summary"):
                    self.assertNotIn(secret, body)

    def test_player_pages_do_not_embed_accepted_answers(self):
        LiveSession.objects.filter(pk=self.session.pk).update(state=LiveSession.STATE_LOBBY)
        pages = (
            self.bob_client.get(reverse("liveExam:join_page", kwargs={"pin": self.session.pin})),
            self.bob_client.get(reverse("liveExam:wait_room", kwargs={"pin": self.session.pin})),
            self.bob_client.get(reverse("liveExam:player_screen", kwargs={"pin": self.session.pin})),
        )
        for response in pages:
            with self.subTest(template=response.templates[0].name if response.templates else response.status_code):
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, _SECRET)

    def test_nul_in_typed_answer_does_not_500(self):
        self.alice_client.raise_request_exception = False
        response = self._submit(self.alice_client, "Ba\x00kı‮")
        self.assertNotEqual(response.status_code, 500)
        stored = LiveAnswer.objects.filter(player=self.alice).values_list("text_answer", flat=True).first() or ""
        self.assertNotIn("‮", stored)
