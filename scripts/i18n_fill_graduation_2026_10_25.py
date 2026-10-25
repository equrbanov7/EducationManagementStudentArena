#!/usr/bin/env python3
"""EMSArena i18n — «Məzun etmə» tələbə hərəkəti + qrup çekmecəsində məzunlar (2026-10-25).

msgid AZ cümlədir → az msgstr = msgid. Şablon `{% trans %}`-i «%» işarəsini «%%» kimi saxlayır (makemessages). İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "ui.status": {"Məzun etmə": t("Graduation", "Выпуск (окончание обучения)", "Mezuniyet", "Studienabschluss")},
    "accounts.groups": {
        "%%d qrupdan çıxıb (məzuniyyət / xaric / məzun)": t(
            "%%d left the group (leave / expelled / graduated)",
            "%%d выбыли из группы (отпуск / отчисление / выпуск)",
            "%%d gruptan ayrıldı (izin / kayıt silme / mezun)",
            "%%d haben die Gruppe verlassen (Beurlaubung / Exmatrikulation / Abschluss)",
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
