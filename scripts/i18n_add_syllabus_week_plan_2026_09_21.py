#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-21: sillabus həftəlik cədvəlinin plandan özü
tənzimlənməsi («+ Sətir əlavə et», «əlavə» damğası, izah) və cədvəl
redaktorunda fənn siyahısının müəllimə görə yenilənməsi izahı.
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_syllabus_week_plan_2026_09_21.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

STRINGS = {
    ("accounts.syllabus", "əlavə"): ("extra", "дополнительно", "ek"),
    ("accounts.syllabus", "Sətir əlavə et"): ("Add a row", "Добавить строку", "Satır ekle"),
    (
        "accounts.syllabus",
        "Sətir sayı tədris planının saatından özü hesablanır (bir dərs = 2 saat); lazım olsa əlavə sətir açın.",
    ): (
        "The number of rows is derived from the curriculum hours (one lesson = 2 hours); add extra rows if needed.",
        "Число строк вычисляется из часов учебного плана (одно занятие = 2 часа); при необходимости добавьте строки.",
        "Satır sayısı ders planındaki saatten otomatik hesaplanır (bir ders = 2 saat); gerekirse ek satır açın.",
    ),
    (
        "accounts.schedule_manage",
        "Müəllim seçiləndə siyahı onun dərs yükü və açılışları ilə, seçilməyəndə qrupun tədris planı və açıq fənn açılışları ilə məhduddur.",
    ): (
        "With a teacher selected the list is limited to their teaching load and offerings; otherwise to the group's curriculum and open course offerings.",
        "При выбранном преподавателе список ограничен его нагрузкой и открытыми курсами; иначе — учебным планом группы и открытыми курсами.",
        "Öğretmen seçildiğinde liste onun ders yükü ve açılan dersleriyle, seçilmediğinde grubun ders planı ve açık derslerle sınırlıdır.",
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
