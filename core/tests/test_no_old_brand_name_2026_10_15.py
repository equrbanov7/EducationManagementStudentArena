"""Köhnə məhsul adı («EMS Arena») istifadəçiyə görünən yerlərdə qalmamalıdır.

Sahib 2026-10-15: «EMS Arena köhnədir, onu sil. Olmasın heç yerdə, dəyiş o hissəni.»
Görünən ad «Qərbi Kaspi Universiteti» (təşkilat adı / ``SITE_BRAND_NAME``), məhsul sözü
isə «Elektron Universitet»dir.

Qapı yoxlayır:
* bütün şablonlar (``templates/`` + ``apps/*/templates/``) — şərhlər (``{# #}``,
  ``{% comment %}``, ``<!-- -->``) görünmür, ona görə sayılmır;
* bütün ``locale/*/LC_MESSAGES/*.po`` kataloqlarının ``msgstr``-ləri;
* ictimai sayt xəritəsi üslubu (``static/seo/*.xsl``) və köhnə loqo faylları.

``…@emsarena.com`` poçt ünvanlarına da istisna YOXDUR (sahib 2026-10-16: info@/support@/no-reply@
qutuları mövcud deyil — yeganə real qutular M365 verification@/recovery@-dur).
Daxili identifikatorlar (paket/konteyner/DB/kuki/keş adları, CSS/JS prefiksləri) yoxlanmır.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

import polib

BASE = Path(__file__).resolve().parents[2]
OLD_NAME_RE = re.compile(r"ems[ _-]?arena", re.IGNORECASE)
COMMENT_RES = (
    re.compile(r"\{#.*?#\}", re.DOTALL),
    re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL),
    re.compile(r"<!--.*?-->", re.DOTALL),
)
TEMPLATE_SUFFIXES = {".html", ".txt", ".xml", ".svg"}
OLD_LOGO_FILES = (
    "logo.png",
    "logo-horizontal.png",
    "logo-horizontal-light.png",
    "logo-stacked.png",
    "logo-stacked-light.png",
    "logo-mark.png",
    "logo-mark-light.png",
    "logo-square.png",
)


def _visible(text: str) -> str:
    for pattern in COMMENT_RES:
        text = pattern.sub("", text)
    return text


def _template_files():
    roots = [BASE / "templates", *sorted((BASE / "apps").glob("*/templates"))]
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in TEMPLATE_SUFFIXES:
                yield path


class OldBrandNameGuardTest(SimpleTestCase):
    def test_templates_do_not_show_the_old_product_name(self):
        offenders = []
        for path in _template_files():
            for lineno, line in enumerate(_visible(path.read_text(encoding="utf-8")).splitlines(), 1):
                if OLD_NAME_RE.search(line):
                    offenders.append(f"{path.relative_to(BASE)}:{lineno}: {line.strip()[:120]}")
        self.assertEqual(offenders, [], "Köhnə məhsul adı şablonda görünür:\n" + "\n".join(offenders))

    def test_catalog_translations_do_not_contain_the_old_product_name(self):
        offenders = []
        for path in sorted((BASE / "locale").glob("*/LC_MESSAGES/*.po")):
            for entry in polib.pofile(str(path)):
                if entry.obsolete:
                    continue
                for value in (entry.msgstr, *entry.msgstr_plural.values()):
                    if OLD_NAME_RE.search(value or ""):
                        offenders.append(f"{path.relative_to(BASE)}: {entry.msgctxt or ''}|{entry.msgid[:60]}")
        self.assertEqual(offenders, [], "Köhnə məhsul adı tərcümədə qalıb:\n" + "\n".join(offenders))

    def test_public_static_brand_assets_are_clean(self):
        for path in sorted((BASE / "static" / "seo").glob("*.xsl")):
            self.assertIsNone(OLD_NAME_RE.search(_visible(path.read_text(encoding="utf-8"))), str(path))
        for name in OLD_LOGO_FILES:
            self.assertFalse((BASE / "static" / "brand" / name).exists(), f"köhnə söz-nişanlı loqo: {name}")
