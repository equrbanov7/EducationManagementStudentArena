#!/usr/bin/env python3
"""EMSArena i18n — «İntensiv kurs» (qrupsuz qısa kurs, 1–2 tələbə), 2026-10-25.

msgid AZ cümlədir → az msgstr = msgid. ``django`` domeni kontekstlə, ``djangojs`` — kontekstsiz (JS kataloqu).
İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

R = "registrar.intensive"
W = "accounts.workload_intensive"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


INTENSIVE = t("Intensive", "Интенсив", "Yoğun", "Intensiv")
INTENSIVE_COURSE = t("Intensive course", "Интенсивный курс", "Yoğun ders", "Intensivkurs")

ENTRIES = {
    "registrar.course_format": {
        "Adi": t("Regular", "Обычный", "Normal", "Regulär"),
        "İntensiv": INTENSIVE,
    },
    "workload": {"İntensiv kurs": INTENSIVE_COURSE},
    R: {
        "İntensiv": INTENSIVE,
        "Kurs tamamlandı": t("Course completed", "Курс завершён", "Ders tamamlandı", "Kurs abgeschlossen"),
        "Başlama və bitmə tarixi seçilməlidir.": t(
            "Select the start and end dates.",
            "Выберите даты начала и окончания.",
            "Başlangıç ve bitiş tarihlerini seçin.",
            "Wählen Sie Beginn- und Enddatum.",
        ),
        "Bitmə tarixi başlama tarixindən əvvəl ola bilməz.": t(
            "The end date cannot be before the start date.",
            "Дата окончания не может быть раньше даты начала.",
            "Bitiş tarihi başlangıç tarihinden önce olamaz.",
            "Das Enddatum darf nicht vor dem Beginndatum liegen.",
        ),
        "Bu açılış intensiv kurs deyil.": t(
            "This offering is not an intensive course.",
            "Это не интенсивный курс.",
            "Bu açılış yoğun ders değil.",
            "Dieses Angebot ist kein Intensivkurs.",
        ),
        "Bu semestrdə «%(group)s» jurnalında aktivdir — «Adi jurnaldan intensivə köçür» seçilməlidir.": t(
            "Active in the “%(group)s” journal this semester — tick “move from the regular journal to the intensive "
            "course”.",
            "В этом семестре активен в журнале «%(group)s» — отметьте «перевести из обычного журнала в интенсив».",
            "Bu dönem «%(group)s» defterinde aktif — «normal defterden yoğun derse taşı» seçilmelidir.",
            "In diesem Semester im Journal „%(group)s“ aktiv — „aus dem regulären Journal in den Intensivkurs "
            "verschieben“ auswählen.",
        ),
        "Fənn tapılmadı.": t(
            "Subject not found.", "Дисциплина не найдена.", "Ders bulunamadı.", "Fach nicht gefunden."
        ),
        "Jurnalda dərs yazılıb — intensiv kursu ləğv etmək olmaz.": t(
            "Lessons are recorded in the journal — the intensive course cannot be cancelled.",
            "В журнале уже есть занятия — интенсивный курс нельзя отменить.",
            "Defterde ders kaydı var — yoğun ders iptal edilemez.",
            "Im Journal sind Stunden erfasst — der Intensivkurs kann nicht storniert werden.",
        ),
        "Kursun açılma səbəbini yazın (məs. yenidən tədris).": t(
            "Enter the reason for the course (e.g. re-teaching).",
            "Укажите причину открытия курса (напр. повторное обучение).",
            "Dersin açılış nedenini yazın (örn. yeniden öğretim).",
            "Geben Sie den Grund für den Kurs an (z. B. Wiederholungsunterricht).",
        ),
        "Kursun saatı %(lo)s–%(hi)s arasında olmalıdır.": t(
            "Course hours must be between %(lo)s and %(hi)s.",
            "Часы курса должны быть от %(lo)s до %(hi)s.",
            "Ders saati %(lo)s–%(hi)s arasında olmalıdır.",
            "Die Kursstunden müssen zwischen %(lo)s und %(hi)s liegen.",
        ),
        "Seçilmiş müəllimin bu təşkilatda bal yazmaq səlahiyyəti (müəllim rolu) yoxdur.": t(
            "The selected teacher cannot enter grades in this organisation (no teacher role).",
            "У выбранного преподавателя нет права выставлять оценки в этой организации (нет роли преподавателя).",
            "Seçilen öğretmenin bu kurumda not girme yetkisi (öğretmen rolü) yok.",
            "Die gewählte Lehrkraft darf in dieser Organisation keine Noten eintragen (keine Lehrkraftrolle).",
        ),
        "Tarixlər semestrin daxilində olmalıdır (%(lo)s – %(hi)s).": t(
            "Dates must fall within the semester (%(lo)s – %(hi)s).",
            "Даты должны быть в пределах семестра (%(lo)s – %(hi)s).",
            "Tarihler dönem içinde olmalıdır (%(lo)s – %(hi)s).",
            "Die Daten müssen im Semester liegen (%(lo)s – %(hi)s).",
        ),
        "Tələbə bu fənn üzrə artıq başqa intensiv kursdadır.": t(
            "The student is already in another intensive course for this subject.",
            "Студент уже записан на другой интенсивный курс по этой дисциплине.",
            "Öğrenci bu derste zaten başka bir yoğun derste.",
            "Die studierende Person ist für dieses Fach bereits in einem anderen Intensivkurs.",
        ),
        "Tələbə bu fənni artıq keçib.": t(
            "The student has already passed this subject.",
            "Студент уже сдал эту дисциплину.",
            "Öğrenci bu dersi zaten geçti.",
            "Die studierende Person hat dieses Fach bereits bestanden.",
        ),
        "Tələbə bu semestrdə bu fəndən azad edilib.": t(
            "The student is exempt from this subject this semester.",
            "Студент освобождён от этой дисциплины в этом семестре.",
            "Öğrenci bu dönem bu dersten muaf tutuldu.",
            "Die studierende Person ist in diesem Semester von diesem Fach befreit.",
        ),
        "Tələbənin aktiv akademik qeydi (qrupu) yoxdur.": t(
            "The student has no active academic record (group).",
            "У студента нет активной академической записи (группы).",
            "Öğrencinin aktif akademik kaydı (grubu) yok.",
            "Die studierende Person hat keinen aktiven Studiendatensatz (Gruppe).",
        ),
        "Tələbənin bu fənn üzrə birdən çox aktiv jurnalı var — əvvəlcə dekanlıq həll etməlidir.": t(
            "The student has more than one active journal for this subject — the dean's office must resolve it first.",
            "У студента несколько активных журналов по этой дисциплине — сначала это должен решить деканат.",
            "Öğrencinin bu derste birden fazla aktif defteri var — önce dekanlık çözmelidir.",
            "Die studierende Person hat mehrere aktive Journale für dieses Fach — zuerst muss das Dekanat das klären.",
        ),
        "İntensiv kurs ləğv edildi": t(
            "Intensive course cancelled",
            "Интенсивный курс отменён",
            "Yoğun ders iptal edildi",
            "Intensivkurs storniert",
        ),
        "İntensiv kurs yalnız cari aktiv semestrdə açılır.": t(
            "An intensive course can only be opened in the current active semester.",
            "Интенсивный курс открывается только в текущем активном семестре.",
            "Yoğun ders yalnızca mevcut aktif dönemde açılır.",
            "Ein Intensivkurs kann nur im aktuellen aktiven Semester eröffnet werden.",
        ),
        "İntensiv kurs: %(note)s": t(
            "Intensive course: %(note)s",
            "Интенсивный курс: %(note)s",
            "Yoğun ders: %(note)s",
            "Intensivkurs: %(note)s",
        ),
        "İntensiv kursa ən çox %(n)s tələbə yazılır.": t(
            "At most %(n)s students can join an intensive course.",
            "На интенсивный курс можно записать не более %(n)s студентов.",
            "Yoğun derse en fazla %(n)s öğrenci yazılabilir.",
            "Höchstens %(n)s Studierende können an einem Intensivkurs teilnehmen.",
        ),
        "İntensiv kursun dərsi %(lo)s – %(hi)s aralığında olmalıdır.": t(
            "Intensive course lessons must be between %(lo)s and %(hi)s.",
            "Занятия интенсивного курса должны быть в период %(lo)s – %(hi)s.",
            "Yoğun dersin dersleri %(lo)s – %(hi)s aralığında olmalıdır.",
            "Stunden des Intensivkurses müssen zwischen %(lo)s und %(hi)s liegen.",
        ),
        "Ən azı bir tələbə seçin.": t(
            "Select at least one student.",
            "Выберите хотя бы одного студента.",
            "En az bir öğrenci seçin.",
            "Wählen Sie mindestens eine studierende Person.",
        ),
    },
    W: {
        "İntensiv kurs": INTENSIVE_COURSE,
        "İntensiv kursu aç": t(
            "Open intensive course", "Открыть интенсивный курс", "Yoğun dersi aç", "Intensivkurs eröffnen"
        ),
        "İmtina": t("Cancel", "Отмена", "Vazgeç", "Abbrechen"),
        "Fənn": t("Subject", "Дисциплина", "Ders", "Fach"),
        "Müəllim": t("Teacher", "Преподаватель", "Öğretmen", "Lehrkraft"),
        "Tələbələr": t("Students", "Студенты", "Öğrenciler", "Studierende"),
        "Mühazirə saatı": t("Lecture hours", "Часы лекций", "Teorik ders saati", "Vorlesungsstunden"),
        "Seminar saatı": t("Seminar hours", "Часы семинаров", "Uygulama saati", "Seminarstunden"),
        "Başlama tarixi": t("Start date", "Дата начала", "Başlangıç tarihi", "Beginndatum"),
        "Bitmə tarixi": t("End date", "Дата окончания", "Bitiş tarihi", "Enddatum"),
        "Səbəb": t("Reason", "Причина", "Neden", "Grund"),
        "Fənn adı və ya kodu…": t(
            "Subject name or code…", "Название или код дисциплины…", "Ders adı veya kodu…", "Fachname oder -code…"
        ),
        "Müəllimin adı…": t("Teacher's name…", "Имя преподавателя…", "Öğretmenin adı…", "Name der Lehrkraft…"),
        "Ad, soyad və ya qrup…": t(
            "First name, last name or group…",
            "Имя, фамилия или группа…",
            "Ad, soyad veya grup…",
            "Vorname, Nachname oder Gruppe…",
        ),
        "məs. yenidən tədris, akademik fərq": t(
            "e.g. re-teaching, academic difference",
            "напр. повторное обучение, академическая разница",
            "örn. yeniden öğretim, akademik fark",
            "z. B. Wiederholungsunterricht, akademische Differenz",
        ),
        "Yazılacaq": t("Will be enrolled", "Будет записан", "Kaydedilecek", "Wird eingeschrieben"),
        "təkrar (əvvəl kəsilib)": t(
            "retake (failed before)",
            "повторно (ранее не сдал)",
            "tekrar (daha önce kaldı)",
            "Wiederholung (zuvor nicht bestanden)",
        ),
        "Əməl alınmadı — yenidən cəhd edin.": t(
            "The action failed — please try again.",
            "Действие не выполнено — попробуйте снова.",
            "İşlem başarısız — tekrar deneyin.",
            "Aktion fehlgeschlagen — bitte erneut versuchen.",
        ),
        "İntensiv kurs açıldı: jurnal yaradıldı, tələbələr yazıldı, müəllimin yükünə əlavə olundu.": t(
            "Intensive course opened: the journal was created, students were enrolled and the hours were added to "
            "the teacher's workload.",
            "Интенсивный курс открыт: журнал создан, студенты записаны, часы добавлены в нагрузку преподавателя.",
            "Yoğun ders açıldı: defter oluşturuldu, öğrenciler kaydedildi, saatler öğretmenin yüküne eklendi.",
            "Intensivkurs eröffnet: Journal angelegt, Studierende eingeschrieben, Stunden dem Deputat der Lehrkraft "
            "hinzugefügt.",
        ),
        "Az saatlı, 1–2 tələbə üçün qısa kurs. Saat müəllimin yükünə «İntensiv» kimi düşür, jurnal açılır və "
        "tələbələr yazılır. Müəllim dərsləri tarix aralığında istədiyi günlərə yazır (bir gündə bir neçə dərs də "
        "olar); cədvəl tələb olunmur.": t(
            "A short course with few hours for 1–2 students. The hours go to the teacher's workload as "
            "“Intensive”, a journal is opened and the students are enrolled. The teacher records lessons on any "
            "days within the date range (several lessons a day are allowed); no timetable is required.",
            "Короткий курс с малым числом часов для 1–2 студентов. Часы попадают в нагрузку преподавателя как "
            "«Интенсив», открывается журнал и записываются студенты. Преподаватель вносит занятия в любые дни "
            "периода (можно несколько занятий в день); расписание не требуется.",
            "1–2 öğrenci için az saatli kısa ders. Saatler öğretmenin yüküne «Yoğun» olarak düşer, defter açılır ve "
            "öğrenciler kaydedilir. Öğretmen dersleri tarih aralığında istediği günlere yazar (bir günde birkaç ders "
            "olabilir); ders programı gerekmez.",
            "Kurzer Kurs mit wenigen Stunden für 1–2 Studierende. Die Stunden gehen als „Intensiv“ in das Deputat "
            "der Lehrkraft ein, ein Journal wird eröffnet und die Studierenden werden eingeschrieben. Die Lehrkraft "
            "erfasst Stunden an beliebigen Tagen im Zeitraum (mehrere Stunden pro Tag möglich); kein Stundenplan "
            "erforderlich.",
        ),
        "Tələbə bu fənni bu semestr adi jurnalda keçirsə — oradan intensivə köçür (ikiqat qiymət olmasın; köhnə bal "
        "mənbədə saxlanılır, qayıb saatı köçür)": t(
            "If the student takes this subject in a regular journal this semester — move them to the intensive "
            "course (no double grade; old marks stay in the source, absence hours are carried over)",
            "Если студент проходит эту дисциплину в обычном журнале в этом семестре — перевести в интенсив (без "
            "двойной оценки; старые баллы остаются в источнике, часы пропусков переносятся)",
            "Öğrenci bu dersi bu dönem normal defterde alıyorsa — yoğun derse taşı (çift not olmasın; eski notlar "
            "kaynakta kalır, devamsızlık saatleri taşınır)",
            "Belegt die studierende Person dieses Fach in diesem Semester in einem regulären Journal — in den "
            "Intensivkurs verschieben (keine Doppelnote; alte Noten bleiben in der Quelle, Fehlstunden werden "
            "übertragen)",
        ),
    },
}

#: JS kataloqu (msgctxt yoxdur) — ``workload_intensive.js`` / render / «Mənim dərs yüküm».
JS_ENTRIES = {
    "İntensiv": INTENSIVE,
    "Jurnal": t("Journal", "Журнал", "Defter", "Journal"),
    "Ləğv et": t("Cancel", "Отменить", "İptal et", "Stornieren"),
    "saat": t("hours", "ч", "saat", "Std."),
    "tələbə": t("students", "студ.", "öğrenci", "Studierende"),
    "Əvvəlcə kafedranı seçin.": t(
        "Select the department first.",
        "Сначала выберите кафедру.",
        "Önce bölümü seçin.",
        "Wählen Sie zuerst den Lehrstuhl.",
    ),
    "İntensiv kurs ləğv edilsin? (yalnız jurnalda dərs yoxdursa mümkündür)": t(
        "Cancel the intensive course? (only possible if no lessons are recorded)",
        "Отменить интенсивный курс? (возможно, только если в журнале нет занятий)",
        "Yoğun ders iptal edilsin mi? (yalnızca defterde ders yoksa mümkündür)",
        "Intensivkurs stornieren? (nur möglich, wenn keine Stunden erfasst sind)",
    ),
    "Əməliyyat alınmadı.": t(
        "The operation failed.", "Операция не выполнена.", "İşlem başarısız.", "Vorgang fehlgeschlagen."
    ),
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _write(path, blocks):
    if not blocks:
        return
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.rstrip("\n") + "\n\n" + "\n".join(blocks))


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    blocks = []
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
    _write(path, blocks)

    js_path = po_path(lang, "djangojs")
    js_existing = {entry.msgid for entry in polib.pofile(js_path) if not entry.obsolete and not entry.msgctxt}
    js_blocks = []
    for msgid, translations in JS_ENTRIES.items():
        if msgid in js_existing:
            continue
        msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
        js_blocks.append(f'msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
    _write(js_path, js_blocks)
    print(f"{lang}: +{len(blocks)} django, +{len(js_blocks)} djangojs")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
