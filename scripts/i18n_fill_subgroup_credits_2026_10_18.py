#!/usr/bin/env python3
"""EMSArena i18n — semestr kredit yükü + «Alt qrupa tələbə əlavə et» aləti (sahib 2026-10-18).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
Hər dəyər: (en, ru, tr, de).
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]
ORDER = ("en", "ru", "tr", "de")

ENTRIES = {
    "core.runtime_settings": {
        "Kredit yükü və alt qrup": (
            "Credit load and subgroups", "Кредитная нагрузка и подгруппы", "Kredi yükü ve alt grup",
            "Kreditlast und Untergruppen",
        ),
        "Semestrdə maksimum kredit": (
            "Maximum credits per semester", "Максимум кредитов за семестр", "Dönem başına azami kredi",
            "Maximale Credits pro Semester",
        ),
        "Tələbənin bir semestrdə daşıya biləcəyi adi kredit yükü (öz qrupunun fənləri). Kabinetdə «Bu semestr: "
        "27 / 30 kredit» kimi göstərilir. Tədris planı bu həddi keçirsə də öz fənləri bloklanmır — yalnız "
        "xəbərdarlıq görünür.": (
            "The regular credit load a student may carry in one semester (their own group's subjects). Shown in the "
            "cabinet as “This semester: 27 / 30 credits”. If the curriculum exceeds this limit, the student's own "
            "subjects are not blocked — only a warning is shown.",
            "Обычная кредитная нагрузка студента за семестр (предметы его группы). В кабинете отображается как "
            "«Этот семестр: 27 / 30 кредитов». Если учебный план превышает предел, собственные предметы не "
            "блокируются — показывается только предупреждение.",
            "Öğrencinin bir dönemde taşıyabileceği olağan kredi yükü (kendi grubunun dersleri). Kabinette «Bu dönem: "
            "27 / 30 kredi» olarak gösterilir. Öğretim planı bu sınırı aşsa da kendi dersleri engellenmez — yalnızca "
            "uyarı görünür.",
            "Die reguläre Kreditlast, die ein Studierender in einem Semester tragen kann (Fächer der eigenen Gruppe). "
            "Im Kabinett als „Dieses Semester: 27 / 30 Credits“ angezeigt. Überschreitet der Studienplan das Limit, "
            "werden die eigenen Fächer nicht gesperrt — es erscheint nur eine Warnung.",
        ),
        "Alt qrupla birlikdə maksimum kredit": (
            "Maximum credits including subgroups", "Максимум кредитов вместе с подгруппами",
            "Alt grupla birlikte azami kredi", "Maximale Credits einschließlich Untergruppen",
        ),
        "Tələbə alt qrupa (başqa qrupun jurnalına) yerləşdiriləndə öz fənləri + alt qrup fənləri birlikdə bu "
        "həddi keçə bilməz — keçərsə yerləşdirmə edilmir. 0 — ayrıca hədd yoxdur, «Semestrdə maksimum "
        "kredit» tətbiq olunur.": (
            "When a student is placed in a subgroup (another group's journal), their own subjects plus subgroup "
            "subjects together may not exceed this limit — otherwise the placement is refused. 0 — no separate "
            "limit, “Maximum credits per semester” applies.",
            "При размещении студента в подгруппе (журнале другой группы) собственные предметы и предметы подгруппы "
            "вместе не могут превышать этот предел — иначе размещение отклоняется. 0 — отдельного предела нет, "
            "действует «Максимум кредитов за семестр».",
            "Öğrenci alt gruba (başka grubun yoklama defterine) yerleştirildiğinde kendi dersleri ile alt grup dersleri "
            "birlikte bu sınırı aşamaz — aşarsa yerleştirme yapılmaz. 0 — ayrı sınır yok, «Dönem başına azami kredi» "
            "uygulanır.",
            "Wird ein Studierender in eine Untergruppe (Journal einer anderen Gruppe) eingeteilt, dürfen eigene Fächer "
            "und Untergruppenfächer zusammen dieses Limit nicht überschreiten — sonst wird die Einteilung abgelehnt. "
            "0 — kein eigenes Limit, es gilt „Maximale Credits pro Semester“.",
        ),
        "Cədvəl toqquşması yerləşdirməni bloklasın": (
            "Timetable clash blocks the placement", "Конфликт расписания блокирует размещение",
            "Ders programı çakışması yerleştirmeyi engellesin", "Stundenplankonflikt blockiert die Einteilung",
        ),
        "Söndürülübsə alt qrupun dərs saatı tələbənin öz cədvəli ilə üst-üstə düşəndə yalnız xəbərdarlıq "
        "göstərilir və işçi bunu təsdiqləyib davam edə bilər. Yandırılıbsa toqquşan yerləşdirmə edilmir.": (
            "When off, a subgroup class that overlaps the student's own timetable only shows a warning, and staff "
            "may confirm and continue. When on, a clashing placement is refused.",
            "Если выключено, при пересечении занятий подгруппы с собственным расписанием студента показывается "
            "только предупреждение, и сотрудник может подтвердить и продолжить. Если включено, конфликтное "
            "размещение не выполняется.",
            "Kapalıysa alt grubun ders saati öğrencinin kendi programıyla çakıştığında yalnızca uyarı gösterilir ve "
            "personel onaylayıp devam edebilir. Açıksa çakışan yerleştirme yapılmaz.",
            "Ausgeschaltet: Überschneidet sich eine Untergruppenstunde mit dem eigenen Stundenplan, erscheint nur "
            "eine Warnung, und das Personal kann bestätigen und fortfahren. Eingeschaltet: Eine kollidierende "
            "Einteilung wird abgelehnt.",
        ),
        "Bir jurnalda maksimum tələbə": (
            "Maximum students per journal", "Максимум студентов в журнале", "Bir defterde azami öğrenci",
            "Maximale Studierende pro Journal",
        ),
        "Alt qrup yerləşdirməsində hədəf jurnalın tutumu: jurnalda bu qədər aktiv tələbə varsa yeni tələbə "
        "əlavə olunmur. 0 — tutum həddi yoxdur.": (
            "Capacity of the target journal for subgroup placements: if the journal already has this many active "
            "students, no new student is added. 0 — no capacity limit.",
            "Вместимость целевого журнала при размещении в подгруппе: если в журнале уже столько активных "
            "студентов, новый студент не добавляется. 0 — без ограничения.",
            "Alt grup yerleştirmesinde hedef defterin kapasitesi: defterde bu kadar aktif öğrenci varsa yeni öğrenci "
            "eklenmez. 0 — kapasite sınırı yok.",
            "Kapazität des Zieljournals bei Untergruppen-Einteilungen: Hat das Journal bereits so viele aktive "
            "Studierende, wird niemand mehr hinzugefügt. 0 — keine Kapazitätsgrenze.",
        ),
        "kredit": ("credits", "кредитов", "kredi", "Credits"),
        "tələbə": ("students", "студентов", "öğrenci", "Studierende"),
    },
    "registrar.model.subgroup_placement": {
        "Alt qrupa yerləşdirildi": (
            "Placed in a subgroup", "Размещён в подгруппе", "Alt gruba yerleştirildi", "In Untergruppe eingeteilt",
        ),
        "Yerləşdirmə geri götürüldü": (
            "Placement withdrawn", "Размещение отменено", "Yerleştirme geri alındı", "Einteilung zurückgenommen",
        ),
        "subgroup placement event": (
            "subgroup placement event", "событие размещения в подгруппе", "alt grup yerleştirme kaydı",
            "Untergruppen-Einteilungsereignis",
        ),
        "subgroup placement events": (
            "subgroup placement events", "события размещения в подгруппе", "alt grup yerleştirme kayıtları",
            "Untergruppen-Einteilungsereignisse",
        ),
    },
    "registrar.subgroup_placement": {
        "%(student)s alt qrupdan jurnalınıza əlavə olundu (öz qrupu: %(source)s).": (
            "%(student)s was added to your journal from a subgroup (own group: %(source)s).",
            "%(student)s добавлен(а) в ваш журнал из подгруппы (своя группа: %(source)s).",
            "%(student)s alt gruptan defterinize eklendi (kendi grubu: %(source)s).",
            "%(student)s wurde aus einer Untergruppe in Ihr Journal aufgenommen (eigene Gruppe: %(source)s).",
        ),
        "%(student)s jurnaldan çıxarıldı (alt qrup yerləşdirməsi geri götürüldü).": (
            "%(student)s was removed from the journal (subgroup placement withdrawn).",
            "%(student)s исключён(а) из журнала (размещение в подгруппе отменено).",
            "%(student)s defterden çıkarıldı (alt grup yerleştirmesi geri alındı).",
            "%(student)s wurde aus dem Journal entfernt (Untergruppen-Einteilung zurückgenommen).",
        ),
        "Alt qrup yerləşdirməsi geri götürüldü — %(subject)s": (
            "Subgroup placement withdrawn — %(subject)s", "Размещение в подгруппе отменено — %(subject)s",
            "Alt grup yerleştirmesi geri alındı — %(subject)s", "Untergruppen-Einteilung zurückgenommen — %(subject)s",
        ),
        "Alt qrupa yerləşdirildiniz — %(subject)s": (
            "You have been placed in a subgroup — %(subject)s", "Вы размещены в подгруппе — %(subject)s",
            "Alt gruba yerleştirildiniz — %(subject)s", "Sie wurden einer Untergruppe zugeteilt — %(subject)s",
        ),
        "Alt qrupa yerləşdirmə üçün «retake.manage» səlahiyyəti lazımdır.": (
            "Subgroup placement requires the “retake.manage” permission.",
            "Для размещения в подгруппе нужно право «retake.manage».",
            "Alt gruba yerleştirme için «retake.manage» yetkisi gerekir.",
            "Für die Untergruppen-Einteilung ist die Berechtigung „retake.manage“ erforderlich.",
        ),
        "Alt qrupun dərs saatı tələbənin öz cədvəli ilə üst-üstə düşür.": (
            "The subgroup's class time overlaps the student's own timetable.",
            "Время занятий подгруппы пересекается с собственным расписанием студента.",
            "Alt grubun ders saati öğrencinin kendi programıyla çakışıyor.",
            "Die Unterrichtszeit der Untergruppe überschneidet sich mit dem eigenen Stundenplan.",
        ),
        "Bu jurnal bu semestrdə aktiv deyil.": (
            "This journal is not active this semester.", "Этот журнал не активен в этом семестре.",
            "Bu defter bu dönemde aktif değil.", "Dieses Journal ist in diesem Semester nicht aktiv.",
        ),
        "Bu tələbə sizin struktur əhatənizdə deyil.": (
            "This student is outside your structural scope.", "Этот студент вне вашей структурной зоны.",
            "Bu öğrenci yapısal kapsamınızın dışında.", "Dieser Studierende liegt außerhalb Ihres Zuständigkeitsbereichs.",
        ),
        "Tələbə bu semestrdə bu fəndən azad edilib — əvvəlcə azadolma geri qaytarılmalıdır.": (
            "The student is exempted from this subject this semester — the exemption must be reverted first.",
            "Студент освобождён от этого предмета в этом семестре — сначала нужно отменить освобождение.",
            "Öğrenci bu dönem bu dersten muaf tutuldu — önce muafiyet geri alınmalıdır.",
            "Der Studierende ist in diesem Semester von diesem Fach befreit — zuerst muss die Befreiung aufgehoben werden.",
        ),
        "Bu qeydiyyat sonradan yenidən yerləşdirilib — yalnız ən son yerləşdirmə geri götürülə bilər.": (
            "This enrolment was placed again later — only the latest placement can be withdrawn.",
            "Эта запись позже была размещена повторно — отменить можно только последнее размещение.",
            "Bu kayıt daha sonra yeniden yerleştirildi — yalnızca en son yerleştirme geri alınabilir.",
            "Diese Einschreibung wurde später erneut eingeteilt — nur die letzte Einteilung kann zurückgenommen werden.",
        ),
        "Jurnal modalından əlavə": (
            "Added from the journal dialog", "Добавлено из окна журнала", "Defter penceresinden eklendi",
            "Aus dem Journaldialog hinzugefügt",
        ),
        "Bu yerləşdirmə artıq geri götürülüb.": (
            "This placement has already been withdrawn.", "Это размещение уже отменено.",
            "Bu yerleştirme zaten geri alındı.", "Diese Einteilung wurde bereits zurückgenommen.",
        ),
        "Bu, tələbənin öz qrupunun jurnalıdır — alt qrup yerləşdirməsi tələb olunmur.": (
            "This is the student's own group journal — no subgroup placement is needed.",
            "Это журнал собственной группы студента — размещение в подгруппе не требуется.",
            "Bu, öğrencinin kendi grubunun defteri — alt grup yerleştirmesi gerekmez.",
            "Dies ist das Journal der eigenen Gruppe — keine Untergruppen-Einteilung nötig.",
        ),
        "Jurnal siyahısı dəyişdi — %(subject)s · %(group)s": (
            "Journal roster changed — %(subject)s · %(group)s", "Состав журнала изменён — %(subject)s · %(group)s",
            "Defter listesi değişti — %(subject)s · %(group)s", "Journalliste geändert — %(subject)s · %(group)s",
        ),
        "Jurnalda boş yer yoxdur (tutum həddi dolub).": (
            "The journal has no free seats (capacity reached).", "В журнале нет свободных мест (лимит заполнен).",
            "Defterde boş yer yok (kapasite doldu).", "Im Journal sind keine Plätze frei (Kapazität erreicht).",
        ),
        "Jurnalın siyahısı bağlıdır — tələbə əlavə edilə bilməz.": (
            "The journal roster is closed — no student can be added.",
            "Состав журнала закрыт — студента добавить нельзя.",
            "Defter listesi kapalı — öğrenci eklenemez.", "Die Journalliste ist geschlossen — niemand kann hinzugefügt werden.",
        ),
        "Semestr kredit həddi keçilir.": (
            "The semester credit limit would be exceeded.", "Превышается семестровый лимит кредитов.",
            "Dönem kredi sınırı aşılıyor.", "Das Semester-Creditlimit würde überschritten.",
        ),
        "Semestr kredit həddi keçilir: yerləşdirmədən sonra %(after)s kredit olacaq, hədd %(limit)s.": (
            "The semester credit limit would be exceeded: after the placement %(after)s credits, limit %(limit)s.",
            "Превышается семестровый лимит: после размещения будет %(after)s кредитов, лимит %(limit)s.",
            "Dönem kredi sınırı aşılıyor: yerleştirmeden sonra %(after)s kredi olacak, sınır %(limit)s.",
            "Das Semester-Creditlimit würde überschritten: nach der Einteilung %(after)s Credits, Limit %(limit)s.",
        ),
        "Siz «%(subject)s» fənni üzrə %(group)s qrupunun jurnalından çıxarıldınız.": (
            "You were removed from the %(group)s journal for “%(subject)s”.",
            "Вы исключены из журнала группы %(group)s по предмету «%(subject)s».",
            "«%(subject)s» dersi için %(group)s grubunun defterinden çıkarıldınız.",
            "Sie wurden aus dem Journal der Gruppe %(group)s für „%(subject)s“ entfernt.",
        ),
        "Səbəb yazılmalıdır (ən azı 10 simvol).": (
            "A reason is required (at least 10 characters).", "Нужно указать причину (не менее 10 символов).",
            "Gerekçe yazılmalıdır (en az 10 karakter).", "Eine Begründung ist erforderlich (mindestens 10 Zeichen).",
        ),
        "Sənəd faylı qəbul edilmədi — yalnız PDF, JPG və PNG (10 MB-a qədər).": (
            "The document file was rejected — PDF, JPG and PNG only (up to 10 MB).",
            "Файл документа не принят — только PDF, JPG и PNG (до 10 МБ).",
            "Belge dosyası kabul edilmedi — yalnızca PDF, JPG ve PNG (10 MB'a kadar).",
            "Die Dokumentdatei wurde abgelehnt — nur PDF, JPG und PNG (bis 10 MB).",
        ),
        "Sənəd məcburidir: təqdimat / sərəncam faylı (PDF, JPG, PNG) yükləyin və ya sərəncamın nömrəsi və tarixini "
        "yazın.": (
            "A document is required: upload the submission / order file (PDF, JPG, PNG) or enter the order number "
            "and date.",
            "Документ обязателен: загрузите файл представления / приказа (PDF, JPG, PNG) или укажите номер и дату "
            "приказа.",
            "Belge zorunludur: teklif / karar dosyasını (PDF, JPG, PNG) yükleyin ya da kararın numarası ve tarihini "
            "yazın.",
            "Ein Dokument ist erforderlich: Antrags-/Anordnungsdatei (PDF, JPG, PNG) hochladen oder Nummer und Datum "
            "der Anordnung eingeben.",
        ),
        "Sərəncam tarixi düzgün deyil.": (
            "The order date is invalid.", "Неверная дата приказа.", "Karar tarihi geçersiz.",
            "Das Datum der Anordnung ist ungültig.",
        ),
        "Sərəncam tarixi gələcəkdə ola bilməz.": (
            "The order date cannot be in the future.", "Дата приказа не может быть в будущем.",
            "Karar tarihi gelecekte olamaz.", "Das Datum der Anordnung darf nicht in der Zukunft liegen.",
        ),
        "Sərəncamın həm nömrəsi, həm tarixi yazılmalıdır.": (
            "Both the order number and date are required.", "Нужно указать и номер, и дату приказа.",
            "Kararın hem numarası hem tarihi yazılmalıdır.", "Nummer und Datum der Anordnung sind beide erforderlich.",
        ),
        "Tələbə artıq bu jurnaldadır.": (
            "The student is already in this journal.", "Студент уже в этом журнале.",
            "Öğrenci zaten bu defterde.", "Der Studierende ist bereits in diesem Journal.",
        ),
        "Tələbə bu fənn üzrə bu semestrdə başqa jurnalda aktivdir. «Öz jurnalından azad et» seçilməlidir — "
        "əvvəlki qeydiyyat tarixçəyə keçir, bal və davamiyyət saxlanılır.": (
            "The student is already active in another journal for this subject this semester. Choose “Release "
            "from own journal” — the previous enrolment moves to history, scores and attendance are kept.",
            "Студент уже активен в другом журнале по этому предмету в этом семестре. Выберите «Освободить от "
            "своего журнала» — прежняя запись переходит в историю, баллы и посещаемость сохраняются.",
            "Öğrenci bu dönem bu derste başka bir defterde aktif. «Kendi defterinden çıkar» seçilmelidir — önceki "
            "kayıt geçmişe taşınır, not ve devam korunur.",
            "Der Studierende ist in diesem Semester bereits in einem anderen Journal für dieses Fach aktiv. "
            "„Aus eigenem Journal lösen“ wählen — die bisherige Einschreibung wird Historie, Noten und Anwesenheit "
            "bleiben erhalten.",
        ),
        "Tələbə bu fənni artıq keçib — təkrar yazılış yalnız kəsilmiş fənn üçündür.": (
            "The student has already passed this subject — re-enrolment is only for failed subjects.",
            "Студент уже сдал этот предмет — повторная запись только для несданных.",
            "Öğrenci bu dersi zaten geçti — tekrar kayıt yalnızca kalınan ders içindir.",
            "Der Studierende hat dieses Fach bereits bestanden — Wiedereinschreibung nur für nicht bestandene Fächer.",
        ),
        "Tələbə jurnala yazıla bilmədi.": (
            "The student could not be enrolled in the journal.", "Не удалось записать студента в журнал.",
            "Öğrenci deftere kaydedilemedi.", "Der Studierende konnte nicht in das Journal eingetragen werden.",
        ),
        "Tələbə və jurnal eyni təşkilata aid olmalıdır.": (
            "The student and the journal must belong to the same organisation.",
            "Студент и журнал должны принадлежать одной организации.",
            "Öğrenci ve defter aynı kuruma ait olmalıdır.",
            "Studierender und Journal müssen zur selben Organisation gehören.",
        ),
        "Tələbənin aktiv akademik qeydi (qrupu) yoxdur — akademik məzuniyyətdə, xaric və ya məzun ola bilər.": (
            "The student has no active academic record (group) — they may be on academic leave, expelled or graduated.",
            "У студента нет активной академической записи (группы) — возможно, академический отпуск, отчисление или "
            "выпуск.",
            "Öğrencinin aktif akademik kaydı (grubu) yok — kayıt dondurmuş, ilişiği kesilmiş veya mezun olmuş olabilir.",
            "Der Studierende hat keinen aktiven Studiendatensatz (Gruppe) — evtl. Urlaubssemester, exmatrikuliert oder "
            "Absolvent.",
        ),
        "Yerləşdirmə geri götürülə bilmir.": (
            "The placement cannot be withdrawn.", "Размещение нельзя отменить.", "Yerleştirme geri alınamıyor.",
            "Die Einteilung kann nicht zurückgenommen werden.",
        ),
        "Yerləşdirmə tapılmadı.": (
            "Placement not found.", "Размещение не найдено.", "Yerleştirme bulunamadı.", "Einteilung nicht gefunden.",
        ),
        "artıq alt qrupdadır": ("already in a subgroup", "уже в подгруппе", "zaten alt grupta", "bereits in Untergruppe"),
        "keçib": ("passed", "сдан", "geçti", "bestanden"),
        "kəsilib": ("failed", "не сдан", "kaldı", "nicht bestanden"),
        "«%(subject)s» fənnini bu semestr %(group)s qrupu ilə keçəcəksiniz. Fənn cədvəlinizdə və jurnalınızda "
        "görünür.": (
            "This semester you will take “%(subject)s” with group %(group)s. It appears in your timetable and journal.",
            "В этом семестре вы будете изучать «%(subject)s» с группой %(group)s. Предмет виден в вашем расписании и "
            "журнале.",
            "Bu dönem «%(subject)s» dersini %(group)s grubuyla alacaksınız. Ders programınızda ve defterinizde görünür.",
            "In diesem Semester belegen Sie „%(subject)s“ mit der Gruppe %(group)s. Es erscheint in Ihrem Stundenplan "
            "und Journal.",
        ),
    },
    "accounts.subgroup_placement": {
        "1. Tələbəni seçin": ("1. Choose the student", "1. Выберите студента", "1. Öğrenciyi seçin", "1. Studierenden wählen"),
        "2. Fənn və alt qrup jurnalı": (
            "2. Subject and subgroup journal", "2. Предмет и журнал подгруппы", "2. Ders ve alt grup defteri",
            "2. Fach und Untergruppen-Journal",
        ),
        "3. Sənəd, səbəb və təsdiq": (
            "3. Document, reason and confirmation", "3. Документ, причина и подтверждение",
            "3. Belge, gerekçe ve onay", "3. Dokument, Begründung und Bestätigung",
        ),
        "Ad, soyad, qrup və ya tələbə nömrəsi…": (
            "Name, surname, group or student number…", "Имя, фамилия, группа или номер студента…",
            "Ad, soyad, grup veya öğrenci numarası…", "Vorname, Nachname, Gruppe oder Matrikelnummer…",
        ),
        "Alt qrup": ("Subgroup", "Подгруппа", "Alt grup", "Untergruppe"),
        "Alt qrupa yerləşdir": ("Place in subgroup", "Разместить в подгруппе", "Alt gruba yerleştir", "In Untergruppe einteilen"),
        "Artıq bu jurnaldadır": ("Already in this journal", "Уже в этом журнале", "Zaten bu defterde", "Bereits in diesem Journal"),
        "Bu ada uyğun tələbə tapılmadı.": (
            "No student matches this name.", "Студент с таким именем не найден.", "Bu ada uygun öğrenci bulunamadı.",
            "Kein Studierender mit diesem Namen gefunden.",
        ),
        "Bu alət üçün «retake.manage» səlahiyyəti lazımdır.": (
            "This tool requires the “retake.manage” permission.", "Для этого инструмента нужно право «retake.manage».",
            "Bu araç için «retake.manage» yetkisi gerekir.", "Dieses Werkzeug erfordert die Berechtigung „retake.manage“.",
        ),
        "Bu fənn bu semestr başqa qrupların heç birində açılmayıb.": (
            "This subject is not offered in any other group this semester.",
            "В этом семестре предмет не открыт ни в одной другой группе.",
            "Bu ders bu dönem başka hiçbir grupta açılmadı.",
            "Dieses Fach wird in diesem Semester in keiner anderen Gruppe angeboten.",
        ),
        "Bu fənni seç": ("Choose this subject", "Выбрать этот предмет", "Bu dersi seç", "Dieses Fach wählen"),
        "Bu semestr": ("This semester", "Этот семестр", "Bu dönem", "Dieses Semester"),
        "Bu semestr başqa qruplarda bu ada uyğun fənn yoxdur.": (
            "No subject with this name in other groups this semester.",
            "В этом семестре в других группах нет предмета с таким названием.",
            "Bu dönem başka gruplarda bu ada uygun ders yok.",
            "Kein Fach mit diesem Namen in anderen Gruppen in diesem Semester.",
        ),
        "Bu semestrin fənləri": ("This semester's subjects", "Предметы этого семестра", "Bu dönemin dersleri", "Fächer dieses Semesters"),
        "Bütün yoxlamalar uğurludur — yerləşdirmək olar.": (
            "All checks passed — the placement can be made.", "Все проверки пройдены — можно разместить.",
            "Tüm kontroller başarılı — yerleştirilebilir.", "Alle Prüfungen bestanden — Einteilung möglich.",
        ),
        "Cari aktiv semestr təyin olunmayıb — yerləşdirmə yalnız cari semestrdə mümkündür.": (
            "No current active semester is set — placements are only possible in the current semester.",
            "Текущий активный семестр не задан — размещение возможно только в текущем семестре.",
            "Geçerli aktif dönem belirlenmedi — yerleştirme yalnızca geçerli dönemde mümkündür.",
            "Kein aktuelles aktives Semester festgelegt — Einteilungen sind nur im aktuellen Semester möglich.",
        ),
        "Cədvəl": ("Timetable", "Расписание", "Program", "Stundenplan"),
        "Cədvəl hələ qurulmayıb": ("Timetable not set yet", "Расписание ещё не составлено", "Program henüz hazırlanmadı", "Stundenplan noch nicht erstellt"),
        "Cədvəl toqquşması yerləşdirməni bloklayır": (
            "A timetable clash blocks the placement", "Конфликт расписания блокирует размещение",
            "Program çakışması yerleştirmeyi engeller", "Ein Stundenplankonflikt blockiert die Einteilung",
        ),
        "Cədvəl toqquşması — xəbərdarlıq, təsdiqlə davam etmək olar": (
            "Timetable clash — warning, you can confirm and continue",
            "Конфликт расписания — предупреждение, можно подтвердить и продолжить",
            "Program çakışması — uyarı, onaylayarak devam edilebilir",
            "Stundenplankonflikt — Warnung, Fortfahren nach Bestätigung möglich",
        ),
        "Cədvəl toqquşmasını gördüm, yerləşdirməni təsdiqləyirəm.": (
            "I have seen the timetable clash and confirm the placement.",
            "Я вижу конфликт расписания и подтверждаю размещение.",
            "Program çakışmasını gördüm, yerleştirmeyi onaylıyorum.",
            "Ich habe den Stundenplankonflikt gesehen und bestätige die Einteilung.",
        ),
        "Daha çox": ("More", "Ещё", "Daha fazla", "Mehr"),
        "Dolub": ("Full", "Заполнено", "Dolu", "Voll"),
        "Dərs saatı tələbənin öz cədvəli ilə üst-üstə düşür — təsdiq qutusunu işarələyin.": (
            "The class time overlaps the student's own timetable — tick the confirmation box.",
            "Время занятий пересекается с расписанием студента — отметьте подтверждение.",
            "Ders saati öğrencinin kendi programıyla çakışıyor — onay kutusunu işaretleyin.",
            "Die Unterrichtszeit überschneidet sich mit dem eigenen Stundenplan — Bestätigung ankreuzen.",
        ),
        "Fayl yükləyin və ya sərəncamın nömrəsi ilə tarixini yazın.": (
            "Upload a file or enter the order number and date.", "Загрузите файл или укажите номер и дату приказа.",
            "Dosya yükleyin ya da kararın numarası ve tarihini yazın.",
            "Datei hochladen oder Nummer und Datum der Anordnung eingeben.",
        ),
        "Fənn": ("Subject", "Предмет", "Ders", "Fach"),
        "Fənn axtarın…": ("Search for a subject…", "Найдите предмет…", "Ders arayın…", "Fach suchen…"),
        "Fənn və jurnal": ("Subject and journal", "Предмет и журнал", "Ders ve defter", "Fach und Journal"),
        "Fənni seçin — sistem bu semestr başqa qruplarda açılmış uyğun jurnalları göstərir.": (
            "Choose a subject — the system lists matching journals opened in other groups this semester.",
            "Выберите предмет — система покажет подходящие журналы других групп в этом семестре.",
            "Dersi seçin — sistem bu dönem başka gruplarda açılmış uygun defterleri gösterir.",
            "Fach wählen — das System zeigt passende Journale anderer Gruppen in diesem Semester.",
        ),
        "Geri götür": ("Withdraw", "Отменить", "Geri al", "Zurücknehmen"),
        "Geri götürmə səbəbi": ("Reason for withdrawal", "Причина отмены", "Geri alma gerekçesi", "Grund der Rücknahme"),
        "Geri götürmə səbəbi (ən azı 10 simvol)": (
            "Reason for withdrawal (at least 10 characters)", "Причина отмены (не менее 10 символов)",
            "Geri alma gerekçesi (en az 10 karakter)", "Grund der Rücknahme (mindestens 10 Zeichen)",
        ),
        "Geri götürüldü": ("Withdrawn", "Отменено", "Geri alındı", "Zurückgenommen"),
        "Hədd": ("Limit", "Лимит", "Sınır", "Limit"),
        "Hələ yerləşdirmə olmayıb.": ("No placements yet.", "Размещений пока не было.", "Henüz yerleştirme olmadı.", "Noch keine Einteilungen."),
        "Hələ yerləşdirmə yoxdur.": ("No placements yet.", "Размещений пока нет.", "Henüz yerleştirme yok.", "Noch keine Einteilungen."),
        "Jurnal bağlıdır": ("Journal closed", "Журнал закрыт", "Defter kapalı", "Journal geschlossen"),
        "Kim": ("By", "Кто", "Kim", "Von"),
        "Kim, nə vaxt, hansı sənədlə — geri götürülənlər də tarixçədə qalır.": (
            "Who, when and with which document — withdrawn placements stay in the history too.",
            "Кто, когда и по какому документу — отменённые размещения тоже остаются в истории.",
            "Kim, ne zaman, hangi belgeyle — geri alınanlar da geçmişte kalır.",
            "Wer, wann, mit welchem Dokument — zurückgenommene Einteilungen bleiben ebenfalls in der Historie.",
        ),
        "Kredit": ("Credits", "Кредиты", "Kredi", "Credits"),
        "Kredit həddi keçilib": ("Credit limit exceeded", "Лимит кредитов превышен", "Kredi sınırı aşıldı", "Creditlimit überschritten"),
        "Kredit həddi: %(base)s (alt qrupla birlikdə %(sub)s)": (
            "Credit limit: %(base)s (%(sub)s including subgroups)", "Лимит кредитов: %(base)s (с подгруппами %(sub)s)",
            "Kredi sınırı: %(base)s (alt grupla birlikte %(sub)s)", "Creditlimit: %(base)s (mit Untergruppen %(sub)s)",
        ),
        "Kəsilmiş fənlər": ("Failed subjects", "Несданные предметы", "Kalınan dersler", "Nicht bestandene Fächer"),
        "Kəsilmiş fənn yoxdur.": ("No failed subjects.", "Несданных предметов нет.", "Kalınan ders yok.", "Keine nicht bestandenen Fächer."),
        "Kəsilmiş fənnin təkrarı": ("Retake of a failed subject", "Повтор несданного предмета", "Kalınan dersin tekrarı", "Wiederholung eines nicht bestandenen Fachs"),
        "Ləğv et": ("Cancel", "Отмена", "İptal", "Abbrechen"),
        "Müəllim": ("Teacher", "Преподаватель", "Öğretmen", "Lehrkraft"),
        "Müəllim təyin olunmayıb": ("No teacher assigned", "Преподаватель не назначен", "Öğretmen atanmadı", "Keine Lehrkraft zugewiesen"),
        "Məs.: 2024/2025 Yaz semestrində kəsilmiş fənn — dekanlığın 12.09.2025 tarixli təqdimatı": (
            "E.g.: failed in the 2024/2025 spring semester — dean's office submission of 12.09.2025",
            "Напр.: не сдан в весеннем семестре 2024/2025 — представление деканата от 12.09.2025",
            "Örn.: 2024/2025 bahar döneminde kalınan ders — dekanlığın 12.09.2025 tarihli teklifi",
            "Z. B.: im Sommersemester 2024/2025 nicht bestanden — Antrag des Dekanats vom 12.09.2025",
        ),
        "Nə vaxt": ("When", "Когда", "Ne zaman", "Wann"),
        "Qalan": ("Remaining", "Осталось", "Kalan", "Verbleibend"),
        "Qaydalar": ("Rules", "Правила", "Kurallar", "Regeln"),
        "Seç": ("Choose", "Выбрать", "Seç", "Wählen"),
        "Seçildi": ("Selected", "Выбрано", "Seçildi", "Ausgewählt"),
        "Son yerləşdirmələr": ("Recent placements", "Последние размещения", "Son yerleştirmeler", "Letzte Einteilungen"),
        "Səbəb": ("Reason", "Причина", "Gerekçe", "Begründung"),
        "Səbəb ən azı 10 simvol olmalıdır.": (
            "The reason must be at least 10 characters.", "Причина должна быть не короче 10 символов.",
            "Gerekçe en az 10 karakter olmalıdır.", "Die Begründung muss mindestens 10 Zeichen lang sein.",
        ),
        "Sənəd faylı (PDF, JPG, PNG · 10 MB-a qədər)": (
            "Document file (PDF, JPG, PNG · up to 10 MB)", "Файл документа (PDF, JPG, PNG · до 10 МБ)",
            "Belge dosyası (PDF, JPG, PNG · 10 MB'a kadar)", "Dokumentdatei (PDF, JPG, PNG · bis 10 MB)",
        ),
        "Sənəd məcburidir": ("Document required", "Документ обязателен", "Belge zorunlu", "Dokument erforderlich"),
        "Sənəd və təsdiq": ("Document and confirmation", "Документ и подтверждение", "Belge ve onay", "Dokument und Bestätigung"),
        "Sənədə bax": ("View document", "Открыть документ", "Belgeyi gör", "Dokument ansehen"),
        "Sərəncam": ("Order", "Приказ", "Karar", "Anordnung"),
        "Sərəncam / təqdimat №": ("Order / submission No.", "№ приказа / представления", "Karar / teklif No", "Anordnungs-/Antrags-Nr."),
        "Tapılmadı.": ("Not found.", "Не найдено.", "Bulunamadı.", "Nicht gefunden."),
        "Tarixi": ("Date", "Дата", "Tarih", "Datum"),
        "Tarixçədə axtar": ("Search the history", "Поиск в истории", "Geçmişte ara", "In der Historie suchen"),
        "Toqquşma": ("Clash", "Конфликт", "Çakışma", "Konflikt"),
        "Toqquşma yoxdur": ("No clash", "Конфликтов нет", "Çakışma yok", "Kein Konflikt"),
        "Toqquşmanı təsdiqləyin.": ("Confirm the clash.", "Подтвердите конфликт.", "Çakışmayı onaylayın.", "Konflikt bestätigen."),
        "Tələbə": ("Student", "Студент", "Öğrenci", "Studierende(r)"),
        "Tələbə alt qrupa yerləşdirildi: %(subject)s · %(group)s.": (
            "Student placed in subgroup: %(subject)s · %(group)s.", "Студент размещён в подгруппе: %(subject)s · %(group)s.",
            "Öğrenci alt gruba yerleştirildi: %(subject)s · %(group)s.",
            "Studierende(r) in Untergruppe eingeteilt: %(subject)s · %(group)s.",
        ),
        "Tələbə jurnaldan çıxarılır (bal və davamiyyət silinmir), birləşmə varsa öz jurnalı bərpa olunur. Hər iki "
        "əməl tarixçədə qalır.": (
            "The student is removed from the journal (scores and attendance are not deleted); after a merge the own "
            "journal is restored. Both actions stay in the history.",
            "Студент исключается из журнала (баллы и посещаемость не удаляются); при объединении восстанавливается "
            "свой журнал. Оба действия остаются в истории.",
            "Öğrenci defterden çıkarılır (not ve devam silinmez), birleştirme varsa kendi defteri geri yüklenir. Her iki "
            "işlem geçmişte kalır.",
            "Der Studierende wird aus dem Journal entfernt (Noten und Anwesenheit bleiben); nach einer Zusammenlegung "
            "wird das eigene Journal wiederhergestellt. Beide Vorgänge bleiben in der Historie.",
        ),
        "Tələbə, fənn, sərəncam №…": ("Student, subject, order No.…", "Студент, предмет, № приказа…", "Öğrenci, ders, karar No…", "Studierende, Fach, Anordnungs-Nr.…"),
        "Tələbəni başqa qrupun jurnalına (alt qrupa) yerləşdirin: sistem kredit həddini, fənnin keçilib-keçilmədiyini, "
        "jurnalın açıq olmasını, tutumu və cədvəl toqquşmasını yoxlayır. Sənəd məcburidir, hər yerləşdirmə tarixçədə "
        "qalır və geri götürülə bilər.": (
            "Place a student in another group's journal (subgroup): the system checks the credit limit, whether the "
            "subject was passed, that the journal is open, capacity and timetable clashes. A document is required; "
            "every placement stays in the history and can be withdrawn.",
            "Разместите студента в журнале другой группы (подгруппе): система проверяет лимит кредитов, сдан ли "
            "предмет, открыт ли журнал, вместимость и конфликты расписания. Документ обязателен; каждое размещение "
            "остаётся в истории и может быть отменено.",
            "Öğrenciyi başka bir grubun defterine (alt gruba) yerleştirin: sistem kredi sınırını, dersin geçilip "
            "geçilmediğini, defterin açık olmasını, kapasiteyi ve program çakışmasını denetler. Belge zorunludur; her "
            "yerleştirme geçmişte kalır ve geri alınabilir.",
            "Teilen Sie Studierende in das Journal einer anderen Gruppe (Untergruppe) ein: Das System prüft "
            "Creditlimit, ob das Fach bestanden ist, ob das Journal offen ist, Kapazität und Stundenplankonflikte. "
            "Ein Dokument ist Pflicht; jede Einteilung bleibt in der Historie und kann zurückgenommen werden.",
        ),
        "Təqdimat / sərəncam faylını yükləyin və ya sərəncamın nömrəsi və tarixini yazın.": (
            "Upload the submission / order file or enter the order number and date.",
            "Загрузите файл представления / приказа или укажите номер и дату приказа.",
            "Teklif / karar dosyasını yükleyin ya da kararın numarası ve tarihini yazın.",
            "Antrags-/Anordnungsdatei hochladen oder Nummer und Datum der Anordnung eingeben.",
        ),
        "Uyğun jurnallar": ("Matching journals", "Подходящие журналы", "Uygun defterler", "Passende Journale"),
        "Xəbərdarlıq": ("Warning", "Предупреждение", "Uyarı", "Warnung"),
        "Yalnız sizin əhatənizdəki oxuyan tələbələr göstərilir.": (
            "Only enrolled students within your scope are shown.", "Показаны только обучающиеся студенты вашей зоны.",
            "Yalnızca kapsamınızdaki öğrenim gören öğrenciler gösterilir.",
            "Nur eingeschriebene Studierende in Ihrem Zuständigkeitsbereich werden angezeigt.",
        ),
        "Yerləşdirildi": ("Placed", "Размещён", "Yerleştirildi", "Eingeteilt"),
        "Yerləşdirmə addımları": ("Placement steps", "Шаги размещения", "Yerleştirme adımları", "Schritte der Einteilung"),
        "Yerləşdirmə geri götürüldü — tarixçə saxlanılır.": (
            "Placement withdrawn — the history is kept.", "Размещение отменено — история сохранена.",
            "Yerleştirme geri alındı — geçmiş korunuyor.", "Einteilung zurückgenommen — die Historie bleibt erhalten.",
        ),
        "Yerləşdirmə mümkün deyil:": ("Placement is not possible:", "Размещение невозможно:", "Yerleştirme mümkün değil:", "Einteilung nicht möglich:"),
        "Yerləşdirmə tarixçəsi": ("Placement history", "История размещений", "Yerleştirme geçmişi", "Einteilungshistorie"),
        "Yerləşdirmədən sonra": ("After placement", "После размещения", "Yerleştirmeden sonra", "Nach der Einteilung"),
        "Yerləşdirməni geri götür": ("Withdraw placement", "Отменить размещение", "Yerleştirmeyi geri al", "Einteilung zurücknehmen"),
        "Yüklənir…": ("Loading…", "Загрузка…", "Yükleniyor…", "Wird geladen…"),
        "boş yer": ("free seats", "свободных мест", "boş yer", "freie Plätze"),
        "kredit": ("credits", "кредитов", "kredi", "Credits"),
        "qrupdan → jurnala": ("group → journal", "группа → журнал", "gruptan → deftere", "Gruppe → Journal"),
        "tələbə": ("students", "студентов", "öğrenci", "Studierende"),
        "«Başqasının adından» rejimində yalnız baxış mümkündür.": (
            "In “view as” mode you can only view.", "В режиме «от имени другого» доступен только просмотр.",
            "«Başkası adına» modunda yalnızca görüntüleme mümkündür.", "Im Modus „Ansicht als“ ist nur Ansehen möglich.",
        ),
        "«Başqasının adından» rejimində yerləşdirmə edilmir — yalnız baxış.": (
            "No placements in “view as” mode — view only.", "В режиме «от имени другого» размещение не выполняется — только просмотр.",
            "«Başkası adına» modunda yerleştirme yapılmaz — yalnızca görüntüleme.",
            "Im Modus „Ansicht als“ keine Einteilungen — nur Ansicht.",
        ),
        "«Başqasının adından» rejimindəsiniz — yoxlamaları görürsünüz, yerləşdirmə edilmir.": (
            "You are in “view as” mode — you see the checks, no placement is made.",
            "Вы в режиме «от имени другого» — проверки видны, размещение не выполняется.",
            "«Başkası adına» modundasınız — kontrolleri görürsünüz, yerleştirme yapılmaz.",
            "Sie sind im Modus „Ansicht als“ — Sie sehen die Prüfungen, es wird nichts eingeteilt.",
        ),
        "Öz fənləri": ("Own subjects", "Свои предметы", "Kendi dersleri", "Eigene Fächer"),
        "Öz qrupunun jurnalında bu fənn var — yerləşdirmədə ondan azad ediləcək.": (
            "This subject is in the own group's journal — the student will be released from it on placement.",
            "Этот предмет есть в журнале своей группы — при размещении студент будет освобождён от него.",
            "Bu ders kendi grubunun defterinde var — yerleştirmede oradan çıkarılacak.",
            "Dieses Fach steht im Journal der eigenen Gruppe — bei der Einteilung wird der Studierende daraus gelöst.",
        ),
        "Öz qrupunun jurnalından azad et — əvvəlki qeydiyyat tarixçəyə keçir, bal və davamiyyət saxlanılır.": (
            "Release from own group's journal — the previous enrolment moves to history, scores and attendance are kept.",
            "Освободить от журнала своей группы — прежняя запись переходит в историю, баллы и посещаемость сохраняются.",
            "Kendi grubunun defterinden çıkar — önceki kayıt geçmişe taşınır, not ve devam korunur.",
            "Aus dem Journal der eigenen Gruppe lösen — die bisherige Einschreibung wird Historie, Noten und Anwesenheit "
            "bleiben erhalten.",
        ),
        "üst-üstə düşür": ("overlaps", "пересекается", "çakışıyor", "überschneidet sich"),
        "Əməliyyat alınmadı — yenidən cəhd edin.": (
            "The action failed — please try again.", "Операция не удалась — попробуйте снова.",
            "İşlem başarısız — yeniden deneyin.", "Vorgang fehlgeschlagen — bitte erneut versuchen.",
        ),
        "Ən azı 10 simvol.": ("At least 10 characters.", "Не менее 10 символов.", "En az 10 karakter.", "Mindestens 10 Zeichen."),
        "Ən azı 10 simvol. Tələbənin izində və audit jurnalında görünür.": (
            "At least 10 characters. Visible in the student's trail and the audit log.",
            "Не менее 10 символов. Видно в истории студента и журнале аудита.",
            "En az 10 karakter. Öğrencinin izinde ve denetim kaydında görünür.",
            "Mindestens 10 Zeichen. Sichtbar im Verlauf des Studierenden und im Audit-Log.",
        ),
        "Əvvəlcə tələbəni seçin…": ("Choose the student first…", "Сначала выберите студента…", "Önce öğrenciyi seçin…", "Zuerst Studierenden wählen…"),
    },
    "profile.sidebar": {
        "Alt qrupa tələbə əlavə et": (
            "Add student to subgroup", "Добавить студента в подгруппу", "Alt gruba öğrenci ekle",
            "Studierende in Untergruppe aufnehmen",
        ),
    },
    "accounts.student_registry": {
        "Alt qrup yerləşdirmələri": ("Subgroup placements", "Размещения в подгруппах", "Alt grup yerleştirmeleri", "Untergruppen-Einteilungen"),
        "Alt qrup yerləşdirməsi olmayıb.": (
            "No subgroup placements.", "Размещений в подгруппах не было.", "Alt grup yerleştirmesi olmadı.",
            "Keine Untergruppen-Einteilungen.",
        ),
        "Alt qrupa tələbə əlavə et": (
            "Add student to subgroup", "Добавить студента в подгруппу", "Alt gruba öğrenci ekle",
            "Studierende in Untergruppe aufnehmen",
        ),
        "Bu semestr": ("This semester", "Этот семестр", "Bu dönem", "Dieses Semester"),
        "Kredit yükü və alt qrup": ("Credit load and subgroups", "Кредитная нагрузка и подгруппы", "Kredi yükü ve alt grup", "Kreditlast und Untergruppen"),
        "Sənəd": ("Document", "Документ", "Belge", "Dokument"),
        "Sərəncam": ("Order", "Приказ", "Karar", "Anordnung"),
        "alt qrup": ("subgroup", "подгруппа", "alt grup", "Untergruppe"),
        "geri götürülüb": ("withdrawn", "отменено", "geri alındı", "zurückgenommen"),
        "kredit": ("credits", "кредитов", "kredi", "Credits"),
    },
    "profile.subjects": {
        "Alt qrup": ("Subgroup", "Подгруппа", "Alt grup", "Untergruppe"),
        "Bu fənni başqa qrupun jurnalında (alt qrupda) keçirsiniz": (
            "You take this subject in another group's journal (subgroup)",
            "Вы изучаете этот предмет в журнале другой группы (подгруппе)",
            "Bu dersi başka bir grubun defterinde (alt grupta) alıyorsunuz",
            "Sie belegen dieses Fach im Journal einer anderen Gruppe (Untergruppe)",
        ),
        "Bu semestr: %(total)s / %(limit)s kredit": (
            "This semester: %(total)s / %(limit)s credits", "Этот семестр: %(total)s / %(limit)s кредитов",
            "Bu dönem: %(total)s / %(limit)s kredi", "Dieses Semester: %(total)s / %(limit)s Credits",
        ),
        "öz fənləri %(own)s, alt qrup %(sub)s": (
            "own subjects %(own)s, subgroup %(sub)s", "свои предметы %(own)s, подгруппа %(sub)s",
            "kendi dersleri %(own)s, alt grup %(sub)s", "eigene Fächer %(own)s, Untergruppe %(sub)s",
        ),
    },
    "registrar.journal": {
        "Alt qrup": ("Subgroup", "Подгруппа", "Alt grup", "Untergruppe"),
        "Bu semestr: %(total)s / %(limit)s kredit": (
            "This semester: %(total)s / %(limit)s credits", "Этот семестр: %(total)s / %(limit)s кредитов",
            "Bu dönem: %(total)s / %(limit)s kredi", "Dieses Semester: %(total)s / %(limit)s Credits",
        ),
    },
}  # fmt: skip


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
            msgstr = msgid if lang == "az" else translations[ORDER.index(lang)]
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
