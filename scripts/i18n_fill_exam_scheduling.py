#!/usr/bin/env python3
"""EMSArena i18n — imtahan-cədvəli qaydaları (eyni vaxt / eyni gün). İdempotent.

2026-07: can_user_start yeni blok səbəbləri (başqa imtahanda aktiv cəhd; eyni
gündə rəsmi imtahan) + kabinet modal mətnləri 4 dildə doldurulur.
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "exams.model.access": {
        "other_exam_in_progress": {
            "az": "Hazırda başqa imtahanınız davam edir. Eyni anda yalnız bir imtahan verə bilərsiniz — əvvəlkini tamamlayın.",
            "en": "You already have another exam in progress. You can sit only one exam at a time — finish the current one first.",
            "ru": "У вас уже идёт другой экзамен. Одновременно можно сдавать только один экзамен — сначала завершите текущий.",
            "tr": "Şu anda başka bir sınavınız devam ediyor. Aynı anda yalnızca bir sınava girebilirsiniz — önce mevcut sınavı tamamlayın.",
        },
        "already_examined_today": {
            "az": "Bu gün artıq bir rəsmi imtahan vermisiniz. Eyni gündə ikinci final/kollokvium yalnız imtahan mərkəzi təkrar imtahan (retake) icazəsi veribsə mümkündür.",
            "en": "You have already sat one official exam today. A second final/midterm on the same day is only possible if the exam centre granted a retake.",
            "ru": "Сегодня вы уже сдавали один официальный экзамен. Второй финал/коллоквиум в тот же день возможен, только если экзаменационный центр разрешил пересдачу.",
            "tr": "Bugün zaten bir resmi sınava girdiniz. Aynı gün ikinci final/vize yalnızca sınav merkezi telafi (retake) izni verdiyse mümkündür.",
        },
    },
    "accounts.assigned_tasks": {
        "İmtahana başlamaq mümkün deyil": {
            "en": "Cannot start the exam",
            "ru": "Невозможно начать экзамен",
            "tr": "Sınava başlanamıyor",
        },
        "Başa düşdüm": {"en": "Understood", "ru": "Понятно", "tr": "Anladım"},
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
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            msgstr = translations.get(lang) if lang != "az" else translations.get("az", msgid)
            if msgstr is None:
                msgstr = msgid
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
