#!/usr/bin/env python3
"""EMSArena i18n — dekan / kafedra müdiri əhatəsi, 2026-10-14.

Əlavə olunan mətnlər:
  * `accounts.staff_management` — «Təşkilatın mövcud üzvləri» süzgəci ikiyə bölündü:
    «Struktur bölməsi» (fakültə/kafedra/şöbə) və «Qrup» («Bütün qruplar»);
  * `accounts.groups` — «Qruplar» KPI-si «TƏLƏBƏ (SƏHİFƏDƏ)» əvəzinə «TƏLƏBƏ» (əhatədəki bütün qruplar üzrə).

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_deanscope_2026_10_14.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

STAFF = "accounts.staff_management"
GROUPS = "accounts.groups"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    STAFF: {
        "Struktur bölməsi": {
            "en": "Structural unit",
            "ru": "Структурное подразделение",
            "tr": "Yapısal birim",
            "de": "Struktureinheit",
        },
        "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup", "de": "Gruppe"},
        "Bütün qruplar": {"en": "All groups", "ru": "Все группы", "tr": "Tüm gruplar", "de": "Alle Gruppen"},
    },
    GROUPS: {
        "TƏLƏBƏ": {"en": "STUDENTS", "ru": "СТУДЕНТЫ", "tr": "ÖĞRENCİ", "de": "STUDIERENDE"},
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
