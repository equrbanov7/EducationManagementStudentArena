#!/usr/bin/env python3
"""Patokun ikinci/üçüncü qrupunun mühazirə xətti («Dərs yükü» kartı): yalnız yeni msgid-ləri əlavə edir.

Mövcud tərcümələrə toxunmur (sahib 2026-11-07).
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
    "djangojs": {
        "": {
            "Patok": t("Joint lecture", "Поток", "Ortak ders", "Gemeinsame Vorlesung"),
            "Patok · %(groups)s ilə birlikdə": t(
                "Joint lecture · together with %(groups)s",
                "Поток · вместе с %(groups)s",
                "Ortak ders · %(groups)s ile birlikte",
                "Gemeinsame Vorlesung · zusammen mit %(groups)s",
            ),
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
                    lines = ["#, javascript-format"] if "%" in msgid else []
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
