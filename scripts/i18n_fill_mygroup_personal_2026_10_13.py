#!/usr/bin/env python3
"""EMSArena i18n — «Qrupum» yalnız şəxsi davamiyyət (sahib 2026-10-13 «ancaq şəxsi görünsün»).

`apps/accounts/templates/accounts/profile/sections/_my_group.html` — yeni mətnlər (az msgstr = msgid).
⚠️ `makemessages` İŞLƏDİLMİR — idempotent; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_mygroup_personal_2026_10_13.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CTX = "accounts.my_group"

ENTRIES = {
    CTX: {
        "Qrup yoldaşlarının yalnız adı və tələbə nömrəsi görünür; davamiyyət şəxsi məlumatdır və yalnız özünüzə göstərilir.": {
            "en": "Only classmates' names and student numbers are shown; attendance is personal and shown only to you.",
            "ru": "Показаны только имена и номера студентов группы; посещаемость — личные данные и видна только вам.",
            "tr": "Grup arkadaşlarının yalnızca adı ve öğrenci numarası görünür; devamsızlık kişisel bilgidir ve yalnızca size gösterilir.",
        },
        "Mənim davamiyyətim": {"en": "My attendance", "ru": "Моя посещаемость", "tr": "Devamsızlığım"},
        "%(period)s %(year)s — qayıb saatı və dərs saatına nisbəti (faiz).": {
            "en": "%(period)s %(year)s — absence hours and their share of lesson hours (percent).",
            "ru": "%(period)s %(year)s — часы пропусков и их доля от учебных часов (процент).",
            "tr": "%(period)s %(year)s — devamsızlık saati ve ders saatine oranı (yüzde).",
        },
        "Fənn üzrə davamiyyətim": {
            "en": "My attendance by subject",
            "ru": "Моя посещаемость по предметам",
            "tr": "Ders bazında devamsızlığım",
        },
        "Fənn": {"en": "Subject", "ru": "Предмет", "tr": "Ders"},
        "Qayıb (saat)": {"en": "Absence (hours)", "ru": "Пропуски (часы)", "tr": "Devamsızlık (saat)"},
        "Faiz": {"en": "Percent", "ru": "Процент", "tr": "Yüzde"},
        "Ümumi": {"en": "Total", "ru": "Итого", "tr": "Toplam"},
        "Cari tədris dövrü müəyyən edilməyib.": {
            "en": "The current academic period is not set.",
            "ru": "Текущий учебный период не определён.",
            "tr": "Geçerli öğretim dönemi belirlenmemiş.",
        },
        "Qrup yoldaşları": {"en": "Classmates", "ru": "Одногруппники", "tr": "Grup arkadaşları"},
        "%(group)s qrupunun tələbələri": {
            "en": "Students of group %(group)s",
            "ru": "Студенты группы %(group)s",
            "tr": "%(group)s grubunun öğrencileri",
        },
        "siz": {"en": "you", "ru": "вы", "tr": "Siz"},
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
