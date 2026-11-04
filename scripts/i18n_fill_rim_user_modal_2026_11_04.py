#!/usr/bin/env python3
"""EMSArena i18n — RİM istifadəçi kartı: «Vəzifə və bölmə», «Məzun et», «Arxivə göndər / Arxivdən çıxar» (2026-11-04).

Yalnız ``django`` domeni (Python ``pgettext`` + şablon ``{% trans %}``; kartın JS mətnləri şablondakı JSON blokundan
gəlir). msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə
edir, idempotentdir. Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_rim_user_modal_2026_11_04.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ARCHIVE = {
    "Bunun üçün «Hesabı bloklamaq» (user.block) icazəsi lazımdır.": t(
        "This needs the «Block account» (user.block) permission.",
        "Для этого нужно разрешение «Блокировка учётной записи» (user.block).",
        "Bunun için «Hesabı engelle» (user.block) izni gerekir.",
        "Dafür ist die Berechtigung «Konto sperren» (user.block) nötig.",
    ),
    "İşdən ayrılıb / müqavilə bitib": t(
        "Left the job / contract ended",
        "Уволен(а) / договор истёк",
        "İşten ayrıldı / sözleşme sona erdi",
        "Ausgeschieden / Vertrag beendet",
    ),
    "Aktiv təşkilat konteksti yoxdur.": t(
        "No active organisation context.",
        "Нет контекста активной организации.",
        "Etkin kurum bağlamı yok.",
        "Kein aktiver Organisationskontext.",
    ),
    "Bu hesab sizin idarə sahənizdə deyil.": t(
        "This account is outside your management scope.",
        "Эта учётная запись вне вашей зоны управления.",
        "Bu hesap yönetim alanınızın dışında.",
        "Dieses Konto liegt außerhalb Ihres Verwaltungsbereichs.",
    ),
    "Hesab silinib — əvvəlcə bərpa edin.": t(
        "The account is deleted — restore it first.",
        "Учётная запись удалена — сначала восстановите её.",
        "Hesap silinmiş — önce geri yükleyin.",
        "Das Konto ist gelöscht — stellen Sie es zuerst wieder her.",
    ),
    "Hesab artıq arxivdədir.": t(
        "The account is already archived.",
        "Учётная запись уже в архиве.",
        "Hesap zaten arşivde.",
        "Das Konto ist bereits archiviert.",
    ),
    "Tələbə arxivə «Məzun et» (və ya reyestrdəki xaric) əmri ilə keçir.": t(
        "A student is archived through «Graduate» (or an expulsion order in the registry).",
        "Студент переводится в архив через «Выпустить» (или приказ об отчислении в реестре).",
        "Öğrenci arşive «Mezun et» (veya kayıttaki ilişik kesme) emriyle geçer.",
        "Ein Studierender wird über «Absolvieren» (oder einen Exmatrikulationsbeschluss im Register) archiviert.",
    ),
    "Hesab arxivdə deyil.": t(
        "The account is not archived.",
        "Учётная запись не в архиве.",
        "Hesap arşivde değil.",
        "Das Konto ist nicht archiviert.",
    ),
    "Arxivdə saxlanmış rol izi tapılmadı — rolları «Rol təyinatı»nda təyin edin.": t(
        "No archived role trace was found — assign the roles in «Role assignment».",
        "След архивированных ролей не найден — назначьте роли в «Назначении ролей».",
        "Arşivlenmiş rol izi bulunamadı — rolleri «Rol atama»da atayın.",
        "Keine archivierte Rollenspur gefunden — weisen Sie die Rollen unter «Rollenzuweisung» zu.",
    ),
    "Arxivdən çıxarmaq alınmadı.": t(
        "Could not take the account out of the archive.",
        "Не удалось вывести учётную запись из архива.",
        "Hesap arşivden çıkarılamadı.",
        "Das Konto konnte nicht aus dem Archiv geholt werden.",
    ),
    "Arxivləmə alınmadı.": t(
        "Archiving failed.", "Не удалось архивировать.", "Arşivleme başarısız oldu.", "Archivierung fehlgeschlagen."
    ),
    "Bu hesab təşkilatın son aktiv administratorudur — əvvəlcə başqa admin təyin edin.": t(
        "This is the organisation's last active administrator — assign another admin first.",
        "Это последний активный администратор организации — сначала назначьте другого.",
        "Bu, kurumun son etkin yöneticisi — önce başka bir yönetici atayın.",
        "Dies ist der letzte aktive Administrator der Organisation — ernennen Sie zuerst einen anderen.",
    ),
}

GRADUATION = {
    "Oxuyur": t("Studying", "Обучается", "Okuyor", "Studiert"),
    "Akademik məzuniyyətdə": t("On academic leave", "В академическом отпуске", "Akademik izinde", "Beurlaubt"),
    "Xaric olunub": t("Expelled", "Отчислен(а)", "İlişiği kesildi", "Exmatrikuliert"),
    "Məzun olub": t("Graduated", "Выпускник", "Mezun oldu", "Absolviert"),
    "Məzun əmri üçün «Tələbə hərəkəti» (student.movement) və «Akademik qeyd» icazələri lazımdır.": t(
        "A graduation order needs the «Student movement» (student.movement) and «Academic record» permissions.",
        "Для приказа о выпуске нужны разрешения «Движение студентов» (student.movement) и «Академическая запись».",
        "Mezuniyet emri için «Öğrenci hareketi» (student.movement) ve «Akademik kayıt» izinleri gerekir.",
        "Für einen Absolventenbeschluss sind die Berechtigungen «Studierendenbewegung» (student.movement) und "
        "«Studienakte» nötig.",
    ),
    "Bu hesab sizin idarə sahənizdə deyil.": ARCHIVE["Bu hesab sizin idarə sahənizdə deyil."],
    "Tələbənin sizin əhatənizdə «Oxuyur» statuslu akademik qeydi yoxdur.": t(
        "The student has no «Studying» academic record within your scope.",
        "У студента нет академической записи со статусом «Обучается» в вашей зоне.",
        "Öğrencinin kapsamınızda «Okuyor» durumunda akademik kaydı yok.",
        "Der/die Studierende hat in Ihrem Bereich keine Studienakte mit Status «Studiert».",
    ),
    "Tələbənin sizin əhatənizdə akademik qeydi yoxdur.": t(
        "The student has no academic record within your scope.",
        "У студента нет академической записи в вашей зоне.",
        "Öğrencinin kapsamınızda akademik kaydı yok.",
        "Der/die Studierende hat in Ihrem Bereich keine Studienakte.",
    ),
    "Akademik qeyd tapılmadı.": t(
        "Academic record not found.",
        "Академическая запись не найдена.",
        "Akademik kayıt bulunamadı.",
        "Studienakte nicht gefunden.",
    ),
    "Tələbənin bir neçə aktiv qeydi var — qeydi seçin.": t(
        "The student has several active records — choose one.",
        "У студента несколько активных записей — выберите одну.",
        "Öğrencinin birden fazla etkin kaydı var — birini seçin.",
        "Der/die Studierende hat mehrere aktive Akten — wählen Sie eine aus.",
    ),
    "Tələbə artıq məzun olub. Səhvdirsə, «Tələbə reyestri»ndə bərpa əmri ilə geri qaytarılır.": t(
        "The student has already graduated. If this is a mistake, a reinstatement order in the «Student registry» "
        "reverts it.",
        "Студент уже выпущен. Если это ошибка, приказ о восстановлении в «Реестре студентов» всё вернёт.",
        "Öğrenci zaten mezun oldu. Hata ise «Öğrenci kaydı»ndaki geri alma emriyle geri döner.",
        "Der/die Studierende hat bereits absolviert. Bei einem Fehler macht ein Wiederaufnahmebeschluss im "
        "«Studierendenregister» es rückgängig.",
    ),
    "Yalnız «Oxuyur» statuslu tələbə məzun edilə bilər.": t(
        "Only a student with «Studying» status can graduate.",
        "Выпустить можно только студента со статусом «Обучается».",
        "Yalnızca «Okuyor» durumundaki öğrenci mezun edilebilir.",
        "Nur Studierende mit Status «Studiert» können absolvieren.",
    ),
    "Məzun et": t("Graduate", "Выпустить", "Mezun et", "Absolvieren"),
    "Akademik qeyd «Məzun» statusuna keçir, cari dövrün açıq qeydiyyatları dondurulur və hesabın girişi bağlanır. "
    "Qiymət, jurnal və imtahan tarixçəsi OLDUĞU KİMİ qalır; səhv olarsa «Tələbə reyestri»ndə bərpa əmri ilə geri "
    "qaytarılır.": t(
        "The academic record moves to «Graduated», open enrolments of the current period are frozen and sign-in is "
        "closed. Grades, journal and exam history stay AS THEY ARE; if this is a mistake, a reinstatement order in "
        "the «Student registry» reverts it.",
        "Академическая запись переходит в статус «Выпускник», открытые записи текущего периода замораживаются, "
        "вход закрывается. Оценки, журнал и история экзаменов остаются КАК ЕСТЬ; при ошибке приказ о восстановлении "
        "в «Реестре студентов» всё вернёт.",
        "Akademik kayıt «Mezun» durumuna geçer, mevcut dönemin açık kayıtları dondurulur ve giriş kapatılır. Not, "
        "yoklama defteri ve sınav geçmişi OLDUĞU GİBİ kalır; hata varsa «Öğrenci kaydı»ndaki geri alma emriyle "
        "geri döner.",
        "Die Studienakte wechselt zu «Absolviert», offene Belegungen der laufenden Periode werden eingefroren und die "
        "Anmeldung wird gesperrt. Noten, Journal und Prüfungsverlauf bleiben UNVERÄNDERT; bei einem Fehler macht ein "
        "Wiederaufnahmebeschluss im «Studierendenregister» es rückgängig.",
    ),
    "Akademik qeyd": t("Academic record", "Академическая запись", "Akademik kayıt", "Studienakte"),
    "Əmr nömrəsi": t("Order number", "Номер приказа", "Emir numarası", "Beschlussnummer"),
    "Əmrin tarixi": t("Order date", "Дата приказа", "Emir tarihi", "Beschlussdatum"),
    "Superadmin: əmr nömrəsi boş qalsa avtomatik «SA-…» əmri yazılır.": t(
        "Superadmin: if the order number is left empty, an automatic «SA-…» order is recorded.",
        "Суперадмин: если номер приказа пуст, записывается автоматический приказ «SA-…».",
        "Süper yönetici: emir numarası boş bırakılırsa otomatik «SA-…» emri yazılır.",
        "Superadmin: Bleibt die Beschlussnummer leer, wird automatisch ein «SA-…»-Beschluss erfasst.",
    ),
    "Səbəb (istəyə bağlı)": t(
        "Reason (optional)", "Причина (необязательно)", "Gerekçe (isteğe bağlı)", "Grund (optional)"
    ),
    "Boş qalsa əmrdən yazılır: «Məzun etmə · Əmr № … · tarix»": t(
        "If empty, it is written from the order: «Graduation · Order No … · date»",
        "Если пусто, берётся из приказа: «Выпуск · Приказ № … · дата»",
        "Boş kalırsa emirden yazılır: «Mezuniyet · Emir No … · tarih»",
        "Wenn leer, aus dem Beschluss: «Absolvierung · Beschluss Nr. … · Datum»",
    ),
}

PLACEMENT = {
    "Təyinat və ya bölmə idarə sahənizdə deyil.": t(
        "The assignment or unit is outside your management scope.",
        "Назначение или подразделение вне вашей зоны управления.",
        "Atama veya birim yönetim alanınızın dışında.",
        "Zuweisung oder Einheit liegt außerhalb Ihres Verwaltungsbereichs.",
    ),
    "Bölmə təyini üçün «Rol təyinatı» səlahiyyəti (role.assign) lazımdır.": t(
        "Placing in a unit needs the «Role assignment» authority (role.assign).",
        "Для назначения подразделения нужно полномочие «Назначение ролей» (role.assign).",
        "Birim ataması için «Rol atama» yetkisi (role.assign) gerekir.",
        "Für die Einheitszuordnung ist die Befugnis «Rollenzuweisung» (role.assign) nötig.",
    ),
    "Bu vəzifənin bölməsi «Rol təyinatı» bölməsində dəyişdirilir.": t(
        "The unit of this position is changed in the «Role assignment» section.",
        "Подразделение этой должности меняется в разделе «Назначение ролей».",
        "Bu görevin birimi «Rol atama» bölümünde değiştirilir.",
        "Die Einheit dieser Funktion wird im Bereich «Rollenzuweisung» geändert.",
    ),
    "Siyahıdan bölmə seçin.": t(
        "Choose a unit from the list.",
        "Выберите подразделение из списка.",
        "Listeden bir birim seçin.",
        "Wählen Sie eine Einheit aus der Liste.",
    ),
    "Təyinat bu arada dəyişib. Kartı yenidən açın.": t(
        "The assignment changed in the meantime. Reopen the card.",
        "Назначение тем временем изменилось. Откройте карточку заново.",
        "Atama bu arada değişti. Kartı yeniden açın.",
        "Die Zuweisung hat sich inzwischen geändert. Öffnen Sie die Karte erneut.",
    ),
    "Cari bölmə sizin icazə əhatənizdən kənardadır.": t(
        "The current unit is outside your permission scope.",
        "Текущее подразделение вне вашей зоны полномочий.",
        "Mevcut birim izin kapsamınızın dışında.",
        "Die aktuelle Einheit liegt außerhalb Ihres Berechtigungsbereichs.",
    ),
    "Əhatənizdə seçilə bilən bölmə yoxdur.": t(
        "There is no selectable unit within your scope.",
        "В вашей зоне нет доступных подразделений.",
        "Kapsamınızda seçilebilir birim yok.",
        "In Ihrem Bereich gibt es keine auswählbare Einheit.",
    ),
}

POSITION = {
    "Assistent": t("Assistant", "Ассистент", "Asistan", "Assistent/in"),
    "Müəllim": t("Lecturer", "Преподаватель", "Öğretim görevlisi", "Lehrkraft"),
    "Baş müəllim": t("Senior lecturer", "Старший преподаватель", "Kıdemli öğretim görevlisi", "Oberlehrkraft"),
    "Dosent": t("Associate professor", "Доцент", "Doçent", "Dozent/in"),
    "Professor": t("Full professor", "Профессор", "Profesör", "Professor/in"),
    "Kafedra müdiri": t("Head of department", "Заведующий кафедрой", "Bölüm başkanı", "Lehrstuhlleiter/in"),
    "Dekan": t("Dean", "Декан", "Fakülte dekanı", "Dekan/in"),
    "Dekan müavini": t("Deputy dean", "Заместитель декана", "Dekan yardımcısı", "Prodekan/in"),
    "Rektor": t("Rector", "Ректор", "Rektör", "Rektor/in"),
    "Prorektor": t("Vice-rector", "Проректор", "Rektör yardımcısı", "Prorektor/in"),
    "Tyutor": t("Tutor", "Тьютор", "Danışman (tutor)", "Tutor/in"),
    "Metodist": t("Methodologist", "Методист", "Eğitim metodoloğu", "Methodiker/in"),
    "Laborant": t("Laboratory assistant", "Лаборант", "Laboratuvar görevlisi", "Laborant/in"),
    "Baş laborant": t("Senior laboratory assistant", "Старший лаборант", "Kıdemli laborant", "Oberlaborant/in"),
    "Şöbə müdiri": t("Head of office", "Начальник отдела", "Şube müdürü", "Abteilungsleiter/in"),
    "Şöbə müdirinin müavini": t(
        "Deputy head of office", "Заместитель начальника отдела", "Şube müdür yardımcısı", "Stellv. Abteilungsleiter/in"
    ),
    "Sektor müdiri": t("Head of sector", "Заведующий сектором", "Sektör müdürü", "Sektorleiter/in"),
    "Mərkəz direktoru": t("Centre director", "Директор центра", "Merkez müdürü", "Zentrumsleiter/in"),
    "Baş mütəxəssis": t("Chief specialist", "Главный специалист", "Baş uzman", "Leitende/r Fachreferent/in"),
    "Aparıcı mütəxəssis": t("Leading specialist", "Ведущий специалист", "Kıdemli uzman", "Erste/r Fachreferent/in"),
    "Mütəxəssis": t("Specialist", "Специалист", "Uzman", "Fachreferent/in"),
    "Baş mühasib": t("Chief accountant", "Главный бухгалтер", "Baş muhasebeci", "Hauptbuchhalter/in"),
    "Mühasib": t("Accountant", "Бухгалтер", "Muhasebeci", "Buchhalter/in"),
    "Hüquqşünas": t("Lawyer", "Юрист", "Hukukçu", "Jurist/in"),
    "Psixoloq": t("Psychologist", "Психолог", "Psikolog", "Psychologe/Psychologin"),
    "Kitabxanaçı": t("Librarian", "Библиотекарь", "Kütüphaneci", "Bibliothekar/in"),
    "Kargüzar": t("Clerk", "Делопроизводитель", "Evrak memuru", "Sachbearbeiter/in"),
    "Katib": t("Secretary", "Секретарь", "Sekreter", "Sekretär/in"),
    "Operator": t("Data-entry operator", "Оператор", "Operatör", "Operator/in"),
    "Proqramçı": t("Programmer", "Программист", "Programcı", "Programmierer/in"),
    "Sistem inzibatçısı": t(
        "System administrator", "Системный администратор", "Sistem yöneticisi", "Systemadministrator/in"
    ),
}

MODAL = {
    "Məlumatlar yeniləndi.": t("Details updated.", "Данные обновлены.", "Bilgiler güncellendi.", "Daten aktualisiert."),
    "Dəyişiklik yoxdur.": t("No changes.", "Без изменений.", "Değişiklik yok.", "Keine Änderungen."),
    "Tələbə məzun edildi — hesab arxivə keçdi, tarixçə saxlanıldı.": t(
        "The student has graduated — the account is archived, history is kept.",
        "Студент выпущен — учётная запись в архиве, история сохранена.",
        "Öğrenci mezun edildi — hesap arşive geçti, geçmiş korundu.",
        "Der/die Studierende hat absolviert — das Konto ist archiviert, der Verlauf bleibt erhalten.",
    ),
    "Hesab arxivdən çıxarıldı: giriş açıldı, %(count)d rol bərpa olundu.": t(
        "The account is out of the archive: sign-in reopened, %(count)d role(s) restored.",
        "Учётная запись выведена из архива: вход открыт, восстановлено ролей: %(count)d.",
        "Hesap arşivden çıkarıldı: giriş açıldı, %(count)d rol geri yüklendi.",
        "Das Konto ist aus dem Archiv geholt: Anmeldung wieder offen, %(count)d Rolle(n) wiederhergestellt.",
    ),
    "Dəyişiklik yoxdur — bu bölmə artıq təyin olunub.": t(
        "No change — this unit is already assigned.",
        "Без изменений — это подразделение уже назначено.",
        "Değişiklik yok — bu birim zaten atanmış.",
        "Keine Änderung — diese Einheit ist bereits zugewiesen.",
    ),
    "Hesab arxivə göndərildi: giriş bağlandı, %(count)d rol deaktiv edildi. Tarixçə saxlanıldı.": t(
        "The account was archived: sign-in closed, %(count)d role(s) deactivated. History is kept.",
        "Учётная запись отправлена в архив: вход закрыт, деактивировано ролей: %(count)d. История сохранена.",
        "Hesap arşive gönderildi: giriş kapatıldı, %(count)d rol devre dışı bırakıldı. Geçmiş korundu.",
        "Das Konto wurde archiviert: Anmeldung gesperrt, %(count)d Rolle(n) deaktiviert. Der Verlauf bleibt erhalten.",
    ),
    "Bölmə təyin edildi: %(unit)s.": t(
        "Unit assigned: %(unit)s.",
        "Подразделение назначено: %(unit)s.",
        "Birim atandı: %(unit)s.",
        "Einheit zugewiesen: %(unit)s.",
    ),
    "Əsas məlumatlar": t("Basic details", "Основные данные", "Temel bilgiler", "Stammdaten"),
    "Vəzifə və bölmə": t("Position and unit", "Должность и подразделение", "Görev ve birim", "Funktion und Einheit"),
    "Akademik vəziyyət": t("Academic status", "Академический статус", "Akademik durum", "Studienstatus"),
    "Status və təhlükəsizlik": t(
        "Status and security", "Статус и безопасность", "Durum ve güvenlik", "Status und Sicherheit"
    ),
    "Yadda saxlanmamış dəyişiklik var": t(
        "There are unsaved changes",
        "Есть несохранённые изменения",
        "Kaydedilmemiş değişiklikler var",
        "Es gibt ungespeicherte Änderungen",
    ),
    "Axtar…": t("Search…", "Поиск…", "Ara…", "Suchen…"),
    "Uyğun nəticə yoxdur": t(
        "No matching results", "Нет подходящих результатов", "Eşleşen sonuç yok", "Keine passenden Ergebnisse"
    ),
    "Təyin edilməyib": t("Not assigned", "Не назначено", "Atanmadı", "Nicht zugewiesen"),
    "Digər (əl ilə yazın)": t(
        "Other (type it in)", "Другое (ввести вручную)", "Diğer (elle yazın)", "Andere (manuell eingeben)"
    ),
    "Vəzifənin adını yazın": t(
        "Type the position name", "Введите название должности", "Görev adını yazın", "Funktionsbezeichnung eingeben"
    ),
    "cari dəyər": t("current value", "текущее значение", "mevcut değer", "aktueller Wert"),
    "Fakültə və kafedra": t(
        "Faculty and department", "Факультет и кафедра", "Fakülte ve bölüm", "Fakultät und Lehrstuhl"
    ),
    "Bu hesabın müəllim və ya əməkdaş rolu yoxdur — əvvəlcə «Rol təyinatı»nda rol verin.": t(
        "This account has no teacher or staff role — grant one in «Role assignment» first.",
        "У этой учётной записи нет роли преподавателя или сотрудника — сначала назначьте её в «Назначении ролей».",
        "Bu hesabın öğretim elemanı veya personel rolü yok — önce «Rol atama»da rol verin.",
        "Dieses Konto hat keine Lehr- oder Mitarbeiterrolle — vergeben Sie zuerst eine unter «Rollenzuweisung».",
    ),
    "Müəllim kafedraya bağlananda həmin kafedranın dərs yükü və müəllim siyahılarına düşür.": t(
        "Once linked to a department, the teacher appears in that department's workload and teacher lists.",
        "После привязки к кафедре преподаватель попадает в её списки нагрузки и преподавателей.",
        "Bölüme bağlanan öğretim elemanı o bölümün ders yükü ve öğretim elemanı listelerine girer.",
        "Mit der Zuordnung zum Lehrstuhl erscheint die Lehrkraft in dessen Lehrdeputats- und Lehrkräftelisten.",
    ),
    "Bölmə təyin edilməyib": t(
        "No unit assigned", "Подразделение не назначено", "Birim atanmadı", "Keine Einheit zugewiesen"
    ),
    "Fakültə": t("Faculty", "Факультет", "Fakülte", "Fakultät"),
    "Bütün fakültələr": t("All faculties", "Все факультеты", "Tüm fakülteler", "Alle Fakultäten"),
    "Kafedra / bölmə": t("Department / unit", "Кафедра / подразделение", "Bölüm / birim", "Lehrstuhl / Einheit"),
    "Kafedra və ya bölmə seçin": t(
        "Choose a department or unit",
        "Выберите кафедру или подразделение",
        "Bölüm veya birim seçin",
        "Lehrstuhl oder Einheit wählen",
    ),
    "Bölməni saxla": t("Save unit", "Сохранить подразделение", "Birimi kaydet", "Einheit speichern"),
    "Akademik qeyd": GRADUATION["Akademik qeyd"],
    "Akademik qeyd tapılmadı.": GRADUATION["Akademik qeyd tapılmadı."],
    "Arxiv (işdən ayrılıb)": t(
        "Archive (left the job)", "Архив (уволен)", "Arşiv (işten ayrıldı)", "Archiv (ausgeschieden)"
    ),
    "Hesab arxivdədir (işdən ayrılıb): giriş bağlıdır, rolları deaktivdir — siyahılarda görünmür. Tarixçə saxlanılır.": t(
        "The account is archived (left the job): sign-in is closed, roles are inactive — it does not appear in lists. "
        "History is kept.",
        "Учётная запись в архиве (уволен): вход закрыт, роли неактивны — в списках не отображается. История сохранена.",
        "Hesap arşivde (işten ayrıldı): giriş kapalı, roller devre dışı — listelerde görünmez. Geçmiş korunur.",
        "Das Konto ist archiviert (ausgeschieden): Anmeldung gesperrt, Rollen inaktiv — erscheint in keinen Listen. "
        "Der Verlauf bleibt erhalten.",
    ),
    "Arxivə göndər": t("Send to archive", "Отправить в архив", "Arşive gönder", "Archivieren"),
    "Arxivdən çıxar": t("Take out of archive", "Вывести из архива", "Arşivden çıkar", "Aus dem Archiv holen"),
    "Birdəfəlik müvəqqəti parol yaradır; istifadəçi ilk girişdə öz parolunu qurur.": t(
        "Creates a one-time temporary password; the user sets their own at first sign-in.",
        "Создаёт одноразовый временный пароль; пользователь задаёт свой при первом входе.",
        "Tek kullanımlık geçici parola oluşturur; kullanıcı ilk girişte kendi parolasını belirler.",
        "Erstellt ein einmaliges temporäres Passwort; der/die Nutzer/in legt beim ersten Login ein eigenes fest.",
    ),
    "Girişi müvəqqəti bağlayır. Məlumatlar və rollar saxlanılır.": t(
        "Temporarily closes sign-in. Data and roles are kept.",
        "Временно закрывает вход. Данные и роли сохраняются.",
        "Girişi geçici olarak kapatır. Veriler ve roller korunur.",
        "Sperrt die Anmeldung vorübergehend. Daten und Rollen bleiben erhalten.",
    ),
    "Girişi yenidən açır.": t(
        "Reopens sign-in.", "Снова открывает вход.", "Girişi yeniden açar.", "Öffnet die Anmeldung wieder."
    ),
    "Əmr nömrəsi və tarixi ilə: akademik qeyd «Məzun» olur, giriş bağlanır, tarixçə qalır.": t(
        "With an order number and date: the academic record becomes «Graduated», sign-in closes, history stays.",
        "С номером и датой приказа: академическая запись становится «Выпускник», вход закрывается, история остаётся.",
        "Emir numarası ve tarihiyle: akademik kayıt «Mezun» olur, giriş kapanır, geçmiş kalır.",
        "Mit Beschlussnummer und -datum: Die Studienakte wird «Absolviert», die Anmeldung gesperrt, der Verlauf bleibt.",
    ),
    "İşdən ayrılıb: giriş bağlanır, rollar deaktiv olur — dərs yükü və müəllim siyahılarından çıxır. Tarixçə qalır.": t(
        "Left the job: sign-in closes, roles are deactivated — removed from workload and teacher lists. History stays.",
        "Уволен(а): вход закрывается, роли деактивируются — исчезает из списков нагрузки и преподавателей. История "
        "остаётся.",
        "İşten ayrıldı: giriş kapanır, roller devre dışı kalır — ders yükü ve öğretim elemanı listelerinden çıkar. "
        "Geçmiş kalır.",
        "Ausgeschieden: Anmeldung gesperrt, Rollen deaktiviert — verschwindet aus Lehrdeputats- und Lehrkräftelisten. "
        "Der Verlauf bleibt.",
    ),
    "Giriş açılır və arxivləmədə deaktiv edilmiş rollar geri qayıdır.": t(
        "Sign-in reopens and the roles deactivated at archiving come back.",
        "Вход открывается, роли, деактивированные при архивировании, возвращаются.",
        "Giriş açılır ve arşivlemede devre dışı bırakılan roller geri gelir.",
        "Die Anmeldung wird geöffnet und die beim Archivieren deaktivierten Rollen kehren zurück.",
    ),
    "Səhvən arxivlənmiş, hələ oxuyan tələbənin girişini açır.": t(
        "Reopens sign-in for a still-studying student who was archived by mistake.",
        "Открывает вход ошибочно архивированному, но ещё обучающемуся студенту.",
        "Yanlışlıkla arşivlenmiş, hâlâ okuyan öğrencinin girişini açar.",
        "Öffnet die Anmeldung für versehentlich archivierte, noch studierende Personen.",
    ),
    "Hesabı siyahılardan çıxarır (yumşaq silmə). Qiymət və jurnal yazıları qalır, bərpa mümkündür.": t(
        "Removes the account from lists (soft delete). Grades and journal entries stay; it can be restored.",
        "Убирает учётную запись из списков (мягкое удаление). Оценки и записи журнала остаются, восстановление возможно.",
        "Hesabı listelerden kaldırır (yumuşak silme). Notlar ve defter kayıtları kalır, geri yüklenebilir.",
        "Entfernt das Konto aus den Listen (Soft-Delete). Noten und Journaleinträge bleiben; Wiederherstellung möglich.",
    ),
    "Silinmiş hesabı və onun rollarını geri qaytarır.": t(
        "Brings back a deleted account and its roles.",
        "Возвращает удалённую учётную запись и её роли.",
        "Silinmiş hesabı ve rollerini geri getirir.",
        "Stellt ein gelöschtes Konto samt Rollen wieder her.",
    ),
    "Bu hesab üçün əlçatan əməliyyat yoxdur.": t(
        "No actions are available for this account.",
        "Для этой учётной записи нет доступных действий.",
        "Bu hesap için kullanılabilir işlem yok.",
        "Für dieses Konto sind keine Aktionen verfügbar.",
    ),
    "Hesab arxivə göndəriləcək: giriş bağlanacaq, bu təşkilatdakı rollar deaktiv olacaq və şəxs dərs yükü / müəllim "
    "siyahılarından çıxacaq. Jurnal, qiymət və yük tarixçəsi silinmir; «Arxivdən çıxar» hər şeyi geri qaytarır.": t(
        "The account will be archived: sign-in closes, roles in this organisation are deactivated and the person "
        "leaves the workload / teacher lists. Journal, grade and workload history is not deleted; «Take out of "
        "archive» brings everything back.",
        "Учётная запись будет отправлена в архив: вход закроется, роли в этой организации будут деактивированы, "
        "человек исчезнет из списков нагрузки / преподавателей. История журнала, оценок и нагрузки не удаляется; "
        "«Вывести из архива» всё вернёт.",
        "Hesap arşive gönderilecek: giriş kapanacak, bu kurumdaki roller devre dışı kalacak ve kişi ders yükü / "
        "öğretim elemanı listelerinden çıkacak. Defter, not ve yük geçmişi silinmez; «Arşivden çıkar» her şeyi geri "
        "getirir.",
        "Das Konto wird archiviert: Die Anmeldung wird gesperrt, die Rollen in dieser Organisation werden deaktiviert "
        "und die Person verschwindet aus den Lehrdeputats- / Lehrkräftelisten. Journal-, Noten- und Deputatsverlauf "
        "wird nicht gelöscht; «Aus dem Archiv holen» stellt alles wieder her.",
    ),
    "Hesab arxivdən çıxarılacaq: giriş açılacaq və arxivləmədə deaktiv edilmiş rollar geri qayıdacaq.": t(
        "The account will be taken out of the archive: sign-in reopens and the roles deactivated at archiving return.",
        "Учётная запись будет выведена из архива: вход откроется, роли, деактивированные при архивировании, вернутся.",
        "Hesap arşivden çıkarılacak: giriş açılacak ve arşivlemede devre dışı bırakılan roller geri gelecek.",
        "Das Konto wird aus dem Archiv geholt: Die Anmeldung wird geöffnet und die beim Archivieren deaktivierten "
        "Rollen kehren zurück.",
    ),
    "Deaktiv ediləcək rollar:": t(
        "Roles to be deactivated:",
        "Роли, которые будут деактивированы:",
        "Devre dışı bırakılacak roller:",
        "Zu deaktivierende Rollen:",
    ),
    "Bərpa olunacaq rollar:": t(
        "Roles to be restored:",
        "Роли, которые будут восстановлены:",
        "Geri yüklenecek roller:",
        "Wiederherzustellende Rollen:",
    ),
    "Səbəb": t("Reason", "Причина", "Gerekçe", "Grund"),
    "Səbəb (istəyə bağlı)": GRADUATION["Səbəb (istəyə bağlı)"],
    "İstifadəçi adı ən azı 3 simvol olmalı və boşluq olmamalıdır.": t(
        "The username must be at least 3 characters with no spaces.",
        "Имя пользователя — не менее 3 символов и без пробелов.",
        "Kullanıcı adı en az 3 karakter olmalı ve boşluk içermemelidir.",
        "Der Benutzername muss mindestens 3 Zeichen lang sein und darf keine Leerzeichen enthalten.",
    ),
    "Email ünvanı düzgün deyil.": t(
        "The email address is not valid.",
        "Неверный адрес эл. почты.",
        "E-posta adresi geçersiz.",
        "Die E-Mail-Adresse ist ungültig.",
    ),
    "FİN 7 simvol olmalıdır (yalnız hərf və rəqəm).": t(
        "The FIN must be 7 characters (letters and digits only).",
        "ФИН должен состоять из 7 символов (только буквы и цифры).",
        "FİN 7 karakter olmalıdır (yalnızca harf ve rakam).",
        "Die FIN muss 7 Zeichen haben (nur Buchstaben und Ziffern).",
    ),
    "Əmr nömrəsi və tarixi məcburidir.": t(
        "The order number and date are required.",
        "Номер и дата приказа обязательны.",
        "Emir numarası ve tarihi zorunludur.",
        "Beschlussnummer und -datum sind Pflicht.",
    ),
}

ENTRIES = {
    "accounts.rim.archive": ARCHIVE,
    "accounts.rim.graduation": GRADUATION,
    "accounts.rim.placement": PLACEMENT,
    "accounts.rim.position": POSITION,
    "accounts.rim.modal": MODAL,
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else translations[lang]
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/django: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
