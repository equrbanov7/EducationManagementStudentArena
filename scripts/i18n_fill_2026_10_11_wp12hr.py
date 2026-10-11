#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-11 (WP12): «Kadr analitikası» (İnsan resursları) mətnləri.

Əlavə olunan mətnlər:
  * `accounts.hr_analytics`: bölmə paneli, tablar, filtrlər, KPI, cədvəl başlıqları, problem adları, Excel ixracı;
  * `profile.sidebar`: «Kadr analitikası» (menyu + bölmə başlığı);
  * `organizations.permission.label`: `people.hr_analytics` açarının etiketi (icazə redaktoru).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_11_wp12hr.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


HR = "accounts.hr_analytics"
PSB = "profile.sidebar"
PERM = "organizations.permission.label"

_HR = [
    _t(
        "%(year)s tədris ili · göstərilir: %(shown)s / %(total)s müəllim",
        "Academic year %(year)s · showing %(shown)s of %(total)s teachers",
        "Учебный год %(year)s · показано: %(shown)s из %(total)s преподавателей",
        "%(year)s öğretim yılı · gösterilen: %(shown)s / %(total)s öğretim elemanı",
    ),
    _t("0,5 ştat", "0.5 position", "0,5 ставки", "0,5 kadro"),
    _t("Ad Soyad Ata adı", "Full name", "ФИО", "Ad Soyad Baba adı"),
    _t(
        "Ad, soyad, istifadəçi adı, kafedra…",
        "Name, surname, username, department…",
        "Имя, фамилия, логин, кафедра…",
        "Ad, soyad, kullanıcı adı, bölüm…",
    ),
    _t("Aktiv", "Active", "Активен", "Aktif"),
    _t("Aktiv hesab", "Active accounts", "Активные учётные записи", "Aktif hesap"),
    _t("Aktivləşdirilməyib", "Not activated", "Не активирован", "Etkinleştirilmedi"),
    _t("Arxiv", "Archived", "Архив", "Arşiv"),
    _t("Axtarış", "Search", "Поиск", "Arama"),
    _t("Az yüklü (<70%)", "Underloaded (<70%)", "Недогружен (<70%)", "Az yüklü (<%70)"),
    _t("Belə müəllim yoxdur.", "No such teachers.", "Таких преподавателей нет.", "Böyle öğretim elemanı yok."),
    _t("Bu il yeni", "New this year", "Новые в этом году", "Bu yıl yeni"),
    _t(
        "Bu tədris ili üçün müəllim tapılmadı",
        "No teachers found for this academic year",
        "Для этого учебного года преподаватели не найдены",
        "Bu öğretim yılı için öğretim elemanı bulunamadı",
    ),
    _t(
        "Bölgü üzrə illik yük / norma.",
        "Distributed annual load / norm.",
        "Распределённая годовая нагрузка / норма.",
        "Dağıtılan yıllık yük / norm.",
    ),
    _t("Bölgü üzrə yük (saat)", "Distributed load (hours)", "Распределённая нагрузка (ч)", "Dağıtılan yük (saat)"),
    _t("Bütün müəllimlər", "All teachers", "Все преподаватели", "Tüm öğretim elemanları"),
    _t("Bəli", "Yes", "Да", "Evet"),
    _t("Cins", "Gender", "Пол", "Cinsiyet"),
    _t("Cəmi", "Total", "Итого", "Toplam"),
    _t(
        "Cəmi ştat vahidi: %(units)s",
        "Total staff units: %(units)s",
        "Всего ставок: %(units)s",
        "Toplam kadro birimi: %(units)s",
    ),
    _t("Dayandırılıb", "Suspended", "Приостановлен", "Askıya alındı"),
    _t("Digər pay", "Other fraction", "Другая доля", "Diğer pay"),
    _t("Doluluq", "Fill", "Заполненность", "Doluluk"),
    _t("Doluluq %", "Fill %", "Заполненность, %", "Doluluk %"),
    _t(
        "Doğum tarixi bilinməyən: %(unknown)s",
        "Unknown date of birth: %(unknown)s",
        "Дата рождения неизвестна: %(unknown)s",
        "Doğum tarihi bilinmeyen: %(unknown)s",
    ),
    _t("Dərs", "Lessons", "Занятия", "Ders"),
    _t("Dərs deyən", "Teaching", "Ведут занятия", "Ders veren"),
    _t("Dərs yükü", "Teaching load", "Учебная нагрузка", "Ders yükü"),
    _t("Dərs yükü doluluğu", "Teaching load fill", "Заполненность нагрузки", "Ders yükü doluluğu"),
    _t("Elmi ad / vəzifə", "Academic title / position", "Учёное звание / должность", "Akademik unvan / görev"),
    _t("Elmi ad · dərəcə", "Title · degree", "Звание · степень", "Unvan · derece"),
    _t(
        "Elmi adı / vəzifəsi yoxdur",
        "No academic title / position",
        "Нет звания / должности",
        "Akademik unvanı / görevi yok",
    ),
    _t("Elmi dərəcə", "Academic degree", "Учёная степень", "Akademik derece"),
    _t("Elmi dərəcəli", "With a degree", "Со степенью", "Dereceli"),
    _t("Elmi dərəcəli %", "With a degree, %", "Со степенью, %", "Dereceli %"),
    _t(
        "Elmi dərəcəsi qeyd olunmayıb",
        "No academic degree recorded",
        "Учёная степень не указана",
        "Akademik derece kaydedilmemiş",
    ),
    _t("Elmlər doktoru", "Doctor of Sciences", "Доктор наук", "Bilim doktoru"),
    _t("Excel-ə ixrac", "Export to Excel", "Экспорт в Excel", "Excel'e aktar"),
    _t(
        "Eyni ad-soyadlı hesablar",
        "Accounts with the same full name",
        "Учётные записи с одинаковым ФИО",
        "Aynı ad-soyadlı hesaplar",
    ),
    _t("Fakültə", "Faculty", "Факультет", "Fakülte"),
    _t(
        "Fakültə və kafedralar üzrə ştat vahidləri",
        "Staff units by faculty and department",
        "Ставки по факультетам и кафедрам",
        "Fakülte ve bölümlere göre kadro birimleri",
    ),
    _t("Fakültə · kafedra", "Faculty · department", "Факультет · кафедра", "Fakülte · bölüm"),
    _t("Fakültə üzrə", "Faculty total", "По факультету", "Fakülte toplamı"),
    _t("Fakültəsiz", "No faculty", "Без факультета", "Fakültesiz"),
    _t(
        "Filtrə uyğun müəllim yoxdur.",
        "No teachers match the filters.",
        "Нет преподавателей, соответствующих фильтрам.",
        "Filtreye uyan öğretim elemanı yok.",
    ),
    _t("Hamısı", "All", "Все", "Tümü"),
    _t("Hesab", "Account", "Учётная запись", "Hesap"),
    _t("Hesab statusu", "Account status", "Статус учётной записи", "Hesap durumu"),
    _t(
        "Heyət aktiv müəllim üzvlüyündən və ya seçilmiş ilin dərs yükü profilindən (ştat vahidi) yığılır. Başqa il seçin və ya müəllim siyahısını idxal edin.",
        "Staff are collected from active teacher memberships or from the selected year's workload profiles (staff units). Choose another year or import the teacher list.",
        "Состав формируется из активных членств преподавателей или профилей нагрузки выбранного года (ставки). Выберите другой год или импортируйте список преподавателей.",
        "Kadro, aktif öğretim elemanı üyeliklerinden veya seçilen yılın ders yükü profillerinden (kadro birimi) oluşturulur. Başka bir yıl seçin veya öğretim elemanı listesini içe aktarın.",
    ),
    _t("Heç daxil olmayıb", "Never signed in", "Ни разу не входил", "Hiç giriş yapmadı"),
    _t("Həddən artıq (>120%)", "Overloaded (>120%)", "Перегружен (>120%)", "Aşırı yüklü (>%120)"),
    _t("Jurnal", "Journals", "Журналы", "Yoklama defteri"),
    _t("Jurnal / dərs", "Journals / lessons", "Журналы / занятия", "Defter / ders"),
    _t(
        "Jurnal — müəllimin seçilmiş tədris ilindəki aktiv fənn açılışı; keçirilmiş saat — jurnala yazılmış dərslərin cəmi; plan — jurnalın semestr kontakt saatı. Cari semestrdə icra faizinin aşağı olması normaldır.",
        "Journal — the teacher's active course offering in the selected academic year; hours held — total of the lessons recorded in the journal; plan — the journal's semester contact hours. A low completion rate during the current semester is normal.",
        "Журнал — активный курс преподавателя в выбранном учебном году; проведённые часы — сумма занятий, записанных в журнал; план — контактные часы семестра по журналу. Низкий процент выполнения в текущем семестре — это нормально.",
        "Defter — öğretim elemanının seçilen öğretim yılındaki aktif ders açılışı; yapılan saat — deftere yazılan derslerin toplamı; plan — defterin dönem temas saati. Mevcut dönemde gerçekleşme oranının düşük olması normaldir.",
    ),
    _t(
        "Kadr analitikası bölmələri",
        "HR analytics sections",
        "Разделы кадровой аналитики",
        "Personel analitiği bölümleri",
    ),
    _t(
        "Kadr analitikası filtrləri",
        "HR analytics filters",
        "Фильтры кадровой аналитики",
        "Personel analitiği filtreleri",
    ),
    _t(
        "Kadr analitikası İnsan resursları, rektor, RİM rəhbəri və superadmin üçündür.",
        "HR analytics is available to Human Resources, the rector, the RİM head and superadmins.",
        "Кадровая аналитика доступна отделу кадров, ректору, руководителю RİM и суперадминистратору.",
        "Personel analitiği İnsan Kaynakları, rektör, RİM başkanı ve süper yönetici içindir.",
    ),
    _t(
        "Kadr analitikasının ixracı",
        "HR analytics export",
        "Экспорт кадровой аналитики",
        "Personel analitiği dışa aktarımı",
    ),
    _t(
        "Kadr məlumatındakı boşluqlar. «Siyahıya bax» həmin problemi olan müəllimləri «Müəllimlər» tabında açır. Elmi dərəcənin olmaması səhv deyil — yalnız qeydin tamlığını göstərir.",
        "Gaps in the staff records. “View list” opens the teachers with that issue in the “Teachers” tab. A missing academic degree is not an error — it only shows how complete the records are.",
        "Пробелы в кадровых данных. «Показать список» открывает преподавателей с этой проблемой на вкладке «Преподаватели». Отсутствие учёной степени — не ошибка, а лишь показатель полноты данных.",
        "Personel kayıtlarındaki eksikler. «Listeyi gör», bu sorunu olan öğretim elemanlarını «Öğretim elemanları» sekmesinde açar. Akademik derecenin olmaması hata değildir — yalnızca kaydın eksiksizliğini gösterir.",
    ),
    _t("Kafedra", "Department", "Кафедра", "Bölüm"),
    _t("Kafedralar üzrə dərs yükü", "Teaching load by department", "Нагрузка по кафедрам", "Bölümlere göre ders yükü"),
    _t(
        "Kafedralar üzrə elmi ad və dərəcə",
        "Academic titles and degrees by department",
        "Звания и степени по кафедрам",
        "Bölümlere göre akademik unvan ve derece",
    ),
    _t(
        "Kafedralar üzrə tədris fəaliyyəti",
        "Teaching activity by department",
        "Учебная деятельность по кафедрам",
        "Bölümlere göre öğretim faaliyeti",
    ),
    _t("Kafedrasız", "No department", "Без кафедры", "Bölümsüz"),
    _t("Kafedraya bağlı deyil", "Not assigned to a department", "Не привязан к кафедре", "Bir bölüme bağlı değil"),
    _t("Keçirilmiş dərs", "Lessons held", "Проведённые занятия", "Yapılan ders"),
    _t("Keçirilmiş saat", "Hours held", "Проведённые часы", "Yapılan saat"),
    _t("Kişi", "Male", "Мужчины", "Erkek"),
    _t("Müəllim", "Teachers", "Преподаватели", "Öğretim elemanı"),
    _t(
        "Müəllim heyəti haqqında bütün göstəricilər: say və hesab vəziyyəti, ştat vahidləri, elmi ad və dərəcə, dərs yükü, tədris fəaliyyəti və məlumat boşluqları. Filtrlər bütün tablara tətbiq olunur; ixrac cari filtr dəstini Excel-ə çıxarır.",
        "All indicators for the teaching staff: headcount and account status, staff units, academic titles and degrees, teaching load, teaching activity and data gaps. Filters apply to every tab; the export writes the current filter set to Excel.",
        "Все показатели профессорско-преподавательского состава: численность и статус учётных записей, ставки, учёные звания и степени, нагрузка, учебная деятельность и пробелы в данных. Фильтры применяются ко всем вкладкам; экспорт выгружает текущий набор фильтров в Excel.",
        "Öğretim kadrosuna ilişkin tüm göstergeler: sayı ve hesap durumu, kadro birimleri, akademik unvan ve derece, ders yükü, öğretim faaliyeti ve veri eksikleri. Filtreler tüm sekmelere uygulanır; dışa aktarım mevcut filtre kümesini Excel'e aktarır.",
    ),
    _t("Müəllimlər", "Teachers", "Преподаватели", "Öğretim elemanları"),
    _t("Müəllimlər siyahısı", "Teacher list", "Список преподавателей", "Öğretim elemanı listesi"),
    _t("Məlumat boşluqları", "Data gaps", "Пробелы в данных", "Veri eksikleri"),
    _t("Məlumat keyfiyyəti", "Data quality", "Качество данных", "Veri kalitesi"),
    _t("Norma", "Norm", "Норма", "Norm"),
    _t("Norma (saat)", "Norm (hours)", "Норма (ч)", "Norm (saat)"),
    _t("Normal (70–100%)", "Normal (70–100%)", "Норма (70–100%)", "Normal (%70–100)"),
    _t("Növbəti", "Next", "Далее", "Sonraki"),
    _t("Plan saat", "Planned hours", "Плановые часы", "Plan saat"),
    _t("Plan saat (jurnal)", "Planned hours (journal)", "Плановые часы (журнал)", "Plan saat (defter)"),
    _t("Problem", "Issue", "Проблема", "Sorun"),
    _t("Problem tapılmadı.", "No issues found.", "Проблем не найдено.", "Sorun bulunamadı."),
    _t("Problem yoxdur.", "No issues.", "Проблем нет.", "Sorun yok."),
    _t("Problemlər", "Issues", "Проблемы", "Sorunlar"),
    _t(
        "Profil sahəsi; boşdursa yük profilindəki vəzifə.",
        "Profile field; if empty, the position from the workload profile.",
        "Поле профиля; если пусто — должность из профиля нагрузки.",
        "Profil alanı; boşsa yük profilindeki görev.",
    ),
    _t("Qadın", "Female", "Женщины", "Kadın"),
    _t("Saathesabı", "Hourly-paid", "Почасовая оплата", "Ders ücretli"),
    _t("Saathesabı saat", "Hourly-paid hours", "Почасовые часы", "Ders ücretli saat"),
    _t("Say", "Count", "Количество", "Sayı"),
    _t(
        "Seçilmiş il üçün ştat vahidi yoxdur",
        "No staff unit for the selected year",
        "Нет ставки на выбранный год",
        "Seçilen yıl için kadro birimi yok",
    ),
    _t("Silinib", "Deleted", "Удалён", "Silindi"),
    _t("Sistemə heç daxil olmayıb", "Never signed in", "Ни разу не входил в систему", "Sisteme hiç giriş yapmadı"),
    _t("Siyahıya bax", "View list", "Показать список", "Listeyi gör"),
    _t(
        "Səhifə %(page)s / %(pages)s · %(total)s müəllim",
        "Page %(page)s of %(pages)s · %(total)s teachers",
        "Страница %(page)s из %(pages)s · %(total)s преподавателей",
        "Sayfa %(page)s / %(pages)s · %(total)s öğretim elemanı",
    ),
    _t("Səhifələmə", "Pagination", "Пагинация", "Sayfalama"),
    _t("Tam ştat", "Full-time", "Полная ставка", "Tam kadro"),
    _t("Tədris fəaliyyəti", "Teaching activity", "Учебная деятельность", "Öğretim faaliyeti"),
    _t("Tədris ili", "Academic year", "Учебный год", "Öğretim yılı"),
    _t("Tərkib", "Composition", "Состав", "Kompozisyon"),
    _t("Təyin edilməyib", "Not set", "Не указано", "Belirtilmemiş"),
    _t("Universitet üzrə", "University total", "По университету", "Üniversite toplamı"),
    _t("Xeyr", "No", "Нет", "Hayır"),
    _t("Yalnız baxış", "View only", "Только просмотр", "Yalnızca görüntüleme"),
    _t("Yaş", "Age", "Возраст", "Yaş"),
    _t("Yaş qrupları", "Age groups", "Возрастные группы", "Yaş grupları"),
    _t("Yoxdur", "None", "Нет", "Yok"),
    _t("Yük", "Load", "Нагрузка", "Yük"),
    _t("Yük doluluğu", "Load fill", "Заполненность нагрузки", "Yük doluluğu"),
    _t(
        "Yük profilindəki vəzifədən",
        "From the workload profile position",
        "Из должности в профиле нагрузки",
        "Yük profilindeki görevden",
    ),
    _t("Yük yoxdur", "No load", "Нет нагрузки", "Yük yok"),
    _t(
        "Yük — dərs yükü bölgüsündə (paylanmış / düzəlişli tapşırıqlar) müəllimə yazılmış illik saat; norma — yük profilindəki illik norma (profil yoxdursa 500 saat). Doluluq kafedra cəmindən hesablanır.",
        "Load — annual hours assigned to the teacher in the workload distribution (distributed / amended tasks); norm — the annual norm in the workload profile (500 hours if there is no profile). Fill is calculated from the department total.",
        "Нагрузка — годовые часы, закреплённые за преподавателем в распределении нагрузки (распределённые / исправленные задания); норма — годовая норма из профиля нагрузки (500 часов, если профиля нет). Заполненность рассчитывается по итогу кафедры.",
        "Yük — ders yükü dağılımında (dağıtılmış / düzeltilmiş görevler) öğretim elemanına yazılan yıllık saat; norm — yük profilindeki yıllık norm (profil yoksa 500 saat). Doluluk bölüm toplamından hesaplanır.",
    ),
    _t("Yüklü (100–120%)", "Loaded (100–120%)", "Загружен (100–120%)", "Yüklü (%100–120)"),
    _t("Yükü olan", "With load", "С нагрузкой", "Yükü olan"),
    _t("akademik heyət", "academic staff", "преподавательский состав", "akademik kadro"),
    _t("blok + arxiv", "blocked + archived", "заблокированы + архив", "engelli + arşiv"),
    _t("hesab yaradılıb", "accounts created", "учётных записей создано", "hesap oluşturuldu"),
    _t("heç daxil olmayıb", "never signed in", "ни разу не входил", "hiç giriş yapmadı"),
    _t("ilk giriş yoxdur", "no first sign-in", "нет первого входа", "ilk giriş yok"),
    _t("ilkin parolda", "on initial password", "с начальным паролем", "ilk şifrede"),
    _t("plan / norma", "plan / norm", "план / норма", "plan / norm"),
    _t("saat", "hours", "ч", "saat"),
    _t("və daha %(more)s nəfər", "and %(more)s more", "и ещё %(more)s", "ve %(more)s kişi daha"),
    _t(
        "«Başqasının adından» rejimində ixrac bağlıdır",
        "Export is disabled in “view as” mode",
        "В режиме «от имени другого» экспорт недоступен",
        "«Başkası adına» modunda dışa aktarım kapalıdır",
    ),
    _t(
        "«Başqasının adından» rejimindəsiniz — analitika yalnız baxış üçündür, ixrac bağlıdır.",
        "You are in “view as” mode — the analytics are view-only and export is disabled.",
        "Вы в режиме «от имени другого» — аналитика только для просмотра, экспорт недоступен.",
        "«Başkası adına» modundasınız — analitik yalnızca görüntüleme içindir, dışa aktarım kapalıdır.",
    ),
    _t("Ümumi baxış", "Overview", "Обзор", "Genel bakış"),
    _t("İcra", "Completion", "Выполнение", "Gerçekleşme"),
    _t("İcra %", "Completion %", "Выполнение, %", "Gerçekleşme %"),
    _t("İstifadəçi adı", "Username", "Логин", "Kullanıcı adı"),
    _t("Ştat", "Staff unit", "Ставка", "Kadro"),
    _t("Ştat növü", "Staff type", "Тип ставки", "Kadro türü"),
    _t("Ştat payı", "Staff fraction", "Доля ставки", "Kadro payı"),
    _t("Ştat vahidi", "Staff units", "Ставки", "Kadro birimi"),
    _t(
        "Ştat vahidi seçilmiş tədris ilinin dərs yükü profilindən gəlir (tam = 1, yarım = 0,5). Saathesabı müəllimlər ştat vahidinə daxil edilmir; «Təyin edilməyib» — bu il üçün profili olmayanlar.",
        "Staff units come from the selected academic year's workload profiles (full = 1, half = 0.5). Hourly-paid teachers are not counted in staff units; “Not set” means no profile for this year.",
        "Ставки берутся из профилей нагрузки выбранного учебного года (полная = 1, половина = 0,5). Почасовики в ставки не входят; «Не указано» — нет профиля на этот год.",
        "Kadro birimi seçilen öğretim yılının ders yükü profillerinden gelir (tam = 1, yarım = 0,5). Ders ücretli öğretim elemanları kadro birimine dahil edilmez; «Belirtilmemiş» — bu yıl için profili olmayanlar.",
    ),
    _t("Ştat vahidləri", "Staff units", "Ставки", "Kadro birimleri"),
    _t("Ştatlı / saathesabı", "Staff / hourly-paid", "Штатные / почасовые", "Kadrolu / ders ücretli"),
    _t(
        "Ştatı var, amma aktiv üzvlüyü yoxdur",
        "Has a staff unit but no active membership",
        "Есть ставка, но нет активного членства",
        "Kadrosu var ama aktif üyeliği yok",
    ),
    _t("ştat vahidi: %(units)s", "staff units: %(units)s", "ставок: %(units)s", "kadro birimi: %(units)s"),
    _t("Ən az yüklənənlər (<70%)", "Least loaded (<70%)", "Наименее загруженные (<70%)", "En az yüklü (<%70)"),
    _t(
        "Ən çox rast gəlinən problemlər.",
        "Most frequent issues.",
        "Наиболее частые проблемы.",
        "En sık görülen sorunlar.",
    ),
    _t("Ən çox yüklənənlər (>100%)", "Most loaded (>100%)", "Наиболее загруженные (>100%)", "En çok yüklü (>%100)"),
    _t("Əvvəlki", "Previous", "Назад", "Önceki"),
]

_SIDEBAR = [
    _t("Kadr analitikası", "HR analytics", "Кадровая аналитика", "Personel analitiği"),
]

_PERM = [
    _t(
        "Kadr analitikası (ştat, tərkib, dərs yükü, ixrac)",
        "HR analytics (staff units, composition, teaching load, export)",
        "Кадровая аналитика (ставки, состав, нагрузка, экспорт)",
        "Personel analitiği (kadro, kompozisyon, ders yükü, dışa aktarım)",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    HR: {row["az"]: row for row in _HR},
    PSB: {row["az"]: row for row in _SIDEBAR},
    PERM: {row["az"]: row for row in _PERM},
}

FORCE = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
