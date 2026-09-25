#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: təhlükəsizlik yoxlamasının düzəlişləri (H-1 imtahan kateqoriyası, sillabus rəsmi plan saatı).

Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_secfix_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

STRINGS = {
    (
        "exams.form.exam.error",
        "Fənnə bağlanan imtahan üçün kateqoriya seçin — jurnala yalnız «Final» imtahanının balı yazılır.",
    ): (
        "Choose a category for an exam linked to a subject — only «Final» exam scores are written to the journal.",
        "Выберите категорию для экзамена, привязанного к предмету, — в журнал записываются только баллы «Final».",
        "Bir derse bağlı sınav için kategori seçin — deftere yalnızca «Final» sınavının puanı yazılır.",
    ),
    (
        "accounts.syllabus",
        "Saat bölgüsü rəsmi tədris planından gəlir — dəyişiklik üçün kafedraya müraciət edin.",
    ): (
        "The hour split comes from the official curriculum plan — contact the chair to change it.",
        "Распределение часов берётся из официального учебного плана — для изменения обратитесь на кафедру.",
        "Saat dağılımı resmî öğretim planından gelir — değişiklik için bölüme başvurun.",
    ),
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
