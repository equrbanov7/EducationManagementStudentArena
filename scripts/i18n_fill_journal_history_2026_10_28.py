"""Jurnal tarixçəsi mətnləri: append-only, idempotent PO/MO doldurulması."""

import json
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = "registrar.journal_history"
MESSAGES = {
    "Jurnalın müəllim tarixçəsi": (
        "Journal teacher history",
        "История преподавателей журнала",
        "Günlüğün öğretmen geçmişi",
        "Lehrkräfteverlauf des Journals",
    ),
    "Cari jurnal sahibi": (
        "Current journal owner",
        "Текущий владелец журнала",
        "Güncel günlük sahibi",
        "Aktuell zuständige Lehrkraft",
    ),
    "Təhvillər": ("Handovers", "Передачи", "Devirler", "Übergaben"),
    "Geri qaytarılıb": ("Reverted", "Отменено", "Geri alındı", "Rückgängig gemacht"),
    "Bu səhifədə göstərilən dərslər": (
        "Lessons shown on this page",
        "Занятия на этой странице",
        "Bu sayfada gösterilen dersler",
        "Auf dieser Seite angezeigte Stunden",
    ),
    "Dərs müəllimi": ("Lesson teacher", "Преподаватель занятия", "Dersin öğretmeni", "Lehrkraft der Stunde"),
    "Dərsi yaradan": ("Lesson created by", "Занятие создано", "Dersi oluşturan", "Stunde erstellt von"),
    "Qeyd müəllifi": ("Entry author", "Автор записи", "Kaydı giren", "Eintrag erstellt von"),
    "Məlum deyil": ("Unknown", "Неизвестно", "Bilinmiyor", "Unbekannt"),
    "Tarixi müəllim məlum deyilsə, cari sahib onun yerinə göstərilmir.": (
        "If the historical teacher is unknown, the current owner is not shown in their place.",
        "Если прежний преподаватель неизвестен, текущий владелец не указывается вместо него.",
        "Geçmişteki öğretmen bilinmiyorsa yerine güncel sahip gösterilmez.",
        "Ist die frühere Lehrkraft unbekannt, wird die aktuell zuständige Lehrkraft nicht an ihrer Stelle angegeben.",
    ),
}


def fill(language, index):
    path = ROOT / "locale" / language / "LC_MESSAGES" / "django.po"
    catalog = polib.pofile(path)
    count = 0
    for message, values in MESSAGES.items():
        if catalog.find(message, msgctxt=CONTEXT):
            continue
        value = message if language == "az" else values[index]
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                "\nmsgctxt "
                + json.dumps(CONTEXT)
                + "\nmsgid "
                + json.dumps(message, ensure_ascii=False)
                + "\nmsgstr "
                + json.dumps(value, ensure_ascii=False)
                + "\n"
            )
        count += 1
    polib.pofile(path).save_as_mofile(path.with_suffix(".mo"))
    return count


if __name__ == "__main__":
    for language, index in (("az", 0), ("en", 0), ("ru", 1), ("tr", 2), ("de", 3)):
        print(f"{language}: {fill(language, index)} added")
