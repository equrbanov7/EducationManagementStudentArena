#!/usr/bin/env python3
"""EMSArena i18n — «Praktiki məşğələ» görünüş etiketi (sahib 2026-10-28).

AZ cümləli msgid-lərdə az msgstr = msgid; ``registrar.lesson_kind`` konteksti (``LessonKind`` kimi) ingiliscə msgid-dir —
az tərcüməsi açıq verilir. İdempotentdir (mövcud msgctxt+msgid toxunulmur); sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de, az=None):
    return {"az": az, "en": en, "ru": ru, "tr": tr, "de": de}


PRACTICAL = t("Practical session", "Практическое занятие", "Uygulama dersi", "Praktische Übung", az="Praktiki məşğələ")

ENTRIES = {
    "registrar.lesson_kind": {"Practical session": PRACTICAL},
    "registrar.practical": {
        "Praktiki məşğələ": PRACTICAL,
        "Yalnız ad: seminar dərsləri bu jurnalda «Praktiki məşğələ» kimi göstərilir. Bal, saat və cədvəl dəyişmir.": t(
            "Label only: seminar lessons in this journal are shown as «Practical session». Scores, hours and the "
            "timetable do not change.",
            "Только название: семинарские занятия в этом журнале показываются как «Практическое занятие». Баллы, "
            "часы и расписание не меняются.",
            "Yalnızca ad: bu defterdeki seminer dersleri «Uygulama dersi» olarak gösterilir. Puan, saat ve ders "
            "programı değişmez.",
            "Nur die Bezeichnung: Seminarstunden werden in diesem Journal als «Praktische Übung» angezeigt. Punkte, "
            "Stunden und Stundenplan ändern sich nicht.",
        ),
        "Seminar dərsləri bu jurnalda «Praktiki məşğələ» adlanır.": t(
            "Seminar lessons in this journal are now called «Practical session».",
            "Семинарские занятия в этом журнале теперь называются «Практическое занятие».",
            "Bu defterdeki seminer dersleri artık «Uygulama dersi» olarak adlandırılıyor.",
            "Seminarstunden heißen in diesem Journal jetzt «Praktische Übung».",
        ),
        "Seminar dərsləri yenidən «Seminar» adlanır.": t(
            "Seminar lessons are called «Seminar» again.",
            "Семинарские занятия снова называются «Семинар».",
            "Seminer dersleri yeniden «Seminer» olarak adlandırılıyor.",
            "Seminarstunden heißen wieder «Seminar».",
        ),
    },
    "registrar.console": {
        "Seminar = «Praktiki məşğələ»": t(
            "Seminar = «Practical session»",
            "Семинар = «Практическое занятие»",
            "Seminer = «Uygulama dersi»",
            "Seminar = «Praktische Übung»",
        ),
    },
    "registrar.catalog": {
        "Praktiki məşğələ — seminar dərsləri jurnalda və cədvəldə «Praktiki məşğələ» adlanır (bal və saat dəyişmir)": t(
            "Practical session — seminar lessons are called «Practical session» in the journal and the timetable "
            "(scores and hours do not change)",
            "Практическое занятие — семинарские занятия называются «Практическое занятие» в журнале и расписании "
            "(баллы и часы не меняются)",
            "Uygulama dersi — seminer dersleri defterde ve ders programında «Uygulama dersi» olarak adlandırılır "
            "(puan ve saat değişmez)",
            "Praktische Übung — Seminarstunden heißen im Journal und im Stundenplan «Praktische Übung» (Punkte und "
            "Stunden ändern sich nicht)",
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
