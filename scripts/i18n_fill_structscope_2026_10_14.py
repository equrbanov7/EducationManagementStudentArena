#!/usr/bin/env python3
"""EMSArena i18n — struktur ağacı əhatəsi + qrup paneli (starosta / tələbələr), 2026-10-14.

Əlavə olunan mətnlər (`accounts.structure_tree`):
  * qrup detalında «Tyutor» kartı (qrupun `head`-i), «Qrupun tələbələri» siyahısı və boş halları;
  * starosta seçicisinin boş halı (qrupda qeydiyyatlı tələbə yoxdur).
Starosta düymələri / dialoq mətnləri «Qruplar» reyestrindən TƏKRAR istifadə olunur (`accounts.group_lead`).

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_structscope_2026_10_14.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

TREE = "accounts.structure_tree"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    TREE: {
        "Tyutor": {"en": "Tutor", "ru": "Тьютор", "tr": "Danışman", "de": "Tutor/in"},
        "Qrupun tələbələri": {
            "en": "Students of the group",
            "ru": "Студенты группы",
            "tr": "Grubun öğrencileri",
            "de": "Studierende der Gruppe",
        },
        "Bu qrupda hələ tələbə yoxdur.": {
            "en": "This group has no students yet.",
            "ru": "В этой группе пока нет студентов.",
            "tr": "Bu grupta henüz öğrenci yok.",
            "de": "Diese Gruppe hat noch keine Studierenden.",
        },
        "Bu qrupda seçilə bilən qeydiyyatlı tələbə yoxdur.": {
            "en": "This group has no enrolled student who can be selected.",
            "ru": "В этой группе нет зачисленных студентов, которых можно выбрать.",
            "tr": "Bu grupta seçilebilecek kayıtlı öğrenci yok.",
            "de": "In dieser Gruppe gibt es keine eingeschriebenen Studierenden zur Auswahl.",
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
