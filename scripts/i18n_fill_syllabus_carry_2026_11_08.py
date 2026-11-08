#!/usr/bin/env python3
"""Paylaşım mənbəyi «carry» (sahib 2026-11-08: təsdiqlənmiş sillabus müəllimin başqa qrupunda da) — yalnız yeni msgid."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")
CONTEXT = "syllabus.model"
MSGID = "Təsdiqlənmiş sillabus başqa qrupdan (avtomatik)"
VALUES = {
    "az": MSGID,
    "en": "Approved syllabus from another group (automatic)",
    "ru": "Утверждённый силлабус из другой группы (автоматически)",
    "tr": "Başka gruptan onaylı müfredat (otomatik)",
    "de": "Genehmigter Syllabus aus einer anderen Gruppe (automatisch)",
}


def fill():
    counts = {}
    for lang in LANGS:
        path = BASE / "locale" / lang / "LC_MESSAGES" / "django.po"
        existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
        if (CONTEXT, MSGID) in existing:
            counts[lang] = 0
            continue
        block = "\n".join(
            [
                f'msgctxt "{CONTEXT}"',
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
