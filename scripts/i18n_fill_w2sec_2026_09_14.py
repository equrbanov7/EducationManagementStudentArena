#!/usr/bin/env python3
"""EMSArena i18n — wave 2 təhlükəsizlik qalıqları (`w2sec`, 2026-09-14, audit F-06).

`core/upload_security.py` məzmun imzası yoxlamaları üçün iki yeni xəta mətni
(`upload.security.error` konteksti):

* şəkil sahəsində Pillow/magic-bytes uyğunsuzluğu;
* allow-list-li sənəd sahəsində bəyan edilən tip ↔ imza uyğunsuzluğu.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir və
idempotentdir. TR qarşılıqları QƏSDƏN AZ mənbədən fərqlidir (i18n qapısı
`msgstr == msgid` sətrini «tərcümə olunmamış» sayır).

İstifadə:  python scripts/i18n_fill_w2sec_2026_09_14.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CTX = "upload.security.error"

ENTRIES = {
    CTX: {
        "Fayl məzmunu bəyan edilən şəkil formatına uyğun deyil.": {
            "en": "The file content does not match the declared image format.",
            "ru": "Содержимое файла не соответствует заявленному формату изображения.",
            "tr": "Dosya içeriği bildirilen görsel biçimiyle eşleşmiyor.",
        },
        "Fayl məzmunu bəyan edilən fayl tipinə uyğun deyil.": {
            "en": "The file content does not match the declared file type.",
            "ru": "Содержимое файла не соответствует заявленному типу файла.",
            "tr": "Dosya içeriği bildirilen dosya türüyle eşleşmiyor.",
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
