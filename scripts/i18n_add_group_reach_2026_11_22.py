#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-22: öz qrupunun başqa bölmədəki jurnalı (jurnal siyahısının etiketi).

Sahib (RİM rəhbəri): tyutor / laborant / kafedra müdiri / dekanlıq öz qrupunun başqa bölmədə (başqa kafedra, başqa
məktəb, dil kohortu) keçən dərsinin jurnalına yalnız baxa bilsin (``registrar.journal_group_reach``). ``django``
kataloquna (``registrar.journal``) beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_group_reach_2026_11_22.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_J = "registrar.journal"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _J, "Başqa bölmə"): (
        "Another unit",
        "Другое подразделение",
        "Başka birim",
        "Andere Einheit",
    ),
    ("django", _J, "Qrupunuzun tələbələrinin başqa bölmədəki dərsi — yalnız baxış"): (
        "A lesson of your group's students in another unit — view only",
        "Занятие студентов вашей группы в другом подразделении — только просмотр",
        "Grubunuzun öğrencilerinin başka birimdeki dersi — yalnızca görüntüleme",
        "Unterricht der Studierenden Ihrer Gruppe in einer anderen Einheit — nur Ansicht",
    ),
}


def main():
    for domain in ("django",):
        for lang in LOCALES:
            path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            po = polib.pofile(path)
            existing = {(e.msgctxt, e.msgid) for e in po}
            added = 0
            for (dom, ctx, msgid), (en, ru, tr, de) in STRINGS.items():
                if dom != domain or (ctx, msgid) in existing:
                    continue
                msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
                entry = polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr)
                if "%(" in msgid:
                    entry.flags.append("python-format")
                po.append(entry)
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()
