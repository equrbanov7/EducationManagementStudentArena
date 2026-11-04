#!/usr/bin/env python3
"""EMSArena i18n — «Alt qrup tələbələri» kabinet bölməsi (sahib 2026-11-05).

Kontekstlər: ``registrar.subgroup_students`` (vəziyyət / növ / sənəd seçimləri, statistika etiketləri),
``accounts.subgroup_students`` (bölmə, cədvəl, statistika, əlavə modalı, Excel), ``profile.section`` (menyu adı).
msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Sonra `.mo` faylları `msgfmt` ilə yığılır.

İstifadə:  python scripts/i18n_fill_subgroup_students_2026_11_05.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de, az=None):
    return {"en": en, "ru": ru, "tr": tr, "de": de, "az": az}


SECTION_TITLE = t("Subgroup students", "Студенты подгрупп", "Alt grup öğrencileri", "Studierende in Untergruppen")
ADD_TITLE = t(
    "Add a student to a subgroup",
    "Добавить студента в подгруппу",
    "Alt gruba öğrenci ekle",
    "Studierende(n) zur Untergruppe hinzufügen",
)
NO_DOCUMENT = t("No document", "Нет документа", "Belge yok", "Kein Dokument")
INTENSIVE = t("Intensive course", "Интенсивный курс", "Yoğun kurs", "Intensivkurs")
RELEASED = t(
    "Released from own journal",
    "Освобождён из своего журнала",
    "Kendi yoklama defterinden muaf",
    "Aus eigenem Journal gelöst",
)

ENTRIES = {
    "profile.section": {"Alt qrup tələbələri": SECTION_TITLE},
    "registrar.subgroup_students": {
        "Aktiv": t("Active", "Активен", "Aktif", "Laufend"),
        "Tamamlanıb": t("Completed", "Завершён", "Tamamlandı", "Abgeschlossen"),
        "Dondurulub": t("Suspended", "Приостановлен", "Donduruldu", "Ausgesetzt"),
        "Jurnaldan çıxarılıb": t(
            "Removed from journal", "Исключён из журнала", "Defterden çıkarıldı", "Aus dem Journal entfernt"
        ),
        "Köçürmə ilə əvəzlənib": t(
            "Superseded by transfer", "Заменён переводом", "Nakil ile değiştirildi", "Durch Versetzung ersetzt"
        ),
        "Öz jurnalından azad edilib": RELEASED,
        "Alt qrup": t("Subgroup", "Подгруппа", "Alt grup", "Untergruppe"),
        "İntensiv kurs": INTENSIVE,
        "Təkrar tədris": t("Re-teaching (retake)", "Повторное обучение", "Tekrar öğretim", "Wiederholung (Retake)"),
        "Sənəd var (fayl və ya sərəncam)": t(
            "Document present (file or order)",
            "Документ есть (файл или приказ)",
            "Belge var (dosya veya emir)",
            "Dokument vorhanden (Datei oder Anordnung)",
        ),
        "Fayl yüklənib": t("File uploaded", "Файл загружен", "Dosya yüklendi", "Datei hochgeladen"),
        "Sərəncam nömrəsi": t("Order number", "Номер приказа", "Emir numarası", "Anordnungsnummer"),
        "Sənədsiz — superadmin / RİM rəhbəri düzəlişi": t(
            "Without document — superadmin / DDC head correction",
            "Без документа — исправление суперадмина / руководителя ЦЦР",
            "Belgesiz — süper yönetici / DGM başkanı düzeltmesi",
            "Ohne Dokument — Korrektur durch Superadmin / DEZ-Leitung",
        ),
        "Sənəd yoxdur": NO_DOCUMENT,
        "Müəllim təyin olunmayıb": t(
            "No teacher assigned", "Преподаватель не назначен", "Öğretim elemanı atanmadı", "Keine Lehrkraft zugewiesen"
        ),
    },
    "accounts.subgroup_students": {
        "%(n)s hazırda aktiv": t(
            "%(n)s active now", "%(n)s активны сейчас", "%(n)s şu an aktif", "%(n)s derzeit aktiv"
        ),
        "Ad, soyad və ya istifadəçi adı": t(
            "First name, last name or username",
            "Имя, фамилия или имя пользователя",
            "Ad, soyad veya kullanıcı adı",
            "Vorname, Nachname oder Benutzername",
        ),
        "Alt qrup olduğu jurnal": t(
            "Journal (as subgroup)", "Журнал (как подгруппа)", "Alt grup olduğu defter", "Journal (als Untergruppe)"
        ),
        "Alt qrup olduğu qrup": t(
            "Group (as subgroup)", "Группа (как подгруппа)", "Alt grup olduğu grup", "Gruppe (als Untergruppe)"
        ),
        "Alt qrup tələbələrinin ixracı": t(
            "Export of subgroup students",
            "Экспорт студентов подгрупп",
            "Alt grup öğrencilerinin dışa aktarımı",
            "Export der Studierenden in Untergruppen",
        ),
        "Alt qrupa tələbə əlavə et": ADD_TITLE,
        "Alt qrupdan əlavə olunmuş tələbələr": t(
            "Students added from other groups",
            "Студенты, добавленные из других групп",
            "Diğer gruplardan eklenen öğrenciler",
            "Aus anderen Gruppen hinzugefügte Studierende",
        ),
        "Başqa (alt) qrupdan jurnala əlavə olunmuş hər tələbə: öz qrupu, alt qrup olduğu jurnal, fənn, müəllim, "
        "kredit, səbəb və əlavə olunarkən təqdim edilən sənəd. Süzgəclərlə daraldın, başlığa klikləyib sıralayın.": t(
            "Every student added to a journal from another (sub)group: home group, journal, subject, teacher, "
            "credits, reason and the document submitted. Narrow with the filters, click a header to sort.",
            "Каждый студент, добавленный в журнал из другой (под)группы: своя группа, журнал, предмет, "
            "преподаватель, кредиты, причина и представленный документ. Сужайте фильтрами, сортируйте по заголовку.",
            "Başka (alt) gruptan deftere eklenen her öğrenci: kendi grubu, defter, ders, öğretim elemanı, kredi, "
            "neden ve sunulan belge. Filtrelerle daraltın, sıralamak için başlığa tıklayın.",
            "Alle Studierenden, die aus einer anderen (Unter-)Gruppe in ein Journal aufgenommen wurden: "
            "Stammgruppe, Journal, Fach, Lehrkraft, Credits, Grund und vorgelegtes Dokument. Mit Filtern "
            "eingrenzen, zum Sortieren auf eine Spaltenüberschrift klicken.",
        ),
        "Bu bölmə RİM rəhbəri, superadmin və alt qrup yerləşdirmə səlahiyyəti olan rollar üçündür.": t(
            "This section is for the DDC head, superadmin and roles allowed to place students in subgroups.",
            "Этот раздел для руководителя ЦЦР, суперадмина и ролей с правом размещения в подгруппы.",
            "Bu bölüm DGM başkanı, süper yönetici ve alt gruba yerleştirme yetkisi olan roller içindir.",
            "Dieser Bereich ist für die DEZ-Leitung, Superadmins und Rollen mit Untergruppen-Zuweisungsrecht.",
        ),
        "Bu jurnalda artıq olan tələbələr göstərilir, amma seçilə bilmir.": t(
            "Students already in this journal are shown but cannot be selected.",
            "Студенты, уже находящиеся в журнале, показаны, но не могут быть выбраны.",
            "Bu defterde zaten olan öğrenciler gösterilir ama seçilemez.",
            "Bereits im Journal befindliche Studierende werden angezeigt, sind aber nicht auswählbar.",
        ),
        "Bu qrupda uyğun tələbə tapılmadı.": t(
            "No matching student in this group.",
            "В этой группе подходящий студент не найден.",
            "Bu grupta uygun öğrenci bulunamadı.",
            "Keine passenden Studierenden in dieser Gruppe.",
        ),
        "Cari qrupu": t("Current group", "Текущая группа", "Mevcut grubu", "Aktuelle Gruppe"),
        "Excel-ə ixrac": t("Export to Excel", "Экспорт в Excel", "Excel'e aktar", "Nach Excel exportieren"),
        "Fakültə": t("Faculty", "Факультет", "Fakülte", "Fakultät"),
        "Fakültə üzrə (tələbənin öz fakültəsi)": t(
            "By faculty (student's own faculty)",
            "По факультетам (факультет студента)",
            "Fakülteye göre (öğrencinin kendi fakültesi)",
            "Nach Fakultät (eigene Fakultät der Studierenden)",
        ),
        "Fayl ilk %(n)s sətirlə məhdudlaşdırılıb — süzgəcləri daraldıb yenidən yükləyin.": t(
            "The file is limited to the first %(n)s rows — narrow the filters and download again.",
            "Файл ограничен первыми %(n)s строками — сузьте фильтры и скачайте снова.",
            "Dosya ilk %(n)s satırla sınırlandı — filtreleri daraltıp yeniden indirin.",
            "Die Datei ist auf die ersten %(n)s Zeilen begrenzt — Filter eingrenzen und erneut herunterladen.",
        ),
        "Fənn": t("Subject", "Предмет", "Ders", "Fach"),
        "Fənn kodu": t("Subject code", "Код предмета", "Ders kodu", "Fachcode"),
        "Hamısı": t("All", "Все", "Tümü", "Alle"),
        "Hədəf jurnal (alt qrup olacağı jurnal)": t(
            "Target journal (where the student joins as subgroup)",
            "Целевой журнал (куда студент добавляется как подгруппа)",
            "Hedef defter (öğrencinin alt grup olacağı defter)",
            "Zieljournal (in das die/der Studierende als Untergruppe kommt)",
        ),
        "Hədəf jurnalı seçin.": t(
            "Select the target journal.", "Выберите целевой журнал.", "Hedef defteri seçin.", "Zieljournal wählen."
        ),
        "Həftəlik trend": t("Weekly trend", "Недельная динамика", "Haftalık eğilim", "Wochentrend"),
        "Həftəlik trend (son 12 həftə)": t(
            "Weekly trend (last 12 weeks)",
            "Недельная динамика (последние 12 недель)",
            "Haftalık eğilim (son 12 hafta)",
            "Wochentrend (letzte 12 Wochen)",
        ),
        "Hələ alt qrupdan əlavə olunmuş tələbə yoxdur": t(
            "No students have been added from other groups yet",
            "Студентов, добавленных из других групп, пока нет",
            "Henüz diğer gruplardan eklenen öğrenci yok",
            "Noch keine aus anderen Gruppen hinzugefügten Studierenden",
        ),
        "Jurnalda və ya «Alt qrupa tələbə əlavə et» bölməsində əlavə ediləndə tələbə burada görünəcək.": t(
            "Students appear here once added in a journal or in «Add a student to a subgroup».",
            "Студент появится здесь после добавления в журнале или в разделе «Добавить студента в подгруппу».",
            "Öğrenci defterde veya «Alt gruba öğrenci ekle» bölümünde eklendiğinde burada görünür.",
            "Studierende erscheinen hier, sobald sie im Journal oder unter «Zur Untergruppe hinzufügen» "
            "aufgenommen werden.",
        ),
        "Kafedra": t("Chair", "Кафедра", "Bölüm", "Lehrstuhl"),
        "Kredit": t("Credits", "Кредиты", "Kredi", "Credits"),
        "Müəllim": t("Teacher", "Преподаватель", "Öğretim elemanı", "Lehrkraft"),
        "Müəllimin adı": t("Teacher's name", "Имя преподавателя", "Öğretim elemanının adı", "Name der Lehrkraft"),
        "Məlumat yoxdur": t("No data", "Нет данных", "Veri yok", "Keine Daten"),
        "Mənbə qrup (tələbənin öz qrupu)": t(
            "Source group (student's own group)",
            "Исходная группа (своя группа студента)",
            "Kaynak grup (öğrencinin kendi grubu)",
            "Herkunftsgruppe (eigene Gruppe)",
        ),
        "Mənbə qrupu və tələbəni seçin.": t(
            "Select the source group and the student.",
            "Выберите исходную группу и студента.",
            "Kaynak grubu ve öğrenciyi seçin.",
            "Herkunftsgruppe und Studierende(n) wählen.",
        ),
        "Məs.: dekanlığın təqdimatı №…, akademik borc": t(
            "E.g.: dean's office submission No…, academic debt",
            "Напр.: представление деканата №…, академическая задолженность",
            "Örn.: dekanlık yazısı No…, akademik borç",
            "Z. B.: Vorlage des Dekanats Nr. …, akademischer Rückstand",
        ),
        "Növ": t("Type", "Тип", "Tür", "Art"),
        "Növbəti": t("Next", "Следующая", "Sonraki", "Weiter"),
        "Nəticə: %(n)s qeyd": t(
            "Result: %(n)s records", "Результат: %(n)s записей", "Sonuç: %(n)s kayıt", "Ergebnis: %(n)s Einträge"
        ),
        "Qrup axtarın…": t("Search for a group…", "Найдите группу…", "Grup arayın…", "Gruppe suchen…"),
        "Qrup, fənn və ya müəllim axtarın…": t(
            "Search group, subject or teacher…",
            "Найдите группу, предмет или преподавателя…",
            "Grup, ders veya öğretim elemanı arayın…",
            "Gruppe, Fach oder Lehrkraft suchen…",
        ),
        "Semestr": t("Semester", "Семестр", "Yarıyıl", "Semester"),
        "Sizin üçün könüllüdür — sənədsiz əlavədə səbəbə avtomatik «sənədsiz düzəliş» qeydi yazılır.": t(
            "Optional for you — without a document the reason automatically gets a «correction without document» note.",
            "Для вас необязательно — без документа к причине автоматически добавляется отметка "
            "«исправление без документа».",
            "Sizin için isteğe bağlı — belgesiz eklemede nedene otomatik «belgesiz düzeltme» notu yazılır.",
            "Für Sie optional — ohne Dokument erhält der Grund automatisch den Vermerk «Korrektur ohne Dokument».",
        ),
        "Statistika": t("Statistics", "Статистика", "İstatistik", "Statistik"),
        "Süzgəcləri dəyişin və ya «Sıfırla» basın.": t(
            "Change the filters or press «Reset».",
            "Измените фильтры или нажмите «Сбросить».",
            "Filtreleri değiştirin veya «Sıfırla»ya basın.",
            "Ändern Sie die Filter oder klicken Sie auf «Zurücksetzen».",
        ),
        "Süzgəcə uyğun tələbə yoxdur": t(
            "No students match the filters",
            "Нет студентов, соответствующих фильтрам",
            "Filtreye uygun öğrenci yok",
            "Keine Studierenden entsprechen den Filtern",
        ),
        "Səbəb": t("Reason", "Причина", "Neden", "Grund"),
        "Səbəb / qeyd": t("Reason / note", "Причина / примечание", "Neden / not", "Grund / Notiz"),
        "Səbəb yazılmalıdır.": t(
            "A reason is required.", "Необходимо указать причину.", "Neden yazılmalıdır.", "Ein Grund ist erforderlich."
        ),
        "Səhifə %(page)s / %(last)s": t(
            "Page %(page)s / %(last)s",
            "Страница %(page)s / %(last)s",
            "Sayfa %(page)s / %(last)s",
            "Seite %(page)s / %(last)s",
        ),
        "Səhifələr": t("Pages", "Страницы", "Sayfalar", "Seiten"),
        "Sənəd": t("Document", "Документ", "Belge", "Dokument"),
        "Sənəd (təqdimat / sərəncam — PDF, JPG, PNG)": t(
            "Document (submission / order — PDF, JPG, PNG)",
            "Документ (представление / приказ — PDF, JPG, PNG)",
            "Belge (yazı / emir — PDF, JPG, PNG)",
            "Dokument (Vorlage / Anordnung — PDF, JPG, PNG)",
        ),
        "Sənəd (təqdimat / sərəncam) yüklənməlidir.": t(
            "A document (submission / order) must be uploaded.",
            "Необходимо загрузить документ (представление / приказ).",
            "Belge (yazı / emir) yüklenmelidir.",
            "Ein Dokument (Vorlage / Anordnung) muss hochgeladen werden.",
        ),
        "Sənəd linki / sərəncam": t(
            "Document link / order",
            "Ссылка на документ / приказ",
            "Belge bağlantısı / emir",
            "Dokumentlink / Anordnung",
        ),
        "Sənəd yoxdur": NO_DOCUMENT,
        "Sənədli": t("With document", "С документом", "Belgeli", "Mit Dokument"),
        "Sənədsiz düzəliş": t(
            "Correction without document", "Исправление без документа", "Belgesiz düzeltme", "Korrektur ohne Dokument"
        ),
        "Sənədə bax": t("View document", "Открыть документ", "Belgeyi görüntüle", "Dokument ansehen"),
        "Sərəncam № %(number)s": t(
            "Order No. %(number)s", "Приказ № %(number)s", "Emir No %(number)s", "Anordnung Nr. %(number)s"
        ),
        "Tarix": t("Date", "Дата", "Tarih", "Datum"),
        "Tarixdən": t("From date", "С даты", "Başlangıç tarihi", "Ab Datum"),
        "Tarixədək": t("To date", "По дату", "Bitiş tarihi", "Bis Datum"),
        "Tələbə": t("Student", "Студент", "Öğrenci", "Studierende(r)"),
        "Tələbə axtarın…": t("Search for a student…", "Найдите студента…", "Öğrenci arayın…", "Studierende suchen…"),
        "Tələbə bu fənn üzrə öz qrupunun jurnalında aktivdirsə: əvvəlki qeydiyyat tarixçəyə keçir, bal və "
        "davamiyyət saxlanılır.": t(
            "If the student is active in this subject in their own group's journal: the previous enrolment moves "
            "to history, marks and attendance are kept.",
            "Если студент активен по этому предмету в журнале своей группы: прежняя запись уходит в историю, "
            "оценки и посещаемость сохраняются.",
            "Öğrenci bu derste kendi grubunun defterinde aktifse: önceki kayıt geçmişe taşınır, not ve devam korunur.",
            "Ist die/der Studierende in diesem Fach im Journal der eigenen Gruppe aktiv: Die bisherige Einschreibung "
            "wird archiviert, Noten und Anwesenheit bleiben erhalten.",
        ),
        "Tələbə jurnala əlavə olundu.": t(
            "The student was added to the journal.",
            "Студент добавлен в журнал.",
            "Öğrenci deftere eklendi.",
            "Die/der Studierende wurde dem Journal hinzugefügt.",
        ),
        "Uyğun jurnal tapılmadı.": t(
            "No matching journal found.",
            "Подходящий журнал не найден.",
            "Uygun defter bulunamadı.",
            "Kein passendes Journal.",
        ),
        "Uyğun qrup tapılmadı.": t(
            "No matching group found.",
            "Подходящая группа не найдена.",
            "Uygun grup bulunamadı.",
            "Keine passende Gruppe.",
        ),
        "Vəziyyət": t("Status", "Состояние", "Durum", "Status"),
        "Yalnız cari semestrin açıq jurnalları və sizin əhatənizdəki qruplar.": t(
            "Only open journals of the current semester and groups in your scope.",
            "Только открытые журналы текущего семестра и группы в вашей зоне ответственности.",
            "Yalnızca mevcut yarıyılın açık defterleri ve yetki alanınızdaki gruplar.",
            "Nur offene Journale des aktuellen Semesters und Gruppen in Ihrem Zuständigkeitsbereich.",
        ),
        "Yalnız sizin struktur əhatənizdəki qrupların tələbələri və jurnalları göstərilir.": t(
            "Only students and journals of groups within your structural scope are shown.",
            "Показаны только студенты и журналы групп в вашей структурной зоне.",
            "Yalnızca yapısal yetki alanınızdaki grupların öğrencileri ve defterleri gösterilir.",
            "Es werden nur Studierende und Journale der Gruppen in Ihrem Zuständigkeitsbereich angezeigt.",
        ),
        "Yazı jurnal modalının rəsmi yolu ilə gedir: kredit həddi, jurnal tutumu və siyahı qapısı eynidir.": t(
            "Saved through the journal dialog's official path: the same credit limit, journal capacity and roster "
            "checks apply.",
            "Запись идёт через официальный путь журнала: те же лимит кредитов, вместимость журнала и проверки списка.",
            "Kayıt, defter penceresinin resmi yolundan geçer: aynı kredi sınırı, defter kapasitesi ve liste kontrolü.",
            "Gespeichert über den offiziellen Weg des Journaldialogs: gleiche Credit-Grenze, Journalkapazität und "
            "Listenprüfung.",
        ),
        "birləşmə: %(n)s · intensiv: %(m)s": t(
            "merged: %(n)s · intensive: %(m)s",
            "объединение: %(n)s · интенсив: %(m)s",
            "birleştirme: %(n)s · yoğun: %(m)s",
            "zusammengeführt: %(n)s · intensiv: %(m)s",
        ),
        "cəmi %(n)s kredit": t(
            "%(n)s credits in total", "всего %(n)s кредитов", "toplam %(n)s kredi", "insgesamt %(n)s Credits"
        ),
        "cəmi %(n)s sənəd": t(
            "%(n)s documents in total", "всего %(n)s документов", "toplam %(n)s belge", "insgesamt %(n)s Dokumente"
        ),
        "fayl və ya sərəncam": t("file or order", "файл или приказ", "dosya veya emir", "Datei oder Anordnung"),
        "indi: %(group)s": t("now: %(group)s", "сейчас: %(group)s", "şimdi: %(group)s", "jetzt: %(group)s"),
        "superadmin / RİM rəhbəri": t(
            "superadmin / DDC head",
            "суперадмин / руководитель ЦЦР",
            "süper yönetici / DGM başkanı",
            "Superadmin / DEZ-Leitung",
        ),
        "sənədsiz — superadmin/RİM rəhbəri düzəlişi": t(
            "no document — superadmin/DDC head correction",
            "без документа — исправление суперадмина/руководителя ЦЦР",
            "belgesiz — süper yönetici/DGM başkanı düzeltmesi",
            "ohne Dokument — Korrektur durch Superadmin/DEZ-Leitung",
        ),
        "Öz jurnalından azad et (alt qrup birləşməsi)": t(
            "Release from own journal (subgroup merge)",
            "Освободить из своего журнала (объединение подгруппы)",
            "Kendi defterinden muaf tut (alt grup birleştirme)",
            "Aus eigenem Journal lösen (Untergruppen-Zusammenführung)",
        ),
        "Öz qrupu": t("Home group", "Своя группа", "Kendi grubu", "Stammgruppe"),
        "öz jurnalından azad edilib": t(
            "released from own journal",
            "освобождён из своего журнала",
            "kendi defterinden muaf",
            "aus eigenem Journal gelöst",
        ),
        "İstifadəçi adı": t("Username", "Имя пользователя", "Kullanıcı adı", "Benutzername"),
        "Əlavə": t("Additions", "Добавления", "Eklemeler", "Hinzufügungen"),
        "Əlavə edən": t("Added by", "Кем добавлен", "Ekleyen", "Hinzugefügt von"),
        "Əlavə et": t("Add", "Добавить", "Ekle", "Hinzufügen"),
        "Əməliyyat alınmadı — yenidən cəhd edin.": t(
            "The operation failed — please try again.",
            "Операция не удалась — попробуйте снова.",
            "İşlem başarısız — tekrar deneyin.",
            "Vorgang fehlgeschlagen — bitte erneut versuchen.",
        ),
        "Ən çox alt qrup olduğu qrup (haraya)": t(
            "Top target groups (where to)",
            "Чаще всего — группа назначения (куда)",
            "En çok hedef grup (nereye)",
            "Häufigste Zielgruppen (wohin)",
        ),
        "Ən çox fənn": t("Top subjects", "Чаще всего — предметы", "En çok ders", "Häufigste Fächer"),
        "Ən çox müəllim": t(
            "Top teachers", "Чаще всего — преподаватели", "En çok öğretim elemanı", "Häufigste Lehrkräfte"
        ),
        "Ən çox öz qrupu (haradan)": t(
            "Top home groups (where from)",
            "Чаще всего — своя группа (откуда)",
            "En çok kaynak grup (nereden)",
            "Häufigste Stammgruppen (woher)",
        ),
        "Əvvəlcə jurnal seçin…": t(
            "Select a journal first…", "Сначала выберите журнал…", "Önce defter seçin…", "Zuerst ein Journal wählen…"
        ),
        "Əvvəlcə qrup seçin…": t(
            "Select a group first…", "Сначала выберите группу…", "Önce grup seçin…", "Zuerst eine Gruppe wählen…"
        ),
        "Əvvəlki": t("Previous", "Предыдущая", "Önceki", "Zurück"),
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
            msgstr = (translations.get("az") or msgid) if lang == "az" else translations[lang]
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for lang in LOCALES:
        fill(lang)
