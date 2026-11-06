#!/usr/bin/env python3
"""EMSArena i18n — kabinetin «Lab qrupları» bölməsi (sahib 2026-11-07: «sidebarda qruplar olan yerdə yerləşsin»).

Kontekstlər: ``accounts.lab_groups`` (``apps/accounts/views/lab_groups_section.py``,
``accounts/profile/sections/_lab_groups.html`` + ``lab_groups/_*.html``), ``registrar.lab_groups`` (jurnal seçimi
modulu ``apps/registrar/lab_groups_section.py``, jurnal başlığındakı keçid), ``profile.section`` (menyu adı).
⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir. Sonra `.mo`
faylları `msgfmt` ilə yığılır.

İstifadə:  python scripts/i18n_fill_lab_groups_section_2026_11_07.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def _t(az, en, ru, tr, de):
    return {"az": az, "en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "profile.section": {
        "Lab qrupları": _t("Lab qrupları", "Lab groups", "Лаб. группы", "Lab grupları", "Laborgruppen"),
    },
    "registrar.lab_groups": {
        "Bu jurnalın laboratoriya qruplarını idarə etmək səlahiyyətiniz yoxdur.": _t(
            "Bu jurnalın laboratoriya qruplarını idarə etmək səlahiyyətiniz yoxdur.",
            "You are not allowed to manage the lab groups of this journal.",
            "У вас нет права управлять лабораторными группами этого журнала.",
            "Bu defterin laboratuvar gruplarını yönetme yetkiniz yok.",
            "Sie dürfen die Laborgruppen dieses Journals nicht verwalten.",
        ),
        "Bölünməyib": _t("Bölünməyib", "Not split", "Не разделён", "Bölünmemiş", "Nicht aufgeteilt"),
        "Qruplara bölünüb": _t(
            "Qruplara bölünüb", "Split into groups", "Разделён на группы", "Gruplara bölünmüş", "In Gruppen aufgeteilt"
        ),
        "Qrupsuz tələbəsi var": _t(
            "Qrupsuz tələbəsi var",
            "Has students without a group",
            "Есть студенты без группы",
            "Grupsuz öğrencisi var",
            "Hat Studierende ohne Gruppe",
        ),
        "Laboratoriya qrupları kabinetin «Lab qrupları» bölməsində idarə olunur": _t(
            "Laboratoriya qrupları kabinetin «Lab qrupları» bölməsində idarə olunur",
            "Lab groups are managed in the “Lab groups” section of the cabinet",
            "Лабораторные группы управляются в разделе кабинета «Лаб. группы»",
            "Laboratuvar grupları kabinetin «Lab grupları» bölümünde yönetilir",
            "Laborgruppen werden im Bereich „Laborgruppen“ des Kabinetts verwaltet",
        ),
    },
    "accounts.lab_groups": {
        "%(n)s dərs bağlıdır": _t(
            "%(n)s dərs bağlıdır",
            "%(n)s lessons linked",
            "Привязано занятий: %(n)s",
            "%(n)s ders bağlı",
            "%(n)s Stunden zugeordnet",
        ),
        "%(n)s jurnal hələ bölünməyib": _t(
            "%(n)s jurnal hələ bölünməyib",
            "%(n)s journals not split yet",
            "Ещё не разделено журналов: %(n)s",
            "%(n)s defter henüz bölünmedi",
            "%(n)s Journale noch nicht aufgeteilt",
        ),
        "%(n)s jurnalda": _t(
            "%(n)s jurnalda", "in %(n)s journals", "в журналах: %(n)s", "%(n)s defterde", "in %(n)s Journalen"
        ),
        "%(n)s qrup": _t("%(n)s qrup", "%(n)s groups", "Групп: %(n)s", "%(n)s grup", "%(n)s Gruppen"),
        "%(n)s qrupsuz tələbə": _t(
            "%(n)s qrupsuz tələbə",
            "%(n)s students without a group",
            "Без группы: %(n)s",
            "%(n)s grupsuz öğrenci",
            "%(n)s Studierende ohne Gruppe",
        ),
        "Ad (istəyə bağlı) — boş qalsa Lab-N": _t(
            "Ad (istəyə bağlı) — boş qalsa Lab-N",
            "Name (optional) — Lab-N if left empty",
            "Название (необязательно) — если пусто, Lab-N",
            "Ad (isteğe bağlı) — boş kalırsa Lab-N",
            "Name (optional) — leer bedeutet Lab-N",
        ),
        "Adını dəyiş": _t("Adını dəyiş", "Rename", "Переименовать", "Adını değiştir", "Umbenennen"),
        "Aktiv tələbə": _t(
            "Aktiv tələbə", "Active students", "Активные студенты", "Aktif öğrenci", "Aktive Studierende"
        ),
        "Axtarış": _t("Axtarış", "Search", "Поиск", "Arama", "Suche"),
        "Bu bölmə jurnalın müəllimi, kafedra müdiri və RİM rəhbəri üçündür.": _t(
            "Bu bölmə jurnalın müəllimi, kafedra müdiri və RİM rəhbəri üçündür.",
            "This section is for the journal's teacher, the head of department and the RIM head.",
            "Этот раздел предназначен для преподавателя журнала, заведующего кафедрой и руководителя RİM.",
            "Bu bölüm defterin öğretmeni, bölüm başkanı ve RİM yöneticisi içindir.",
            "Dieser Bereich ist für die Lehrkraft des Journals, die Lehrstuhlleitung und die RİM-Leitung.",
        ),
        "Bu jurnal hələ laboratoriya qruplarına bölünməyib. «Qrup yarat» ilə Lab-1, Lab-2 … yaradın, sonra tələbələri yerləşdirin.": _t(
            "Bu jurnal hələ laboratoriya qruplarına bölünməyib. «Qrup yarat» ilə Lab-1, Lab-2 … yaradın, sonra tələbələri yerləşdirin.",
            "This journal is not split into lab groups yet. Use “Create group” to add Lab-1, Lab-2 …, then place the students.",
            "Журнал ещё не разделён на лабораторные группы. Создайте Lab-1, Lab-2 … кнопкой «Создать группу», затем распределите студентов.",
            "Bu defter henüz laboratuvar gruplarına bölünmedi. «Grup oluştur» ile Lab-1, Lab-2 … oluşturun, sonra öğrencileri yerleştirin.",
            "Dieses Journal ist noch nicht in Laborgruppen aufgeteilt. Legen Sie mit „Gruppe anlegen“ Lab-1, Lab-2 … an und ordnen Sie dann die Studierenden zu.",
        ),
        "Bu semestrdə laboratoriya saatı olan jurnal yoxdur": _t(
            "Bu semestrdə laboratoriya saatı olan jurnal yoxdur",
            "No journals with lab hours in this semester",
            "В этом семестре нет журналов с лабораторными часами",
            "Bu dönemde laboratuvar saati olan defter yok",
            "In diesem Semester gibt es keine Journale mit Laborstunden",
        ),
        "Bölünməyib": _t("Bölünməyib", "Not split", "Не разделён", "Bölünmemiş", "Nicht aufgeteilt"),
        "Bütün tələbələr qrupa yerləşdirilib.": _t(
            "Bütün tələbələr qrupa yerləşdirilib.",
            "All students are placed in a group.",
            "Все студенты распределены по группам.",
            "Tüm öğrenciler bir gruba yerleştirildi.",
            "Alle Studierenden sind einer Gruppe zugeordnet.",
        ),
        "Fakültə": _t("Fakültə", "Faculty", "Факультет", "Fakülte", "Fakultät"),
        "Fənn, kod, qrup və ya müəllim": _t(
            "Fənn, kod, qrup və ya müəllim",
            "Subject, code, group or teacher",
            "Предмет, код, группа или преподаватель",
            "Ders, kod, grup veya öğretmen",
            "Fach, Code, Gruppe oder Lehrkraft",
        ),
        "Hamısı": _t("Hamısı", "All", "Все", "Tümü", "Alle"),
        "Hansı qrupa köçürülsün": _t(
            "Hansı qrupa köçürülsün",
            "Move to which group",
            "В какую группу перевести",
            "Hangi gruba taşınsın",
            "In welche Gruppe verschieben",
        ),
        "Hansı qrupa köçürüləcəyini seçin.": _t(
            "Hansı qrupa köçürüləcəyini seçin.",
            "Choose the group to move to.",
            "Выберите группу для перевода.",
            "Taşınacak grubu seçin.",
            "Wählen Sie die Zielgruppe.",
        ),
        "Hansı qrupa…": _t("Hansı qrupa…", "To which group…", "В какую группу…", "Hangi gruba…", "In welche Gruppe…"),
        "Hələ dərs bağlanmayıb": _t(
            "Hələ dərs bağlanmayıb",
            "No lessons linked yet",
            "Занятия ещё не привязаны",
            "Henüz ders bağlanmadı",
            "Noch keine Stunden zugeordnet",
        ),
        "Jurnal seçin": _t("Jurnal seçin", "Choose a journal", "Выберите журнал", "Defter seçin", "Journal auswählen"),
        "Jurnallar": _t("Jurnallar", "Journals", "Журналы", "Defterler", "Journale"),
        "Jurnalı aç": _t("Jurnalı aç", "Open journal", "Открыть журнал", "Defteri aç", "Journal öffnen"),
        "Kafedra": _t("Kafedra", "Department", "Кафедра", "Bölüm", "Lehrstuhl"),
        "Köçür": _t("Köçür", "Move", "Перевести", "Taşı", "Verschieben"),
        "Lab qrupu": _t("Lab qrupu", "Lab groups", "Лаб. групп", "Lab grubu", "Laborgruppen"),
        "Lab saatlı jurnal": _t(
            "Lab saatlı jurnal",
            "Journals with lab hours",
            "Журналы с лаб. часами",
            "Lab saatli defter",
            "Journale mit Laborstunden",
        ),
        "Laboratoriya dərsləri yarım qruplarla keçirsə, jurnalı burada Lab-1, Lab-2 … qruplarına bölün: jurnalı seçin, qrup yaradın, tələbələri seçib köçürün və ya sürüşdürüb qrupun üzərinə atın. Mühazirə və seminar bütün qrupla qalır.": _t(
            "Laboratoriya dərsləri yarım qruplarla keçirsə, jurnalı burada Lab-1, Lab-2 … qruplarına bölün: jurnalı seçin, qrup yaradın, tələbələri seçib köçürün və ya sürüşdürüb qrupun üzərinə atın. Mühazirə və seminar bütün qrupla qalır.",
            "If lab classes are held in half-groups, split the journal into Lab-1, Lab-2 … here: choose the journal, create groups, then select students and move them or drag them onto a group. Lectures and seminars stay with the whole group.",
            "Если лабораторные занятия проходят по подгруппам, разделите журнал здесь на Lab-1, Lab-2 …: выберите журнал, создайте группы, отметьте студентов и переведите их или перетащите на группу. Лекции и семинары остаются для всей группы.",
            "Laboratuvar dersleri yarım gruplarla yapılıyorsa defteri burada Lab-1, Lab-2 … gruplarına bölün: defteri seçin, grup oluşturun, öğrencileri seçip taşıyın veya sürükleyip grubun üzerine bırakın. Ders ve seminer tüm grupla kalır.",
            "Finden Laborstunden in Halbgruppen statt, teilen Sie das Journal hier in Lab-1, Lab-2 … auf: Journal wählen, Gruppen anlegen, Studierende auswählen und verschieben oder auf eine Gruppe ziehen. Vorlesung und Seminar bleiben bei der ganzen Gruppe.",
        ),
        "Laboratoriya saatı tədris planında, dərs yükündə və ya cədvəldə göstərilən jurnallar burada görünür. Başqa semestri seçə bilərsiniz.": _t(
            "Laboratoriya saatı tədris planında, dərs yükündə və ya cədvəldə göstərilən jurnallar burada görünür. Başqa semestri seçə bilərsiniz.",
            "Journals with lab hours in the curriculum, the teaching load or the timetable appear here. You can choose another semester.",
            "Здесь показаны журналы, у которых лабораторные часы указаны в учебном плане, нагрузке или расписании. Можно выбрать другой семестр.",
            "Laboratuvar saati öğretim planında, ders yükünde veya programda belirtilen defterler burada görünür. Başka bir dönem seçebilirsiniz.",
            "Hier erscheinen Journale, deren Laborstunden im Lehrplan, im Lehrdeputat oder im Stundenplan stehen. Sie können ein anderes Semester wählen.",
        ),
        "Ləğv et": _t("Ləğv et", "Cancel", "Отмена", "İptal", "Abbrechen"),
        "Müəllim": _t("Müəllim", "Teacher", "Преподаватель", "Öğretmen", "Lehrkraft"),
        "Növbəti": _t("Növbəti", "Next", "Далее", "Sonraki", "Weiter"),
        "Nəticə: %(n)s jurnal": _t(
            "Nəticə: %(n)s jurnal",
            "Result: %(n)s journals",
            "Найдено журналов: %(n)s",
            "Sonuç: %(n)s defter",
            "Ergebnis: %(n)s Journale",
        ),
        "Qrup": _t("Qrup", "Group", "Группа", "Grup", "Gruppe"),
        "Qrup yarat": _t("Qrup yarat", "Create group", "Создать группу", "Grup oluştur", "Gruppe anlegen"),
        "Qrupa dərs bağlıdır — silmək olmaz. Əvvəlcə həmin dərslərin qrupunu dəyişin.": _t(
            "Qrupa dərs bağlıdır — silmək olmaz. Əvvəlcə həmin dərslərin qrupunu dəyişin.",
            "Lessons are linked to this group — it cannot be deleted. Change the group of those lessons first.",
            "К группе привязаны занятия — удалить нельзя. Сначала измените группу этих занятий.",
            "Gruba ders bağlı — silinemez. Önce o derslerin grubunu değiştirin.",
            "Der Gruppe sind Stunden zugeordnet — Löschen nicht möglich. Ändern Sie zuerst die Gruppe dieser Stunden.",
        ),
        "Qrupda hələ tələbə yoxdur.": _t(
            "Qrupda hələ tələbə yoxdur.",
            "No students in the group yet.",
            "В группе пока нет студентов.",
            "Grupta henüz öğrenci yok.",
            "Noch keine Studierenden in der Gruppe.",
        ),
        "Qruplara bölünüb": _t(
            "Qruplara bölünüb", "Split into groups", "Разделено на группы", "Gruplara bölünmüş", "In Gruppen aufgeteilt"
        ),
        "Qruplu laboratoriya dərsləri bu tələbələrə aid deyil — onları qrupa yerləşdirin.": _t(
            "Qruplu laboratoriya dərsləri bu tələbələrə aid deyil — onları qrupa yerləşdirin.",
            "Group lab lessons do not apply to these students — place them in a group.",
            "Групповые лабораторные занятия к этим студентам не относятся — распределите их по группам.",
            "Gruplu laboratuvar dersleri bu öğrencilere ait değil — onları bir gruba yerleştirin.",
            "Gruppen-Laborstunden gelten nicht für diese Studierenden — ordnen Sie sie einer Gruppe zu.",
        ),
        "Qrupsuz": _t("Qrupsuz", "No group", "Без группы", "Grupsuz", "Ohne Gruppe"),
        "Qrupsuz et": _t(
            "Qrupsuz et", "Remove from group", "Убрать из группы", "Gruptan çıkar", "Aus Gruppe entfernen"
        ),
        "Qrupsuz tələbə": _t(
            "Qrupsuz tələbə",
            "Students without a group",
            "Студенты без группы",
            "Grupsuz öğrenci",
            "Studierende ohne Gruppe",
        ),
        "Qrupu sil": _t("Qrupu sil", "Delete group", "Удалить группу", "Grubu sil", "Gruppe löschen"),
        "Qrupu silmək": _t("Qrupu silmək", "Delete the group", "Удаление группы", "Grubu silmek", "Gruppe löschen"),
        "Qrupun adı": _t("Qrupun adı", "Group name", "Название группы", "Grubun adı", "Gruppenname"),
        "Saxla": _t("Saxla", "Save", "Сохранить", "Kaydet", "Speichern"),
        "Semestr": _t("Semestr", "Semester", "Семестр", "Dönem", "Semester"),
        "Seçilib": _t("Seçilib", "Selected", "Выбрано", "Seçildi", "Ausgewählt"),
        "Seçimi təmizlə": _t("Seçimi təmizlə", "Clear selection", "Снять выбор", "Seçimi temizle", "Auswahl aufheben"),
        "Soldakı siyahıdan jurnalı seçin — onun laboratoriya qrupları, qrupsuz tələbələri və köçürmə alətləri burada açılacaq.": _t(
            "Soldakı siyahıdan jurnalı seçin — onun laboratoriya qrupları, qrupsuz tələbələri və köçürmə alətləri burada açılacaq.",
            "Choose a journal from the list on the left — its lab groups, students without a group and the move tools will open here.",
            "Выберите журнал в списке слева — здесь откроются его лабораторные группы, студенты без группы и инструменты перевода.",
            "Soldaki listeden bir defter seçin — laboratuvar grupları, grupsuz öğrencileri ve taşıma araçları burada açılacak.",
            "Wählen Sie links ein Journal — hier öffnen sich seine Laborgruppen, Studierende ohne Gruppe und die Verschiebewerkzeuge.",
        ),
        "Sütundakı hamısını seç": _t(
            "Sütundakı hamısını seç",
            "Select all in the column",
            "Выбрать всех в столбце",
            "Sütundakilerin tümünü seç",
            "Alle in der Spalte auswählen",
        ),
        "Süzgəcləri dəyişin və ya «Sıfırla» basın.": _t(
            "Süzgəcləri dəyişin və ya «Sıfırla» basın.",
            "Change the filters or press “Reset”.",
            "Измените фильтры или нажмите «Сбросить».",
            "Filtreleri değiştirin veya «Sıfırla»ya basın.",
            "Ändern Sie die Filter oder klicken Sie auf „Zurücksetzen“.",
        ),
        "Süzgəcə uyğun jurnal yoxdur": _t(
            "Süzgəcə uyğun jurnal yoxdur",
            "No journals match the filters",
            "Нет журналов по фильтрам",
            "Filtreye uyan defter yok",
            "Keine Journale passen zu den Filtern",
        ),
        "Səhifələr": _t("Səhifələr", "Pages", "Страницы", "Sayfalar", "Seiten"),
        "Tələbə axtar": _t("Tələbə axtar", "Search students", "Поиск студента", "Öğrenci ara", "Studierende suchen"),
        "Tələbə axtar…": _t(
            "Tələbə axtar…", "Search students…", "Поиск студента…", "Öğrenci ara…", "Studierende suchen…"
        ),
        "Tələbə sayı": _t(
            "Tələbə sayı", "Number of students", "Число студентов", "Öğrenci sayısı", "Anzahl Studierende"
        ),
        "Tələbələri buraya sürüşdürün": _t(
            "Tələbələri buraya sürüşdürün",
            "Drag students here",
            "Перетащите студентов сюда",
            "Öğrencileri buraya sürükleyin",
            "Studierende hierher ziehen",
        ),
        "Tələbəni sürüşdürüb qrupun üzərinə atın və ya bir neçəsini seçib «Köçür» basın.": _t(
            "Tələbəni sürüşdürüb qrupun üzərinə atın və ya bir neçəsini seçib «Köçür» basın.",
            "Drag a student onto a group, or select several and press “Move”.",
            "Перетащите студента на группу или выберите нескольких и нажмите «Перевести».",
            "Öğrenciyi sürükleyip grubun üzerine bırakın veya birkaçını seçip «Taşı»ya basın.",
            "Ziehen Sie Studierende auf eine Gruppe oder wählen Sie mehrere und klicken Sie auf „Verschieben“.",
        ),
        "Tələbənin öz qrupunun dərslərində qeydi var — köçürmək olmaz (qeydlər itməsin deyə).": _t(
            "Tələbənin öz qrupunun dərslərində qeydi var — köçürmək olmaz (qeydlər itməsin deyə).",
            "The student has records in their own group's lessons — cannot be moved (so the records are kept).",
            "У студента есть отметки на занятиях его группы — перевести нельзя (чтобы отметки не потерялись).",
            "Öğrencinin kendi grubunun derslerinde kaydı var — taşınamaz (kayıtlar kaybolmasın diye).",
            "Die Person hat Einträge in Stunden ihrer Gruppe — Verschieben nicht möglich (damit die Einträge erhalten bleiben).",
        ),
        "Vəziyyət": _t("Vəziyyət", "Status", "Состояние", "Durum", "Status"),
        "Yeni laboratoriya qrupu": _t(
            "Yeni laboratoriya qrupu",
            "New lab group",
            "Новая лабораторная группа",
            "Yeni laboratuvar grubu",
            "Neue Laborgruppe",
        ),
        "Yerləşdirilib: %(done)s / %(total)s": _t(
            "Yerləşdirilib: %(done)s / %(total)s",
            "Placed: %(done)s / %(total)s",
            "Распределено: %(done)s / %(total)s",
            "Yerleştirildi: %(done)s / %(total)s",
            "Zugeordnet: %(done)s / %(total)s",
        ),
        "qeyd var": _t("qeyd var", "has records", "есть отметки", "kaydı var", "hat Einträge"),
        "tələbə": _t("tələbə", "students", "студ.", "öğrenci", "Studierende"),
        "«%(label)s» silinəcək; onun %(n)s tələbəsi qrupsuz qalacaq. Davam edilsin?": _t(
            "«%(label)s» silinəcək; onun %(n)s tələbəsi qrupsuz qalacaq. Davam edilsin?",
            "“%(label)s” will be deleted; its %(n)s students will be left without a group. Continue?",
            "«%(label)s» будет удалена; её студенты (%(n)s) останутся без группы. Продолжить?",
            "«%(label)s» silinecek; %(n)s öğrencisi grupsuz kalacak. Devam edilsin mi?",
            "„%(label)s“ wird gelöscht; ihre %(n)s Studierenden bleiben ohne Gruppe. Fortfahren?",
        ),
        "«Başqasının adından» rejimində qruplar yalnız göstərilir — dəyişiklik edilmir.": _t(
            "«Başqasının adından» rejimində qruplar yalnız göstərilir — dəyişiklik edilmir.",
            "In “view as” mode the groups are only shown — nothing can be changed.",
            "В режиме «от имени другого» группы только отображаются — изменения недоступны.",
            "«Başkası adına» modunda gruplar yalnızca gösterilir — değişiklik yapılmaz.",
            "Im Modus „Ansicht als“ werden die Gruppen nur angezeigt — Änderungen sind nicht möglich.",
        ),
        "Əməliyyat alınmadı — yenidən cəhd edin.": _t(
            "Əməliyyat alınmadı — yenidən cəhd edin.",
            "The action failed — please try again.",
            "Операция не удалась — попробуйте ещё раз.",
            "İşlem başarısız — tekrar deneyin.",
            "Aktion fehlgeschlagen — bitte erneut versuchen.",
        ),
        "Əvvəlcə tələbələri seçin.": _t(
            "Əvvəlcə tələbələri seçin.",
            "Select students first.",
            "Сначала выберите студентов.",
            "Önce öğrencileri seçin.",
            "Wählen Sie zuerst Studierende aus.",
        ),
        "Əvvəlki": _t("Əvvəlki", "Previous", "Назад", "Önceki", "Zurück"),
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain="django"):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(translations[lang])}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for lang in LOCALES:
        fill(lang)
