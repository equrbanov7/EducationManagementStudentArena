"""L2 (2026-10-08): sual vaxtı — müəllim «Yenə 15 saniyə qalır… Save etmişdim».

Kök səbəb: oyunun vaxt zənciri «sualın vaxtı → imtahanın standart vaxtı → **15 s**» idi və aparıcının
vaxtı dəyişmək üçün heç bir ayarı yox idi (``LiveSession.question_seconds`` heç yerdə oxunmurdu).
İmtahanda «Hər sual üçün standart vaxt» boş qalanda (placeholder «Məs: 60» dəyər kimi görünür) hər sual
səssizcə 15 s gedirdi. İndi: aparıcının ``question_time_seconds`` seçimi → sualın vaxtı → imtahanın
vaxtı → 30 s; seçim oyun gedərkən də saxlanır və NÖVBƏTİ sualdan tətbiq olunur (cari sual dondurulur).
"""

from __future__ import annotations

import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.exams.models import ExamQuestion
from apps.live_exam import services
from apps.live_exam.domain.session import build_question_phase_times, question_time_limit
from apps.live_exam.models import LiveSession
from apps.live_exam.session_settings import get_session_settings, update_session_settings
from apps.live_exam.transport import build_lobby_state_payload

from .lx_be_support import IN_MEMORY_LAYERS, add_question, host_client, make_exam, make_host, make_session

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "lx-timer"}}


def answer_window_seconds(session: LiveSession) -> float:
    session.refresh_from_db()
    question = ExamQuestion.objects.get(id=session.current_question_id)
    _ready, answer_starts_at, _ends = build_question_phase_times(
        session, question, started_at=session.question_started_at, idx=int(session.current_index or 0)
    )
    return round((session.question_ends_at - answer_starts_at).total_seconds(), 3)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS, CACHES=LOCMEM)
