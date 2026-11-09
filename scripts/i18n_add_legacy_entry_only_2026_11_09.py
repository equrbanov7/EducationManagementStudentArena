#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-09: köçürülmüş imtahansız xarici dil səviyyə kursu — «yekun = giriş balı» statusu
(``apps/registrar/legacy_entry_only.py``). Beş kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_legacy_entry_only_2026_11_09.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")

_E = "registrar.eligibility"

STRINGS = {
    (_E, "Köhnə sistem: imtahansız kurs, yekun = giriş balı"): (
        "Old system: course without an exam, final = entry score",
        "Старая система: курс без экзамена, итог = входной балл",
        "Eski sistem: sınavsız ders, final = giriş puanı",
        "Altes System: Kurs ohne Prüfung, Endnote = Eingangspunktzahl",
    ),
    (
        _E,
        "Köhnə sistemdə xarici dil səviyyə kursları imtahansız aparılıb: yekun bal giriş balına bərabərdir və fənn "
        "keçilmiş sayılır. Bu nəticə ÜOMG-yə daxil edilmir.",
    ): (
        "In the old system, foreign-language level courses had no exam: the final score equals the entry score and "
        "the course counts as passed. This result is not included in the GPA.",
        "В старой системе уровневые курсы иностранного языка проводились без экзамена: итоговый балл равен входному, "
        "предмет считается сданным. Этот результат не входит в средний балл (ÜOMG).",
        "Eski sistemde yabancı dil seviye dersleri sınavsız yürütülmüştür: final puanı giriş puanına eşittir ve ders "
        "geçilmiş sayılır. Bu sonuç genel not ortalamasına (ÜOMG) dahil edilmez.",
        "Im alten System wurden Fremdsprachen-Niveaukurse ohne Prüfung geführt: die Endnote entspricht der "
        "Eingangspunktzahl und der Kurs gilt als bestanden. Dieses Ergebnis fließt nicht in den Notendurchschnitt (ÜOMG) ein.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
