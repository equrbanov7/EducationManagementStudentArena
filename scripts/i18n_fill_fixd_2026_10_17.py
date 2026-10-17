#!/usr/bin/env python3
"""EMSArena i18n — FIX-D (QA dalğası 2026-10-17) mətnləri.

QA-1 P3: tələbənin bal bölgüsündə (``registrar/partials/_entry_parts.html``) kəsirli cəm ilə yuvarlaqlaşdırılmış
«İmtahana qədər bal» birlikdə göstərilir («Cəm: 9,55 → 10») — kontekst `registrar.journal`.

Digər FIX-D düzəlişləri (qrup köçürməsinin geri qaytarılması, cədvəl əhatəsi, profil qapısı, workflow) yeni
istifadəçi mətni əlavə etmir.

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir (mövcudluq `polib`
ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_fixd_2026_10_17.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

JOURNAL = "registrar.journal"

ROUNDING_HELP = (
    "İmtahana qədər bal tam ədəddir: hissələrin cəmi yarım-yuxarı yuvarlaqlaşdırılır (məs. 9,5 → 10, 9,4 → 9)."
)

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    JOURNAL: {
        "Cəm": {"en": "Sum", "ru": "Сумма", "tr": "Toplam", "de": "Summe"},
        ROUNDING_HELP: {
            "en": "The pre-exam score is a whole number: the sum of the parts is rounded half up "
            "(e.g. 9.5 → 10, 9.4 → 9).",
            "ru": "Балл до экзамена — целое число: сумма частей округляется по правилу «половина вверх» "
            "(напр. 9,5 → 10, 9,4 → 9).",
            "tr": "Sınav öncesi puan tam sayıdır: bölümlerin toplamı yarım yukarı yuvarlanır (örn. 9,5 → 10, 9,4 → 9).",
            "de": "Die Punktzahl vor der Prüfung ist eine ganze Zahl: Die Summe der Teile wird kaufmännisch gerundet "
            "(z. B. 9,5 → 10, 9,4 → 9).",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
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