class QuestionTimerRegressionTest(TestCase):
    def setUp(self):
        self.host, self.org = make_host("lxtimer")
        self.exam = make_exam(self.host, self.org)
        self.q1, _ = add_question(self.exam, "Q1", [("a", True), ("b", False)], order=1)
        self.q2, _ = add_question(self.exam, "Q2", [("a", True), ("b", False)], order=2)
        self.session = make_session(self.exam, self.host)
        update_session_settings(self.session, {"randomize_questions": False})
        self.client = host_client(self.host, self.org)

    def _post(self, name, data=None):
        return self.client.post(reverse(f"liveExam:{name}", kwargs={"pin": self.session.pin}), data or {})

    def _save_time(self, value):
        return self.client.post(
            reverse("liveExam:host_update_settings", kwargs={"pin": self.session.pin}),
            data=json.dumps({"question_time_seconds": value}),
            content_type="application/json",
        )

    def _state(self):
        return self.client.get(reverse("liveExam:state_json", kwargs={"pin": self.session.pin})).json()

    def test_empty_exam_default_no_longer_falls_back_to_15_seconds(self):
        """Boş imtahan vaxtı + aparıcı seçimi yoxdur → 30 s (əvvəl 15 s)."""
        self.assertIsNone(self.exam.default_question_time_seconds)
        self.assertEqual(self._post("host_start_game", {"question_count": "2"}).status_code, 200)
        self.assertEqual(answer_window_seconds(self.session), 30)
        self.assertEqual(self._state()["question"]["time_limit"], 30)

    def test_saved_host_setting_is_used_by_the_game(self):
        """«Save etmişdim» — saxlanmış seçim oyunun cavab pəncərəsini təyin edir."""
        response = self._save_time(45)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["settings"]["question_time_seconds"], 45)
        self.assertEqual(self._post("host_start_game", {"question_count": "2"}).status_code, 200)
        self.assertEqual(answer_window_seconds(self.session), 45)
        self.assertEqual(self._state()["question"]["time_limit"], 45)

    def test_host_setting_overrides_per_question_and_exam_values(self):
        self.exam.default_question_time_seconds = 30
        self.exam.save(update_fields=["default_question_time_seconds"])
        self.q1.time_limit_seconds = 15
        self.q1.save(update_fields=["time_limit_seconds"])
        session = LiveSession.objects.select_related("exam").get(pk=self.session.pk)
        self.assertEqual(question_time_limit(session, self.q1), 15)  # standart: sualın öz vaxtı
        self._save_time(60)
        session.refresh_from_db()
        self.assertEqual(question_time_limit(session, self.q1), 60)  # aparıcının seçimi HƏR suala
        self._save_time("")  # «Standart»-a qayıt
        session.refresh_from_db()
        self.assertIsNone(get_session_settings(session)["question_time_seconds"])
        self.assertEqual(question_time_limit(session, self.q1), 15)

    def test_change_between_questions_applies_to_next_question_only(self):
        self.assertEqual(self._post("host_start_game", {"question_count": "2"}).status_code, 200)
        self.assertEqual(answer_window_seconds(self.session), 30)
        ends_before = LiveSession.objects.get(pk=self.session.pk).question_ends_at

        # Sual gedərkən saxlanır — cari raund dəyişmir (vaxt dondurulub), state JSON köhnə vaxtı göstərir.
        self.assertEqual(self._save_time(90).status_code, 200)
        self.assertEqual(LiveSession.objects.get(pk=self.session.pk).question_ends_at, ends_before)
        self.assertEqual(self._state()["question"]["time_limit"], 30)

        self.assertEqual(self._post("host_reveal").status_code, 200)
        self.assertEqual(self._post("host_next_question").status_code, 200)
        self.assertEqual(answer_window_seconds(self.session), 90)
        self.assertEqual(self._state()["question"]["time_limit"], 90)

    def test_skip_intro_keeps_the_frozen_time(self):
        self._save_time(20)
        self.assertEqual(self._post("host_start_game", {"question_count": "2"}).status_code, 200)
        self._save_time(120)  # sual gedərkən dəyişir
        self.assertEqual(self._post("host_skip_question_intro").status_code, 200)
        session = LiveSession.objects.get(pk=self.session.pk)
        _ready, answer_starts_at, _ends = build_question_phase_times(
            session, self.q1, started_at=session.question_started_at, idx=0
        )
        self.assertEqual(round((session.question_ends_at - answer_starts_at).total_seconds()), 20)

    def test_setting_validation_and_lobby_broadcast(self):
        self.assertEqual(self._save_time(1000).json()["settings"]["question_time_seconds"], 300)
        self.assertEqual(self._save_time(2).json()["settings"]["question_time_seconds"], 5)
        self.assertEqual(self._save_time(0).json()["settings"]["question_time_seconds"], None)
        self.assertEqual(self._save_time("abc").status_code, 400)
        self._save_time(30)
        self.session.refresh_from_db()
        # Lobbi (proyektor + gözləmə otağı) yeni dəyəri görür — keşlənmiş köhnə dəyər yoxdur.
        self.assertEqual(build_lobby_state_payload(self.session)["settings"]["question_time_seconds"], 30)

    def test_host_pages_ship_the_time_control(self):
        self.exam.default_question_time_seconds = 40
        self.exam.save(update_fields=["default_question_time_seconds"])
        for name, query in (("host_lobby", ""), ("host_presentation", "?controls=1")):
            response = self.client.get(reverse(f"liveExam:{name}", kwargs={"pin": self.session.pin}) + query)
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            self.assertIn('id="hostQuestionTime"', html)
            self.assertIn('"default": 40', html)
            self.assertIn("data-time-setting", html)  # idarə panelindəki seçici
            self.assertNotIn("<select", html)  # native select yoxdur

    def test_legacy_frozen_snapshot_without_time_uses_live_value(self):
        """Deploy anında gedən sessiya (dondurulmuş snapshot-da vaxt yoxdur) — canlı hesab."""
        services.start_game(self.session, question_count=2)
        session = LiveSession.objects.select_related("exam").get(pk=self.session.pk)
        raw = dict(session.host_settings)
        raw["_question_config"] = {k: v for k, v in raw["_question_config"].items() if k != "time_limit"}
        raw["question_time_seconds"] = 25
        session.host_settings = raw
        self.assertEqual(question_time_limit(session, self.q1), 25)
