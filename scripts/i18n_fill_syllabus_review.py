#!/usr/bin/env python3
"""EMSArena i18n — «Sillabus təsdiqi» ekranının sətirləri (4 dil). İdempotent.

Kafedra müdirinin təsdiq növbəsi, baxış paneli (bölmələr / fərqlər / audit),
qərar dialoqları, əhatə analitikası və `noscope` boş vəziyyəti.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir və mövcud girişə TOXUNMUR.
⚠️ Yer tutucular (`%(name)s`) hər dildə EYNİ qalmalıdır — `check_i18n_catalogs`
uyğunsuzluğu runtime `KeyError` riski kimi bloklayır.

İstifadə:  python scripts/i18n_fill_syllabus_review.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

_SIDEBAR = {
    "Sillabus təsdiqi": {"en": "Syllabus approval", "ru": "Утверждение силлабуса", "tr": "Ders izlencesi onayı"},
}

_REVIEW = {
    # ── Başlıq, rol, əhatə ────────────────────────────────────────────────
    "Sillabus təsdiqi": {"en": "Syllabus approval", "ru": "Утверждение силлабуса", "tr": "Ders izlencesi onayı"},
    "Kafedra müdiri paneli": {
        "en": "Department head panel",
        "ru": "Панель заведующего кафедрой",
        "tr": "Bölüm başkanı paneli",
    },
    "Təsdiq paneli": {"en": "Approval panel", "ru": "Панель утверждения", "tr": "Onay paneli"},
    "Kafedra müdiri": {"en": "Department head", "ru": "Заведующий кафедрой", "tr": "Bölüm başkanı"},
    "Genişləndirilmiş əhatə": {"en": "Extended scope", "ru": "Расширенная зона", "tr": "Genişletilmiş kapsam"},
    "Əhatə yoxdur": {"en": "No scope", "ru": "Зона не задана", "tr": "Kapsam yok"},
    "Əhatə: %(count)s struktur bölmə": {
        "en": "Scope: %(count)s organizational units",
        "ru": "Зона: %(count)s структурных подразделений",
        "tr": "Kapsam: %(count)s yapısal birim",
    },
    "Yalnız öz kafedranızın müəllimlərinin təqdim etdiyi sillabuslar görünür. Təsdiqlənmiş versiya "
    "dəyişdirilmir — düzəliş yeni versiya ilə aparılır.": {
        "en": "Only syllabi submitted by teachers of your own department are shown. An approved version is never "
        "modified — corrections go through a new version.",
        "ru": "Показываются только силлабусы, поданные преподавателями вашей кафедры. Утверждённая версия не "
        "изменяется — правки вносятся новой версией.",
        "tr": "Yalnızca kendi bölümünüzün öğretim elemanlarının gönderdiği izlenceler görünür. Onaylanmış sürüm "
        "değiştirilmez — düzeltme yeni sürümle yapılır.",
    },
    "Əhatənizdəki bütün kafedralar üzrə sillabus vəziyyəti. Təsdiqlənmiş versiya dəyişdirilmir — düzəliş "
    "yeni versiya ilə aparılır.": {
        "en": "Syllabus status across every department in your scope. An approved version is never modified — "
        "corrections go through a new version.",
        "ru": "Состояние силлабусов по всем кафедрам вашей зоны. Утверждённая версия не изменяется — правки "
        "вносятся новой версией.",
        "tr": "Kapsamınızdaki tüm bölümler için izlence durumu. Onaylanmış sürüm değiştirilmez — düzeltme yeni "
        "sürümle yapılır.",
    },
    "Əhatə təyin edilməyib.": {"en": "No scope assigned.", "ru": "Зона не назначена.", "tr": "Kapsam atanmamış."},
    "Sillabus təsdiqi bölməsi üçün icazəniz yoxdur.": {
        "en": "You do not have permission for the syllabus approval section.",
        "ru": "У вас нет прав доступа к разделу утверждения силлабусов.",
        "tr": "Ders izlencesi onayı bölümü için yetkiniz yok.",
    },
    # ── noscope boş vəziyyəti ─────────────────────────────────────────────
    "Təşkilati əhatə təyin edilməmişdir": {
        "en": "No organizational scope has been assigned",
        "ru": "Организационная зона не назначена",
        "tr": "Kurumsal kapsam atanmamış",
    },
    "Hesabınıza kafedra və ya fakültə əhatəsi verilməyib. Əhatə olmadan sillabus məlumatları göstərilmir — "
    "bu, «bütün universitet» kimi şərh edilmir. Səlahiyyət təyin edildikdən sonra yalnız aid olduğunuz "
    "struktur bölmə görünəcək.": {
        "en": "Your account has no department or faculty scope. Without a scope, syllabus data is not shown — this "
        "is never read as «the whole university». Once the scope is assigned, only your own unit will appear.",
        "ru": "Вашей учётной записи не назначена кафедра или факультет. Без зоны данные силлабусов не "
        "показываются — это не трактуется как «весь университет». После назначения появится только ваше "
        "подразделение.",
        "tr": "Hesabınıza bölüm veya fakülte kapsamı verilmemiş. Kapsam olmadan izlence verileri gösterilmez — bu "
        "«tüm üniversite» olarak yorumlanmaz. Yetki atandıktan sonra yalnızca kendi biriminiz görünecek.",
    },
    "Əhatənin təyini üçün təşkilat administratoruna və ya tədris şöbəsinə müraciət edin.": {
        "en": "Contact the organization administrator or the academic affairs office to have your scope assigned.",
        "ru": "Обратитесь к администратору организации или в учебный отдел для назначения зоны.",
        "tr": "Kapsamın atanması için kurum yöneticisine veya öğrenci işlerine başvurun.",
    },
    # ── Tab və KPI ────────────────────────────────────────────────────────
    "Təsdiq növbəsi": {"en": "Approval queue", "ru": "Очередь на утверждение", "tr": "Onay kuyruğu"},
    "Əhatə və analitika": {"en": "Coverage and analytics", "ru": "Охват и аналитика", "tr": "Kapsam ve analitik"},
    "Növbədə gözləyən": {"en": "Waiting in the queue", "ru": "Ожидают в очереди", "tr": "Kuyrukta bekleyen"},
    "baxış tələb edən sillabus": {
        "en": "syllabi awaiting review",
        "ru": "силлабусов ожидают рассмотрения",
        "tr": "inceleme bekleyen izlence",
    },
    "10 gündən çox gözləyir": {
        "en": "Waiting more than 10 days",
        "ru": "Ожидают более 10 дней",
        "tr": "10 günden fazla bekliyor",
    },
    "gözləmə həddi aşılıb": {
        "en": "waiting limit exceeded",
        "ru": "превышен предел ожидания",
        "tr": "bekleme sınırı aşıldı",
    },
    "Çatışmayan bölməsi var": {
        "en": "Has an incomplete section",
        "ru": "Есть незаполненный раздел",
        "tr": "Eksik bölümü var",
    },
    "tam doldurulmayıb": {"en": "not fully filled in", "ru": "заполнено не полностью", "tr": "tam doldurulmamış"},
    "Orta gözləmə": {"en": "Average wait", "ru": "Среднее ожидание", "tr": "Ortalama bekleme"},
    "hədəf: 5 gündən az": {"en": "target: under 5 days", "ru": "цель: менее 5 дней", "tr": "hedef: 5 günden az"},
    "gün": {"en": "days", "ru": "дн.", "tr": "gün sayısı"},
    # ── Filtr paneli ──────────────────────────────────────────────────────
    "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama"},
    "Fənn, kod və ya müəllim": {
        "en": "Course, code or teacher",
        "ru": "Дисциплина, код или преподаватель",
        "tr": "Ders, kod veya öğretim elemanı",
    },
    "Status": {"en": "State", "ru": "Статус", "tr": "Durum"},
    "Sıralama": {"en": "Sorting", "ru": "Сортировка", "tr": "Sıralama ölçütü"},
    "Akademik il": {"en": "Academic year", "ru": "Учебный год", "tr": "Akademik yıl"},
    "Filtrləri sıfırla": {"en": "Reset filters", "ru": "Сбросить фильтры", "tr": "Filtreleri sıfırla"},
    "Bütün statuslar": {"en": "All statuses", "ru": "Все статусы", "tr": "Tüm durumlar"},
    "Bütün illər": {"en": "All years", "ru": "Все годы", "tr": "Tüm yıllar"},
    "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
    "Gözləmə müddətinə görə": {"en": "By waiting time", "ru": "По времени ожидания", "tr": "Bekleme süresine göre"},
    "Fənn adına görə": {"en": "By course name", "ru": "По названию дисциплины", "tr": "Ders adına göre"},
    "Tamamlanmaya görə": {"en": "By completion", "ru": "По заполненности", "tr": "Tamamlanmaya göre"},
    "Təhsil proqramı": {"en": "Study programme", "ru": "Образовательная программа", "tr": "Eğitim programı"},
    "Kafedra": {"en": "Department", "ru": "Кафедра", "tr": "Bölüm"},
    "Görünüş": {"en": "View", "ru": "Вид", "tr": "Görünüm"},
    # ── Növbə cədvəli ─────────────────────────────────────────────────────
    "Fənn və proqram": {
        "en": "Course and programme",
        "ru": "Дисциплина и программа",
        "tr": "Ders ve program",
    },
    "Müəllim": {"en": "Teacher", "ru": "Преподаватель", "tr": "Öğretim elemanı"},
    "Təqdim / gözləmə": {"en": "Submitted / waiting", "ru": "Подано / ожидание", "tr": "Gönderim / bekleme"},
    "Tamamlanma": {"en": "Completion", "ru": "Заполненность", "tr": "Tamamlanma oranı"},
    "Risk": {"en": "Risks", "ru": "Риски", "tr": "Riskler"},
    "Əməllər": {"en": "Actions", "ru": "Действия", "tr": "İşlemler"},
    "Baxışa keç": {"en": "Open review", "ru": "Перейти к рассмотрению", "tr": "İncelemeye geç"},
    "Təsdiq növbəsi boşdur": {
        "en": "The approval queue is empty",
        "ru": "Очередь на утверждение пуста",
        "tr": "Onay kuyruğu boş",
    },
    "Seçilmiş filtrə uyğun gözləyən sillabus yoxdur. Ümumi vəziyyəti «Əhatə və analitika» tabından izləyə "
    "bilərsiniz.": {
        "en": "No pending syllabus matches the selected filter. Track the overall picture on the «Coverage and "
        "analytics» tab.",
        "ru": "Нет ожидающих силлабусов по выбранному фильтру. Общую картину можно посмотреть на вкладке «Охват и "
        "аналитика».",
        "tr": "Seçilen filtreye uyan bekleyen izlence yok. Genel durumu «Kapsam ve analitik» sekmesinden "
        "izleyebilirsiniz.",
    },
    "Əhatəyə keç": {"en": "Go to coverage", "ru": "Перейти к охвату", "tr": "Kapsama geç"},
    # ── Risk çipləri və gözləmə ───────────────────────────────────────────
    "bugün gəlib": {"en": "arrived today", "ru": "поступило сегодня", "tr": "bugün geldi"},
    "%(days)s gündür gözləyir": {
        "en": "waiting for %(days)s days",
        "ru": "ожидает %(days)s дн.",
        "tr": "%(days)s gündür bekliyor",
    },
    "%(version)s aktivdir": {
        "en": "%(version)s is active",
        "ru": "%(version)s активна",
        "tr": "%(version)s etkin",
    },
    "çatışmayan bölmə var": {
        "en": "has an incomplete section",
        "ru": "есть незаполненный раздел",
        "tr": "eksik bölüm var",
    },
    "siyasət yoxlaması": {"en": "policy check", "ru": "проверка политики", "tr": "politika kontrolü"},
    "böyük dəyişiklik": {"en": "major change", "ru": "крупное изменение", "tr": "büyük değişiklik"},
    "risk yoxdur": {"en": "no risk", "ru": "рисков нет", "tr": "risk yok"},
    "Müəllif göstərilməyib": {"en": "No author specified", "ru": "Автор не указан", "tr": "Yazar belirtilmemiş"},
    "Proqram təyin edilməyib": {
        "en": "No programme assigned",
        "ru": "Программа не назначена",
        "tr": "Program atanmamış",
    },
    "Kafedra təyin edilməyib": {"en": "No department assigned", "ru": "Кафедра не назначена", "tr": "Bölüm atanmamış"},
    # ── Əhatə analitikası ─────────────────────────────────────────────────
    "Təsdiq faizi": {"en": "Approval rate", "ru": "Доля утверждённых", "tr": "Onay oranı"},
    "təsdiqlənmiş / ümumi fənn": {
        "en": "approved / total courses",
        "ru": "утверждено / всего дисциплин",
        "tr": "onaylanan / toplam ders",
    },
    "Təsdiqlənmiş": {"en": "Approved", "ru": "Утверждено", "tr": "Onaylanan"},
    "jurnal açıla bilər": {"en": "the journal can be opened", "ru": "журнал можно открыть", "tr": "yoklama açılabilir"},
    "Baxışda": {"en": "Under review", "ru": "На рассмотрении", "tr": "İncelemede"},
    "təsdiq gözləyir": {"en": "awaiting approval", "ru": "ожидает утверждения", "tr": "onay bekliyor"},
    "Düzəlişdə": {"en": "In revision", "ru": "На доработке", "tr": "Düzeltmede"},
    "müəllimdədir": {"en": "with the teacher", "ru": "у преподавателя", "tr": "öğretim elemanında"},
    "Gecikib": {"en": "Overdue", "ru": "Просрочено", "tr": "Gecikmiş"},
    "semestr başlayıb, təsdiq yoxdur": {
        "en": "the semester has started, no approval yet",
        "ru": "семестр начался, утверждения нет",
        "tr": "dönem başladı, onay yok",
    },
    "Kafedra üzrə breakdown — təhsil proqramları": {
        "en": "Department breakdown — study programmes",
        "ru": "Разрез по кафедре — образовательные программы",
        "tr": "Bölüm kırılımı — eğitim programları",
    },
    "Əhatə üzrə breakdown — kafedralar": {
        "en": "Scope breakdown — departments",
        "ru": "Разрез по зоне — кафедры",
        "tr": "Kapsam kırılımı — bölümler",
    },
    "Yalnız sizin əhatənizdəki fənlər": {
        "en": "Only the courses within your scope",
        "ru": "Только дисциплины вашей зоны",
        "tr": "Yalnızca kapsamınızdaki dersler",
    },
    "Əhatənizə düşən bütün struktur bölmələr": {
        "en": "Every organizational unit in your scope",
        "ru": "Все структурные подразделения вашей зоны",
        "tr": "Kapsamınıza giren tüm yapısal birimler",
    },
    "Fənn": {"en": "Courses", "ru": "Дисциплины", "tr": "Dersler"},
    "Cəmi": {"en": "Total", "ru": "Итого", "tr": "Toplam"},
    "Təyin edilməyib": {"en": "Not assigned", "ru": "Не назначено", "tr": "Atanmamış"},
    "Seçilmiş tədris ilində qeyd tapılmadı.": {
        "en": "No records found for the selected academic year.",
        "ru": "За выбранный учебный год записей не найдено.",
        "tr": "Seçilen akademik yıl için kayıt bulunamadı.",
    },
    "Semestr üzrə dinamika": {"en": "Trend by semester", "ru": "Динамика по семестрам", "tr": "Döneme göre eğilim"},
    "Müqayisə üçün kifayət qədər semestr qeydi yoxdur.": {
        "en": "There are not enough semester records to compare.",
        "ru": "Недостаточно записей по семестрам для сравнения.",
        "tr": "Karşılaştırma için yeterli dönem kaydı yok.",
    },
    # ── Təsdiq marşrutu ───────────────────────────────────────────────────
    "Təsdiq marşrutu — universitet siyasəti": {
        "en": "Approval route — university policy",
        "ru": "Маршрут утверждения — политика университета",
        "tr": "Onay rotası — üniversite politikası",
    },
    "Kafedra təsdiqi state maşını ilə məcburidir. Sonrakı mərhələlər (dekan təsdiqi, tədris şöbəsinin yekun "
    "yoxlaması) hələ tətbiq olunmayıb — burada onların cari vəziyyəti göstərilir.": {
        "en": "Department approval is enforced by the state machine. The later stages (dean approval, final check "
        "by academic affairs) are not implemented yet — their current status is shown here.",
        "ru": "Утверждение кафедрой обязательно и обеспечивается конечным автоматом. Следующие этапы (утверждение "
        "деканом, финальная проверка учебного отдела) ещё не реализованы — здесь показан их текущий статус.",
        "tr": "Bölüm onayı durum makinesi ile zorunludur. Sonraki aşamalar (dekan onayı, öğrenci işlerinin son "
        "kontrolü) henüz uygulanmadı — burada mevcut durumları gösterilir.",
    },
    "Kafedra müdiri təsdiqi": {
        "en": "Department head approval",
        "ru": "Утверждение заведующим кафедрой",
        "tr": "Bölüm başkanı onayı",
    },
    "Bütün sillabuslar üçün məcburidir — state maşını ilə tətbiq olunur.": {
        "en": "Mandatory for every syllabus — enforced by the state machine.",
        "ru": "Обязательно для всех силлабусов — обеспечивается конечным автоматом.",
        "tr": "Tüm izlenceler için zorunlu — durum makinesi ile uygulanır.",
    },
    "İkinci təsdiq — dekan": {
        "en": "Second approval — dean",
        "ru": "Второе утверждение — декан",
        "tr": "İkinci onay — dekan",
    },
    "Universitet siyasətindən asılı ikinci mərhələ — hələ tətbiq olunmayıb.": {
        "en": "A second stage that depends on university policy — not implemented yet.",
        "ru": "Второй этап, зависящий от политики университета, — пока не реализован.",
        "tr": "Üniversite politikasına bağlı ikinci aşama — henüz uygulanmadı.",
    },
    "Tədris şöbəsinin son yoxlaması": {
        "en": "Final check by academic affairs",
        "ru": "Финальная проверка учебного отдела",
        "tr": "Öğrenci işlerinin son kontrolü",
    },
    "Semestr açılışından əvvəl toplu yoxlama — hələ tətbiq olunmayıb.": {
        "en": "A bulk check before the semester opens — not implemented yet.",
        "ru": "Массовая проверка перед открытием семестра — пока не реализована.",
        "tr": "Dönem açılışından önce toplu kontrol — henüz uygulanmadı.",
    },
    "aktiv": {"en": "active", "ru": "активно", "tr": "etkin"},
    "tətbiq olunmur": {"en": "not in effect", "ru": "не применяется", "tr": "uygulanmıyor"},
}

_PANEL = {
    # ── Baxış paneli ──────────────────────────────────────────────────────
    "Baxış bölmələri": {"en": "Review tabs", "ru": "Разделы рассмотрения", "tr": "İnceleme bölümleri"},
    "Baxışı bağla": {"en": "Close the review", "ru": "Закрыть рассмотрение", "tr": "İncelemeyi kapat"},
    "Sillabus bölmələri": {"en": "Syllabus sections", "ru": "Разделы силлабуса", "tr": "İzlence bölümleri"},
    "Dəyişikliklər": {"en": "Changes", "ru": "Изменения", "tr": "Değişiklikler"},
    "Audit tarixçəsi": {"en": "Audit history", "ru": "История аудита", "tr": "Denetim geçmişi"},
    "Müəllimin qeydi:": {"en": "Teacher's note:", "ru": "Заметка преподавателя:", "tr": "Öğretim elemanının notu:"},
    "Müəllim təqdimata əlavə qeyd yazmayıb.": {
        "en": "The teacher added no note to the submission.",
        "ru": "Преподаватель не добавил заметку к подаче.",
        "tr": "Öğretim elemanı gönderime not eklemedi.",
    },
    "Müəllim: %(value)s": {
        "en": "Teacher: %(value)s",
        "ru": "Преподаватель: %(value)s",
        "tr": "Öğretim elemanı: %(value)s",
    },
    "Məsləhət saatı: %(value)s": {
        "en": "Office hours: %(value)s",
        "ru": "Часы консультаций: %(value)s",
        "tr": "Danışma saati: %(value)s",
    },
    "Prerekvizit: %(value)s": {
        "en": "Prerequisite: %(value)s",
        "ru": "Пререквизит: %(value)s",
        "tr": "Ön koşul: %(value)s",
    },
    "— doldurulmayıb —": {"en": "— not filled in —", "ru": "— не заполнено —", "tr": "— doldurulmamış —"},
    "Təqdim: %(sent)s · tamamlanma %(percent)s%%": {
        "en": "Submitted: %(sent)s · completion %(percent)s%%",
        "ru": "Подано: %(sent)s · заполненность %(percent)s%%",
        "tr": "Gönderim: %(sent)s · tamamlanma %(percent)s%%",
    },
    "Ümumi rəy": {"en": "Overall feedback", "ru": "Общий отзыв", "tr": "Genel görüş"},
    "Təsdiq və ya geri qaytarma ilə birlikdə müəllimə göndərilir": {
        "en": "Sent to the teacher together with the approval or the return",
        "ru": "Отправляется преподавателю вместе с утверждением или возвратом",
        "tr": "Onay veya iade ile birlikte öğretim elemanına gönderilir",
    },
    "Bölmə üzrə şərh": {"en": "Section comment", "ru": "Комментарий к разделу", "tr": "Bölüm yorumu"},
    "Müəllimə göndəriləcək konkret qeyd": {
        "en": "A specific note to be sent to the teacher",
        "ru": "Конкретная заметка для преподавателя",
        "tr": "Öğretim elemanına gönderilecek somut not",
    },
    "Şərh əlavə et": {"en": "Add a comment", "ru": "Добавить комментарий", "tr": "Yorum ekle"},
    "Şərhi gizlət": {"en": "Hide the comment", "ru": "Скрыть комментарий", "tr": "Yorumu gizle"},
    "şərh var": {"en": "has a comment", "ru": "есть комментарий", "tr": "yorum var"},
    "dəyişib": {"en": "changed", "ru": "изменено", "tr": "değişti"},
    "Şərh yazılmış bölmə: %(count)s · geri qaytarma və rədd üçün səbəb məcburidir": {
        "en": "Sections with a comment: %(count)s · a reason is mandatory for returning and rejecting",
        "ru": "Разделов с комментарием: %(count)s · для возврата и отклонения причина обязательна",
        "tr": "Yorum yazılan bölüm: %(count)s · iade ve ret için gerekçe zorunludur",
    },
    # ── Fərqlər ───────────────────────────────────────────────────────────
    "Müqayisə: təsdiqlənmiş %(old)s ilə təqdim edilmiş %(new)s arasında.": {
        "en": "Comparison: approved %(old)s versus submitted %(new)s.",
        "ru": "Сравнение: утверждённая %(old)s и поданная %(new)s.",
        "tr": "Karşılaştırma: onaylı %(old)s ile gönderilen %(new)s arasında.",
    },
    "Bu, dosyenin ilk təsdiq namizədidir — müqayisə üçün əvvəlki versiya yoxdur.": {
        "en": "This is the file's first approval candidate — there is no earlier version to compare with.",
        "ru": "Это первый кандидат на утверждение в деле — сравнивать не с чем.",
        "tr": "Bu, dosyanın ilk onay adayıdır — karşılaştırılacak önceki sürüm yok.",
    },
    "Bu versiya üçün müqayisə oluna bilən əvvəlki təsdiq yoxdur.": {
        "en": "There is no previous approval to compare this version with.",
        "ru": "Нет предыдущего утверждения для сравнения с этой версией.",
        "tr": "Bu sürümle karşılaştırılacak önceki bir onay yok.",
    },
    "%(changed)s bölmə dəyişib · %(same)s bölmə dəyişməyib": {
        "en": "%(changed)s sections changed · %(same)s unchanged",
        "ru": "Изменено разделов: %(changed)s · без изменений: %(same)s",
        "tr": "%(changed)s bölüm değişti · %(same)s bölüm değişmedi",
    },
    "struktur dəyişikliyi": {"en": "structural change", "ru": "структурное изменение", "tr": "yapısal değişiklik"},
    "məzmun dəyişikliyi": {"en": "content change", "ru": "изменение содержания", "tr": "içerik değişikliği"},
    "dəyişməmişdir": {"en": "unchanged", "ru": "без изменений", "tr": "değişmedi"},
    "təsdiqlənmiş versiya": {"en": "approved version", "ru": "утверждённая версия", "tr": "onaylı sürüm"},
    "təqdim edilmiş versiya": {"en": "submitted version", "ru": "поданная версия", "tr": "gönderilen sürüm"},
    "Bu, jurnalın mövzu siyahısını dəyişir. Cari semestrdə jurnal artıq açılıbsa, dəyişiklik yalnız "
    "növbəti semestrdən qüvvəyə minir.": {
        "en": "This changes the journal's topic list. If the journal is already open this semester, the change "
        "takes effect only from the next semester.",
        "ru": "Это меняет список тем журнала. Если журнал текущего семестра уже открыт, изменение вступит в силу "
        "только со следующего семестра.",
        "tr": "Bu, yoklama defterinin konu listesini değiştirir. Bu dönem defter açıldıysa değişiklik yalnızca "
        "gelecek dönemden geçerli olur.",
    },
    "Qiymətləndirmə çəkiləri jurnalın sütun strukturunu dəyişir. Mövcud qiymətlər arxivdə saxlanılır və "
    "silinmir.": {
        "en": "Assessment weights change the journal's column structure. Existing grades are archived, never "
        "deleted.",
        "ru": "Веса оценивания меняют структуру столбцов журнала. Существующие оценки сохраняются в архиве и не "
        "удаляются.",
        "tr": "Değerlendirme ağırlıkları defterin sütun yapısını değiştirir. Mevcut notlar arşivde saklanır, "
        "silinmez.",
    },
    "Sərbəst iş sütunlarının sayı dəyişir. Köhnə sütunların qiymətləri arxivdə saxlanılır və silinmir.": {
        "en": "The number of self-study columns changes. Grades in the old columns are archived, never deleted.",
        "ru": "Меняется число столбцов самостоятельной работы. Оценки старых столбцов сохраняются в архиве и не "
        "удаляются.",
        "tr": "Bağımsız çalışma sütunlarının sayısı değişir. Eski sütunların notları arşivde saklanır, silinmez.",
    },
    # ── Audit xronologiyası ───────────────────────────────────────────────
    "%(version)s versiyası yaradıldı": {
        "en": "Version %(version)s was created",
        "ru": "Создана версия %(version)s",
        "tr": "%(version)s sürümü oluşturuldu",
    },
    "%(version)s təsdiqə göndərildi": {
        "en": "%(version)s was submitted for approval",
        "ru": "%(version)s подана на утверждение",
        "tr": "%(version)s onaya gönderildi",
    },
    "%(version)s təqdimatı geri çağırıldı": {
        "en": "The submission of %(version)s was withdrawn",
        "ru": "Подача %(version)s отозвана",
        "tr": "%(version)s gönderimi geri çekildi",
    },
    "%(version)s baxışa götürüldü": {
        "en": "%(version)s was taken into review",
        "ru": "%(version)s взята на рассмотрение",
        "tr": "%(version)s incelemeye alındı",
    },
    "%(version)s təsdiqləndi": {
        "en": "%(version)s was approved",
        "ru": "%(version)s утверждена",
        "tr": "%(version)s onaylandı",
    },
    "%(version)s düzəliş üçün geri qaytarıldı": {
        "en": "%(version)s was returned for revision",
        "ru": "%(version)s возвращена на доработку",
        "tr": "%(version)s düzeltme için iade edildi",
    },
    "%(version)s rədd edildi": {
        "en": "%(version)s was rejected",
        "ru": "%(version)s отклонена",
        "tr": "%(version)s reddedildi",
    },
    "%(version)s yeniləndi": {
        "en": "%(version)s was updated",
        "ru": "%(version)s обновлена",
        "tr": "%(version)s güncellendi",
    },
}

_DIALOGS = {
    "Sillabus təsdiqlənsin?": {
        "en": "Approve the syllabus?",
        "ru": "Утвердить силлабус?",
        "tr": "İzlence onaylansın mı?",
    },
    "Versiya təsdiqlənəcək və dəyişdirilməz sənəd kimi kilidlənəcək. Sonrakı düzəliş yalnız yeni "
    "versiya ilə mümkündür.": {
        "en": "The version will be approved and locked as an immutable document. Any later correction is possible "
        "only through a new version.",
        "ru": "Версия будет утверждена и заблокирована как неизменяемый документ. Дальнейшие правки возможны "
        "только новой версией.",
        "tr": "Sürüm onaylanacak ve değiştirilemez belge olarak kilitlenecek. Sonraki düzeltme yalnızca yeni "
        "sürümle mümkündür.",
    },
    "Təsdiqlə": {"en": "Approve", "ru": "Утвердить", "tr": "Onayla"},
    "Təsdiqlənmiş versiya həftəlik mövzuların, qiymətləndirmə strukturunun və sərbəst iş "
    "konfiqurasiyasının yeganə mənbəyi olur": {
        "en": "The approved version becomes the single source for weekly topics, the assessment structure and the "
        "self-study configuration",
        "ru": "Утверждённая версия становится единственным источником еженедельных тем, структуры оценивания и "
        "конфигурации самостоятельной работы",
        "tr": "Onaylanan sürüm, haftalık konuların, değerlendirme yapısının ve bağımsız çalışma yapılandırmasının "
        "tek kaynağı olur",
    },
    "Elektron jurnal bu versiyadan yaradılır və müəllim üçün açılır": {
        "en": "The electronic journal is created from this version and opened for the teacher",
        "ru": "Электронный журнал создаётся из этой версии и открывается преподавателю",
        "tr": "Elektronik yoklama defteri bu sürümden oluşturulur ve öğretim elemanına açılır",
    },
    "Tələbə kabinetində sillabus dərhal görünür": {
        "en": "The syllabus appears in the student cabinet immediately",
        "ru": "Силлабус сразу появляется в кабинете студента",
        "tr": "İzlence öğrenci kabininde hemen görünür",
    },
    "Mövcud qiymət və davamiyyət qeydləri toxunulmaz qalır": {
        "en": "Existing grade and attendance records remain untouched",
        "ru": "Существующие оценки и записи посещаемости остаются нетронутыми",
        "tr": "Mevcut not ve devam kayıtları dokunulmaz kalır",
    },
    "Düzəliş üçün geri qaytarılsın?": {
        "en": "Return for revision?",
        "ru": "Вернуть на доработку?",
        "tr": "Düzeltme için iade edilsin mi?",
    },
    "Sillabus müəllimə qaytarılır və «Düzəliş tələb olunur» statusuna keçir. Səbəb məcburidir — müəllim "
    "onu birbaşa redaktorda görəcək.": {
        "en": "The syllabus goes back to the teacher and moves to the «Revision required» status. A reason is "
        "mandatory — the teacher will see it directly in the editor.",
        "ru": "Силлабус возвращается преподавателю и переходит в статус «Требуется доработка». Причина "
        "обязательна — преподаватель увидит её прямо в редакторе.",
        "tr": "İzlence öğretim elemanına iade edilir ve «Düzeltme gerekli» durumuna geçer. Gerekçe zorunludur — "
        "öğretim elemanı bunu doğrudan düzenleyicide görecek.",
    },
    "Geri qaytar": {"en": "Return", "ru": "Вернуть", "tr": "İade et"},
    "Düzəliş səbəbi": {"en": "Reason for revision", "ru": "Причина доработки", "tr": "Düzeltme gerekçesi"},
    "Konkret yazın: hansı bölmədə nə düzəldilməlidir.": {
        "en": "Be specific: which section needs what correction.",
        "ru": "Пишите конкретно: в каком разделе что исправить.",
        "tr": "Somut yazın: hangi bölümde ne düzeltilmeli.",
    },
    "Düzəliş tələb olunan bölmələr": {
        "en": "Sections that need revision",
        "ru": "Разделы, требующие доработки",
        "tr": "Düzeltme gereken bölümler",
    },
    "Düzəliş üçün geri qaytar": {
        "en": "Return for revision",
        "ru": "Вернуть на доработку",
        "tr": "Düzeltme için iade et",
    },
    "Sillabus rədd edilsin?": {
        "en": "Reject the syllabus?",
        "ru": "Отклонить силлабус?",
        "tr": "İzlence reddedilsin mi?",
    },
    "Rədd edilən versiya bağlanır və yenidən göndərilə bilmir — müəllim yeni versiya yaratmalıdır. "
    "Səbəb məcburidir və audit izinə yazılır.": {
        "en": "A rejected version is closed and cannot be resubmitted — the teacher has to create a new version. "
        "A reason is mandatory and is written into the audit trail.",
        "ru": "Отклонённая версия закрывается и не может быть подана повторно — преподаватель должен создать "
        "новую. Причина обязательна и записывается в аудит.",
        "tr": "Reddedilen sürüm kapanır ve yeniden gönderilemez — öğretim elemanı yeni sürüm oluşturmalıdır. "
        "Gerekçe zorunludur ve denetim izine yazılır.",
    },
    "Rədd et": {"en": "Reject", "ru": "Отклонить", "tr": "Reddet"},
    "Rədd səbəbi": {"en": "Reason for rejection", "ru": "Причина отклонения", "tr": "Ret gerekçesi"},
    "Məsələn: qiymətləndirmə strukturu universitet siyasətinə uyğun deyil.": {
        "en": "For example: the assessment structure does not comply with university policy.",
        "ru": "Например: структура оценивания не соответствует политике университета.",
        "tr": "Örneğin: değerlendirme yapısı üniversite politikasına uygun değil.",
    },
    "Mövcud təsdiqlənmiş versiya (varsa) aktiv qalır": {
        "en": "The existing approved version (if any) stays active",
        "ru": "Существующая утверждённая версия (если есть) остаётся активной",
        "tr": "Mevcut onaylı sürüm (varsa) etkin kalır",
    },
    "Tələbələr köhnə təsdiqlənmiş versiyanı görməyə davam edir": {
        "en": "Students keep seeing the previously approved version",
        "ru": "Студенты продолжают видеть ранее утверждённую версию",
        "tr": "Öğrenciler önceki onaylı sürümü görmeye devam eder",
    },
    "Jurnal statusu dəyişmir": {
        "en": "The journal status does not change",
        "ru": "Статус журнала не меняется",
        "tr": "Yoklama defteri durumu değişmez",
    },
    "Ləğv et": {"en": "Cancel", "ru": "Отмена", "tr": "İptal"},
    "Səbəb müəllimə göndərilir və audit izinə yazılır": {
        "en": "The reason is sent to the teacher and written into the audit trail",
        "ru": "Причина отправляется преподавателю и записывается в аудит",
        "tr": "Gerekçe öğretim elemanına gönderilir ve denetim izine yazılır",
    },
    "Ən azı %(min)s simvol — səbəb məcburidir": {
        "en": "At least %(min)s characters — a reason is mandatory",
        "ru": "Не менее %(min)s символов — причина обязательна",
        "tr": "En az %(min)s karakter — gerekçe zorunludur",
    },
    "Səbəb ən azı %(min)s simvol olmalıdır.": {
        "en": "The reason must be at least %(min)s characters long.",
        "ru": "Причина должна содержать не менее %(min)s символов.",
        "tr": "Gerekçe en az %(min)s karakter olmalıdır.",
    },
    # ── API cavabları ─────────────────────────────────────────────────────
    "Aktiv təşkilat seçilməyib.": {
        "en": "No active organization is selected.",
        "ru": "Активная организация не выбрана.",
        "tr": "Etkin kurum seçilmemiş.",
    },
    "Sillabus versiyası tapılmadı və ya əhatənizdə deyil.": {
        "en": "The syllabus version was not found or is outside your scope.",
        "ru": "Версия силлабуса не найдена или вне вашей зоны.",
        "tr": "İzlence sürümü bulunamadı veya kapsamınızda değil.",
    },
    "Sorğu düzgün deyil.": {
        "en": "The request is not valid.",
        "ru": "Некорректный запрос.",
        "tr": "İstek geçerli değil.",
    },
    "Əməliyyat yerinə yetirilmədi.": {
        "en": "The operation was not completed.",
        "ru": "Операция не выполнена.",
        "tr": "İşlem gerçekleştirilemedi.",
    },
    "Yüklənir…": {"en": "Loading…", "ru": "Загрузка…", "tr": "Yükleniyor…"},
    "%(name)s — %(version)s təsdiqləndi və kilidləndi.": {
        "en": "%(name)s — %(version)s was approved and locked.",
        "ru": "%(name)s — %(version)s утверждена и заблокирована.",
        "tr": "%(name)s — %(version)s onaylandı ve kilitlendi.",
    },
    "%(name)s — düzəliş üçün geri qaytarıldı, müəllimə bildiriş göndərildi.": {
        "en": "%(name)s — returned for revision, the teacher has been notified.",
        "ru": "%(name)s — возвращён на доработку, преподаватель уведомлён.",
        "tr": "%(name)s — düzeltme için iade edildi, öğretim elemanı bilgilendirildi.",
    },
    "%(name)s — versiya rədd edildi. Tələbələr köhnə təsdiqlənmiş versiyanı görür.": {
        "en": "%(name)s — the version was rejected. Students see the previously approved version.",
        "ru": "%(name)s — версия отклонена. Студенты видят ранее утверждённую версию.",
        "tr": "%(name)s — sürüm reddedildi. Öğrenciler önceki onaylı sürümü görüyor.",
    },
}

ENTRIES = {
    "profile.sidebar": _SIDEBAR,
    "accounts.syllabus": {**_REVIEW, **_PANEL, **_DIALOGS},
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
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
