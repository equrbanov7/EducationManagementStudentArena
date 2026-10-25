#!/usr/bin/env python3
"""EMSArena i18n — telefon sahəsi: ölkə seçicisi + ölkəyə uyğun yoxlama (2026-10-25).

Mənbə: `core/phone.py` (xəta mətnləri), `templates/partials/_phone_field.html` (seçici etiketləri).
msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

PH = "core.phone"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    PH: {
        "Telefon nömrəsini yazın.": t(
            "Enter the phone number.",
            "Введите номер телефона.",
            "Telefon numarasını yazın.",
            "Geben Sie die Telefonnummer ein.",
        ),
        "Telefon nömrəsi düzgün deyil (məs. %(example)s).": t(
            "The phone number is not valid (e.g. %(example)s).",
            "Номер телефона указан неверно (напр. %(example)s).",
            "Telefon numarası geçerli değil (örn. %(example)s).",
            "Die Telefonnummer ist ungültig (z. B. %(example)s).",
        ),
        "Nömrə çox qısadır (məs. %(example)s).": t(
            "The number is too short (e.g. %(example)s).",
            "Номер слишком короткий (напр. %(example)s).",
            "Numara çok kısa (örn. %(example)s).",
            "Die Nummer ist zu kurz (z. B. %(example)s).",
        ),
        "Nömrə çox uzundur (məs. %(example)s).": t(
            "The number is too long (e.g. %(example)s).",
            "Номер слишком длинный (напр. %(example)s).",
            "Numara çok uzun (örn. %(example)s).",
            "Die Nummer ist zu lang (z. B. %(example)s).",
        ),
        "Ölkə və ya kod axtar…": t(
            "Search country or code…",
            "Поиск страны или кода…",
            "Ülke veya kod ara…",
            "Land oder Vorwahl suchen…",
        ),
        "Uyğun ölkə tapılmadı": t(
            "No matching country",
            "Подходящая страна не найдена",
            "Eşleşen ülke bulunamadı",
            "Kein passendes Land gefunden",
        ),
        "Ölkə və zəng kodu": t(
            "Country and dialling code",
            "Страна и телефонный код",
            "Ülke ve arama kodu",
            "Land und Vorwahl",
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
