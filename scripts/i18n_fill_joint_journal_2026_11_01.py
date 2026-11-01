"""Append only the joint-journal/history safety UI translations; preserve catalogs."""

import json
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = {
    (None, "Adınıza keçirilmiş birgə dərslər"): (
        "Joint lessons taught by you",
        "Проведённые вами совместные занятия",
        "Birlikte işlediğiniz dersler",
        "Von Ihnen gehaltene gemeinsame Lehrveranstaltungen",
    ),
    (None, "Birgə keçirilmiş dərslər"): (
        "Joint lessons taught",
        "Проведённые совместные занятия",
        "Birlikte işlenen dersler",
        "Gemeinsam gehaltene Lehrveranstaltungen",
    ),
    (None, "Qrupların ayrıca qeydləri"): (
        "Separate group records",
        "Отдельные записи групп",
        "Grupların ayrı kayıtları",
        "Separate Gruppenaufzeichnungen",
    ),
    (None, "Müəllifi göstərilməyən tarixçə"): (
        "History with no recorded instructor",
        "История без указанного преподавателя",
        "Öğretim elemanı belirtilmeyen geçmiş kayıtlar",
        "Historie ohne eingetragene Lehrkraft",
    ),
    (None, "Ayrıca keçirilmiş dərslər"): (
        "Separately taught lessons",
        "Отдельно проведённые занятия",
        "Ayrı işlenen dersler",
        "Separat gehaltene Lehrveranstaltungen",
    ),
    (None, "Bu qeydlər birgə keçirilmiş dərs saatlarına əlavə edilmir; tam tarixçədə ayrıca saxlanılır."): (
        "These records are excluded from joint teaching hours and remain separate in the full history.",
        "Эти записи не добавляются к часам совместных занятий и хранятся отдельно в полной истории.",
        "Bu kayıtlar birlikte işlenen ders saatlerine eklenmez; tam geçmişte ayrı olarak tutulur.",
        "Diese Einträge werden nicht zu den gemeinsamen Unterrichtsstunden addiert und bleiben separat in der vollständigen Historie erhalten.",
    ),
    (None, "Yalnız oxu"): ("Read only", "Только чтение", "Salt okunur", "Nur lesen"),
    (
        "registrar.journal_timing",
        "Bu dərs növündə saxlanmış əvvəlki bal müəllim tərəfindən dəyişdirilə bilməz. Düzəliş üçün RİM-ə müraciət edin.",
    ): (
        "The previously stored score for this lesson type cannot be changed by the teacher. Contact RIM for a correction.",
        "Преподаватель не может изменить ранее сохранённый балл для этого вида занятия. Для исправления обратитесь в РИМ.",
        "Bu ders türünde daha önce kaydedilmiş puan öğretim elemanı tarafından değiştirilemez. Düzeltme için RİM'e başvurun.",
        "Die bereits gespeicherte Note für diese Unterrichtsart kann von der Lehrkraft nicht geändert werden. Wenden Sie sich für eine Korrektur an RIM.",
    ),
}


def fill(language, index):
    path = ROOT / "locale" / language / "LC_MESSAGES" / "django.po"
    catalog = polib.pofile(path)
    added = 0
    for (context, message), translations in MESSAGES.items():
        if catalog.find(message, msgctxt=context):
            continue
        value = message if language == "az" else translations[index]
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n"
                + ("msgctxt " + json.dumps(context) + "\n" if context else "")
                + "msgid "
                + json.dumps(message, ensure_ascii=False)
                + "\nmsgstr "
                + json.dumps(value, ensure_ascii=False)
                + "\n"
            )
        added += 1
    polib.pofile(path).save_as_mofile(path.with_suffix(".mo"))
    return added


if __name__ == "__main__":
    for language, index in (("az", 0), ("en", 0), ("ru", 1), ("tr", 2), ("de", 3)):
        print(f"{language}: {fill(language, index)} added")
