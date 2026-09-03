#!/usr/bin/env python3
"""EMSArena i18n — Dizayn Faza-5/6 (Stage-5/6) mətnləri (4 dil). İdempotent.

Mənbə: `docs/audits/2026-09-02/DESIGN_STAGE5_MSGIDS.txt` (sillabus qəbul
qaydaları — çəkilər, kontakt saat = plan, avto-MAJOR versiya, SLA siyasəti,
təsdiqlənmiş sillabus→jurnal mövzuları, commit `fbb629cd`) və
`DESIGN_STAGE6_MSGIDS.txt` (97 msgid, 8 kontekst — "Keçilmiş dərslər" bölməsi
+ tələbə kabineti deltaları, commit `ce626464`).

Yoxlama metodu (audit tələbi): `scripts/i18n_source_scan.py` HƏMİN skanerin
bilinən kor-nöqtəsi ilə (modul-səviyyəli `_CTX = "…"` dəyişəni ilə çağırılan
`pgettext(_CTX, …)` / `pgettext_lazy(_CTX, …)` cütlərini görmür — kontekst
arqumenti `ast.Name`-dir, `ast.Constant` deyil) + ƏL İLƏ AST gəzintisi
(modul-səviyyəli sabit təyinatlarını Name→str həll edən köməkçi skan) — hər
ikisinin BİRLƏŞMƏSİ AZ kataloqu ilə tutuşdurulub (`gap = source − catalog`).
Nəticə 10 kontekstdə YALNIZ bu iki commit-lə (fbb629cd/ce626464) əlaqəli
113 (=12+4+1+54+3+1+7+3+3+25) giriş verdi — say hər kontekst üzrə audit
sənədlərinin elan etdiyi ədədlərlə (accounts.syllabus 12, registrar.journal
4, accounts.dashboard 1, accounts.lessons_log 54, profile.results 3,
profile.sidebar 1, profile.subjects 7, profile.transcript 3,
registrar.journal_policy 3, registrar.lessons_log 25) TAM üst-üstə düşür.

⚠️ `profile.sidebar` kontekstində EYNİ faylda (`apps/accounts/views/profile/
   _sections/labels.py`) paralel Mərhələ-4 (dərs yükü) agentinin əlavə etdiyi
   4 YENİ çağırış da mənbədə var («Dərs yükü mərkəzi», «Yük təsdiqi», «Yük
   vizası», «Yük — ümumi baxış») — onlar bu skriptin ƏHATƏSİNDƏN QƏSDƏN
   KƏNARDIR (Stage-6 sənədinin öz qeydi: "profile.sidebar bölməsində paralel
   Mərhələ 4 agentinin 5 yazısı QƏSDƏN çıxarılıb"). `check_i18n_catalogs.py
   --report` işlədikdən sonra `source_missing` siyahısında yalnız bu 4 giriş
   qalmalıdır (Stage-4 WIP, ayrıca skriptdə doldurulacaq).

⚠️ DESIGN_STAGE5_MSGIDS.txt-də "DƏYİŞMİŞ msgid — köhnəsi kataloqdan
   ÇIXARILMALIDIR" bölməsi var (`10 gündən çox gözləyir` → `Eskalasiya
   həddini keçib`, `hədəf: 5 gündən az` → `hədəf: SLA çərçivəsində`,
   `Ən azı 15 simvol…` → `Ən azı 20 simvol…`, `Kursun mövzu siyahısı
   yoxdur…` → `Təsdiqlənmiş sillabus və kurs mövzu planı yoxdur…`). Bu
   skript YALNIZ ƏLAVƏ edir (aşağıya bax — append-only, paralel Mərhələ-4
   agenti EYNİ 4 `.po` faylını yaza bilər) — köhnə msgid-lər kataloqdan
   BURADA silinmir. Onlar artıq mənbədə çağırılmır, ona görə `source_missing`-i
   artırmırlar, sadəcə kataloqda ölü (istifadə olunmayan) qalırlar — təmizlik
   ayrıca (təhlükəsiz, təkbaşına) commit-də edilməlidir.

AZ: bütün msgid artıq Azərbaycanca UI mətnidir və heç bir kontekst model/
seçim/icazə etiketi DEYİL → `az_override` YOXDUR (identity: az msgstr == msgid).

⚠️ PARALEL AGENT TƏHLÜKƏSİZLİYİ (bax `i18n_fill_design_stage2_3.py`):
     * mövcudluq yoxlaması `polib` ilə (bax `existing_pairs`);
     * YAZMADAN DƏRHAL ƏVVƏL fayl YENİDƏN oxunur (`fill()` daxilində);
     * yazma xam mətn ƏLAVƏSİ ilə — `polib.save()` İŞLƏDİLMİR. Yalnız
       ƏLAVƏ olunur — mövcud sətirlərə TOXUNULMUR, fuzzy flag-lar
       dəyişdirilmir.

⚠️ `makemessages` İŞLƏDİLMİR (əl ilə yazılmış blokları silə bilər).

İstifadə:  python scripts/i18n_fill_design_stage5_6.py
Sonra:     django-admin compilemessages && python scripts/check_i18n_catalogs.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def _e(en, ru, tr):
    return {"en": en, "ru": ru, "tr": tr}


# ─────────────────────────────────────────────────────────────────────────────
# accounts.syllabus — qəbul siyasəti (çəkilər, avto-MAJOR, SLA) — Stage 5
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_SYLLABUS = {
    "Sərbəst bölünən %(need)s bal tam paylanmayıb (hazırda %(have)s) — cəm 100 olmalıdır": _e(
        "The freely-distributed %(need)s points have not been fully allocated (currently %(have)s) — "
        "the total must be 100",
        "Свободно распределяемые %(need)s баллов распределены не полностью (сейчас %(have)s) — "
        "сумма должна быть 100",
        "Serbest dağıtılan %(need)s puan tam dağıtılmamış (şu anda %(have)s) — toplam 100 olmalı",
    ),
    "Qiymətləndirmə çəkisi mənfi ola bilməz": _e(
        "The assessment weight cannot be negative",
        "Вес оценивания не может быть отрицательным",
        "Değerlendirme ağırlığı negatif olamaz",
    ),
    "Qiymətləndirmə bölgüsü siyasətə uyğun deyil: sərbəst bölünən %(need)s bal tam paylanmalıdır.": _e(
        "The assessment breakdown does not comply with policy: the freely-distributed %(need)s "
        "points must be fully allocated.",
        "Распределение оценивания не соответствует политике: свободно распределяемые %(need)s "
        "баллов должны быть распределены полностью.",
        "Değerlendirme dağılımı politikaya uygun değil: serbest dağıtılan %(need)s puan tam " "olarak dağıtılmalıdır.",
    ),
    "Mövzu, çəki və ya struktur dəyişdiyi üçün versiya avtomatik BÖYÜK versiyaya qaldırıldı — "
    "dəyişiklik növbəti semestrdən qüvvəyə minir.": _e(
        "Because the topic, weight, or structure changed, the version was automatically bumped to "
        "a MAJOR version — the change takes effect from the next semester.",
        "Поскольку тема, вес или структура изменились, версия была автоматически повышена до "
        "ГЛАВНОЙ версии — изменение вступает в силу со следующего семестра.",
        "Konu, ağırlık veya yapı değiştiği için sürüm otomatik olarak BÜYÜK sürüme yükseltildi — "
        "değişiklik bir sonraki dönemden itibaren geçerli olur.",
    ),
    "SLA-nı keçib": _e("Past SLA", "Просрочено по SLA", "SLA'yı aştı"),
    "%(days)s gündən çox kafedra növbəsindədir": _e(
        "Has been waiting on the department for more than %(days)s days",
        "Уже более %(days)s дней ожидает на кафедре",
        "%(days)s günden fazladır bölüm sırasında bekliyor",
    ),
    "%(days)s gündür gözləyir — SLA %(sla)s gün": _e(
        "Waiting for %(days)s days — SLA %(sla)s days",
        "Ожидает %(days)s дней — SLA %(sla)s дней",
        "%(days)s gündür bekliyor — SLA %(sla)s gün",
    ),
    "%(days)s gündən çox gözləyir": _e(
        "Waiting for more than %(days)s days",
        "Ожидает более %(days)s дней",
        "%(days)s günden fazla bekliyor",
    ),
    "Eskalasiya həddini keçib": _e(
        "Past the escalation threshold", "Превышен порог эскалации", "Eskalasyon eşiğini aştı"
    ),
    "hədəf: SLA çərçivəsində": _e("target: within SLA", "цель: в рамках SLA", "hedef: SLA çerçevesinde"),
    "Ən azı 20 simvol — səbəb audit izinə yazılır.": _e(
        "At least 20 characters — the reason is recorded in the audit trail.",
        "Не менее 20 символов — причина записывается в журнал аудита.",
        "En az 20 karakter — gerekçe denetim izine yazılır.",
    ),
    "Ən azı 20 simvol — səbəb məcburidir.": _e(
        "At least 20 characters — the reason is mandatory.",
        "Не менее 20 символов — причина обязательна.",
        "En az 20 karakter — gerekçe zorunludur.",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# registrar.journal — dərs modalı: mövzu mənbəyi sillabusa keçdi — Stage 5
# ─────────────────────────────────────────────────────────────────────────────
REGISTRAR_JOURNAL = {
    "mühazirə": _e("lecture", "лекция", "teorik ders"),
    "seminar": _e("seminar", "семинар", "seminer"),
    "laboratoriya": _e("laboratory", "лаборатория", "laboratuvar"),
    "Təsdiqlənmiş sillabus və kurs mövzu planı yoxdur — mövzunu əl ilə yazın.": _e(
        "There is no approved syllabus or course topic plan — enter the topic manually.",
        "Нет утверждённого силлабуса или плана тем курса — введите тему вручную.",
        "Onaylanmış sillabus veya ders konu planı yok — konuyu elle yazın.",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.dashboard — Stage 6 (tələbə kabineti dashboard vidjeti)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_DASHBOARD = {
    "Bu gün / növbəti dərslər": _e(
        "Today / upcoming lessons", "Сегодня / ближайшие занятия", "Bugün / sonraki dersler"
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.lessons_log — ekran 21 «Keçilmiş dərslər» bölməsi — Stage 6
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_LESSONS_LOG = {
    "Aktiv təşkilat konteksti yoxdur": _e(
        "There is no active organization context",
        "Нет активного контекста организации",
        "Aktif kurum bağlamı yok",
    ),
    "Auditoriya saatı": _e("Contact hours", "Аудиторные часы", "Sınıf saati"),
    "Axtarış": _e("Search", "Поиск", "Ara"),
    "Bazar": _e("Sunday", "Воскресенье", "Pazar"),
    "Bazar ertəsi": _e("Monday", "Понедельник", "Pazartesi"),
    "Bütün fənlər": _e("All subjects", "Все дисциплины", "Tüm dersler"),
    "Bütün müəllimlər": _e("All teachers", "Все преподаватели", "Tüm öğretmenler"),
    "Bütün qruplar": _e("All groups", "Все группы", "Tüm gruplar"),
    "Bütün tiplər": _e("All types", "Все типы", "Tüm türler"),
    "Cümə": _e("Friday", "Пятница", "Cuma"),
    "Cümə axşamı": _e("Thursday", "Четверг", "Perşembe"),
    "Dövr": _e("Period", "Период", "Dönem"),
    "Dövrü genişləndirin və ya filtrləri sıfırlayın.": _e(
        "Widen the period or reset the filters.",
        "Расширьте период или сбросьте фильтры.",
        "Dönemi genişletin veya filtreleri sıfırlayın.",
    ),
    "Dərs əlavə et": _e("Add a lesson", "Добавить занятие", "Ders ekle"),
    "Dərsin tipi": _e("Lesson type", "Тип занятия", "Ders türü"),
    "Elektron jurnal": _e("Electronic journal", "Электронный журнал", "Elektronik jurnal"),
    "Fənn": _e("Subject", "Дисциплина", "Ders"),
    "Fənn və qrup": _e("Subject and group", "Дисциплина и группа", "Ders ve grup"),
    "Gec yazılan qeyd": _e("Late entry", "Поздняя запись", "Geç girilen kayıt"),
    "Hesabatı yüklə": _e("Download the report", "Скачать отчёт", "Raporu indir"),
    "Jurnal qeydi": _e("Journal entry", "Запись в журнале", "Jurnal kaydı"),
    "Jurnalı aç": _e("Open the journal", "Открыть журнал", "Jurnalı aç"),
    "Jurnalı boş dərs": _e("Lesson with an empty journal", "Занятие с пустым журналом", "Jurnalı boş ders"),
    "Kafedranın müəllimləri hansı dərsi, hansı qrupa, hansı mövzu ilə keçib. Jurnalı vaxtında "
    "doldurulmayan dərslər ayrıca işarələnir.": _e(
        "Which lesson the department's teachers taught, to which group, with which topic. Lessons "
        "whose journal was not filled in on time are marked separately.",
        "Какое занятие преподаватели кафедры провели, для какой группы, по какой теме. Занятия, "
        "журнал которых не был заполнен вовремя, отмечаются отдельно.",
        "Bölümün öğretmenlerinin hangi dersi, hangi gruba, hangi konuyla işlediği. Jurnalı "
        "zamanında doldurulmayan dersler ayrıca işaretlenir.",
    ),
    "Keçdiyiniz dərslərin qeydi — hansı qrupa, hansı mövzunu, neçə saat. Dövrü dəyişib istənilən "
    "aralığa baxa bilərsiniz.": _e(
        "A record of the lessons you taught — which group, which topic, how many hours. You can "
        "change the period to view any range.",
        "Запись проведённых вами занятий — какой группе, какую тему, сколько часов. Вы можете "
        "изменить период, чтобы посмотреть любой диапазон.",
        "İşlediğiniz derslerin kaydı — hangi gruba, hangi konuyu, kaç saat. Dönemi değiştirerek "
        "istediğiniz aralığa bakabilirsiniz.",
    ),
    "Keçilmiş dərs": _e("Lesson held", "Проведённое занятие", "İşlenen ders"),
    "Keçilən mövzu": _e("Topic covered", "Пройденная тема", "İşlenen konu"),
    "Mövzu yazılmayıb": _e("No topic entered", "Тема не указана", "Konu yazılmamış"),
    "Mövzu, fənn və ya qrup axtar": _e(
        "Search by topic, subject, or group",
        "Поиск по теме, дисциплине или группе",
        "Konu, ders veya gruba göre ara",
    ),
    "Müəllim": _e("Teacher", "Преподаватель", "Öğretmen"),
    "Orta iştirak": _e("Average attendance", "Средняя посещаемость", "Ortalama katılım"),
    "Qrup": _e("Group", "Группа", "Grup"),
    "Saat": _e("Hour", "Час", "Saat"),
    "Semestr": _e("Semester", "Семестр", "Dönem"),
    "Seçilmiş dövrdə dərs qeydi yoxdur": _e(
        "There are no lesson entries for the selected period",
        "За выбранный период нет записей занятий",
        "Seçilen dönemde ders kaydı yok",
    ),
    "Sillabus mövzu əhatəsi": _e("Syllabus topic coverage", "Охват тем силлабуса", "Sillabus konu kapsamı"),
    "Təsdiqlənmiş sillabus yoxdur": _e(
        "No approved syllabus", "Нет утверждённого силлабуса", "Onaylanmış sillabus yok"
    ),
    "Təşkilat seçin və ya administratora müraciət edin.": _e(
        "Select an organization or contact the administrator.",
        "Выберите организацию или обратитесь к администратору.",
        "Bir kurum seçin veya yöneticinize başvurun.",
    ),
    "akademik saat cəmi": _e("total contact hours", "всего академических часов", "toplam akademik saat"),
    "dərs": _e("lesson", "занятие", "ders"),
    "dərsdən 48 saat sonra": _e("48 hours after the lesson", "через 48 часов после занятия", "dersten 48 saat sonra"),
    "dərsə gələn tələbə payı": _e(
        "share of students who attended the lesson",
        "доля студентов, посетивших занятие",
        "derse gelen öğrenci payı",
    ),
    "gecikmə yoxdur": _e("no delay", "без задержки", "gecikme yok"),
    "hamısı doldurulub": _e("all filled in", "все заполнено", "hepsi dolduruldu"),
    "mövzu": _e("topic", "тема", "konu"),
    "mövzu və qiymət yazılmayıb": _e(
        "topic and grade not entered", "тема и оценка не указаны", "konu ve not yazılmamış"
    ),
    "saat": _e("hour", "час", "saat"),
    "seçilmiş dövrdə": _e("in the selected period", "за выбранный период", "seçilen dönemde"),
    "Çərşənbə": _e("Wednesday", "Среда", "Çarşamba"),
    "Çərşənbə axşamı": _e("Tuesday", "Вторник", "Salı"),
    "Üzrlü qayıb": _e("Excused absence", "Уважительный пропуск", "Mazeretli devamsızlık"),
    "İlk %(cap)s dərs göstərilir — cəmi %(total)s qeyd var. Daha dar dövr seçin və ya hesabatı "
    "yükləyin.": _e(
        "The first %(cap)s lessons are shown — there are %(total)s entries in total. Choose a "
        "narrower period or download the report.",
        "Показаны первые %(cap)s занятий — всего %(total)s записей. Выберите более узкий период " "или скачайте отчёт.",
        "İlk %(cap)s ders gösteriliyor — toplam %(total)s kayıt var. Daha dar bir dönem seçin veya " "raporu indirin.",
    ),
    "İştirak": _e("Attendance", "Посещаемость", "Katılım"),
    "Şənbə": _e("Saturday", "Суббота", "Cumartesi"),
}

# ─────────────────────────────────────────────────────────────────────────────
# profile.results — «Rəsmi transkript» CTA (Stage 6)
# ─────────────────────────────────────────────────────────────────────────────
PROFILE_RESULTS = {
    "Bu səhifə qeyri-rəsmi baxış nüsxəsidir. Möhürlü transkript Tələbə Xidmətləri Mərkəzinə "
    "müraciət əsasında verilir — orta cavab müddəti 3 iş günü.": _e(
        "This page is an unofficial preview copy. A sealed transcript is issued upon request to "
        "the Student Services Center — average response time 3 business days.",
        "Эта страница является неофициальной предварительной копией. Заверенный печатью "
        "транскрипт выдаётся по заявке в Центр обслуживания студентов — среднее время ответа "
        "3 рабочих дня.",
        "Bu sayfa gayriresmi bir önizleme kopyasıdır. Mühürlü transkript, Öğrenci Hizmetleri "
        "Merkezi'ne başvuru üzerine verilir — ortalama yanıt süresi 3 iş günü.",
    ),
    "Rəsmi transkript": _e("Official transcript", "Официальный транскрипт", "Resmi transkript"),
    "Transkript sorğusu göndər": _e(
        "Send a transcript request", "Отправить запрос на транскрипт", "Transkript talebi gönder"
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# profile.sidebar — YALNIZ «Keçilmiş dərslər» (Stage 6). DİQQƏT: eyni
# kontekstdə paralel Mərhələ-4 agentinin 4 yazısı QƏSDƏN buraxılıb (bax
# modul başlığı).
# ─────────────────────────────────────────────────────────────────────────────
PROFILE_SIDEBAR = {
    "Keçilmiş dərslər": _e("Lessons held", "Проведённые занятия", "İşlenen dersler"),
}

# ─────────────────────────────────────────────────────────────────────────────
# profile.subjects — qiymətləndirmə strukturu çəkiləri (Stage 6)
# ─────────────────────────────────────────────────────────────────────────────
PROFILE_SUBJECTS = {
    "Cari qiymətləndirmə": _e("Current assessment", "Текущее оценивание", "Güncel değerlendirme"),
    "Cəmi": _e("Total", "Всего", "Toplam"),
    "Davamiyyət": _e("Attendance", "Посещаемость", "Devam"),
    "Qiymətləndirmə strukturu": _e("Assessment structure", "Структура оценивания", "Değerlendirme yapısı"),
    "Sillabus (təsdiqlənmiş)": _e("Syllabus (approved)", "Силлабус (утверждён)", "Sillabus (onaylı)"),
    "Sərbəst iş": _e("Independent work", "Самостоятельная работа", "Serbest çalışma"),
    "Yekun imtahan": _e("Final exam", "Итоговый экзамен", "Final sınavı"),
}

# ─────────────────────────────────────────────────────────────────────────────
# profile.transcript — rəsmi transkript sorğusu CTA (Stage 6)
# ─────────────────────────────────────────────────────────────────────────────
PROFILE_TRANSCRIPT = {
    "Bu səhifə qeyri-rəsmi baxış nüsxəsidir. Möhürlü/imzalı rəsmi transkript Tələbə Xidmətləri "
    "Mərkəzinə müraciət əsasında verilir — orta cavab müddəti 3 iş günü.": _e(
        "This page is an unofficial preview copy. A sealed/signed official transcript is issued "
        "upon request to the Student Services Center — average response time 3 business days.",
        "Эта страница является неофициальной предварительной копией. Официальный транскрипт с "
        "печатью/подписью выдаётся по заявке в Центр обслуживания студентов — среднее время "
        "ответа 3 рабочих дня.",
        "Bu sayfa gayriresmi bir önizleme kopyasıdır. Mühürlü/imzalı resmi transkript, Öğrenci "
        "Hizmetleri Merkezi'ne başvuru üzerine verilir — ortalama yanıt süresi 3 iş günü.",
    ),
    "Rəsmi transkript Tələbə Xidmətləri Mərkəzindən sorğu ilə verilir (3 iş günü).": _e(
        "The official transcript is issued by the Student Services Center upon request " "(3 business days).",
        "Официальный транскрипт выдаётся Центром обслуживания студентов по заявке " "(3 рабочих дня).",
        "Resmi transkript, Öğrenci Hizmetleri Merkezi tarafından talep üzerine verilir " "(3 iş günü).",
    ),
    "Transkript sorğusu göndər": _e(
        "Send a transcript request", "Отправить запрос на транскрипт", "Transkript talebi gönder"
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# registrar.journal_policy — jurnal kilidi (təsdiqlənmiş sillabus tələbi) — Stage 6
# ─────────────────────────────────────────────────────────────────────────────
REGISTRAR_JOURNAL_POLICY = {
    "Jurnal təsdiqlənmiş sillabus olmadan açılmır": _e(
        "The journal cannot be opened without an approved syllabus",
        "Журнал не открывается без утверждённого силлабуса",
        "Jurnal, onaylanmış bir sillabus olmadan açılmaz",
    ),
    "Sillabusa keç": _e("Go to the syllabus", "Перейти к силлабусу", "Sillabusa git"),
    "Universitet siyasətinə görə dərs sətri yalnız təsdiqlənmiş sillabusdan yaradılır: mövzu, "
    "saat bölgüsü və qiymətləndirmə strukturu oradan gəlir. Jurnal yalnız oxunuş rejimindədir — "
    "sillabusu tamamlayıb kafedra müdirinin təsdiqinə göndərin.": _e(
        "Under university policy, a lesson row is created only from an approved syllabus: the "
        "topic, hour breakdown, and assessment structure come from it. The journal is read-only "
        "— complete the syllabus and send it for the department head's approval.",
        "Согласно политике университета, строка занятия создаётся только из утверждённого "
        "силлабуса: тема, распределение часов и структура оценивания берутся из него. Журнал "
        "доступен только для чтения — завершите силлабус и отправьте его на утверждение "
        "заведующему кафедрой.",
        "Üniversite politikasına göre ders satırı yalnızca onaylanmış bir sillabustan "
        "oluşturulur: konu, saat dağılımı ve değerlendirme yapısı oradan gelir. Jurnal yalnızca "
        "salt okunur durumdadır — sillabusu tamamlayıp bölüm başkanının onayına gönderin.",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# registrar.lessons_log — kafedra/RİM «Keçilmiş dərslər» cədvəli (Stage 6)
# ─────────────────────────────────────────────────────────────────────────────
REGISTRAR_LESSONS_LOG = {
    "Akademik saat": _e("Academic hour", "Академический час", "Akademik saat"),
    "Bu ay": _e("This month", "Этот месяц", "Bu ay"),
    "Bu gün": _e("Today", "Сегодня", "Bugün"),
    "Bu həftə": _e("This week", "Эта неделя", "Bu hafta"),
    "Dövr": _e("Period", "Период", "Dönem"),
    "Dərsin tipi": _e("Lesson type", "Тип занятия", "Ders türü"),
    "Fənn": _e("Subject", "Дисциплина", "Ders"),
    "Fənn kodu": _e("Subject code", "Код дисциплины", "Ders kodu"),
    "Gec yazılıb": _e("Recorded late", "Записано с опозданием", "Geç kaydedildi"),
    "Jurnal boşdur": _e("Journal is empty", "Журнал пуст", "Jurnal boş"),
    "Jurnal qeydi": _e("Journal entry", "Запись в журнале", "Jurnal kaydı"),
    "Mövzu": _e("Topic", "Тема", "Konu"),
    "Müəllim": _e("Teacher", "Преподаватель", "Öğretmen"),
    "Otaq": _e("Room", "Аудитория", "Oda"),
    "Qayıb": _e("Absence", "Пропуск", "Devamsızlık"),
    "Qiymətləndirilib": _e("Graded", "Оценено", "Değerlendirildi"),
    "Qrup": _e("Group", "Группа", "Grup"),
    "Saat": _e("Hour", "Час", "Saat"),
    "Semestr": _e("Semester", "Семестр", "Dönem"),
    "Seçilmiş aralıq": _e("Selected range", "Выбранный диапазон", "Seçilen aralık"),
    "Tarix": _e("Date", "Дата", "Tarih"),
    "Vaxtında yazılıb": _e("Recorded on time", "Записано вовремя", "Zamanında kaydedildi"),
    "Üzrlü": _e("Excused", "Уважительная", "Mazeretli"),
    "İl": _e("Year", "Год", "Yıl"),
    "İştirak": _e("Attendance", "Посещаемость", "Katılım"),
}

ENTRIES = {
    "accounts.syllabus": ACCOUNTS_SYLLABUS,
    "registrar.journal": REGISTRAR_JOURNAL,
    "accounts.dashboard": ACCOUNTS_DASHBOARD,
    "accounts.lessons_log": ACCOUNTS_LESSONS_LOG,
    "profile.results": PROFILE_RESULTS,
    "profile.sidebar": PROFILE_SIDEBAR,
    "profile.subjects": PROFILE_SUBJECTS,
    "profile.transcript": PROFILE_TRANSCRIPT,
    "registrar.journal_policy": REGISTRAR_JOURNAL_POLICY,
    "registrar.lessons_log": REGISTRAR_LESSONS_LOG,
}

#: Bu Stage-də heç bir kontekst model/seçim/icazə etiketi deyil → AZ hər yerdə identity.
AZ_OVERRIDES: dict = {}

_expected_total = 113
_actual_total = sum(len(v) for v in ENTRIES.values())
assert _actual_total == _expected_total, f"Gözlənilən {_expected_total}, tapılan {_actual_total}"


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def existing_pairs(lang):
    """`polib` ilə mövcudluq yoxlaması (bax modul başlığı — YAZMA üçün deyil)."""
    import polib

    return {(e.msgctxt or "", e.msgid) for e in polib.pofile(po_path(lang)) if not e.obsolete}


def fill(lang):
    path = po_path(lang)
    existing = existing_pairs(lang)

    # Yazmadan DƏRHAL ƏVVƏL fayl yenidən oxunur — paralel agentin bu arada
    # etdiyi əlavələr itirilməsin.
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        overrides = AZ_OVERRIDES.get(ctx, {})
        for msgid, translations in messages.items():
            key = (ctx, msgid)
            if key in existing:
                continue
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            if lang == "az":
                msgstr = overrides.get(msgid, msgid)
            else:
                msgstr = translations[lang]
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
