#!/usr/bin/env python3
"""Apellyasiya balı — sənəd opsional (sahib 2026-11-19): yalnız yeni msgid-ləri əlavə edir (təkrar işlətmək təhlükəsizdir)."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")
CONTEXT = "registrar.exam_score_entry"
ENTRIES = {
    "Apellyasiya rejimi: «Yekun» ballar açıldı. Sənəd və qeyd istəyə bağlıdır.": (
        "Appeal mode: the “Final” scores are unlocked. The document and the note are optional.",
        "Режим апелляции: итоговые баллы открыты. Документ и примечание необязательны.",
        "İtiraz modu: «Final» puanları açıldı. Belge ve not isteğe bağlıdır.",
        "Einspruchsmodus: Die Endpunkte sind freigegeben. Dokument und Notiz sind optional.",
    ),
    "Apellyasiya ilə dəyişiklik — sənəd (qərar / ərizə) və qeyd istəyə bağlıdır. Dəyişiklik «apellyasiya» kimi işarələnir: kim, köhnə → yeni bal, nə vaxt — tarixçədə görünür.": (
        "Change by appeal — the document (decision / application) and the note are optional. The change is marked as “appeal”: who, old → new score and when are shown in the history.",
        "Изменение по апелляции — документ (решение / заявление) и примечание необязательны. Изменение помечается как «апелляция»: кто, старый → новый балл и когда — видно в истории.",
        "İtiraz ile değişiklik — belge (karar / dilekçe) ve not isteğe bağlıdır. Değişiklik «itiraz» olarak işaretlenir: kim, eski → yeni puan, ne zaman — geçmişte görünür.",
        "Änderung per Einspruch — Dokument (Entscheidung / Antrag) und Notiz sind optional. Die Änderung wird als „Einspruch“ markiert: wer, alte → neue Punktzahl und wann stehen im Verlauf.",
    ),
}


def fill():
    counts = {}
    for lang in LANGS:
        path = BASE / "locale" / lang / "LC_MESSAGES" / "django.po"
        existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
        blocks = []
        for msgid, translations in ENTRIES.items():
            if (CONTEXT, msgid) in existing:
                continue
            value = msgid if lang == "az" else translations[LANGS.index(lang) - 1]
            blocks.append(
                "msgctxt %s\nmsgid %s\nmsgstr %s\n"
                % tuple(json.dumps(text, ensure_ascii=False) for text in (CONTEXT, msgid, value))
            )
        if blocks:
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n" + "\n".join(blocks))
        counts[lang] = len(blocks)
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    fill()
