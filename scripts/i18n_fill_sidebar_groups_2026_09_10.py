#!/usr/bin/env python3
"""EMSArena i18n — kabinet sidebar-ının yeni qrup başlıqları (2026-09-10).

Sahib: «sidebar-a bax … onu yenə səliqəli bölmək olursa bölə bilərsən».
19 bəndlik «Universitet» qrupu üç məntiqli qrupa ayrıldı, «Tələbə Xidmətləri»
insan reyestrlərini də əhatə edəcək şəkildə genişləndi, «İdarəetmə» isə
platforma səthlərindən ayrıldı. Yeni başlıqlar burada 4 dilə doldurulur.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir və idempotentdir.

İstifadə:  python scripts/i18n_fill_sidebar_groups_2026_09_10.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "profile.sidebar": {
        "Dərs və cədvəl": {
            "en": "Lessons & schedule",
            "ru": "Занятия и расписание",
            "tr": "Dersler ve program",
        },
        "Dərs yükü": {
            "en": "Teaching load",
            "ru": "Учебная нагрузка",
            "tr": "Ders yükü",
        },
        "Sillabus və sual": {
            "en": "Syllabus & questions",
            "ru": "Силлабус и вопросы",
            "tr": "İzlence ve sorular",
        },
        "İmtahan və qiymətləndirmə": {
            "en": "Exams & assessment",
            "ru": "Экзамены и оценивание",
            "tr": "Sınavlar ve değerlendirme",
        },
        "Tələbə və heyət": {
            "en": "Students & staff",
            "ru": "Студенты и персонал",
            "tr": "Öğrenciler ve personel",
        },
        # ⚠️ «Sistem» tək sözü türkcədə eyni qalır — i18n qapısı `identity`
        # borcunu artırdığına görə başlıq «Sistem idarəetməsi» seçildi.
        "Sistem idarəetməsi": {
            "en": "System administration",
            "ru": "Администрирование системы",
            "tr": "Sistem yönetimi",
        },
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
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
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
