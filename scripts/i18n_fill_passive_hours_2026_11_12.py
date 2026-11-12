#!/usr/bin/env python3
"""«Passiv saat» (sahib 2026-11-12, MR-000303): yalnız yeni msgid-ləri əlavə edir; mövcudlara toxunmur."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return dict(zip(LANGS[1:], (en, ru, tr, de)))


def quote(text):
    return json.dumps(text, ensure_ascii=False)


ENTRIES = {
    "django": {
        "registrar.passive_hours": {
            "Passiv saat": t("Passive hours", "Пассивные часы", "Pasif saat", "Passive Stunden"),
            "Passiv saat əlavə et": t(
                "Add passive hours", "Добавить пассивные часы", "Pasif saat ekle", "Passive Stunden hinzufügen"
            ),
            "Hələ passiv saat qeyd olunmayıb.": t(
                "No passive hours recorded yet.",
                "Пассивные часы пока не записаны.",
                "Henüz pasif saat kaydedilmedi.",
                "Noch keine passiven Stunden erfasst.",
            ),
            "Qeyd / mövzu": t("Note / topic", "Заметка / тема", "Not / konu", "Notiz / Thema"),
            "Saat": t("Hours", "Часы", "Saat sayısı", "Stunden"),
            "Tarix": t("Date", "Дата", "Tarih", "Datum"),
            "Sil": t("Delete", "Удалить", "Kaldır", "Löschen"),
            "auditoriyadan kənar (müstəqil) saatlar — davamiyyətə və keçirilmiş dərs saatına daxil deyil": t(
                "out-of-class (independent) hours — not part of attendance or held class hours",
                "внеаудиторные (самостоятельные) часы — не входят в посещаемость и проведённые часы",
                "sınıf dışı (bağımsız) saatler — devama ve işlenen ders saatine dahil değil",
                "Stunden außerhalb des Unterrichts (Selbststudium) — zählen nicht zur Anwesenheit oder zu gehaltenen Stunden",
            ),
            "İntensiv tədris: passiv saat": t(
                "Intensive teaching: passive hours",
                "Интенсивное обучение: пассивные часы",
                "Yoğun öğretim: pasif saat",
                "Intensivunterricht: passive Stunden",
            ),
            "Adi jurnalda passiv saat qeydini açır və ya bağlayır (intensiv tədris olunan qrup). "
            "Yazılmış qeydlər silinmir.": t(
                "Turns passive-hour recording on or off in a regular journal (group taught intensively). "
                "Recorded entries are not deleted.",
                "Включает или выключает учёт пассивных часов в обычном журнале (группа обучается интенсивно). "
                "Записанные данные не удаляются.",
                "Normal yoklamada pasif saat kaydını açar veya kapatır (yoğun öğretilen grup). "
                "Girilmiş kayıtlar silinmez.",
                "Schaltet die Erfassung passiver Stunden in einem regulären Journal ein oder aus "
                "(intensiv unterrichtete Gruppe). Erfasste Einträge werden nicht gelöscht.",
            ),
            "Bu jurnalda passiv saat qeydi açıq deyil.": t(
                "Passive-hour recording is not enabled in this journal.",
                "В этом журнале учёт пассивных часов не включён.",
                "Bu yoklamada pasif saat kaydı açık değil.",
                "In diesem Journal ist die Erfassung passiver Stunden nicht aktiviert.",
            ),
            "Bu jurnalda «Passiv saat» qeydi açıldı.": t(
                "«Passive hours» recording is now on in this journal.",
                "В этом журнале включён учёт «Пассивных часов».",
                "Bu yoklamada «Pasif saat» kaydı açıldı.",
                "In diesem Journal ist die Erfassung «Passive Stunden» jetzt aktiviert.",
            ),
            "Bu jurnalda «Passiv saat» qeydi bağlandı.": t(
                "«Passive hours» recording is now off in this journal.",
                "В этом журнале учёт «Пассивных часов» выключен.",
                "Bu yoklamada «Pasif saat» kaydı kapatıldı.",
                "In diesem Journal ist die Erfassung «Passive Stunden» jetzt deaktiviert.",
            ),
            "Passiv saat qeydi silindi.": t(
                "Passive-hour entry deleted.",
                "Запись пассивных часов удалена.",
                "Pasif saat kaydı silindi.",
                "Eintrag für passive Stunden gelöscht.",
            ),
            "Passiv saat əlavə olundu: %(date)s · %(hours)s saat.": t(
                "Passive hours added: %(date)s · %(hours)s h.",
                "Пассивные часы добавлены: %(date)s · %(hours)s ч.",
                "Pasif saat eklendi: %(date)s · %(hours)s saat.",
                "Passive Stunden hinzugefügt: %(date)s · %(hours)s Std.",
            ),
            "Passiv saatın tarixi %(lo)s – %(hi)s aralığında olmalıdır.": t(
                "The passive-hour date must be between %(lo)s and %(hi)s.",
                "Дата пассивных часов должна быть в диапазоне %(lo)s – %(hi)s.",
                "Pasif saat tarihi %(lo)s – %(hi)s aralığında olmalıdır.",
                "Das Datum der passiven Stunden muss zwischen %(lo)s und %(hi)s liegen.",
            ),
            "Qeyd tapılmadı.": t(
                "Entry not found.", "Запись не найдена.", "Kayıt bulunamadı.", "Eintrag nicht gefunden."
            ),
            "Qeyd ən çox %(max)s simvol ola bilər.": t(
                "The note can be at most %(max)s characters.",
                "Заметка может содержать не более %(max)s символов.",
                "Not en fazla %(max)s karakter olabilir.",
                "Die Notiz darf höchstens %(max)s Zeichen lang sein.",
            ),
            "Saat 1 ilə %(max)s arasında olmalıdır.": t(
                "Hours must be between 1 and %(max)s.",
                "Часы должны быть от 1 до %(max)s.",
                "Saat 1 ile %(max)s arasında olmalıdır.",
                "Die Stunden müssen zwischen 1 und %(max)s liegen.",
            ),
            "Tarixi seçin.": t("Choose a date.", "Выберите дату.", "Tarih seçin.", "Wählen Sie ein Datum."),
        },
        "registrar.model.passive_hour.meta": {
            "passiv saat": t("passive hours entry", "пассивные часы", "pasif saat", "passive Stunden"),
            "passiv saatlar": t("passive hours entries", "пассивные часы", "pasif saatler", "passive Stunden"),
        },
    },
}


def fill():
    counts = {}
    for domain, contexts in ENTRIES.items():
        for lang in LANGS:
            path = BASE / "locale" / lang / "LC_MESSAGES" / f"{domain}.po"
            existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
            blocks = []
            for context, messages in contexts.items():
                for msgid, translations in messages.items():
                    if (context, msgid) in existing:
                        continue
                    value = msgid if lang == "az" else translations[lang]
                    lines = ["#, python-format"] if "%" in msgid else []
                    if context:
                        lines.append("msgctxt " + quote(context))
                    lines += ["msgid " + quote(msgid), "msgstr " + quote(value)]
                    blocks.append("\n".join(lines) + "\n")
            if blocks:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(blocks))
            counts[f"{domain}/{lang}"] = len(blocks)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    fill()
