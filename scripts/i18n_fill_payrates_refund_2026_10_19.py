#!/usr/bin/env python3
"""EMSArena i18n — «Mühasibatlıq» → «Dərs saatının ödəniş dərəcələri» (ilkin məbləğ, KPI, dərəcə kartı, ixrac) və
25% → «Ödənişin qaytarılması qərarı» (qərar, «Qaytarılacaq ödənişlər» növbəsi, «Qaytarıldı», bildirişlər), 2026-10-19.

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`. ⚠️ `makemessages` İŞLƏDİLMİR.
İstifadə:  python scripts/i18n_fill_payrates_refund_2026_10_19.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

AC = "accounts.accounting"
META = "accounts.model.pay_rate.meta"
PERM = "organizations.permission.label"
RT = "registrar.retake"
RTN = "registrar.retake.notification"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    AC: {
        "Dərs saatının ödəniş dərəcələri": t(
            "Teaching hour pay rates",
            "Ставки оплаты учебного часа",
            "Ders saati ücret oranları",
            "Stundensätze für Lehre",
        ),
        "Hesablanmış məbləğ": t("Calculated amount", "Рассчитанная сумма", "Hesaplanan tutar", "Berechneter Betrag"),
        "{n} müəllim · ilkin hesablama": t(
            "{n} teachers · preliminary calculation",
            "{n} преп. · предварительный расчёт",
            "{n} öğretmen · ön hesaplama",
            "{n} Lehrkräfte · vorläufige Berechnung",
        ),
        "{n} müəllim · dərəcəsi olmayan: {m}": t(
            "{n} teachers · without a rate: {m}",
            "{n} преп. · без ставки: {m}",
            "{n} öğretmen · oranı olmayan: {m}",
            "{n} Lehrkräfte · ohne Satz: {m}",
        ),
        "Məbləğ": t("Amount", "Сумма", "Tutar", "Betrag"),
        "Məbləğ (AZN)": t("Amount (AZN)", "Сумма (AZN)", "Tutar (AZN)", "Betrag (AZN)"),
        "məbləğ, AZN": t("amount, AZN", "сумма, AZN", "tutar, AZN", "Betrag, AZN"),
        "Məbləğ qeydi": t("Amount note", "Примечание к сумме", "Tutar notu", "Hinweis zum Betrag"),
        "Dərəcə (AZN / saat)": t("Rate (AZN / hour)", "Ставка (AZN / час)", "Oran (AZN / saat)", "Satz (AZN / Stunde)"),
        "Dərəcə təyin edilməyib": t("No rate set", "Ставка не задана", "Oran belirlenmedi", "Kein Satz festgelegt"),
        "Dərəcə təyin edilməyib (vəzifə yoxdur)": t(
            "No rate set (no position)",
            "Ставка не задана (нет должности)",
            "Oran belirlenmedi (unvan yok)",
            "Kein Satz festgelegt (keine Stelle)",
        ),
        "Dərəcə təyin edilməyib: {kinds}": t(
            "No rate set: {kinds}",
            "Ставка не задана: {kinds}",
            "Oran belirlenmedi: {kinds}",
            "Kein Satz festgelegt: {kinds}",
        ),
        "Saathesabı müəllim — bütün saatlar saathesabı ödənilir.": t(
            "Hourly-paid teacher — all hours are paid hourly.",
            "Почасовик — все часы оплачиваются почасово.",
            "Saat ücretli öğretmen — tüm saatler saat ücretiyle ödenir.",
            "Honorarlehrkraft — alle Stunden werden stundenweise vergütet.",
        ),
        "Plan üzrə bütün saatlar ştat yükündədir.": t(
            "By plan, all hours are within the staff load.",
            "По плану все часы входят в штатную нагрузку.",
            "Plana göre tüm saatler kadro yükü içindedir.",
            "Laut Plan liegen alle Stunden im Stellendeputat.",
        ),
        "Plan üzrə (semestr): ştat yükü {norm} saat, saathesabı {hourly} saat.": t(
            "By plan (semester): staff load {norm} h, hourly-paid {hourly} h.",
            "По плану (семестр): штатная нагрузка {norm} ч, почасовая {hourly} ч.",
            "Plana göre (dönem): kadro yükü {norm} saat, saat ücretli {hourly} saat.",
            "Laut Plan (Semester): Stellendeputat {norm} Std., Honorar {hourly} Std.",
        ),
        "İlkin hesablama — rəsmi əmək haqqı hesabı deyil.": t(
            "Preliminary calculation — not an official payroll statement.",
            "Предварительный расчёт — не официальный расчёт зарплаты.",
            "Ön hesaplama — resmi maaş bordrosu değildir.",
            "Vorläufige Berechnung — keine offizielle Gehaltsabrechnung.",
        ),
        "Bütün növlər": t("All kinds", "Все виды", "Tüm türler", "Alle Arten"),
        "Saat dərəcəsini yazın (AZN).": t(
            "Enter the hourly rate (AZN).",
            "Укажите ставку за час (AZN).",
            "Saat oranını girin (AZN).",
            "Stundensatz eingeben (AZN).",
        ),
        "Dərəcə rəqəm olmalıdır.": t(
            "The rate must be a number.",
            "Ставка должна быть числом.",
            "Oran bir sayı olmalıdır.",
            "Der Satz muss eine Zahl sein.",
        ),
        "Dərəcə 0-dan böyük və 10 000 AZN-dən az olmalıdır.": t(
            "The rate must be above 0 and below 10,000 AZN.",
            "Ставка должна быть больше 0 и меньше 10 000 AZN.",
            "Oran 0'dan büyük ve 10.000 AZN'den küçük olmalıdır.",
            "Der Satz muss über 0 und unter 10.000 AZN liegen.",
        ),
        "Tədris ilini seçin (akademik dövrlərdə olan il).": t(
            "Choose an academic year (one that has academic periods).",
            "Выберите учебный год (из академических периодов).",
            "Öğretim yılını seçin (akademik dönemlerdeki yıl).",
            "Studienjahr wählen (eines mit akademischen Perioden).",
        ),
        "Vəzifəni seçin.": t("Choose a position.", "Выберите должность.", "Unvanı seçin.", "Stelle wählen."),
        "Dərs növü düzgün deyil.": t(
            "Invalid class type.", "Неверный вид занятия.", "Ders türü geçersiz.", "Ungültige Lehrveranstaltungsart."
        ),
        "Bu dərəcə artıq qüvvədədir — dəyişiklik yoxdur.": t(
            "This rate is already in force — nothing changed.",
            "Эта ставка уже действует — изменений нет.",
            "Bu oran zaten yürürlükte — değişiklik yok.",
            "Dieser Satz gilt bereits — keine Änderung.",
        ),
        "Bu dərəcə eyni anda başqa istifadəçi tərəfindən dəyişdirilib.": t(
            "This rate was changed by another user at the same time.",
            "Эту ставку одновременно изменил другой пользователь.",
            "Bu oran aynı anda başka bir kullanıcı tarafından değiştirildi.",
            "Dieser Satz wurde gleichzeitig von einem anderen Benutzer geändert.",
        ),
        "Yeni dərəcə ilə əvəzləndi": t(
            "Replaced by a new rate", "Заменена новой ставкой", "Yeni oranla değiştirildi", "Durch neuen Satz ersetzt"
        ),
        "Ləğv edildi": t("Cancelled", "Отменена", "İptal edildi", "Aufgehoben"),
        "Ödəniş dərəcələrini yalnız Mühasibatlıq dəyişə bilər.": t(
            "Only Accounting can change pay rates.",
            "Изменять ставки оплаты может только бухгалтерия.",
            "Ücret oranlarını yalnızca Muhasebe değiştirebilir.",
            "Nur die Buchhaltung kann Vergütungssätze ändern.",
        ),
        "Başqasının adından baxış rejimində dəyişiklik etmək olmaz.": t(
            "Changes are not allowed in view-as mode.",
            "В режиме просмотра от имени другого изменения запрещены.",
            "Başkası adına görüntüleme modunda değişiklik yapılamaz.",
            "Im Ansicht-als-Modus sind keine Änderungen möglich.",
        ),
        "Dərəcə tapılmadı.": t("Rate not found.", "Ставка не найдена.", "Oran bulunamadı.", "Satz nicht gefunden."),
        "Ödəniş dərəcəsi yadda saxlanıldı.": t(
            "Pay rate saved.", "Ставка оплаты сохранена.", "Ücret oranı kaydedildi.", "Vergütungssatz gespeichert."
        ),
        "Dərəcə ləğv edildi — tarixçədə qalır.": t(
            "Rate cancelled — it stays in the history.",
            "Ставка отменена — остаётся в истории.",
            "Oran iptal edildi — geçmişte kalır.",
            "Satz aufgehoben — bleibt im Verlauf.",
        ),
        "Vəzifə": t("Position", "Должность", "Unvan", "Stelle"),
        "Saathesabı plan (semestr, saat)": t(
            "Hourly-paid plan (semester, h)",
            "Почасовой план (семестр, ч)",
            "Saat ücretli plan (dönem, saat)",
            "Honorarplan (Semester, Std.)",
        ),
        "Tədris ili": t("Academic year", "Учебный год", "Öğretim yılı", "Studienjahr"),
        "Qeyd": t("Note", "Примечание", "Not", "Notiz"),
        "Əlavə edib": t("Added by", "Добавил(а)", "Ekleyen", "Hinzugefügt von"),
        "Dərəcə id": t("Rate ID", "ID ставки", "Oran kimliği", "Satz-ID"),
        "Dərəcələr": t("Rates", "Ставки", "Oranlar", "Sätze"),
        "Məbləğ = keçirilmiş saat × dərəcə (tədris ili × vəzifə × növ; növə xas dərəcə yoxdursa «bütün növlər» "
        "dərəcəsi). Vəzifə «Yük bölgüsü»ndəki müəllim profilindən götürülür. Dərəcə və ya vəzifə yoxdursa məbləğ boş "
        "qalır.": t(
            "Amount = hours held × rate (academic year × position × kind; if there is no kind-specific rate, the “all "
            "kinds” rate). The position comes from the teacher profile in “Load distribution”. Without a rate or "
            "position the amount stays empty.",
            "Сумма = проведённые часы × ставка (учебный год × должность × вид; если нет ставки для вида — ставка «все "
            "виды»). Должность берётся из профиля преподавателя в «Распределении нагрузки». Без ставки или должности "
            "сумма остаётся пустой.",
            "Tutar = yapılan saat × oran (öğretim yılı × unvan × tür; türe özel oran yoksa «tüm türler» oranı). Unvan "
            "«Yük dağılımı»ndaki öğretmen profilinden alınır. Oran veya unvan yoksa tutar boş kalır.",
            "Betrag = gehaltene Stunden × Satz (Studienjahr × Stelle × Art; ohne artspezifischen Satz gilt der Satz "
            "„alle Arten“). Die Stelle stammt aus dem Lehrkraftprofil in der „Lastverteilung“. Ohne Satz oder Stelle "
            "bleibt der Betrag leer.",
        ),
        "Dərəcəsi olmayan vəzifələr": t(
            "Positions without a rate", "Должности без ставки", "Oranı olmayan unvanlar", "Stellen ohne Satz"
        ),
        "Qüvvədə olan ödəniş dərəcələri — %(year)s": t(
            "Pay rates in force — %(year)s",
            "Действующие ставки оплаты — %(year)s",
            "Yürürlükteki ücret oranları — %(year)s",
            "Geltende Vergütungssätze — %(year)s",
        ),
        "Əməl": t("Action", "Действие", "İşlem", "Aktion"),
        "Dərəcə ləğv edilsin? Sətir tarixçədə qalır, keçmiş ixraclar dəyişmir.": t(
            "Cancel this rate? The row stays in the history; past exports do not change.",
            "Отменить ставку? Строка останется в истории, прошлые выгрузки не изменятся.",
            "Oran iptal edilsin mi? Satır geçmişte kalır, eski dışa aktarmalar değişmez.",
            "Satz aufheben? Die Zeile bleibt im Verlauf, frühere Exporte ändern sich nicht.",
        ),
        "Ləğv et": t("Cancel rate", "Отменить", "İptal et", "Aufheben"),
        "Bu tədris ili üçün dərəcə yoxdur": t(
            "No rates for this academic year",
            "Для этого учебного года ставок нет",
            "Bu öğretim yılı için oran yok",
            "Für dieses Studienjahr gibt es keine Sätze",
        ),
        "Dərəcə olmadan cədvəldə və ixracda «Dərəcə təyin edilməyib» görünür, məbləğ hesablanmır.": t(
            "Without a rate the table and the export show “No rate set” and no amount is calculated.",
            "Без ставки в таблице и выгрузке видно «Ставка не задана», сумма не считается.",
            "Oran olmadan tabloda ve dışa aktarmada «Oran belirlenmedi» görünür, tutar hesaplanmaz.",
            "Ohne Satz zeigen Tabelle und Export „Kein Satz festgelegt“, es wird kein Betrag berechnet.",
        ),
        "Dərəcə əlavə et və ya dəyiş": t(
            "Add or change a rate",
            "Добавить или изменить ставку",
            "Oran ekle veya değiştir",
            "Satz hinzufügen oder ändern",
        ),
        "Məs. rektorun əmri № …": t(
            "E.g. rector's order No. …",
            "Напр., приказ ректора № …",
            "Örn. rektörün emri No. …",
            "Z. B. Anordnung des Rektors Nr. …",
        ),
        "Eyni il, vəzifə və növ üçün dərəcə artıq varsa, köhnəsi arxivə düşür və yenisi qüvvəyə minir.": t(
            "If a rate already exists for the same year, position and kind, the old one is archived and the new one "
            "takes effect.",
            "Если ставка для того же года, должности и вида уже есть, старая уходит в архив, а новая вступает в силу.",
            "Aynı yıl, unvan ve tür için oran zaten varsa eskisi arşivlenir ve yenisi yürürlüğe girer.",
            "Gibt es bereits einen Satz für dasselbe Jahr, dieselbe Stelle und Art, wird der alte archiviert und der "
            "neue gilt.",
        ),
        "Yadda saxla": t("Save", "Сохранить", "Kaydet", "Speichern"),
        "Dərəcələri Mühasibatlıq (və RİM rəhbəri) dəyişir; siz yalnız baxırsınız.": t(
            "Rates are changed by Accounting (and the IT head); you can only view them.",
            "Ставки меняет бухгалтерия (и руководитель ИТ); вы только просматриваете.",
            "Oranları Muhasebe (ve BT yöneticisi) değiştirir; siz yalnızca görüntülersiniz.",
            "Sätze ändert die Buchhaltung (und die IT-Leitung); Sie können sie nur ansehen.",
        ),
        "Tarixçə": t("History", "История", "Geçmiş", "Verlauf"),
        "Yadda saxlanılmadı — icazənizi yoxlayın və ya səhifəni yeniləyin.": t(
            "Not saved — check your permission or reload the page.",
            "Не сохранено — проверьте права или обновите страницу.",
            "Kaydedilmedi — yetkinizi kontrol edin veya sayfayı yenileyin.",
            "Nicht gespeichert — prüfen Sie Ihre Berechtigung oder laden Sie die Seite neu.",
        ),
        "Məbləğ — dövrün keçirilmiş saatı × «Dərs saatının ödəniş dərəcələri» cədvəlindəki dərəcə (tədris ili × "
        "müəllimin vəzifəsi × növ). Vəzifə və ya dərəcə yoxdursa məbləğ boş qalır («Dərəcə təyin edilməyib»), 0 "
        "yazılmır. Saathesabı və ştat saatları plan üzrə etiketlənir (jurnal dərsi konkret yük sətrinə bağlı deyil). "
        "İlkin hesablamadır — rəsmi əmək haqqı hesabı deyil.": t(
            "Amount — hours held in the period × the rate from “Teaching hour pay rates” (academic year × teacher's "
            "position × kind). Without a position or rate the amount stays empty (“No rate set”), never 0. Hourly-paid "
            "and staff hours are labelled by plan (a journal class is not tied to a specific load line). This is a "
            "preliminary calculation — not an official payroll statement.",
            "Сумма — проведённые за период часы × ставка из таблицы «Ставки оплаты учебного часа» (учебный год × "
            "должность преподавателя × вид). Без должности или ставки сумма пуста («Ставка не задана»), 0 не пишется. "
            "Почасовые и штатные часы помечаются по плану (занятие в журнале не привязано к строке нагрузки). Это "
            "предварительный расчёт, а не официальный расчёт зарплаты.",
            "Tutar — dönemde yapılan saat × «Ders saati ücret oranları» tablosundaki oran (öğretim yılı × öğretmenin "
            "unvanı × tür). Unvan veya oran yoksa tutar boş kalır («Oran belirlenmedi»), 0 yazılmaz. Saat ücretli ve "
            "kadro saatleri plana göre etiketlenir (yoklama dersi belirli bir yük satırına bağlı değildir). Ön "
            "hesaplamadır — resmi maaş bordrosu değildir.",
            "Betrag — im Zeitraum gehaltene Stunden × Satz aus „Stundensätze für Lehre“ (Studienjahr × Stelle der "
            "Lehrkraft × Art). Ohne Stelle oder Satz bleibt der Betrag leer („Kein Satz festgelegt“), nie 0. Honorar- "
            "und Deputatsstunden werden laut Plan gekennzeichnet (eine Journalstunde ist keiner Lastzeile zugeordnet). "
            "Vorläufige Berechnung — keine offizielle Gehaltsabrechnung.",
        ),
        "Aylıq plan — semestr planı dərs pəncərəsinin (semestrin başlanğıcından imtahan sessiyasına qədər) iş "
        "günlərinə (B.e.–Cümə) mütənasib bölünür; aylıq payların cəmi semestr planına bərabərdir. Bayram və qeyri-iş "
        "günləri (Akademik təqvim) iş günü sayılmır, iş günü elan olunmuş şənbə / bazar isə sayılır.": t(
            "Monthly plan — the semester plan is split in proportion to the working days (Mon–Fri) of the teaching "
            "window (from the start of the semester to the exam session); the monthly shares add up to the semester "
            "plan. Holidays and non-working days (Academic calendar) are not counted as working days, while a Saturday "
            "/ Sunday declared a working day is counted.",
            "Месячный план — семестровый план делится пропорционально рабочим дням (Пн–Пт) учебного окна (от начала "
            "семестра до сессии); сумма месячных долей равна семестровому плану. Праздничные и нерабочие дни "
            "(Академический календарь) не считаются рабочими, а объявленные рабочими суббота / воскресенье считаются.",
            "Aylık plan — dönem planı, ders penceresinin (dönem başından sınav dönemine kadar) iş günlerine (Pzt–Cum) "
            "orantılı bölünür; aylık payların toplamı dönem planına eşittir. Bayram ve çalışma dışı günler (Akademik "
            "takvim) iş günü sayılmaz, iş günü ilan edilen cumartesi / pazar ise sayılır.",
            "Monatsplan — der Semesterplan wird anteilig auf die Arbeitstage (Mo–Fr) des Lehrfensters (vom "
            "Semesterbeginn bis zur Prüfungsphase) verteilt; die Monatsanteile ergeben zusammen den Semesterplan. "
            "Feiertage und arbeitsfreie Tage (akademischer Kalender) zählen nicht als Arbeitstage, ein zum Arbeitstag "
            "erklärter Samstag / Sonntag zählt.",
        ),
    },
    META: {
        "teaching pay rate": t(
            "teaching pay rate", "ставка оплаты учебного часа", "ders saati ücret oranı", "Stundensatz"
        ),
        "teaching pay rates": t(
            "teaching pay rates", "ставки оплаты учебного часа", "ders saati ücret oranları", "Stundensätze"
        ),
    },
    PERM: {
        "Təhsil haqqı cədvəlini (25% təkrar imtahanın təxmini məbləği) və dərs saatının ödəniş dərəcələrini idarə "
        "etmək": t(
            "Manage the tuition table (estimated 25% resit amount) and teaching hour pay rates",
            "Управление таблицей платы за обучение (ориентировочная сумма пересдачи 25%) и ставками оплаты учебного часа",
            "Öğrenim ücreti tablosunu (%25 bütünleme tahmini tutarı) ve ders saati ücret oranlarını yönetme",
            "Studiengebührentabelle (geschätzter Betrag der 25%-Wiederholung) und Stundensätze für Lehre verwalten",
        ),
    },
    RT: {
        "Cəhd istifadə olunmuş sayılmasın": t(
            "Do not count the attempt as used",
            "Не считать попытку использованной",
            "Hak kullanılmış sayılmasın",
            "Versuch nicht als verbraucht zählen",
        ),
        "Qaytarılma ödənilmiş cəhdin verilmədiyini tanıyır: «İmtahana gəlmədi» ilə sayılmış 25% cəhdi tələbəyə geri "
        "qayıdır. Rədd / geri götürmə cəhd saymır — orada bu seçim təsirsizdir. Qərardan sonra dəyişmir.": t(
            "A refund acknowledges that the paid attempt was not delivered: a 25% attempt counted by “Did not attend the "
            "exam” is given back to the student. Rejection / withdrawal never count an attempt — there this option has "
            "no effect. It cannot be changed after the decision.",
            "Возврат признаёт, что оплаченная попытка не была предоставлена: попытка 25%, засчитанная как «Не явился на "
            "экзамен», возвращается студенту. Отклонение / отзыв попытку не засчитывают — там эта опция ни на что не "
            "влияет. После решения не меняется.",
            "İade, ödenen hakkın verilmediğini kabul eder: «Sınava gelmedi» ile sayılan %25 hakkı öğrenciye geri verilir. "
            "Ret / geri çekme hak saymaz — orada bu seçenek etkisizdir. Karardan sonra değiştirilemez.",
            "Eine Erstattung erkennt an, dass der bezahlte Versuch nicht erbracht wurde: Ein durch „Nicht zur Prüfung "
            "erschienen“ gezählter 25%-Versuch wird dem Studierenden zurückgegeben. Ablehnung / Rückzug zählen nie einen "
            "Versuch — dort ist die Option wirkungslos. Nach der Entscheidung nicht änderbar.",
        ),
        "25% cəhdi istifadə olunmuş sayılır": t(
            "The 25% attempt counts as used",
            "Попытка 25% считается использованной",
            "%25 hakkı kullanılmış sayılır",
            "Der 25%-Versuch gilt als verbraucht",
        ),
        "25% cəhdi istifadə olunmuş sayılmır": t(
            "The 25% attempt does not count as used",
            "Попытка 25% не считается использованной",
            "%25 hakkı kullanılmış sayılmaz",
            "Der 25%-Versuch gilt nicht als verbraucht",
        ),
        "Qaytarılma yoxdur": t("No refund", "Без возврата", "İade yok", "Keine Erstattung"),
        "Ödənişin qaytarılması qərarı verilib": t(
            "Refund decision issued",
            "Решение о возврате оплаты принято",
            "Ödeme iadesi kararı verildi",
            "Erstattungsentscheidung erlassen",
        ),
        "Ödəniş qaytarılıb": t("Payment refunded", "Оплата возвращена", "Ödeme iade edildi", "Zahlung erstattet"),
        "Ödənişin qaytarılması qərarı verildi": t(
            "Refund decision issued",
            "Принято решение о возврате оплаты",
            "Ödeme iadesi kararı verildi",
            "Erstattungsentscheidung erlassen",
        ),
        "Ödəniş qaytarıldı": t("Payment refunded", "Оплата возвращена", "Ödeme iade edildi", "Zahlung erstattet"),
        "Ödənişin qaytarılması qərarı": t(
            "Refund decision", "Решение о возврате оплаты", "Ödeme iadesi kararı", "Erstattungsentscheidung"
        ),
        "Qaytarılacaq ödənişlər": t("Refunds to pay", "Возвраты к выплате", "Yapılacak iadeler", "Offene Erstattungen"),
        "Qaytarılmalı": t("To refund", "К возврату", "İade edilecek", "Zu erstatten"),
        "Qaytarılıb": t("Refunded", "Возвращено", "İade edildi", "Erstattet"),
        "Qaytarıldı": t("Refunded", "Возвращено", "İade edildi", "Erstattet"),
        "Hamısı": t("All", "Все", "Tümü", "Alle"),
        "Ödənilən məbləğ": t("Amount paid", "Оплаченная сумма", "Ödenen tutar", "Gezahlter Betrag"),
        "Qaytarılacaq məbləğ": t(
            "Amount to refund", "Сумма к возврату", "İade edilecek tutar", "Zu erstattender Betrag"
        ),
        "Qaytarılacaq məbləğ (AZN)": t(
            "Amount to refund (AZN)",
            "Сумма к возврату (AZN)",
            "İade edilecek tutar (AZN)",
            "Zu erstattender Betrag (AZN)",
        ),
        "Qaytarılacaq məbləğ: %(amount)s AZN": t(
            "Amount to refund: %(amount)s AZN",
            "Сумма к возврату: %(amount)s AZN",
            "İade edilecek tutar: %(amount)s AZN",
            "Zu erstattender Betrag: %(amount)s AZN",
        ),
        "Qaytarılacaq məbləğ: {amount} AZN.": t(
            "Amount to refund: {amount} AZN.",
            "Сумма к возврату: {amount} AZN.",
            "İade edilecek tutar: {amount} AZN.",
            "Zu erstattender Betrag: {amount} AZN.",
        ),
        "Ödənilib: {amount} AZN.": t(
            "Paid: {amount} AZN.", "Оплачено: {amount} AZN.", "Ödendi: {amount} AZN.", "Gezahlt: {amount} AZN."
        ),
        "Ödənilən məbləğ qeyd olunmayıb — məbləği yazın.": t(
            "The paid amount was not recorded — enter the amount.",
            "Оплаченная сумма не записана — укажите сумму.",
            "Ödenen tutar kaydedilmemiş — tutarı girin.",
            "Der gezahlte Betrag ist nicht erfasst — Betrag eingeben.",
        ),
        "(boş — ödənilənin hamısı)": t(
            "(empty — the full amount paid)",
            "(пусто — вся оплаченная сумма)",
            "(boş — ödenenin tamamı)",
            "(leer — der gesamte gezahlte Betrag)",
        ),
        "qaytarılıb: %(day)s, arayış № %(ref)s": t(
            "refunded: %(day)s, reference No. %(ref)s",
            "возвращено: %(day)s, справка № %(ref)s",
            "iade edildi: %(day)s, dekont No. %(ref)s",
            "erstattet: %(day)s, Beleg Nr. %(ref)s",
        ),
        "Əmr": t("Order", "Приказ", "Emir", "Anordnung"),
        "Qərar": t("Decision", "Решение", "Karar", "Entscheidung"),
        "Qərarı verib": t("Decided by", "Решение принял(а)", "Kararı veren", "Entschieden von"),
        "Bank arayışı / ödəniş tapşırığı №": t(
            "Bank reference / payment order No.",
            "Банковская справка / платёжное поручение №",
            "Banka dekontu / ödeme talimatı No.",
            "Bankbeleg / Zahlungsauftrag Nr.",
        ),
        "Qaytarılma tarixi": t("Refund date", "Дата возврата", "İade tarihi", "Erstattungsdatum"),
        "Qeyd geri alınmır — yalnız pul faktiki qaytarıldıqdan sonra təsdiqləyin.": t(
            "This record cannot be undone — confirm only after the money has actually been returned.",
            "Запись нельзя отменить — подтверждайте только после фактического возврата денег.",
            "Kayıt geri alınamaz — yalnızca para fiilen iade edildikten sonra onaylayın.",
            "Der Eintrag ist endgültig — erst bestätigen, wenn das Geld tatsächlich erstattet wurde.",
        ),
        "Sistem pul köçürmür: qərar qeyd olunur, Mühasibatlıq «Qaytarılacaq ödənişlər» növbəsində icranı «Qaytarıldı» "
        "ilə təsdiqləyir.": t(
            "The system does not move money: the decision is recorded, and Accounting confirms execution with “Refunded” "
            "in the “Refunds to pay” queue.",
            "Система не переводит деньги: решение записывается, бухгалтерия подтверждает исполнение кнопкой «Возвращено» "
            "в очереди «Возвраты к выплате».",
            "Sistem para aktarmaz: karar kaydedilir, Muhasebe «Yapılacak iadeler» kuyruğunda işlemi «İade edildi» ile "
            "onaylar.",
            "Das System überweist kein Geld: Die Entscheidung wird erfasst, die Buchhaltung bestätigt die Ausführung in "
            "der Warteschlange „Offene Erstattungen“ mit „Erstattet“.",
        ),
        "Defolt qaytarılma yoxdur — qaytarılma yalnız rəsmi qərarla: əmr nömrəsi və tarixi və ya qərar sənədi, səbəb "
        "məcburidir. Bir müraciətə bir dəfə.": t(
            "By default there is no refund — a refund only by official decision: an order number and date or a decision "
            "document, and a reason, are required. Once per application.",
            "По умолчанию возврата нет — только по официальному решению: номер и дата приказа или документ решения и "
            "причина обязательны. Один раз на заявку.",
            "Varsayılan olarak iade yoktur — iade yalnızca resmi kararla: emir numarası ve tarihi veya karar belgesi ile "
            "gerekçe zorunludur. Başvuru başına bir kez.",
            "Standardmäßig gibt es keine Erstattung — nur per offizieller Entscheidung: Anordnungsnummer und -datum oder "
            "ein Entscheidungsdokument sowie eine Begründung sind Pflicht. Einmal pro Antrag.",
        ),
        "Defolt qaytarılma yoxdur. Qaytarılma lazımdırsa, bağlanışdan sonra «Ödənişin qaytarılması qərarı» ilə ayrıca "
        "rəsmi qərar verilir (Tədris şöbəsi / RİM).": t(
            "By default there is no refund. If a refund is needed, a separate official “Refund decision” is issued after "
            "the closure (Teaching Office / IT head).",
            "По умолчанию возврата нет. Если возврат нужен, после закрытия принимается отдельное официальное «Решение о "
            "возврате оплаты» (учебный отдел / руководитель ИТ).",
            "Varsayılan olarak iade yoktur. İade gerekiyorsa kapanıştan sonra «Ödeme iadesi kararı» ile ayrı bir resmi "
            "karar verilir (Öğretim birimi / BT yöneticisi).",
            "Standardmäßig gibt es keine Erstattung. Ist eine nötig, wird nach dem Abschluss eine eigene offizielle "
            "„Erstattungsentscheidung“ erlassen (Studienbüro / IT-Leitung).",
        ),
        "Bank arayışı və ya ödəniş tapşırığı nömrəsini yazın.": t(
            "Enter the bank reference or payment order number.",
            "Укажите номер банковской справки или платёжного поручения.",
            "Banka dekontu veya ödeme talimatı numarasını girin.",
            "Bankbeleg- oder Zahlungsauftragsnummer eingeben.",
        ),
        "Bu müraciət üzrə qaytarılma qərarı artıq verilib.": t(
            "A refund decision has already been issued for this application.",
            "По этой заявке решение о возврате уже принято.",
            "Bu başvuru için iade kararı zaten verildi.",
            "Für diesen Antrag wurde bereits eine Erstattungsentscheidung erlassen.",
        ),
        "Bu müraciət üzrə qaytarılma qərarı yoxdur.": t(
            "There is no refund decision for this application.",
            "По этой заявке нет решения о возврате.",
            "Bu başvuru için iade kararı yok.",
            "Für diesen Antrag gibt es keine Erstattungsentscheidung.",
        ),
        "Qaytarılacaq məbləğ ödənilən məbləğdən çox ola bilməz.": t(
            "The refund cannot exceed the amount paid.",
            "Сумма возврата не может превышать оплаченную.",
            "İade tutarı ödenen tutarı aşamaz.",
            "Die Erstattung darf den gezahlten Betrag nicht übersteigen.",
        ),
        "Qaytarılma qərarı yalnız ödənişi təsdiqlənmiş və sonra rədd edilmiş, «İmtahana gəlmədi» və ya qərarla geri "
        "götürülmüş 25% müraciətinə verilir.": t(
            "A refund decision is only possible for a 25% application whose payment was verified and which was then "
            "rejected, marked “Did not attend the exam” or withdrawn by decision.",
            "Решение о возврате принимается только по заявке 25% с подтверждённой оплатой, которая затем отклонена, "
            "отмечена «Не явился на экзамен» или отозвана решением.",
            "İade kararı yalnızca ödemesi onaylanmış ve ardından reddedilmiş, «Sınava gelmedi» olarak işaretlenmiş veya "
            "kararla geri çekilmiş %25 başvurusuna verilir.",
            "Eine Erstattungsentscheidung ist nur für einen 25%-Antrag möglich, dessen Zahlung bestätigt und der danach "
            "abgelehnt, als „Nicht zur Prüfung erschienen“ markiert oder per Entscheidung zurückgezogen wurde.",
        ),
        "Qaytarılma rəsmi qərarla olur: əmr nömrəsi və tarixi və ya qərar sənədi əlavə edin.": t(
            "A refund needs an official decision: add an order number and date or a decision document.",
            "Возврат — только по официальному решению: добавьте номер и дату приказа или документ решения.",
            "İade resmi kararla olur: emir numarası ve tarihi veya karar belgesi ekleyin.",
            "Eine Erstattung braucht eine offizielle Entscheidung: Anordnungsnummer und -datum oder ein "
            "Entscheidungsdokument hinzufügen.",
        ),
        "Qaytarılma tarixi düzgün deyil.": t(
            "Invalid refund date.", "Неверная дата возврата.", "İade tarihi geçersiz.", "Ungültiges Erstattungsdatum."
        ),
        "Qaytarılma tarixi gələcəkdə ola bilməz.": t(
            "The refund date cannot be in the future.",
            "Дата возврата не может быть в будущем.",
            "İade tarihi gelecekte olamaz.",
            "Das Erstattungsdatum darf nicht in der Zukunft liegen.",
        ),
        "Qaytarılma tarixi qərar tarixindən əvvəl ola bilməz.": t(
            "The refund date cannot be before the decision date.",
            "Дата возврата не может быть раньше даты решения.",
            "İade tarihi karar tarihinden önce olamaz.",
            "Das Erstattungsdatum darf nicht vor dem Entscheidungsdatum liegen.",
        ),
        "Qaytarılma tarixini yazın.": t(
            "Enter the refund date.", "Укажите дату возврата.", "İade tarihini girin.", "Erstattungsdatum eingeben."
        ),
        "Ödəniş artıq qaytarılmış kimi qeyd olunub.": t(
            "The payment is already recorded as refunded.",
            "Оплата уже отмечена как возвращённая.",
            "Ödeme zaten iade edilmiş olarak kaydedildi.",
            "Die Zahlung ist bereits als erstattet erfasst.",
        ),
        "Qaytarılma qərarı yazıldı — Mühasibatlığa bildiriş göndərildi.": t(
            "Refund decision recorded — Accounting has been notified.",
            "Решение о возврате записано — бухгалтерия уведомлена.",
            "İade kararı kaydedildi — Muhasebeye bildirim gönderildi.",
            "Erstattungsentscheidung erfasst — die Buchhaltung wurde benachrichtigt.",
        ),
        "Ödəniş qaytarılmış kimi qeyd olundu.": t(
            "Payment recorded as refunded.",
            "Оплата отмечена как возвращённая.",
            "Ödeme iade edildi olarak kaydedildi.",
            "Zahlung als erstattet erfasst.",
        ),
    },
    RTN: {
        "Ödənişin qaytarılması qərarı verildi": t(
            "Refund decision issued",
            "Принято решение о возврате оплаты",
            "Ödeme iadesi kararı verildi",
            "Erstattungsentscheidung erlassen",
        ),
        "Ödəniş qaytarıldı": t("Payment refunded", "Оплата возвращена", "Ödeme iade edildi", "Zahlung erstattet"),
        "Qaytarılacaq ödəniş növbədədir": t(
            "A refund is waiting in the queue",
            "Возврат оплаты ожидает в очереди",
            "Kuyrukta bekleyen bir iade var",
            "Eine Erstattung wartet in der Warteschlange",
        ),
        "{student} — {message}": t(
            "{student} — {message}", "{student} — {message}", "{student} — {message}", "{student} — {message}"
        ),
        '"{subject}" — 25% ödənişi qaytarıldı: {amount} AZN ({date}).': t(
            '"{subject}" — the 25% payment was refunded: {amount} AZN ({date}).',
            "«{subject}» — оплата 25% возвращена: {amount} AZN ({date}).",
            '"{subject}" — %25 ödemesi iade edildi: {amount} AZN ({date}).',
            "„{subject}“ — die 25%-Zahlung wurde erstattet: {amount} AZN ({date}).",
        ),
        '"{subject}" — 25% ödənişinin qaytarılması qərarı: {amount} AZN. Mühasibatlıq icra edəcək.': t(
            '"{subject}" — decision to refund the 25% payment: {amount} AZN. Accounting will process it.',
            "«{subject}» — решение о возврате оплаты 25%: {amount} AZN. Бухгалтерия исполнит его.",
            '"{subject}" — %25 ödemesinin iadesi kararı: {amount} AZN. Muhasebe işleme alacak.',
            "„{subject}“ — Entscheidung zur Erstattung der 25%-Zahlung: {amount} AZN. Die Buchhaltung führt sie aus.",
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
