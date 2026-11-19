#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-19: «Cari yükə bərpa et» formasında saat cəmi və gözləmə bildirişi.

``django`` kataloquna beş dildə;
AZ msgstr = msgid. İdempotent. İstifadə:  python scripts/i18n_add_history_restore_ui_2026_11_19.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_E = "workload.history_restore"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_E, "Cəmi"): ("Total", "Итого", "Toplam", "Summe"),
    (_E, "Yük bərpa olunur — bu bir az çəkə bilər, səhifəni bağlamayın."): (
        "Restoring the load — this may take a moment, please keep the page open.",
        "Нагрузка восстанавливается — это может занять немного времени, не закрывайте страницу.",
        "Yük geri yükleniyor — bu biraz sürebilir, sayfayı kapatmayın.",
        "Die Lehrlast wird wiederhergestellt — das kann etwas dauern, bitte die Seite geöffnet lassen.",
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
