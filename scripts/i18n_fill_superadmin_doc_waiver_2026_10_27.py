#!/usr/bin/env python3
"""EMSArena i18n — superadmin sənədsiz düzəliş (sahib 2026-10-27).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "core.superadmin_waiver": {
        "Superadmin: sənəd / əmr istəyə bağlıdır — boş qalsa avtomatik «Superadmin düzəlişi — sənədsiz» qeydi "
        "yazılır.": t(
            "Superadmin: the document / order is optional — if left empty, an automatic "
            "«Superadmin correction — no document» note is recorded.",
            "Суперадмин: документ / приказ необязателен — если поле пустое, автоматически записывается отметка "
            "«Исправление суперадмина — без документа».",
            "Süper yönetici: belge / emir isteğe bağlıdır — boş bırakılırsa otomatik olarak "
            "«Süper yönetici düzeltmesi — belgesiz» notu yazılır.",
            "Superadmin: Dokument / Anordnung ist optional — bleibt das Feld leer, wird automatisch der Vermerk "
            "«Superadmin-Korrektur — ohne Dokument» gespeichert.",
        ),
    },
    "registrar.guest_roster": {
        "SƏNƏD — TƏQDİMAT / SƏRƏNCAM (İSTƏYƏ BAĞLI)": t(
            "DOCUMENT — SUBMISSION / ORDER (OPTIONAL)",
            "ДОКУМЕНТ — ПРЕДСТАВЛЕНИЕ / РАСПОРЯЖЕНИЕ (НЕОБЯЗАТЕЛЬНО)",
            "BELGE — TEKLİF / EMİR (İSTEĞE BAĞLI)",
            "DOKUMENT — ANTRAG / ANORDNUNG (OPTIONAL)",
        ),
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
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
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
