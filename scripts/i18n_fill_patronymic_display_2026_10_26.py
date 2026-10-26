#!/usr/bin/env python3
"""EMSArena i18n — ata adı profil/PIN axtarışında görünür (sahib 2026-10-26).

msgid AZ cümlədir → az msgstr = msgid. Mövcud açarlar atlanır (idempotent); sonra
`compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "profile.info": {
        "Ata adı": t("Patronymic", "Отчество", "Baba adı", "Vatersname"),
    },
    "exams.pin_lookup": {
        "Ad, soyad, ata adı və ya istifadəçi adı…": t(
            "First name, last name, patronymic or username…",
            "Имя, фамилия, отчество или имя пользователя…",
            "Ad, soyad, baba adı veya kullanıcı adı…",
            "Vorname, Nachname, Vatersname oder Benutzername…",
        ),
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    blocks = []
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
    if blocks:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.rstrip("\n") + "\n\n" + "\n".join(blocks))
    print(f"{lang}: +{len(blocks)} django")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
