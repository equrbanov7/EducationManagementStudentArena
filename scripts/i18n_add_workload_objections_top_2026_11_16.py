#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-16: «Yük bölgüsü» müəllim etirazları yuxarıda (açıq sayı + bağlanmışlar).

Sahib: «etirazlar aşağı düşür, görmək olmur». ``django`` kataloquna (``accounts.workload``) beş dildə
əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_workload_form_filter_2026_11_15.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_W = "accounts.workload"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _W, "%(n)s açıq"): ("%(n)s open", "%(n)s открыто", "%(n)s açık", "%(n)s offen"),
    ("django", _W, "Bağlanmış etirazlar"): (
        "Closed objections",
        "Закрытые возражения",
        "Kapatılmış itirazlar",
        "Geschlossene Einwände",
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
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()
