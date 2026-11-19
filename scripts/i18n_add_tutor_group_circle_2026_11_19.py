#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-19: tyutorun «qrup dövrəsi» — iki yeni icazə açarının etiketi.

Sahib: «tyutora özəllik olaraq rol ver … bütün bu circle-i edə bilsin». ``django`` kataloquna
(``organizations.permission.label``) beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_tutor_group_circle_2026_11_19.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_P = "organizations.permission.label"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _P, "Öz qruplarının jurnallarında lab qruplarını idarə etmək"): (
        "Manage lab groups in journals of own groups",
        "Управлять лабораторными группами в журналах своих групп",
        "Kendi gruplarının yoklama defterlerinde laboratuvar gruplarını yönetmek",
        "Laborgruppen in den Journalen der eigenen Gruppen verwalten",
    ),
    ("django", _P, "Dil kafedrasında xarici dil səviyyə qrupu açmaq (öz tələbələri üçün)"): (
        "Open a foreign-language level group at a language department (for own students)",
        "Открывать группу уровня иностранного языка на языковой кафедре (для своих студентов)",
        "Dil bölümünde yabancı dil seviye grubu açmak (kendi öğrencileri için)",
        "Fremdsprachen-Niveaugruppe am Sprachlehrstuhl eröffnen (für eigene Studierende)",
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
