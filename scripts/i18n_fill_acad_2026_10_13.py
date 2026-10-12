#!/usr/bin/env python3
"""EMSArena i18n — rol auditi 2026-10-13 B11 (acad): «Cədvəl idarəetməsi» YALNIZ-OXU rejimi.

`schedule.view` daşıyan aktor (prorektor, Tədris şöbəsi, RİM əməkdaşı, qəyyum, inzibati bölmə)
cədvəl bölməsini yalnız-oxu görür — başlıq alt-mətni + status qeydi.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Orkestrator serial işlədir; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_acad_2026_10_13.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

SCHEDULE = "accounts.schedule_manage"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    SCHEDULE: {
        "Cədvələ yalnız baxış icazəniz var — qrup və ya müəllim seçib həftəlik cədvələ baxın.": {
            "en": "You have view-only access to the timetable — pick a group or a teacher to see the week.",
            "ru": "У вас доступ к расписанию только для просмотра — выберите группу или преподавателя, "
            "чтобы увидеть неделю.",
            "tr": "Ders programına yalnızca görüntüleme yetkiniz var — haftayı görmek için bir grup veya "
            "öğretim elemanı seçin.",
        },
        "Yalnız baxış rejimi — cədvəli dəyişmək üçün «Cədvəl idarəetməsi» (schedule.manage) icazəsi lazımdır.": {
            "en": "View-only mode — changing the timetable requires the “Timetable management” "
            "(schedule.manage) permission.",
            "ru": "Режим только для просмотра — для изменения расписания нужно право «Управление расписанием» "
            "(schedule.manage).",
            "tr": "Yalnızca görüntüleme modu — programı değiştirmek için «Ders programı yönetimi» "
            "(schedule.manage) yetkisi gerekir.",
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
