#!/usr/bin/env python3
"""EMSArena i18n — toplu sual önizləməsində «Yalnız təmiz sualları seç» + «Təmiz: N / M» (sahib 2026-10-26).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur); sonra
`compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ENTRIES = {
    "exams.template.test_question_bank": {
        "Təmiz: %(clean)s / %(total)s": {
            "en": "Clean: %(clean)s / %(total)s",
            "ru": "Чистые: %(clean)s / %(total)s",
            "tr": "Temiz: %(clean)s / %(total)s",
            "de": "Fehlerfrei: %(clean)s / %(total)s",
        },
        "Yalnız təmiz sualları seç": {
            "en": "Select only clean questions",
            "ru": "Выбрать только чистые вопросы",
            "tr": "Yalnızca temiz soruları seç",
            "de": "Nur fehlerfreie Fragen auswählen",
        },
        "Xətasız, xəbərdarlıqsız və dublikatsız sualları seçir, qalanlarının seçimini götürür": {
            "en": "Selects questions without errors, warnings or duplicates and deselects the rest",
            "ru": "Выбирает вопросы без ошибок, предупреждений и дубликатов, с остальных снимает выбор",
            "tr": "Hatasız, uyarısız ve yinelenmeyen soruları seçer, diğerlerinin seçimini kaldırır",
            "de": "Wählt Fragen ohne Fehler, Warnungen und Duplikate aus und hebt die Auswahl der übrigen auf",
        },
        "Seçildi: {count} təmiz sual": {
            "en": "Selected: {count} clean questions",
            "ru": "Выбрано чистых вопросов: {count}",
            "tr": "Seçildi: {count} temiz soru",
            "de": "Ausgewählt: {count} fehlerfreie Fragen",
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
