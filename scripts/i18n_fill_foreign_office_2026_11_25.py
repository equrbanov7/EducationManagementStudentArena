#!/usr/bin/env python3
"""Əcnəbi tələbələrlə iş şöbəsi + qrup «Tarixçə» / «Məzun et» / «Qrup növü» (sahib 2026-11-25): yeni msgid-lər.

Yalnız kataloqda OLMAYAN sətirlər əlavə olunur (idempotent); mövcud tərcümələrə toxunulmur. Rol adları
(``Role.display_name``) DB mətnidir, kataloqa düşmür.
"""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return dict(zip(LANGS[1:], (en, ru, tr, de)))


def quote(text):
    return json.dumps(text, ensure_ascii=False)


HISTORY = {
    "Akademik məzuniyyət": t("Academic leave", "Академический отпуск", "Akademik izin", "Beurlaubung"),
    "Akademik məzuniyyət əmri": t(
        "Academic leave order", "Приказ об академическом отпуске", "Akademik izin kararı", "Beurlaubungsbescheid"
    ),
    "Bal sayı": t("Marks", "Кол-во оценок", "Not sayısı", "Anzahl Noten"),
    "Bu tələbənin jurnal qeydi yoxdur.": t(
        "This student has no gradebook records.",
        "У этого студента нет записей в журнале.",
        "Bu öğrencinin defter kaydı yok.",
        "Für diese Person gibt es keine Einträge im Klassenbuch.",
    ),
    "Bütün semestrlərin jurnal statistikası — dondurulmuş və köçürülmüş qeydiyyatlar da daxildir.": t(
        "Gradebook statistics for all semesters — frozen and transferred enrolments included.",
        "Статистика журнала за все семестры — включая замороженные и переведённые записи.",
        "Tüm dönemlerin defter istatistikleri — dondurulmuş ve aktarılmış kayıtlar dahil.",
        "Klassenbuch-Statistik aller Semester — einschließlich ruhender und übertragener Belegungen.",
    ),
    "Dondurulana qədər bal": t(
        "Marks before leave", "Оценки до заморозки", "Dondurmadan önceki notlar", "Noten vor der Beurlaubung"
    ),
    "Dondurulub": t("Frozen", "Заморожено", "Donduruldu", "Ruhend"),
    "Fənn": t("Subject", "Дисциплина", "Ders", "Fach"),
    "Hərəkət əmri yoxdur.": t(
        "No movement orders.", "Приказов о движении нет.", "Hareket kararı yok.", "Keine Statusbescheide."
    ),
    "Hərəkət əmrləri": t("Movement orders", "Приказы о движении", "Hareket kararları", "Statusbescheide"),
    "Jurnal qrupu": t("Gradebook group", "Группа журнала", "Defter grubu", "Klassenbuchgruppe"),
    "Məzun": t("Graduated", "Выпускник", "Mezun", "Absolvent"),
    "Orta bal": t("Average", "Средний балл", "Ortalama", "Durchschnitt"),
    "Oxuyur": t("Studying", "Обучается", "Okuyor", "Aktiv"),
    "Qayıb": t("Absent", "Пропуск", "Devamsız", "Abwesend"),
    "Qayıb saatı": t("Absence hours", "Часы пропусков", "Devamsızlık saati", "Fehlstunden"),
    "Qeydiyyatlı": t("Enrolled", "Зачислен", "Kayıtlı", "Eingeschrieben"),
    "Qrup tapılmadı.": t("Group not found.", "Группа не найдена.", "Grup bulunamadı.", "Gruppe nicht gefunden."),
    "Siyahı çox uzundur — ən yeni qeydiyyatlar göstərilir.": t(
        "The list is too long — the most recent enrolments are shown.",
        "Список слишком длинный — показаны последние записи.",
        "Liste çok uzun — en yeni kayıtlar gösteriliyor.",
        "Die Liste ist zu lang — die neuesten Belegungen werden angezeigt.",
    ),
    "Son dərs": t("Last lesson", "Последнее занятие", "Son ders", "Letzte Stunde"),
    "Struktur əhatəniz yoxdur.": t(
        "You have no structural scope.",
        "У вас нет структурной зоны.",
        "Yapısal kapsamınız yok.",
        "Kein Zuständigkeitsbereich.",
    ),
    "Tamamlanıb": t("Completed", "Завершено", "Tamamlandı", "Abgeschlossen"),
    "Tarixçə yüklənir…": t("Loading history…", "Загрузка истории…", "Geçmiş yükleniyor…", "Verlauf wird geladen…"),
    "Tarixçə yüklənmədi — yenidən cəhd edin.": t(
        "History could not be loaded — try again.",
        "История не загрузилась — попробуйте снова.",
        "Geçmiş yüklenemedi — tekrar deneyin.",
        "Verlauf konnte nicht geladen werden — bitte erneut versuchen.",
    ),
    "Tələbə bu qrupda tapılmadı.": t(
        "Student not found in this group.",
        "Студент не найден в этой группе.",
        "Öğrenci bu grupta bulunamadı.",
        "Person in dieser Gruppe nicht gefunden.",
    ),
    "Tələbənin tarixçəsi": t("Student history", "История студента", "Öğrenci geçmişi", "Verlauf"),
    "Tələbənin tarixçəsinə baxmaq səlahiyyətiniz yoxdur.": t(
        "You are not allowed to view the student's history.",
        "У вас нет права просматривать историю студента.",
        "Öğrenci geçmişini görme yetkiniz yok.",
        "Sie dürfen den Verlauf nicht einsehen.",
    ),
    "Vəziyyət": t("Status", "Статус", "Durum", "Status"),
    "Xaric edilib": t("Expelled", "Отчислен", "İlişiği kesildi", "Exmatrikuliert"),
    "bitmə tarixi": t("ends", "дата окончания", "bitiş tarihi", "endet am"),
    "Çıxarılıb / köçürülüb": t(
        "Removed / transferred", "Исключён / переведён", "Çıkarıldı / aktarıldı", "Entfernt / übertragen"
    ),
    "Üzrlü": t("Excused", "Уважительная", "Mazeretli", "Entschuldigt"),
    "İştirak": t("Present", "Присутствие", "Katılım", "Anwesend"),
    "Əmr №": t("Order no.", "Приказ №", "Karar no.", "Bescheid Nr."),
}

