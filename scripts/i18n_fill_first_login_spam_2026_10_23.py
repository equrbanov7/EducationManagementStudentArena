#!/usr/bin/env python3
"""EMSArena i18n — ilk girişdə görünən «Spam qovluğuna baxın» xəbərdarlığı (2026-10-23).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

FL = "accounts.first_login"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    FL: {
        "Diqqət:": t("Note:", "Внимание:", "Dikkat:", "Hinweis:"),
        "kod gəlməsə e-poçtunuzun «Spam» (Junk / Lazımsız) qovluğuna mütləq baxın.": t(
            "if the code does not arrive, be sure to check your “Spam” (Junk) folder.",
            "если код не пришёл, обязательно проверьте папку «Спам» (Нежелательная почта).",
            "kod gelmezse e-postanızın “Spam” (Gereksiz) klasörüne mutlaka bakın.",
            "falls der Code nicht ankommt, sehen Sie unbedingt im Ordner „Spam“ (Junk) nach.",
        ),
        "«Gələnlər» qovluğunda yoxdursa, e-poçtunuzun «Spam» (Junk / Lazımsız) qovluğuna baxın — kod çox vaxt ora düşür.": t(
            "If it is not in your Inbox, check your “Spam” (Junk) folder — the code often lands there.",
            "Если письма нет во «Входящих», проверьте папку «Спам» (Нежелательная почта) — код часто попадает туда.",
            "“Gelen kutusu”nda yoksa “Spam” (Gereksiz) klasörüne bakın — kod çoğu zaman oraya düşer.",
            "Wenn sie nicht im Posteingang ist, sehen Sie im Ordner „Spam“ (Junk) nach — der Code landet oft dort.",
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
