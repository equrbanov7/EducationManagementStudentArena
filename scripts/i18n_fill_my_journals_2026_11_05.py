#!/usr/bin/env python3
"""EMSArena i18n — jurnal siyahısında «Mənim jurnallarım» düyməsi (sahib 2026-11-05).

Kontekst: ``registrar.journal``. msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız
çatışmayan blokları əlavə edir, idempotentdir. Sonra `.mo` faylları `msgfmt` ilə yığılır.

İstifadə:  python scripts/i18n_fill_my_journals_2026_11_05.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de, az=None):
    return {"en": en, "ru": ru, "tr": tr, "de": de, "az": az}


ENTRIES = {
    "registrar.journal": {
        "Mənim jurnallarım": t("My journals", "Мои журналы", "Defterlerim", "Meine Journale"),
        "hamısını göstər": t("show all", "показать все", "tümünü göster", "alle anzeigen"),
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain="django"):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = (translations.get("az") or msgid) if lang == "az" else translations[lang]
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for lang in LOCALES:
        fill(lang)
