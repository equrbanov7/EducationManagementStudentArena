"""Audit 2026-09-28 FQ-FE-1/FQ-FE-2: inline CSS/JS qapısı (`scripts/check_inline_assets.py`).

* Skanerin özü: inline `<style>`, src-siz `<script>`, `on*=` atributları tutulur;
  xarici skript, JSON/ld+json data blokları və şərhlər tutulmur.
* Real ağac: bütün şablonlar təmizdir (CSP `unsafe-inline` vermir).
"""

import importlib.util
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

_SCRIPT = Path(settings.BASE_DIR) / "scripts" / "check_inline_assets.py"
_spec = importlib.util.spec_from_file_location("check_inline_assets", _SCRIPT)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


class InlineAssetScannerTest(SimpleTestCase):
    def test_detects_inline_style_script_and_event_handlers(self):
        text = (
            "<div>\n"
            "<style>.x{color:red}</style>\n"
            "<script>alert(1)</script>\n"
            '<button type="submit" onclick="return confirm(\'x\')">x</button>\n'
            '<form onsubmit="go()"></form>\n'
            "</div>\n"
        )
        reasons = [reason for _line, reason in checker.scan_text(text)]
        self.assertEqual(len(reasons), 4, reasons)
        self.assertEqual([line for line, _r in checker.scan_text(text)], [2, 3, 4, 5])

    def test_allows_external_data_blocks_and_comments(self):
        text = (
            '<script src="/static/js/app.js"></script>\n'
            '<script type="application/json" id="cfg">{"onclick=": "x"}</script>\n'
            '<script type="application/ld+json">{}</script>\n'
            "{# <style>.x{}</style> #}\n"
            "{% comment %}<script>bad()</script>{% endcomment %}\n"
            '<!-- <div onclick="x()"></div> -->\n'
            '<button data-ems-confirm="Silinsin?">Sil</button>\n'
            "<p>Common = sentence with onion= text</p>\n"
        )
        self.assertEqual(checker.scan_text(text), [])

    def test_repository_templates_are_clean(self):
        findings = checker.scan()
        self.assertEqual(findings, {}, "Inline CSS/JS tapıldı — xarici static fayla çıxarın.")

    def test_main_exit_code(self):
        self.assertEqual(checker.main(["--quiet"]), 0)
