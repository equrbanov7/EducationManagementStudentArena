#!/usr/bin/env python3
"""EMSArena i18n — test midterm balı jurnala avtomatik (sahib 2026-10-21).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

JOURNAL = "registrar.journal"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


AZ_OVERRIDES = {}

ENTRIES = {
    JOURNAL: {
        "Test formatında keçirilən midterm balı imtahandan avtomatik yazılır və burada əl ilə dəyişdirilmir. "
        "Düzəliş yalnız apellyasiya və ya sənədli düzəliş ilə mümkündür.": t(
            "The score of a midterm taken as a test is written automatically from the exam and cannot be changed "
            "here by hand. It can only be corrected through an appeal or a documented correction.",
            "Балл промежуточного экзамена в формате теста записывается автоматически из экзамена и здесь вручную "
            "не меняется. Исправить его можно только через апелляцию или документированное исправление.",
            "Test olarak yapılan ara sınavın puanı sınavdan otomatik yazılır ve burada elle değiştirilemez. "
            "Düzeltme yalnızca itiraz veya belgeli düzeltme ile yapılabilir.",
            "Die Punktzahl einer als Test abgelegten Zwischenprüfung wird automatisch aus der Prüfung übernommen und "
            "kann hier nicht manuell geändert werden. Eine Korrektur ist nur per Einspruch oder dokumentierter "
            "Korrektur möglich.",
        ),
        "İmtahandan avtomatik — %(title)s (%(percent)s%%)": t(
            "Automatically from the exam — %(title)s (%(percent)s%%)",
            "Автоматически из экзамена — %(title)s (%(percent)s%%)",
            "Sınavdan otomatik — %(title)s (%(percent)s%%)",
            "Automatisch aus der Prüfung — %(title)s (%(percent)s%%)",
        ),
        "test imtahanından avtomatik": t(
            "automatically from the test exam",
            "автоматически из тестового экзамена",
            "test sınavından otomatik",
            "automatisch aus der Testprüfung",
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
            if lang == "az":
                msgstr = AZ_OVERRIDES.get((ctx, msgid), msgid)
            else:
                msgstr = translations.get(lang) or msgid
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
