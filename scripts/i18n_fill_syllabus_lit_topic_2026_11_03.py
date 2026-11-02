#!/usr/bin/env python3
"""Sillabus ədəbiyyatı istənilən formada (sahib 2026-11-03): yalnız yeni msgid-ləri əlavə edir.

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
        "accounts.syllabus": {
            "Əsas və əlavə ədəbiyyat sahələrinin hər biri doldurulmalıdır. Mənbələri istənilən formada yaza "
            "bilərsiniz — alt-alta, vergüllə və ya bir sətirdə.": t(
                "Both the primary and the additional literature fields must be filled in. You can write the sources "
                "in any form — one per line, separated by commas or on a single line.",
                "Нужно заполнить оба поля — основную и дополнительную литературу. Источники можно записывать в любой "
                "форме: каждый с новой строки, через запятую или в одну строку.",
                "Ana ve ek kaynakça alanlarının her ikisi doldurulmalıdır. Kaynakları istediğiniz biçimde "
                "yazabilirsiniz — alt alta, virgülle ya da tek satırda.",
                "Sowohl das Feld für Grundlagenliteratur als auch das für weiterführende Literatur muss ausgefüllt "
                "werden. Die Quellen können in beliebiger Form angegeben werden — untereinander, durch Kommas "
                "getrennt oder in einer Zeile.",
            ),
            "Müəllif, ad, nəşr ili — alt-alta və ya bir sətirdə, vergüllə.": t(
                "Author, title, year — one per line or on a single line, separated by commas.",
                "Автор, название, год издания — с новой строки или в одну строку через запятую.",
                "Yazar, eser adı, yayın yılı — alt alta ya da tek satırda, virgülle.",
                "Autor, Titel, Erscheinungsjahr — untereinander oder in einer Zeile, durch Kommas getrennt.",
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
