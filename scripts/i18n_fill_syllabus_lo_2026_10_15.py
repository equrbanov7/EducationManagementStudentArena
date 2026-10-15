#!/usr/bin/env python3
"""EMSArena i18n — sillabusda yalnız 1 təlim nəticəsi məcburi, həftəlik bağlama istəyə bağlı (2026-10-15).

Sahib: «Sillabusda təlim nəticəsinin ancaq 1-ni yazmaq məcbur olsun, hər həftəyə görə olmasın.»
Əlavə olunan mətnlər (`accounts.syllabus`):
  * `out` panelinin izahı (`apps/accounts/views/syllabus/editor.py`, `pgettext_lazy`);
  * `out` panelinin ipucu qutusu (`_editor_basics.html`);
  * nəticə silmə xəbərdarlığı (`_editor_dialog.html`);
  * həftə cədvəlinin «Təlim nəticəsi» sütununun «(istəyə bağlı)» qeydi (`_editor_plan.html`,
    `_editor_week_row.html`).

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir (mövcudluq `polib` ilə yoxlanılır — sarılmış uzun msgid-lər də tanınır).
Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_syllabus_lo_2026_10_15.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

SYLLABUS = "accounts.syllabus"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    SYLLABUS: {
        "Tələbə fənni bitirəndə nə bacaracaq. Ən azı 1 təlim nəticəsi yazın; həftəlik mövzuları nəticə ilə "
        "əlaqələndirmək istəyə bağlıdır.": {
            "en": "What the student will be able to do upon completing the course. Write at least 1 learning "
            "outcome; linking weekly topics to an outcome is optional.",
            "ru": "Что студент будет уметь после завершения дисциплины. Укажите хотя бы 1 результат обучения; "
            "привязка недельных тем к результату необязательна.",
            "tr": "Öğrenci dersi tamamladığında neler yapabilecek. En az 1 öğrenme çıktısı yazın; haftalık konuları "
            "bir çıktıyla ilişkilendirmek isteğe bağlıdır.",
            "de": "Was die Studierenden nach Abschluss des Fachs können. Geben Sie mindestens 1 Lernergebnis an; "
            "die Zuordnung der Wochenthemen zu einem Lernergebnis ist optional.",
        },
        "Ən azı 1 təlim nəticəsi yazın. Həftəlik mövzuları nəticə ilə əlaqələndirmək istəyə bağlıdır.": {
            "en": "Write at least 1 learning outcome. Linking weekly topics to an outcome is optional.",
            "ru": "Укажите хотя бы 1 результат обучения. Привязка недельных тем к результату необязательна.",
            "tr": "En az 1 öğrenme çıktısı yazın. Haftalık konuları bir çıktıyla ilişkilendirmek isteğe bağlıdır.",
            "de": "Geben Sie mindestens 1 Lernergebnis an. Die Zuordnung der Wochenthemen zu einem Lernergebnis "
            "ist optional.",
        },
        "Ən azı 1 təlim nəticəsi tələb olunur — silinmə mümkün deyil.": {
            "en": "At least 1 learning outcome is required — deletion is not possible.",
            "ru": "Требуется хотя бы 1 результат обучения — удаление невозможно.",
            "tr": "En az 1 öğrenme çıktısı gereklidir — silme mümkün değildir.",
            "de": "Mindestens 1 Lernergebnis ist erforderlich — Löschen ist nicht möglich.",
        },
        "(istəyə bağlı)": {"en": "(optional)", "ru": "(необязательно)", "tr": "(isteğe bağlı)", "de": "(optional)"},
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
