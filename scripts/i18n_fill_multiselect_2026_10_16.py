#!/usr/bin/env python3
"""EMSArena i18n — stilli çoxseçimli seçici (EMSMultiSelect) 2026-10-16.

Sahib qaydası (2026-09-09): «hər yerdə stilli select, uzun siyahıda menyu-daxili axtarış». Native
``<select multiple>``-lər `static/js/ems_multi_select.js` komponentinə keçdi. Əlavə olunan mətnlər:
  * ``djangojs`` (msgctxt YOX) — komponentin öz mətnləri (placeholder, axtarış, «Hamısı / Təmizlə»,
    «{count} seçilib»);
  * ``django`` / `accounts.workload` — «Yük bölgüsü» sətir modalında qrup seçicisi
    (`_workload_distribution.html`);
  * ``django`` / `accounts.semester` — «Plandan açılış yarat» ixtisas seçicisi
    (`teaching_office/_generate_fields.html`);
  * ``django`` / `accounts.workload_center` — «Tədris planından gətir» ixtisas seçicisi
    (`workload/_generate_fields.html`).

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları
əlavə edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_multiselect_2026_10_16.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

PROGRAMS_COUNT = {
    "en": "{count} programmes selected",
    "ru": "Выбрано специальностей: {count}",
    "tr": "{count} program seçildi",
    "de": "{count} Studiengänge ausgewählt",
}
PROGRAMS_SEARCH = {
    "en": "Search programmes…",
    "ru": "Поиск специальности…",
    "tr": "Program ara…",
    "de": "Studiengang suchen…",
}

# domen → ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    "django": {
        "accounts.workload": {
            "{count} qrup seçilib": {
                "en": "{count} groups selected",
                "ru": "Выбрано групп: {count}",
                "tr": "{count} grup seçildi",
                "de": "{count} Gruppen ausgewählt",
            },
            "Qrup axtar…": {"en": "Search groups…", "ru": "Поиск группы…", "tr": "Grup ara…", "de": "Gruppe suchen…"},
        },
        "accounts.semester": {
            "Bütün aktiv ixtisaslar": {
                "en": "All active programmes",
                "ru": "Все активные специальности",
                "tr": "Tüm aktif programlar",
                "de": "Alle aktiven Studiengänge",
            },
            "{count} ixtisas seçilib": PROGRAMS_COUNT,
            "İxtisas axtar…": PROGRAMS_SEARCH,
        },
        "accounts.workload_center": {
            "Kafedranın bütün ixtisasları": {
                "en": "All programmes of the department",
                "ru": "Все специальности кафедры",
                "tr": "Bölümün tüm programları",
                "de": "Alle Studiengänge des Lehrstuhls",
            },
            "{count} ixtisas seçilib": PROGRAMS_COUNT,
            "İxtisas axtar…": PROGRAMS_SEARCH,
        },
    },
    "djangojs": {
        "": {
            "Seçilməyib": {"en": "Not selected", "ru": "Не выбрано", "tr": "Seçilmedi", "de": "Nicht ausgewählt"},
            "Axtar…": {"en": "Search…", "ru": "Поиск…", "tr": "Ara…", "de": "Suchen…"},
            "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü", "de": "Alle"},
            "Təmizlə": {"en": "Clear", "ru": "Очистить", "tr": "Temizle", "de": "Leeren"},
            "Uyğun nəticə yoxdur": {
                "en": "No matches",
                "ru": "Совпадений нет",
                "tr": "Eşleşme yok",
                "de": "Keine Treffer",
            },
            "{count} seçilib": {
                "en": "{count} selected",
                "ru": "Выбрано: {count}",
                "tr": "{count} seçildi",
                "de": "{count} ausgewählt",
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
        for name in ("django", "djangojs"):
            fill(locale, name)
