#!/usr/bin/env python3
"""EMSArena i18n — dalğa 2 `w2rbac` (2026-09-14): bal yazan endpoint-lərin rate-limit mesajı.

Backend auditi 2026-09-13 F-15: `core/write_rate_limit.py` dekoratoru 429 JSON
cavabında istifadəçiyə göstərilən BİR yeni mətn işlədir (`core.rate_limit`
konteksti). Mövcud `live_exam.consumer.error|rate_limited` msgid-i təkrar
istifadə OLUNMADI — onun msgstr-i kataloqda yanlışdır («Format: say/müddət…»).

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız əlavə edir və idempotentdir.
Orkestrator bütün fill skriptlərini sonda ardıcıl işlədir; sonra
`python manage.py compilemessages`.
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "core.rate_limit": {
        "Çox tez-tez sorğu göndərilir — bir az sonra yenidən cəhd edin.": {
            "en": "Too many requests — please try again in a moment.",
            "ru": "Слишком много запросов — повторите попытку чуть позже.",
            "tr": "Çok sık istek gönderiliyor — biraz sonra yeniden deneyin.",
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
