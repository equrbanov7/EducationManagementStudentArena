#!/usr/bin/env python3
"""EMSArena i18n — FIX-A (QA 2026-10-17): oxu əhatəsi və şəxsi məlumat sızmaları.

Əlavə olunan mətnlər:
  * `django.po`, `accounts.groups` — qrupun tələbə çekmecəsi tələbə tərəfi açarı istəyir (QA-2 F-03,
    `apps/organizations/group_students.py`);
  * `djangojs.po` (msgctxt YOXDUR) — imtahan sehrbazının tələbə seçicisində boş vəziyyət ipucu (SEC-2 Low #2,
    `apps/exams/static/exams/js/exam_create_edit_modal/searchable_select.js`).

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir (mövcudluq `polib`
ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_fixa_2026_10_17.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

GROUPS = "accounts.groups"

# ENTRIES[domen][ctx][msgid] = {lang: msgstr}. ctx "" → msgctxt yazılmır (JS kataloqu). az msgstr = msgid.
ENTRIES = {
    "django": {
        GROUPS: {
            "Qrupun tələbə siyahısına baxmaq səlahiyyətiniz yoxdur.": {
                "en": "You do not have permission to view this group's student list.",
                "ru": "У вас нет прав на просмотр списка студентов этой группы.",
                "tr": "Bu grubun öğrenci listesini görüntüleme yetkiniz yok.",
                "de": "Sie sind nicht berechtigt, die Studierendenliste dieser Gruppe anzuzeigen.",
            },
        },
    },
    "djangojs": {
        "": {
            "Axtarmaq üçün ən az %(n)s hərf yazın": {
                "en": "Type at least %(n)s letters to search",
                "ru": "Введите не менее %(n)s букв для поиска",
                "tr": "Aramak için en az %(n)s harf yazın",
                "de": "Geben Sie mindestens %(n)s Buchstaben ein, um zu suchen",
            },
        },
    },
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain):
    path = po_path(lang, domain)
    if not os.path.exists(path):
        print(f"{lang}/{domain}: fayl yoxdur, atlandı")
        return
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES[domain].items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            blocks.append(f'{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        for po_domain in ENTRIES:
            fill(locale, po_domain)
