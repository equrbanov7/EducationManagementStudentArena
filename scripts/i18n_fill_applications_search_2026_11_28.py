#!/usr/bin/env python3
"""«Müraciətlərim» axtarışı başqa bölmədə tapılanda göstərilən mətn: yalnız yeni msgid-i əlavə edir."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")

ENTRIES = {
    "django": {
        "applications": {
            "Axtarışa uyğun müraciət başqa bölmədədir:": {
                "en": "Matching applications are in another section:",
                "ru": "Подходящие обращения находятся в другом разделе:",
                "tr": "Aramaya uygun başvuru başka bir bölümde:",
                "de": "Passende Anträge befinden sich in einem anderen Bereich:",
            },
        },
    },
}


def quote(text):
    return json.dumps(text, ensure_ascii=False)


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
                    lines = ["msgctxt " + quote(context)] if context else []
                    lines += ["msgid " + quote(msgid), "msgstr " + quote(value)]
                    blocks.append("\n".join(lines) + "\n")
            if blocks:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(blocks))
            counts[f"{domain}/{lang}"] = len(blocks)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    fill()
