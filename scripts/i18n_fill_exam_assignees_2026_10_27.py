#!/usr/bin/env python3
"""EMSArena i18n — «Tapşırıq təyin olunmuşlar» səhifəsi (sahib 2026-10-27).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CTX = "exams.assignees"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    CTX: {
        "%(n)s cəhd": t("%(n)s attempts", "Попыток: %(n)s", "%(n)s deneme", "%(n)s Versuche"),
        "%(n)s davam edir": t("%(n)s in progress", "в процессе: %(n)s", "%(n)s devam ediyor", "%(n)s laufen"),
        "Ad (A → Z)": t("Name (A → Z)", "Имя (А → Я)", "İsim (A → Z)", "Name (A → Z)"),
        "Ad (Z → A)": t("Name (Z → A)", "Имя (Я → А)", "İsim (Z → A)", "Name (Z → A)"),
        "Ad Soyad (ata adı)": t("Full name (patronymic)", "ФИО (отчество)", "Ad Soyad (baba adı)", "Name (Vatersname)"),
        "Ad, ata adı, istifadəçi adı və ya tələbə kodu": t(
            "Name, patronymic, username or student code",
            "Имя, отчество, логин или код студента",
            "Ad, baba adı, kullanıcı adı veya öğrenci kodu",
            "Name, Vatersname, Benutzername oder Matrikelnummer",
        ),
        "Ad, soyad və ya istifadəçi adı…": t(
            "Name, surname or username…",
            "Имя, фамилия или логин…",
            "Ad, soyad veya kullanıcı adı…",
            "Vorname, Nachname oder Benutzername…",
        ),
        "Axtarış": t("Search", "Поиск", "Arama", "Suche"),
        "Bağla": t("Close", "Закрыть", "Kapat", "Schließen"),
        "Başlamayıb": t("Not started", "Не начинал", "Başlamadı", "Nicht begonnen"),
        "Bir dəfəyə ən çox %(max)d tələbə əlavə etmək olar.": t(
            "You can add at most %(max)d students at once.",
            "За один раз можно добавить не более %(max)d студентов.",
            "Bir seferde en fazla %(max)d öğrenci eklenebilir.",
            "Es können höchstens %(max)d Studierende auf einmal hinzugefügt werden.",
        ),
        "Bitib": t("Finished", "Завершено", "Bitti", "Beendet"),
        "Bitirib": t("Finished", "Завершили", "Bitirdi", "Abgeschlossen"),
        "Bu imtahana hələ heç kim təyin olunmayıb": t(
            "Nobody is assigned to this exam yet",
            "На этот экзамен пока никто не назначен",
            "Bu sınava henüz kimse atanmadı",
            "Dieser Prüfung ist noch niemand zugewiesen",
        ),
        "Bu tələbə imtahana fərdi təyin olunmayıb.": t(
            "This student is not individually assigned to the exam.",
            "Этот студент не назначен на экзамен индивидуально.",
            "Bu öğrenci sınava bireysel atanmamış.",
            "Diese Person ist der Prüfung nicht einzeln zugewiesen.",
        ),
        "Bu tələbə istisna siyahısında deyil.": t(
            "This student is not on the exclusion list.",
            "Этого студента нет в списке исключённых.",
            "Bu öğrenci hariç tutulanlar listesinde değil.",
            "Diese Person steht nicht auf der Ausschlussliste.",
        ),
        "Bu tələbənin fərdi icazəsi çıxarılsın? Qrupla təyin olunubsa imtahanı yenə görəcək.": t(
            "Remove this student's individual access? If assigned via a group, they will still see the exam.",
            "Убрать индивидуальный доступ студента? Если он назначен через группу, экзамен останется доступен.",
            "Bu öğrencinin bireysel izni kaldırılsın mı? Grupla atanmışsa sınavı yine görecek.",
            "Einzelzugang entfernen? Bei Zuweisung über eine Gruppe bleibt die Prüfung sichtbar.",
        ),
        "Bütün mənbələr": t("All sources", "Все источники", "Tüm kaynaklar", "Alle Quellen"),
        "Bütün qruplar": t("All groups", "Все группы", "Tüm gruplar", "Alle Gruppen"),
        "Bütün statuslar": t("All statuses", "Все статусы", "Tüm durumlar", "Alle Status"),
        "Bərpa et": t("Restore", "Восстановить", "Geri al", "Wiederherstellen"),
        "Cəhd statusu": t("Attempt status", "Статус попытки", "Deneme durumu", "Versuchsstatus"),
        "Davam edir": t("In progress", "В процессе", "Devam ediyor", "Läuft"),
        "Dəyişiklik imtahan redaktəsi ilə eyni yoxlamalardan keçir: fənnin jurnalında olmayan qrup üçün səbəb, "
        "final/midterm üçün PIN avtomatik verilir.": t(
            "Changes go through the same checks as editing the exam: a group outside the subject journal needs a "
            "reason, final/midterm PINs are issued automatically.",
            "Изменения проходят те же проверки, что и редактирование экзамена: для группы вне журнала предмета "
            "нужна причина, PIN для финала/мидтерма выдаётся автоматически.",
            "Değişiklik sınav düzenlemesiyle aynı kontrollerden geçer: dersin defterinde olmayan grup için neden "
            "gerekir, final/ara sınav PIN'i otomatik verilir.",
            "Änderungen durchlaufen dieselben Prüfungen wie das Bearbeiten der Prüfung: Für eine Gruppe außerhalb "
            "des Fachjournals ist eine Begründung nötig, Final-/Midterm-PINs werden automatisch vergeben.",
        ),
        "Filtrlər": t("Filters", "Фильтры", "Filtreler", "Filter"),
        "Filtrləri sıfırla": t("Reset filters", "Сбросить фильтры", "Filtreleri sıfırla", "Filter zurücksetzen"),
        "Fərdi": t("Individual", "Индивидуально", "Bireysel", "Einzeln"),
        "Fərdi icazə çıxarıldı.": t(
            "Individual access removed.",
            "Индивидуальный доступ удалён.",
            "Bireysel izin kaldırıldı.",
            "Einzelzugang entfernt.",
        ),
        "Hamısı": t("All", "Все", "Tümü", "Alle"),
        "Kursla": t("Via course", "Через курс", "Kurs üzerinden", "Über Kurs"),
        "Ləğv et": t("Cancel", "Отмена", "İptal", "Abbrechen"),
        "Mənbə": t("Source", "Источник", "Kaynak", "Quelle"),
        "Naməlum əməliyyat.": t("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem.", "Unbekannte Aktion."),
        "Qrup": t("Group", "Группа", "Grup", "Gruppe"),
        "Qrup axtar…": t("Search group…", "Найти группу…", "Grup ara…", "Gruppe suchen…"),
        "Qrup imtahana əlavə olundu.": t(
            "Group added to the exam.",
            "Группа добавлена на экзамен.",
            "Grup sınava eklendi.",
            "Gruppe zur Prüfung hinzugefügt.",
        ),
        "Qrup imtahandan çıxarıldı.": t(
            "Group removed from the exam.",
            "Группа удалена с экзамена.",
            "Grup sınavdan çıkarıldı.",
            "Gruppe aus der Prüfung entfernt.",
        ),
        "Qrup imtahandan çıxarılsın? Qrupun tələbələri (fərdi icazəsi olmayanlar) imtahanı görməyəcək.": t(
            "Remove the group from the exam? Its students (without individual access) will no longer see the exam.",
            "Убрать группу с экзамена? Её студенты (без индивидуального доступа) не будут видеть экзамен.",
            "Grup sınavdan çıkarılsın mı? Grubun öğrencileri (bireysel izni olmayanlar) sınavı görmeyecek.",
            "Gruppe aus der Prüfung entfernen? Ihre Studierenden (ohne Einzelzugang) sehen die Prüfung nicht mehr.",
        ),
        "Qrup tapılmadı və ya onu çıxarmaq icazəniz yoxdur.": t(
            "Group not found or you may not remove it.",
            "Группа не найдена или у вас нет права её убрать.",
            "Grup bulunamadı veya onu çıkarma izniniz yok.",
            "Gruppe nicht gefunden oder Sie dürfen sie nicht entfernen.",
        ),
        "Qrup əlavə et": t("Add group", "Добавить группу", "Grup ekle", "Gruppe hinzufügen"),
        "Qrupla": t("Via group", "Через группу", "Grupla", "Über Gruppe"),
        "Qrupla / fərdi": t(
            "Via group / individual", "Группа / индивидуально", "Grupla / bireysel", "Gruppe / einzeln"
        ),
        "Qruplar, tələbələr, PIN və cəhd statusu": t(
            "Groups, students, PIN and attempt status",
            "Группы, студенты, PIN и статус попыток",
            "Gruplar, öğrenciler, PIN ve deneme durumu",
            "Gruppen, Studierende, PIN und Versuchsstatus",
        ),
        "Qrupsuz": t("No group", "Без группы", "Grupsuz", "Ohne Gruppe"),
        "Qrupu əlavə et": t("Add the group", "Добавить группу", "Grubu ekle", "Gruppe hinzufügen"),
        "Reyestr qrupu təyin olunmayıb.": t(
            "No registry group is assigned.",
            "Группа из реестра не назначена.",
            "Kayıt grubu atanmadı.",
            "Keine Registergruppe zugewiesen.",
        ),
        "Seçilmiş qruplar artıq bu imtahana təyin olunub.": t(
            "The selected groups are already assigned to this exam.",
            "Выбранные группы уже назначены на этот экзамен.",
            "Seçilen gruplar zaten bu sınava atanmış.",
            "Die gewählten Gruppen sind dieser Prüfung bereits zugewiesen.",
        ),
        "Süzgəcə uyğun tələbə yoxdur": t(
            "No students match the filters",
            "Нет студентов по фильтру",
            "Filtreye uyan öğrenci yok",
            "Keine Studierenden entsprechen den Filtern",
        ),
        "Sıralama": t("Sort", "Сортировка", "Sırala", "Sortierung"),
        "Səbəb (ən azı 10 simvol)": t(
            "Reason (at least 10 characters)",
            "Причина (не менее 10 символов)",
            "Neden (en az 10 karakter)",
            "Begründung (mindestens 10 Zeichen)",
        ),
        "Səbəblə davam et": t(
            "Continue with reason", "Продолжить с причиной", "Nedenle devam et", "Mit Begründung fortfahren"
        ),
        "Tapşırıq təyin olunmuşlar": t(
            "Assigned students", "Назначенные студенты", "Atanan öğrenciler", "Zugewiesene Studierende"
        ),
        "Tələbə axtar": t("Search student", "Найти студента", "Öğrenci ara", "Studierende suchen"),
        "Tələbə bu imtahandan istisna edilsin? İmtahanı görməyəcək və başlaya bilməyəcək.": t(
            "Exclude the student from this exam? They will not see or start it.",
            "Исключить студента из экзамена? Он не увидит и не сможет начать экзамен.",
            "Öğrenci bu sınavdan hariç tutulsun mu? Sınavı görmeyecek ve başlatamayacak.",
            "Person von dieser Prüfung ausschließen? Sie sieht die Prüfung nicht und kann sie nicht starten.",
        ),
        "Tələbə imtahana əlavə olundu.": t(
            "Student added to the exam.",
            "Студент добавлен на экзамен.",
            "Öğrenci sınava eklendi.",
            "Person zur Prüfung hinzugefügt.",
        ),
        "Tələbə imtahandan istisna edildi.": t(
            "Student excluded from the exam.",
            "Студент исключён из экзамена.",
            "Öğrenci sınavdan hariç tutuldu.",
            "Person von der Prüfung ausgeschlossen.",
        ),
        "Tələbə kodu": t("Student code", "Код студента", "Öğrenci kodu", "Matrikelnummer"),
        "Tələbə tapılmadı.": t(
            "Student not found.", "Студент не найден.", "Öğrenci bulunamadı.", "Person nicht gefunden."
        ),
        "Tələbə yenidən imtahana daxil edildi.": t(
            "Student included in the exam again.",
            "Студент снова допущен к экзамену.",
            "Öğrenci yeniden sınava dahil edildi.",
            "Person wieder zur Prüfung zugelassen.",
        ),
        "Tələbə yenidən imtahana daxil edilsin?": t(
            "Include the student in the exam again?",
            "Снова допустить студента к экзамену?",
            "Öğrenci yeniden sınava dahil edilsin mi?",
            "Person wieder zur Prüfung zulassen?",
        ),
        "Tələbə əlavə et": t("Add student", "Добавить студента", "Öğrenci ekle", "Person hinzufügen"),
        "Tələbələr": t("Students", "Студенты", "Öğrenciler", "Studierende"),
        "Tələbələrin qrupları": t(
            "Students' groups", "Группы студентов", "Öğrencilerin grupları", "Gruppen der Studierenden"
        ),
        "Tələbəni əlavə et": t("Add the student", "Добавить студента", "Öğrenciyi ekle", "Person hinzufügen"),
        "Təsdiq edirəm": t("I confirm", "Подтверждаю", "Onaylıyorum", "Ich bestätige"),
        "Təsdiq və səbəb tələb olunur": t(
            "Confirmation and reason required",
            "Требуются подтверждение и причина",
            "Onay ve neden gerekli",
            "Bestätigung und Begründung erforderlich",
        ),
        "Təyin olunmuş qruplar": t("Assigned groups", "Назначенные группы", "Atanan gruplar", "Zugewiesene Gruppen"),
        "Təyinat əlavə et": t("Add assignment", "Добавить назначение", "Atama ekle", "Zuweisung hinzufügen"),
        "Uyğun qrup yoxdur": t("No matching group", "Нет подходящей группы", "Uygun grup yok", "Keine passende Gruppe"),
        "Var": t("Yes", "Есть", "Mevcut", "Vorhanden"),
        "Xülasə": t("Summary", "Сводка", "Özet", "Übersicht"),
        "Yalnız baxış: təyinatı dəyişmək üçün imtahanı redaktə etmək icazəniz yoxdur.": t(
            "View only: you are not allowed to edit this exam's assignment.",
            "Только просмотр: у вас нет права редактировать назначение экзамена.",
            "Yalnızca görüntüleme: sınav atamasını değiştirme izniniz yok.",
            "Nur Ansicht: Sie dürfen die Zuweisung dieser Prüfung nicht bearbeiten.",
        ),
        "Yalnız qrupla təyin olunmuş tələbəni istisna etmək olar.": t(
            "Only students assigned via a group can be excluded.",
            "Исключить можно только студента, назначенного через группу.",
            "Yalnızca grupla atanmış öğrenci hariç tutulabilir.",
            "Nur über eine Gruppe zugewiesene Studierende können ausgeschlossen werden.",
        ),
        "Yoxdur": t("No", "Нет", "Yok", "Fehlt"),
        "Yuxarıdan qrup və ya tələbə əlavə edin (və ya imtahanı redaktə edin).": t(
            "Add a group or a student above (or edit the exam).",
            "Добавьте группу или студента выше (или отредактируйте экзамен).",
            "Yukarıdan grup veya öğrenci ekleyin (ya da sınavı düzenleyin).",
            "Fügen Sie oben eine Gruppe oder Person hinzu (oder bearbeiten Sie die Prüfung).",
        ),
        "və daha {n} nəfər": t("and {n} more", "и ещё {n}", "ve {n} kişi daha", "und {n} weitere"),
        "{n} / {total} tələbə fənnin cari semestr jurnalında yoxdur": t(
            "{n} / {total} students are not in the subject's current-semester journal",
            "{n} / {total} студентов нет в журнале предмета текущего семестра",
            "{n} / {total} öğrenci dersin bu dönem defterinde yok",
            "{n} / {total} Studierende stehen nicht im Journal des laufenden Semesters",
        ),
        "«%(name)s» qrupunu çıxar": t(
            "Remove group «%(name)s»",
            "Убрать группу «%(name)s»",
            "«%(name)s» grubunu çıkar",
            "Gruppe «%(name)s» entfernen",
        ),
        "Çıxar": t("Remove", "Убрать", "Çıkar", "Entfernen"),
        "İmtahan hamı üçün açıqdır — təşkilatın istənilən tələbəsi (istisna edilənlərdən başqa) onu görə bilər. "
        "Aşağıda yalnız ayrıca təyin olunanlar göstərilir.": t(
            "The exam is open to everyone — any student of the organization (except excluded ones) can see it. "
            "Only explicitly assigned students are listed below.",
            "Экзамен открыт для всех — его видит любой студент организации (кроме исключённых). "
            "Ниже показаны только явно назначенные.",
            "Sınav herkese açık — kurumun her öğrencisi (hariç tutulanlar dışında) görebilir. "
            "Aşağıda yalnızca ayrıca atananlar gösterilir.",
            "Die Prüfung ist für alle offen — alle Studierenden der Organisation (außer Ausgeschlossenen) sehen "
            "sie. Unten stehen nur ausdrücklich Zugewiesene.",
        ),
        "İmtahanı verə bilər": t("Can take the exam", "Могут сдавать", "Sınava girebilir", "Dürfen teilnehmen"),
        "İstisna edilib": t("Excluded", "Исключён", "Hariç tutuldu", "Ausgeschlossen"),
        "İstisna et": t("Exclude", "Исключить", "Hariç tut", "Ausschließen"),
        "Əməliyyat": t("Action", "Действие", "İşlem", "Aktion"),
        "Əməliyyat alınmadı. Yenidən cəhd edin.": t(
            "The action failed. Please try again.",
            "Не удалось выполнить действие. Попробуйте ещё раз.",
            "İşlem başarısız. Tekrar deneyin.",
            "Die Aktion ist fehlgeschlagen. Bitte erneut versuchen.",
        ),
        "Ən azı bir qrup seçin.": t(
            "Select at least one group.",
            "Выберите хотя бы одну группу.",
            "En az bir grup seçin.",
            "Wählen Sie mindestens eine Gruppe.",
        ),
        "Ən azı bir tələbə seçin.": t(
            "Select at least one student.",
            "Выберите хотя бы одного студента.",
            "En az bir öğrenci seçin.",
            "Wählen Sie mindestens eine Person.",
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
