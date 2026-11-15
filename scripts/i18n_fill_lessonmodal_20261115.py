#!/usr/bin/env python3
"""«Yeni dərs» modalı (sahib 2026-11-15): patok / eyni saat mesajının yeni mətni — yalnız yeni msgid-ləri əlavə edir.

Saat həddi mesajı («Dərs saatı 1 ilə %(max)s arasında olmalıdır.», registrar.journal_lessons) kataloqda artıq var.
"""

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
        "registrar.journal_lessons": {
            "Bu jurnalda %(date)s, saat %(time)s üçün dərs artıq var — qeydləri həmin dərsin sütununa yazın. "
            "Patok dərsində hər qrupun dərsi öz jurnalına yazılır; alt qrupların (Lab / seminar) dərsi üçün alt "
            "qrupu seçin.": t(
                "This journal already has a lesson on %(date)s at %(time)s — enter the records in that lesson's "
                "column. In a joint (stream) lesson each group's lesson is written in its own journal; for a "
                "sub-group lesson (Lab / seminar) choose the sub-group.",
                "В этом журнале уже есть занятие %(date)s в %(time)s — вносите записи в столбец этого занятия. "
                "При поточном занятии занятие каждой группы записывается в её собственный журнал; для занятия "
                "подгруппы (лаб. / семинар) выберите подгруппу.",
                "Bu dergide %(date)s, saat %(time)s için zaten bir ders var — kayıtları o dersin sütununa girin. "
                "Ortak (akış) derste her grubun dersi kendi dergisine yazılır; alt grup dersi (Lab / seminer) için "
                "alt grubu seçin.",
                "In diesem Journal gibt es am %(date)s um %(time)s bereits eine Stunde — tragen Sie die Einträge in "
                "die Spalte dieser Stunde ein. Bei einer gemeinsamen (Strom-)Vorlesung wird die Stunde jeder "
                "Gruppe in deren eigenem Journal erfasst; für eine Untergruppenstunde (Labor / Seminar) wählen Sie "
                "die Untergruppe.",
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
