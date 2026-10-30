"""Append-only translations for current workload and protected own journal history."""

import json
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = {
    "Davamiyyət": ("Attendance", "Посещаемость", "Devam durumu", "Anwesenheit"),
    "dərs": ("lessons", "занятий", "ders", "Stunden"),
    "saat": ("hours", "часов", "ders saati", "Lehrstunden"),
    "Öz jurnal qeydlərim": (
        "My journal entries",
        "Мои записи журнала",
        "Kendi günlük kayıtlarım",
        "Meine Journaleinträge",
    ),
    "Bu fənn üzrə cari dərs yükü təyinatınız yoxdur. Yalnız əvvəl adınıza keçirilmiş və ya sizin yazdığınız dərslər və daxil etdiyiniz xanalar göstərilir. Tarixçə yalnız oxunur.": (
        "You have no current workload assignment for this subject. Only lessons previously attributed to or created by you and cells you entered are shown. History is read-only.",
        "По этому предмету у вас нет текущего назначения нагрузки. Показаны только занятия, проведённые или созданные вами, и введённые вами ячейки. История доступна только для чтения.",
        "Bu ders için güncel yük atamanız yok. Yalnızca daha önce adınıza işlenen veya oluşturduğunuz dersler ve girdiğiniz hücreler gösterilir. Geçmiş salt okunurdur.",
        "Für dieses Fach haben Sie keinen aktuellen Lehrauftrag. Angezeigt werden nur Ihnen zugeordnete oder von Ihnen erstellte Stunden und Ihre Zelleinträge. Der Verlauf ist schreibgeschützt.",
    ),
    "Bu dərsdə şəxsən daxil etdiyiniz bal/davamiyyət xanası yoxdur.": (
        "You have not personally entered any grade or attendance cells in this lesson.",
        "В этом занятии нет ячеек оценок или посещаемости, введённых лично вами.",
        "Bu derste şahsen girdiğiniz not veya devam hücresi yok.",
        "Für diese Stunde haben Sie keine Noten- oder Anwesenheitszellen eingegeben.",
    ),
    "Jurnal tarixçəsinə qayıt": (
        "Return to journal history",
        "Вернуться к истории журнала",
        "Günlük geçmişine dön",
        "Zum Journalverlauf zurück",
    ),
    "Cari dərs yükü": (
        "Current teaching workload",
        "Текущая учебная нагрузка",
        "Güncel ders yükü",
        "Aktuelle Lehrbelastung",
    ),
    "Tarixçə: cari yük təyinatı yoxdur": (
        "History: no current workload assignment",
        "История: текущего назначения нагрузки нет",
        "Geçmiş: güncel yük ataması yok",
        "Verlauf: kein aktueller Lehrauftrag",
    ),
    "Adınıza keçirilmiş": (
        "Lessons attributed to you",
        "Занятия, проведённые вами",
        "Adınıza işlenen dersler",
        "Ihnen zugeordnete Stunden",
    ),
    "Qeyd daxil etdiyiniz": (
        "Lessons with your entries",
        "Занятия с вашими записями",
        "Kayıt girdiğiniz dersler",
        "Stunden mit Ihren Einträgen",
    ),
    "GÖRÜNÜŞ": ("VIEW", "ВИД", "GÖRÜNÜM", "ANSICHT"),
    "Cari dərs yüküm": (
        "My current workload",
        "Моя текущая нагрузка",
        "Güncel ders yüküm",
        "Meine aktuelle Lehrbelastung",
    ),
    "Əvvəlki jurnal qeydlərim": (
        "My previous journal entries",
        "Мои прежние записи журнала",
        "Önceki günlük kayıtlarım",
        "Meine früheren Journaleinträge",
    ),
}


def fill(language, index):
    path = ROOT / "locale" / language / "LC_MESSAGES" / "django.po"
    catalog = polib.pofile(path)
    for message, translations in MESSAGES.items():
        if catalog.find(message, msgctxt=None):
            continue
        value = message if language == "az" else translations[index]
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                "\nmsgid "
                + json.dumps(message, ensure_ascii=False)
                + "\nmsgstr "
                + json.dumps(value, ensure_ascii=False)
                + "\n"
            )
    polib.pofile(path).save_as_mofile(path.with_suffix(".mo"))


if __name__ == "__main__":
    for language, index in (("az", 0), ("en", 0), ("ru", 1), ("tr", 2), ("de", 3)):
        fill(language, index)
