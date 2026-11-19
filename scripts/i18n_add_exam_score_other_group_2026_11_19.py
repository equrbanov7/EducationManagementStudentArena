#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-19: imtahan balı siyahısında tələbənin cari qrupu nişanı (MR-555/558).

``django`` kataloquna beş dildə;
AZ msgstr = msgid. İdempotent. İstifadə:  python scripts/i18n_add_exam_score_other_group_2026_11_19.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_E = "registrar.exam_score_entry"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_E, "Tələbənin cari qrupu"): (
        "Student's current group",
        "Текущая группа студента",
        "Öğrencinin mevcut grubu",
        "Aktuelle Gruppe des Studierenden",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt or "", e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
