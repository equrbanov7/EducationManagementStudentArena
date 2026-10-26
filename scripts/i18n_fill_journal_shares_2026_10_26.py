#!/usr/bin/env python3
"""EMSArena i18n — bölünmüş jurnal: çip, POST rəddi, pay mənbəyi, model adı (sahib 2026-10-26).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur); sonra
`compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ENTRIES = {
    "registrar.journal_share": {
        "Bölünmüş jurnal: yalnız sizin tələbələriniz / dərs növləriniz göstərilir": {
            "en": "Shared journal: only your students / lesson types are shown",
            "ru": "Разделённый журнал: показаны только ваши студенты / виды занятий",
            "tr": "Paylaşılan dergi: yalnızca sizin öğrencileriniz / ders türleriniz gösterilir",
            "de": "Geteiltes Journal: Nur Ihre Studierenden / Lehrveranstaltungsarten werden angezeigt",
        },
        "Bu xana bölünmüş jurnalda sizin payınıza aid deyil.": {
            "en": "This cell is not part of your share of the shared journal.",
            "ru": "Эта ячейка не относится к вашей части разделённого журнала.",
            "tr": "Bu hücre paylaşılan dergideki payınıza ait değil.",
            "de": "Diese Zelle gehört nicht zu Ihrem Anteil am geteilten Journal.",
        },
        "Köhnə sistem": {
            "en": "Legacy system",
            "ru": "Старая система",
            "tr": "Eski sistem",
            "de": "Altsystem",
        },
        "Əl ilə": {
            "en": "Manual",
            "ru": "Вручную",
            "tr": "Elle",
            "de": "Manuell",
        },
    },
    "registrar.model.journal_share.meta": {
        "jurnal payı": {
            "en": "journal share",
            "ru": "часть журнала",
            "tr": "dergi payı",
            "de": "Journalanteil",
        },
        "jurnal payları": {
            "en": "journal shares",
            "ru": "части журнала",
            "tr": "dergi payları",
            "de": "Journalanteile",
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
            msgstr = translations.get("az", msgid) if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
