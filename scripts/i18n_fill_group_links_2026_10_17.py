#!/usr/bin/env python3
"""EMSArena i18n — qruplar reyestri: ortaq ana / alt qrup işarəsi (QA-2 F-16, 2026-10-17).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

GR = "accounts.groups"

ENTRIES = {
    GR: {
        "alt qrup · ana: %(parent)s": {
            "en": "subgroup · parent: %(parent)s",
            "ru": "подгруппа · основная: %(parent)s",
            "tr": "alt grup · ana: %(parent)s",
            "de": "Untergruppe · Hauptgruppe: %(parent)s",
        },
        "ortaq qrup · alt qruplar: %(n)s": {
            "en": "shared group · subgroups: %(n)s",
            "ru": "общая группа · подгрупп: %(n)s",
            "tr": "ortak grup · alt gruplar: %(n)s",
            "de": "Gemeinsame Gruppe · Untergruppen: %(n)s",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
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
