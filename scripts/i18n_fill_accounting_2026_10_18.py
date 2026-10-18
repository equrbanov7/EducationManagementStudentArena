#!/usr/bin/env python3
"""EMSArena i18n — «Mühasibatlıq» bölməsi + «Mühasib» rolu + `accounting.view` / `retake.*` açarları (2026-10-18).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

AC = "accounts.accounting"
PERM = "organizations.permission.label"
SIDEBAR = "profile.sidebar"
STATUS = "ui.status"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    PERM: {
        "Mühasibatlıq bölməsi (müəllimlərin aylıq keçirilmiş dərs saatı, plan, ixrac)": t(
            "Accounting section (teachers' monthly taught hours, plan, export)",
            "Раздел «Бухгалтерия» (проведённые часы преподавателей по месяцам, план, экспорт)",
            "Muhasebe bölümü (öğretim elemanlarının aylık verilen ders saatleri, plan, dışa aktarma)",
            "Bereich Buchhaltung (monatlich gehaltene Unterrichtsstunden der Lehrkräfte, Plan, Export)",
        ),
        "25% təkrar imtahan ödəniş qəbzini yoxlamaq": t(
            "Verify 25% re-exam payment receipts",
            "Проверять квитанции об оплате пересдачи (25%)",
            "%25 tekrar sınav ödeme makbuzunu doğrulamak",
            "Zahlungsbelege für die 25-%-Wiederholungsprüfung prüfen",
        ),
        "Tələbəni 25% təkrar imtahana buraxmaq və alt qrup yerləşdirməsinə qərar vermək": t(
            "Admit students to the 25% re-exam and decide subgroup placement",
            "Допускать студента к пересдаче (25%) и решать распределение по подгруппам",
            "Öğrenciyi %25 tekrar sınavına kabul etmek ve alt grup yerleşimine karar vermek",
            "Studierende zur 25-%-Wiederholungsprüfung zulassen und über die Untergruppe entscheiden",
        ),
    },
    SIDEBAR: {
        "Mühasibatlıq": t("Accounting", "Бухгалтерия", "Muhasebe", "Buchhaltung"),
    },
    STATUS: {
        "Plana uyğun": t("On plan", "По плану", "Plana uygun", "Planmäßig"),
        "Plandan az": t("Below plan", "Меньше плана", "Planın altında", "Unter Plan"),
        "Plandan çox": t("Above plan", "Больше плана", "Planın üstünde", "Über Plan"),
        "Plan yoxdur": t("No plan", "Нет плана", "Plan yok", "Kein Plan"),
        "Dərs yoxdur": t("No lessons", "Нет занятий", "Ders yok", "Keine Stunden"),
    },
    AC: {
        # constants.py
        "Mühazirə": t("Lecture", "Лекция", "Ders (teori)", "Vorlesung"),
        "Seminar": t("Seminar", "Семинар", "Seminer", "Seminar"),
        "Laboratoriya": t("Laboratory", "Лаборатория", "Laboratuvar", "Labor"),
        "Payız semestri": t("Fall semester", "Осенний семестр", "Güz dönemi", "Wintersemester"),
        "Yaz semestri": t("Spring semester", "Весенний семестр", "Bahar dönemi", "Sommersemester"),
        "Yay semestri": t("Summer semester", "Летний семестр", "Yaz dönemi", "Sommerkurs"),
        "Yanvar": t("January", "Январь", "Ocak", "Januar"),
        "Fevral": t("February", "Февраль", "Şubat", "Februar"),
        "Mart": t("March", "Март", "Mart", "März"),
        "Aprel": t("April", "Апрель", "Nisan", "April"),
        "May": t("May", "Май", "Mayıs", "Mai"),
        "İyun": t("June", "Июнь", "Haziran", "Juni"),
        "İyul": t("July", "Июль", "Temmuz", "Juli"),
        "Avqust": t("August", "Август", "Ağustos", "August"),
        "Sentyabr": t("September", "Сентябрь", "Eylül", "September"),
        "Oktyabr": t("October", "Октябрь", "Ekim", "Oktober"),
        "Noyabr": t("November", "Ноябрь", "Kasım", "November"),
        "Dekabr": t("December", "Декабрь", "Aralık", "Dezember"),
        # panel.py / detail.py / export.py / formatting.py / views
        "Hamısı": t("All", "Все", "Tümü", "Alle"),
        "Semestr": t("Semester", "Семестр", "Dönem", "Semester"),
        "Ay": t("Month", "Месяц", "Ay", "Monat"),
        "Bütün semestr": t("Whole semester", "Весь семестр", "Tüm dönem", "Ganzes Semester"),
        "Fakültə": t("Faculty", "Факультет", "Fakülte", "Fakultät"),
        "Kafedra": t("Department", "Кафедра", "Bölüm", "Lehrstuhl"),
        "Kənarlaşma": t("Deviation", "Отклонение", "Sapma", "Abweichung"),
        "Bütün müəllimlər": t("All teachers", "Все преподаватели", "Tüm öğretim elemanları", "Alle Lehrkräfte"),
        "Yalnız plandan kənarlaşanlar": t(
            "Only those off plan", "Только с отклонением от плана", "Yalnızca plandan sapanlar", "Nur Planabweichungen"
        ),
        "s/h": t("hourly", "почас.", "saat ücretli", "Std.-Basis"),
        "Keçirilmiş saat": t("Hours taught", "Проведено часов", "Verilen saat", "Gehaltene Stunden"),
        "Plan": t("Plan", "План", "Plan", "Plan"),
        "İcra": t("Completion", "Выполнение", "Gerçekleşme", "Erfüllung"),
        "saat": t("h", "ч", "saat", "Std."),
        "Plandan çox": t("Above plan", "Больше плана", "Planın üstünde", "Über Plan"),
        "Plandan az": t("Below plan", "Меньше плана", "Planın altında", "Unter Plan"),
        "müəllim (> +10%)": t(
            "teachers (> +10%)", "преп. (> +10%)", "öğretim elemanı (> +%10)", "Lehrkräfte (> +10 %)"
        ),
        "müəllim (< −10%)": t(
            "teachers (< −10%)", "преп. (< −10%)", "öğretim elemanı (< −%10)", "Lehrkräfte (< −10 %)"
        ),
        "Müəllim": t("Teacher", "Преподаватель", "Öğretim elemanı", "Lehrkraft"),
        "Fakt": t("Actual", "Факт", "Gerçekleşen", "Ist"),
        "Fərq": t("Difference", "Разница", "Fark", "Differenz"),
        "Mühasibatlıq bölməsi mühasib, rektor, Qəyyumlar Şurası və RİM rəhbəri üçündür.": t(
            "The accounting section is for the accountant, the rector, the Board of Trustees and the DDC head.",
            "Раздел «Бухгалтерия» доступен бухгалтеру, ректору, Попечительскому совету и руководителю ЦЦР.",
            "Muhasebe bölümü muhasebeci, rektör, Mütevelli Heyeti ve DGM yöneticisi içindir.",
            "Der Bereich Buchhaltung ist für Buchhaltung, Rektor, Kuratorium und die Leitung des DEZ bestimmt.",
        ),
        "İstifadəçi adı": t("Username", "Имя пользователя", "Kullanıcı adı", "Benutzername"),
        "Ştat": t("Staff rate", "Ставка", "Kadro oranı", "Stellenanteil"),
        "Ştat növü": t("Staff type", "Тип ставки", "Kadro türü", "Stellenart"),
        "Plan (saat)": t("Plan (h)", "План (ч)", "Plan (saat)", "Plan (Std.)"),
        "fakt": t("actual", "факт", "gerçekleşen", "Ist"),
        "Fakt (saat)": t("Actual (h)", "Факт (ч)", "Gerçekleşen (saat)", "Ist (Std.)"),
        "Dərs sayı": t("Lessons", "Кол-во занятий", "Ders sayısı", "Anzahl Stunden"),
        "Fərq (saat)": t("Difference (h)", "Разница (ч)", "Fark (saat)", "Differenz (Std.)"),
        "İcra, %": t("Completion, %", "Выполнение, %", "Gerçekleşme, %", "Erfüllung, %"),
        "Status": t("Status", "Статус", "Durum", "Status"),
        "Semestr planı": t("Semester plan", "План семестра", "Dönem planı", "Semesterplan"),
        "Semestr faktı": t("Semester actual", "Факт семестра", "Dönem gerçekleşen", "Semester-Ist"),
        "Müəllimlər": t("Teachers", "Преподаватели", "Öğretim elemanları", "Lehrkräfte"),
        "Fənn": t("Subject", "Дисциплина", "Ders", "Fach"),
        "Qrup": t("Group", "Группа", "Grup", "Gruppe"),
        "Növ": t("Type", "Вид", "Tür", "Art"),
        "Saat": t("Hours", "Часы", "Saat", "Stunden"),
        "Vaxt": t("Time", "Время", "Saat", "Uhrzeit"),
        "Fənn və qrup": t("Subject and group", "Дисциплина и группа", "Ders ve grup", "Fach und Gruppe"),
        "Tarix": t("Date", "Дата", "Tarih", "Datum"),
        "Akademik saat": t("Academic hours", "Академ. часы", "Akademik saat", "Unterrichtsstunden"),
        "Dərslər": t("Lessons", "Занятия", "Dersler", "Stunden"),
        "Mühasibatlıq · %(period)s · keçirilmiş dərs saatı və plan": t(
            "Accounting · %(period)s · hours taught and plan",
            "Бухгалтерия · %(period)s · проведённые часы и план",
            "Muhasebe · %(period)s · verilen ders saatleri ve plan",
            "Buchhaltung · %(period)s · gehaltene Stunden und Plan",
        ),
        "Mühasibatlıq ixracı": t(
            "Accounting export", "Экспорт бухгалтерии", "Muhasebe dışa aktarımı", "Buchhaltungsexport"
        ),
        # templates
        "«Başqasının adından» rejimində ixrac bağlıdır": t(
            "Export is disabled in “view as” mode",
            "В режиме «от имени другого» экспорт недоступен",
            "«Başkası adına» modunda dışa aktarma kapalıdır",
            "Im Modus „Ansicht als“ ist der Export deaktiviert",
        ),
        "Yalnız baxış": t("View only", "Только просмотр", "Yalnızca görüntüleme", "Nur Ansicht"),
        "Excel-ə ixrac": t("Export to Excel", "Экспорт в Excel", "Excel'e aktar", "Nach Excel exportieren"),
        "Mühasibatlıq filtrləri": t(
            "Accounting filters", "Фильтры бухгалтерии", "Muhasebe filtreleri", "Buchhaltungsfilter"
        ),
        "Müəllim axtarışı": t("Teacher search", "Поиск преподавателя", "Öğretim elemanı ara", "Lehrkraft suchen"),
        "Ad, soyad, istifadəçi adı, kafedra…": t(
            "Name, surname, username, department…",
            "Имя, фамилия, имя пользователя, кафедра…",
            "Ad, soyad, kullanıcı adı, bölüm…",
            "Vorname, Nachname, Benutzername, Lehrstuhl…",
        ),
        "Müəllimlərin jurnalda keçirdiyi dərs saatları ay üzrə, paylanmış dərs yükündən aylıq plan payı ilə müqayisədə: mühazirə, seminar, laboratoriya, fərq və ştat. Filtrlər cədvələ və KPI-lara tətbiq olunur; ixrac cari filtr dəstini Excel-ə çıxarır.": t(  # noqa: E501
            "Hours teachers taught in the journal, by month, compared with the monthly share of their distributed workload: lecture, seminar, lab, difference and staff rate. Filters apply to the table and KPIs; the export writes the current filter set to Excel.",  # noqa: E501
            "Проведённые преподавателями по журналу часы по месяцам в сравнении с месячной долей распределённой нагрузки: лекции, семинары, лабораторные, разница и ставка. Фильтры применяются к таблице и KPI; экспорт выгружает текущий набор фильтров в Excel.",  # noqa: E501
            "Öğretim elemanlarının yoklama defterinde verdiği ders saatleri, aylara göre, dağıtılmış ders yükünün aylık payıyla karşılaştırmalı: teori, seminer, laboratuvar, fark ve kadro oranı. Filtreler tabloya ve KPI'lara uygulanır; dışa aktarma mevcut filtre kümesini Excel'e yazar.",  # noqa: E501
            "Im Klassenbuch gehaltene Unterrichtsstunden der Lehrkräfte nach Monat im Vergleich zum Monatsanteil des verteilten Lehrdeputats: Vorlesung, Seminar, Labor, Differenz und Stellenanteil. Filter gelten für Tabelle und KPIs; der Export schreibt den aktuellen Filtersatz nach Excel.",  # noqa: E501
        ),
        "«Başqasının adından» rejimindəsiniz — bölmə yalnız baxış üçündür, ixrac bağlıdır.": t(
            "You are in “view as” mode — the section is view-only and export is disabled.",
            "Вы в режиме «от имени другого» — раздел только для просмотра, экспорт недоступен.",
            "«Başkası adına» modundasınız — bölüm yalnızca görüntüleme içindir, dışa aktarma kapalıdır.",
            "Sie sind im Modus „Ansicht als“ — der Bereich ist schreibgeschützt, der Export ist deaktiviert.",
        ),
        "Akademik dövr tapılmadı": t(
            "No academic period found",
            "Учебный период не найден",
            "Akademik dönem bulunamadı",
            "Kein akademischer Zeitraum gefunden",
        ),
        "Semestr təqvimi «Semestr açılışı» bölməsində yaradılır. Dövr olmadan keçirilmiş dərslər aylara bölünə bilmir.": t(  # noqa: E501
            "The semester calendar is created in “Semester opening”. Without a period, taught lessons cannot be split by month.",  # noqa: E501
            "Календарь семестра создаётся в разделе «Открытие семестра». Без периода проведённые занятия нельзя распределить по месяцам.",  # noqa: E501
            "Dönem takvimi «Dönem açılışı» bölümünde oluşturulur. Dönem olmadan verilen dersler aylara bölünemez.",
            "Der Semesterkalender wird unter „Semestereröffnung“ angelegt. Ohne Zeitraum lassen sich gehaltene Stunden nicht nach Monaten aufteilen.",  # noqa: E501
        ),
        "%(period)s · göstərilir: %(shown)s / %(total)s müəllim": t(
            "%(period)s · showing %(shown)s / %(total)s teachers",
            "%(period)s · показано: %(shown)s / %(total)s преподавателей",
            "%(period)s · gösterilen: %(shown)s / %(total)s öğretim elemanı",
            "%(period)s · angezeigt: %(shown)s / %(total)s Lehrkräfte",
        ),
        "filtr tətbiq olunub": t("filter applied", "фильтр применён", "filtre uygulandı", "Filter aktiv"),
        "Ay hələ bitməyib — fakt ayın sonunadək artacaq, «Plandan az» statusu ilkin göstəricidir.": t(
            "The month is not over yet — actual hours will grow until month end; “Below plan” is preliminary.",
            "Месяц ещё не закончился — факт будет расти до конца месяца, статус «Меньше плана» предварительный.",
            "Ay henüz bitmedi — gerçekleşen saatler ay sonuna kadar artacak; «Planın altında» durumu ön göstergedir.",
            "Der Monat ist noch nicht vorbei — die Ist-Stunden steigen bis Monatsende; „Unter Plan“ ist vorläufig.",
        ),
        "Bu semestr üçün nə keçirilmiş dərs, nə də paylanmış yük var": t(
            "There are neither taught lessons nor distributed workload for this semester",
            "За этот семестр нет ни проведённых занятий, ни распределённой нагрузки",
            "Bu dönem için ne verilen ders ne de dağıtılmış yük var",
            "Für dieses Semester gibt es weder gehaltene Stunden noch verteiltes Deputat",
        ),
        "Fakt elektron jurnalın dərslərindən, plan «Yük bölgüsü»ndə müəllimlərə paylanmış saatlardan yığılır. Başqa semestr seçin.": t(  # noqa: E501
            "Actual hours come from the e-journal lessons, the plan from hours distributed to teachers in “Workload distribution”. Choose another semester.",  # noqa: E501
            "Факт берётся из занятий электронного журнала, план — из часов, распределённых преподавателям в «Распределении нагрузки». Выберите другой семестр.",  # noqa: E501
            "Gerçekleşen saatler e-yoklama defterinin derslerinden, plan «Yük dağılımı»nda öğretim elemanlarına dağıtılan saatlerden gelir. Başka bir dönem seçin.",  # noqa: E501
            "Ist-Stunden stammen aus den Stunden des E-Klassenbuchs, der Plan aus den in „Deputatsverteilung“ zugewiesenen Stunden. Wählen Sie ein anderes Semester.",  # noqa: E501
        ),
        "Saatlar necə hesablanır?": t(
            "How are the hours calculated?",
            "Как считаются часы?",
            "Saatler nasıl hesaplanır?",
            "Wie werden die Stunden berechnet?",
        ),
        "Fakt — elektron jurnalda yazılmış (keçirilmiş) dərslərin akademik saatı (adətən 1 dərs = 2 saat). Dərsi bölünmüş fəndə dərsin öz müəllimi, əks halda jurnal sahibi sayılır. Bütün tələbələri «Jurnal təmizliyi» ilə çıxarılmış (keçirilməyən) fənnin dərsləri və passiv jurnallar sayılmır.": t(  # noqa: E501
            "Actual — academic hours of lessons recorded (held) in the e-journal (usually 1 lesson = 2 hours). For a split subject the lesson's own teacher counts, otherwise the journal owner. Lessons of subjects whose students were all removed via “Journal hygiene” (not held) and inactive journals are not counted.",  # noqa: E501
            "Факт — академические часы занятий, записанных (проведённых) в электронном журнале (обычно 1 занятие = 2 часа). В разделённой дисциплине учитывается преподаватель самого занятия, иначе владелец журнала. Занятия дисциплин, все студенты которых исключены через «Чистку журнала» (не проводилась), и неактивные журналы не учитываются.",  # noqa: E501
            "Gerçekleşen — e-yoklama defterine yazılmış (verilmiş) derslerin akademik saati (genellikle 1 ders = 2 saat). Bölünmüş derste dersin kendi öğretim elemanı, aksi halde defter sahibi sayılır. Tüm öğrencileri «Defter temizliği» ile çıkarılmış (verilmeyen) derslerin dersleri ve pasif defterler sayılmaz.",  # noqa: E501
            "Ist — Unterrichtsstunden der im E-Klassenbuch erfassten (gehaltenen) Stunden (meist 1 Stunde = 2 Unterrichtsstunden). Bei geteilten Fächern zählt die Lehrkraft der Stunde selbst, sonst die Klassenbuchverantwortliche. Stunden von Fächern, deren Studierende alle per „Klassenbuch-Bereinigung“ entfernt wurden (nicht durchgeführt), und inaktive Klassenbücher zählen nicht.",  # noqa: E501
        ),
        "Plan — semestr üçün müəllimə paylanmış dərs yükü (mühazirə, seminar, laboratoriya; bölgüsü bitmiş tapşırıqlar). Məsləhət, imtahan, təcrübə və buraxılış işi saatları jurnalda dərs kimi yazılmadığı üçün müqayisəyə daxil deyil.": t(  # noqa: E501
            "Plan — the workload distributed to the teacher for the semester (lecture, seminar, lab; tasks whose distribution is finished). Consultation, exam, practice and thesis hours are not recorded as journal lessons, so they are not compared.",  # noqa: E501
            "План — распределённая преподавателю нагрузка на семестр (лекции, семинары, лабораторные; задания с завершённым распределением). Часы консультаций, экзаменов, практики и выпускных работ не записываются в журнал как занятия, поэтому не сравниваются.",  # noqa: E501
            "Plan — öğretim elemanına dönem için dağıtılmış ders yükü (teori, seminer, laboratuvar; dağıtımı tamamlanmış görevler). Danışmanlık, sınav, staj ve bitirme çalışması saatleri defterde ders olarak yazılmadığından karşılaştırmaya dahil değildir.",  # noqa: E501
            "Plan — das der Lehrkraft für das Semester verteilte Deputat (Vorlesung, Seminar, Labor; Aufgaben mit abgeschlossener Verteilung). Sprechstunden-, Prüfungs-, Praktikums- und Abschlussarbeitsstunden werden nicht als Klassenbuchstunden erfasst und daher nicht verglichen.",  # noqa: E501
        ),
        "Aylıq plan — semestr planı dərs pəncərəsinin (semestrin başlanğıcından imtahan sessiyasına qədər) iş günlərinə (B.e.–Cümə) mütənasib bölünür; aylıq payların cəmi semestr planına bərabərdir. Bayram günləri nəzərə alınmır.": t(  # noqa: E501
            "Monthly plan — the semester plan is split in proportion to the working days (Mon–Fri) of the teaching window (from semester start to the exam session); the monthly shares add up to the semester plan. Public holidays are not taken into account.",  # noqa: E501
            "Месячный план — план семестра делится пропорционально рабочим дням (пн–пт) учебного окна (от начала семестра до сессии); сумма месячных долей равна плану семестра. Праздничные дни не учитываются.",  # noqa: E501
            "Aylık plan — dönem planı, ders penceresinin (dönem başından sınav dönemine kadar) iş günlerine (Pzt–Cum) orantılı bölünür; aylık payların toplamı dönem planına eşittir. Resmî tatiller dikkate alınmaz.",  # noqa: E501
            "Monatsplan — der Semesterplan wird anteilig auf die Arbeitstage (Mo–Fr) des Unterrichtszeitraums (Semesterbeginn bis Prüfungszeit) verteilt; die Monatsanteile ergeben zusammen den Semesterplan. Feiertage werden nicht berücksichtigt.",  # noqa: E501
        ),
        "Status — fakt planın ±10%-i daxilindədirsə «Plana uyğun»; az və ya çoxdursa müvafiq olaraq «Plandan az» / «Plandan çox».": t(  # noqa: E501
            "Status — “On plan” if actual hours are within ±10% of the plan; otherwise “Below plan” / “Above plan”.",
            "Статус — «По плану», если факт в пределах ±10% плана; иначе «Меньше плана» / «Больше плана».",
            "Durum — gerçekleşen planın ±%10'u içindeyse «Plana uygun»; değilse «Planın altında» / «Planın üstünde».",
            "Status — „Planmäßig“, wenn die Ist-Stunden innerhalb von ±10 % des Plans liegen; sonst „Unter Plan“ / „Über Plan“.",
        ),
        "Müəllimlərin keçirilmiş dərs saatı və planı — %(period)s": t(
            "Teachers' hours taught and plan — %(period)s",
            "Проведённые часы и план преподавателей — %(period)s",
            "Öğretim elemanlarının verilen ders saatleri ve planı — %(period)s",
            "Gehaltene Stunden und Plan der Lehrkräfte — %(period)s",
        ),
        "Semestr: plan / fakt": t(
            "Semester: plan / actual", "Семестр: план / факт", "Dönem: plan / gerçekleşen", "Semester: Plan / Ist"
        ),
        "Filtrə uyğun müəllim yoxdur.": t(
            "No teachers match the filter.",
            "Нет преподавателей по фильтру.",
            "Filtreye uyan öğretim elemanı yok.",
            "Keine Lehrkräfte entsprechen dem Filter.",
        ),
        "Cəmi · %(count)s müəllim": t(
            "Total · %(count)s teachers",
            "Итого · %(count)s преп.",
            "Toplam · %(count)s öğretim elemanı",
            "Summe · %(count)s Lehrkräfte",
        ),
        "Səhifələmə": t("Pagination", "Пагинация", "Sayfalama", "Seitennavigation"),
        "Əvvəlki": t("Previous", "Назад", "Önceki", "Zurück"),
        "Səhifə %(page)s / %(pages)s · %(total)s müəllim": t(
            "Page %(page)s / %(pages)s · %(total)s teachers",
            "Страница %(page)s / %(pages)s · %(total)s преп.",
            "Sayfa %(page)s / %(pages)s · %(total)s öğretim elemanı",
            "Seite %(page)s / %(pages)s · %(total)s Lehrkräfte",
        ),
        "Növbəti": t("Next", "Далее", "Sonraki", "Weiter"),
        "Müəllim tapılmadı": t(
            "Teacher not found", "Преподаватель не найден", "Öğretim elemanı bulunamadı", "Lehrkraft nicht gefunden"
        ),
        "Bu semestrdə həmin müəllimin nə keçirilmiş dərsi, nə də paylanmış yükü var, və ya müəllim sizin əhatənizdən kənardadır.": t(  # noqa: E501
            "This teacher has neither taught lessons nor distributed workload this semester, or is outside your scope.",
            "У этого преподавателя в семестре нет ни проведённых занятий, ни распределённой нагрузки, или он вне вашей зоны доступа.",  # noqa: E501
            "Bu öğretim elemanının bu dönem ne verilmiş dersi ne de dağıtılmış yükü var ya da yetki alanınızın dışında.",
            "Diese Lehrkraft hat in diesem Semester weder gehaltene Stunden noch verteiltes Deputat oder liegt außerhalb Ihres Bereichs.",  # noqa: E501
        ),
        "ştat": t("staff rate", "ставка", "kadro", "Stelle"),
        "Aylar üzrə": t("By month", "По месяцам", "Aylara göre", "Nach Monaten"),
        "Aylar üzrə plan və keçirilmiş saat": t(
            "Plan and hours taught by month",
            "План и проведённые часы по месяцам",
            "Aylara göre plan ve verilen saat",
            "Plan und gehaltene Stunden nach Monaten",
        ),
        "Dərs": t("Lessons", "Занятий", "Ders", "Stunden"),
        "Semestr planı növlər üzrə:": t(
            "Semester plan by type:", "План семестра по видам:", "Türlere göre dönem planı:", "Semesterplan nach Art:"
        ),
        "Fənn və qrup üzrə — %(period)s": t(
            "By subject and group — %(period)s",
            "По дисциплинам и группам — %(period)s",
            "Ders ve gruba göre — %(period)s",
            "Nach Fach und Gruppe — %(period)s",
        ),
        "Fənn və qrup üzrə keçirilmiş saat": t(
            "Hours taught by subject and group",
            "Проведённые часы по дисциплинам и группам",
            "Ders ve gruba göre verilen saat",
            "Gehaltene Stunden nach Fach und Gruppe",
        ),
        "Cəmi": t("Total", "Итого", "Toplam", "Summe"),
        "Bu dövrdə keçirilmiş dərs yoxdur.": t(
            "No lessons were taught in this period.",
            "В этом периоде нет проведённых занятий.",
            "Bu dönemde verilmiş ders yok.",
            "In diesem Zeitraum wurden keine Stunden gehalten.",
        ),
        "Keçirilmiş dərslər · %(total)s": t(
            "Lessons taught · %(total)s",
            "Проведённые занятия · %(total)s",
            "Verilen dersler · %(total)s",
            "Gehaltene Stunden · %(total)s",
        ),
        "Keçirilmiş dərslərin siyahısı": t(
            "List of lessons taught",
            "Список проведённых занятий",
            "Verilen derslerin listesi",
            "Liste der gehaltenen Stunden",
        ),
        "Dərslərin səhifələnməsi": t(
            "Lesson pagination", "Пагинация занятий", "Ders sayfalama", "Seitennavigation der Stunden"
        ),
        "Səhifə %(page)s / %(pages)s": t(
            "Page %(page)s / %(pages)s",
            "Страница %(page)s / %(pages)s",
            "Sayfa %(page)s / %(pages)s",
            "Seite %(page)s / %(pages)s",
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
