#!/usr/bin/env python3
"""«Cədvəldən kənar» işarəsi tənzimləməsi (sahib 2026-11-14, MR-356): yalnız yeni msgid-ləri əlavə edir."""

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
        "core.runtime_settings": {
            "«Cədvəldən kənar» işarəsi": t(
                "“Off-timetable” mark",
                "Отметка «вне расписания»",
                "«Program dışı» işareti",
                "Markierung „außerhalb des Stundenplans“",
            ),
            (
                "Yandırılıbsa tarixi və saatı dərs cədvəlinə uyğun gəlməyən yeni dərs üçün səbəb soruşulur və dərs "
                "«cədvəldən kənar» kimi işarələnir. Söndürülüdə müəllim istənilən tarix və saatda dərs aça bilər — "
                "səbəb soruşulmur, heç nə işarələnmir və «cədvəldən kənar» yazısı heç yerdə göstərilmir."
            ): t(
                "When on, a new lesson whose date and time do not match the timetable needs a reason and is marked "
                "“off-timetable”. When off, the teacher may open a lesson at any date and time — no reason is asked, "
                "nothing is marked and the “off-timetable” label is not shown anywhere.",
                "Если включено, для нового занятия, дата и время которого не совпадают с расписанием, требуется "
                "причина, и занятие отмечается как «вне расписания». Если выключено, преподаватель может открыть "
                "занятие в любую дату и время — причина не запрашивается, ничего не отмечается и надпись «вне "
                "расписания» нигде не показывается.",
                "Açıksa tarihi ve saati ders programına uymayan yeni ders için gerekçe istenir ve ders «program dışı» "
                "olarak işaretlenir. Kapalıyken öğretmen herhangi bir tarih ve saatte ders açabilir — gerekçe "
                "istenmez, hiçbir şey işaretlenmez ve «program dışı» yazısı hiçbir yerde gösterilmez.",
                "Wenn aktiviert, braucht eine neue Lehrveranstaltung, deren Datum und Uhrzeit nicht zum Stundenplan "
                "passen, eine Begründung und wird als „außerhalb des Stundenplans“ markiert. Wenn deaktiviert, kann "
                "die Lehrkraft eine Lehrveranstaltung zu jedem Datum und jeder Uhrzeit anlegen — es wird keine "
                "Begründung verlangt, nichts markiert und die Markierung nirgends angezeigt.",
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
