#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-26: «Yeni dərs» köhnə dərsi dəyişmir (o saatda dərs var / keçilmiş mövzu xəbərdarlığı).

``django`` kataloquna beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_new_lesson_slot_taken_2026_11_26.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_J = "registrar.journal"
_P = "registrar.journal_prefill"
_T = "registrar.journal_topics"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (
        _J,
        "Bu jurnalda %(date)s, saat %(time)s üçün artıq «%(lesson)s» dərsi var. Yeni dərs mövcud dərsi dəyişmir — "
        "yeni dərs üçün başqa dərs saatı seçin.",
    ): (
        "This journal already has a “%(lesson)s” lesson on %(date)s at %(time)s. A new lesson does not change the "
        "existing one — choose another lesson time for the new lesson.",
        "В этом журнале на %(date)s, %(time)s уже есть занятие «%(lesson)s». Новое занятие не меняет существующее — "
        "выберите для нового занятия другое время.",
        "Bu yoklama defterinde %(date)s, saat %(time)s için zaten «%(lesson)s» dersi var. Yeni ders mevcut dersi "
        "değiştirmez — yeni ders için başka bir ders saati seçin.",
        "In diesem Journal gibt es am %(date)s um %(time)s bereits die Stunde „%(lesson)s“. Eine neue Stunde ändert "
        "die vorhandene nicht — wählen Sie für die neue Stunde eine andere Zeit.",
    ),
    (_P, "Bu tarix və saatda artıq dərs var"): (
        "There is already a lesson at this date and time",
        "На эту дату и время уже есть занятие",
        "Bu tarih ve saatte zaten ders var",
        "Zu diesem Datum und dieser Uhrzeit gibt es bereits eine Stunde",
    ),
    (_P, "Yeni dərs onu dəyişmir — yeni dərs üçün başqa dərs saatı seçin."): (
        "The new lesson does not change it — choose another lesson time for the new lesson.",
        "Новое занятие его не меняет — выберите для нового занятия другое время.",
        "Yeni ders onu değiştirmez — yeni ders için başka bir ders saati seçin.",
        "Die neue Stunde ändert sie nicht — wählen Sie für die neue Stunde eine andere Zeit.",
    ),
    (_T, "Bu mövzu artıq keçilib — yeni dərs AYRICA sütun kimi əlavə olunur, əvvəlki dərs dəyişmir."): (
        "This topic has already been covered — the new lesson is added as a SEPARATE column, the earlier lesson "
        "does not change.",
        "Эта тема уже пройдена — новое занятие добавляется ОТДЕЛЬНЫМ столбцом, прежнее занятие не меняется.",
        "Bu konu zaten işlendi — yeni ders AYRI bir sütun olarak eklenir, önceki ders değişmez.",
        "Dieses Thema wurde bereits behandelt — die neue Stunde wird als EIGENE Spalte hinzugefügt, die frühere "
        "Stunde bleibt unverändert.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        if added:
            po.save(path)
            subprocess.run(["msgfmt", "-o", path[:-2] + "mo", path], check=True)
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
