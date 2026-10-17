#!/usr/bin/env python3
"""EMSArena i18n — özü yazılmış FİN və rəsmi idxal (SEC-1 F2, sahib 2026-10-17 «tövsiyə olunan kimi»).

`student_intake` kontekstində ön baxış mətnləri (`apps/accounts/services/intake/fin_claims.py`).
msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

SI = "student_intake"

ENTRIES = {
    SI: {
        "Bu FİN artıq sistemdə var (sahibi özü daxil edib, ad-soyad uyğundur) — FİN təsdiqlənir.": {
            "en": "This FIN already exists (entered by its owner, name matches) — the FIN is confirmed.",
            "ru": "Этот FIN уже есть в системе (введён владельцем, имя совпадает) — FIN подтверждается.",
            "tr": "Bu FİN sistemde zaten var (sahibi kendisi girmiş, ad-soyad uyuşuyor) — FİN onaylanıyor.",
            "de": "Diese FIN existiert bereits (vom Inhaber selbst eingegeben, Name stimmt) — die FIN wird bestätigt.",
        },
        (
            "Bu FİN-i başqa adlı hesab özü daxil edib (təsdiqlənməyib) — rəsmi sətir üstündür: FİN o hesabdan "
            "götürüləcək, sahibi FİN-i yenidən yazacaq."
        ): {
            "en": "An account with a different name entered this FIN itself (unverified) — the official row wins: "
            "the FIN will be removed from that account and its owner will be asked to enter it again.",
            "ru": "Этот FIN ввёл сам владелец другого аккаунта с иным именем (не подтверждён) — приоритет у "
            "официальной строки: FIN будет снят с того аккаунта, владельцу нужно будет ввести его заново.",
            "tr": "Bu FİN'i farklı adlı bir hesap kendisi girmiş (onaylanmamış) — resmi satır önceliklidir: FİN o "
            "hesaptan kaldırılacak, sahibi FİN'i yeniden girecek.",
            "de": "Ein Konto mit anderem Namen hat diese FIN selbst eingegeben (unbestätigt) — die offizielle Zeile hat "
            "Vorrang: Die FIN wird diesem Konto entzogen, der Inhaber muss sie erneut eingeben.",
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
