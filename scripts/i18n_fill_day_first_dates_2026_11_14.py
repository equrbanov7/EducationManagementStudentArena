#!/usr/bin/env python3
"""Tarix sahələri «gg.aa.iiii» (EMSDateTime date rejimi, sahib 2026-11-14): yalnız yeni msgid-ləri əlavə edir."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return dict(zip(LANGS[1:], (en, ru, tr, de)))


def quote(text):
    return json.dumps(text, ensure_ascii=False)


ENTRIES = {
    "django": {
        "core.datetime_input": {
            "Tarixi gg.aa.iiii formatında yazın (məsələn, 06.10.2026).": t(
                "Enter the date as dd.mm.yyyy (for example, 06.10.2026).",
                "Введите дату в формате дд.мм.гггг (например, 06.10.2026).",
                "Tarihi gg.aa.yyyy biçiminde yazın (örneğin, 06.10.2026).",
                "Geben Sie das Datum im Format TT.MM.JJJJ ein (z. B. 06.10.2026).",
            ),
            "Tarix {min} ilə {max} arasında olmalıdır.": t(
                "The date must be between {min} and {max}.",
                "Дата должна быть в промежутке с {min} по {max}.",
                "Tarih {min} ile {max} arasında olmalıdır.",
                "Das Datum muss zwischen {min} und {max} liegen.",
            ),
            "Tarix {min} və ya daha sonra olmalıdır.": t(
                "The date must be {min} or later.",
                "Дата должна быть не раньше {min}.",
                "Tarih {min} veya daha sonra olmalıdır.",
                "Das Datum muss am {min} oder später liegen.",
            ),
            "Tarix {max} və ya daha əvvəl olmalıdır.": t(
                "The date must be {max} or earlier.",
                "Дата должна быть не позже {max}.",
                "Tarih {max} veya daha önce olmalıdır.",
                "Das Datum muss am {max} oder früher liegen.",
            ),
            "Tarixi seçin": t("Choose a date", "Выберите дату", "Tarih seçin", "Datum auswählen"),
            "Bağla": t("Close", "Закрыть", "Kapat", "Schließen"),
            "gg.aa.iiii": t("dd.mm.yyyy", "дд.мм.гггг", "gg.aa.yyyy", "TT.MM.JJJJ"),
        },
        "registrar.journal": {
            "Keçmiş tarixə dərs ən çox %(d)s gün geriyə — %(date)s tarixindən bu günədək açmaq olar.": t(
                "A lesson can be opened for a past date at most %(d)s day(s) back — from %(date)s up to today.",
                "Занятие можно открыть на прошедшую дату не более чем на %(d)s дн. назад — с %(date)s по сегодня.",
                "Geçmiş bir tarihe en fazla %(d)s gün geriye — %(date)s tarihinden bugüne kadar ders açılabilir.",
                "Eine Stunde kann höchstens %(d)s Tag(e) rückwirkend angelegt werden — vom %(date)s bis heute.",
            ),
        },
    },
}


def fill():
    counts = {}
    for domain, contexts in ENTRIES.items():
        for lang in LANGS:
            path = BASE / "locale" / lang / "LC_MESSAGES" / f"{domain}.po"
            existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
            blocks = []
            for context, messages in contexts.items():
                for msgid, translations in messages.items():
                    if (context, msgid) in existing:
                        continue
                    value = msgid if lang == "az" else translations[lang]
                    lines = ["#, python-format"] if "%" in msgid else []
                    if context:
                        lines.append("msgctxt " + quote(context))
                    lines += ["msgid " + quote(msgid), "msgstr " + quote(value)]
                    blocks.append("\n".join(lines) + "\n")
            if blocks:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(blocks))
            counts[f"{domain}/{lang}"] = len(blocks)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    fill()
