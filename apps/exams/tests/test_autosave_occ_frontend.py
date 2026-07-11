"""Autosave OCC brauzer kontraktı üçün statik regresiya testləri."""

from pathlib import Path

from django.test import SimpleTestCase

JS_DIR = Path(__file__).resolve().parents[1] / "static" / "exams" / "js" / "take_exam"


class AutosaveOccFrontendContractTests(SimpleTestCase):
    def test_conflict_pauses_all_automatic_retry_paths(self):
        """409-dan sonra yeni base ilə stale draft avtomatik yazıla bilməz."""
        config_source = (JS_DIR / "config.js").read_text(encoding="utf-8")
        draft_source = (JS_DIR / "draft.js").read_text(encoding="utf-8")

        self.assertIn("autosaveConflict: false", config_source)
        self.assertIn("ctx.autosaveConflict = true", draft_source)
        self.assertIn("if (ctx.autosaveConflict)", draft_source)
        self.assertIn("if (!ctx.autosaveConflict && ctx.hasUnsavedChanges)", draft_source)
        self.assertIn('data.error === "question_timer_not_started"', draft_source)
        self.assertIn("syncQuestionTimerWithServer(ctx, timerSlide)", draft_source)

    def test_answer_draft_uses_tab_scoped_storage_and_cleans_legacy_plaintext(self):
        draft_source = (JS_DIR / "draft.js").read_text(encoding="utf-8")

        self.assertIn("sessionStorage.setItem(ctx.draftStorageKey", draft_source)
        self.assertIn("sessionStorage.getItem(ctx.draftStorageKey", draft_source)
        self.assertIn("localStorage.removeItem(ctx.draftStorageKey)", draft_source)
        self.assertNotIn("localStorage.setItem(ctx.draftStorageKey", draft_source)
