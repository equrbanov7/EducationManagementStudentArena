"""LX-BE — yazılı cavab (typed answer): uyğunluq cədvəli, uyğunluq şərtləri, ayarlar,
sual/reveal paketləri, bal və məxfilik."""

from __future__ import annotations

import json
from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.live_exam.models import LiveAnswer, LivePlayer
from apps.live_exam.reveal import build_reveal_bundle
from apps.live_exam.scoring import save_answer_and_score
from apps.live_exam.serializers import serialize_question
from apps.live_exam.session_settings import (
    SessionSettingsError,
    get_host_session_settings,
    get_session_settings,
    host_question_catalog,
    update_session_settings,
)
from apps.live_exam.transport import build_lobby_state_payload, parse_answer_submission
from apps.live_exam.typed_answers import (
    build_typed_summary,
    normalize_typed_text,
    typed_answer_matches,
    typed_eligibility,
    within_one_edit,
)

from .lx_be_support import (
    add_question,
    host_client,
    make_exam,
    make_host,
    make_players,
    make_session,
    open_question,
    player_client,
    reset_rate_limits,
)


class TypedMatchingTableTest(SimpleTestCase):
    def test_matching_table(self):
        cases = [
            # (oyunçu, qəbul siyahısı, tolerantlıq, gözlənilən)
            ("Bakı", ["Bakı"], True, True),
            ("baki", ["Bakı"], True, True),
            ("BAKI", ["Bakı"], True, True),
            ("  Bakı!! ", ["Bakı"], True, True),
            ("Gəncə", ["gence"], True, True),
            ("GƏNCƏ", ["Gəncə"], True, True),
            ("İstanbul", ["istanbul"], True, True),
            ("ıstanbul", ["Istanbul"], True, True),
            ("Şəki", ["seki"], True, True),
            ("çay", ["CAY"], True, True),
            ("dağ", ["dag"], True, True),
            ("gözəl", ["gozel"], True, True),
            ("Üzüm", ["uzum"], True, True),
            ("Nizami   Gəncəvi", ["nizami gencevi"], True, True),
            ("Nizami-Gəncəvi", ["Nizami Gəncəvi"], True, True),
            ("3,0", ["3"], True, True),
            ("3.0", ["3,0"], True, True),
            ("3", ["3.00"], True, True),
            ("-2,50", ["-2.5"], True, True),
            ("１２", ["12"], True, True),  # fullwidth → NFKC
            ("12", ["13"], True, False),  # rəqəmə səhv tolerantlığı YOXDUR
            ("123456", ["123457"], True, False),
            ("Azerbaycan", ["Azərbaycan"], True, True),
            ("Azerbajcan", ["Azərbaycan"], True, True),  # 1 əvəzetmə, ≥ 6 simvol
            ("Azrebaycan", ["Azərbaycan"], True, True),  # qonşu yerdəyişmə
            ("Azerbaycann", ["Azərbaycan"], True, True),  # 1 əlavə
            ("Azerbaycan", ["Azərbaycan"], False, True),  # dəqiq (qatlanmış)
            ("Azerbajcan", ["Azərbaycan"], False, False),  # tolerantlıq söndürülüb
            ("Azerbajcaan", ["Azərbaycan"], True, False),  # 2 səhv
            ("Baku", ["Bakı"], True, False),  # 4 simvol → tolerantlıq yoxdur
            ("", ["Bakı"], True, False),
            ("   ", ["Bakı"], True, False),
            ("Paris", ["London", "Paris"], True, True),
        ]
        for text, accepted, tolerance, expected in cases:
            with self.subTest(text=text, accepted=accepted, tolerance=tolerance):
                self.assertIs(typed_answer_matches(text, accepted, typo_tolerance=tolerance), expected)

    def test_normalization_and_edit_distance_helpers(self):
        self.assertEqual(normalize_typed_text("  ƏLİ, Şəkili!  "), "eli sekili")
        self.assertEqual(normalize_typed_text("3,50"), "3.5")
        self.assertEqual(normalize_typed_text("100"), "100")
        self.assertEqual(normalize_typed_text("-0,0"), "0")
        self.assertTrue(within_one_edit("abcdef", "abcdfe"))
        self.assertTrue(within_one_edit("abcdef", "abcdf"))
        self.assertFalse(within_one_edit("abcdef", "abcfed"))

    def test_typed_summary_groups_by_normalized_form(self):
        answers = [
            {"text_answer": "Bakı", "is_correct": True},
            {"text_answer": "baki", "is_correct": True},
            {"text_answer": "Bakı", "is_correct": True},
            {"text_answer": "Gəncə", "is_correct": False},
            {"text_answer": "", "is_correct": False},
        ]
        summary = build_typed_summary(answers)
        self.assertEqual(summary[0], {"text": "Bakı", "count": 3, "correct": True})
        self.assertEqual(summary[1], {"text": "Gəncə", "count": 1, "correct": False})
        self.assertEqual(len(summary), 2)

    def test_parse_answer_submission_accepts_text(self):
        ok, parsed = parse_answer_submission({"type": "answer", "question_id": 5, "text": " Bakı​ ", "answer_ms": 3})
        self.assertTrue(ok)
        self.assertEqual(parsed, (5, [], 3, "Bakı"))
        self.assertFalse(parse_answer_submission({"question_id": 5, "text": "x" * 61})[0])
        self.assertFalse(parse_answer_submission({"question_id": 5, "text": "ok", "option_id": 3})[0])
        self.assertFalse(parse_answer_submission({"question_id": 5, "text": 7})[0])
        self.assertFalse(parse_answer_submission({"question_id": 2**40, "option_id": 3})[0])


