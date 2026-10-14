#!/usr/bin/env python3
"""EMSArena i18n — UI düzəlişləri 2026-10-14 (sahib: «yalnız Sınaq» kateqoriyası).

Əlavə olunan mətn:
  * `exams.template.create_exam_modal_form` — sehrbazda kateqoriya yeganə icazəli
    «Sınaq» olduqda select yerinə göstərilən həbin izahı
    (apps/exams/templates/exams/teacher/partials/_exam_category_field.html).

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_uifix_2026_10_14.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

WIZARD = "exams.template.create_exam_modal_form"

# Terminlər modelin «quiz» etiketinin tərcüməsi ilə eynidir (en/tr/de «Quiz», ru «Контрольный опрос»).
# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    WIZARD: {
        "Sizin səlahiyyətinizlə yalnız Sınaq imtahanı yaradılır — kateqoriya avtomatik təyin olunur.": {
            "en": "With your permissions only Quiz exams can be created — the category is set automatically.",
            "ru": "С вашими правами можно создавать только контрольные опросы — категория назначается автоматически.",
            "tr": "Yetkinizle yalnızca Quiz sınavı oluşturulabilir — kategori otomatik olarak atanır.",
            "de": "Mit Ihren Berechtigungen können nur Quiz-Prüfungen erstellt werden — die Kategorie wird automatisch festgelegt.",
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
