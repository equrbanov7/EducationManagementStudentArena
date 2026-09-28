#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-28 audit remediasiyası, iş paketi B1 (jurnal bütövlüyü).

Əlavə olunan mətnlər:
  * `registrar.finals` — rəqəm olmayan imtahan/təkrar/bonus balı rədd edilir (J-01);
  * `registrar.journal_finals` — «Yekun» əməlində yazılmayan xanaların xülasəsi (J-01)
    və rəqəm olmayan komponent/kollokvium xanaları (J-03);
  * `registrar.journal_lessons` — dərs redaktəsində saat aralığı (J-02);
  * `registrar.correction` — qayıb/üzrlü qayıb xanasına sənədli bal düzəlişi (J-05).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_b1_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

FIN = "registrar.finals"
JF = "registrar.journal_finals"
JL = "registrar.journal_lessons"
COR = "registrar.correction"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    FIN: {
        "Bal rəqəm olmalıdır.": {
            "az": "Bal rəqəm olmalıdır.",
            "en": "The score must be a number.",
            "ru": "Балл должен быть числом.",
            "tr": "Puan sayı olmalıdır.",
        },
    },
    JF: {
        "%(n)s xana yazılmadı: %(details)s. Yazılmış imtahan balının dəyişdirilməsi "
        "İmtahan Mərkəzinin bal daxiletmə səhifəsindən, təqdimatla aparılır.": {
            "az": "%(n)s xana yazılmadı: %(details)s. Yazılmış imtahan balının dəyişdirilməsi "
            "İmtahan Mərkəzinin bal daxiletmə səhifəsindən, təqdimatla aparılır.",
            "en": "%(n)s cell(s) were not saved: %(details)s. An exam score that is already recorded "
            "can only be changed on the Exam Centre score entry page, with a supporting document.",
            "ru": "Не сохранено ячеек: %(n)s: %(details)s. Уже внесённый экзаменационный балл "
            "изменяется только на странице ввода баллов Экзаменационного центра, с подтверждающим документом.",
            "tr": "%(n)s hücre kaydedilmedi: %(details)s. Girilmiş sınav puanı yalnızca Sınav Merkezinin "
            "puan girişi sayfasından, belge ile değiştirilebilir.",
        },
        "%(n)s xana yazılmadı — bal rəqəm olmalıdır; mövcud bal dəyişdirilmədi.": {
            "az": "%(n)s xana yazılmadı — bal rəqəm olmalıdır; mövcud bal dəyişdirilmədi.",
            "en": "%(n)s cell(s) were not saved — the score must be a number; the existing score was kept.",
            "ru": "Не сохранено ячеек: %(n)s — балл должен быть числом; прежний балл не изменён.",
            "tr": "%(n)s hücre kaydedilmedi — puan sayı olmalıdır; mevcut puan değiştirilmedi.",
        },
    },
    JL: {
        "Dərs saatı müsbət tam ədəd olmalıdır.": {
            "az": "Dərs saatı müsbət tam ədəd olmalıdır.",
            "en": "Lesson hours must be a positive whole number.",
            "ru": "Количество часов занятия должно быть целым положительным числом.",
            "tr": "Ders saati pozitif bir tam sayı olmalıdır.",
        },
        "Dərs saatı 1 ilə %(max)s arasında olmalıdır.": {
            "az": "Dərs saatı 1 ilə %(max)s arasında olmalıdır.",
            "en": "Lesson hours must be between 1 and %(max)s.",
            "ru": "Количество часов занятия должно быть от 1 до %(max)s.",
            "tr": "Ders saati 1 ile %(max)s arasında olmalıdır.",
        },
    },
    COR: {
        "Absent (or excused) cells hold no score — correct the attendance first.": {
            "az": "Qayıb (və ya üzrlü qayıb) xanasına bal yazılmır — əvvəlcə davamiyyəti düzəldin.",
            "en": "Absent (or excused) cells hold no score — correct the attendance first.",
            "ru": "В ячейку пропуска (в том числе уважительного) балл не ставится — сначала исправьте посещаемость.",
            "tr": "Devamsız (veya mazeretli) hücreye puan girilmez — önce devam durumunu düzeltin.",
        },
    },
}

# Mövcud səhv tərcüməni üstələmək lazım olan açarlar (yoxdur — hamısı yenidir).
FORCE: set = set()


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
