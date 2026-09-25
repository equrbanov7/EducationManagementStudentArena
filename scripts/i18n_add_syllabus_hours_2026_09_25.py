#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: sillabus redaktorunda əl ilə semestr saatı — dropdown + redaktə.

Sahib: «bir dəfə yazandan sonra edit etmək olmur» + «dropdown olsun, əl ilə yazılmasın».
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_syllabus_hours_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")
S = "accounts.syllabus"

STRINGS = {
    (S, "Bu fənn üçün tədris planı / dərs yükü saatı tapılmadı. Fənnin semestr saatını növ üzrə seçin:"): (
        "No curriculum / teaching-load hours were found for this subject. Choose the semester hours per lesson type:",
        "Для этого предмета не найдены часы учебного плана / нагрузки. Выберите семестровые часы по видам занятий:",
        "Bu ders için öğretim planı / ders yükü saati bulunamadı. Dönem saatini ders türüne göre seçin:",
    ),
    (
        S,
        "Tədris planında bu fənnin saatı tapılmadığı üçün saat əl ilə seçilib. Səhv seçilibsə dəyişin və yenidən "
        "yadda saxlayın:",
    ): (
        "The hours were chosen manually because the curriculum has no hours for this subject. If they are wrong, "
        "change them and save again:",
        "Часы выбраны вручную, так как в учебном плане нет часов для этого предмета. Если они неверны, измените их "
        "и сохраните снова:",
        "Öğretim planında bu dersin saati bulunmadığı için saat elle seçildi. Yanlışsa değiştirip yeniden kaydedin:",
    ),
    (S, "Ən azı bir dərs növü üçün saat seçin."): (
        "Choose hours for at least one lesson type.",
        "Выберите часы хотя бы для одного вида занятий.",
        "En az bir ders türü için saat seçin.",
    ),
    (S, "Saatı yenilə"): ("Update hours", "Обновить часы", "Saati güncelle"),
    (S, "saat"): ("h", "ч", "saat"),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
