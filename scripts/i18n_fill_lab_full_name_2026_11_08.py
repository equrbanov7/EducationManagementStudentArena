#!/usr/bin/env python3
"""Lab qrupunun tam adı «236 SBİO · Lab-1» (sahib 2026-11-08): yalnız yeni msgid-i əlavə edir."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")
MSGID = "%(group)s · Lab-%(n)s"
VALUES = {
    "az": MSGID,
    "en": "%(group)s · Lab group %(n)s",
    "ru": "%(group)s · Лаб-%(n)s",
    "tr": "%(group)s · Lab-%(n)s grubu",
    "de": "%(group)s · Laborgruppe %(n)s",
}


def fill():
    counts = {}
    for lang in LANGS:
        path = BASE / "locale" / lang / "LC_MESSAGES" / "django.po"
        existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
        if ("registrar.lab_groups", MSGID) in existing:
            counts[lang] = 0
            continue
        block = "\n".join(
            [
                "#, python-format",
                'msgctxt "registrar.lab_groups"',
                "msgid " + json.dumps(MSGID, ensure_ascii=False),
                "msgstr " + json.dumps(VALUES[lang], ensure_ascii=False),
            ]
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + block + "\n")
        counts[lang] = 1
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    fill()
