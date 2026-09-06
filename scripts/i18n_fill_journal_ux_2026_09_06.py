#!/usr/bin/env python3
"""EMSArena i18n — jurnal UX düzəlişinin (2026-09-06) yeni istifadəçi mətnləri.

Elektron jurnal siyahısındakı filtr/axtarış yüklənmə vəziyyətinin mətni
(`registrar.journal` konteksti). İdempotent — mövcud girişə toxunmur.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir.
İstifadə:  python scripts/i18n_fill_journal_ux_2026_09_06.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "registrar.journal": {
        "Nəticələr yüklənir…": {
            "en": "Loading results…",
            "ru": "Загрузка результатов…",
            "tr": "Sonuçlar yükleniyor…",
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
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            probe = f'{head}msgid "{esc(msgid)}"\nmsgstr'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
