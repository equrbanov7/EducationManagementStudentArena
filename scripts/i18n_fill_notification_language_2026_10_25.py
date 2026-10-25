#!/usr/bin/env python3
"""EMSArena i18n — bildirişlərin oxuyanın dilində göstərilməsi (sahib 2026-10-25).

«Dərs yükü təyin edildi» bildirişi (``apps/workload/services/distribution.py``) əvvəl sərt AZ f-string idi — indi
``LText`` ilə oxuyanın dilində göstərilir, ona görə mətnlər kataloqa düşür (kontekst ``workload.notify``).

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR; skript yalnız çatışmayan blokları əlavə
edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_notification_language_2026_10_25.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

WN = "workload.notify"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    WN: {
        "Dərs yükü təyin edildi: %(head)s — %(hours)d saat": t(
            "Teaching load assigned: %(head)s — %(hours)d hours",
            "Назначена учебная нагрузка: %(head)s — %(hours)d ч.",
            "Ders yükü atandı: %(head)s — %(hours)d saat",
            "Lehrdeputat zugewiesen: %(head)s — %(hours)d Stunden",
        ),
        "%(year)s tədris ili üçün dərs yükünüz təsdiqləndi. Fənn sayı: %(count)d, cəmi %(hours)d saat. "
        "«Dərs yüküm» bölməsindən baxa bilərsiniz.": t(
            "Your teaching load for the %(year)s academic year has been confirmed. Number of subjects: %(count)d, "
            "%(hours)d hours in total. You can view it in the “My teaching load” section.",
            "Ваша учебная нагрузка на %(year)s учебный год утверждена. Количество дисциплин: %(count)d, "
            "всего %(hours)d ч. Посмотреть можно в разделе «Моя учебная нагрузка».",
            "%(year)s eğitim yılı için ders yükünüz onaylandı. Ders sayısı: %(count)d, toplam %(hours)d saat. "
            "«Ders yüküm» bölümünden bakabilirsiniz.",
            "Ihr Lehrdeputat für das Studienjahr %(year)s wurde bestätigt. Anzahl der Fächer: %(count)d, "
            "insgesamt %(hours)d Stunden. Sie finden es im Bereich „Mein Lehrdeputat“.",
        ),
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
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
