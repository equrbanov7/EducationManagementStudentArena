#!/usr/bin/env python3
"""EMSArena i18n — parol bərpası: SMTP xətası mesajı + «kod gəlmirsə» göstərişi (2026-10-25).

msgid AZ cümlədir → az msgstr = msgid. Şablon `{% trans %}`-i «%» işarəsini «%%» kimi saxlayır (makemessages). İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "accounts.form.password_reset.error": {
        "Məktub göndərilə bilmədi. Bir neçə dəqiqə sonra yenidən cəhd edin.": t(
            "The email could not be sent. Please try again in a few minutes.",
            "Не удалось отправить письмо. Повторите попытку через несколько минут.",
            "E-posta gönderilemedi. Birkaç dakika sonra tekrar deneyin.",
            "Die E-Mail konnte nicht gesendet werden. Bitte versuchen Sie es in einigen Minuten erneut.",
        ),
    },
    "accounts.password_reset_done_page": {
        "Kod gəlmirsə, hesabınızda başqa e-poçt qeydə alınmış ola bilər — RİM-ə müraciət edin.": t(
            "If the code does not arrive, a different email may be registered on your account — contact the RİM office.",
            "Если код не приходит, в вашей учётной записи может быть указан другой e-mail — обратитесь в RİM.",
            "Kod gelmiyorsa hesabınızda farklı bir e-posta kayıtlı olabilir — RİM'e başvurun.",
            "Kommt der Code nicht an, ist in Ihrem Konto möglicherweise eine andere E-Mail-Adresse hinterlegt — wenden Sie sich an das RİM.",
        ),
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
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
