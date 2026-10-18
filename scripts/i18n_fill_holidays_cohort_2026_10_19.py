#!/usr/bin/env python3
"""EMSArena i18n — «Bayram və qeyri-iş günləri», semestr açılışının kohort planı, «Cədvəl yoxdur» xatırlatması
(2026-10-19).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur); sonra
`compilemessages -i .claude -i venv`. `{% blocktrans %}` mətnləri `%(ad)s` yer tutucusu ilə yazılıb; msgid-lərdə
xam «%» işarəsi YOXDUR.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

HOL = "organizations.holiday"
CAL = "registrar.calendar"
SEM = "accounts.semester"
LOG = "accounts.lessons_log"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    HOL: {
        "Bayram": t("Public holiday", "Праздник", "Resmî tatil", "Feiertag"),
        "Qeyri-iş günü": t("Day off", "Нерабочий день", "Çalışılmayan gün", "Arbeitsfreier Tag"),
        "İş günü köçürməsi": t(
            "Transferred working day", "Перенесённый рабочий день", "Taşınan iş günü", "Verlegter Arbeitstag"
        ),
        "Bayram / qeyri-iş günü": t(
            "Holiday / day off", "Праздник / нерабочий день", "Tatil / çalışılmayan gün", "Feiertag / freier Tag"
        ),
        "Bayram və qeyri-iş günləri": t(
            "Holidays and days off",
            "Праздники и нерабочие дни",
            "Tatiller ve çalışılmayan günler",
            "Feiertage und arbeitsfreie Tage",
        ),
        "Tarix düzgün deyil.": t(
            "The date is invalid.", "Неверная дата.", "Tarih geçersiz.", "Das Datum ist ungültig."
        ),
        "Günün adı boş ola bilməz.": t(
            "The day name cannot be empty.",
            "Название дня не может быть пустым.",
            "Günün adı boş olamaz.",
            "Der Name des Tages darf nicht leer sein.",
        ),
        "Günün növü düzgün deyil.": t(
            "The day type is invalid.",
            "Неверный тип дня.",
            "Gün türü geçersiz.",
            "Die Art des Tages ist ungültig.",
        ),
        "«İş günü köçürməsi» yalnız şənbə və ya bazar gününə yazılır — həmin gün iş günü elan olunur.": t(
            "A “transferred working day” can only be set on a Saturday or Sunday — that day is declared a working "
            "day.",
            "«Перенесённый рабочий день» можно указать только для субботы или воскресенья — этот день объявляется "
            "рабочим.",
            "“Taşınan iş günü” yalnızca cumartesi veya pazar gününe yazılır — o gün iş günü ilan edilir.",
            "Ein „verlegter Arbeitstag“ kann nur auf einen Samstag oder Sonntag gelegt werden — dieser Tag wird zum "
            "Arbeitstag erklärt.",
        ),
        "Qeyd tapılmadı.": t("Entry not found.", "Запись не найдена.", "Kayıt bulunamadı.", "Eintrag nicht gefunden."),
        "Bu tarix artıq təqvimdədir — mövcud qeydi redaktə edin.": t(
            "This date is already in the calendar — edit the existing entry.",
            "Эта дата уже есть в календаре — отредактируйте существующую запись.",
            "Bu tarih zaten takvimde — mevcut kaydı düzenleyin.",
            "Dieses Datum ist bereits im Kalender — bearbeiten Sie den vorhandenen Eintrag.",
        ),
    },
    CAL: {
        "Bazar ertəsi": t("Monday", "Понедельник", "Pazartesi", "Montag"),
        "Çərşənbə axşamı": t("Tuesday", "Вторник", "Salı", "Dienstag"),
        "Çərşənbə": t("Wednesday", "Среда", "Çarşamba", "Mittwoch"),
        "Cümə axşamı": t("Thursday", "Четверг", "Perşembe", "Donnerstag"),
        "Cümə": t("Friday", "Пятница", "Cuma", "Freitag"),
        "Şənbə": t("Saturday", "Суббота", "Cumartesi", "Samstag"),
        "Bazar": t("Sunday", "Воскресенье", "Pazar", "Sonntag"),
        "Gün təqvimə əlavə olundu.": t(
            "The day was added to the calendar.",
            "День добавлен в календарь.",
            "Gün takvime eklendi.",
            "Der Tag wurde dem Kalender hinzugefügt.",
        ),
        "Dəyişiklik yadda saxlanıldı.": t(
            "Changes saved.", "Изменения сохранены.", "Değişiklik kaydedildi.", "Änderungen gespeichert."
        ),
        "%(year)s: təqvimə %(created)d gün əlavə olundu, %(skipped)d tarix artıq təqvimdə idi.": t(
            "%(year)s: %(created)d days added to the calendar, %(skipped)d dates were already in the calendar.",
            "%(year)s: в календарь добавлено дней — %(created)d, уже было в календаре дат — %(skipped)d.",
            "%(year)s: takvime %(created)d gün eklendi, %(skipped)d tarih zaten takvimdeydi.",
            "%(year)s: %(created)d Tage zum Kalender hinzugefügt, %(skipped)d Daten waren bereits im Kalender.",
        ),
        "Gün təqvimdən silindi.": t(
            "The day was removed from the calendar.",
            "День удалён из календаря.",
            "Gün takvimden silindi.",
            "Der Tag wurde aus dem Kalender entfernt.",
        ),
        "Tədris ili seçilməyib.": t(
            "No academic year selected.",
            "Учебный год не выбран.",
            "Öğretim yılı seçilmedi.",
            "Kein Studienjahr gewählt.",
        ),
        "Bayram təqvimini dəyişmək üçün səlahiyyətiniz yoxdur.": t(
            "You are not allowed to change the holiday calendar.",
            "У вас нет прав на изменение календаря праздников.",
            "Tatil takvimini değiştirme yetkiniz yok.",
            "Sie dürfen den Feiertagskalender nicht ändern.",
        ),
        "Naməlum əməl.": t("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem.", "Unbekannte Aktion."),
        "Başqasının adından baxış rejimində dəyişiklik etmək olmaz.": t(
            "Changes are not allowed while viewing as another user.",
            "В режиме просмотра от имени другого пользователя изменения запрещены.",
            "Başka bir kullanıcı adına görüntüleme modunda değişiklik yapılamaz.",
            "Im Modus „Ansicht als anderer Benutzer“ sind keine Änderungen erlaubt.",
        ),
        "Əməl alınmadı. Yenidən cəhd edin.": t(
            "The action failed. Please try again.",
            "Не удалось выполнить действие. Попробуйте ещё раз.",
            "İşlem başarısız oldu. Lütfen tekrar deneyin.",
            "Die Aktion ist fehlgeschlagen. Bitte versuchen Sie es erneut.",
        ),
        "Bayram və qeyri-iş günləri · %(year)s": t(
            "Holidays and days off · %(year)s",
            "Праздники и нерабочие дни · %(year)s",
            "Tatiller ve çalışılmayan günler · %(year)s",
            "Feiertage und arbeitsfreie Tage · %(year)s",
        ),
        "Rəsmi bayramları əlavə et (sabit tarixli)": t(
            "Add public holidays (fixed dates)",
            "Добавить государственные праздники (с фиксированной датой)",
            "Resmî tatilleri ekle (sabit tarihli)",
            "Gesetzliche Feiertage hinzufügen (feste Daten)",
        ),
        "Gün əlavə et": t("Add day", "Добавить день", "Gün ekle", "Tag hinzufügen"),
        "Tədris ili %(start)s — %(end)s. Bayram və qeyri-iş günləri dərs günü sayılmır: «Keçilmiş dərslər» onları "
        "«qeydə alınmayıb» saymır, mühasibatlığın aylıq planı və müraciətlərin cavab müddəti iş günü ilə "
        "hesablananda çıxılır. «İş günü köçürməsi» iş günü elan olunmuş şənbə/bazardır.": t(
            "Academic year %(start)s — %(end)s. Holidays and days off are not teaching days: “Lessons held” does not "
            "count them as “not recorded”, and they are excluded when the accounting monthly plan and the response "
            "deadline of applications are calculated in working days. A “transferred working day” is a Saturday/Sunday "
            "declared a working day.",
            "Учебный год %(start)s — %(end)s. Праздники и нерабочие дни не считаются учебными: «Проведённые занятия» "
            "не считают их «не отмеченными», а при расчёте месячного плана бухгалтерии и срока ответа на обращения в "
            "рабочих днях они исключаются. «Перенесённый рабочий день» — суббота/воскресенье, объявленные рабочими.",
            "Öğretim yılı %(start)s — %(end)s. Tatiller ve çalışılmayan günler ders günü sayılmaz: “İşlenen dersler” "
            "bunları “kaydedilmedi” saymaz; muhasebenin aylık planı ve başvuruların yanıt süresi iş günüyle "
            "hesaplanırken bu günler çıkarılır. “Taşınan iş günü”, iş günü ilan edilmiş cumartesi/pazardır.",
            "Studienjahr %(start)s — %(end)s. Feiertage und arbeitsfreie Tage sind keine Unterrichtstage: „Gehaltene "
            "Stunden“ zählt sie nicht als „nicht erfasst“, und bei der Berechnung des monatlichen Plans der "
            "Buchhaltung sowie der Antwortfrist von Anträgen in Arbeitstagen werden sie abgezogen. Ein „verlegter "
            "Arbeitstag“ ist ein zum Arbeitstag erklärter Samstag/Sonntag.",
        ),
        "Düymə yalnız SABİT tarixli rəsmi bayramları (Yeni il, 8 Mart, Novruz, 9 May, 28 May, 15 İyun, 26 İyun, 8–9 "
        "Noyabr, 31 Dekabr) və 20 Yanvarı (Ümumxalq hüzn günü — qeyri-iş günü) əlavə edir; təqvimdə olan tarixlər "
        "atlanır. Ramazan və Qurban bayramları (hər il dəyişir), bayram həftə sonuna düşəndə verilən əlavə istirahət "
        "günləri və hökumətin iş günü köçürmələri «Gün əlavə et» ilə ƏL İLƏ daxil edilir.": t(
            "The button adds only public holidays with FIXED dates (New Year, 8 March, Novruz, 9 May, 28 May, 15 June, "
            "26 June, 8–9 November, 31 December) and 20 January (National Day of Mourning — a day off); dates already "
            "in the calendar are skipped. Ramadan and Gurban holidays (they change every year), extra days off when a "
            "holiday falls on a weekend and government working-day transfers are entered MANUALLY with “Add day”.",
            "Кнопка добавляет только государственные праздники с ФИКСИРОВАННОЙ датой (Новый год, 8 Марта, Новруз, "
            "9 Мая, 28 Мая, 15 Июня, 26 Июня, 8–9 Ноября, 31 Декабря) и 20 Января (День всенародной скорби — "
            "нерабочий день); даты, уже имеющиеся в календаре, пропускаются. Рамазан и Гурбан (меняются каждый год), "
            "дополнительные выходные при совпадении праздника с выходными и правительственные переносы рабочих дней "
            "вносятся ВРУЧНУЮ через «Добавить день».",
            "Düğme yalnızca SABİT tarihli resmî tatilleri (Yılbaşı, 8 Mart, Nevruz, 9 Mayıs, 28 Mayıs, 15 Haziran, "
            "26 Haziran, 8–9 Kasım, 31 Aralık) ve 20 Ocak'ı (Ulusal Yas Günü — çalışılmayan gün) ekler; takvimde olan "
            "tarihler atlanır. Ramazan ve Kurban bayramları (her yıl değişir), tatil hafta sonuna denk geldiğinde "
            "verilen ek izin günleri ve hükümetin iş günü taşımaları “Gün ekle” ile ELLE girilir.",
            "Die Schaltfläche fügt nur gesetzliche Feiertage mit FESTEM Datum (Neujahr, 8. März, Nowruz, 9. Mai, "
            "28. Mai, 15. Juni, 26. Juni, 8.–9. November, 31. Dezember) und den 20. Januar (Tag der Volkstrauer — "
            "arbeitsfreier Tag) hinzu; bereits vorhandene Daten werden übersprungen. Ramadan- und Opferfest "
            "(jährlich wechselnd), zusätzliche freie Tage bei Feiertagen am Wochenende und staatliche Verlegungen "
            "von Arbeitstagen werden MANUELL über „Tag hinzufügen“ eingetragen.",
        ),
        "Günü redaktə et": t("Edit day", "Редактировать день", "Günü düzenle", "Tag bearbeiten"),
        "Redaktə et: %(name)s": t(
            "Edit: %(name)s", "Редактировать: %(name)s", "Düzenle: %(name)s", "Bearbeiten: %(name)s"
        ),
        "«%(name)s» (%(day)s) təqvimdən silinsin? Əməl audit jurnalına yazılır.": t(
            "Remove “%(name)s” (%(day)s) from the calendar? The action is recorded in the audit log.",
            "Удалить «%(name)s» (%(day)s) из календаря? Действие записывается в журнал аудита.",
            "“%(name)s” (%(day)s) takvimden silinsin mi? İşlem denetim günlüğüne yazılır.",
            "„%(name)s“ (%(day)s) aus dem Kalender entfernen? Die Aktion wird im Audit-Protokoll erfasst.",
        ),
        "Sil: %(name)s": t("Remove: %(name)s", "Удалить: %(name)s", "Kaldır: %(name)s", "Entfernen: %(name)s"),
        "Bu tədris ili üçün bayram və qeyri-iş günü daxil edilməyib.": t(
            "No holidays or days off have been entered for this academic year.",
            "Для этого учебного года праздники и нерабочие дни не внесены.",
            "Bu öğretim yılı için tatil ve çalışılmayan gün girilmemiş.",
            "Für dieses Studienjahr wurden keine Feiertage oder arbeitsfreien Tage eingetragen.",
        ),
        "Bayram / qeyri-iş günü": t(
            "Holiday / day off", "Праздник / нерабочий день", "Tatil / çalışılmayan gün", "Feiertag / freier Tag"
        ),
        "Tarix təqvimdə bir dəfə ola bilər; dəyişiklik audit jurnalına yazılır.": t(
            "A date can appear in the calendar only once; changes are recorded in the audit log.",
            "Дата может быть в календаре только один раз; изменения записываются в журнал аудита.",
            "Bir tarih takvimde yalnızca bir kez yer alabilir; değişiklikler denetim günlüğüne yazılır.",
            "Ein Datum kann nur einmal im Kalender stehen; Änderungen werden im Audit-Protokoll erfasst.",
        ),
        "Rəsmi bayramları əlavə et": t(
            "Add public holidays",
            "Добавить государственные праздники",
            "Resmî tatilleri ekle",
            "Gesetzliche Feiertage hinzufügen",
        ),
        "Seçilmiş tədris ilinin sabit tarixli bayramları əlavə olunur; mövcud tarixlərə toxunulmur.": t(
            "Fixed-date holidays of the selected academic year are added; existing dates are left untouched.",
            "Добавляются праздники выбранного учебного года с фиксированной датой; существующие даты не изменяются.",
            "Seçilen öğretim yılının sabit tarihli tatilleri eklenir; mevcut tarihlere dokunulmaz.",
            "Die Feiertage mit festem Datum des gewählten Studienjahres werden hinzugefügt; vorhandene Daten bleiben "
            "unverändert.",
        ),
        "Əlavə et": t("Add", "Добавить", "Ekle", "Hinzufügen"),
        "Tarix": t("Date", "Дата", "Tarih", "Datum"),
        "Növ": t("Type", "Тип", "Tür", "Art"),
        "«İş günü köçürməsi» — şənbə/bazar iş günü elan olunub (yalnız həftə sonu tarixinə yazılır). Köçürmə ilə "
        "istirahət olan iş günü «Qeyri-iş günü»dür.": t(
            "“Transferred working day” — a Saturday/Sunday declared a working day (weekend dates only). A weekday "
            "that becomes a rest day through a transfer is a “Day off”.",
            "«Перенесённый рабочий день» — суббота/воскресенье, объявленные рабочими (только для выходных). Будний "
            "день, ставший выходным из-за переноса, — «Нерабочий день».",
            "“Taşınan iş günü” — iş günü ilan edilmiş cumartesi/pazar (yalnızca hafta sonu tarihine yazılır). "
            "Taşıma nedeniyle tatil olan hafta içi gün “Çalışılmayan gün”dür.",
            "„Verlegter Arbeitstag“ — ein zum Arbeitstag erklärter Samstag/Sonntag (nur Wochenenddaten). Ein "
            "Werktag, der durch eine Verlegung frei wird, ist ein „arbeitsfreier Tag“.",
        ),
        "Ad": t("Name", "Название", "Adı", "Bezeichnung"),
        "Ramazan bayramı": t("Ramadan holiday", "Рамазан байрам", "Ramazan Bayramı", "Ramadanfest"),
        "Qeyd": t("Note", "Примечание", "Not", "Notiz"),
        "Məs. Nazirlər Kabinetinin qərarı": t(
            "E.g. Cabinet of Ministers decision",
            "Напр., решение Кабинета министров",
            "Örn. Bakanlar Kurulu kararı",
            "Z. B. Beschluss des Ministerkabinetts",
        ),
        "Sentyabr–dekabr bayramları tədris ilinin birinci ilinə, yanvar–avqust bayramları ikinci ilinə yazılır. "
        "Ramazan və Qurban bayramları, hökumətin iş günü köçürmələri əlavə olunmur — onları əl ilə daxil edin.": t(
            "September–December holidays go to the first year of the academic year, January–August holidays to the "
            "second. Ramadan and Gurban holidays and government working-day transfers are not added — enter them "
            "manually.",
            "Праздники сентября–декабря относятся к первому году учебного года, января–августа — ко второму. "
            "Рамазан, Гурбан и правительственные переносы рабочих дней не добавляются — внесите их вручную.",
            "Eylül–aralık tatilleri öğretim yılının ilk yılına, ocak–ağustos tatilleri ikinci yılına yazılır. "
            "Ramazan ve Kurban bayramları ile hükümetin iş günü taşımaları eklenmez — bunları elle girin.",
            "Feiertage von September bis Dezember gehören zum ersten Jahr des Studienjahres, Januar bis August zum "
            "zweiten. Ramadan- und Opferfest sowie staatliche Verlegungen von Arbeitstagen werden nicht hinzugefügt "
            "— tragen Sie sie manuell ein.",
        ),
    },
    SEM: {
        "və daha %(n)d": t("and %(n)d more", "и ещё %(n)d", "ve %(n)d tane daha", "und %(n)d weitere"),
        "Bu qəbul ili üçün təsdiqlənmiş plan yoxdur — ən son plan tətbiq olundu: %(groups)s.": t(
            "There is no approved plan for this admission year — the latest plan was applied: %(groups)s.",
            "Для этого года приёма нет утверждённого плана — применён последний план: %(groups)s.",
            "Bu kabul yılı için onaylanmış plan yok — en son plan uygulandı: %(groups)s.",
            "Für diesen Aufnahmejahrgang gibt es keinen genehmigten Plan — der neueste Plan wurde angewendet: "
            "%(groups)s.",
        ),
        "Qrupun qəbul ili bilinmir (ad və ayarda yoxdur) — ən son plan tətbiq olundu: %(groups)s.": t(
            "The group's admission year is unknown (not in the name or settings) — the latest plan was applied: "
            "%(groups)s.",
            "Год приёма группы неизвестен (нет ни в названии, ни в настройках) — применён последний план: %(groups)s.",
            "Grubun kabul yılı bilinmiyor (adda ve ayarlarda yok) — en son plan uygulandı: %(groups)s.",
            "Der Aufnahmejahrgang der Gruppe ist unbekannt (weder im Namen noch in den Einstellungen) — der neueste "
            "Plan wurde angewendet: %(groups)s.",
        ),
        "%(n)d açılışın fənni qrupun öz qəbul ili planının bu semestrində yoxdur (əvvəlki qayda ilə ən son plandan "
        "yaradılıb). Açılışlar avtomatik silinmir — lazımsızdırsa «Ləğv et» ilə ləğv edin.": t(
            "%(n)d offerings have a subject that is not in this semester of the group's own admission-year plan "
            "(created from the latest plan under the previous rule). Offerings are not deleted automatically — "
            "cancel unneeded ones with “Cancel”.",
            "У %(n)d открытий дисциплина отсутствует в этом семестре плана года приёма группы (созданы по прежнему "
            "правилу из последнего плана). Открытия не удаляются автоматически — ненужные отмените кнопкой "
            "«Отменить».",
            "%(n)d açılışın dersi, grubun kendi kabul yılı planının bu yarıyılında yok (önceki kuralla en son plandan "
            "oluşturuldu). Açılışlar otomatik silinmez — gereksizse “İptal et” ile iptal edin.",
            "Bei %(n)d Angeboten ist das Fach nicht in diesem Semester des Plans des eigenen Aufnahmejahrgangs der "
            "Gruppe enthalten (nach der bisherigen Regel aus dem neuesten Plan erstellt). Angebote werden nicht "
            "automatisch gelöscht — nicht benötigte mit „Stornieren“ stornieren.",
        ),
        "Yuxarıdakı süzgəcdən semestri seçin. «Plandan açılış yarat» həmin semestri oxuyan (kursu uyğun) hər qrup "
        "üçün qrupun ÖZ qəbul ilinin təsdiqlənmiş tədris planının (yoxdursa ən son planın) məcburi fənlərindən açılış "
        "yaradır və qrupun aktiv tələbələrini dərhal qeydiyyata alır; seçmə fənlər qrupun seçimi ilə açılır. Mövcud "
        "sətir təkrarlanmır, heç nə silinmir. «Plan yoxdur» ixtisaslar üçün sətir yaranmır — əvvəlcə «Tədris planı» "
        "bölməsində planı təsdiqləyin.": t(
            "Select the semester in the filter above. “Create offerings from plan” creates offerings for every group "
            "studying that semester (matching year of study) from the compulsory subjects of the approved curriculum "
            "of the group's OWN admission year (or the latest plan if there is none) and immediately enrols the "
            "group's active students; electives open according to the group's choice. Existing rows are not "
            "duplicated, nothing is deleted. No rows are created for programmes with “No plan” — approve the plan in "
            "the “Curriculum” section first.",
            "Выберите семестр в фильтре выше. «Создать открытия по плану» создаёт открытия для каждой группы, "
            "изучающей этот семестр (подходящий курс), из обязательных дисциплин утверждённого учебного плана "
            "СОБСТВЕННОГО года приёма группы (если его нет — последнего плана) и сразу зачисляет активных студентов "
            "группы; элективы открываются по выбору группы. Существующие строки не дублируются, ничего не удаляется. "
            "Для специальностей «Нет плана» строки не создаются — сначала утвердите план в разделе «Учебный план».",
            "Yukarıdaki filtreden yarıyılı seçin. “Plandan açılış oluştur”, o yarıyılı okuyan (sınıfı uygun) her grup "
            "için grubun KENDİ kabul yılının onaylanmış öğretim planındaki (yoksa en son plandaki) zorunlu derslerden "
            "açılış oluşturur ve grubun aktif öğrencilerini hemen kaydeder; seçmeli dersler grubun seçimine göre "
            "açılır. Mevcut satır tekrarlanmaz, hiçbir şey silinmez. “Plan yok” programlar için satır oluşturulmaz — "
            "önce “Öğretim planı” bölümünde planı onaylayın.",
            "Wählen Sie das Semester im Filter oben. „Angebote aus dem Plan erstellen“ erstellt für jede Gruppe, die "
            "dieses Semester studiert (passendes Studienjahr), Angebote aus den Pflichtfächern des genehmigten "
            "Studienplans des EIGENEN Aufnahmejahrgangs der Gruppe (falls keiner vorhanden ist, des neuesten Plans) "
            "und schreibt die aktiven Studierenden der Gruppe sofort ein; Wahlfächer werden nach Wahl der Gruppe "
            "geöffnet. Vorhandene Zeilen werden nicht dupliziert, nichts wird gelöscht. Für Studiengänge mit „Kein "
            "Plan“ entstehen keine Zeilen — genehmigen Sie zuerst den Plan im Bereich „Studienplan“.",
        ),
        "Xatırlatma göndərildi: %(teachers)d müəllimə, %(chair)d kafedra əməkdaşına, %(schedule)d cədvəl quran "
        "əməkdaşa (dekanlıq / koordinator).": t(
            "Reminder sent: to %(teachers)d teachers, %(chair)d department staff and %(schedule)d timetable builders "
            "(dean's office / coordinator).",
            "Напоминание отправлено: преподавателям — %(teachers)d, сотрудникам кафедры — %(chair)d, составителям "
            "расписания (деканат / координатор) — %(schedule)d.",
            "Hatırlatma gönderildi: %(teachers)d öğretim elemanına, %(chair)d bölüm çalışanına, %(schedule)d ders "
            "programını hazırlayan çalışana (dekanlık / koordinatör).",
            "Erinnerung gesendet: an %(teachers)d Lehrkräfte, %(chair)d Mitarbeitende des Lehrstuhls und "
            "%(schedule)d Stundenplanersteller (Dekanat / Koordination).",
        ),
        "%(program)s · %(year)s qəbulu · semestr %(n)d": t(
            "%(program)s · %(year)s intake · semester %(n)d",
            "%(program)s · приём %(year)s · семестр %(n)d",
            "%(program)s · %(year)s girişi · yarıyıl %(n)d",
            "%(program)s · Jahrgang %(year)s · Semester %(n)d",
        ),
        "Qəbul ili planı": t(
            "Admission-year plan", "План года приёма", "Kabul yılı planı", "Plan des Aufnahmejahrgangs"
        ),
        "Hər qrup öz qəbul ilinin təsdiqlənmiş planından açılır.": t(
            "Each group is opened from the approved plan of its own admission year.",
            "Каждая группа открывается по утверждённому плану своего года приёма.",
            "Her grup kendi kabul yılının onaylanmış planından açılır.",
            "Jede Gruppe wird aus dem genehmigten Plan ihres eigenen Aufnahmejahrgangs eröffnet.",
        ),
        "Nümunə:": t("Example:", "Пример:", "Örnek:", "Beispiel:"),
        "Hər qrup üçün qrupun öz qəbul ilinin TƏSDİQLƏNMİŞ planından açılış sətirləri yaradılır (həmin il üçün plan "
        "yoxdursa — ən son plandan, xəbərdarlıqla). Əməl idempotentdir — mövcud açılış təkrarlanmır və heç nə "
        "silinmir.": t(
            "Offering rows are created for each group from the APPROVED plan of the group's own admission year (if "
            "there is no plan for that year — from the latest plan, with a warning). The action is idempotent — "
            "existing offerings are not duplicated and nothing is deleted.",
            "Для каждой группы строки открытий создаются по УТВЕРЖДЁННОМУ плану её собственного года приёма (если "
            "для этого года плана нет — по последнему плану, с предупреждением). Действие идемпотентно — "
            "существующие открытия не дублируются, ничего не удаляется.",
            "Her grup için grubun kendi kabul yılının ONAYLANMIŞ planından açılış satırları oluşturulur (o yıl için "
            "plan yoksa — en son plandan, uyarıyla). İşlem idempotenttir — mevcut açılış tekrarlanmaz ve hiçbir şey "
            "silinmez.",
            "Für jede Gruppe werden Angebotszeilen aus dem GENEHMIGTEN Plan ihres eigenen Aufnahmejahrgangs erstellt "
            "(gibt es für dieses Jahr keinen Plan — aus dem neuesten Plan, mit Warnung). Die Aktion ist idempotent — "
            "vorhandene Angebote werden nicht dupliziert und nichts wird gelöscht.",
        ),
        "Xatırlatma göndərilsin? Müəllimlərə — sillabus / jurnal, kafedra rəhbərinə — xülasə, cədvəli olmayan fənlər "
        "üçün isə cədvəli quran dekanlıq / koordinatora. Eyni kafedraya 12 saatda bir dəfə göndərilir.": t(
            "Send the reminder? Teachers get syllabus / journal items, the head of department a summary, and the "
            "dean's office / coordinator who builds the timetable gets subjects without a timetable. The same "
            "department can be reminded once every 12 hours.",
            "Отправить напоминание? Преподавателям — силлабус / журнал, заведующему кафедрой — сводка, а деканату / "
            "координатору, составляющему расписание, — дисциплины без расписания. Одной кафедре — не чаще раза в "
            "12 часов.",
            "Hatırlatma gönderilsin mi? Öğretim elemanlarına — izlence / yoklama defteri, bölüm başkanına — özet, ders "
            "programı olmayan dersler için ise programı hazırlayan dekanlık / koordinatöre. Aynı bölüme 12 saatte bir "
            "gönderilir.",
            "Erinnerung senden? Lehrkräfte erhalten Syllabus / Klassenbuch, die Lehrstuhlleitung eine Übersicht und "
            "das Dekanat / die Koordination, die den Stundenplan erstellt, die Fächer ohne Stundenplan. Derselbe "
            "Lehrstuhl kann einmal alle 12 Stunden erinnert werden.",
        ),
    },
    LOG: {
        "Keçmiş tarixə dərs sütununu yalnız RİM rəhbəri aça bilər (audit izinə düşür). «Akademik təqvim»də qeyd "
        "olunmuş bayram və qeyri-iş günləri burada sayılmır.": t(
            "Only the RİM head can open a lesson column for a past date (it is audited). Holidays and days off "
            "entered in the “Academic calendar” are not counted here.",
            "Открыть столбец занятия за прошедшую дату может только руководитель РИМ (попадает в аудит). Праздники и "
            "нерабочие дни, отмеченные в «Академическом календаре», здесь не учитываются.",
            "Geçmiş tarihe ders sütununu yalnızca RİM başkanı açabilir (denetim kaydına düşer). “Akademik takvim”de "
            "işaretlenen tatiller ve çalışılmayan günler burada sayılmaz.",
            "Nur die RİM-Leitung kann eine Unterrichtsspalte für ein vergangenes Datum öffnen (wird im Audit "
            "erfasst). Im „Akademischen Kalender“ eingetragene Feiertage und arbeitsfreie Tage werden hier nicht "
            "gezählt.",
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
