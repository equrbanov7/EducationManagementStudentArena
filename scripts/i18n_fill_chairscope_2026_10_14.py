#!/usr/bin/env python3
"""EMSArena i18n — kafedra/fakültə əhatəsi 2026-10-14 («Yük — ümumi baxış»).

Əlavə olunan mətnlər:
  * `accounts.workload_overview` — başlıq altı mətni əhatəyə görə: kafedra müdiri «kafedranız üzrə»,
    dekan «fakültəniz üzrə» görür (org-wide mətn dəyişməyib).

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Orkestrator serial işlədir; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_chairscope_2026_10_14.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

OVERVIEW = "accounts.workload_overview"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    OVERVIEW: {
        "Tapşırıqdan müəllim təsdiqinə qədər bütün mərhələlərin kafedranız üzrə vəziyyəti.": {
            "en": "Status of every stage for your department, from the teaching task to teacher confirmation.",
            "ru": "Состояние всех этапов по вашей кафедре — от учебного задания до подтверждения преподавателем.",
            "tr": "Görevlendirmeden öğretim elemanı onayına kadar tüm aşamaların bölümünüzdeki durumu.",
            "de": "Stand aller Phasen für Ihren Lehrstuhl – vom Lehrauftrag bis zur Bestätigung durch die Lehrkraft.",
        },
        "Tapşırıqdan müəllim təsdiqinə qədər bütün mərhələlərin fakültəniz üzrə vəziyyəti.": {
            "en": "Status of every stage for your faculty, from the teaching task to teacher confirmation.",
            "ru": "Состояние всех этапов по вашему факультету — от учебного задания до подтверждения преподавателем.",
            "tr": "Görevlendirmeden öğretim elemanı onayına kadar tüm aşamaların fakültenizdeki durumu.",
            "de": "Stand aller Phasen für Ihre Fakultät – vom Lehrauftrag bis zur Bestätigung durch die Lehrkraft.",
        },
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
