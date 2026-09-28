"""Audit 2026-09-28 EX28-10 — canlı quiz: reveal-dən əvvəl nəticə sızmır, join limiti.

* ``answer_saved`` (HTTP) reveal-ə qədər ``is_correct`` / bal / sıra daşımır;
* state endpoint açıq sual ərzində ``player_answer``-də düzlük vermir, reveal-də verir;
* join İP + sessiya vedrəsi ``live_client_id`` cookie-sini dəyişməklə sıfırlanmır;
* PIN axtarışı (GET ``?pin=``) da limitlidir;
* sessiya yaratmaq yalnız POST (bax ``test_views.LiveSessionCreationTest``).
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.auth import PLAYER_COOKIE_NAME, build_player_token
from apps.live_exam.models import LivePlayer, LiveSession
from apps.live_exam.transport import PRE_REVEAL_ANSWER_KEYS, build_answer_saved_payload, public_player_answer
from apps.organizations.models import Organization
from core import rate_limit as rate_limit_module
from core.constants import OrganizationType

User = get_user_model()

_SECRET_KEYS = {"is_correct", "awarded_points", "total_score", "score", "answer_rank", "fraction", "picked_correct"}


class _LiveBase(TestCase):
    def setUp(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.teacher = User.objects.create_user("ex2810_teacher", "ex2810@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="EX28-10 Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.exam = Exam.objects.create(title="EX28-10", slug="ex28-10-live", author=self.teacher, is_active=True)
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.question = ExamQuestion.objects.create(exam=self.exam, text="2+2?", order=1)
        self.correct = ExamQuestionOption.objects.create(question=self.question, text="4", is_correct=True)
        self.wrong = ExamQuestionOption.objects.create(question=self.question, text="5", is_correct=False)

    def _player_client(self, nickname, client_id):
        player = LivePlayer.objects.create(
            session=self.session, nickname=nickname, avatar_key="avatar_1", client_id=client_id
        )
        client = Client()
        client.cookies["live_client_id"] = client_id
        client.cookies[PLAYER_COOKIE_NAME] = build_player_token(
            pin=self.session.pin, player_id=player.id, client_id=client_id
        )
        return player, client

    def _open_question(self):
        started_at = timezone.now() - timezone.timedelta(seconds=12)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.current_question_id = self.question.id
        self.session.question_started_at = started_at
        self.session.question_ends_at = started_at + timezone.timedelta(seconds=60)
        self.session.save(
            update_fields=["state", "current_index", "current_question_id", "question_started_at", "question_ends_at"]
        )

    def _answer(self, client, option):
        return client.post(
            reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin}),
            data=json.dumps({"question_id": self.question.id, "option_id": option.id, "answer_ms": 900}),
            content_type="application/json",
        )


class AnswerPayloadBeforeRevealTest(_LiveBase):
    def test_http_answer_saved_hides_correctness_until_reveal(self):
        player, client = self._player_client("Probe", "ex2810-probe")
        self._player_client("Main", "ex2810-main")  # ikinci oyunçu — raund bitmir, reveal yoxdur
        self._open_question()

        response = self._answer(client, self.correct)

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertEqual(answer["type"], "answer_saved")
        self.assertTrue(answer["saved"])
        self.assertEqual(answer["player_id"], player.id)
        self.assertFalse(_SECRET_KEYS & set(answer), answer)
        self.assertNotIn("reveal", response.json())

    def test_state_endpoint_hides_player_correctness_during_question_and_shows_at_reveal(self):
        _player, client = self._player_client("Probe", "ex2810-state")
        self._player_client("Other", "ex2810-state-other")
        self._open_question()
        self._answer(client, self.wrong)

        during = client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin})).json()
        self.assertTrue(during["player_answer"]["saved"])
        self.assertFalse(_SECRET_KEYS & set(during["player_answer"]), during["player_answer"])
        self.assertEqual(during["correct_option_ids"], [])

        LiveSession.objects.filter(pk=self.session.pk).update(state=LiveSession.STATE_REVEAL)
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        after = client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin})).json()
        self.assertIs(after["player_answer"]["is_correct"], False)
        self.assertIn("awarded_points", after["player_answer"])

    def test_last_answer_that_triggers_reveal_returns_full_result(self):
        _player, client = self._player_client("Solo", "ex2810-solo")
        self._open_question()

        payload = self._answer(client, self.correct).json()

        self.assertIn("reveal", payload)
        self.assertIs(payload["answer"]["is_correct"], True)

    def test_public_player_answer_whitelist(self):
        full = {"player_id": 1, "choice_ids": [3], "is_correct": True, "awarded_points": 900, "answer_rank": 1}
        self.assertEqual(public_player_answer(full, revealed=False), {"player_id": 1, "choice_ids": [3], "saved": True})
        self.assertEqual(public_player_answer(full, revealed=True), full)
        self.assertIsNone(public_player_answer(None, revealed=False))
        self.assertLessEqual(set(PRE_REVEAL_ANSWER_KEYS), {"player_id", "choice_ids", "message"})
        saved = build_answer_saved_payload({"answer": full, "question_id": 7, "reveal_question_id": None})
        self.assertEqual(saved["question_id"], 7)
        self.assertNotIn("is_correct", saved)


@override_settings(LIVE_EXAM_JOIN_IP_RATE_LIMIT="3/10m", LIVE_EXAM_JOIN_RATE_LIMIT="20/5m")
class JoinIpBucketTest(_LiveBase):
    def test_rotating_client_cookie_does_not_reset_ip_bucket(self):
        url = reverse("liveExam:join_enter", kwargs={"pin": self.session.pin})
        statuses = []
        for index in range(5):
            client = Client(REMOTE_ADDR="10.28.10.1")
            client.cookies["live_client_id"] = f"rotating-{index}"
            statuses.append(client.post(url, {"nickname": f"Throwaway{index}", "avatar_key": "avatar_1"}).status_code)

        self.assertEqual(statuses[:3], [200, 200, 200])
        self.assertEqual(statuses[3:], [429, 429])
        self.assertEqual(LivePlayer.objects.filter(session=self.session).count(), 3)

    def test_other_ip_is_not_affected(self):
        url = reverse("liveExam:join_enter", kwargs={"pin": self.session.pin})
        for index in range(4):
            client = Client(REMOTE_ADDR="10.28.10.2")
            client.cookies["live_client_id"] = f"spam-{index}"
            client.post(url, {"nickname": f"Spam{index}", "avatar_key": "avatar_1"})

        other = Client(REMOTE_ADDR="10.28.10.3")
        response = other.post(url, {"nickname": "Legit", "avatar_key": "avatar_1"})
        self.assertEqual(response.status_code, 200)


@override_settings(LIVE_PIN_IP_RATE_LIMIT="2/10m", LIVE_EXAM_JOIN_RATE_LIMIT="20/5m")
class PinLookupLimitTest(_LiveBase):
    def test_get_pin_lookup_is_rate_limited_per_ip(self):
        url = reverse("liveExam:pin_entry")
        for index in range(2):
            client = Client(REMOTE_ADDR="10.28.10.9")
            client.cookies["live_client_id"] = f"guess-{index}"
            self.assertEqual(client.get(url, {"pin": f"ZZZZZZZZZ{index}"}).status_code, 200)

        # İP vedrəsi doldu: düzgün PIN belə GET ilə həll olunmur (yönləndirmə yoxdur).
        client = Client(REMOTE_ADDR="10.28.10.9")
        client.cookies["live_client_id"] = "guess-final"
        blocked = client.get(url, {"pin": self.session.pin})
        self.assertEqual(blocked.status_code, 200)

        fresh = Client(REMOTE_ADDR="10.28.10.10").get(url, {"pin": self.session.pin})
        self.assertEqual(fresh.status_code, 302)
