#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-12 (MR-000277): RİM «Yeni hesab» tələbəni də FİN-siz açır — FİN sahəsinin ipucu.

Sahib: «FİN olmadan əlavə et o tələbəni». ``django`` kataloquna (``profile.rim``) beş dildə əlavə edir;
AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_rim_student_without_fin_2026_11_12.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_R = "profile.rim"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (
        "django",
        _R,
        "Bilinmirsə boş qala bilər — FİN-i sonradan RİM-də hesabı redaktə edərək və ya tələbə ilk girişdə özü yazır.",
    ): (
        "May be left empty if unknown — the FIN can be added later by editing the account in RİM, "
        "or the student enters it at first login.",
        "Если неизвестен, можно оставить пустым — ФИН позже вносится при редактировании учётной записи в RİM "
        "или студент вводит его сам при первом входе.",
        "Bilinmiyorsa boş bırakılabilir — FİN daha sonra RİM'de hesap düzenlenerek eklenir veya öğrenci ilk "
        "girişte kendisi yazar.",
        "Kann leer bleiben, falls unbekannt — die FIN wird später beim Bearbeiten des Kontos im RİM ergänzt "
        "oder der Studierende gibt sie bei der ersten Anmeldung selbst ein.",
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
