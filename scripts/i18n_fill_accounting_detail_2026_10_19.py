#!/usr/bin/env python3
"""EMSArena i18n — «Mühasibatlıq»: müəllim pəncərəsi (modal), tarix aralığı, leqenda, aydın KPI-lar (2026-10-19).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`. `{% blocktrans %}` mətnləri `%(ad)s` yer tutucusu ilə yazılıb.
«%» işarəsi msgid-lərdə YOXDUR (arqumentdədir) — «%-i» xgettext-də python-format direktivi sayılırdı.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

AC = "accounts.accounting"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    AC: {
        # ── Başlıq, dövr sətri, ipucu ───────────────────────────────────────
        "Müəllimlərin jurnalda keçirdiyi dərs saatları paylanmış dərs yükünün seçilmiş dövrə düşən payı ilə "
        "müqayisədə: mühazirə, seminar, laboratoriya, fərq və status. Dövr — ay, bütün semestr və ya tarix aralığı. "
        "Filtrlər KPI-lara, cədvələ və Excel ixracına eyni tətbiq olunur; müəllimin sətrinə klik ətraflı pəncərəni "
        "açır.": t(
            "Hours taught by teachers according to the journal, compared with the share of the distributed workload "
            "for the selected period: lectures, seminars, labs, difference and status. Period — a month, the whole "
            "semester or a date range. Filters apply equally to the KPIs, the table and the Excel export; clicking a "
            "teacher's row opens a detailed window.",
            "Проведённые преподавателями часы по журналу в сравнении с долей распределённой нагрузки за выбранный "
            "период: лекции, семинары, лабораторные, разница и статус. Период — месяц, весь семестр или диапазон "
            "дат. Фильтры одинаково применяются к KPI, таблице и экспорту в Excel; щелчок по строке преподавателя "
            "открывает подробное окно.",
            "Öğretim elemanlarının yoklama defterine göre verdiği ders saatleri, dağıtılmış ders yükünün seçilen "
            "döneme düşen payıyla karşılaştırmalı: teorik ders, seminer, laboratuvar, fark ve durum. Dönem — ay, tüm "
            "yarıyıl veya tarih aralığı. Filtreler KPI'lara, tabloya ve Excel dışa aktarımına aynı şekilde uygulanır; "
            "öğretim elemanının satırına tıklamak ayrıntılı pencereyi açar.",
            "Laut Klassenbuch gehaltene Unterrichtsstunden der Lehrkräfte im Vergleich zum Anteil des verteilten "
            "Lehrdeputats im gewählten Zeitraum: Vorlesungen, Seminare, Labore, Differenz und Status. Zeitraum — ein "
            "Monat, das ganze Semester oder ein Datumsbereich. Filter gelten gleichermaßen für KPIs, Tabelle und "
            "Excel-Export; ein Klick auf die Zeile einer Lehrkraft öffnet ein Detailfenster.",
        ),
        "göstərilir: %(shown)s / %(total)s müəllim": t(
            "shown: %(shown)s / %(total)s teachers",
            "показано: %(shown)s / %(total)s преподавателей",
            "gösterilen: %(shown)s / %(total)s öğretim elemanı",
            "angezeigt: %(shown)s / %(total)s Lehrkräfte",
        ),
        "Müəllimin sətrinə klikləyin — aylar, fənlər və keçirilmiş dərslər ətraflı pəncərədə açılır.": t(
            "Click a teacher's row — months, subjects and taught lessons open in a detailed window.",
            "Щёлкните по строке преподавателя — месяцы, дисциплины и проведённые занятия откроются в подробном окне.",
            "Öğretim elemanının satırına tıklayın — aylar, dersler ve işlenen dersler ayrıntılı pencerede açılır.",
            "Klicken Sie auf die Zeile einer Lehrkraft — Monate, Fächer und gehaltene Stunden öffnen sich im "
            "Detailfenster.",
        ),
        "Aralıq bu günü əhatə edir — fakt aralığın sonunadək artacaq, «Plandan az» statusu ilkin göstəricidir.": t(
            "The range includes today — actual hours will grow until its end; «Below plan» is preliminary.",
            "Диапазон включает сегодняшний день — факт будет расти до его конца, статус «Меньше плана» предварительный.",
            "Aralık bugünü kapsıyor — gerçekleşen saat aralığın sonuna kadar artacak, «Planın altında» durumu ön "
            "göstergedir.",
            "Der Bereich umfasst heute — die Ist-Stunden steigen bis zu seinem Ende, «Unter Plan» ist vorläufig.",
        ),
        "Aralığın planı: hər ayın plan payı həmin ayın aralığa düşən iş günləri qədər götürülür (ayın payı × "
        "aralıqdakı iş günləri ÷ ayın iş günləri). Tam düşən ay ay rejimi ilə, bütün semestr isə semestr planı ilə "
        "eyni rəqəmi verir.": t(
            "Range plan: each month's plan share is taken in proportion to that month's working days inside the range "
            "(month share × working days in range ÷ month's working days). A fully covered month gives the same "
            "figure as month mode, the whole semester gives the semester plan.",
            "План диапазона: плановая доля каждого месяца берётся пропорционально его рабочим дням внутри диапазона "
            "(доля месяца × рабочие дни в диапазоне ÷ рабочие дни месяца). Полностью вошедший месяц даёт ту же "
            "цифру, что и режим месяца, весь семестр — план семестра.",
            "Aralığın planı: her ayın plan payı, o ayın aralığa düşen iş günleri kadar alınır (ayın payı × aralıktaki "
            "iş günleri ÷ ayın iş günleri). Tamamen kapsanan ay, ay moduyla; tüm yarıyıl ise yarıyıl planıyla aynı "
            "sonucu verir.",
            "Plan des Bereichs: Der Planteil jedes Monats wird anteilig nach seinen Arbeitstagen im Bereich "
            "übernommen (Monatsanteil × Arbeitstage im Bereich ÷ Arbeitstage des Monats). Ein voll enthaltener Monat "
            "ergibt denselben Wert wie der Monatsmodus, das ganze Semester den Semesterplan.",
        ),
        "Tarix aralığı — aralığın planı aylıq paylardan götürülür: qismən düşən ayın payı aralığa düşən iş günləri "
        "qədər kəsilir; fakt aralığın içində keçirilmiş dərslərdir. Aralıq seçilmiş semestrin hüdudlarında "
        "olmalıdır.": t(
            "Date range — the range plan is taken from the monthly shares: a partially covered month's share is cut "
            "to its working days inside the range; actual hours are lessons held within the range. The range must "
            "lie within the selected semester.",
            "Диапазон дат — план диапазона берётся из месячных долей: доля частично вошедшего месяца урезается до "
            "его рабочих дней в диапазоне; факт — занятия, проведённые внутри диапазона. Диапазон должен быть в "
            "пределах выбранного семестра.",
            "Tarih aralığı — aralığın planı aylık paylardan alınır: kısmen kapsanan ayın payı aralığa düşen iş "
            "günleri kadar kesilir; gerçekleşen, aralık içinde işlenen derslerdir. Aralık seçilen yarıyılın "
            "sınırları içinde olmalıdır.",
            "Datumsbereich — der Plan des Bereichs ergibt sich aus den Monatsanteilen: Der Anteil eines teilweise "
            "enthaltenen Monats wird auf seine Arbeitstage im Bereich gekürzt; Ist sind die im Bereich gehaltenen "
            "Stunden. Der Bereich muss innerhalb des gewählten Semesters liegen.",
        ),
        # ── Filtr: tarix aralığı ────────────────────────────────────────────
        "Tarix aralığı…": t("Date range…", "Диапазон дат…", "Tarih aralığı…", "Datumsbereich…"),
        "Tarix aralığı": t("Date range", "Диапазон дат", "Tarih aralığı", "Datumsbereich"),
        "Başlanğıc tarixi": t("Start date", "Дата начала", "Başlangıç tarihi", "Startdatum"),
        "Son tarix": t("End date", "Дата окончания", "Bitiş tarihi", "Enddatum"),
        "-dan": t("(from)", "(с)", "-den", "(ab)"),
        "-dək": t("(to)", "(по)", "-e kadar", "(bis)"),
        "Başlanğıc tarixi son tarixdən sonra ola bilməz.": t(
            "The start date cannot be after the end date.",
            "Дата начала не может быть позже даты окончания.",
            "Başlangıç tarihi bitiş tarihinden sonra olamaz.",
            "Das Startdatum darf nicht nach dem Enddatum liegen.",
        ),
        "Tarix seçilmiş semestrin hüdudlarında olmalıdır.": t(
            "The date must lie within the selected semester.",
            "Дата должна быть в пределах выбранного семестра.",
            "Tarih seçilen yarıyılın sınırları içinde olmalıdır.",
            "Das Datum muss innerhalb des gewählten Semesters liegen.",
        ),
        "Tarix tanınmadı — defolt aralıq göstərilir (semestrin başlanğıcından bu günədək).": t(
            "The date was not recognised — showing the default range (from the semester start to today).",
            "Дата не распознана — показан диапазон по умолчанию (с начала семестра до сегодня).",
            "Tarih tanınmadı — varsayılan aralık gösteriliyor (yarıyıl başından bugüne kadar).",
            "Datum nicht erkannt — Standardbereich wird angezeigt (vom Semesterbeginn bis heute).",
        ),
        "Başlanğıc tarixi son tarixdən sonra idi — tarixlərin yeri dəyişdirildi.": t(
            "The start date was after the end date — the dates were swapped.",
            "Дата начала была позже даты окончания — даты поменяны местами.",
            "Başlangıç tarihi bitiş tarihinden sonraydı — tarihlerin yeri değiştirildi.",
            "Das Startdatum lag nach dem Enddatum — die Daten wurden vertauscht.",
        ),
        "Seçilmiş aralıq bu semestrə düşmür — defolt aralıq göstərilir ({start} – {end}).": t(
            "The selected range is outside this semester — showing the default range ({start} – {end}).",
            "Выбранный диапазон не входит в этот семестр — показан диапазон по умолчанию ({start} – {end}).",
            "Seçilen aralık bu yarıyıla denk gelmiyor — varsayılan aralık gösteriliyor ({start} – {end}).",
            "Der gewählte Bereich liegt außerhalb dieses Semesters — Standardbereich wird angezeigt ({start} – {end}).",
        ),
        "Aralıq seçilmiş semestrin hüdudlarına ({start} – {end}) uyğunlaşdırıldı.": t(
            "The range was adjusted to the selected semester ({start} – {end}).",
            "Диапазон приведён к границам выбранного семестра ({start} – {end}).",
            "Aralık seçilen yarıyılın sınırlarına ({start} – {end}) uyarlandı.",
            "Der Bereich wurde an das gewählte Semester ({start} – {end}) angepasst.",
        ),
        # ── KPI ─────────────────────────────────────────────────────────────
        "{period} üçün paylanmış yükün payı": t(
            "share of the distributed workload for {period}",
            "доля распределённой нагрузки за {period}",
            "{period} için dağıtılmış yükün payı",
            "Anteil des verteilten Deputats für {period}",
        ),
        "fakt ÷ plan · fərq {diff} saat": t(
            "actual ÷ plan · difference {diff} h",
            "факт ÷ план · разница {diff} ч",
            "gerçekleşen ÷ plan · fark {diff} saat",
            "Ist ÷ Plan · Differenz {diff} Std.",
        ),
        "müəllim · fakt > plan + {band}": t(
            "teachers · actual > plan + {band}",
            "преподавателей · факт > план + {band}",
            "öğretim elemanı · gerçekleşen > plan + {band}",
            "Lehrkräfte · Ist > Plan + {band}",
        ),
        "müəllim · fakt < plan − {band}": t(
            "teachers · actual < plan − {band}",
            "преподавателей · факт < план − {band}",
            "öğretim elemanı · gerçekleşen < plan − {band}",
            "Lehrkräfte · Ist < Plan − {band}",
        ),
        # ── Leqenda ─────────────────────────────────────────────────────────
        "Statusların izahı": t("Status legend", "Пояснение статусов", "Durumların açıklaması", "Statuslegende"),
        "fakt planın ±{band} hüdudunda": t(
            "actual within ±{band} of plan",
            "факт в пределах ±{band} от плана",
            "gerçekleşen, planın ±{band} sınırında",
            "Ist innerhalb von ±{band} des Plans",
        ),
        "fakt planın {share}-indən az": t(
            "actual below {share} of plan",
            "факт меньше {share} плана",
            "gerçekleşen, planın {share}'inden az",
            "Ist unter {share} des Plans",
        ),
        "fakt planın {share}-indən çox": t(
            "actual above {share} of plan",
            "факт больше {share} плана",
            "gerçekleşen, planın {share}'inden fazla",
            "Ist über {share} des Plans",
        ),
        "dərs keçilib, amma bu dövr üçün plan yoxdur": t(
            "lessons held, but there is no plan for this period",
            "занятия проведены, но плана на этот период нет",
            "ders işlendi, ancak bu dönem için plan yok",
            "Stunden gehalten, aber kein Plan für diesen Zeitraum",
        ),
        "nə plan, nə keçirilmiş dərs": t(
            "neither plan nor taught lessons",
            "нет ни плана, ни проведённых занятий",
            "ne plan ne de işlenen ders var",
            "weder Plan noch gehaltene Stunden",
        ),
        # ── Cədvəl / boş vəziyyət ───────────────────────────────────────────
        "Müəllimlər cədvəli": t(
            "Teachers table", "Таблица преподавателей", "Öğretim elemanları tablosu", "Lehrkräftetabelle"
        ),
        "Filtrə uyğun müəllim yoxdur": t(
            "No teachers match the filter",
            "Нет преподавателей, соответствующих фильтру",
            "Filtreye uyan öğretim elemanı yok",
            "Keine Lehrkräfte entsprechen dem Filter",
        ),
        "Fakültə, kafedra, kənarlaşma və ya axtarış filtrini dəyişin. Dövr (ay və ya aralıq) saxlanılır.": t(
            "Change the faculty, department, deviation or search filter. The period (month or range) is kept.",
            "Измените фильтр факультета, кафедры, отклонения или поиска. Период (месяц или диапазон) сохраняется.",
            "Fakülte, bölüm, sapma veya arama filtresini değiştirin. Dönem (ay veya aralık) korunur.",
            "Ändern Sie den Filter für Fakultät, Lehrstuhl, Abweichung oder Suche. Der Zeitraum (Monat oder Bereich) "
            "bleibt erhalten.",
        ),
        "Filtrləri təmizlə": t("Clear filters", "Сбросить фильтры", "Filtreleri temizle", "Filter zurücksetzen"),
        # ── Müəllim pəncərəsi ───────────────────────────────────────────────
        "Dövr: {period}": t("Period: {period}", "Период: {period}", "Dönem: {period}", "Zeitraum: {period}"),
        "Yüklənir…": t("Loading…", "Загрузка…", "Yükleniyor…", "Wird geladen…"),
        "Məlumatı yükləmək alınmadı. Bir az sonra yenidən cəhd edin.": t(
            "Could not load the data. Please try again shortly.",
            "Не удалось загрузить данные. Повторите попытку чуть позже.",
            "Veriler yüklenemedi. Biraz sonra tekrar deneyin.",
            "Die Daten konnten nicht geladen werden. Bitte versuchen Sie es gleich erneut.",
        ),
        "Müəllim tapılmadı və ya sizin əhatənizdən kənardadır.": t(
            "Teacher not found or outside your scope.",
            "Преподаватель не найден или вне вашей зоны доступа.",
            "Öğretim elemanı bulunamadı veya yetki alanınızın dışında.",
            "Lehrkraft nicht gefunden oder außerhalb Ihres Zuständigkeitsbereichs.",
        ),
        "Bu məlumata baxmaq üçün icazəniz yoxdur.": t(
            "You do not have permission to view this information.",
            "У вас нет прав на просмотр этих данных.",
            "Bu bilgiyi görüntüleme yetkiniz yok.",
            "Sie sind nicht berechtigt, diese Informationen anzuzeigen.",
        ),
        "Növlər üzrə": t("By type", "По видам", "Türlere göre", "Nach Art"),
        "Növlər üzrə — %(period)s": t(
            "By type — %(period)s", "По видам — %(period)s", "Türlere göre — %(period)s", "Nach Art — %(period)s"
        ),
        "Növlər üzrə plan və keçirilmiş saat — %(period)s": t(
            "Plan and taught hours by type — %(period)s",
            "План и проведённые часы по видам — %(period)s",
            "Türlere göre plan ve işlenen saat — %(period)s",
            "Plan und gehaltene Stunden nach Art — %(period)s",
        ),
        "Aylar üzrə — %(semester)s": t(
            "By month — %(semester)s",
            "По месяцам — %(semester)s",
            "Aylara göre — %(semester)s",
            "Nach Monaten — %(semester)s",
        ),
        "Aralığın ayları": t("Months in the range", "Месяцы диапазона", "Aralıktaki aylar", "Monate im Bereich"),
        "Fənn və qrup üzrə": t(
            "By subject and group", "По дисциплинам и группам", "Ders ve gruba göre", "Nach Fach und Gruppe"
        ),
        "Bu dövrdə ay yoxdur.": t(
            "There are no months in this period.",
            "В этом периоде нет месяцев.",
            "Bu dönemde ay yok.",
            "In diesem Zeitraum gibt es keine Monate.",
        ),
        "Qismən ayın planı aralığa düşən iş günləri qədər götürülür.": t(
            "A partial month's plan is taken in proportion to its working days inside the range.",
            "План неполного месяца берётся пропорционально его рабочим дням в диапазоне.",
            "Kısmi ayın planı, aralığa düşen iş günleri kadar alınır.",
            "Der Plan eines Teilmonats wird anteilig nach seinen Arbeitstagen im Bereich übernommen.",
        ),
        "Daha çox göstər · %(count)s qalıb": t(
            "Show more · %(count)s left",
            "Показать ещё · осталось %(count)s",
            "Daha fazla göster · %(count)s kaldı",
            "Mehr anzeigen · %(count)s übrig",
        ),
        "Tam səhifədə aç": t("Open full page", "Открыть на всю страницу", "Tam sayfada aç", "Als ganze Seite öffnen"),
        "Excel-ə ixrac (bu müəllim)": t(
            "Export to Excel (this teacher)",
            "Экспорт в Excel (этот преподаватель)",
            "Excel'e aktar (bu öğretim elemanı)",
            "Nach Excel exportieren (diese Lehrkraft)",
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
