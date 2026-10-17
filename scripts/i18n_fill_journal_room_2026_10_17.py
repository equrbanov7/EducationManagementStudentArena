#!/usr/bin/env python3
"""EMSArena i18n — «Yeni dərs»də otaq cədvəldən avtomatik 2026-10-17.

Sahib: «Elektron jurnalda yeni dərs əlavə edərkən otaq nömrəsi cədvəldəki avtomatik gəlsin, müəllim istəsə
dəyişə bilər.» Əlavə olunan mətnlər:
  * ``django`` / `registrar.journal_prefill` — dərs modalında cədvəl otağı ipucu və «Cədvəldəki otaq: … ↺»
    düyməsi (`registrar/partials/_jd_lesson_modal.html`).

JS faylları (journal_lesson_schedule.js, journal_lesson_room.js) yeni mətn gətirmir — ``djangojs`` dəyişmir.

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları
əlavə edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_journal_room_2026_10_17.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

PREFILL = "registrar.journal_prefill"

# domen → ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    "django": {
        PREFILL: {
            "Otaq dərs cədvəlindən götürülüb — dəyişə bilərsiniz.": {
                "en": "The room is taken from the timetable — you can change it.",
                "ru": "Аудитория взята из расписания — её можно изменить.",
                "tr": "Derslik ders programından alındı — değiştirebilirsiniz.",
                "de": "Der Raum stammt aus dem Stundenplan — Sie können ihn ändern.",
            },
            "Cədvəldəki otaq": {
                "en": "Timetable room",
                "ru": "Аудитория по расписанию",
                "tr": "Programdaki derslik",
                "de": "Raum laut Stundenplan",
            },
            "Cədvəldəki otağı qaytar": {
                "en": "Restore the timetable room",
                "ru": "Вернуть аудиторию по расписанию",
                "tr": "Programdaki dersliği geri getir",
                "de": "Raum laut Stundenplan wiederherstellen",
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
        for name in ENTRIES:
            fill(locale, name)