GROUPS = {
    "%d tələbə məzun edildi.": t(
        "%d students graduated.",
        "Выпускниками стали %d студентов.",
        "%d öğrenci mezun edildi.",
        "%d Personen graduiert.",
    ),
    "Adi qrup": t("Regular group", "Обычная группа", "Normal grup", "Reguläre Gruppe"),
    "Başqa bölmənin tələbəsini yalnız «əlavə olaraq» qoşmaq olar — öz qrupu dəyişmir.": t(
        "A student of another unit can only be added «as extra» — their own group stays.",
        "Студента другого подразделения можно добавить только «дополнительно» — его группа не меняется.",
        "Başka birimin öğrencisi yalnızca «ek olarak» eklenebilir — kendi grubu değişmez.",
        "Personen anderer Bereiche nur «zusätzlich» hinzufügen — die eigene Gruppe bleibt.",
    ),
    "Məzun et": t("Graduate", "Выпустить", "Mezun et", "Graduieren"),
    "Qrup məzun edilmədi — heç bir dəyişiklik yazılmadı: %s": t(
        "The group was not graduated — nothing was saved: %s",
        "Группа не выпущена — изменения не сохранены: %s",
        "Grup mezun edilmedi — hiçbir değişiklik kaydedilmedi: %s",
        "Die Gruppe wurde nicht graduiert — nichts gespeichert: %s",
    ),
    "Qrup növü": t("Group type", "Тип группы", "Grup türü", "Gruppentyp"),
    "Qrupda məzun ediləcək qeydiyyatlı tələbə yoxdur.": t(
        "The group has no enrolled students to graduate.",
        "В группе нет зачисленных студентов для выпуска.",
        "Grupta mezun edilecek kayıtlı öğrenci yok.",
        "Die Gruppe hat keine eingeschriebenen Personen zum Graduieren.",
    ),
    "Qrupu məzun et": t("Graduate the group", "Выпустить группу", "Grubu mezun et", "Gruppe graduieren"),
    "Qrupun BÜTÜN qeydiyyatlı tələbələri bir əmrlə məzun edilir (əlavə üzvlər öz qrupu ilə). Bir tələbə rədd olunsa "
    "heç kim məzun edilmir. Əmr nömrəsi və tarixi məcburidir.": t(
        "ALL enrolled students of the group graduate with one order (extra members with their own group). If one "
        "student is rejected, nobody graduates. Order number and date are required.",
        "ВСЕ зачисленные студенты группы выпускаются одним приказом (дополнительные — со своей группой). Если один "
        "студент отклонён, никто не выпускается. Номер и дата приказа обязательны.",
        "Grubun TÜM kayıtlı öğrencileri tek kararla mezun edilir (ek üyeler kendi gruplarıyla). Bir öğrenci "
        "reddedilirse kimse mezun edilmez. Karar numarası ve tarihi zorunludur.",
        "ALLE eingeschriebenen Personen der Gruppe werden mit einem Bescheid graduiert (Zusatzmitglieder mit ihrer "
        "Gruppe). Wird eine Person abgelehnt, graduiert niemand. Bescheidnummer und -datum sind Pflicht.",
    ),
    "Status «məzun» olur: tələbə qrupun aktiv siyahısından çıxır, akademik qeyd və qiymət tarixçəsi qalır. Səhv məzun "
    "etmə «Bərpa et» ilə geri qaytarılır. Əmr nömrəsi və tarixi məcburidir.": t(
        "Status becomes «graduated»: the student leaves the active list, the academic record and grade history stay. "
        "A mistaken graduation is undone with «Reinstate». Order number and date are required.",
        "Статус «выпускник»: студент выходит из активного списка, академическая запись и история оценок сохраняются. "
        "Ошибочный выпуск отменяется через «Восстановить». Номер и дата приказа обязательны.",
        "Durum «mezun» olur: öğrenci aktif listeden çıkar, akademik kayıt ve not geçmişi kalır. Hatalı mezuniyet "
        "«Geri al» ile geri alınır. Karar numarası ve tarihi zorunludur.",
        "Status wird «graduiert»: die Person verlässt die aktive Liste, Akte und Notenverlauf bleiben. Eine "
        "irrtümliche Graduierung wird mit «Wiederherstellen» rückgängig gemacht. Bescheidnummer und -datum sind Pflicht.",
    ),
    "Tarixçə": t("History", "История", "Geçmiş", "Verlauf"),
    "Tələbəni məzun et": t("Graduate the student", "Выпустить студента", "Öğrenciyi mezun et", "Person graduieren"),
    "Tələbəni məzun etmək səlahiyyətiniz yoxdur.": t(
        "You are not allowed to graduate students.",
        "У вас нет права выпускать студентов.",
        "Öğrenci mezun etme yetkiniz yok.",
        "Sie dürfen keine Personen graduieren.",
    ),
    "Əcnəbi tələbələr qrupu": t(
        "International students group",
        "Группа иностранных студентов",
        "Yabancı öğrenci grubu",
        "Gruppe internationaler Studierender",
    ),
    "Əcnəbi tələbələr qrupunu Əcnəbi tələbələrlə iş şöbəsi idarə edir; müəllim belə qruplarda eyni saatda bir neçə "
    "qrupla dərs keçə bilir.": t(
        "International student groups are managed by the International Students Office; a teacher may teach several "
        "such groups at the same time.",
        "Группы иностранных студентов ведёт отдел по работе с иностранными студентами; преподаватель может вести "
        "несколько таких групп в одно время.",
        "Yabancı öğrenci gruplarını Yabancı Öğrenci Ofisi yönetir; öğretmen bu gruplarda aynı saatte birden fazla "
        "grupla ders yapabilir.",
        "Gruppen internationaler Studierender verwaltet das International Office; Lehrende können mehrere solche "
        "Gruppen gleichzeitig unterrichten.",
    ),
}

