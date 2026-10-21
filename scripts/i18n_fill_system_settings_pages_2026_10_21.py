#!/usr/bin/env python3
"""EMSArena i18n — «Sistem tənzimləmələri» alt səhifələri (sidebar qrupu, ümumi baxış, axtarış; sahib 2026-10-21).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur); cəm formaları
(`blocktrans count`) hər dilin öz ``Plural-Forms`` sayı ilə yazılır. Sonra `compilemessages -i .claude -i venv`.
"""

import os
import re

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RS = "accounts.runtime_settings"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


AZ_OVERRIDES = {}

ENTRIES = {
    RS: {
        "Ümumi baxış": t("Overview", "Обзор", "Genel bakış", "Übersicht"),
        "Tənzimləmə qrupları": t("Settings groups", "Группы настроек", "Ayar grupları", "Einstellungsgruppen"),
        "Hamısı standartdır": t("All default", "Все по умолчанию", "Tümü varsayılan", "Alles Standard"),
        "Tənzimləmələrdə axtar": t(
            "Search settings", "Поиск по настройкам", "Ayarlarda ara", "Einstellungen durchsuchen"
        ),
        "Tənzimləmələrdə axtar: ad, izah və ya açar": t(
            "Search settings: name, description or key",
            "Поиск по настройкам: название, описание или ключ",
            "Ayarlarda ara: ad, açıklama veya anahtar",
            "Einstellungen durchsuchen: Name, Beschreibung oder Schlüssel",
        ),
        "Heç nə tapılmadı": t("Nothing found", "Ничего не найдено", "Hiçbir şey bulunamadı", "Nichts gefunden"),
        "Tapıldı: {n}": t("Found: {n}", "Найдено: {n}", "Bulundu: {n}", "Gefunden: {n}"),
    },
}

#: Cəm formalı mesajlar: (ctx, msgid, msgid_plural) → dil → formalar (Plural-Forms sırası ilə).
PLURALS = {
    (RS, "%(n)s tənzimləmə", "%(n)s tənzimləmə"): {
        "az": ["%(n)s tənzimləmə", "%(n)s tənzimləmə"],
        "en": ["%(n)s setting", "%(n)s settings"],
        "ru": ["%(n)s настройка", "%(n)s настройки", "%(n)s настроек", "%(n)s настройки"],
        "tr": ["%(n)s ayar", "%(n)s ayar"],
        "de": ["%(n)s Einstellung", "%(n)s Einstellungen"],
    },
    (RS, "%(n)s dəyişdirilib", "%(n)s dəyişdirilib"): {
        "az": ["%(n)s dəyişdirilib", "%(n)s dəyişdirilib"],
        "en": ["%(n)s changed", "%(n)s changed"],
        "ru": ["%(n)s изменена", "%(n)s изменены", "%(n)s изменено", "%(n)s изменены"],
        "tr": ["%(n)s değiştirildi", "%(n)s değiştirildi"],
        "de": ["%(n)s geändert", "%(n)s geändert"],
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def nplurals(po):
    match = re.search(r"nplurals\s*=\s*(\d+)", po.metadata.get("Plural-Forms", ""))
    return int(match.group(1)) if match else 2


def fill(lang):
    path = po_path(lang)
    po = polib.pofile(path)
    existing = {(entry.msgctxt, entry.msgid) for entry in po if not entry.obsolete}
    count = nplurals(po)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            if lang == "az":
                msgstr = AZ_OVERRIDES.get((ctx, msgid), msgid)
            else:
                msgstr = translations.get(lang) or msgid
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    for (ctx, msgid, msgid_plural), forms_by_lang in PLURALS.items():
        if (ctx, msgid) in existing:
            continue
        forms = list(forms_by_lang.get(lang) or [msgid, msgid_plural])
        forms = (forms + [forms[-1]] * count)[:count]
        lines = [
            f'#, python-format\nmsgctxt "{esc(ctx)}"',
            f'msgid "{esc(msgid)}"',
            f'msgid_plural "{esc(msgid_plural)}"',
        ]
        lines += [f'msgstr[{index}] "{esc(form)}"' for index, form in enumerate(forms)]
        blocks.append("\n".join(lines) + "\n")
        added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
