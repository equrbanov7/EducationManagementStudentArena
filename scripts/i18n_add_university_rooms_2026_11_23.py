"""EMSArena i18n — 2026-11-23: «Universitet otaqları» bölməsi, otaq dialoqunda bina seçimi və təkrar ad xətası.

Sahib: «bina select option kimi çıxsın, eyni adlı otaq əlavə edə bilməyim; soldakı İmtahan zalları yazısını
Universitet otaqları kimi dəyiş». ``django`` kataloquna beş dildə; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_university_rooms_2026_11_23.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_R = "accounts.superadmin_exam_rooms"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("profile.section", "Universitet otaqları"): (
        "University rooms",
        "Аудитории университета",
        "Üniversite odaları",
        "Universitätsräume",
    ),
    (_R, "— Bina seçin —"): ("— Select building —", "— Выберите корпус —", "— Bina seçiniz —", "— Gebäude wählen —"),
    (_R, "Axtar…"): ("Search…", "Поиск…", "Ara…", "Suchen…"),
    (_R, "Uyğun nəticə yoxdur"): ("No matches", "Нет совпадений", "Eşleşme yok", "Keine Treffer"),
    ("exams.final_center.form", "Bu binada bu adla otaq artıq var."): (
        "A room with this name already exists in this building.",
        "В этом корпусе уже есть аудитория с таким названием.",
        "Bu binada bu adla bir oda zaten var.",
        "In diesem Gebäude gibt es bereits einen Raum mit diesem Namen.",
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
