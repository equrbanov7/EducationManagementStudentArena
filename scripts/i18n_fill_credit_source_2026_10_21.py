#!/usr/bin/env python3
"""EMSArena i18n — R02 (2026-10-21): «Fənlərim» kredit tərəqqisi pill-i.

«Məzuniyyət yükü tamamlandı» → «Kredit hədəfinə çatılıb»: pill YALNIZ kredit tərəqqisidir (toplanmış ≥ tələb olunan),
məzuniyyət qərarı deyil (``registrar.services.get_credit_summary`` → ``credit_target_reached``). Əlavə olunan mətn:
  * ``django`` / `profile.subjects` — `_my_subjects.html`.

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları
əlavə edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_credit_source_2026_10_21.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

SUBJECTS = "profile.subjects"

# domen → ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    "django": {
        SUBJECTS: {
            "Kredit hədəfinə çatılıb": {
                "en": "Credit target reached",
                "ru": "Целевое количество кредитов набрано",
                "tr": "Kredi hedefine ulaşıldı",
                "de": "Kreditziel erreicht",
            },
        },
    },
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES[domain].items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            blocks.append(f'{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        for name in ENTRIES:
            fill(locale, name)
