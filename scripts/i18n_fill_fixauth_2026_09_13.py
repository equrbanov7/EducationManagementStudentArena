#!/usr/bin/env python3
"""EMSArena i18n — access auditi düzəlişləri (`fixauth`, 2026-09-13).

F-08: ilk-giriş axınında başqa hesabın e-poçtuna kod göndərilməsi bloklanır —
istifadəçiyə generik mesaj göstərilir (`apps/accounts/views/auth/first_login.py`).

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız əlavə edir və idempotentdir.
TR qarşılığı QƏSDƏN AZ mənbədən fərqlidir — i18n qapısı `msgstr == msgid`
sətrini «tərcümə olunmamış» sayır.

İstifadə:  python scripts/i18n_fill_fixauth_2026_09_13.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# msgid = AZ mətn; msgstr: az = msgid, digərləri lüğətdən.
ENTRIES = {
    "accounts.first_login": {
        "Bu email ünvanı istifadə oluna bilməz. Başqa ünvan daxil edin.": {
            "en": "This e-mail address cannot be used. Enter a different address.",
            "ru": "Этот адрес электронной почты использовать нельзя. Введите другой адрес.",
            "tr": "Bu e-posta adresi kullanılamaz. Başka bir adres girin.",
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
