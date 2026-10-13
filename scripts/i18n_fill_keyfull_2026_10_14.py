#!/usr/bin/env python3
"""EMSArena i18n — açar düzəlişi TAM bal verir (sahib 2026-10-14): apellyasiya baxış ipucu mətni.

⚠️ `makemessages` İŞLƏDİLMİR — idempotent; sonra `compilemessages`.
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = [lang for lang in ("az", "en", "ru", "tr", "de") if os.path.isdir(os.path.join(BASE, "locale", lang))]

ENTRIES = {
    "appeals.template": {
        "«Qəbul et» yalnız bu tələbəyə +1 verir. Açar özü səhvdirsə, düzgün variant(lar)ı seçin — sualı həmin variantla cavablayan hər kəs sualın tam balını alır.": {
            "en": "“Accept” gives +1 only to this student. If the key itself is wrong, select the correct option(s) — everyone who answered with that option gets the question's full points.",
            "ru": "«Принять» даёт +1 только этому студенту. Если ошибочен сам ключ, выберите правильный вариант(ы) — все, кто ответил этим вариантом, получат полный балл за вопрос.",
            "tr": "«Kabul et» yalnızca bu öğrenciye +1 verir. Anahtarın kendisi yanlışsa doğru seçenek(ler)i işaretleyin — soruyu o seçenekle yanıtlayan herkes sorunun tam puanını alır.",
            "de": "„Annehmen“ gibt nur dieser/diesem Studierenden +1. Ist der Schlüssel selbst falsch, wählen Sie die richtige(n) Option(en) — alle, die mit dieser Option geantwortet haben, erhalten die volle Punktzahl der Frage.",
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
