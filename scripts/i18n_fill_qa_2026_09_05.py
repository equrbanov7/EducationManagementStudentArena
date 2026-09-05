#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-05 QA düzəlişlərinin istifadəçi mətnləri. İdempotent.

Jurnal (registrar/views.py — kontekstsiz `gettext`) və sillabus (`accounts.syllabus`
kontekstli TransitionDenied etiketləri) üçün 4 dil doldurulur.
⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir, mövcud girişə toxunmur.
İstifadə:  python scripts/i18n_fill_qa_2026_09_05.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    None: {
        "Seçilmiş müəllim bu təşkilatın tədris heyətində deyil.": {
            "en": "The selected teacher is not on this organisation's teaching staff.",
            "ru": "Выбранный преподаватель не входит в преподавательский состав организации.",
            "tr": "Seçilen öğretim elemanı bu kurumun öğretim kadrosunda değil.",
        },
        "Jurnal bağlıdır — dəyişikliklər yazılmadı.": {
            "en": "The journal is closed — the changes were not saved.",
            "ru": "Журнал закрыт — изменения не сохранены.",
            "tr": "Yoklama defteri kapalı — değişiklikler kaydedilmedi.",
        },
        "Heç bir xana yazılmadı — dərs günü qaydası və ya xana kilidi buna imkan vermədi.": {
            "en": "No cell was saved — the lesson-day rule or a cell lock prevented it.",
            "ru": "Ни одна ячейка не сохранена — помешало правило дня занятия или блокировка ячейки.",
            "tr": "Hiçbir hücre kaydedilmedi — ders günü kuralı veya hücre kilidi buna izin vermedi.",
        },
    },
    "accounts.syllabus": {
        "Bölmə məzmununun formatı düzgün deyil (%(field)s).": {
            "en": "The section content has an invalid format (%(field)s).",
            "ru": "Содержимое раздела имеет неверный формат (%(field)s).",
            "tr": "Bölüm içeriğinin biçimi geçersiz (%(field)s).",
        },
        "Məzmun həddindən böyükdür — ən çox %(max)s (%(field)s).": {
            "en": "The content is too large — at most %(max)s (%(field)s).",
            "ru": "Содержимое слишком велико — не более %(max)s (%(field)s).",
            "tr": "İçerik çok büyük — en fazla %(max)s (%(field)s).",
        },
        "Bu açılış üçün sillabus artıq mövcuddur — siyahıdan açın.": {
            "en": "A syllabus already exists for this course offering — open it from the list.",
            "ru": "Для этого курса силлабус уже существует — откройте его из списка.",
            "tr": "Bu ders açılışı için zaten bir izlence var — listeden açın.",
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
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            probe = f'{head}msgid "{esc(msgid)}"\nmsgstr'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
