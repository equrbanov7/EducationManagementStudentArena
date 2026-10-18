#!/usr/bin/env python3
"""EMSArena i18n — nəzarətçi növbəsi axtarış ipucu (sahib 2026-10-18). İdempotent; sonra compilemessages."""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ENTRIES = {
    "exams.final_center.invigilators": {
        (
            "Siyahıda yalnız nəzarətçi təyin oluna bilən müəllim və əməkdaşlar var. Siyahıdan «+» ilə seçin və ya ad "
            "yazın (ən az 2 hərf)."
        ): {
            "en": "Only teachers and staff who can be invigilators are listed. Pick with «+» or type a name (at least 2 letters).",
            "ru": "В списке только преподаватели и сотрудники, которых можно назначить наблюдателями. Выберите «+» или введите имя (не менее 2 букв).",
            "tr": "Listede yalnızca gözetmen atanabilecek öğretim üyeleri ve personel var. «+» ile seçin veya ad yazın (en az 2 harf).",
            "de": "Aufgeführt sind nur Lehrkräfte und Mitarbeitende, die Aufsicht führen können. Mit «+» wählen oder Namen eingeben (mind. 2 Buchstaben).",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def fill(lang):
    path = po_path(lang)
    existing = {(e.msgctxt, e.msgid) for e in polib.pofile(path) if not e.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    blocks = []
    for ctx, messages in ENTRIES.items():
        for msgid, tr in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else tr.get(lang) or msgid
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
    if blocks:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.rstrip("\n") + "\n\n" + "\n".join(blocks))
    print(f"{lang}: +{len(blocks)} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
