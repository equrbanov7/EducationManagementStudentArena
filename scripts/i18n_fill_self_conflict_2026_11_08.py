#!/usr/bin/env python3
"""Tələbə + heyət rolu qapısı (sahib 2026-11-08, ``organizations.self_conflict``) — yalnız yeni msgid."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")
CONTEXT = "organizations.self_conflict"
MSGID = (
    "Siz bu təşkilatda həm də tələbəsiniz: işçi rolu ilə özünüzə, öz qrupunuza və öz jurnallarınıza "
    "aid əməliyyat apara bilməzsiniz."
)
VALUES = {
    "az": MSGID,
    "en": (
        "You are also a student in this organization: with a staff role you cannot act on yourself, "
        "your own group or your own journals."
    ),
    "ru": (
        "Вы также являетесь студентом этой организации: со служебной ролью нельзя выполнять действия "
        "в отношении себя, своей группы и своих журналов."
    ),
    "tr": (
        "Bu kurumda aynı zamanda öğrencisiniz: personel rolüyle kendinize, kendi grubunuza ve kendi "
        "yoklama defterlerinize ilişkin işlem yapamazsınız."
    ),
    "de": (
        "Sie sind in dieser Organisation auch Studierende(r): Mit einer Mitarbeiterrolle können Sie keine "
        "Aktionen an sich selbst, Ihrer eigenen Gruppe oder Ihren eigenen Journalen ausführen."
    ),
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
