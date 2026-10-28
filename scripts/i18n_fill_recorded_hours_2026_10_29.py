"""Append-only translations for the separate recorded teaching-hours table."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parent.parent
CONTEXT = "workload.recorded"
LANGUAGES = ("en", "ru", "tr", "de")
ENTRIES = {
    "Jurnalda qeydə alınmış dərs saatlarım": (
        "My recorded teaching hours",
        "Мои учебные часы по журналу",
        "Günlüğe kaydedilen ders saatlerim",
        "Meine erfassten Unterrichtsstunden",
    ),
    "Dərsin müəllimi kimi adınız yazılmış saatlar göstərilir. Təhvil tarixçəsi saxlanılır; bu rəqəmlər rəsmi yük bölgüsünü dəyişmir. Gələcək tarixli dərslər daxil deyil.": (
        "Hours explicitly recorded with you as the teacher are shown. Handover history is retained; these figures do not change the official workload allocation. Future lessons are excluded.",
        "Показаны часы, в которых вы явно указаны преподавателем. История передачи сохраняется; эти цифры не меняют официальное распределение нагрузки. Будущие занятия исключены.",
        "Öğretmen olarak adınızın açıkça yazıldığı saatler gösterilir. Devir geçmişi korunur; bu sayılar resmi ders yükü dağılımını değiştirmez. Gelecek dersler dahil değildir.",
        "Angezeigt werden Stunden, in denen Sie ausdrücklich als Lehrkraft erfasst sind. Die Übergabehistorie bleibt erhalten; diese Zahlen ändern die offizielle Lehrverteilung nicht. Zukünftige Termine sind ausgeschlossen.",
    ),
    "Fənn / kafedra": ("Subject / department", "Предмет / кафедра", "Ders / bölüm", "Fach / Fachbereich"),
    "Qrup / semestr": ("Group / semester", "Группа / семестр", "Grup / dönem", "Gruppe / Semester"),
    "Mühazirə": ("Lecture", "Лекция", "Ders anlatımı", "Vorlesung"),
    "Seminar": ("Seminar hours", "Семинар", "Seminer", "Seminarstunden"),
    "Laboratoriya": ("Laboratory", "Лаборатория", "Laboratuvar", "Labor"),
    "Qeydə alınmış saatım": ("My recorded hours", "Мои учтённые часы", "Kayıtlı saatlerim", "Meine erfassten Stunden"),
    "Müəllifi dəqiqləşdirilməmiş saat": (
        "Hours with unidentified teacher",
        "Часы без установленного преподавателя",
        "Öğretmeni belirlenmemiş saatler",
        "Stunden ohne zugeordnete Lehrkraft",
    ),
    "Cari müəllim / təhvil tarixçəsi": (
        "Current teacher / handover history",
        "Текущий преподаватель / история передачи",
        "Mevcut öğretmen / devir geçmişi",
        "Aktuelle Lehrkraft / Übergabehistorie",
    ),
    "geri qaytarılıb": ("reverted", "отменено", "geri alındı", "rückgängig gemacht"),
    "Cəmi": ("Total", "Итого", "Toplam", "Gesamt"),
    "Müəllifi göstərilməyən saatlar sizin cəminizə əlavə edilmir. Dərsi yazan şəxs və cari jurnal sahibi əsasında müəllim təxmin edilmir.": (
        "Hours without a recorded teacher are not added to your total. The teacher is not inferred from the recorder or the current journal owner.",
        "Часы без указанного преподавателя не включаются в ваш итог. Преподаватель не определяется по автору записи или текущему владельцу журнала.",
        "Öğretmeni belirtilmeyen saatler toplamınıza eklenmez. Kaydı yapan kişiden veya günlüğün mevcut sahibinden öğretmen tahmin edilmez.",
        "Stunden ohne erfasste Lehrkraft werden Ihrer Summe nicht hinzugefügt. Die Lehrkraft wird weder aus der eintragenden Person noch dem aktuellen Journalinhaber abgeleitet.",
    ),
    "Bu seçim üzrə jurnal saatı qeydə alınmayıb.": (
        "No journal hours recorded for this selection.",
        "По этому выбору часы в журнале не записаны.",
        "Bu seçim için günlük saati kaydedilmemiş.",
        "Für diese Auswahl sind keine Journalstunden erfasst.",
    ),
}


def fill(language):
    path = BASE / "locale" / language / "LC_MESSAGES" / "django.po"
    catalog = polib.pofile(path)
    additions = []
    for message, translations in ENTRIES.items():
        if catalog.find(message, msgctxt=CONTEXT) is None:
            translation = message if language == "az" else translations[LANGUAGES.index(language)]
            quote = lambda value: json.dumps(value, ensure_ascii=False)  # noqa: E731
            additions.append(f"msgctxt {quote(CONTEXT)}\nmsgid {quote(message)}\nmsgstr {quote(translation)}\n")
    if additions:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + "\n".join(additions))
    polib.pofile(path).save_as_mofile(str(path.with_suffix(".mo")))
    print(f"{language}: +{len(additions)}")


if __name__ == "__main__":
    for code in ("az", *LANGUAGES):
        fill(code)
