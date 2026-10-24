#!/usr/bin/env python3
"""EMSArena i18n — «Müraciətlərim → Bütün müraciətlər» (RİM nəzarəti) tabı (2026-10-24).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

APX = "applications"
PERM = "organizations.permission.label"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    APX: {
        "Bütün müraciətlər": t("All applications", "Все обращения", "Tüm başvurular", "Alle Anträge"),
        "Şöbə (ünvan)": t("Department (addressee)", "Отдел (адресат)", "Birim (muhatap)", "Abteilung (Empfänger)"),
        "Bütün şöbələr": t("All departments", "Все отделы", "Tüm birimler", "Alle Abteilungen"),
        "Göndərənin bölməsi": t(
            "Sender's unit", "Подразделение отправителя", "Gönderenin birimi", "Einheit des Absenders"
        ),
        "Bütün göndərənlər": t("All senders", "Все отправители", "Tüm gönderenler", "Alle Absender"),
        "Fakültələr": t("Faculties", "Факультеты", "Fakülteler", "Fakultäten"),
        "Kafedralar": t("Departments (chairs)", "Кафедры", "Bölümler", "Lehrstühle"),
        "Mərkəz və digər bölmələr": t(
            "Centres and other units",
            "Центры и другие подразделения",
            "Merkezler ve diğer birimler",
            "Zentren und andere Einheiten",
        ),
    },
    PERM: {
        "Bütün müraciətlərə baxmaq (yalnız oxu)": t(
            "View all applications (read-only)",
            "Просмотр всех обращений (только чтение)",
            "Tüm başvuruları görüntüleme (salt okunur)",
            "Alle Anträge einsehen (nur lesen)",
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
