#!/usr/bin/env python3
"""EMSArena i18n — geri qaytarma (revert) istiqamətinin mətnləri (4 dil). İdempotent.

`handover_actions.revert` artıq oxu qatının blokerlərindən keçir və POST cavabı
kodlardan qurulur (`apps/accounts/views/handover/labels.py`). Geri qaytarma
istiqamətində üç bloker öz mətnini alır («təhvil verilə bilməz» yox, «geri
qaytarıla bilməz») — həmin mətnlər burada dörd dilə doldurulur.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silə bilir) — skript
yalnız ƏLAVƏ edir və mövcud girişə toxunmur.

⚠️ DIRNAQ TƏLƏSİ. Mətnlər burada AÇIQ sadalanır (skan yox), ona görə mənbədəki
`context "…"` / `context '…'` yazılışı nəticəyə təsir etmir.

İstifadə:  python scripts/i18n_fill_handover_revert.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "accounts.handover": {
        # ── Geri qaytarma istiqamətli bloker etiketləri ──────────────────────
        "Semestr təhvildən sonra başa çatıb — tarixi jurnalın sahibliyi geri qaytarılmır": {
            "en": "The semester ended after the handover — ownership of a historical journal is not reverted",
            "ru": "Семестр завершился после передачи — владение историческим журналом не возвращается",
            "tr": "Dönem devirden sonra sona erdi — geçmiş günlüğün sahipliği geri alınmaz",
        },
        "Jurnal bağlanıb — geri qaytarmadan əvvəl RİM jurnalı açmalıdır": {
            "en": "The journal is closed — the registrar must reopen it before reverting",
            "ru": "Журнал закрыт — перед возвратом его должен открыть учебный отдел",
            "tr": "Günlük kapatıldı — geri almadan önce öğrenci işleri günlüğü açmalıdır",
        },
        "Dərs açılışı arxivləşdirilib — geri qaytarma mümkün deyil": {
            "en": "The course offering is archived — it cannot be reverted",
            "ru": "Учебная позиция архивирована — возврат невозможен",
            "tr": "Ders açılışı arşivlendi — geri alma mümkün değil",
        },
        # ── Bloker kodu gəlmədikdə ümumi mətn ───────────────────────────────
        "Geri qaytarma mümkün deyil.": {
            "en": "The handover cannot be reverted.",
            "ru": "Возврат передачи невозможен.",
            "tr": "Devir geri alınamaz.",
        },
        "Təhvil mümkün deyil.": {
            "en": "The handover is not possible.",
            "ru": "Передача невозможна.",
            "tr": "Devir mümkün değil.",
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
