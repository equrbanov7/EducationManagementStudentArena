#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: avtomatik dərs cədvəli generatoru (apps/timetable),
toplu dərc (registrar.schedule_publish) və «Cədvəl idarəetməsi» bölməsindəki keçid.
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_timetable_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

_S = "registrar.schedule_publish"
_API = "timetable.api"
_AV = "timetable.availability"
_ED = "timetable.edit"
_HM = "timetable.home"
_MD = "timetable.model"
_NV = "timetable.nav"
_PG = "timetable.page"
_PO = "timetable.policy"
_PC = "timetable.precheck"
_PB = "timetable.publish"
_RV = "timetable.review"
_RN = "timetable.run"

STRINGS = {
    ("accounts.schedule_manage", "Avtomatik cədvəl"): (
        "Automatic timetable",
        "Автоматическое расписание",
        "Otomatik ders programı",
    ),
    # ── registrar.schedule_publish ───────────────────────────────────────
    (_S, "Bu semestr bitib — cədvəl dərc edilə bilməz."): (
        "This semester has ended — the timetable cannot be published.",
        "Семестр завершён — расписание нельзя опубликовать.",
        "Bu dönem bitti — ders programı yayımlanamaz.",
    ),
    (_S, "Bəzi açılışlar sizin səlahiyyət sahənizdən kənardadır — cədvəl dərc edilmədi."): (
        "Some course offerings are outside your scope — the timetable was not published.",
        "Некоторые курсы вне вашей зоны полномочий — расписание не опубликовано.",
        "Bazı dersler yetki alanınızın dışında — ders programı yayımlanmadı.",
    ),
    (_S, "Cədvəlin toplu dərci"): (
        "Bulk timetable publication",
        "Пакетная публикация расписания",
        "Ders programının toplu yayımı",
    ),
    (_S, "Dərc olunmadı: canlı cədvəllə %(count)s toqquşma var."): (
        "Not published: %(count)s conflicts with the live timetable.",
        "Не опубликовано: %(count)s конфликтов с действующим расписанием.",
        "Yayımlanmadı: canlı programla %(count)s çakışma var.",
    ),
    (_S, "Dərs cədvəli dərc edildi: %(period)s"): (
        "Timetable published: %(period)s",
        "Расписание опубликовано: %(period)s",
        "Ders programı yayımlandı: %(period)s",
    ),
    (_S, "Qaralamada yararsız slot var — yenidən yaradın."): (
        "The draft contains an invalid slot — regenerate it.",
        "В черновике есть недопустимый слот — создайте заново.",
        "Taslakta geçersiz bir slot var — yeniden oluşturun.",
    ),
    (_S, "Qrupunuzun yeni həftəlik dərs cədvəli dərc olundu."): (
        "Your group's new weekly timetable has been published.",
        "Опубликовано новое недельное расписание вашей группы.",
        "Grubunuzun yeni haftalık ders programı yayımlandı.",
    ),
    (_S, "Yeni həftəlik cədvəliniz hazırdır — dərslərinizi yoxlayın."): (
        "Your new weekly timetable is ready — please review your classes.",
        "Ваше новое недельное расписание готово — проверьте занятия.",
        "Yeni haftalık programınız hazır — derslerinizi kontrol edin.",
    ),
    # ── timetable.api ────────────────────────────────────────────────────
    (_API, "Bu işləmə növbədə deyil."): (
        "This run is not queued.",
        "Этот запуск не в очереди.",
        "Bu çalıştırma kuyrukta değil.",
    ),
    (_API, "Cədvəl dərc edildi: %(created)s dərs yazıldı, %(removed)s köhnə slot əvəz olundu."): (
        "Timetable published: %(created)s classes written, %(removed)s old slots replaced.",
        "Расписание опубликовано: записано занятий — %(created)s, заменено старых слотов — %(removed)s.",
        "Program yayımlandı: %(created)s ders yazıldı, %(removed)s eski slot değiştirildi.",
    ),
    (_API, "Dərs köçürüldü."): ("Class moved.", "Занятие перенесено.", "Ders taşındı."),
    (_API, "Naməlum əməliyyat."): ("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
    (_API, "Növbə siyasəti yadda saxlanıldı."): (
        "Shift policy saved.",
        "Политика смен сохранена.",
        "Vardiya politikası kaydedildi.",
    ),
    (_API, "Seçilmiş əhatədə sizin idarə etdiyiniz qrup yoxdur."): (
        "The selected scope contains no groups you manage.",
        "В выбранной области нет групп, которыми вы управляете.",
        "Seçilen kapsamda yönettiğiniz grup yok.",
    ),
    (_API, "Sizin artıq işləyən cədvəl işləmələriniz var — bitməsini gözləyin."): (
        "You already have timetable runs in progress — wait for them to finish.",
        "У вас уже выполняются запуски расписания — дождитесь их завершения.",
        "Zaten devam eden program çalıştırmalarınız var — bitmelerini bekleyin.",
    ),
    (_API, "Yalnız hazır qaralama redaktə edilə bilər."): (
        "Only a finished draft can be edited.",
        "Редактировать можно только готовый черновик.",
        "Yalnızca tamamlanmış taslak düzenlenebilir.",
    ),
    (_API, "İşləmə ləğv edildi."): ("Run discarded.", "Запуск отменён.", "Çalıştırma iptal edildi."),
    (_API, "Əlçatanlıq yadda saxlanıldı."): ("Availability saved.", "Доступность сохранена.", "Uygunluk kaydedildi."),
    # ── timetable.availability ───────────────────────────────────────────
    (_AV, "Ad və ya istifadəçi adı…"): ("Name or username…", "Имя или логин…", "Ad veya kullanıcı adı…"),
    (_AV, "Adi"): ("Normal", "Обычный", "Normal"),
    (_AV, "Axtar"): ("Search", "Найти", "Ara"),
    (_AV, "Bu müəllimin əhatənizdə fənni tapılmadı."): (
        "No subjects of this teacher were found in your scope.",
        "В вашей области не найдено предметов этого преподавателя.",
        "Kapsamınızda bu öğretmenin dersi bulunamadı.",
    ),
    (_AV, "Bu semestrdə sizin əhatənizdəki açılışlara müəllim təyin edilməyib."): (
        "No teachers are assigned to course offerings in your scope this semester.",
        "В этом семестре преподаватели не назначены на курсы вашей области.",
        "Bu dönem kapsamınızdaki derslere öğretmen atanmamış.",
    ),
    (_AV, "Dövr et"): ("Cycle", "По кругу", "Döngü"),
    (_AV, "Dəyişdirilə bilən saatlar"): ("Flexible hours", "Гибкие часы", "Değiştirilebilir saatler"),
    (_AV, "Dəyər %(low)s–%(high)s aralığında olmalıdır."): (
        "The value must be between %(low)s and %(high)s.",
        "Значение должно быть в диапазоне %(low)s–%(high)s.",
        "Değer %(low)s–%(high)s aralığında olmalıdır.",
    ),
    (_AV, "Fırça (səviyyə seçimi)"): ("Brush (level selection)", "Кисть (выбор уровня)", "Fırça (seviye seçimi)"),
    (_AV, "Fırça:"): ("Brush:", "Кисть:", "Fırça:"),
    (_AV, "Fənləri (bu semestr)"): ("Subjects (this semester)", "Предметы (этот семестр)", "Dersleri (bu dönem)"),
    (_AV, "Fənn"): ("Subject", "Предмет", "Ders"),
    (_AV, "Fənn prioriteti"): ("Subject priority", "Приоритет предмета", "Ders önceliği"),
    (_AV, "Gündə maksimum cüt"): ("Max. pairs per day", "Макс. пар в день", "Günde en fazla ders"),
    (_AV, "Gələ bilmədiyi xanalar"): ("Unavailable slots", "Недоступные ячейки", "Gelemediği saatler"),
    (_AV, "Həftədə maksimum iş günü"): (
        "Max. working days per week",
        "Макс. рабочих дней в неделю",
        "Haftada en fazla iş günü",
    ),
    (_AV, "Həftəlik şəbəkə: hər xana bir dərs saatıdır (cüt = 2 saat)."): (
        "Weekly grid: each cell is one class period (a pair = 2 hours).",
        "Недельная сетка: каждая ячейка — одна пара (пара = 2 часа).",
        "Haftalık tablo: her hücre bir ders saatidir (çift ders = 2 saat).",
    ),
    (
        _AV,
        "Klik — səviyyə dəyişir. Klaviatura: oxlarla gəzin, Boşluq — dövr, 1–4 — səviyyəni birbaşa seçin. Gün başlığı — bütün günü «gələ bilmir» ⇄ «neytral».",
    ): (
        "Click changes the level. Keyboard: move with arrows, Space cycles, 1–4 picks a level directly. Day header toggles the whole day «unavailable» ⇄ «neutral».",
        "Клик меняет уровень. Клавиатура: стрелки — перемещение, Пробел — по кругу, 1–4 — выбрать уровень. Заголовок дня — весь день «недоступен» ⇄ «нейтрально».",
        "Tıklama seviyeyi değiştirir. Klavye: oklarla gezinin, Boşluk döngü yapar, 1–4 seviyeyi doğrudan seçer. Gün başlığı tüm günü «gelemez» ⇄ «nötr» yapar.",
    ),
    (_AV, "Müəllim axtar"): ("Search teacher", "Поиск преподавателя", "Öğretmen ara"),
    (_AV, "Müəllim seçin"): ("Select a teacher", "Выберите преподавателя", "Öğretmen seçin"),
    (_AV, "Müəllim tapılmadı"): ("No teacher found", "Преподаватель не найден", "Öğretmen bulunamadı"),
    (_AV, "Müəllim əlçatanlığı"): ("Teacher availability", "Доступность преподавателя", "Öğretmen uygunluğu"),
    (_AV, "Müəllimlər"): ("Teachers", "Преподаватели", "Öğretmenler"),
    (_AV, "Növ (tapşırıq saatı)"): ("Type (workload hours)", "Вид (часы нагрузки)", "Tür (yük saati)"),
    (_AV, "Prioritet (1 — adi, 5 — ən yüksək)"): (
        "Priority (1 — normal, 5 — highest)",
        "Приоритет (1 — обычный, 5 — наивысший)",
        "Öncelik (1 — normal, 5 — en yüksek)",
    ),
    (_AV, "Qeyd"): ("Note", "Примечание", "Not"),
    (_AV, "Qruplar"): ("Groups", "Группы", "Gruplar"),
    (_AV, "Saat"): ("Time", "Время", "Saat"),
    (
        _AV,
        "Soldakı siyahıdan müəllimi seçin — gələ bilmədiyi günləri, olmayan və dəyişdirilə bilən saatları qeyd edin.",
    ): (
        "Pick a teacher from the list on the left and mark the days they cannot come, unavailable and flexible hours.",
        "Выберите преподавателя в списке слева и отметьте дни, когда он не может прийти, недоступные и гибкие часы.",
        "Soldaki listeden öğretmeni seçin; gelemediği günleri, uygun olmayan ve değiştirilebilir saatleri işaretleyin.",
    ),
    (_AV, "Son dəyişiklik:"): ("Last change:", "Последнее изменение:", "Son değişiklik:"),
    (_AV, "Tam ədəd daxil edin."): ("Enter a whole number.", "Введите целое число.", "Tam sayı girin."),
    (_AV, "Yadda saxla"): ("Save", "Сохранить", "Kaydet"),
    (_AV, "Yadda saxlanılmadı — yenidən cəhd edin."): (
        "Not saved — please try again.",
        "Не сохранено — попробуйте снова.",
        "Kaydedilmedi — tekrar deneyin.",
    ),
    (_AV, "boş"): ("empty", "пусто", "boş"),
    (_AV, "doldurulub"): ("filled in", "заполнено", "dolduruldu"),
    (_AV, "laboratoriya"): ("laboratory", "лабораторная", "laboratuvar"),
    (_AV, "mühazirə"): ("lecture", "лекция", "teorik ders"),
    (_AV, "seminar"): ("seminar", "семинар", "seminer"),
    (_AV, "Şəbəkədə naməlum səviyyə var."): (
        "The grid contains an unknown level.",
        "В сетке есть неизвестный уровень.",
        "Tabloda bilinmeyen bir seviye var.",
    ),
    (_AV, "Əlçatanlıq yadda saxlanılmadı — xanaları yoxlayın."): (
        "Availability was not saved — check the fields.",
        "Доступность не сохранена — проверьте поля.",
        "Uygunluk kaydedilmedi — alanları kontrol edin.",
    ),
    (_AV, "Əlçatanlıq şəbəkəsi"): ("Availability grid", "Сетка доступности", "Uygunluk tablosu"),
    # ── timetable.edit ───────────────────────────────────────────────────
    (_ED, "%(building)s korpusunda həmin vaxt boş otaq qalmır (%(week)s)."): (
        "No free room is left in building %(building)s at that time (%(week)s).",
        "В корпусе %(building)s в это время нет свободных аудиторий (%(week)s).",
        "%(building)s binasında o saatte boş derslik kalmıyor (%(week)s).",
    ),
    (_ED, "%(group)s qrupunun günündə boş cüt yaranır (%(week)s) — qrupda boşluq qadağandır."): (
        "An idle pair appears in group %(group)s's day (%(week)s) — gaps are not allowed for groups.",
        "В дне группы %(group)s появляется «окно» (%(week)s) — окна у групп запрещены.",
        "%(group)s grubunun gününde boş ders oluşuyor (%(week)s) — grupta boşluk yasak.",
    ),
    (_ED, "%(group)s qrupunun həmin vaxt dərsi var: %(subjects)s (%(week)s)."): (
        "Group %(group)s already has a class at that time: %(subjects)s (%(week)s).",
        "У группы %(group)s в это время занятие: %(subjects)s (%(week)s).",
        "%(group)s grubunun o saatte dersi var: %(subjects)s (%(week)s).",
    ),
    (_ED, "Bu saat %(group)s qrupunun növbəsinə daxil deyil."): (
        "This time is outside group %(group)s's shift.",
        "Это время не входит в смену группы %(group)s.",
        "Bu saat %(group)s grubunun vardiyasına dahil değil.",
    ),
    (_ED, "Dərs kilidlidir — əvvəlcə kilidi açın."): (
        "The class is locked — unlock it first.",
        "Занятие заблокировано — сначала разблокируйте.",
        "Ders kilitli — önce kilidi açın.",
    ),
    (_ED, "Dərs qaralamada tapılmadı."): (
        "Class not found in the draft.",
        "Занятие не найдено в черновике.",
        "Ders taslakta bulunamadı.",
    ),
    (_ED, "Gün və dərs saatı düzgün seçilməlidir."): (
        "Select a valid day and class period.",
        "Выберите корректные день и пару.",
        "Geçerli bir gün ve ders saati seçin.",
    ),
    (_ED, "Müəllim %(teacher)s həmin vaxt məşğuldur: %(subjects)s (%(week)s)."): (
        "Teacher %(teacher)s is busy at that time: %(subjects)s (%(week)s).",
        "Преподаватель %(teacher)s в это время занят: %(subjects)s (%(week)s).",
        "Öğretmen %(teacher)s o saatte meşgul: %(subjects)s (%(week)s).",
    ),
    (_ED, "Müəllim bu saatda gələ bilmir (əlçatanlıq)."): (
        "The teacher cannot come at this time (availability).",
        "Преподаватель не может в это время (доступность).",
        "Öğretmen bu saatte gelemez (uygunluk).",
    ),
    (_ED, "Qaralama köhnəlib (açılışlar dəyişib) — yenidən işlədin."): (
        "The draft is outdated (course offerings changed) — run it again.",
        "Черновик устарел (курсы изменились) — запустите заново.",
        "Taslak eskidi (dersler değişti) — yeniden çalıştırın.",
    ),
    (_ED, "alt həftə"): ("even week", "нижняя неделя", "alt hafta"),
    (_ED, "başqa fakültənin dərc olunmuş dərsi"): (
        "a published class of another faculty",
        "опубликованное занятие другого факультета",
        "başka fakültenin yayımlanmış dersi",
    ),
    (_ED, "üst həftə"): ("odd week", "верхняя неделя", "üst hafta"),
    # ── timetable.home ───────────────────────────────────────────────────
    (_HM, "Aç"): ("Open", "Открыть", "Aç"),
    (_HM, "Bakalavr — səhər və günorta, magistr — yalnız axşam; istənilən qrup üçün istisna."): (
        "Bachelor — morning and afternoon, master — evening only; exceptions for any group.",
        "Бакалавриат — утро и день, магистратура — только вечер; исключения для любой группы.",
        "Lisans — sabah ve öğleden sonra, yüksek lisans — yalnızca akşam; her grup için istisna.",
    ),
    (_HM, "Bax, düzəlt, dərc et"): (
        "Review, adjust, publish",
        "Просмотр, правка, публикация",
        "İncele, düzelt, yayımla",
    ),
    (_HM, "Bu semestr üçün hələ işləmə yoxdur"): (
        "No runs for this semester yet",
        "Для этого семестра ещё нет запусков",
        "Bu dönem için henüz çalıştırma yok",
    ),
    (_HM, "Gələ bilmədiyi günlər, olmayan və dəyişdirilə bilən saatlar, gündəlik limit, prioritet."): (
        "Days off, unavailable and flexible hours, daily limit, priority.",
        "Недоступные дни, недоступные и гибкие часы, дневной лимит, приоритет.",
        "Gelemediği günler, uygun olmayan ve değiştirilebilir saatler, günlük sınır, öncelik.",
    ),
    (_HM, "Hər işləmə ayrıca qaralamadır — canlı cədvələ yalnız «Dərc et» ilə keçir."): (
        "Each run is a separate draft — it reaches the live timetable only via «Publish».",
        "Каждый запуск — отдельный черновик; в действующее расписание он попадает только через «Опубликовать».",
        "Her çalıştırma ayrı bir taslaktır — canlı programa yalnızca «Yayımla» ile geçer.",
    ),
    (_HM, "Müəllim boş cütü"): ("Teacher idle pairs", "«Окна» преподавателей", "Öğretmen boş dersleri"),
    (_HM, "Müəllim əlçatanlığı"): ("Teacher availability", "Доступность преподавателей", "Öğretmen uygunluğu"),
    (_HM, "Qrup / müəllim / otaq şəbəkəsi, kilid və köçürmə; «Dərc et» canlı cədvəli bir dəfəyə yazır."): (
        "Group / teacher / room grids, locking and moving; «Publish» writes the live timetable in one step.",
        "Сетки по группам / преподавателям / аудиториям, блокировка и перенос; «Опубликовать» записывает расписание за один шаг.",
        "Grup / öğretmen / derslik tabloları, kilitleme ve taşıma; «Yayımla» canlı programı tek adımda yazar.",
    ),
    (_HM, "Qrup növbələri"): ("Group shifts", "Смены групп", "Grup vardiyaları"),
    (_HM, "Status"): ("Status", "Статус", "Durum"),
    (_HM, "Sərt pozuntu"): ("Hard violations", "Жёсткие нарушения", "Katı ihlal"),
    (_HM, "Yaradan"): ("Created by", "Создал", "Oluşturan"),
    (_HM, "Yeni işləmə"): ("New run", "Новый запуск", "Yeni çalıştırma"),
    (_HM, "Yerləşdirilib"): ("Placed", "Размещено", "Yerleştirildi"),
    (_HM, "Yoxla və işlət"): ("Check and run", "Проверка и запуск", "Kontrol et ve çalıştır"),
    (_HM, "«Məlumatı yoxla» tələb ilə tutumu müqayisə edir; sonra mühərrik cədvəli qurur."): (
        "«Check data» compares demand with capacity; then the engine builds the timetable.",
        "«Проверить данные» сравнивает потребность с ёмкостью; затем движок строит расписание.",
        "«Verileri kontrol et» talebi kapasiteyle karşılaştırır; ardından motor programı oluşturur.",
    ),
    (_HM, "İş axını"): ("Workflow", "Порядок работы", "İş akışı"),
    (_HM, "İşləmələr"): ("Runs", "Запуски", "Çalıştırmalar"),
    (_HM, "Əhatə"): ("Scope", "Охват", "Kapsam"),
    (_HM, "Əməliyyat"): ("Action", "Действие", "İşlem"),
    (_HM, "Əvvəlcə müəllim əlçatanlığını və qrup növbələrini yoxlayın, sonra «Yeni işləmə» ilə cədvəl qurun."): (
        "First check teacher availability and group shifts, then build a timetable with «New run».",
        "Сначала проверьте доступность преподавателей и смены групп, затем постройте расписание через «Новый запуск».",
        "Önce öğretmen uygunluğunu ve grup vardiyalarını kontrol edin, sonra «Yeni çalıştırma» ile program oluşturun.",
    ),
    # ── timetable.model ──────────────────────────────────────────────────
    (_MD, "Axın yoxdur (hər qrup ayrıca)"): (
        "No streams (each group separately)",
        "Без потоков (каждая группа отдельно)",
        "Akış yok (her grup ayrı)",
    ),
    (_MD, "Axşam"): ("Evening", "Вечер", "Akşam"),
    (_MD, "Bakalavr"): ("Bachelor", "Бакалавриат", "Lisans"),
    (_MD, "Doktorantura"): ("Doctoral", "Докторантура", "Doktora"),
    (_MD, "Dərc edilib"): ("Published", "Опубликовано", "Yayımlandı"),
    (_MD, "Dəyişdirilə bilən saat"): ("Flexible hour", "Гибкий час", "Değiştirilebilir saat"),
    (_MD, "Eyni fənn + eyni müəllim + eyni dil"): (
        "Same subject + same teacher + same language",
        "Тот же предмет + преподаватель + язык",
        "Aynı ders + aynı öğretmen + aynı dil",
    ),
    (_MD, "Fakültə"): ("Faculty", "Факультет", "Fakülte"),
    (_MD, "Günorta"): ("Afternoon", "День", "Öğleden sonra"),
    (_MD, "Gələ bilmir"): ("Unavailable", "Недоступен", "Gelemez"),
    (_MD, "Hazırdır"): ("Ready", "Готово", "Hazır"),
    (_MD, "Ləğv edilib"): ("Discarded", "Отменено", "İptal edildi"),
    (_MD, "Magistr"): ("Master", "Магистратура", "Yüksek lisans"),
    (_MD, "Neytral"): ("Neutral", "Нейтрально", "Nötr"),
    (_MD, "Növbədə"): ("Queued", "В очереди", "Kuyrukta"),
    (_MD, "Qaralama"): ("Draft", "Черновик", "Taslak"),
    (_MD, "Qiyabi (bütün pillələr)"): (
        "Part-time (all levels)",
        "Заочное (все уровни)",
        "Uzaktan/kısmi (tüm seviyeler)",
    ),
    (_MD, "Seçilmiş qruplar"): ("Selected groups", "Выбранные группы", "Seçili gruplar"),
    (_MD, "Səhər"): ("Morning", "Утро", "Sabah"),
    (_MD, "Tədris tapşırığındakı birləşmələr + alt qruplar"): (
        "Unions in the teaching task + subgroups",
        "Объединения в учебном поручении + подгруппы",
        "Öğretim görevindeki birleşmeler + alt gruplar",
    ),
    (_MD, "Uğursuz"): ("Failed", "Ошибка", "Başarısız"),
    (_MD, "cədvəl işləmələri"): ("timetable runs", "запуски расписания", "program çalıştırmaları"),
    (_MD, "cədvəl işləməsi"): ("timetable run", "запуск расписания", "program çalıştırması"),
    (_MD, "müəllim əlçatanlıqları"): ("teacher availabilities", "доступность преподавателей", "öğretmen uygunlukları"),
    (_MD, "müəllim əlçatanlığı"): ("teacher availability", "доступность преподавателя", "öğretmen uygunluğu"),
    (_MD, "qaralama slot"): ("draft slot", "слот черновика", "taslak slot"),
    (_MD, "qaralama slotlar"): ("draft slots", "слоты черновика", "taslak slotlar"),
    (_MD, "qrup növbə siyasəti"): ("group shift policy", "политика смен группы", "grup vardiya politikası"),
    (_MD, "qrup növbə siyasətləri"): ("group shift policies", "политики смен групп", "grup vardiya politikaları"),
    (_MD, "Üstünlük verilir"): ("Preferred", "Предпочтительно", "Tercih edilir"),
    (_MD, "İxtisas"): ("Programme", "Специальность", "Bölüm"),
    (_MD, "İşləyir"): ("Running", "Выполняется", "Çalışıyor"),
    # ── timetable.nav / page ─────────────────────────────────────────────
    (_NV, "Avtomatik cədvəl bölmələri"): (
        "Automatic timetable sections",
        "Разделы автоматического расписания",
        "Otomatik program bölümleri",
    ),
    (_NV, "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur."): (
        "You do not have permission to manage the timetable.",
        "У вас нет права управлять расписанием.",
        "Ders programını yönetme izniniz yok.",
    ),
    (_NV, "Müəllim əlçatanlığı"): ("Teacher availability", "Доступность преподавателей", "Öğretmen uygunluğu"),
    (_NV, "Növbələr"): ("Shifts", "Смены", "Vardiyalar"),
    (_NV, "Yeni işləmə"): ("New run", "Новый запуск", "Yeni çalıştırma"),
    (_NV, "İşləmələr"): ("Runs", "Запуски", "Çalıştırmalar"),
    (_NV, "Əl ilə redaktor"): ("Manual editor", "Ручной редактор", "Elle düzenleyici"),
    (_PG, "Avtomatik dərs cədvəli"): ("Automatic timetable", "Автоматическое расписание", "Otomatik ders programı"),
    (
        _PG,
        "Müəllim əlçatanlığı və qrup növbələri əsasında qrupda boşluqsuz həftəlik cədvəl qurulur; qaralama yoxlanıldıqdan sonra dərc edilir.",
    ): (
        "A gap-free weekly timetable is built from teacher availability and group shifts; the draft is published after review.",
        "Недельное расписание без «окон» у групп строится по доступности преподавателей и сменам групп; черновик публикуется после проверки.",
        "Öğretmen uygunluğu ve grup vardiyalarına göre gruplarda boşluksuz haftalık program oluşturulur; taslak incelendikten sonra yayımlanır.",
    ),
    (_PG, "Semestr"): ("Semester", "Семестр", "Dönem"),
    (_PG, "Semestr seçin"): ("Select a semester", "Выберите семестр", "Dönem seçin"),
    # ── timetable.policy ─────────────────────────────────────────────────
    (_PO, "Axtar"): ("Search", "Найти", "Ara"),
    (_PO, "Bu semestr açılışı olan qruplar. İstisna yalnız həmin qrupa aiddir (məs. 1-ci kurs yalnız səhər)."): (
        "Groups with course offerings this semester. An exception applies to that group only (e.g. 1st year mornings only).",
        "Группы с курсами в этом семестре. Исключение относится только к этой группе (напр., 1-й курс только утром).",
        "Bu dönem dersi olan gruplar. İstisna yalnızca o gruba uygulanır (ör. 1. sınıf yalnızca sabah).",
    ),
    (_PO, "Bu semestrdə sizin əhatənizdə açılışı olan qrup tapılmadı."): (
        "No groups with course offerings were found in your scope this semester.",
        "В этом семестре в вашей области нет групп с курсами.",
        "Bu dönem kapsamınızda dersi olan grup bulunamadı.",
    ),
    (_PO, "Cədvələ daxil etmə"): ("Exclude from timetable", "Не включать в расписание", "Programa dahil etme"),
    (_PO, "Daxil etmə"): ("Exclude", "Исключить", "Dahil etme"),
    (_PO, "Defolta qaytar"): ("Reset to default", "Сбросить к умолчанию", "Varsayılana dön"),
    (_PO, "Gündə maks."): ("Max./day", "Макс./день", "Günde maks."),
    (_PO, "Gündə maks. cüt"): ("Max. pairs/day", "Макс. пар/день", "Günde maks. ders"),
    (_PO, "Gündə maksimum cüt"): ("Max. pairs per day", "Макс. пар в день", "Günde en fazla ders"),
    (_PO, "Gündəlik limit 1–%(max)s aralığında olmalıdır."): (
        "The daily limit must be between 1 and %(max)s.",
        "Дневной лимит должен быть от 1 до %(max)s.",
        "Günlük sınır 1–%(max)s aralığında olmalıdır.",
    ),
    (_PO, "Naməlum pillə."): ("Unknown level.", "Неизвестный уровень.", "Bilinmeyen seviye."),
    (_PO, "Növbələr"): ("Shifts", "Смены", "Vardiyalar"),
    (_PO, "Pillə / forma"): ("Level / form", "Уровень / форма", "Seviye / biçim"),
    (_PO, "Pillə defoltları"): ("Level defaults", "Значения по уровням", "Seviye varsayılanları"),
    (_PO, "Qrup"): ("Group", "Группа", "Grup"),
    (_PO, "Qrup adı…"): ("Group name…", "Название группы…", "Grup adı…"),
    (_PO, "Qrup axtar"): ("Search group", "Поиск группы", "Grup ara"),
    (_PO, "Qrup növbələri"): ("Group shifts", "Смены групп", "Grup vardiyaları"),
    (_PO, "Qrup yoxdur"): ("No groups", "Нет групп", "Grup yok"),
    (_PO, "Qrup üçün ayrıca istisna yoxdursa bu qayda işləyir. Magistr dərsi susmaya görə yalnız axşam qoyulur."): (
        "This rule applies when a group has no own exception. Master's classes are evening-only by default.",
        "Правило действует, если у группы нет своего исключения. Занятия магистратуры по умолчанию только вечером.",
        "Grubun kendi istisnası yoksa bu kural geçerlidir. Yüksek lisans dersleri varsayılan olarak yalnızca akşam.",
    ),
    (_PO, "Qruplar"): ("Groups", "Группы", "Gruplar"),
    (_PO, "Siyasət yadda saxlanılmadı — sahələri yoxlayın."): (
        "The policy was not saved — check the fields.",
        "Политика не сохранена — проверьте поля.",
        "Politika kaydedilmedi — alanları kontrol edin.",
    ),
    (_PO, "Tələbə"): ("Students", "Студенты", "Öğrenci"),
    (_PO, "Yadda saxla"): ("Save", "Сохранить", "Kaydet"),
    (_PO, "Yadda saxlanılmadı — sahələri yoxlayın."): (
        "Not saved — check the fields.",
        "Не сохранено — проверьте поля.",
        "Kaydedilmedi — alanları kontrol edin.",
    ),
    (_PO, "alt qrup:"): ("subgroup of:", "подгруппа:", "alt grup:"),
    (_PO, "dəyişdirilib"): ("customised", "изменено", "değiştirildi"),
    (_PO, "istisna"): ("exception", "исключение", "istisna"),
    (_PO, "qiyabi"): ("part-time", "заочная", "uzaktan/kısmi"),
    (_PO, "susmaya görə"): ("default", "по умолчанию", "varsayılan"),
    (_PO, "İcazəli növbələr"): ("Allowed shifts", "Разрешённые смены", "İzinli vardiyalar"),
    (_PO, "Əməliyyat"): ("Action", "Действие", "İşlem"),
    (_PO, "Ən azı bir növbə seçilməlidir."): (
        "Select at least one shift.",
        "Выберите хотя бы одну смену.",
        "En az bir vardiya seçilmelidir.",
    ),
    (_PO, "əyani"): ("full-time", "очная", "örgün"),
    # ── timetable.precheck ───────────────────────────────────────────────
    (_PC, "Bu dərslər yerləşdirilməyəcək — səbəbi sətirdə göstərilib."): (
        "These classes will not be placed — the reason is shown on each line.",
        "Эти занятия не будут размещены — причина указана в строке.",
        "Bu dersler yerleştirilmeyecek — neden satırda gösterilmiştir.",
    ),
    (_PC, "Bəzi dərslər üçün heç bir mümkün vaxt yoxdur"): (
        "Some classes have no possible time at all",
        "Для некоторых занятий нет ни одного возможного времени",
        "Bazı dersler için hiçbir uygun saat yok",
    ),
    (_PC, "Cədvələ daxil edilməyən qruplar (qiyabi və ya siyasətdə istisna)"): (
        "Groups excluded from the timetable (part-time or policy exception)",
        "Группы, не включённые в расписание (заочные или исключение в политике)",
        "Programa dahil edilmeyen gruplar (uzaktan/kısmi veya politika istisnası)",
    ),
    (_PC, "Kilidli dərs indiki növbə/əlçatanlıqdan kənardadır"): (
        "A locked class is outside the current shift/availability",
        "Заблокированное занятие вне текущей смены/доступности",
        "Kilitli ders mevcut vardiya/uygunluk dışında",
    ),
    (_PC, "Korpusda eyni anda lazım olan otaq sayı mövcud otaqlardan çoxdur"): (
        "A building needs more simultaneous rooms than it has",
        "Корпусу одновременно нужно больше аудиторий, чем есть",
        "Binada aynı anda gereken derslik sayısı mevcut derslikten fazla",
    ),
    (_PC, "Lazım olan / mövcud otaq."): (
        "Needed / available rooms.",
        "Нужно / имеется аудиторий.",
        "Gereken / mevcut derslik.",
    ),
    (_PC, "Magistr qruplarının dərsi axşam xanalarına sığmır"): (
        "Master's group classes do not fit into the evening slots",
        "Занятия магистрантов не помещаются в вечерние пары",
        "Yüksek lisans gruplarının dersleri akşam saatlerine sığmıyor",
    ),
    (_PC, "Mühazirə axınları (bir neçə qrup birlikdə)"): (
        "Lecture streams (several groups together)",
        "Лекционные потоки (несколько групп вместе)",
        "Teorik ders akışları (birkaç grup birlikte)",
    ),
    (_PC, "Müəllimi təyin edilməmiş dərslər (vakant) — yalnız qrupa görə yerləşir"): (
        "Classes without an assigned teacher (vacant) — placed by group constraints only",
        "Занятия без назначенного преподавателя (вакансия) — размещаются только по группе",
        "Öğretmeni atanmamış dersler (boş kadro) — yalnızca gruba göre yerleşir",
    ),
    (_PC, "Müəllimin həftəlik dərsi uyğun boş xanalardan çoxdur"): (
        "A teacher's weekly classes exceed the suitable free slots",
        "Недельная нагрузка преподавателя превышает подходящие свободные ячейки",
        "Öğretmenin haftalık dersi uygun boş saatlerden fazla",
    ),
    (_PC, "Müəllimin vaxtı çox sıxdır (80%-dən çox dolu)"): (
        "A teacher's time is very tight (over 80% full)",
        "Время преподавателя очень плотное (заполнено более 80%)",
        "Öğretmenin zamanı çok sıkışık (%80'den fazla dolu)",
    ),
    (_PC, "Qrupun həftəlik dərsi icazəli xanalara sığmır"): (
        "A group's weekly classes do not fit into its allowed slots",
        "Недельная нагрузка группы не помещается в разрешённые ячейки",
        "Grubun haftalık dersi izinli saatlere sığmıyor",
    ),
    (_PC, "Saat bölgüsü tapılmayan açılışlar (plan/tapşırıqda saat yoxdur)"): (
        "Course offerings without an hour breakdown (no hours in plan/task)",
        "Курсы без распределения часов (нет часов в плане/поручении)",
        "Saat dağılımı bulunamayan dersler (plan/görevde saat yok)",
    ),
    (_PC, "Tələb / axşam tutumu. Növbə siyasətində magistr üçün günortanı açmaq olar."): (
        "Demand / evening capacity. You can allow afternoons for master's groups in the shift policy.",
        "Потребность / вечерняя ёмкость. В политике смен можно разрешить магистрам дневные пары.",
        "Talep / akşam kapasitesi. Vardiya politikasında yüksek lisans için öğleden sonrayı açabilirsiniz.",
    ),
    (_PC, "Tələb / tutum (cüt/həftə) — boşluqsuz cədvəl çətinləşə bilər."): (
        "Demand / capacity (pairs/week) — a gap-free timetable may be hard.",
        "Потребность / ёмкость (пар/неделя) — расписание без «окон» может быть затруднено.",
        "Talep / kapasite (ders/hafta) — boşluksuz program zorlaşabilir.",
    ),
    (_PC, "Tələb / tutum (cüt/həftə). Növbəni genişləndirin və ya gündəlik limiti artırın."): (
        "Demand / capacity (pairs/week). Widen the shift or raise the daily limit.",
        "Потребность / ёмкость (пар/неделя). Расширьте смену или увеличьте дневной лимит.",
        "Talep / kapasite (ders/hafta). Vardiyayı genişletin veya günlük sınırı artırın.",
    ),
    (_PC, "Tələb / tutum (cüt/həftə). Əlçatanlığı genişləndirin və ya dərsi başqasına verin."): (
        "Demand / capacity (pairs/week). Widen the availability or reassign the class.",
        "Потребность / ёмкость (пар/неделя). Расширьте доступность или передайте занятие другому.",
        "Talep / kapasite (ders/hafta). Uygunluğu genişletin veya dersi başkasına verin.",
    ),
    (_PC, "axının qruplarının ortaq növbəsi yoxdur"): (
        "the stream's groups have no common shift",
        "у групп потока нет общей смены",
        "akıştaki grupların ortak vardiyası yok",
    ),
    (_PC, "müəllim qrupun növbəsində heç gələ bilmir"): (
        "the teacher can never come during the group's shift",
        "преподаватель не может прийти ни в одну пару смены группы",
        "öğretmen grubun vardiyasında hiç gelemiyor",
    ),
    (_PC, "qrup üçün icazəli xana yoxdur"): (
        "the group has no allowed slots",
        "у группы нет разрешённых ячеек",
        "grup için izinli saat yok",
    ),
    # ── timetable.publish ────────────────────────────────────────────────
    (_PB, "Avtomatik cədvəl generatoru ilə dərc"): (
        "Published with the automatic timetable generator",
        "Опубликовано генератором расписания",
        "Otomatik program oluşturucuyla yayımlandı",
    ),
    (_PB, "Qaralamada yerləşdirilmiş dərs yoxdur."): (
        "The draft has no placed classes.",
        "В черновике нет размещённых занятий.",
        "Taslakta yerleştirilmiş ders yok.",
    ),
    (_PB, "Yalnız hazır (tamamlanmış) qaralama dərc edilə bilər."): (
        "Only a ready (finished) draft can be published.",
        "Опубликовать можно только готовый черновик.",
        "Yalnızca hazır (tamamlanmış) taslak yayımlanabilir.",
    ),
}

STRINGS.update(
    {
        # ── timetable.review ─────────────────────────────────────────────────
        (_RV, "ALT"): ("EVEN", "НИЖН", "ALT"),
        (_RV, "Alt həftə"): ("Even week", "Нижняя неделя", "Alt hafta"),
        (_RV, "Arzuolunmaz saat"): ("Discouraged hours", "Нежелательные часы", "İstenmeyen saat"),
        (_RV, "Axtar…"): ("Search…", "Поиск…", "Ara…"),
        (_RV, "Baxış"): ("View", "Вид", "Görünüm"),
        (_RV, "Bağla"): ("Close", "Закрыть", "Kapat"),
        (
            _RV,
            "Bu dərslərin müəllimi (dərs yükü bölgüsündən) açılışın jurnal sahibindən fərqlidir. Canlı cədvəldə slotun ayrıca müəllim sahəsi olmadığı üçün jurnal sahibi göstəriləcək.",
        ): (
            "These classes' teacher (from the workload split) differs from the offering's journal owner. The live timetable has no per-slot teacher field, so the journal owner will be shown.",
            "Преподаватель этих занятий (по распределению нагрузки) отличается от владельца журнала курса. В действующем расписании нет поля преподавателя слота, поэтому будет показан владелец журнала.",
            "Bu derslerin öğretmeni (yük dağılımından) dersin yoklama sahibinden farklı. Canlı programda slot için ayrı öğretmen alanı olmadığından yoklama sahibi gösterilecek.",
        ),
        (_RV, "Bu qaralama canlı cədvələ dərc edilib"): (
            "This draft has been published to the live timetable",
            "Этот черновик опубликован в действующем расписании",
            "Bu taslak canlı programa yayımlandı",
        ),
        (_RV, "Bu qaralama ləğv edilsin? Canlı cədvəl dəyişməyəcək."): (
            "Discard this draft? The live timetable will not change.",
            "Отменить этот черновик? Действующее расписание не изменится.",
            "Bu taslak iptal edilsin mi? Canlı program değişmeyecek.",
        ),
        (_RV, "Bölünmüş tədris"): ("Split teaching", "Разделённое преподавание", "Bölünmüş öğretim"),
        (_RV, "Bütün dərslər yerləşdirilib."): (
            "All classes are placed.",
            "Все занятия размещены.",
            "Tüm dersler yerleştirildi.",
        ),
        (_RV, "Cədvəli dərc et"): ("Publish timetable", "Опубликовать расписание", "Programı yayımla"),
        (_RV, "Diqqət: %(total)s dərs yerləşdirilməyib — dərcdən sonra canlı cədvəldə olmayacaq."): (
            "Warning: %(total)s class(es) are not placed — they will not be in the live timetable after publishing.",
            "Внимание: не размещено занятий — %(total)s; после публикации их не будет в расписании.",
            "Dikkat: %(total)s ders yerleştirilmedi — yayımdan sonra canlı programda olmayacak.",
        ),
        (_RV, "Dərc et"): ("Publish", "Опубликовать", "Yayımla"),
        (_RV, "Dərc olunmuşdan fərq"): ("Changes vs published", "Отличия от опубликованного", "Yayımlanandan fark"),
        (_RV, "Dərs"): ("Class", "Занятие", "Ders"),
        (_RV, "Dərs saatı"): ("Class period", "Пара", "Ders saati"),
        (_RV, "Fənn"): ("Subject", "Предмет", "Ders"),
        (_RV, "Gün"): ("Day", "День", "Gün"),
        (_RV, "Həftə"): ("Week", "Неделя", "Hafta"),
        (_RV, "Həftəlik cədvəl şəbəkəsi"): (
            "Weekly timetable grid",
            "Сетка недельного расписания",
            "Haftalık program tablosu",
        ),
        (_RV, "Həftəlik şəbəkə"): ("Weekly grid", "Недельная сетка", "Haftalık tablo"),
        (_RV, "Hər həftə"): ("Every week", "Каждую неделю", "Her hafta"),
        (_RV, "Kilidli"): ("Locked", "Заблокировано", "Kilitli"),
        (_RV, "Kilidlə / kilidi aç"): ("Lock / unlock", "Заблокировать / разблокировать", "Kilitle / kilidi aç"),
        (_RV, "Köçür"): ("Move", "Перенести", "Taşı"),
        (_RV, "Laboratoriya"): ("Laboratory", "Лабораторная", "Laboratuvar"),
        (_RV, "Ləğv et"): ("Discard", "Отменить", "İptal et"),
        (_RV, "Mühazirə"): ("Lecture", "Лекция", "Teorik ders"),
        (_RV, "Mühərrik işləyir — səhifə hazır olanda avtomatik yenilənəcək."): (
            "The engine is running — the page will refresh automatically when ready.",
            "Движок работает — страница обновится автоматически по готовности.",
            "Motor çalışıyor — sayfa hazır olunca otomatik yenilenecek.",
        ),
        (_RV, "Müəllim"): ("Teacher", "Преподаватель", "Öğretmen"),
        (_RV, "Müəllim boş cütü"): ("Teacher idle pairs", "«Окна» преподавателей", "Öğretmen boş dersleri"),
        (_RV, "Məşğələ"): ("Seminar", "Практика", "Uygulama"),
        (_RV, "Növ"): ("Type", "Вид", "Tür"),
        (_RV, "Otaq"): ("Room", "Аудитория", "Derslik"),
        (_RV, "Otaq (təklif)"): ("Room (suggested)", "Аудитория (предложение)", "Derslik (öneri)"),
        (
            _RV,
            "Qaralama canlı cədvələ yazılacaq: işləmədəki açılışların köhnə slotları yumşaq silinir və yerləşdirilmiş dərslər əlavə olunur. Müəllimlərə və qrupların tələbələrinə bir bildiriş göndərilir.",
        ): (
            "The draft will be written to the live timetable: the run's old slots are soft-deleted and the placed classes are added. Teachers and the groups' students receive one notification.",
            "Черновик будет записан в действующее расписание: старые слоты курсов запуска мягко удаляются, размещённые занятия добавляются. Преподаватели и студенты групп получат одно уведомление.",
            "Taslak canlı programa yazılacak: çalıştırmadaki derslerin eski slotları geçici silinir ve yerleştirilen dersler eklenir. Öğretmenlere ve grupların öğrencilerine bir bildirim gönderilir.",
        ),
        (_RV, "Qeyd"): ("Note", "Примечание", "Not"),
        (_RV, "Qrup"): ("Group", "Группа", "Grup"),
        (_RV, "Qruplar"): ("Groups", "Группы", "Gruplar"),
        (_RV, "Saat"): ("Time", "Время", "Saat"),
        (
            _RV,
            "Server sərt qaydaları yoxlayır: müəllim/qrup toqquşması, qrupda boşluq, növbə və «gələ bilmir» saatı.",
        ): (
            "The server checks hard rules: teacher/group clashes, group gaps, shifts and «unavailable» hours.",
            "Сервер проверяет жёсткие правила: конфликты преподавателя/группы, «окна» групп, смену и часы «недоступен».",
            "Sunucu katı kuralları denetler: öğretmen/grup çakışması, grupta boşluk, vardiya ve «gelemez» saati.",
        ),
        (_RV, "Seçim"): ("Selection", "Выбор", "Seçim"),
        (_RV, "Səbəb / qeyd (auditə düşür)"): (
            "Reason / note (recorded in the audit log)",
            "Причина / примечание (в журнал аудита)",
            "Neden / not (denetim kaydına düşer)",
        ),
        (_RV, "Sərt pozuntu"): ("Hard violations", "Жёсткие нарушения", "Katı ihlal"),
        (
            _RV,
            "Sərt qaydalar pozulmadan yer tapılmayan dərslər. Səbəbə baxın, lazım olsa əl ilə yerləşdirin və ya giriş məlumatını dəyişib yenidən işlədin.",
        ): (
            "Classes that could not be placed without breaking hard rules. Check the reason, place them manually if needed, or change the input data and run again.",
            "Занятия, для которых не нашлось места без нарушения жёстких правил. Посмотрите причину, при необходимости разместите вручную или измените данные и запустите снова.",
            "Katı kurallar ihlal edilmeden yer bulunamayan dersler. Nedene bakın, gerekirse elle yerleştirin veya giriş verilerini değiştirip yeniden çalıştırın.",
        ),
        (_RV, "Tək cütlük gün"): ("Single-class days", "Дни с одной парой", "Tek dersli gün"),
        (_RV, "Worker cavab vermir — brauzerdə işlət (qısa limit)"): (
            "Worker not responding — run in the browser (short limit)",
            "Воркер не отвечает — запустить в браузере (короткий лимит)",
            "Worker yanıt vermiyor — tarayıcıda çalıştır (kısa sınır)",
        ),
        (_RV, "Yenidən işlət (kilidlər qalır)"): (
            "Run again (locks kept)",
            "Запустить снова (блокировки сохраняются)",
            "Yeniden çalıştır (kilitler kalır)",
        ),
        (_RV, "Yerləşdir"): ("Place", "Разместить", "Yerleştir"),
        (_RV, "Yerləşdirilib"): ("Placed", "Размещено", "Yerleştirildi"),
        (_RV, "Yerləşdirilməyən dərslər"): ("Unplaced classes", "Неразмещённые занятия", "Yerleştirilemeyen dersler"),
        (_RV, "həftədə orta (üst/alt)"): (
            "weekly average (odd/even)",
            "среднее в неделю (верх./нижн.)",
            "haftalık ortalama (üst/alt)",
        ),
        (_RV, "qrup bir dərs üçün gəlir"): (
            "group comes for a single class",
            "группа приходит на одну пару",
            "grup tek ders için geliyor",
        ),
        (_RV, "san."): ("s", "с", "sn"),
        (_RV, "toqquşma + qrupda boşluq"): (
            "clashes + group gaps",
            "конфликты + «окна» групп",
            "çakışma + grupta boşluk",
        ),
        (_RV, "yaradıb:"): ("created by:", "создал:", "oluşturan:"),
        (_RV, "«dəyişdirilə bilən» xanalar"): ("«flexible» slots", "«гибкие» ячейки", "«değiştirilebilir» saatler"),
        (_RV, "ÜST"): ("ODD", "ВЕРХ", "ÜST"),
        (_RV, "Üst həftə"): ("Odd week", "Верхняя неделя", "Üst hafta"),
        (_RV, "İmtina"): ("Cancel", "Отмена", "Vazgeç"),
        (_RV, "İşləmə uğursuz oldu"): ("The run failed", "Запуск завершился ошибкой", "Çalıştırma başarısız oldu"),
        (_RV, "Əl ilə köçürülüb"): ("Moved manually", "Перенесено вручную", "Elle taşındı"),
        (_RV, "Əməliyyat yerinə yetirilmədi."): (
            "The action failed.",
            "Действие не выполнено.",
            "İşlem gerçekleştirilemedi.",
        ),
        # ── timetable.run ────────────────────────────────────────────────────
        (_RN, "30 saat = hər həftə 1 cüt; 15 saat = iki həftədən bir (üst və ya alt)."): (
            "30 hours = 1 pair every week; 15 hours = every other week (odd or even).",
            "30 часов = 1 пара каждую неделю; 15 часов = раз в две недели (верхняя или нижняя).",
            "30 saat = her hafta 1 ders; 15 saat = iki haftada bir (üst veya alt).",
        ),
        (_RN, "Alt qrup ailəsi (birləşik qrup + alt qruplar) avtomatik birlikdə götürülür."): (
            "A subgroup family (combined group + subgroups) is included together automatically.",
            "Семейство подгрупп (объединённая группа + подгруппы) включается автоматически.",
            "Alt grup ailesi (birleşik grup + alt gruplar) otomatik olarak birlikte alınır.",
        ),
        (_RN, "Axtar…"): ("Search…", "Поиск…", "Ara…"),
        (_RN, "Axın"): ("Streams", "Потоки", "Akış"),
        (_RN, "Axının qruplarının ortaq növbəsi yoxdur."): (
            "The stream's groups have no common shift.",
            "У групп потока нет общей смены.",
            "Akıştaki grupların ortak vardiyası yok.",
        ),
        (_RN, "Aşağı"): ("Down", "Вниз", "Aşağı"),
        (_RN, "Bu semestrdə açılışı olan qrup yoxdur."): (
            "No groups have course offerings this semester.",
            "В этом семестре нет групп с курсами.",
            "Bu dönem dersi olan grup yok.",
        ),
        (_RN, "Cərimə çəkiləri (ətraflı)"): (
            "Penalty weights (advanced)",
            "Веса штрафов (подробно)",
            "Ceza ağırlıkları (gelişmiş)",
        ),
        (_RN, "Dərc olunmuş cədvəldən fərq (sabitlik)"): (
            "Change vs published timetable (stability)",
            "Отличие от опубликованного (стабильность)",
            "Yayımlanan programdan fark (kararlılık)",
        ),
        (_RN, "Dərc olunmuş cədvəli mümkün qədər saxla (minimal dəyişiklik)"): (
            "Keep the published timetable as much as possible (minimal change)",
            "Максимально сохранить опубликованное расписание (минимальные изменения)",
            "Yayımlanan programı mümkün olduğunca koru (asgari değişiklik)",
        ),
        (_RN, "Dərs (hadisə)"): ("Classes (events)", "Занятия (события)", "Ders (olay)"),
        (_RN, "Effektiv tədris həftəsi"): (
            "Effective teaching weeks",
            "Эффективных учебных недель",
            "Etkin öğretim haftası",
        ),
        (_RN, "Eyni fənn eyni gün (mühazirə + məşğələ)"): (
            "Same subject on the same day (lecture + seminar)",
            "Один предмет в один день (лекция + практика)",
            "Aynı gün aynı ders (teorik + uygulama)",
        ),
        (_RN, "Eyni toxum + eyni məlumat → eyni başlanğıc; fərqli toxum alternativ variant verir."): (
            "Same seed + same data → same start; a different seed gives an alternative variant.",
            "Одинаковое зерно + данные → одинаковый старт; другое зерно даёт альтернативный вариант.",
            "Aynı tohum + aynı veri → aynı başlangıç; farklı tohum alternatif bir seçenek verir.",
        ),
        (_RN, "Fakültə"): ("Faculty", "Факультет", "Fakülte"),
        (_RN, "Fakültə seçin"): ("Select a faculty", "Выберите факультет", "Fakülte seçin"),
        (_RN, "Həftəlik cüt"): ("Weekly pairs", "Пар в неделю", "Haftalık ders"),
        (_RN, "Korpusda eyni anda boş otaq qalmayıb."): (
            "No free room is left in the building at the same time.",
            "В корпусе одновременно не осталось свободных аудиторий.",
            "Binada aynı anda boş derslik kalmadı.",
        ),
        (_RN, "Kritik problem tapılmadı — işlədə bilərsiniz."): (
            "No critical problems found — you can run.",
            "Критических проблем нет — можно запускать.",
            "Kritik sorun bulunamadı — çalıştırabilirsiniz.",
        ),
        (_RN, "Kritik problemlər var — işləmə yenə mümkündür, amma bəzi dərslər yerləşməyəcək."): (
            "There are critical problems — you can still run, but some classes will not be placed.",
            "Есть критические проблемы — запуск возможен, но часть занятий не будет размещена.",
            "Kritik sorunlar var — yine çalıştırabilirsiniz, ancak bazı dersler yerleşmeyecek.",
        ),
        (_RN, "Mühazirə axınları"): ("Lecture streams", "Лекционные потоки", "Teorik ders akışları"),
        (_RN, "Mümkün vaxt yoxdur."): ("There is no possible time.", "Нет возможного времени.", "Uygun saat yok."),
        (_RN, "Müəllim"): ("Teachers", "Преподаватели", "Öğretmen"),
        (_RN, "Müəllim bütün uyğun xanalarda başqa dərsdədir."): (
            "The teacher has another class in every suitable slot.",
            "Во всех подходящих ячейках у преподавателя другое занятие.",
            "Öğretmenin tüm uygun saatlerde başka dersi var.",
        ),
        (_RN, "Müəllim prioriteti"): ("Teacher priority", "Приоритет преподавателей", "Öğretmen önceliği"),
        (_RN, "Müəllim qrupun növbəsində heç gələ bilmir."): (
            "The teacher can never come during the group's shift.",
            "Преподаватель не может прийти ни в одну пару смены группы.",
            "Öğretmen grubun vardiyasında hiç gelemiyor.",
        ),
        (_RN, "Müəllim seçin"): ("Select a teacher", "Выберите преподавателя", "Öğretmen seçin"),
        (_RN, "Müəllim uyğun xanalarda başqa fakültənin dərc olunmuş dərsindədir."): (
            "In the suitable slots the teacher has published classes of another faculty.",
            "В подходящих ячейках у преподавателя опубликованные занятия другого факультета.",
            "Uygun saatlerde öğretmenin başka fakültenin yayımlanmış dersi var.",
        ),
        (_RN, "Müəllim əlavə et"): ("Add teacher", "Добавить преподавателя", "Öğretmen ekle"),
        (_RN, "Müəllimi təyin edilməmiş (vakant) dərsləri də yerləşdir"): (
            "Also place classes without an assigned teacher (vacant)",
            "Размещать и занятия без назначенного преподавателя (вакансия)",
            "Öğretmeni atanmamış (boş kadro) dersleri de yerleştir",
        ),
        (_RN, "Müəllimin boş cütü (pəncərə)"): (
            "Teacher idle pair (gap)",
            "«Окно» преподавателя",
            "Öğretmen boş dersi (pencere)",
        ),
        (_RN, "Müəllimin gündəlik limiti aşması"): (
            "Teacher exceeds daily limit",
            "Превышение дневного лимита преподавателя",
            "Öğretmenin günlük sınırı aşması",
        ),
        (_RN, "Məlumat"): ("Info", "Информация", "Bilgi"),
        (_RN, "Məlumatı yoxla"): ("Check data", "Проверить данные", "Verileri kontrol et"),
        (_RN, "Mənbə işləmənin kilidli dərsləri yerində saxlanılacaq"): (
            "Locked classes of the source run will be kept in place",
            "Заблокированные занятия исходного запуска останутся на месте",
            "Kaynak çalıştırmanın kilitli dersleri yerinde kalacak",
        ),
        (_RN, "Növbəyə qoyulur…"): ("Queueing…", "Постановка в очередь…", "Kuyruğa alınıyor…"),
        (_RN, "Parametrlər"): ("Parameters", "Параметры", "Parametreler"),
        (_RN, "Prioritet sırası"): ("Priority order", "Порядок приоритета", "Öncelik sırası"),
        (_RN, "Qrup"): ("Groups", "Группы", "Grup"),
        (_RN, "Qrup adı ilə süz…"): ("Filter by group name…", "Фильтр по названию группы…", "Grup adına göre süz…"),
        (_RN, "Qrup üçün icazəli xana yoxdur (növbə siyasəti)."): (
            "The group has no allowed slots (shift policy).",
            "У группы нет разрешённых ячеек (политика смен).",
            "Grup için izinli saat yok (vardiya politikası).",
        ),
        (_RN, "Qrupları süz"): ("Filter groups", "Фильтр групп", "Grupları süz"),
        (_RN, "Qrupun bir dərs üçün gəldiyi gün"): (
            "A group comes for a single class",
            "Группа приходит на одну пару",
            "Grubun tek ders için geldiği gün",
        ),
        (_RN, "Qrupun gündəlik limiti aşması"): (
            "Group exceeds daily limit",
            "Превышение дневного лимита группы",
            "Grubun günlük sınırı aşması",
        ),
        (_RN, "Qrupun gününü boşluqsuz saxlamaq mümkün olmadı."): (
            "The group's day could not be kept gap-free.",
            "Не удалось сохранить день группы без «окон».",
            "Grubun günü boşluksuz tutulamadı.",
        ),
        (_RN, "Qrupun uyğun xanaları başqa dərslərlə doludur."): (
            "The group's suitable slots are taken by other classes.",
            "Подходящие ячейки группы заняты другими занятиями.",
            "Grubun uygun saatleri başka derslerle dolu.",
        ),
        (
            _RN,
            "Siyahı boşdur — bütün müəllimlər bərabər prioritetlidir. «Məlumatı yoxla»dan sonra müəllimləri əlavə edə bilərsiniz.",
        ): (
            "The list is empty — all teachers have equal priority. You can add teachers after «Check data».",
            "Список пуст — у всех преподавателей равный приоритет. Добавить преподавателей можно после «Проверить данные».",
            "Liste boş — tüm öğretmenler eşit önceliğe sahip. «Verileri kontrol et»ten sonra öğretmen ekleyebilirsiniz.",
        ),
        (
            _RN,
            "Siyahıdakı müəllimlər əvvəl yerləşdirilir və onların istəkləri daha güclü çəki alır (yuxarıdakı — ən vacib).",
        ): (
            "Teachers in the list are placed first and their wishes weigh more (top — most important).",
            "Преподаватели из списка размещаются первыми, их пожелания весят больше (сверху — самый важный).",
            "Listedeki öğretmenler önce yerleştirilir ve istekleri daha ağır basar (en üstteki — en önemli).",
        ),
        (_RN, "Siyahıdan çıxar"): ("Remove from list", "Убрать из списка", "Listeden çıkar"),
        (
            _RN,
            "Sərt qaydalar (toqquşma, qrupda boşluq, magistr — yalnız axşam, «gələ bilmir» saatı) çəki ilə dəyişmir — HƏMİŞƏ qorunur.",
        ): (
            "Hard rules (clashes, group gaps, master's — evening only, «unavailable» hours) are not weighted — they are ALWAYS enforced.",
            "Жёсткие правила (конфликты, «окна» групп, магистратура — только вечер, часы «недоступен») не зависят от весов — соблюдаются ВСЕГДА.",
            "Katı kurallar (çakışma, grupta boşluk, yüksek lisans — yalnızca akşam, «gelemez» saati) ağırlıkla değişmez — HER ZAMAN korunur.",
        ),
        (_RN, "Sərt qaydaları pozmadan yer tapılmadı."): (
            "No place was found without breaking hard rules.",
            "Не найдено места без нарушения жёстких правил.",
            "Katı kuralları ihlal etmeden yer bulunamadı.",
        ),
        (_RN, "Toxum (seed)"): ("Seed", "Зерно (seed)", "Tohum (seed)"),
        (
            _RN,
            "Tövsiyə: fakültə-fakültə qurun — başqa fakültənin dərc olunmuş dərsləri müəllim üçün sabit məşğulluq sayılır.",
        ): (
            "Tip: build faculty by faculty — another faculty's published classes count as fixed teacher occupancy.",
            "Совет: стройте по факультетам — опубликованные занятия другого факультета считаются фиксированной занятостью преподавателя.",
            "Öneri: fakülte fakülte oluşturun — başka fakültenin yayımlanmış dersleri öğretmen için sabit meşguliyet sayılır.",
        ),
        (_RN, "Tədris günləri"): ("Teaching days", "Учебные дни", "Öğretim günleri"),
        (_RN, "Uzun limit daha az «boş pəncərə» verir; 30–60 san. adətən kifayətdir."): (
            "A longer limit gives fewer idle gaps; 30–60 s is usually enough.",
            "Больший лимит даёт меньше «окон»; обычно достаточно 30–60 с.",
            "Daha uzun sınır daha az boş pencere verir; genellikle 30–60 sn yeterlidir.",
        ),
        (_RN, "Vaxt limiti (saniyə)"): ("Time limit (seconds)", "Лимит времени (секунды)", "Süre sınırı (saniye)"),
        (_RN, "Xəbərdarlıq"): ("Warning", "Предупреждение", "Uyarı"),
        (_RN, "Xəta"): ("Error", "Ошибка", "Hata"),
        (_RN, "Yeni işləmə"): ("New run", "Новый запуск", "Yeni çalıştırma"),
        (_RN, "Yoxlama nəticəsi"): ("Check result", "Результат проверки", "Kontrol sonucu"),
        (_RN, "Yoxlanılır…"): ("Checking…", "Проверка…", "Kontrol ediliyor…"),
        (_RN, "Yuxarı"): ("Up", "Вверх", "Yukarı"),
        (_RN, "boşluq yaranır"): ("creates a gap", "появляется «окно»", "boşluk oluşur"),
        (_RN, "digər"): ("other", "другое", "diğer"),
        (_RN, "müəllim məşğul"): ("teacher busy", "преподаватель занят", "öğretmen meşgul"),
        (_RN, "müəllimin kənar dərsi"): (
            "teacher's external class",
            "внешнее занятие преподавателя",
            "öğretmenin dış dersi",
        ),
        (_RN, "otaq yoxdur"): ("no room", "нет аудитории", "derslik yok"),
        (_RN, "qrup məşğul"): ("group busy", "группа занята", "grup meşgul"),
        (_RN, "«Dəyişdirilə bilən» saatın istifadəsi"): (
            "Use of a «flexible» hour",
            "Использование «гибкого» часа",
            "«Değiştirilebilir» saatin kullanımı",
        ),
        (_RN, "İxtisas"): ("Programme", "Специальность", "Bölüm"),
        (_RN, "İxtisas seçin"): ("Select a programme", "Выберите специальность", "Bölüm seçin"),
        (_RN, "İşləməni yaradan istifadəçi tapılmadı."): (
            "The user who created the run was not found.",
            "Пользователь, создавший запуск, не найден.",
            "Çalıştırmayı oluşturan kullanıcı bulunamadı.",
        ),
        (_RN, "İşlət"): ("Run", "Запустить", "Çalıştır"),
        (_RN, "Əhatə"): ("Scope", "Охват", "Kapsam"),
        (_RN, "Əhatə növü"): ("Scope type", "Тип охвата", "Kapsam türü"),
        (_RN, "Əhatə seçin (fakültə, ixtisas və ya ən azı bir qrup)."): (
            "Select a scope (faculty, programme or at least one group).",
            "Выберите охват (факультет, специальность или хотя бы одну группу).",
            "Bir kapsam seçin (fakülte, bölüm veya en az bir grup).",
        ),
        (_RN, "Əməliyyat yerinə yetirilmədi."): (
            "The action failed.",
            "Действие не выполнено.",
            "İşlem gerçekleştirilemedi.",
        ),
    }
)


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
