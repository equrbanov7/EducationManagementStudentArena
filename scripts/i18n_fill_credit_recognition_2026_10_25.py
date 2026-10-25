#!/usr/bin/env python3
"""EMSArena i18n — «Xarici nəticələrin tanınması» (Erasmus+ / mübadilə / başqa ali məktəb → fəndən azad), 2026-10-25.

msgid AZ cümlədir → az msgstr = msgid (model meta-ları istisna: ``AZ_OVERRIDES``). İdempotentdir; sonra
`compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

R = "registrar.recognition"
META = "registrar.model.recognition.meta"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


AZ_OVERRIDES = {
    (META, "external credit recognition"): "xarici nəticənin tanınması",
    (META, "external credit recognitions"): "xarici nəticələrin tanınması",
}

ENTRIES = {
    META: {
        "external credit recognition": t(
            "external credit recognition",
            "признание внешнего результата",
            "dış sonucun tanınması",
            "Anerkennung externer Leistung",
        ),
        "external credit recognitions": t(
            "external credit recognitions",
            "признания внешних результатов",
            "dış sonuçların tanınması",
            "Anerkennungen externer Leistungen",
        ),
    },
    "registrar.subject_exempt": {
        "Bu azadlıq xarici nəticənin tanınmasına bağlıdır — «Xarici nəticələrin tanınması» bölməsində tanınmanı "
        "ləğv edin.": t(
            "This exemption is linked to an external result recognition — revoke the recognition in the "
            "“External results recognition” section.",
            "Это освобождение связано с признанием внешнего результата — отмените признание в разделе "
            "«Признание внешних результатов».",
            "Bu muafiyet dış sonucun tanınmasına bağlıdır — tanımayı «Dış sonuçların tanınması» bölümünde iptal edin.",
            "Diese Befreiung ist an eine Anerkennung externer Leistung gebunden — widerrufen Sie die Anerkennung im "
            "Bereich „Anerkennung externer Leistungen“.",
        ),
    },
    "registrar.pdf": {
        "%(mark)s Başqa təhsil proqramında keçilmiş fənnin tanınmış nəticəsi; bal universitetin 100 ballıq "
        "şkalasına çevrilib. Proqramlar:": t(
            "%(mark)s Recognised result of a course taken in another study programme; the score has been converted "
            "to the university's 100-point scale. Programmes:",
            "%(mark)s Признанный результат дисциплины, пройденной в другой образовательной программе; балл переведён "
            "в 100-балльную шкалу университета. Программы:",
            "%(mark)s Başka bir eğitim programında alınan dersin tanınmış sonucu; puan üniversitenin 100'lük ölçeğine "
            "dönüştürülmüştür. Programlar:",
            "%(mark)s Anerkanntes Ergebnis eines in einem anderen Studienprogramm belegten Fachs; die Punktzahl wurde "
            "auf die 100-Punkte-Skala der Universität umgerechnet. Programme:",
        ),
        "%(mark)s Başqa ali məktəbdə (Erasmus+, mübadilə və s.) keçilmiş fənnin tanınmış nəticəsi; bal universitetin "
        "100 ballıq şkalasına çevrilib.": t(
            "%(mark)s Recognised result of a course taken at another higher education institution (Erasmus+, "
            "exchange, etc.); the score has been converted to the university's 100-point scale.",
            "%(mark)s Признанный результат дисциплины, пройденной в другом вузе (Erasmus+, обмен и т. п.); балл "
            "переведён в 100-балльную шкалу университета.",
            "%(mark)s Başka bir yükseköğretim kurumunda (Erasmus+, değişim vb.) alınan dersin tanınmış sonucu; puan "
            "üniversitenin 100'lük ölçeğine dönüştürülmüştür.",
            "%(mark)s Anerkanntes Ergebnis eines an einer anderen Hochschule (Erasmus+, Austausch usw.) belegten "
            "Fachs; die Punktzahl wurde auf die 100-Punkte-Skala der Universität umgerechnet.",
        ),
    },
    "profile.sidebar": {
        "Xarici nəticələrin tanınması": t(
            "External results recognition",
            "Признание внешних результатов",
            "Dış sonuçların tanınması",
            "Anerkennung externer Leistungen",
        ),
    },
    "organizations.permission.label": {
        "Xarici nəticəni tanımaq (Erasmus+, mübadilə, başqa ali məktəb, yay məktəbi və s.) və tələbəni fəndən azad "
        "etmək": t(
            "Recognise external results (Erasmus+, exchange, another university, summer school, etc.) and exempt the "
            "student from the course",
            "Признавать внешние результаты (Erasmus+, обмен, другой вуз, летняя школа и т. п.) и освобождать студента "
            "от дисциплины",
            "Dış sonuçları tanımak (Erasmus+, değişim, başka üniversite, yaz okulu vb.) ve öğrenciyi dersten muaf tutmak",
            "Externe Leistungen anerkennen (Erasmus+, Austausch, andere Hochschule, Sommerschule usw.) und Studierende "
            "vom Fach befreien",
        ),
        "Xarici nəticəni tanımaq (Erasmus+, mübadilə, başqa ali məktəb) və tələbəni fəndən azad etmək": t(
            "Recognise external results (Erasmus+, exchange, another university) and exempt the student from the "
            "course",
            "Признавать внешние результаты (Erasmus+, обмен, другой вуз) и освобождать студента от дисциплины",
            "Dış sonuçları tanımak (Erasmus+, değişim, başka üniversite) ve öğrenciyi dersten muaf tutmak",
            "Externe Leistungen anerkennen (Erasmus+, Austausch, andere Hochschule) und Studierende vom Fach befreien",
        ),
    },
    R: {
        "Digər (adını yazın)": t(
            "Other (enter the name)", "Другое (укажите название)", "Diğer (adını yazın)", "Sonstiges (Namen angeben)"
        ),
        "Proqram / səbəb": t("Programme / reason", "Программа / основание", "Program / gerekçe", "Programm / Grund"),
        "Proqramın / səbəbin adı": t(
            "Programme / reason name",
            "Название программы / основания",
            "Programın / gerekçenin adı",
            "Name des Programms / Grundes",
        ),
        "məs. Yay məktəbi, onlayn kurs, Erasmus+ KA171": t(
            "e.g. Summer school, online course, Erasmus+ KA171",
            "напр. летняя школа, онлайн-курс, Erasmus+ KA171",
            "örn. Yaz okulu, çevrimiçi kurs, Erasmus+ KA171",
            "z. B. Sommerschule, Online-Kurs, Erasmus+ KA171",
        ),
        "«Digər» seçilibsə məcburidir; digər növlərdə dəqiqləşdirmə üçündür.": t(
            "Required when “Other” is selected; for other types it is an optional refinement.",
            "Обязательно, если выбрано «Другое»; для остальных типов — уточнение.",
            "«Diğer» seçildiyse zorunludur; diğer türlerde açıklama içindir.",
            "Pflicht bei „Sonstiges“; bei anderen Arten eine optionale Präzisierung.",
        ),
        "«Digər» seçilibsə proqramın / səbəbin adını yazın (məs. yay məktəbi, onlayn kurs).": t(
            "If “Other” is selected, enter the programme / reason name (e.g. summer school, online course).",
            "Если выбрано «Другое», укажите название программы / основания (напр. летняя школа, онлайн-курс).",
            "«Diğer» seçildiyse programın / gerekçenin adını yazın (örn. yaz okulu, çevrimiçi kurs).",
            "Bei „Sonstiges“ den Namen des Programms / Grundes angeben (z. B. Sommerschule, Online-Kurs).",
        ),
        "Başqa təhsil proqramında keçilmiş fənnin nəticəsi (Erasmus+, mübadilə, başqa ali məktəb, yay məktəbi, onlayn "
        "kurs və s.) sənədlə tanınır: tələbə bizim fənndən azad olur (jurnal, davamiyyət limiti və imtahan tələbi ona "
        "aid olmur), transkriptdə tanınmış bal göstərilir. Tanınma səbəblə ləğv edilə bilər; hər addım audit izinə "
        "düşür.": t(
            "The result of a course taken in another study programme (Erasmus+, exchange, another university, summer "
            "school, online course, etc.) is recognised with a document: the student is exempted from our course "
            "(journal, attendance limit and exam requirement no longer apply), and the transcript shows the recognised "
            "score. A recognition can be revoked with a reason; every step is audited.",
            "Результат дисциплины, пройденной в другой образовательной программе (Erasmus+, обмен, другой вуз, летняя "
            "школа, онлайн-курс и т. п.), признаётся по документу: студент освобождается от нашей дисциплины (журнал, "
            "лимит пропусков и требование экзамена на него не распространяются), в транскрипте показывается признанный "
            "балл. Признание можно отменить с указанием причины; каждый шаг попадает в аудит.",
            "Başka bir eğitim programında alınan dersin sonucu (Erasmus+, değişim, başka üniversite, yaz okulu, "
            "çevrimiçi kurs vb.) belgeyle tanınır: öğrenci bizim dersten muaf olur (yoklama defteri, devamsızlık sınırı "
            "ve sınav şartı ona uygulanmaz), transkriptte tanınan puan gösterilir. Tanıma gerekçeyle iptal edilebilir; "
            "her adım denetim kaydına düşer.",
            "Das Ergebnis eines in einem anderen Studienprogramm belegten Fachs (Erasmus+, Austausch, andere "
            "Hochschule, Sommerschule, Online-Kurs usw.) wird mit Nachweis anerkannt: Die/der Studierende wird von "
            "unserem Fach befreit (Journal, Fehlzeitenlimit und Prüfungspflicht entfallen), im Transcript erscheint die "
            "anerkannte Punktzahl. Eine Anerkennung kann mit Begründung widerrufen werden; jeder Schritt wird "
            "protokolliert.",
        ),
        "%(floor)s–100; hərf universitetin şkalasından avtomatik.": t(
            "%(floor)s–100; the letter comes automatically from the university scale.",
            "%(floor)s–100; буква определяется автоматически по шкале университета.",
            "%(floor)s–100; harf üniversitenin ölçeğinden otomatik belirlenir.",
            "%(floor)s–100; der Buchstabe ergibt sich automatisch aus der Skala der Universität.",
        ),
        "%(n)s kredit": t("%(n)s credits", "%(n)s кредитов", "%(n)s kredi", "%(n)s Credits"),
        "(istəyə bağlı)": t("(optional)", "(необязательно)", "(isteğe bağlı)", "(optional)"),
        "Ad, soyad və ya tələbə nömrəsi": t(
            "Name, surname or student number",
            "Имя, фамилия или номер студента",
            "Ad, soyad veya öğrenci numarası",
            "Vorname, Nachname oder Matrikelnummer",
        ),
        "Axtar": t("Search", "Найти", "Ara", "Suchen"),
        "Axtarış nəticəsi": t("Search results", "Результаты поиска", "Arama sonucu", "Suchergebnis"),
        "Axtar…": t("Search…", "Поиск…", "Ara…", "Suchen…"),
        "Azad (xarici nəticə tanınıb)": t(
            "Exempt (external result recognised)",
            "Освобождён (внешний результат признан)",
            "Muaf (dış sonuç tanındı)",
            "Befreit (externe Leistung anerkannt)",
        ),
        "Bağlı azadlıq geri açılır — tələbə fənnin jurnalına qayıdır; transkriptdə yenidən jurnal nəticəsi "
        "göstərilir. Qeyd silinmir, ləğv tarixçədə qalır.": t(
            "The linked exemption is lifted — the student returns to the course journal; the transcript shows the "
            "journal result again. The record is not deleted; the revocation stays in the history.",
            "Связанное освобождение снимается — студент возвращается в журнал дисциплины; в транскрипте снова "
            "показывается результат журнала. Запись не удаляется, отмена остаётся в истории.",
            "Bağlı muafiyet kaldırılır — öğrenci dersin yoklama defterine döner; transkriptte yeniden defter sonucu "
            "gösterilir. Kayıt silinmez, iptal geçmişte kalır.",
            "Die verknüpfte Befreiung wird aufgehoben — die/der Studierende kehrt ins Fachjournal zurück; im "
            "Transcript erscheint wieder das Journalergebnis. Der Eintrag wird nicht gelöscht, der Widerruf bleibt "
            "im Verlauf.",
        ),
        "Başqa ali məktəb": t("Another university", "Другой вуз", "Başka üniversite", "Andere Hochschule"),
        "Başqasının adından baxış rejimində dəyişiklik etmək olmaz.": t(
            "Changes cannot be made while viewing as another user.",
            "В режиме просмотра от имени другого пользователя изменения невозможны.",
            "Başkası adına görüntüleme modunda değişiklik yapılamaz.",
            "Im Modus „Ansicht als andere Person“ sind keine Änderungen möglich.",
        ),
        "Bizim fənn (semestr · fənn)": t(
            "Our course (semester · course)",
            "Наша дисциплина (семестр · дисциплина)",
            "Bizim ders (dönem · ders)",
            "Unser Fach (Semester · Fach)",
        ),
        "Bizim fənni (jurnal qeydiyyatını) seçin.": t(
            "Select our course (journal enrolment).",
            "Выберите нашу дисциплину (запись в журнале).",
            "Bizim dersi (defter kaydını) seçin.",
            "Wählen Sie unser Fach (Journaleinschreibung).",
        ),
        "Bizim şkalada (100 bal)": t(
            "On our scale (100 points)",
            "По нашей шкале (100 баллов)",
            "Bizim ölçekte (100 puan)",
            "Auf unserer Skala (100 Punkte)",
        ),
        "Bizim şkalada qarşılıq %(floor)s–100 arası tam bal olmalıdır (tanınma keçmiş nəticəyədir).": t(
            "The equivalent on our scale must be a whole number between %(floor)s and 100 (only passed results are "
            "recognised).",
            "Эквивалент по нашей шкале должен быть целым числом от %(floor)s до 100 (признаётся только сданный "
            "результат).",
            "Bizim ölçekteki karşılık %(floor)s–100 arası tam puan olmalıdır (yalnız geçilmiş sonuç tanınır).",
            "Der Gegenwert auf unserer Skala muss eine ganze Zahl zwischen %(floor)s und 100 sein (nur bestandene "
            "Leistungen werden anerkannt).",
        ),
        "Bu bölmə dekanlıq, tədris şöbəsi və RİM üçündür.": t(
            "This section is for the dean's office, the academic office and the IT directorate.",
            "Этот раздел предназначен для деканата, учебного отдела и ДИТ.",
            "Bu bölüm dekanlık, eğitim birimi ve BİM içindir.",
            "Dieser Bereich ist für Dekanat, Studienbüro und IT-Leitung bestimmt.",
        ),
        "Bu fənn üzrə bu semestrdə qüvvədə olan tanınma artıq var — əvvəlcə onu ləğv edin.": t(
            "There is already an active recognition for this course in this semester — revoke it first.",
            "По этой дисциплине в этом семестре уже есть действующее признание — сначала отмените его.",
            "Bu ders için bu dönemde geçerli bir tanıma zaten var — önce onu iptal edin.",
            "Für dieses Fach gibt es in diesem Semester bereits eine gültige Anerkennung — widerrufen Sie sie zuerst.",
        ),
        "Bu tanınma artıq ləğv edilib.": t(
            "This recognition has already been revoked.",
            "Это признание уже отменено.",
            "Bu tanıma zaten iptal edildi.",
            "Diese Anerkennung wurde bereits widerrufen.",
        ),
        "Bu tələbə üçün hələ tanınma yoxdur.": t(
            "There are no recognitions for this student yet.",
            "Для этого студента признаний пока нет.",
            "Bu öğrenci için henüz tanıma yok.",
            "Für diese/n Studierende/n gibt es noch keine Anerkennung.",
        ),
        "Digər": t("Other", "Другое", "Diğer", "Sonstiges"),
        "Erasmus+": t("Erasmus+", "Erasmus+", "Erasmus+", "Erasmus+"),
        "Erasmus+, mübadilə proqramı və ya başqa ali məktəbdə keçilmiş fənnin nəticəsi sənədlə tanınır: tələbə "
        "bizim fənndən azad olur (jurnal, davamiyyət limiti və imtahan tələbi ona aid olmur), transkriptdə tanınmış "
        "bal göstərilir. Tanınma səbəblə ləğv edilə bilər; hər addım audit izinə düşür.": t(
            "The result of a course taken through Erasmus+, an exchange programme or at another university is "
            "recognised with a document: the student is exempted from our course (journal, attendance limit and exam "
            "requirement no longer apply), and the transcript shows the recognised score. A recognition can be "
            "revoked with a reason; every step is audited.",
            "Результат дисциплины, пройденной по Erasmus+, программе обмена или в другом вузе, признаётся по "
            "документу: студент освобождается от нашей дисциплины (журнал, лимит пропусков и требование экзамена на "
            "него не распространяются), в транскрипте показывается признанный балл. Признание можно отменить с "
            "указанием причины; каждый шаг попадает в аудит.",
            "Erasmus+, değişim programı veya başka bir üniversitede alınan dersin sonucu belgeyle tanınır: öğrenci "
            "bizim dersten muaf olur (yoklama defteri, devamsızlık sınırı ve sınav şartı ona uygulanmaz), transkriptte "
            "tanınan puan gösterilir. Tanıma gerekçeyle iptal edilebilir; her adım denetim kaydına düşer.",
            "Das Ergebnis eines über Erasmus+, ein Austauschprogramm oder an einer anderen Hochschule belegten Fachs "
            "wird mit Nachweis anerkannt: Die/der Studierende wird von unserem Fach befreit (Journal, Fehlzeitenlimit "
            "und Prüfungspflicht entfallen), im Transcript erscheint die anerkannte Punktzahl. Eine Anerkennung kann "
            "mit Begründung widerrufen werden; jeder Schritt wird protokolliert.",
        ),
        "Hələ tanınma yoxdur. Tələbəni axtarın və «Yeni tanınma» ilə xarici nəticəni əlavə edin.": t(
            "No recognitions yet. Search for a student and add the external result with “New recognition”.",
            "Признаний пока нет. Найдите студента и добавьте внешний результат кнопкой «Новое признание».",
            "Henüz tanıma yok. Öğrenciyi arayın ve «Yeni tanıma» ile dış sonucu ekleyin.",
            "Noch keine Anerkennungen. Suchen Sie die/den Studierende/n und fügen Sie die externe Leistung mit „Neue "
            "Anerkennung“ hinzu.",
        ),
        "Ləğv edilib": t("Revoked", "Отменено", "İptal edildi", "Widerrufen"),
        "Ləğv et": t("Revoke", "Отменить", "İptal et", "Widerrufen"),
        "Ləğvin səbəbini yazın (ən azı %(n)s simvol).": t(
            "Enter the reason for revocation (at least %(n)s characters).",
            "Укажите причину отмены (не менее %(n)s символов).",
            "İptal gerekçesini yazın (en az %(n)s karakter).",
            "Geben Sie den Grund für den Widerruf an (mindestens %(n)s Zeichen).",
        ),
        "Mübadilə proqramı": t("Exchange programme", "Программа обмена", "Değişim programı", "Austauschprogramm"),
        "PDF, JPG və ya PNG · ən çox 10 MB": t(
            "PDF, JPG or PNG · up to 10 MB",
            "PDF, JPG или PNG · не более 10 МБ",
            "PDF, JPG veya PNG · en fazla 10 MB",
            "PDF, JPG oder PNG · höchstens 10 MB",
        ),
        "Proqram": t("Programme", "Программа", "Program", "Programm"),
        "Proqramı seçin.": t(
            "Select the programme.", "Выберите программу.", "Programı seçin.", "Wählen Sie das Programm."
        ),
        "Qeyd": t("Note", "Примечание", "Not", "Notiz"),
        "Qurum": t("Institution", "Учреждение", "Kurum", "Einrichtung"),
        "Qurum (universitet)": t(
            "Institution (university)", "Учреждение (вуз)", "Kurum (üniversite)", "Einrichtung (Hochschule)"
        ),
        "Qüvvədə olan tanınma": t(
            "Active recognitions", "Действующие признания", "Geçerli tanıma", "Gültige Anerkennungen"
        ),
        "Qüvvədə · fəndən azad edilib": t(
            "Active · exempted from the course",
            "Действует · освобождён от дисциплины",
            "Geçerli · dersten muaf tutuldu",
            "Gültig · vom Fach befreit",
        ),
        "Qüvvədə · jurnal bağlı idi (yalnız transkript)": t(
            "Active · journal was closed (transcript only)",
            "Действует · журнал был закрыт (только транскрипт)",
            "Geçerli · defter kapalıydı (yalnız transkript)",
            "Gültig · Journal war geschlossen (nur Transcript)",
        ),
        "Seçin": t("Select", "Выберите", "Seçin", "Auswählen"),
        "Son tanınmalar": t("Recent recognitions", "Последние признания", "Son tanımalar", "Letzte Anerkennungen"),
        "Sənəd": t("Document", "Документ", "Belge", "Dokument"),
        "Tanı və azad et": t(
            "Recognise and exempt", "Признать и освободить", "Tanı ve muaf tut", "Anerkennen und befreien"
        ),
        "Tanınma ləğv edildi — tələbə fənnin jurnalına qaytarıldı.": t(
            "Recognition revoked — the student has been returned to the course journal.",
            "Признание отменено — студент возвращён в журнал дисциплины.",
            "Tanıma iptal edildi — öğrenci dersin defterine geri döndü.",
            "Anerkennung widerrufen — die/der Studierende wurde ins Fachjournal zurückgeführt.",
        ),
        "Tanınma ləğv edildi.": t(
            "Recognition revoked.", "Признание отменено.", "Tanıma iptal edildi.", "Anerkennung widerrufen."
        ),
        "Tanınma tapılmadı.": t(
            "Recognition not found.", "Признание не найдено.", "Tanıma bulunamadı.", "Anerkennung nicht gefunden."
        ),
        "Tanınmanı ləğv et": t(
            "Revoke recognition", "Отменить признание", "Tanımayı iptal et", "Anerkennung widerrufen"
        ),
        "Tanınmış bal": t("Recognised score", "Признанный балл", "Tanınan puan", "Anerkannte Punktzahl"),
        "Təhsil müddəti": t("Study period", "Период обучения", "Öğrenim süresi", "Studienzeitraum"),
        "Təhsil müddəti / semestr": t(
            "Study period / semester",
            "Период обучения / семестр",
            "Öğrenim süresi / dönem",
            "Studienzeitraum / Semester",
        ),
        "Tələbə axtarışı": t("Student search", "Поиск студента", "Öğrenci arama", "Studierendensuche"),
        "Tələbənin tanınma üçün açıq jurnal qeydiyyatı yoxdur (bütün fənlər ya tanınıb, ya da semestr hələ "
        "açılmayıb).": t(
            "The student has no journal enrolment available for recognition (all courses are already recognised or "
            "the semester has not been opened yet).",
            "У студента нет записи в журнале, доступной для признания (все дисциплины уже признаны или семестр ещё "
            "не открыт).",
            "Öğrencinin tanıma için uygun defter kaydı yok (tüm dersler zaten tanındı veya dönem henüz açılmadı).",
            "Für die/den Studierende/n gibt es keine Journaleinschreibung für eine Anerkennung (alle Fächer sind "
            "bereits anerkannt oder das Semester ist noch nicht eröffnet).",
        ),
        "Uyğun nəticə yoxdur": t(
            "No matching results", "Нет совпадений", "Uygun sonuç yok", "Keine passenden Ergebnisse"
        ),
        "Xarici fənn": t("External course", "Внешняя дисциплина", "Dış ders", "Externes Fach"),
        "Xarici fənnin adı": t(
            "External course title", "Название внешней дисциплины", "Dış dersin adı", "Titel des externen Fachs"
        ),
        "Xarici kredit (ECTS)": t(
            "External credits (ECTS)", "Внешние кредиты (ECTS)", "Dış kredi (AKTS)", "Externe Credits (ECTS)"
        ),
        "Xarici kredit / qiymət": t(
            "External credits / grade", "Внешние кредиты / оценка", "Dış kredi / not", "Externe Credits / Note"
        ),
        "Xarici kredit 0-dan böyük rəqəm olmalıdır (ən çox 60).": t(
            "External credits must be a number greater than 0 (at most 60).",
            "Внешние кредиты должны быть числом больше 0 (не более 60).",
            "Dış kredi 0'dan büyük bir sayı olmalıdır (en fazla 60).",
            "Externe Credits müssen eine Zahl größer als 0 sein (höchstens 60).",
        ),
        "Xarici nəticə tanındı — tələbə bu fəndən azad edildi (jurnaldan çıxdı).": t(
            "External result recognised — the student has been exempted from this course (removed from the journal).",
            "Внешний результат признан — студент освобождён от этой дисциплины (исключён из журнала).",
            "Dış sonuç tanındı — öğrenci bu dersten muaf tutuldu (defterden çıkarıldı).",
            "Externe Leistung anerkannt — die/der Studierende wurde von diesem Fach befreit (aus dem Journal "
            "entfernt).",
        ),
        "Xarici nəticə tanındı. Jurnal bağlı olduğundan jurnal sətri dəyişmədi — transkriptdə tanınmış nəticə "
        "göstərilir.": t(
            "External result recognised. The journal is closed, so the journal row did not change — the transcript "
            "shows the recognised result.",
            "Внешний результат признан. Журнал закрыт, поэтому строка журнала не изменилась — в транскрипте "
            "показывается признанный результат.",
            "Dış sonuç tanındı. Defter kapalı olduğundan defter satırı değişmedi — transkriptte tanınan sonuç "
            "gösterilir.",
            "Externe Leistung anerkannt. Das Journal ist geschlossen, daher blieb die Journalzeile unverändert — im "
            "Transcript erscheint das anerkannte Ergebnis.",
        ),
        "Xarici nəticə tanınıb": t(
            "External result recognised", "Внешний результат признан", "Dış sonuç tanındı", "Externe Leistung anerkannt"
        ),
        "Xarici nəticə tanınıb: %(program)s · %(institution)s · %(subject)s": t(
            "External result recognised: %(program)s · %(institution)s · %(subject)s",
            "Внешний результат признан: %(program)s · %(institution)s · %(subject)s",
            "Dış sonuç tanındı: %(program)s · %(institution)s · %(subject)s",
            "Externe Leistung anerkannt: %(program)s · %(institution)s · %(subject)s",
        ),
        "Xarici nəticə tanınıb: %(score)s (%(letter)s)": t(
            "External result recognised: %(score)s (%(letter)s)",
            "Внешний результат признан: %(score)s (%(letter)s)",
            "Dış sonuç tanındı: %(score)s (%(letter)s)",
            "Externe Leistung anerkannt: %(score)s (%(letter)s)",
        ),
        "Xarici nəticəni tanı": t(
            "Recognise external result", "Признать внешний результат", "Dış sonucu tanı", "Externe Leistung anerkennen"
        ),
        "Xarici nəticəni tanımaq üçün səlahiyyətiniz yoxdur.": t(
            "You are not allowed to recognise external results.",
            "У вас нет прав на признание внешних результатов.",
            "Dış sonuçları tanıma yetkiniz yok.",
            "Sie sind nicht berechtigt, externe Leistungen anzuerkennen.",
        ),
        "Xarici nəticənin tanınması ləğv edildi: %(reason)s": t(
            "External result recognition revoked: %(reason)s",
            "Признание внешнего результата отменено: %(reason)s",
            "Dış sonucun tanınması iptal edildi: %(reason)s",
            "Anerkennung externer Leistung widerrufen: %(reason)s",
        ),
        "Xarici qiymət": t("External grade", "Внешняя оценка", "Dış not", "Externe Note"),
        "Yeni tanınma": t("New recognition", "Новое признание", "Yeni tanıma", "Neue Anerkennung"),
        "kredit": t("credits", "кредитов", "kredi", "Credits"),
        "məs. 2025/2026 yaz semestri": t(
            "e.g. 2025/2026 spring semester",
            "напр. весенний семестр 2025/2026",
            "örn. 2025/2026 bahar dönemi",
            "z. B. Sommersemester 2025/2026",
        ),
        "məs. B, 8/10, 1.7": t("e.g. B, 8/10, 1.7", "напр. B, 8/10, 1.7", "örn. B, 8/10, 1.7", "z. B. B, 8/10, 1,7"),
        "qiymət": t("grade", "оценка", "not", "Note"),
        "«%(field)s» doldurulmalıdır.": t(
            "“%(field)s” is required.",
            "Поле «%(field)s» обязательно.",
            "«%(field)s» doldurulmalıdır.",
            "„%(field)s“ ist erforderlich.",
        ),
        "Ölkə": t("Country", "Страна", "Ülke", "Land"),
        "Əhatənizdə uyğun tələbə tapılmadı.": t(
            "No matching student found in your scope.",
            "В вашей зоне ответственности подходящий студент не найден.",
            "Kapsamınızda uygun öğrenci bulunamadı.",
            "In Ihrem Zuständigkeitsbereich wurde keine passende Person gefunden.",
        ),
        "Əməl yerinə yetirilmədi — icazənizi yoxlayın və ya səhifəni yeniləyin.": t(
            "The action failed — check your permissions or reload the page.",
            "Действие не выполнено — проверьте права или обновите страницу.",
            "İşlem gerçekleştirilemedi — yetkinizi kontrol edin veya sayfayı yenileyin.",
            "Aktion fehlgeschlagen — prüfen Sie Ihre Berechtigung oder laden Sie die Seite neu.",
        ),
        "Əsas sənəd (transkript, Learning Agreement və ya əmr)": t(
            "Supporting document (transcript, Learning Agreement or order)",
            "Основной документ (транскрипт, Learning Agreement или приказ)",
            "Esas belge (transkript, Learning Agreement veya karar)",
            "Nachweis (Transcript, Learning Agreement oder Bescheid)",
        ),
        "Əsas sənəd məcburidir. Açıq jurnalda tələbə bu fəndən dərhal azad edilir; bağlı jurnalda yalnız transkript "
        "dəyişir.": t(
            "A supporting document is required. If the journal is open, the student is exempted from this course "
            "immediately; if it is closed, only the transcript changes.",
            "Основной документ обязателен. В открытом журнале студент сразу освобождается от дисциплины; в закрытом "
            "меняется только транскрипт.",
            "Esas belge zorunludur. Açık defterde öğrenci bu dersten hemen muaf tutulur; kapalı defterde yalnız "
            "transkript değişir.",
            "Ein Nachweis ist erforderlich. Bei offenem Journal wird die/der Studierende sofort vom Fach befreit; "
            "bei geschlossenem Journal ändert sich nur das Transcript.",
        ),
        "Əsas sənədi yükləyin (transkript, Learning Agreement və ya əmr) — sənədsiz tanınma olmur.": t(
            "Upload the supporting document (transcript, Learning Agreement or order) — no recognition without a "
            "document.",
            "Загрузите основной документ (транскрипт, Learning Agreement или приказ) — без документа признание "
            "невозможно.",
            "Esas belgeyi yükleyin (transkript, Learning Agreement veya karar) — belgesiz tanıma olmaz.",
            "Laden Sie den Nachweis hoch (Transcript, Learning Agreement oder Bescheid) — ohne Nachweis keine "
            "Anerkennung.",
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
            if lang == "az":
                msgstr = AZ_OVERRIDES.get((ctx, msgid), msgid)
            else:
                msgstr = translations.get(lang) or msgid
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
