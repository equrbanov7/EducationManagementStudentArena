#!/usr/bin/env python3
"""Sahib 2026-11-25: paylaşımda saat fərqi (əyani ↔ qiyabi) — «Kopyala və uyğunlaşdır» tövsiyəli yeni mətn.

Yalnız yeni msgid-ləri əlavə edir (``accounts.views.syllabus.labels.SHARE_HOURS_DIFFER``).
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
            "Bu qrupun dərs saatı sillabusun saatından fərqlidir (məsələn, əyani və qiyabi qrup) — eyni sillabus hər iki "
            "jurnalda istifadə oluna bilməz. «Kopyala və uyğunlaşdır» ilə bu qrup üçün ayrıca sillabus yaradın.": t(
                "This group's teaching hours differ from the syllabus hours (for example, a full-time and a part-time "
                "group) — the same syllabus cannot be used in both journals. Use «Copy and adjust» to create a separate "
                "syllabus for this group.",
                "Учебные часы этой группы отличаются от часов силлабуса (например, очная и заочная группа) — один и "
                "тот же силлабус нельзя использовать в обоих журналах. С помощью «Скопировать и адаптировать» создайте "
                "для этой группы отдельный силлабус.",
                "Bu grubun ders saatleri izlencenin saatlerinden farklı (örneğin örgün ve uzaktan/kısmi zamanlı grup) "
                "— aynı izlence her iki dergide kullanılamaz. «Kopyala ve uyarla» ile bu grup için ayrı bir izlence "
                "oluşturun.",
                "Die Unterrichtsstunden dieser Gruppe weichen von den Stunden des Syllabus ab (z. B. Vollzeit- und "
                "Fernstudiengruppe) — derselbe Syllabus kann nicht in beiden Journalen verwendet werden. Erstellen Sie "
                "mit «Kopieren und anpassen» einen eigenen Syllabus für diese Gruppe.",
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
