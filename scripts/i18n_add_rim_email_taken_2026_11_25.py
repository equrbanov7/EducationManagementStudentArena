#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-25: RİM «Yeni yarat» — e-poçt unikal indeksi toqquşanda 500 yox, sahə xətası.

``django`` kataloquna (``profile.rim``) beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_rim_email_taken_2026_11_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_R = "profile.rim"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _R, "Bu e-poçt artıq başqa hesabdadır. Başqa ünvan yazın və ya boş saxlayın."): (
        "This e-mail already belongs to another account. Enter a different address or leave it empty.",
        "Этот e-mail уже принадлежит другой учётной записи. Укажите другой адрес или оставьте поле пустым.",
        "Bu e-posta zaten başka bir hesaba ait. Başka bir adres yazın veya boş bırakın.",
        "Diese E-Mail-Adresse gehört bereits zu einem anderen Konto. Geben Sie eine andere Adresse ein "
        "oder lassen Sie das Feld leer.",
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
