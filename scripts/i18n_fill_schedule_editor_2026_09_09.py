#!/usr/bin/env python3
"""EMSArena i18n — həftəlik cədvəl REDAKTORU (4 dil). İdempotent, append-only.

Əhatə (sahibin 2026-09-09 tapşırığı — «Cədvəl idarəetməsi»):
  * `accounts.schedule_manage`     — panel, filtrlər, dialoqlar, çekmecə
  * `accounts.schedule_editor`     — JSON səthinin xəta mətnləri
  * `registrar.schedule_grid`      — həmişə görünən matris (ortaq partial)
  * `registrar.schedule_conflicts` — konflikt cümlələri (placeholder-li)
  * `registrar.schedule_editor`    — hüceyrə validasiyası / açılış bağlaması

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir, mövcud girişə toxunmur.
   Paralel işləyən başqa agent eyni `.po` fayllarını dəyişə bilər; ona görə
   yazma append-only-dir və mövcud (msgctxt, msgid) cütü görünəndə keçilir.

İstifadə:  python scripts/i18n_fill_schedule_editor_2026_09_09.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def _e(en, ru, tr):
    return {"en": en, "ru": ru, "tr": tr}


# ─────────────────────────────────────────────────────────────────────────────
# registrar.schedule_grid — həmişə görünən matris
# ─────────────────────────────────────────────────────────────────────────────
GRID = {
    # tr: «SAAT» azərbaycanca ilə eyni yazılır — identity borcu yaratmasın deyə açıqlanır.
    "SAAT": _e("HOUR", "ЧАС", "DERS SAATİ"),
    # tr: üst/alt həftə Türkiyədə «tek/çift hafta» adlanır (identity də olmur).
    "ÜST": _e("UPPER", "ВЕРХ", "TEK"),
    "ALT": _e("LOWER", "НИЗ", "ÇİFT"),
    "bu gün": _e("today", "сегодня", "bugün"),
    "Həftəlik dərs cədvəli": _e("Weekly timetable", "Недельное расписание", "Haftalık ders programı"),
    "Sətirlər — nömrələnmiş dərs saatları, sütunlar — həftənin günləri.": _e(
        "Rows are the numbered lesson hours, columns are the days of the week.",
        "Строки — пронумерованные учебные часы, столбцы — дни недели.",
        "Satırlar numaralandırılmış ders saatleri, sütunlar haftanın günleridir.",
    ),
    "Bu xanaya dərs əlavə et": _e("Add a lesson to this cell", "Добавить занятие в эту ячейку", "Bu hücreye ders ekle"),
    "Standart zəngdən kənar": _e("Outside the bell schedule", "Вне расписания звонков", "Zil düzeninin dışında"),
    "Bu saatlar təşkilatın zəng cədvəlində yoxdur — köçürülmüş və ya əl ilə yazılmış dərslərdir.": _e(
        "These hours are not in the organisation’s bell schedule — they are migrated or manually entered lessons.",
        "Этих часов нет в расписании звонков организации — это перенесённые или введённые вручную занятия.",
        "Bu saatler kurumun zil düzeninde yok — taşınmış veya elle girilmiş derslerdir.",
    ),
    "Bu qrupun bu semestrdə hələ dərsi yoxdur — boş xanaya klikləyib ilk dərsi qoyun.": _e(
        "This group has no lessons this semester yet — click an empty cell to place the first one.",
        "У этой группы ещё нет занятий в этом семестре — щёлкните пустую ячейку, чтобы поставить первое.",
        "Bu grubun bu dönemde henüz dersi yok — boş bir hücreye tıklayıp ilk dersi yerleştirin.",
    ),
    "Bu semestr üçün hələ dərs qeyd edilməyib — cədvəl boş görünür.": _e(
        "No lessons have been recorded for this semester yet — the timetable is empty.",
        "На этот семестр занятия ещё не внесены — расписание пустое.",
        "Bu dönem için henüz ders girilmedi — program boş görünüyor.",
    ),
    "Səhər növbəsi": _e("Morning shift", "Утренняя смена", "Sabah vardiyası"),
    "Günorta növbəsi": _e("Afternoon shift", "Дневная смена", "Öğleden sonra vardiyası"),
    "Axşam (magistratura)": _e("Evening (master’s)", "Вечер (магистратура)", "Akşam (yüksek lisans)"),
}


# ─────────────────────────────────────────────────────────────────────────────
# registrar.schedule_conflicts — konflikt cümlələri
# ─────────────────────────────────────────────────────────────────────────────
CONFLICTS = {
    "Müəllimin %(day)s %(time)s-da %(group)s qrupunda dərsi var (%(subject)s).": _e(
        "The teacher already has a lesson with group %(group)s on %(day)s at %(time)s (%(subject)s).",
        "У преподавателя уже есть занятие с группой %(group)s в %(day)s в %(time)s (%(subject)s).",
        "Öğretmenin %(day)s günü %(time)s saatinde %(group)s grubunda dersi var (%(subject)s).",
    ),
    "Qrupun %(day)s %(time)s-da artıq dərsi var (%(subject)s).": _e(
        "The group already has a lesson on %(day)s at %(time)s (%(subject)s).",
        "У группы уже есть занятие в %(day)s в %(time)s (%(subject)s).",
        "Grubun %(day)s günü %(time)s saatinde zaten dersi var (%(subject)s).",
    ),
    "%(room)s auditoriyası %(day)s %(time)s-da %(group)s qrupu tərəfindən tutulub.": _e(
        "Room %(room)s is taken by group %(group)s on %(day)s at %(time)s.",
        "Аудитория %(room)s занята группой %(group)s в %(day)s в %(time)s.",
        "%(room)s dersliği %(day)s günü %(time)s saatinde %(group)s grubu tarafından kullanılıyor.",
    ),
    "müəllim": _e("teacher", "преподаватель", "öğretmen"),
    "qrup": _e("group", "группа", "grup"),
    "auditoriya": _e("room", "аудитория", "derslik"),
    "üst həftə": _e("upper week", "верхняя неделя", "üst hafta"),
    "alt həftə": _e("lower week", "нижняя неделя", "alt hafta"),
    "hər həftə": _e("every week", "каждую неделю", "her hafta"),
    "təyin edilməmiş qrup": _e("unassigned group", "группа не назначена", "atanmamış grup"),
    "müəllim təyin edilməyib": _e("no teacher assigned", "преподаватель не назначен", "öğretmen atanmadı"),
}


# ─────────────────────────────────────────────────────────────────────────────
# registrar.schedule_editor — hüceyrə validasiyası / açılış bağlaması
# ─────────────────────────────────────────────────────────────────────────────
EDITOR = {
    "Həftənin günü seçilməlidir.": _e("Pick a day of the week.", "Выберите день недели.", "Haftanın gününü seçin."),
    "Dərs saatı seçilməlidir.": _e("Pick a lesson hour.", "Выберите учебный час.", "Ders saatini seçin."),
    "Auditoriya adı 64 simvoldan uzun ola bilməz.": _e(
        "The room name cannot be longer than 64 characters.",
        "Название аудитории не может быть длиннее 64 символов.",
        "Derslik adı 64 karakterden uzun olamaz.",
    ),
    "Fənn seçilməlidir.": _e("Pick a subject.", "Выберите предмет.", "Ders seçin."),
    "Semestr və qrup seçilməlidir.": _e(
        "Pick a semester and a group.", "Выберите семестр и группу.", "Dönem ve grup seçin."
    ),
    "Bu slot artıq cədvəldədir.": _e(
        "This slot is already in the timetable.", "Этот слот уже есть в расписании.", "Bu slot zaten programda."
    ),
    "Bu slot parklanmayıb.": _e("This slot is not parked.", "Этот слот не отложен.", "Bu slot beklemede değil."),
    "Slot yadda saxlanılmadı — məlumatları yoxlayın.": _e(
        "The slot was not saved — check the details.",
        "Слот не сохранён — проверьте данные.",
        "Slot kaydedilmedi — bilgileri kontrol edin.",
    ),
    "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur.": _e(
        "You do not have permission to manage the timetable.",
        "У вас нет прав управлять расписанием.",
        "Ders programını yönetme yetkiniz yok.",
    ),
    "Açılışın müəllimi «Fənn təhvili» ilə dəyişilir.": _e(
        "The offering’s teacher is changed through “Course handover”.",
        "Преподаватель дисциплины меняется через «Передачу предмета».",
        "Dersin öğretmeni “Ders devri” ile değiştirilir.",
    ),
    (
        "Bu fənn həmin qrupda artıq %(teacher)s müəlliminə bağlıdır. Müəllimi dəyişmək üçün "
        "«Fənn təhvili» bölməsindən istifadə edin — cədvəl redaktoru jurnal sahibliyini dəyişmir."
    ): _e(
        "This subject is already assigned to %(teacher)s for that group. Use “Course handover” to change the "
        "teacher — the timetable editor does not change gradebook ownership.",
        "Этот предмет в данной группе уже закреплён за преподавателем %(teacher)s. Чтобы сменить преподавателя, "
        "используйте «Передачу предмета» — редактор расписания не меняет владельца журнала.",
        "Bu ders o grupta zaten %(teacher)s öğretmenine bağlı. Öğretmeni değiştirmek için “Ders devri” bölümünü "
        "kullanın — program editörü not defteri sahipliğini değiştirmez.",
    ),
    "Məcburi dəyişiklik üçün ən azı 10 simvolluq səbəb yazılmalıdır (auditə düşür).": _e(
        "A forced change needs a reason of at least 10 characters (it goes to the audit log).",
        "Для принудительного изменения нужна причина не менее 10 символов (она попадает в журнал аудита).",
        "Zorunlu değişiklik için en az 10 karakterlik bir gerekçe gerekir (denetim günlüğüne yazılır).",
    ),
    "Səbəb qısadır.": _e("The reason is too short.", "Причина слишком короткая.", "Gerekçe çok kısa."),
    "Toqquşan dərs sizin səlahiyyət sahənizdən kənardadır — məcburi dəyişiklik mümkün deyil.": _e(
        "The clashing lesson is outside your scope — a forced change is not possible.",
        "Конфликтующее занятие вне вашей зоны ответственности — принудительное изменение невозможно.",
        "Çakışan ders yetki alanınızın dışında — zorunlu değişiklik yapılamaz.",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# accounts.schedule_editor — JSON səthi
# ─────────────────────────────────────────────────────────────────────────────
VIEW = {
    "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur.": _e(
        "You do not have permission to manage the timetable.",
        "У вас нет прав управлять расписанием.",
        "Ders programını yönetme yetkiniz yok.",
    ),
    "Naməlum əməliyyat.": _e("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
}


# ─────────────────────────────────────────────────────────────────────────────
# accounts.schedule_manage — panel, dialoq, çekmecə
# ─────────────────────────────────────────────────────────────────────────────
PANEL = {
    # Başlıq / boş hallar
    "Bu bölmə sizin üçün bağlıdır": _e(
        "This section is closed for you", "Этот раздел вам недоступен", "Bu bölüm size kapalı"
    ),
    "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur — bu bölmə yalnız səlahiyyətli rollar üçündür.": _e(
        "You do not have permission to manage the timetable — this section is for authorised roles only.",
        "У вас нет прав управлять расписанием — этот раздел только для уполномоченных ролей.",
        "Ders programını yönetme yetkiniz yok — bu bölüm yalnızca yetkili roller içindir.",
    ),
    "Səlahiyyət sahənizdə qrup yoxdur": _e(
        "No groups in your scope", "В вашей зоне нет групп", "Yetki alanınızda grup yok"
    ),
    "Üzvlüyünüzə struktur bölməsi (scope_unit) təyin edilməyibsə qrup siyahısı boş qalır.": _e(
        "If no structural unit (scope_unit) is set on your membership, the group list stays empty.",
        "Если у вашего членства не задано структурное подразделение (scope_unit), список групп будет пустым.",
        "Üyeliğinize bir yapı birimi (scope_unit) atanmadıysa grup listesi boş kalır.",
    ),
    "Akademik semestr yoxdur": _e("No academic semester", "Нет учебного семестра", "Akademik dönem yok"),
    "Bu təşkilatda semestr yaradılmayıb — cədvəl qurmaq üçün əvvəlcə semestr açılmalıdır.": _e(
        "No semester has been created in this organisation — open a semester first to build a timetable.",
        "В этой организации не создан семестр — чтобы составить расписание, сначала откройте семестр.",
        "Bu kurumda dönem oluşturulmamış — program kurmak için önce dönem açılmalıdır.",
    ),
    "Qrupu seçin, boş xanaya klikləyib dərs qoyun, dərsi sürüşdürüb yerini dəyişin. Toqquşmalar saxlamadan əvvəl "
    "göstərilir; hər dəyişiklik müəllimə və qrupun tələbələrinə bildiriş kimi gedir.": _e(
        "Pick a group, click an empty cell to place a lesson, drag a lesson to move it. Clashes are shown before "
        "saving; every change is sent as a notification to the teacher and the group’s students.",
        "Выберите группу, щёлкните пустую ячейку, чтобы поставить занятие, перетащите занятие, чтобы перенести его. "
        "Конфликты показываются до сохранения; каждое изменение уходит уведомлением преподавателю и студентам группы.",
        "Grubu seçin, boş hücreye tıklayıp ders yerleştirin, dersi sürükleyerek taşıyın. Çakışmalar kaydetmeden önce "
        "gösterilir; her değişiklik öğretmene ve grubun öğrencilerine bildirim olarak gider.",
    ),
    "Bütün universitet": _e("The whole university", "Весь университет", "Tüm üniversite"),
    "Yalnız öz struktur bölmələriniz": _e(
        "Only your own structural units", "Только ваши структурные подразделения", "Yalnızca kendi yapı birimleriniz"
    ),
    # KPI
    "CƏDVƏLDƏ DƏRS": _e("LESSONS PLACED", "ЗАНЯТИЙ В РАСПИСАНИИ", "PROGRAMDAKİ DERS"),
    "BOŞ XANA": _e("EMPTY CELLS", "ПУСТЫХ ЯЧЕЕК", "BOŞ HÜCRE"),
    "YENİDƏN YERLƏŞDİRİLMƏLİ": _e("NEEDS REPLACING", "ТРЕБУЕТ ПЕРЕНОСА", "YENİDEN YERLEŞTİRİLECEK"),
    "PLANDAKI FƏNN": _e("SUBJECTS IN PLAN", "ПРЕДМЕТОВ В ПЛАНЕ", "PLANDAKİ DERS"),
    # Filtrlər
    "Tədris ili": _e("Academic year", "Учебный год", "Öğretim yılı"),
    "Semestr": _e("Semester", "Семестр", "Dönem"),
    "Görünüş": _e("View", "Вид", "Görünüm"),
    "Qrup cədvəli": _e("Group timetable", "Расписание группы", "Grup programı"),
    "Müəllim cədvəli": _e("Teacher timetable", "Расписание преподавателя", "Öğretmen programı"),
    "Qrup": _e("Group", "Группа", "Grup"),
    "Müəllim": _e("Teacher", "Преподаватель", "Öğretmen"),
    "Seçin…": _e("Select…", "Выберите…", "Seçiniz…"),
    # Həftə pilləri / legend
    "Bu həftə": _e("This week", "Эта неделя", "Bu hafta"),
    "Gələn həftə": _e("Next week", "Следующая неделя", "Gelecek hafta"),
    "ÜST": _e("UPPER", "ВЕРХ", "TEK"),
    "ALT": _e("LOWER", "НИЗ", "ÇİFT"),
    "Mühazirə": _e("Lecture", "Лекция", "Ders anlatımı"),
    "Məşğələ": _e("Seminar", "Семинар", "Uygulama"),
    "Laboratoriya": _e("Lab", "Лаборатория", "Laboratuvar"),
    "Dərsi sürüşdürüb başqa xanaya buraxın — təsdiq soruşulacaq.": _e(
        "Drag a lesson onto another cell — you will be asked to confirm.",
        "Перетащите занятие в другую ячейку — потребуется подтверждение.",
        "Dersi başka bir hücreye sürükleyin — onay istenecektir.",
    ),
    "Müəllim görünüşü yalnız-oxudur — dərs qoymaq üçün «Qrup cədvəli» görünüşünə keçin.": _e(
        "The teacher view is read-only — switch to “Group timetable” to place lessons.",
        "Вид преподавателя доступен только для чтения — перейдите к «Расписанию группы», чтобы ставить занятия.",
        "Öğretmen görünümü salt okunurdur — ders yerleştirmek için “Grup programı” görünümüne geçin.",
    ),
    "Yenidən yerləşdirilməli": _e("Needs replacing", "Требует переноса", "Yeniden yerleştirilecek"),
    # Hüceyrə dialoqu
    "Xanaya dərs qoy": _e("Place a lesson", "Поставить занятие", "Hücreye ders yerleştir"),
    "Dərsi redaktə et": _e("Edit the lesson", "Изменить занятие", "Dersi düzenle"),
    "Müəllim, fənn, dərs növü və həftə seçin; otaq opsionaldır. Toqquşma varsa saxlamadan əvvəl göstərilir.": _e(
        "Pick the teacher, subject, lesson type and week; the room is optional. Clashes are shown before saving.",
        "Выберите преподавателя, предмет, тип занятия и неделю; аудитория необязательна. Конфликты показываются "
        "до сохранения.",
        "Öğretmeni, dersi, ders türünü ve haftayı seçin; derslik isteğe bağlıdır. Çakışmalar kaydetmeden önce "
        "gösterilir.",
    ),
    "Cədvələ yaz": _e("Save to timetable", "Записать в расписание", "Programa yaz"),
    "Fənn": _e("Subject", "Предмет", "Ders"),
    "Fənn axtar…": _e("Search subjects…", "Поиск предмета…", "Ders ara…"),
    "Uyğun fənn yoxdur": _e("No matching subject", "Подходящего предмета нет", "Uygun ders yok"),
    "Siyahı qrupun tədris planı və açıq fənn açılışları ilə məhduddur.": _e(
        "The list is limited to the group’s study plan and its open course offerings.",
        "Список ограничен учебным планом группы и открытыми дисциплинами.",
        "Liste, grubun öğretim planı ve açık ders kayıtlarıyla sınırlıdır.",
    ),
    "Müəllim axtar…": _e("Search teachers…", "Поиск преподавателя…", "Öğretmen ara…"),
    "Uyğun müəllim yoxdur": _e("No matching teacher", "Подходящего преподавателя нет", "Uygun öğretmen yok"),
    "Seçilməyib": _e("Not selected", "Не выбрано", "Seçilmedi"),
    "Fənn artıq başqa müəllimə bağlıdırsa müəllim burada dəyişmir — «Fənn təhvili» bölməsindən istifadə edin.": _e(
        "If the subject is already bound to another teacher, the teacher is not changed here — use “Course handover”.",
        "Если предмет уже закреплён за другим преподавателем, здесь он не меняется — используйте «Передачу предмета».",
        "Ders zaten başka bir öğretmene bağlıysa öğretmen burada değişmez — “Ders devri” bölümünü kullanın.",
    ),
    "Dərs növü": _e("Lesson type", "Тип занятия", "Ders türü"),
    "Həftə": _e("Week", "Неделя", "Hafta"),
    "Gün": _e("Day", "День", "Gün"),
    "Dərs saatı": _e("Lesson hour", "Учебный час", "Ders saati"),
    "Otaq (opsional)": _e("Room (optional)", "Аудитория (необязательно)", "Derslik (isteğe bağlı)"),
    "məs. Otaq 304 · II korpus": _e(
        "e.g. Room 304 · Building II", "напр. Ауд. 304 · корпус II", "örn. Oda 304 · II. blok"
    ),
    "Dərsi cədvəldən çıxar": _e(
        "Remove the lesson from the timetable", "Убрать занятие из расписания", "Dersi programdan çıkar"
    ),
    # Toqquşma / tövsiyə / məcburi dəyişiklik
    "Toqquşma yoxdur — dərs bu xanaya qoyula bilər.": _e(
        "No clash — the lesson can be placed in this cell.",
        "Конфликтов нет — занятие можно поставить в эту ячейку.",
        "Çakışma yok — ders bu hücreye yerleştirilebilir.",
    ),
    "Yoxlanılır…": _e("Checking…", "Проверяется…", "Kontrol ediliyor…"),
    "Boş xanalar (həm müəllim, həm qrup boşdur)": _e(
        "Free cells (both the teacher and the group are free)",
        "Свободные ячейки (свободны и преподаватель, и группа)",
        "Boş hücreler (hem öğretmen hem grup boş)",
    ),
    "Boş yer təklif et": _e("Suggest a free slot", "Предложить свободное место", "Boş yer öner"),
    "Uyğun boş xana tapılmadı.": _e(
        "No suitable free cell was found.", "Подходящая свободная ячейка не найдена.", "Uygun boş hücre bulunamadı."
    ),
    "Bura qoy": _e("Place here", "Поставить сюда", "Buraya yerleştir"),
    "Məcburi dəyişikliyin səbəbi": _e(
        "Reason for the forced change", "Причина принудительного изменения", "Zorunlu değişikliğin gerekçesi"
    ),
    "Səbəb auditə yazılır (ən azı 10 simvol)": _e(
        "The reason is written to the audit log (at least 10 characters)",
        "Причина записывается в журнал аудита (не менее 10 символов)",
        "Gerekçe denetim günlüğüne yazılır (en az 10 karakter)",
    ),
    "Toqquşan dərs SİLİNMİR — «Yenidən yerləşdirilməli» siyahısına düşür və oradan başqa xanaya qoyula bilər.": _e(
        "The clashing lesson is NOT deleted — it moves to the “Needs replacing” list and can be placed elsewhere.",
        "Конфликтующее занятие НЕ удаляется — оно попадает в список «Требует переноса» и может быть поставлено "
        "в другую ячейку.",
        "Çakışan ders SİLİNMEZ — “Yeniden yerleştirilecek” listesine düşer ve başka bir hücreye konabilir.",
    ),
    "Toqquşan dərs SİLİNMİR — «Yenidən yerləşdirilməli» siyahısına düşür.": _e(
        "The clashing lesson is NOT deleted — it moves to the “Needs replacing” list.",
        "Конфликтующее занятие НЕ удаляется — оно попадает в список «Требует переноса».",
        "Çakışan ders SİLİNMEZ — “Yeniden yerleştirilecek” listesine düşer.",
    ),
    "Yenə də yerləşdir": _e("Place anyway", "Всё равно поставить", "Yine de yerleştir"),
    # Köçürmə dialoqu
    "Dərsin yerini dəyişmək": _e("Move the lesson", "Перенести занятие", "Dersin yerini değiştir"),
    "Dərs bu xanaya köçürülsün?": _e(
        "Move the lesson to this cell?", "Перенести занятие в эту ячейку?", "Ders bu hücreye taşınsın mı?"
    ),
    "Köçür": _e("Move", "Перенести", "Taşı"),
    "Ləğv et": _e("Cancel", "Отмена", "İptal"),
    # Çekmecə
    "Yenidən yerləşdirilməli dərslər": _e(
        "Lessons that need replacing", "Занятия, требующие переноса", "Yeniden yerleştirilecek dersler"
    ),
    "Məcburi dəyişiklik zamanı yerindən çıxarılan dərslər silinmir — buradan yeni xanaya qoyulur.": _e(
        "Lessons displaced by a forced change are not deleted — place them into a new cell from here.",
        "Занятия, снятые при принудительном изменении, не удаляются — поставьте их в новую ячейку отсюда.",
        "Zorunlu değişiklikte yerinden alınan dersler silinmez — buradan yeni bir hücreye yerleştirilir.",
    ),
    "Yenidən yerləşdiriləcək dərs yoxdur": _e(
        "No lesson needs replacing", "Нет занятий, требующих переноса", "Yeniden yerleştirilecek ders yok"
    ),
    "Məcburi dəyişiklik edilməyib — bütün dərslər öz yerindədir.": _e(
        "No forced change has been made — every lesson is in its place.",
        "Принудительных изменений не было — все занятия на своих местах.",
        "Zorunlu değişiklik yapılmadı — tüm dersler yerinde.",
    ),
    "Yerləşdirilməyib": _e("Not placed", "Не размещено", "Yerleştirilmedi"),
    "Əməliyyat yerinə yetirilmədi.": _e(
        "The action could not be completed.", "Действие не выполнено.", "İşlem gerçekleştirilemedi."
    ),
}


ENTRIES = {
    "registrar.schedule_grid": GRID,
    "registrar.schedule_conflicts": CONFLICTS,
    "registrar.schedule_editor": EDITOR,
    "accounts.schedule_editor": VIEW,
    "accounts.schedule_manage": PANEL,
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def existing_keys(text):
    """Kataloqdakı (msgctxt, msgid) cütləri — SƏTİRLƏRƏ BÖLÜNMÜŞ formada da.

    ⚠️ Sadə «probe in text» yoxlaması yetərli DEYİL: `msgmerge`/`makemessages`
    uzun msgid-ləri çox sətirli (`msgid ""` + davam sətirləri) formada yazır və
    tək sətirli axtarış onları görmür → təkrar giriş əlavə olunur, `msgfmt` isə
    «duplicate message definition» ilə qırılır (2026-09-09-da məhz belə oldu).
    """
    keys, ctx, field, buf = set(), "", None, []

    def flush():
        nonlocal ctx
        if field == "msgctxt":
            ctx = "".join(buf)
        elif field == "msgid":
            keys.add((ctx, "".join(buf)))

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            flush()
            ctx, field, buf = "", None, []
            continue
        for name in ("msgctxt", "msgid_plural", "msgid", "msgstr"):
            if stripped.startswith(name + " "):
                flush()
                if name == "msgctxt":
                    ctx = ""
                field, buf = name, [stripped[len(name) + 1 :].strip().strip('"')]
                break
        else:
            if field and stripped.startswith('"'):
                buf.append(stripped.strip('"'))
    flush()
    return {(c.replace('\\"', '"'), m.replace('\\"', '"')) for c, m in keys}


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    present = existing_keys(text)

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in present:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append('msgctxt "%s"\nmsgid "%s"\nmsgstr "%s"\n' % (esc(ctx), esc(msgid), esc(msgstr)))
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print("%s: +%d entry" % (lang, added))


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
