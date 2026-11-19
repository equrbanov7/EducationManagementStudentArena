#!/usr/bin/env python3
"""Monitorinq rolu + jurnal dərs xanasında otaq (sahib 2026-11-19): yalnız yeni msgid-ləri əlavə edir.

Yeni mətn TƏKDİR — cədvəl slotundan götürülən otağın nişanı («cədvəl üzrə»). «Otaq» (``registrar.journal``)
artıq kataloqdadır; rol adları (``Role.display_name``) DB mətnidir, kataloqa düşmür. Mövcud tərcümələrə toxunmur.
"""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return dict(zip(LANGS[1:], (en, ru, tr, de)))


def quote(text):
    return json.dumps(text, ensure_ascii=False)


ENTRIES = {
    "django": {
        "registrar.journal": {
            "cədvəl üzrə": t("per timetable", "по расписанию", "ders programına göre", "laut Stundenplan"),
        },
    },
}


def fill():
    counts = {}
    for domain, contexts in ENTRIES.items():
        for lang in LANGS:
            path = BASE / "locale" / lang / "LC_MESSAGES" / f"{domain}.po"
            existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
            blocks = []
            for context, messages in contexts.items():
                for msgid, translations in messages.items():
                    if (context, msgid) in existing:
                        continue
                    value = msgid if lang == "az" else translations[lang]
                    lines = ["#, python-format"] if "%s" in msgid else []
                    if context:
                        lines.append("msgctxt " + quote(context))
                    lines += ["msgid " + quote(msgid), "msgstr " + quote(value)]
                    blocks.append("\n".join(lines) + "\n")
            if blocks:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(blocks))
            counts[f"{domain}/{lang}"] = len(blocks)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    fill()
