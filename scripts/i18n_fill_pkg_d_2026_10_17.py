#!/usr/bin/env python3
"""EMSArena i18n — Paket D (imtahan günü: imtahan mərkəzi + imtahana giriş), 2026-10-17.

«İmtahana başla?» təsdiq səhifəsindəki «başlamazdan əvvəl» siyahısı + imtahan mərkəzi
krambının «Kabinet» bəndi. Qalan başlıq sətirləri
(`_breadcrumb.html`) kataloqda artıq var
(«Naviqasiya», «Canlı monitor», «Zal oturumu», «Tarixçə», «Hesabatlar»).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

START = "exams.start_confirm"
CENTER = "exams.final_center"

ENTRIES = {
    CENTER: {
        "Kabinet": {
            "en": "Cabinet",
            "ru": "Кабинет",
            "tr": "Panelim",
            "de": "Mein Bereich",
        },
    },
    START: {
        "Yazdığınız cavablar avtomatik saxlanılır.": {
            "en": "Your typed answers are saved automatically.",
            "ru": "Набранные ответы сохраняются автоматически.",
            "tr": "Yazdığınız cevaplar otomatik olarak kaydedilir.",
            "de": "Ihre getippten Antworten werden automatisch gespeichert.",
        },
        "Vaxt serverdə hesablanır — səhifəni bağlasanız da dayanmır.": {
            "en": "Time is counted on the server — it does not stop if you close the page.",
            "ru": "Время отсчитывается на сервере — оно не останавливается, даже если закрыть страницу.",
            "tr": "Süre sunucuda hesaplanır — sayfayı kapatsanız da durmaz.",
            "de": "Die Zeit läuft auf dem Server — sie stoppt nicht, wenn Sie die Seite schließen.",
        },
        "Başlamazdan əvvəl internet bağlantınızı yoxlayın.": {
            "en": "Check your internet connection before you start.",
            "ru": "Перед началом проверьте подключение к интернету.",
            "tr": "Başlamadan önce internet bağlantınızı kontrol edin.",
            "de": "Prüfen Sie vor dem Start Ihre Internetverbindung.",
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
