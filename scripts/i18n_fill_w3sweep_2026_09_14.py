#!/usr/bin/env python3
"""EMSArena i18n — W3 `w3sweep` brauzer süpürgəsi (2026-09-14).

1. ƏLAVƏ: Sual bankı səhifəsi (`question_bank_detail`) imtahanla PAYLAŞILAN
   `_question_management.html` partial-ını işlədir; boş vəziyyətdə «Bu imtahanda
   hələ sual yoxdur.» yazılırdı. Bank konteksti (`qm_context == "bank"`) üçün
   ayrıca mətn əlavə olunur (`exams.question_bank.empty`).

2. DÜZƏLİŞ (mövcud msgstr-lər, `exams.template.teacher_pending_attempts`):
   brauzerdə `/exams/pending-work/` səhifəsinin başlığı 4 dildə «Yeni Kurs
   Yaratma / Create a New Course» idi, boş vəziyyət («Great work! The grading
   queue is empty»), sayğac etiketi («Status») və status nişanları («Pending»,
   «Submitted») isə AZ/RU/TR-də ingiliscə qalmışdı. Yalnız sadalanan üçlüklər
   dəyişir.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir və
idempotentdir. TR qarşılığı QƏSDƏN AZ mənbədən fərqlidir (i18n qapısı
`msgstr == msgid` sətrini «tərcümə olunmamış» sayır).

İstifadə:  python scripts/i18n_fill_w3sweep_2026_09_14.py
           python manage.py compilemessages
"""

import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CTX = "exams.question_bank.empty"

ENTRIES = {
    CTX: {
        "Bu bankda hələ sual yoxdur.": {
            "en": "There are no questions in this bank yet.",
            "ru": "В этом банке пока нет вопросов.",
            "tr": "Bu bankada henüz soru yok.",
        },
    },
}

PA = "exams.template.teacher_pending_attempts"

FIXES = {
    (PA, "page_title"): {
        "az": "Yoxlanılacaq işlər",
        "en": "Work awaiting review",
        "ru": "Работы на проверку",
        "tr": "İncelenecek çalışmalar",
    },
    (PA, "label_task"): {"az": "iş", "en": "items", "ru": "работ", "tr": "çalışma"},
    (PA, "status_reviewing"): {"az": "Baxılır", "en": "Reviewing", "ru": "На проверке", "tr": "İnceleniyor"},
    (PA, "status_submitted"): {"az": "Təqdim edilib", "en": "Submitted", "ru": "Отправлено", "tr": "Gönderildi"},
    (PA, "empty_title"): {"az": "Əla iş!", "en": "Great work!", "ru": "Отличная работа!", "tr": "Harika iş!"},
    (PA, "empty_description"): {
        "az": "Yoxlama növbəsi boşdur.",
        "en": "The grading queue is empty.",
        "ru": "Очередь на проверку пуста.",
        "tr": "İnceleme kuyruğu boş.",
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
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    fixed = 0
    for (ctx, msgid), per_lang in FIXES.items():
        new = per_lang.get(lang)
        if new is None:
            continue
        # Tək-sətirli msgstr-ə düzəliş; blok tapılmasa səssiz keçir (drift yox).
        pattern = re.compile(
            r'(msgctxt "' + re.escape(esc(ctx)) + r'"\nmsgid "' + re.escape(esc(msgid)) + r'"\nmsgstr ")([^"\n]*)(")',
        )
        text, count = pattern.subn(lambda m, rep=esc(new): m.group(1) + rep + m.group(3), text, count=1)
        fixed += count

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
    if blocks or fixed:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry, {fixed} düzəliş")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
