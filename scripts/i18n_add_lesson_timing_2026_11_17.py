#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-17: dərsin vaxt məlumatı (yalnız əməkdaşa) + əməkdaş ixracı.

Sahib: jurnalda əməkdaş dərsin başladıldığı saatı, saat aralığını və saat sayını görsün; xlsx ixracında da olsun.
``django`` kataloquna beş dildə; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_lesson_timing_2026_11_17.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_J = "registrar.journal"
_L = "registrar.lessons_log"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_J, "Dərs başladılıb"): ("Lesson started", "Занятие начато", "Ders başlatıldı", "Unterricht begonnen"),
    (_L, "Dərs başladılıb"): ("Lesson started", "Занятие начато", "Ders başlatıldı", "Unterricht begonnen"),
    (_J, "Dərs saatı"): ("Lesson time", "Время занятия", "Ders saati", "Unterrichtszeit"),
    (_J, "Akademik saat"): ("Academic hours", "Академические часы", "Akademik ders saati", "Unterrichtsstunden"),
    (_J, "Bəli"): ("Yes", "Да", "Evet", "Ja"),
    (_J, "Dərslər"): ("Lessons", "Занятия", "Dersler", "Unterrichtseinheiten"),
    (_J, "Dərs növü"): ("Lesson type", "Тип занятия", "Ders türü", "Unterrichtsart"),
    (_J, "köhnə sistemdən"): ("from the old system", "из старой системы", "eski sistemden", "aus dem alten System"),
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
