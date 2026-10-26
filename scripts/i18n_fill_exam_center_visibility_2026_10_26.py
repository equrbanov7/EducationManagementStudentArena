#!/usr/bin/env python3
"""EMSArena i18n — «İmtahanlarım» bölməsində imtahan mərkəzinin «Midterm / Final» tabı + «Yaradan» (sahib 2026-10-26).

İmtahan mərkəzi işçisi / rəhbəri təşkilatın bütün midterm/final imtahanlarını yaradandan asılı
olmayaraq görür. msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid
toxunulmur); sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ENTRIES = {
    "profile.my_exams.center": {
        "Midterm / Final": {
            "en": "Midterms / Finals",
            "ru": "Промежуточные / Итоговые",
            "tr": "Ara sınav / Final",
            "de": "Zwischen- / Abschlussprüfungen",
        },
        "Təşkilatın bütün midterm və final imtahanları — kim yaratmasından asılı olmayaraq": {
            "en": "All midterm and final exams of the organisation, regardless of who created them",
            "ru": "Все промежуточные и итоговые экзамены организации — независимо от того, кто их создал",
            "tr": "Kurumun tüm ara sınav ve final sınavları — kimin oluşturduğundan bağımsız olarak",
            "de": "Alle Zwischen- und Abschlussprüfungen der Organisation – unabhängig davon, wer sie erstellt hat",
        },
        "Yaradan": {
            "en": "Created by",
            "ru": "Создатель",
            "tr": "Oluşturan",
            "de": "Erstellt von",
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
