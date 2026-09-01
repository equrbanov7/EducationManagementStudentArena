#!/usr/bin/env python3
"""EMSArena i18n — jurnal asimmetriyası düzəlişinin yeni sətirləri, 4 dil.

Alt qrup birləşməsindən sonra hədəf jurnalın sətri əvvəl YALNIZ ziyanı (qayıb)
göstərirdi; indi əvvəlki jurnalda QAZANILMIŞ giriş balı da görünür. Bu skript
həmin iki yeni mətni kataloqlara yazır.

Geri qaytarma blokerlərinin etiketləri YENİ DEYİL — ``blocker_labels`` mövcud
msgid-ləri (``chain_moved`` üçün ``error_message``-in mətni,
«Geri qaytarma mümkün deyil.») təkrar işlədir, ona görə burada yoxdur.

İdempotent: mövcud girişə TOXUNMUR, yalnız çatışmayanı əlavə edir.

⚠️ `makemessages` İŞLƏDİLMİR (əl ilə yazılmış blokları silə bilir).

İstifadə:  python scripts/i18n_fill_journal_asymmetry.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CTX = "registrar.guest_roster"

ENTRIES = {
    CTX: {
        # Qrid nişanının ikinci rəqəmi: əvvəlki jurnalda qazanılmış giriş balı.
        "%(score)s bal": {
            "en": "%(score)s pts",
            "ru": "%(score)s балл.",
            "tr": "%(score)s puan",
        },
        # Nişanın tooltip-inə əlavə olunan ikinci cümlə.
        (
            "Əvvəlki jurnalda yığılmış giriş balı: %(score)s / %(cap)s. "
            "Bu bal bura köçürülmür — lazım bilinsə müəllim onu komponent və ya "
            "rəsmi düzəliş axını ilə özü yazır."
        ): {
            "en": (
                "Entry score accumulated in the previous journal: %(score)s / %(cap)s. "
                "This score is not moved here — if needed, the teacher records it through "
                "the assessment-component or official-correction flow."
            ),
            "ru": (
                "Входной балл, накопленный в прежнем журнале: %(score)s / %(cap)s. "
                "Этот балл сюда не переносится — при необходимости преподаватель вносит его "
                "через компоненты оценивания или официальную корректировку."
            ),
            "tr": (
                "Önceki günlükte biriken giriş puanı: %(score)s / %(cap)s. "
                "Bu puan buraya taşınmaz — gerekirse öğretmen onu değerlendirme bileşeni "
                "veya resmî düzeltme akışıyla kendisi girer."
            ),
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
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
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
