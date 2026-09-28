#!/usr/bin/env python3
"""Inline CSS/JS qapısı — CLAUDE.md «Frontend: HEÇ VAXT inline/internal CSS və ya JS».

Niyə?
-----
Layihənin CSP-si (``config/settings/components/csp.py``) ``script-src`` və
``style-src`` üçün ``'unsafe-inline'`` VERMİR. Deməli şablonlardakı:

* ``<style>…</style>`` blokları,
* ``src=`` olmayan icra olunan ``<script>…</script>`` blokları,
* ``onclick="…"`` / ``onsubmit="…"`` kimi inline hadisə atributları

brauzerdə ya bloklanır, ya da (nonce ilə) qaydanı pozur. Audit 2026-09-28
FQ-FE-2: CLAUDE.md-dəki köhnə ``grep -E '(?!…)'`` əmri PCRE look-ahead
işlətdiyi üçün heç işləmirdi; bu skript onun işlək əvəzidir. FQ-FE-1: inline
``on*=`` atributları da tutulur (CSP onları səssizcə bloklayır — məs. silmə
təsdiqi görünmədən forma göndərilirdi).

İcazəli (sayılmır):

* ``<script src="…">`` — xarici fayl;
* ``<script type="application/json">`` / ``application/ld+json`` — data bloku
  (icra olunmur);
* ``{# … #}``, ``{% comment %}…{% endcomment %}`` və ``<!-- … -->`` şərhləri;
* e-poçt şablonları (``templates/emails/**``, ``*/templates/*/emails/**``) —
  poçt klientləri xarici CSS yükləmir, CSP orada tətbiq olunmur.

İstifadə
--------
    python scripts/check_inline_assets.py          # tapıntı varsa exit 1
    python scripts/check_inline_assets.py --quiet  # yalnız exit kodu + say
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_GLOBS = ("apps/**/templates/**/*.html", "templates/**/*.html")

# İcra olunmayan data bloklarının `type` dəyərləri.
DATA_SCRIPT_TYPES = {"application/json", "application/ld+json"}

_DJANGO_COMMENT = re.compile(r"\{#.*?#\}", re.S)
_DJANGO_BLOCK_COMMENT = re.compile(r"\{%\s*comment\b.*?%\}.*?\{%\s*endcomment\s*%\}", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_ASSET_TAG = re.compile(r"<(script|style)\b([^>]*)>(.*?)</\1\s*>", re.I | re.S)
_SRC_ATTR = re.compile(r"\bsrc\s*=", re.I)
_TYPE_ATTR = re.compile(r"""\btype\s*=\s*["']?([^"'\s>]+)""", re.I)
_OPEN_TAG = re.compile(r"<[a-zA-Z][\w:-]*\b[^>]*>", re.S)
_EVENT_ATTR = re.compile(r"""\s(on[a-z]+)\s*=\s*["']""", re.I)


def _is_email_template(rel: str) -> bool:
    return rel.startswith("templates/emails/") or "/emails/" in rel


def _strip_comments(text: str) -> str:
    """Şərhləri eyni sayda sətir sonu ilə əvəzləyir (sətir nömrələri dəyişməsin)."""

    def blank(match: re.Match) -> str:
        return "\n" * match.group(0).count("\n")

    for pattern in (_DJANGO_BLOCK_COMMENT, _DJANGO_COMMENT, _HTML_COMMENT):
        text = pattern.sub(blank, text)
    return text


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_text(text: str) -> list[tuple[int, str]]:
    """Bir şablon mətnində (sətir, səbəb) siyahısı qaytarır."""
    text = _strip_comments(text)
    findings: list[tuple[int, str]] = []

    # 1) <script>/<style> blokları. Onların məzmunu sonrakı atribut
    #    skanından çıxarılır (JSON içindəki "onX=" yalançı tapıntı verməsin).
    def check_block(match: re.Match) -> str:
        name, attrs = match.group(1).lower(), match.group(2)
        line = _line_of(text, match.start())
        if name == "style":
            findings.append((line, "inline <style> bloku"))
        elif not _SRC_ATTR.search(attrs):
            type_match = _TYPE_ATTR.search(attrs)
            script_type = type_match.group(1).lower() if type_match else ""
            if script_type not in DATA_SCRIPT_TYPES:
                findings.append((line, "src-siz icra olunan <script> bloku"))
        opening = match.group(0)[: match.start(3) - match.start()]
        return opening + "\n" * match.group(3).count("\n") + "</" + match.group(1) + ">"

    scrubbed = _ASSET_TAG.sub(check_block, text)

    # 2) Açılış teqlərində inline hadisə atributları (onclick=, onsubmit= …).
    for tag in _OPEN_TAG.finditer(scrubbed):
        for attr in _EVENT_ATTR.finditer(tag.group(0)):
            line = _line_of(scrubbed, tag.start() + attr.start(1))
            findings.append((line, f"inline hadisə atributu {attr.group(1).lower()}="))

    return sorted(findings)


def iter_templates(root: Path = ROOT):
    seen = set()
    for pattern in TEMPLATE_GLOBS:
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root).as_posix()
            if rel in seen or _is_email_template(rel):
                continue
            seen.add(rel)
            yield rel, path


def scan(root: Path = ROOT) -> dict[str, list[tuple[int, str]]]:
    result: dict[str, list[tuple[int, str]]] = {}
    for rel, path in iter_templates(root):
        hits = scan_text(path.read_text(encoding="utf-8", errors="ignore"))
        if hits:
            result[rel] = hits
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quiet", action="store_true", help="yalnız yekun sayı çap et")
    args = parser.parse_args(argv)

    findings = scan()
    total = sum(len(hits) for hits in findings.values())
    if not args.quiet:
        for rel, hits in findings.items():
            for line, reason in hits:
                print(f"{rel}:{line}: {reason}")
    if total:
        print(f"❌ {total} inline CSS/JS tapıntısı ({len(findings)} faylda) — xarici static fayla çıxarın.")
        return 1
    print("✅ Şablonlarda inline <script>/<style> və on*= atributu yoxdur.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
