"""Smoke tests for the frontend coding-exam assets.

These don't spin up a JS engine — they assert on the static source of
`coding_exam.js` so the contract the backend depends on (function names,
constants, defensive guards) cannot regress unnoticed in CI.

Pure-Python so they run in the same pytest job as the rest of the suite.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

JS_ASSET = Path(settings.BASE_DIR) / "apps" / "exams" / "static" / "exams" / "js" / "coding_exam.js"
JS_MODULE_DIR = Path(settings.BASE_DIR) / "apps" / "exams" / "static" / "exams" / "js" / "coding_exam"
SUPERVISION_JS_ASSET = Path(settings.BASE_DIR) / "apps" / "exams" / "static" / "exams" / "js" / "exam_supervision.js"


class CodingExamJavaScriptAssetTests(SimpleTestCase):
    """Guard the public surface area of `coding_exam.js`.

    These checks are intentionally string-level — we don't try to evaluate
    the JS. They catch the most common regressions: a helper being renamed,
    a critical guard being removed, or a constant we depend on being
    accidentally inlined and lost.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        module_sources = [path.read_text(encoding="utf-8") for path in sorted(JS_MODULE_DIR.glob("*.js"))]
        cls.source = JS_ASSET.read_text(encoding="utf-8") + "\n".join(module_sources)

    def test_js_asset_exists_on_disk(self):
        self.assertTrue(JS_ASSET.exists(), f"Expected {JS_ASSET} to exist")
        self.assertTrue(JS_MODULE_DIR.joinpath("coding_exam.entry.js").exists())

    def test_inline_terminal_helpers_are_defined(self):
        # The interactive terminal that students type into; these names are
        # exercised by `runCode` and the Clear button handler.
        for name in (
            "function startInlineTerminal",
            "function renderInlineTerminal",
            "function completeInlineTerminal",
            "function resolveExecutionFile",
            "function detectStdinPrompts",
            "function outputWithInlineInput",
            "function performBackendRun",
        ):
            self.assertIn(name, self.source, f"Missing helper: {name}")

    def test_run_clears_previous_stdin_before_inline_terminal(self):
        # Without this guard, a second click on Run silently reuses the
        # previous answers and the interactive prompt loop is skipped.
        # We check for both the textarea reset and the question.stdin reset.
        run_block_start = self.source.index("function runCode()")
        run_block_end = self.source.index("function ", run_block_start + 1)
        run_block = self.source[run_block_start:run_block_end]
        self.assertIn('stdinNode.value = ""', run_block)
        self.assertIn('question.stdin = ""', run_block)

    def test_clear_button_resets_stdin_and_terminal_state(self):
        # The Clear button must wipe BOTH the visible output and the stdin
        # buffer; otherwise the next Run reuses old values.
        clear_idx = self.source.index("consoleClearBtn.addEventListener")
        # Take a generous slice of the handler body.
        clear_block = self.source[clear_idx : clear_idx + 1200]
        self.assertIn("outputNode.innerHTML", clear_block)
        self.assertIn('stdinNode.value = ""', clear_block)
        self.assertIn("inlineTerminalActive = false", clear_block)
        self.assertIn("lastInteractivePrompts = []", clear_block)

    def test_keyboard_shortcuts_are_wired(self):
        # VS Code parity for the editor — these bindings are not tested in
        # any other way and silently regressing them would hurt UX badly.
        for binding in ('"Ctrl-Enter"', '"Cmd-Enter"', '"Ctrl-Space"', '"Ctrl-/"'):
            self.assertIn(binding, self.source, f"Missing shortcut binding: {binding}")

    def test_redirects_stop_supervision_before_navigation(self):
        self.assertIn("function navigateAway", self.source)
        self.assertIn("window.EXAM_SUPERVISION_NAVIGATING = true", self.source)
        self.assertIn("window.ExamSupervision.destroy", self.source)


class ExamSupervisionJavaScriptAssetTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = SUPERVISION_JS_ASSET.read_text(encoding="utf-8")

    def test_result_navigation_is_idempotent(self):
        self.assertIn("_navigatingToResult", self.source)
        self.assertIn("window.EXAM_SUPERVISION_NAVIGATING === true", self.source)
        self.assertIn("window.EXAM_SUPERVISION_NAVIGATING = true", self.source)
        self.assertIn("this.destroy();", self.source)
