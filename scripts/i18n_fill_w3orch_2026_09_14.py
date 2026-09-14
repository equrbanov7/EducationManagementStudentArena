#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-14 gecə dalğası, orkestrator əlavələri (djangojs).

`testQuestionBank.js` fayl-növü xəbərdarlığı `.docx` idxalını da qeyd edir.
⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız əlavə edir və idempotentdir.
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "djangojs": {
        "Bu fayl növü təhlükəsizlik səbəbi ilə qəbul edilmir. Yalnız .pdf / .docx / .txt / .png / .jpg yükləyin.": {
            "en": "This file type is not accepted for security reasons. Upload only .pdf / .docx / .txt / .png / .jpg.",
            "ru": "Этот тип файла не принимается по соображениям безопасности. Загружайте только .pdf / .docx / .txt / .png / .jpg.",
            "tr": "Bu dosya türü güvenlik nedeniyle kabul edilmiyor. Yalnızca .pdf / .docx / .txt / .png / .jpg yükleyin.",
        },
    }
}


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    for domain, messages in ENTRIES.items():
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        blocks, added = [], 0
        for msgid, translations in messages.items():
            if f'msgid "{esc(msgid)}"\n' in text:
                continue
            msgstr = translations.get(lang) or msgid
            blocks.append(f'msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1
        if blocks:
            text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        print(f"{domain}/{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
