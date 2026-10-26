#!/usr/bin/env python3
"""EMSArena i18n — jurnal xana kilidi: balsız i/e pəncərədən sonra da dəyişir (sahib 2026-10-26).

Yeni mətnlər: q/b/bal kilidinin dəqiqləşdirilmiş mesajı və yazma müddəti bitmiş i/e xanasının mesajı
(``journal_edit_windows.lock_message``). msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud
msgctxt+msgid toxunulmur); sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ENTRIES = {
    "registrar.journal_timing": {
        "Bu q/b və ya bal %(m)s dəqiqədən çox əvvəl yazılıb və dəyişdirilə bilməz. Dəyişiklik üçün RİM-ə "
        "müraciət edib təqdimat yazın.": {
            "en": "This absence or score was entered more than %(m)s minutes ago and cannot be changed. To change "
            "it, submit a request to the Registrar's Office (RİM) with a written statement.",
            "ru": "Эта отметка «н/б» или балл внесены более %(m)s минут назад и не могут быть изменены. Для "
            "изменения обратитесь в РИМ с письменным представлением.",
            "tr": "Bu devamsızlık veya puan %(m)s dakikadan daha önce yazıldı ve değiştirilemez. Değişiklik için "
            "RİM'e başvurup dilekçe yazın.",
            "de": "Diese Abwesenheit oder Punktzahl wurde vor mehr als %(m)s Minuten eingetragen und kann nicht "
            "geändert werden. Für eine Änderung reichen Sie beim RİM einen schriftlichen Antrag ein.",
        },
        "Bu dərsin yazma müddəti bitib — i/e qeydi artıq dəyişdirilə bilməz. Dəyişiklik üçün RİM-ə müraciət "
        "edib təqdimat yazın.": {
            "en": "The entry period for this lesson has ended — the “present” mark can no longer be changed. To "
            "change it, submit a request to the Registrar's Office (RİM) with a written statement.",
            "ru": "Срок внесения записей по этому занятию истёк — отметку «присутствовал» больше нельзя изменить. "
            "Для изменения обратитесь в РИМ с письменным представлением.",
            "tr": "Bu dersin giriş süresi doldu — «katıldı» kaydı artık değiştirilemez. Değişiklik için RİM'e "
            "başvurup dilekçe yazın.",
            "de": "Die Eintragungsfrist für diese Lehrveranstaltung ist abgelaufen — die Markierung „anwesend“ "
            "kann nicht mehr geändert werden. Für eine Änderung reichen Sie beim RİM einen schriftlichen Antrag ein.",
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
            msgstr = translations.get("az", msgid) if lang == "az" else (translations.get(lang) or msgid)
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
