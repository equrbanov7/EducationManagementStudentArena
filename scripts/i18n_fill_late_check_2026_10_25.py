#!/usr/bin/env python3
"""EMSArena i18n — «"Gec yazılıb" nəzarətinin başlanğıc tarixi» tənzimləməsi (2026-10-25).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CR = "core.runtime_settings"
AR = "accounts.runtime_settings"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    CR: {
        "«Gec yazılıb» nəzarətinin başlanğıc tarixi": t(
            "Start date of the “Recorded late” check",
            "Дата начала контроля «Записано с опозданием»",
            "“Geç yazıldı” denetiminin başlangıç tarihi",
            "Startdatum der Prüfung „Verspätet eingetragen“",
        ),
        "Tarixi bu gündən əvvəl olan dərs heç vaxt «Gec yazılıb» sayılmır — nişanda, «Keçilmiş dərslər» sayında, KPI-da və ixracda. Bu tarixdən (və sonrakı) dərslər üçün qayda dəyişmir: dərsin ilk xanası dərs tarixindən 48 saatdan gec yazılıbsa «gec»dir. Köhnə sistemdən köçürülmüş data üçün tarixi köçürmə sonrası ilk iş gününə qoyun.": t(
            "A lesson dated before this day is never counted as “Recorded late” — in the badge, the “Conducted lessons” count, the KPI and the export. For lessons from this date onwards the rule is unchanged: a lesson is “late” if its first mark was entered more than 48 hours after the lesson date. For data migrated from the old system, set the date to the first working day after the migration.",
            "Занятие с датой раньше этого дня никогда не считается «Записано с опозданием» — ни в метке, ни в счётчике «Проведённые занятия», ни в KPI, ни в экспорте. Для занятий с этой даты и позже правило прежнее: занятие «позднее», если первая отметка внесена позже чем через 48 часов после даты занятия. Для данных, перенесённых из старой системы, поставьте первый рабочий день после переноса.",
            "Bu günden önce tarihli bir ders asla “Geç yazıldı” sayılmaz — rozette, “Geçilen dersler” sayısında, KPI'da ve dışa aktarımda. Bu tarihten itibaren dersler için kural değişmez: dersin ilk kaydı ders tarihinden 48 saatten geç girildiyse “geç”tir. Eski sistemden aktarılan veri için tarihi aktarımdan sonraki ilk iş gününe ayarlayın.",
            "Eine Stunde mit einem Datum vor diesem Tag gilt nie als „Verspätet eingetragen“ — weder im Kennzeichen noch in der Zahl „Gehaltene Stunden“, im KPI oder im Export. Für Stunden ab diesem Datum bleibt die Regel: Eine Stunde ist „verspätet“, wenn der erste Eintrag mehr als 48 Stunden nach dem Stundendatum erfolgte. Für aus dem Altsystem übernommene Daten setzen Sie den ersten Werktag nach der Übernahme.",
        ),
    },
    AR: {
        "Tarix seçin (gün.ay.il).": t(
            "Choose a date (day.month.year).",
            "Выберите дату (день.месяц.год).",
            "Bir tarih seçin (gün.ay.yıl).",
            "Wählen Sie ein Datum (Tag.Monat.Jahr).",
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
