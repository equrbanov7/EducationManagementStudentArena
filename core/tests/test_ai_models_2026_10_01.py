"""Sahib 2026-10-01 — Gemini model adlarının mərkəzi həlli (``core.ai_models``).

Prod diaqnostikası: yeni API açarı üçün ``gemini-2.5-*`` HTTP 404 «no longer available to new users».
Köhnə adlar (baza/env/kod) cari modellərə çevrilməli, imtahan AI zəncirləri də eyni qaydaya tabe olmalıdır.
"""

import os
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from core.ai_models import resolve_chain, resolve_model, thinking_config


class ResolveModelTests(SimpleTestCase):
    def test_legacy_names_map_to_current(self):
        with patch.dict(os.environ, {"GEMINI_MODEL_ALIASES": ""}):
            self.assertEqual(resolve_model("gemini-2.5-flash"), "gemini-3.8-flash")
            self.assertEqual(resolve_model("gemini-2.5-flash-lite"), "gemini-3.5-flash-lite")
            self.assertEqual(resolve_model(" gemini-3.8-flash "), "gemini-3.8-flash")
            self.assertEqual(resolve_model(None), "")

    def test_env_aliases_override_and_bad_json_is_ignored(self):
        with patch.dict(os.environ, {"GEMINI_MODEL_ALIASES": '{"gemini-2.5-flash": "gemini-3.7-flash"}'}):
            self.assertEqual(resolve_model("gemini-2.5-flash"), "gemini-3.7-flash")
            self.assertEqual(resolve_model("gemini-2.5-flash-lite"), "gemini-3.5-flash-lite")
        with patch.dict(os.environ, {"GEMINI_MODEL_ALIASES": "{not json"}):
            self.assertEqual(resolve_model("gemini-2.5-flash"), "gemini-3.8-flash")

    def test_chain_is_resolved_and_deduplicated(self):
        with patch.dict(os.environ, {"GEMINI_MODEL_ALIASES": ""}):
            chain = resolve_chain(("gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", ""))
        self.assertEqual(chain, ("gemini-3.8-flash", "gemini-3.5-flash-lite"))

    def test_thinking_config_per_family(self):
        with patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": ""}):
            self.assertEqual(thinking_config("gemini-3.8-flash"), {"thinkingLevel": "low"})
            self.assertEqual(thinking_config("gemini-2.5-flash"), {"thinkingBudget": 0})
            self.assertIsNone(thinking_config("gemma-4-31b-it"))
        with patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": "HIGH"}):
            self.assertEqual(thinking_config("gemini-3.8-flash"), {"thinkingLevel": "high"})
        with patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": "bogus"}):
            self.assertEqual(thinking_config("gemini-3.8-flash"), {"thinkingLevel": "low"})


class ExamAIChainsUseCurrentModelsTests(SimpleTestCase):
    """İmtahan AI funksiyaları (xülasə, qiymətləndirmə, sual yaratma) köhnə adla 404 almasın."""

    def _cfg(self, **kw):
        cfg = MagicMock()
        cfg.summary_model = kw.get("summary", "gemini-2.5-flash")
        cfg.grading_model = kw.get("grading", "gemini-2.5-flash-lite")
        return cfg

    def test_summary_chain(self):
        from apps.exams.services import ai_summary

        with patch.object(ai_summary, "_get_ai_config", return_value=self._cfg()):
            chain = ai_summary._get_summary_model_chain()
        self.assertTrue(chain)
        self.assertFalse([m for m in chain if m.startswith("gemini-2.5")], chain)

    def test_grading_chain(self):
        from apps.exams.services import ai_grading

        with patch("apps.exams.domain.ai_config.get_ai_config", return_value=self._cfg()):
            chain = ai_grading._get_grading_model_chain()
        self.assertEqual(chain[0], "gemini-3.5-flash-lite")
        self.assertFalse([m for m in chain if m.startswith("gemini-2.5")], chain)

    def test_question_chain(self):
        from apps.exams.services import ai_question_generation

        chain = ai_question_generation._question_model_chain()
        self.assertTrue(chain)
        self.assertFalse([m for m in chain if m.startswith("gemini-2.5")], chain)


class AssistantPayloadTests(SimpleTestCase):
    def test_chat_payload_carries_low_thinking_for_gemini3(self):
        from apps.ai_assistant import gemini_client

        response = MagicMock(status_code=200)
        response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        with (
            patch.object(gemini_client, "_get_api_key", return_value="test-key"),
            patch.object(gemini_client, "_get_model", return_value="gemini-3.8-flash"),
            patch.object(gemini_client.requests, "post", return_value=response) as post,
            patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": ""}),
        ):
            result = gemini_client.ask_gemini(user_message="salam", context="ctx")
        self.assertTrue(result["ok"])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["generationConfig"]["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertIn("gemini-3.8-flash:generateContent", post.call_args.args[0])
