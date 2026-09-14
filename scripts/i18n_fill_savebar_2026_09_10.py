#!/usr/bin/env python3
"""EMSArena i18n — profil redaktəsi əməliyyat panelinin «saxlanılıb» nişanı.

2026-09-10 sahib rəyi: panel FIXED qalsın, amma status nişanı görünüb-yox
olduqda düymələr sürüşməsin. Ona görə nişanın İKİNCİ (sakit) vəziyyəti əlavə
olundu və o, həmişə yer tutur.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir və idempotentdir.

İstifadə:  python scripts/i18n_fill_savebar_2026_09_10.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "profile.edit_v2": {
        "Bütün dəyişikliklər yadda saxlanılıb": {
            "en": "All changes are saved",
            "ru": "Все изменения сохранены",
            "tr": "Tüm değişiklikler kaydedildi",
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
