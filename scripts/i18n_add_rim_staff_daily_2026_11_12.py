#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-12: RİM əməkdaşının gündəlik girişi, ``journal.direct_edit`` icazə etiketi.

Server (``django``, ``organizations.permission.label``) kataloquna beş dildə əlavə edir; AZ msgstr = msgid.
İdempotent. İstifadə:  python scripts/i18n_add_rim_staff_daily_2026_11_12.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_CTX = "organizations.permission.label"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_CTX, "Başqa müəllimin jurnalında birbaşa redaktə (dərs günü əlavə et / dəyiş / sil)"): (
        "Edit another teacher's journal directly (add / change / delete lesson days)",
        "Прямое редактирование журнала другого преподавателя (добавить / изменить / удалить день занятия)",
        "Başka öğretim elemanının yoklama defterini doğrudan düzenleme (ders günü ekle / değiştir / sil)",
        "Klassenbuch einer anderen Lehrkraft direkt bearbeiten (Unterrichtstag hinzufügen / ändern / löschen)",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
