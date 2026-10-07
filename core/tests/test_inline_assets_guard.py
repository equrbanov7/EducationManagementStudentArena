"""Audit 2026-09-28 FQ-FE-1/FQ-FE-2: inline CSS/JS qapısı (`scripts/check_inline_assets.py`).

* Skanerin özü: inline `<style>`, src-siz `<script>`, `on*=` atributları tutulur;
  xarici skript, JSON/ld+json data blokları və şərhlər tutulmur.
* Real ağac: bütün şablonlar təmizdir (CSP `unsafe-inline` vermir).
"""

import importlib.util
import re
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


# base.html-in asset slotları: uşaq şablon bunları BAŞQA blokun içində təyin edərsə
# Django override-ı iki yerdə render edir (həm valideyn blokun içində, həm də base-in
# öz slotunda) — hər skript/stil İKİ DƏFƏ icra olunur.
_BASE_ASSET_BLOCKS = ("extraHead", "extraCss", "extraJs", "global_search_js", "ai_assistant_js")
_BLOCK_TAG = re.compile(r"{%\s*(?:block\s+(\w+)|endblock(?:\s+\w+)?)\s*%}")
_COMMENT_BLOCK = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", re.S)


def _nested_asset_blocks(text: str) -> list[tuple[str, list[str]]]:
    found = []
    stack: list[str] = []
    for match in _BLOCK_TAG.finditer(_COMMENT_BLOCK.sub("", text)):
        name = match.group(1)
        if name is None:
            if stack:
                stack.pop()
            continue
        if name in _BASE_ASSET_BLOCKS and stack:
            found.append((name, list(stack)))
        stack.append(name)
    return found


class AssetBlockNestingGuardTest(SimpleTestCase):
    """Perf 2026-10-07: `take_exam.html`-də `extraJs` `content`-in içində idi —
    KaTeX (266 KB), paint/nəzarət skriptləri hər imtahan açılışında İKİ DƏFƏ icra
    olunurdu. Base asset blokları heç vaxt başqa blokun içində təyin olunmamalıdır."""

    def test_detector(self):
        bad = "{% block content %}<p>x</p>{% block extraJs %}<script src='a.js'></script>{% endblock %}{% endblock %}"
        ok = "{% block content %}x{% endblock %}{% block extraJs %}{% block inner %}{% endblock %}{% endblock %}"
        self.assertEqual(_nested_asset_blocks(bad), [("extraJs", ["content"])])
        self.assertEqual(_nested_asset_blocks(ok), [])

    def test_no_base_asset_block_is_nested(self):
        base = Path(settings.BASE_DIR)
        offenders = []
        for pattern in ("apps/*/templates/**/*.html", "templates/**/*.html"):
            for path in sorted(base.glob(pattern)):
                for name, parents in _nested_asset_blocks(path.read_text(encoding="utf-8")):
                    offenders.append(f"{path.relative_to(base)}: {{% block {name} %}} inside {parents}")
        self.assertEqual(offenders, [], "Asset bloku başqa blokun içindədir — iki dəfə render olunur.")
