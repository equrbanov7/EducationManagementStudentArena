#!/usr/bin/env python3
"""EMSArena i18n — «Qruplar» tələbə çekmecəsi, «Semestr açılışı» izahı,
qrup-yaratma təsdiqi və alt-qrup sənədi sətirləri (4 dil). İdempotent.

2026-09-07 sahib rəyi ilə gələn mətnlər:
* qrup sətrindəki «Tələbələr» çekmecəsi + «qrupdan çıxar / dondur / uzaqlaşdır»
  dialoqları (`accounts.groups`);
* semestr açılışının «Necə işləyir» kartı və bloklayıcı lenti (`accounts.semester`);
* imtahan kohortu modalında ixtisas süzgəci və yaratma təsdiqi
  (`profile.checkbox_select`, `profile.groups`);
* alt qrupdan əlavədə MƏCBURİ sənəd (`registrar.guest_roster`) + model meta.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir. Yer tutucular (`%d`, `%(n)s`) tərcümədə də EYNİ qalmalıdır
(`scripts/check_i18n_catalogs.py` bunu yoxlayır).

İstifadə:  python scripts/i18n_fill_groups_students_2026_09.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

_GROUPS = {
    # Şablon `{% trans %}`-də `%` kataloqda `%%` kimi yazılır (Django escaping).
    "%%d tələbə": {"en": "%%d students", "ru": "студентов: %%d", "tr": "%%d öğrenci"},
    "Ad və ya istifadəçi adı üzrə axtar": {
        "en": "Search by name or username",
        "ru": "Поиск по имени или логину",
        "tr": "Ad veya kullanıcı adına göre ara",
    },
    "Akademik məzuniyyət": {"en": "Academic leave", "ru": "Академический отпуск", "tr": "Akademik izin"},
    "Aktiv qeydiyyatlı tələbələr. Hər əməl səbəb və təsdiq tələb edir; tarixçə silinmir.": {
        "en": "Active enrolled students. Every action requires a reason and confirmation; history is never deleted.",
        "ru": "Активные зачисленные студенты. Каждое действие требует причины и подтверждения; история не удаляется.",
        "tr": "Aktif kayıtlı öğrenciler. Her işlem gerekçe ve onay ister; geçmiş silinmez.",
    },
    "Axtarışa uyğun tələbə tapılmadı.": {
        "en": "No student matches the search.",
        "ru": "По запросу студенты не найдены.",
        "tr": "Aramaya uyan öğrenci bulunamadı.",
    },
    "Bu qrupda aktiv tələbə yoxdur.": {
        "en": "This group has no active students.",
        "ru": "В этой группе нет активных студентов.",
        "tr": "Bu grupta aktif öğrenci yok.",
    },
    "Bu tarixə qədər tələbənin statusu «akademik məzuniyyət» olur; bərpa ayrıca əməldir.": {
        "en": "Until this date the student's status is “academic leave”; reinstatement is a separate action.",
        "ru": "До этой даты статус студента — «академический отпуск»; восстановление — отдельное действие.",
        "tr": "Bu tarihe kadar öğrencinin durumu “akademik izin” olur; geri dönüş ayrı bir işlemdir.",
    },
    "Dondur": {"en": "Freeze", "ru": "Заморозить", "tr": "Askıya al"},
    "Fərdi plan (DOCX)": {
        "en": "Individual plan (DOCX)",
        "ru": "Индивидуальный план (DOCX)",
        "tr": "Bireysel plan (DOCX)",
    },
    "Fərdi tədris planı (DOCX) — bütöv qrup": {
        "en": "Individual study plan (DOCX) — whole group",
        "ru": "Индивидуальный учебный план (DOCX) — вся группа",
        "tr": "Bireysel öğretim planı (DOCX) — tüm grup",
    },
    "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
    "Məs.: 12/T": {"en": "e.g. 12/T", "ru": "напр. 12/T", "tr": "örn. 12/T"},
    "Məzun": {"en": "Graduated", "ru": "Выпускник", "tr": "Mezun"},
    "Məzuniyyətdə": {"en": "On leave", "ru": "В отпуске", "tr": "İzinde"},
    "Məzuniyyətin bitmə tarixi": {"en": "Leave end date", "ru": "Дата окончания отпуска", "tr": "İzin bitiş tarihi"},
    "Qeydiyyatlı": {"en": "Enrolled", "ru": "Зачислен", "tr": "Kayıtlı"},
    "Qrupdan çıxar": {"en": "Remove from group", "ru": "Убрать из группы", "tr": "Gruptan çıkar"},
    "Qrupun fərdi planı (DOCX)": {
        "en": "Group individual plan (DOCX)",
        "ru": "Индивидуальный план группы (DOCX)",
        "tr": "Grubun bireysel planı (DOCX)",
    },
    "Qrupun tələbələri": {"en": "Group students", "ru": "Студенты группы", "tr": "Grubun öğrencileri"},
    "Qəbul": {"en": "Admitted", "ru": "Приём", "tr": "Kabul"},
    "Siyahı yüklənmədi — yenidən cəhd edin.": {
        "en": "The list failed to load — try again.",
        "ru": "Список не загрузился — попробуйте ещё раз.",
        "tr": "Liste yüklenemedi — yeniden deneyin.",
    },
    "Status «akademik məzuniyyət» olur, qrup üzvlüyü qalır. Əmr nömrəsi, tarixi və bitmə tarixi məcburidir; hərəkət sətri silinmir.": {
        "en": "Status becomes “academic leave”; group membership stays. Order number, order date and end date are mandatory; the movement record is never deleted.",
        "ru": "Статус становится «академический отпуск», членство в группе сохраняется. Номер, дата приказа и дата окончания обязательны; запись о движении не удаляется.",
        "tr": "Durum “akademik izin” olur, grup üyeliği kalır. Emir numarası, tarihi ve bitiş tarihi zorunludur; hareket kaydı silinmez.",
    },
    "Status «xaric edilib» olur. Əmr nömrəsi və tarixi məcburidir; bərpa ayrıca əməldir və yenə səbəblə audit olunur.": {
        "en": "Status becomes “expelled”. Order number and date are mandatory; reinstatement is a separate, audited action.",
        "ru": "Статус становится «отчислен». Номер и дата приказа обязательны; восстановление — отдельное действие с аудитом.",
        "tr": "Durum “ihraç edildi” olur. Emir numarası ve tarihi zorunludur; geri dönüş ayrı ve denetlenen bir işlemdir.",
    },
    "Statusa görə süz": {"en": "Filter by status", "ru": "Фильтр по статусу", "tr": "Duruma göre süz"},
    "Sənəd universitetin rəsmi formasındadır — hər tələbə ayrıca səhifədə.": {
        "en": "The document follows the university's official form — one page per student.",
        "ru": "Документ в официальной форме университета — каждый студент на отдельной странице.",
        "tr": "Belge üniversitenin resmi formundadır — her öğrenci ayrı sayfada.",
    },
    "Tələbə": {"en": "Student", "ru": "Студент", "tr": "Öğrenci"},
    "Tələbələr": {"en": "Students", "ru": "Студенты", "tr": "Öğrenciler"},
    "Tələbələr yüklənir…": {"en": "Loading students…", "ru": "Загрузка студентов…", "tr": "Öğrenciler yükleniyor…"},
    "Tələbəni dondur (akademik məzuniyyət)": {
        "en": "Freeze student (academic leave)",
        "ru": "Заморозить студента (академический отпуск)",
        "tr": "Öğrenciyi askıya al (akademik izin)",
    },
    "Tələbəni qrupdan çıxar (başqa qrupa köçür)": {
        "en": "Remove student from group (transfer to another group)",
        "ru": "Убрать студента из группы (перевести в другую группу)",
        "tr": "Öğrenciyi gruptan çıkar (başka gruba aktar)",
    },
    "Qrup dəyişikliyi yalnız rəsmi köçürmə ilə olur: hədəf qrup, əmr nömrəsi və tarixi məcburidir. Köhnə qrupdakı jurnal qeydiyyatı tarixçəyə keçir, silinmir.": {
        "en": "A group change is only done by an official transfer: target group, order number and date are mandatory. Journal enrollments in the old group move to history — nothing is deleted.",
        "ru": "Смена группы возможна только официальным переводом: целевая группа, номер и дата приказа обязательны. Зачисления в журналах старой группы уходят в историю — ничего не удаляется.",
        "tr": "Grup değişikliği yalnızca resmi aktarımla yapılır: hedef grup, emir numarası ve tarihi zorunludur. Eski gruptaki günlük kayıtları geçmişe geçer, silinmez.",
    },
    "Hədəf qrup": {"en": "Target group", "ru": "Целевая группа", "tr": "Hedef grup"},
    "Seçin": {"en": "Select", "ru": "Выберите", "tr": "Seçin"},
    "Yalnız sizin əhatənizdəki aktiv qruplar. Köçürmə cari tədris dövründə aparılır.": {
        "en": "Only active groups within your scope. The transfer is made in the current academic term.",
        "ru": "Только активные группы в вашей зоне ответственности. Перевод выполняется в текущем учебном периоде.",
        "tr": "Yalnızca kapsamınızdaki aktif gruplar. Aktarım cari öğretim döneminde yapılır.",
    },
    "Tələbəni uzaqlaşdır (xaric)": {
        "en": "Expel student",
        "ru": "Отчислить студента",
        "tr": "Öğrenciyi uzaklaştır (ihraç)",
    },
    "Uzaqlaşdır": {"en": "Expel", "ru": "Отчислить", "tr": "Uzaklaştır"},
    "Xaric edilib": {"en": "Expelled", "ru": "Отчислен", "tr": "İhraç edildi"},
    "Əmr nömrəsi": {"en": "Order number", "ru": "Номер приказа", "tr": "Emir numarası"},
    "Əmr tarixi": {"en": "Order date", "ru": "Дата приказа", "tr": "Emir tarihi"},
}

_SEMESTER = {
    "Açılış sətirləri": {"en": "Offering rows", "ru": "Строки открытия", "tr": "Açılış satırları"},
    "Hər kafedranın neçə açılışı var və neçəsinə müəllim təyin olunub — təyinat kafedra rəhbərinin «Dərs yükü» bölməsindən edilir.": {
        "en": "How many offerings each chair has and how many have an instructor — assignment is done from the chair head's “Teaching load” section.",
        "ru": "Сколько открытий у каждой кафедры и скольким назначен преподаватель — назначение выполняется из раздела «Нагрузка» заведующего кафедрой.",
        "tr": "Her bölümün kaç açılışı var ve kaçına öğretim üyesi atandı — atama bölüm başkanının “Ders yükü” bölümünden yapılır.",
    },
    "Necə işləyir — 5 addımda semestr açılışı": {
        "en": "How it works — semester opening in 5 steps",
        "ru": "Как это работает — открытие семестра за 5 шагов",
        "tr": "Nasıl çalışır — 5 adımda dönem açılışı",
    },
    "Planı təsdiqlənməmiş ixtisaslar": {
        "en": "Specialties without an approved plan",
        "ru": "Специальности без утверждённого плана",
        "tr": "Planı onaylanmamış uzmanlıklar",
    },
    "cəmi %(n)s ixtisas": {
        "en": "%(n)s specialties in total",
        "ru": "всего специальностей: %(n)s",
        "tr": "toplam %(n)s uzmanlık",
    },
    "«Plan yoxdur» — bu ixtisaslar üçün açılış yaradıla bilməz": {
        "en": "“No plan” — offerings cannot be created for these specialties",
        "ru": "«Нет плана» — для этих специальностей нельзя создать открытия",
        "tr": "“Plan yok” — bu uzmanlıklar için açılış oluşturulamaz",
    },
    "Üç şərt də ödənəndə «Semestri kilidlə» düyməsi aktivləşir. Kilid açılış sətirlərini dondurur; geri açmaq ayrıca səlahiyyət və səbəb tələb edir.": {
        "en": "When all three conditions are met, “Lock semester” becomes active. The lock freezes offering rows; unlocking needs a separate permission and a reason.",
        "ru": "Когда выполнены все три условия, кнопка «Закрыть семестр» становится активной. Блокировка замораживает строки открытия; снятие требует отдельного права и причины.",
        "tr": "Üç koşul da sağlanınca “Dönemi kilitle” etkinleşir. Kilit açılış satırlarını dondurur; açmak ayrı yetki ve gerekçe ister.",
    },
    "İndi:": {"en": "Now:", "ru": "Сейчас:", "tr": "Şimdi:"},
    "Əvvəlcə «Tədris planı» bölməsində həmin ixtisasın planı təsdiqlənməlidir; təsdiqdən sonra «Plandan açılış yarat» onları da əhatə edir.": {
        "en": "First approve that specialty's plan in the “Curriculum” section; after approval “Create offerings from plan” covers them too.",
        "ru": "Сначала утвердите план этой специальности в разделе «Учебный план»; после утверждения «Создать открытия из плана» охватит и их.",
        "tr": "Önce “Öğretim planı” bölümünde o uzmanlığın planı onaylanmalı; onaydan sonra “Plandan açılış oluştur” onları da kapsar.",
    },
    # semester_open.semester_howto / semester_steps — pgettext(_CTX, …) (skaner görmür).
    "Tədris dövrünü seçin və plandan açılış yaradın": {
        "en": "Pick the term and create offerings from the plan",
        "ru": "Выберите период и создайте открытия из плана",
        "tr": "Dönemi seçin ve plandan açılış oluşturun",
    },
    "Yuxarıdakı süzgəcdən semestri seçin. «Plandan açılış yarat» hər qrup üçün təsdiqlənmiş tədris planından fənn sətirləri yaradır; mövcud sətir təkrarlanmır, heç nə silinmir. «Plan yoxdur» ixtisaslar üçün sətir yaranmır — əvvəlcə «Tədris planı» bölməsində planı təsdiqləyin.": {
        "en": "Pick the semester in the filter above. “Create offerings from plan” creates subject rows for every group from the approved curriculum; existing rows are not duplicated and nothing is deleted. No rows are created for “no plan” specialties — approve the plan in “Curriculum” first.",
        "ru": "Выберите семестр в фильтре выше. «Создать открытия из плана» создаёт строки предметов для каждой группы из утверждённого плана; существующие строки не дублируются, ничего не удаляется. Для специальностей «нет плана» строки не создаются — сначала утвердите план в «Учебном плане».",
        "tr": "Yukarıdaki süzgeçten dönemi seçin. “Plandan açılış oluştur” onaylı öğretim planından her grup için ders satırları oluşturur; mevcut satır yinelenmez, hiçbir şey silinmez. “Plan yok” uzmanlıklar için satır oluşmaz — önce “Öğretim planı”nda planı onaylayın.",
    },
    "Plandan açılış yarat": {
        "en": "Create offerings from plan",
        "ru": "Создать открытия из плана",
        "tr": "Plandan açılış oluştur",
    },
    "Tədris şöbəsi": {"en": "Teaching office", "ru": "Учебный отдел", "tr": "Öğretim işleri"},
    "Kafedralara göndərin": {"en": "Send to chairs", "ru": "Отправьте кафедрам", "tr": "Bölümlere gönderin"},
    "Açılış sətirləri hazır olanda «Kafedraya göndər» kafedra rəhbərlərinə bildiriş göndərir — bundan sonra onlar «Dərs yükü» bölməsində öz fənlərinə müəllim təyin edə bilir.": {
        "en": "Once offering rows are ready, “Send to chair” notifies chair heads — after that they assign instructors to their subjects in “Teaching load”.",
        "ru": "Когда строки готовы, «Отправить кафедре» уведомляет заведующих — после этого они назначают преподавателей в разделе «Нагрузка».",
        "tr": "Açılış satırları hazır olunca “Bölüme gönder” bölüm başkanlarına bildirim yollar — sonra onlar “Ders yükü”nde derslerine öğretim üyesi atar.",
    },
    "Kafedraya göndər": {"en": "Send to chair", "ru": "Отправить кафедре", "tr": "Bölüme gönder"},
    "Kafedra müəllim təyin edir": {
        "en": "Chair assigns instructors",
        "ru": "Кафедра назначает преподавателей",
        "tr": "Bölüm öğretim üyesi atar",
    },
    "Hər açılışa müəllim təyin olunmalıdır. Aşağıdakı «Kafedralar üzrə açılış» cədvəli neçə sətrin müəllim gözlədiyini göstərir; açılış sətrindəki «Müəllim» əməli ilə buradan da təyin etmək olar.": {
        "en": "Every offering needs an instructor. The “Offerings by chair” table below shows how many rows are still waiting; you can also assign from the row's “Instructor” action here.",
        "ru": "Каждому открытию нужен преподаватель. Таблица «Открытия по кафедрам» ниже показывает, сколько строк ещё ждут; назначить можно и отсюда действием «Преподаватель» в строке.",
        "tr": "Her açılışa öğretim üyesi atanmalı. Aşağıdaki “Bölümlere göre açılış” tablosu kaç satırın beklediğini gösterir; satırdaki “Öğretim üyesi” işlemiyle buradan da atanabilir.",
    },
    "Dərs yükü → Müəllim təyin et": {
        "en": "Teaching load → Assign instructor",
        "ru": "Нагрузка → Назначить преподавателя",
        "tr": "Ders yükü → Öğretim üyesi ata",
    },
    "Kafedra rəhbəri": {"en": "Chair head", "ru": "Заведующий кафедрой", "tr": "Bölüm başkanı"},
    "Jurnallar açılır": {"en": "Journals open", "ru": "Журналы открываются", "tr": "Günlükler açılır"},
    "Müəllim təyin olunan kimi həmin fənnin elektron jurnalı avtomatik yaranır. Jurnalı olmayan sətir müəllimi olmayan sətirdir — ayrıca əməl tələb olunmur.": {
        "en": "As soon as an instructor is assigned, the subject's e-journal is created automatically. A row without a journal is a row without an instructor — no separate action is needed.",
        "ru": "Как только назначен преподаватель, электронный журнал предмета создаётся автоматически. Строка без журнала — строка без преподавателя; отдельное действие не требуется.",
        "tr": "Öğretim üyesi atanır atanmaz dersin e-günlüğü otomatik oluşur. Günlüğü olmayan satır öğretim üyesi olmayan satırdır — ayrı işlem gerekmez.",
    },
    "Sistem (avtomatik)": {"en": "System (automatic)", "ru": "Система (автоматически)", "tr": "Sistem (otomatik)"},
    "Semestri kilidləyin": {"en": "Lock the semester", "ru": "Закройте семестр", "tr": "Dönemi kilitleyin"},
    "Üç şərt ödənəndə (plan təsdiqlənib, bütün açılışlara müəllim var, jurnallar açılıb) «Semestri kilidlə» aktivləşir. Kilid açılış sətirlərini dondurur; onu yalnız ayrıca səlahiyyətli şəxs səbəb yazmaqla aça bilər.": {
        "en": "When the three conditions hold (plan approved, every offering has an instructor, journals open), “Lock semester” becomes active. The lock freezes offering rows; only a separately authorised person can unlock it with a reason.",
        "ru": "Когда выполнены три условия (план утверждён, у всех открытий есть преподаватель, журналы открыты), «Закрыть семестр» становится активной. Блокировка замораживает строки; снять её может только отдельно уполномоченный, указав причину.",
        "tr": "Üç koşul sağlanınca (plan onaylı, her açılışta öğretim üyesi var, günlükler açık) “Dönemi kilitle” etkinleşir. Kilit açılış satırlarını dondurur; yalnız ayrı yetkili biri gerekçe yazarak açabilir.",
    },
    "Semestri kilidlə": {"en": "Lock semester", "ru": "Закрыть семестр", "tr": "Dönemi kilitle"},
    "Tədris şöbəsi rəhbəri": {
        "en": "Head of teaching office",
        "ru": "Руководитель учебного отдела",
        "tr": "Öğretim işleri başkanı",
    },
    "%(n)d açılış sətri yaradılıb": {
        "en": "%(n)d offering rows created",
        "ru": "создано строк открытия: %(n)d",
        "tr": "%(n)d açılış satırı oluşturuldu",
    },
    "«Plandan açılış yarat» düyməsi ilə başlayın": {
        "en": "Start with the “Create offerings from plan” button",
        "ru": "Начните с кнопки «Создать открытия из плана»",
        "tr": "“Plandan açılış oluştur” düğmesiyle başlayın",
    },
    "Kafedra rəhbərlərinə bildiriş gedib": {
        "en": "Chair heads have been notified",
        "ru": "Заведующие кафедрами уведомлены",
        "tr": "Bölüm başkanlarına bildirim gitti",
    },
    "«Kafedraya göndər» — rəhbərlərə bildiriş gedir, təyinat başlayır": {
        "en": "“Send to chair” — heads get notified, assignment begins",
        "ru": "«Отправить кафедре» — заведующие получат уведомление, начнётся назначение",
        "tr": "“Bölüme gönder” — başkanlara bildirim gider, atama başlar",
    },
    "Bütün açılışlara müəllim təyin olunub": {
        "en": "Every offering has an instructor",
        "ru": "Всем открытиям назначен преподаватель",
        "tr": "Tüm açılışlara öğretim üyesi atandı",
    },
    "%(n)d açılış müəllim gözləyir — kafedra «Dərs yükü»ndən təyin edir": {
        "en": "%(n)d offerings await an instructor — the chair assigns from “Teaching load”",
        "ru": "открытий без преподавателя: %(n)d — кафедра назначает из «Нагрузки»",
        "tr": "%(n)d açılış öğretim üyesi bekliyor — bölüm “Ders yükü”nden atar",
    },
    "Bütün jurnallar açılıb": {
        "en": "All journals are open",
        "ru": "Все журналы открыты",
        "tr": "Tüm günlükler açıldı",
    },
    "%(n)d açılışın jurnalı açılmayıb — müəllim təyin olunduqca açılır": {
        "en": "%(n)d offerings have no journal yet — it opens once an instructor is assigned",
        "ru": "открытий без журнала: %(n)d — журнал открывается после назначения преподавателя",
        "tr": "%(n)d açılışın günlüğü açılmadı — öğretim üyesi atanınca açılır",
    },
    "Semestr kilidlidir — açılış sətirləri dəyişmir": {
        "en": "Semester is locked — offering rows are frozen",
        "ru": "Семестр закрыт — строки открытия не меняются",
        "tr": "Dönem kilitli — açılış satırları değişmez",
    },
    "Üç şərt ödənəndə «Semestri kilidlə» aktivləşir; kilid geri qaytarılmır": {
        "en": "“Lock semester” activates when the three conditions hold; the lock is not reversible",
        "ru": "«Закрыть семестр» активируется при трёх условиях; блокировка не отменяется",
        "tr": "Üç koşul sağlanınca “Dönemi kilitle” etkinleşir; kilit geri alınmaz",
    },
}

_CHECKBOX = {
    "all_specialties": {
        "az": "Bütün ixtisaslar",
        "en": "All specialties",
        "ru": "Все специальности",
        "tr": "Tüm uzmanlıklar",
    },
    "filter_by_specialty": {
        "az": "İxtisasa görə süz",
        "en": "Filter by specialty",
        "ru": "Фильтр по специальности",
        "tr": "Uzmanlığa göre süz",
    },
}

_PROFILE_GROUPS = {
    "confirm_back": {"az": "Geri", "en": "Back", "ru": "Назад", "tr": "Geri"},
    "confirm_create_submit": {
        "az": "Təsdiqlə və yarat",
        "en": "Confirm and create",
        "ru": "Подтвердить и создать",
        "tr": "Onayla ve oluştur",
    },
    "confirm_create_title": {
        "az": "Qrupu yaratmağı təsdiqləyin",
        "en": "Confirm group creation",
        "ru": "Подтвердите создание группы",
        "tr": "Grup oluşturmayı onaylayın",
    },
    "confirm_no_students": {
        "az": "Tələbə seçilməyib — qrup boş yaradılacaq.",
        "en": "No students selected — the group will be created empty.",
        "ru": "Студенты не выбраны — группа будет создана пустой.",
        "tr": "Öğrenci seçilmedi — grup boş oluşturulacak.",
    },
    "confirm_student_count": {
        "az": "Tələbə sayı",
        "en": "Number of students",
        "ru": "Число студентов",
        "tr": "Öğrenci sayısı",
    },
}

_GUEST = {
    "PDF və ya şəkil, 10 MB-dək. Sənəd əlavə qeydiyyatı ilə birlikdə saxlanılır və silinmir.": {
        "en": "PDF or image, up to 10 MB. The document is stored with the enrollment and never deleted.",
        "ru": "PDF или изображение до 10 МБ. Документ хранится вместе с зачислением и не удаляется.",
        "tr": "PDF veya görsel, 10 MB'a kadar. Belge kayıtla birlikte saklanır ve silinmez.",
    },
    "SƏNƏD — TƏQDİMAT / SƏRƏNCAM (MƏCBURİ)": {
        "en": "DOCUMENT — SUBMISSION / ORDER (REQUIRED)",
        "ru": "ДОКУМЕНТ — ПРЕДСТАВЛЕНИЕ / РАСПОРЯЖЕНИЕ (ОБЯЗАТЕЛЬНО)",
        "tr": "BELGE — SUNUM / TALİMAT (ZORUNLU)",
    },
    "Sənəd": {"en": "Document", "ru": "Документ", "tr": "Belge"},
    "Sənəd (təqdimat / sərəncam) yüklənməlidir.": {
        "en": "A document (submission / order) must be uploaded.",
        "ru": "Необходимо загрузить документ (представление / распоряжение).",
        "tr": "Belge (sunum / talimat) yüklenmelidir.",
    },
    "Təqdimat və ya sərəncamın skanı (PDF/şəkil, 10 MB-dək)": {
        "en": "Scan of the submission or order (PDF/image, up to 10 MB)",
        "ru": "Скан представления или распоряжения (PDF/изображение, до 10 МБ)",
        "tr": "Sunum veya talimatın taraması (PDF/görsel, 10 MB'a kadar)",
    },
    "Sənəd (təqdimat / sərəncam) yüklənməlidir — alt qrupdan əlavə sənədsiz edilmir.": {
        "en": "A document (submission / order) must be uploaded — adding from a subgroup is not allowed without it.",
        "ru": "Необходимо загрузить документ (представление / распоряжение) — добавление из подгруппы без него невозможно.",
        "tr": "Belge (sunum / talimat) yüklenmelidir — alt gruptan ekleme belgesiz yapılamaz.",
    },
}

_GROUPS_PY = {}

_MODEL_META = {
    "guest roster document": {
        "az": "alt qrup sənədi",
        "en": "guest roster document",
        "ru": "документ подгруппы",
        "tr": "alt grup belgesi",
    },
    "guest roster documents": {
        "az": "alt qrup sənədləri",
        "en": "guest roster documents",
        "ru": "документы подгруппы",
        "tr": "alt grup belgeleri",
    },
}

ENTRIES = {
    "accounts.groups": {**_GROUPS, **_GROUPS_PY},
    "accounts.semester": _SEMESTER,
    "profile.checkbox_select": _CHECKBOX,
    "profile.groups": _PROFILE_GROUPS,
    "registrar.guest_roster": _GUEST,
    "registrar.model.guest_document.meta": _MODEL_META,
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
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            # Açar-tipli msgid-lərdə (`confirm_back`) AZ mətni də lüğətdən gəlir.
            msgstr = translations.get(lang) if lang != "az" else translations.get("az", msgid)
            if msgstr is None:
                msgstr = msgid
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
