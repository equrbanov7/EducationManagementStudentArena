#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-18: apellyasiya balını RİM rəhbəri və İmtahan Mərkəzinin rəhbəri / işçisi yazır.

Sahib: «RİM rəhbəri, İmtahan Mərkəzinin rəhbəri və İmtahan Mərkəzinin işçisi burada işləyə bilməlidir və əlavə
olaraq apellyasiya xanasını da yaza bilməlidir». ``django`` kataloquna beş dildə; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_exam_appeal_staff_2026_11_18.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_E = "registrar.exam_score_entry"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_E, "Apellyasiya balını yalnız RİM rəhbəri və İmtahan Mərkəzinin rəhbəri / işçisi yazır."): (
        "Only the head of the Registrar and the Exam Center head / staff enter an appeal score.",
        "Балл апелляции вносят только руководитель РИМ и руководитель / сотрудник Экзаменационного центра.",
        "İtiraz puanını yalnızca RİM yöneticisi ve Sınav Merkezi yöneticisi / çalışanı yazar.",
        "Eine Einspruchspunktzahl tragen nur die RİM-Leitung und die Leitung / Mitarbeitende des Prüfungszentrums ein.",
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
