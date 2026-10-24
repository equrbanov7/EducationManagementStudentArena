#!/usr/bin/env python3
"""EMSArena i18n — sillabusun plan saatının kafedra düzəlişi (sahib 2026-10-25).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

SYL = "accounts.syllabus"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    SYL: {
        "Plan saatı düzəldildi — %(count)s versiya yeniləndi.": t(
            "Planned hours corrected — %(count)s version(s) updated.",
            "Плановые часы исправлены — обновлено версий: %(count)s.",
            "Plan saatleri düzeltildi — %(count)s sürüm güncellendi.",
            "Planstunden korrigiert — %(count)s Version(en) aktualisiert.",
        ),
        "Əl ilə düzəliş silindi — saat yenidən tədris planı / dərs yükündən gəlir.": t(
            "Manual correction removed — hours come from the curriculum / teaching load again.",
            "Ручная правка удалена — часы снова берутся из учебного плана / учебной нагрузки.",
            "Elle düzeltme kaldırıldı — saatler yeniden öğretim planından / ders yükünden gelir.",
            "Manuelle Korrektur entfernt — die Stunden kommen wieder aus dem Lehrplan / Lehrdeputat.",
        ),
        "Plan saatı kafedra tərəfindən əl ilə düzəldilib (bir qrup üçün):": t(
            "Planned hours were corrected manually by the chair (for one group):",
            "Плановые часы исправлены кафедрой вручную (для одной группы):",
            "Plan saatleri bölüm tarafından elle düzeltildi (bir grup için):",
            "Die Planstunden wurden vom Lehrstuhl manuell korrigiert (für eine Gruppe):",
        ),
        "Plan saatını düzəlt — sillabusda fənnin BİR qrup üçün saatı yazılır (müəllimin ümumi dərs yükü deyil):": t(
            "Correct the planned hours — the syllabus shows the subject's hours for ONE group (not the teacher's total load):",
            "Исправить плановые часы — в силлабусе указываются часы дисциплины для ОДНОЙ группы (а не общая нагрузка преподавателя):",
            "Plan saatlerini düzelt — izlencede dersin BİR grup için saatleri yazılır (öğretim elemanının toplam yükü değil):",
            "Planstunden korrigieren — der Syllabus zeigt die Stunden des Fachs für EINE Gruppe (nicht das Gesamtdeputat der Lehrkraft):",
        ),
        "Avtomatik hesab (tədris planı / dərs yükü): %(auto)s": t(
            "Automatic calculation (curriculum / teaching load): %(auto)s",
            "Автоматический расчёт (учебный план / нагрузка): %(auto)s",
            "Otomatik hesap (öğretim planı / ders yükü): %(auto)s",
            "Automatische Berechnung (Lehrplan / Lehrdeputat): %(auto)s",
        ),
        "Plan saatını yadda saxla": t(
            "Save planned hours", "Сохранить плановые часы", "Plan saatlerini kaydet", "Planstunden speichern"
        ),
        "Avtomatik hesaba qayıt": t(
            "Back to automatic calculation",
            "Вернуться к автоматическому расчёту",
            "Otomatik hesaba dön",
            "Zurück zur automatischen Berechnung",
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
