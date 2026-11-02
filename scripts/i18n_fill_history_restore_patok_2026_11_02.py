#!/usr/bin/env python3
"""Tarixçə jurnalının patok sətri qeydi: yalnız yeni msgid-ləri əlavə edir.

Mövcud tərcümələrə toxunmur.
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
        "workload.history_restore": {
            "Bu jurnalın yükü çoxqruplu (patok) sətirdədir": t(
                "This journal's load is in a multi-group (stream) row",
                "Нагрузка этого журнала находится в многогрупповой (поточной) строке",
                "Bu defterin yükü çok gruplu (akış) satırdadır",
                "Die Lehrlast dieses Journals steht in einer gruppenübergreifenden (Strom-)Zeile",
            ),
            "Ortaq mühazirə bütün qruplara aiddir, ona görə müəllim «Yük bölgüsü»ndə həmin sətirdə təyin edilir. Jurnal qeydləri dəyişmir.": t(
                "The shared lecture belongs to every group, so the teacher is assigned on that row in «Load distribution». Journal records do not change.",
                "Общая лекция относится ко всем группам, поэтому преподаватель назначается в этой строке в разделе «Распределение нагрузки». Записи журнала не меняются.",
                "Ortak ders tüm gruplara aittir; bu nedenle öğretim elemanı «Yük dağılımı» bölümünde o satıra atanır. Defter kayıtları değişmez.",
                "Die gemeinsame Vorlesung gehört allen Gruppen, daher wird die Lehrkraft in dieser Zeile unter «Lastverteilung» zugeordnet. Die Journaleinträge ändern sich nicht.",
            ),
            "Yük bölgüsündə aç": t(
                "Open in load distribution",
                "Открыть в распределении нагрузки",
                "Yük dağılımında aç",
                "In der Lastverteilung öffnen",
            ),
            "Patok sətri": t("Stream row", "Поточная строка", "Akış satırı", "Stromzeile"),
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
                    lines = []
                    if context:
                        lines.append("msgctxt " + quote(context))
                    lines += ["msgid " + quote(msgid), "msgstr " + quote(value)]
                    blocks.append("\n".join(lines) + "\n")
            if blocks:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(blocks))
                polib.pofile(path).save_as_mofile(path.with_suffix(".mo"))
            counts[f"{domain}/{lang}"] = len(blocks)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    fill()
