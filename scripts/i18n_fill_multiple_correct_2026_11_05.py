#!/usr/bin/env python3
"""EMSArena i18n — midterm / final yükləməsində «birdən çox düzgün cavab» xətası (sahib 2026-11-05).

Kontekst: ``exams.view.question_bank.warning`` (``bulk_workbench`` xəbərdarlıq açarları açar-msgid ilə).
⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir. Sonra `.mo`
faylları `msgfmt` ilə yığılır.

İstifadə:  python scripts/i18n_fill_multiple_correct_2026_11_05.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ENTRIES = {
    "exams.view.question_bank.warning": {
        "multiple_correct": {
            "az": "Birdən çox düzgün cavab işarələnib ({labels}) — midterm və final imtahanında sualın yalnız bir "
            "düzgün cavabı olmalıdır.",
            "en": "More than one correct answer is marked ({labels}) — a midterm or final question must have "
            "exactly one correct answer.",
            "ru": "Отмечено несколько правильных ответов ({labels}) — в мидтерме и финальном экзамене у вопроса "
            "должен быть ровно один правильный ответ.",
            "tr": "Birden fazla doğru cevap işaretlenmiş ({labels}) — ara sınav ve final sınavında sorunun yalnızca "
            "bir doğru cevabı olmalıdır.",
            "de": "Mehr als eine richtige Antwort markiert ({labels}) — eine Midterm- oder Finalfrage muss genau "
            "eine richtige Antwort haben.",
        },
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain="django"):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(translations[lang])}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for lang in LOCALES:
        fill(lang)