class TypedAnswerFlowTest(TestCase):
    def setUp(self):
        reset_rate_limits()
        self.host, self.org = make_host("lxbetyped")
        self.exam = make_exam(self.host, self.org)
        self.capital, capital_options = add_question(
            self.exam, "Azərbaycanın paytaxtı?", [("Bakı", True), ("Gəncə", False)], order=1
        )
        self.short_answer, _ = add_question(
            self.exam, "Ən böyük göl?", [], order=2, correct_answer="Xəzər\nKaspi dənizi"
        )
        self.multi, _ = add_question(self.exam, "Hansılar?", [("A", True), ("B", True), ("C", False)], order=3)
        self.long_option, _ = add_question(self.exam, "Uzun?", [("x" * 61, True), ("y", False)], order=4)
        self.session = make_session(self.exam, self.host)
        self.client = host_client(self.host, self.org)

    def _set_typed(self, mapping, **extra):
        url = reverse("liveExam:host_update_settings", kwargs={"pin": self.session.pin})
        body = {"typed_questions": mapping, **extra}
        return self.client.post(url, data=json.dumps(body), content_type="application/json")

    def test_eligibility_and_catalog(self):
        self.assertEqual(typed_eligibility(self.capital), (True, ["Bakı"]))
        self.assertEqual(typed_eligibility(self.short_answer), (True, ["Xəzər", "Kaspi dənizi"]))
        self.assertEqual(typed_eligibility(self.multi), (False, []))
        self.assertEqual(typed_eligibility(self.long_option), (False, []))

        catalog = host_question_catalog(self.session)
        self.assertEqual([row["index"] for row in catalog], [1, 2, 3, 4])
        self.assertEqual(catalog[0]["id"], self.capital.id)
        self.assertTrue(catalog[0]["typed_eligible"])
        self.assertEqual(catalog[0]["typed_default_accepted"], ["Bakı"])
        self.assertFalse(catalog[2]["typed_eligible"])
        self.assertFalse(catalog[0]["typed"])

    def test_settings_validation_and_echo(self):
        response = self._set_typed({str(self.capital.id): {"accepted": ["Bakı", "baki", "Baku", ""]}})
        self.assertEqual(response.status_code, 200, response.content)
        settings = response.json()["settings"]
        # Normallaşmadan sonra təkrarlar atılır (baki == Bakı), boş sətir atılır.
        self.assertEqual(settings["typed_questions"], {str(self.capital.id): {"accepted": ["Bakı", "Baku"]}})
        self.assertIs(settings["typed_typo_tolerance"], True)
        self.assertEqual(settings["multi_scoring"], "partial")

        bad = self._set_typed({str(self.multi.id): {"accepted": []}})
        self.assertEqual(bad.status_code, 400)
        self.assertTrue(bad.json()["message"])
        self.assertEqual(self._set_typed({"999999": {"accepted": []}}).status_code, 400)
        self.assertEqual(self._set_typed({str(self.capital.id): {"accepted": ["x"] * 11}}).status_code, 400)
        self.assertEqual(self._set_typed({str(self.capital.id): {"accepted": ["x" * 61]}}).status_code, 400)
        self.assertEqual(self._set_typed(["nope"]).status_code, 400)

        # Tam əvəzləmə: boş xəritə → heç bir sual yazılı deyil.
        cleared = self._set_typed({}, multi_scoring="strict", typed_typo_tolerance=False)
        self.assertEqual(cleared.json()["settings"]["typed_questions"], {})
        self.assertEqual(cleared.json()["settings"]["multi_scoring"], "strict")
        self.assertIs(cleared.json()["settings"]["typed_typo_tolerance"], False)

    def test_accepted_answers_never_reach_players(self):
        update_session_settings(self.session, {"typed_questions": {str(self.capital.id): {"accepted": ["Bakı"]}}})
        self.assertIn("typed_questions", get_host_session_settings(self.session))
        self.assertNotIn("typed_questions", get_session_settings(self.session))
        self.assertNotIn("typed_questions", build_lobby_state_payload(self.session)["settings"])

        player = make_players(self.session, 1)[0]
        open_question(self.session, self.capital)
        data = player_client(self.session, player).get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin}))
        self.assertEqual(data.status_code, 200)
        body = data.json()
        self.assertNotIn("typed_questions", body["settings"])
        self.assertEqual(body["question"]["answer_input"], "text")
        self.assertEqual(body["question"]["text_max_length"], 60)
        self.assertEqual(body["question"]["options"], [])
        self.assertNotIn("Bakı", json.dumps(body, ensure_ascii=False))

    def test_typed_scoring_reveal_and_storage(self):
        update_session_settings(self.session, {"typed_questions": {str(self.capital.id): {"accepted": []}}})
        players = make_players(self.session, 4)
        answer_starts_at = open_question(self.session, self.capital, opened_seconds_ago=0.5)
        plan = [("Bakı", 1000, True), ("  baki ", 2000, True), ("Gəncə", 1500, False), ("", 500, False)]
        results = []
        for player, (text, ms, _correct) in zip(players, plan):
            ok, result = save_answer_and_score(
                pin=self.session.pin,
                player_id=player.id,
                client_id=player.client_id,
                question_id=self.capital.id,
                option_ids=[],
                answer_ms=ms,
                received_at=answer_starts_at + timedelta(milliseconds=ms),
                text=text,
            )
            self.assertTrue(ok, result)
            results.append(result)

        for result, (_text, ms, correct) in zip(results, plan):
            self.assertIs(result["answer"]["is_correct"], correct)
            expected = round(1000 * (1 - 0.5 * ms / 20000)) if correct else 0
            self.assertEqual(result["answer"]["awarded_points"], expected)
        self.assertEqual(results[-1]["reveal_question_id"], self.capital.id)
        stored = {answer.player_id: answer.text_answer for answer in LiveAnswer.objects.filter(session=self.session)}
        self.assertEqual(stored[players[1].id], "baki")

        self.session.refresh_from_db()
        bundle = build_reveal_bundle(self.session, self.capital.id)
        self.assertEqual(bundle.host["answer_input"], "text")
        self.assertEqual(bundle.host["accepted_answers"], ["Bakı"])
        self.assertEqual(bundle.host["typed_total"], 4)
        self.assertEqual(bundle.host["typed_correct"], 2)
        self.assertEqual(bundle.host["typed_summary"][0], {"text": "Bakı", "count": 2, "correct": True})
        self.assertEqual(bundle.players["accepted_answers"], ["Bakı"])
        self.assertNotIn("typed_summary", bundle.players)
        mine = bundle.personal_for(players[1].id)
        self.assertEqual(mine["your_text"], "baki")
        self.assertEqual(mine["player_answer"]["your_text"], "baki")
        self.assertTrue(mine["player_answer"]["is_correct"])

    def _typed_round(self, texts, accepted):
        update_session_settings(self.session, {"typed_questions": {str(self.capital.id): {"accepted": accepted}}})
        players = make_players(self.session, len(texts))
        open_question(self.session, self.capital)
        for player, text in zip(players, texts):
            response = player_client(self.session, player).post(
                reverse("liveExam:answer_submit", kwargs={"pin": self.session.pin}),
                data=json.dumps({"question_id": self.capital.id, "text": text, "answer_ms": 900}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, response.content)
        self.session.refresh_from_db()
        return build_reveal_bundle(self.session, self.capital.id).host

    def test_typed_summary_regression_five_inputs(self):
        # LX-FE-STAGE hesabatı: «Bakı» etiketli İKİ qrup görünməməlidir.
        host = self._typed_round(["Bakı", "baki", "BAKI", "Bakıı", "Baku"], [])
        self.assertEqual(
            host["typed_summary"],
            [
                {"text": "Bakı", "count": 3, "correct": True},
                {"text": "Baku", "count": 1, "correct": False},
                {"text": "Bakıı", "count": 1, "correct": False},
            ],
        )
        labels = [row["text"] for row in host["typed_summary"]]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual((host["typed_total"], host["typed_correct"]), (5, 3))
        stored = dict(LiveAnswer.objects.values_list("text_answer", "is_correct"))
        for row in host["typed_summary"]:
            self.assertEqual(row["correct"], stored[row["text"]])  # qrupun uyğunluq nəticəsi

    def test_typed_summary_with_extra_accepted_spelling(self):
        host = self._typed_round(["Bakı", "baki", "BAKI", "Bakıı", "Baku"], ["Bakı", "Baku"])
        self.assertEqual(
            [(row["text"], row["count"], row["correct"]) for row in host["typed_summary"]],
            [("Bakı", 3, True), ("Baku", 1, True), ("Bakıı", 1, False)],
        )

    def test_choice_payload_for_typed_question_is_rejected_and_vice_versa(self):
        update_session_settings(self.session, {"typed_questions": {str(self.capital.id): {"accepted": []}}})
        player = make_players(self.session, 2)[0]
        open_question(self.session, self.capital)
        option_id = self.capital.options.first().id
        ok, _ = save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.capital.id,
            option_ids=[option_id],
            answer_ms=0,
        )
        self.assertFalse(ok)

        self.session.host_settings = {}
        self.session.save(update_fields=["host_settings"])
        ok, _ = save_answer_and_score(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
            question_id=self.capital.id,
            option_ids=[],
            answer_ms=0,
            text="Bakı",
        )
        self.assertFalse(ok)
        self.assertEqual(LiveAnswer.objects.count(), 0)

    def test_question_payload_config_is_frozen_at_publish(self):
        from apps.live_exam.services import publish_question

        update_session_settings(self.session, {"typed_questions": {str(self.capital.id): {"accepted": ["Bakı"]}}})
        payload = publish_question(self.session, self.capital, idx=0, total=1)
        self.assertEqual(payload["question"]["answer_input"], "text")
        # Oyun gedərkən ayar dəyişsə də aktiv sualın qaydası dəyişmir.
        update_session_settings(self.session, {"typed_questions": {}})
        again = serialize_question(
            self.session,
            self.capital,
            idx=0,
            total=1,
            started_at=self.session.question_started_at,
            ready_ends_at=None,
            answer_starts_at=None,
            ends_at=self.session.question_ends_at,
        )
        self.assertEqual(again["answer_input"], "text")
        self.assertEqual(LivePlayer.objects.count(), 0)

    def test_update_session_settings_raises_for_ineligible(self):
        with self.assertRaises(SessionSettingsError):
            update_session_settings(self.session, {"typed_questions": {str(self.long_option.id): {}}})
