#!/usr/bin/env python3
"""EMSArena i18n — «Dəyərləndirilmiş nəticələr»: Excel ixracı, yeni süzgəclər, «Avtomatik (sistem)» (sahib 2026-10-27).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RR = "accounts.review_results"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    RR: {
        "İmtahan — Midterm": t("Exam — Midterm", "Экзамен — Midterm", "Sınav — Ara sınav", "Prüfung — Zwischenprüfung"),
        "İmtahan — Final": t("Exam — Final", "Экзамен — Финал", "Sınav — Final", "Prüfung — Abschlussprüfung"),
        "İmtahan — Quiz": t("Exam — Quiz", "Экзамен — Квиз", "Sınav — Quiz", "Prüfung — Quiz"),
        "Fənn": t("Subject", "Предмет", "Ders", "Fach"),
        "Bütün fənlər": t("All subjects", "Все предметы", "Tüm dersler", "Alle Fächer"),
        "Seçilmiş aralıq": t("Custom range", "Выбранный интервал", "Seçilen aralık", "Benutzerdefinierter Zeitraum"),
        "Başlanğıc (tarix, saat)": t(
            "From (date, time)", "Начало (дата, время)", "Başlangıç (tarih, saat)", "Von (Datum, Uhrzeit)"
        ),
        "Son (tarix, saat)": t("To (date, time)", "Конец (дата, время)", "Bitiş (tarih, saat)", "Bis (Datum, Uhrzeit)"),
        "Excel-ə yüklə": t("Download Excel", "Скачать Excel", "Excel'e indir", "Als Excel herunterladen"),
        "Yükləmək üçün nəticə yoxdur.": t(
            "There are no results to download.",
            "Нет результатов для скачивания.",
            "İndirilecek sonuç yok.",
            "Keine Ergebnisse zum Herunterladen.",
        ),
        "Dəyərləndirilmiş nəticələr": t(
            "Evaluated results", "Оценённые результаты", "Değerlendirilmiş sonuçlar", "Bewertete Ergebnisse"
        ),
    },
    "exams.results_export": {
        "Avtomatik (sistem)": t(
            "Automatic (system)", "Автоматически (система)", "Otomatik (sistem)", "Automatisch (System)"
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