ENTRIES = {
    "django": {
        "accounts.group_history": HISTORY,
        "accounts.groups": GROUPS,
        "registrar.admission_channel": {
            "Müqavilə ilə qəbul": t(
                "Admission by contract", "Приём по договору", "Sözleşmeli kabul", "Zulassung per Vertrag"
            ),
        },
        "profile.rim": {
            "Azərbaycan Respublikası": t(
                "Republic of Azerbaijan",
                "Азербайджанская Республика",
                "Azerbaycan Cumhuriyeti",
                "Republik Aserbaidschan",
            ),
            "Əcnəbi vətəndaş (əcnəbi tələbə)": t(
                "Foreign citizen (international student)",
                "Иностранный гражданин (иностранный студент)",
                "Yabancı uyruklu (yabancı öğrenci)",
                "Ausländische Staatsangehörigkeit (internationale Studierende)",
            ),
            "Vətəndaşlığı olmayan şəxs": t(
                "Stateless person", "Лицо без гражданства", "Vatansız kişi", "Staatenlose Person"
            ),
            "Qrup tapılmadı və ya icazə əhatənizdən kənardadır.": t(
                "Group not found or outside your scope.",
                "Группа не найдена или вне вашей зоны.",
                "Grup bulunamadı veya yetki kapsamınız dışında.",
                "Gruppe nicht gefunden oder außerhalb Ihres Bereichs.",
            ),
        },
        "student_intake": {
            "Bu qrupa tələbə əlavə etmək icazəniz yoxdur — yalnız öz qruplarınızı seçin.": t(
                "You may not add students to this group — choose one of your own groups.",
                "Вы не можете добавлять студентов в эту группу — выберите свою группу.",
                "Bu gruba öğrenci ekleme yetkiniz yok — yalnızca kendi gruplarınızı seçin.",
                "Sie dürfen dieser Gruppe niemanden hinzufügen — wählen Sie eine eigene Gruppe.",
            ),
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
                    lines = ["#, python-format"] if ("%s" in msgid or "%d" in msgid) else []
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
