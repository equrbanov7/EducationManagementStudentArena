#!/usr/bin/env python3
"""EMSArena i18n — Dizayn Faza-1 (Stage-1) mətnləri (4 dil). İdempotent.

Mənbə: `docs/audits/2026-09-02/DESIGN_STAGE1_MSGIDS.txt` (185 msgid, 8 kontekst)
— commit `6c028efe` ilə əlavə olunan Tədris şöbəsi bölmələri: universitet
strukturu ağacı, kafedra profili, ixtisaslar reyestri, fənn kataloqu, yeni
icazə etiketləri, profil menyusu, təhsil forması/fənn növü seçimləri, ümumi
status kataloqu.

Yoxlama metodu (audit tələbi): `scripts/i18n_source_scan.py` + ƏL İLƏ AST
skanı, çünki mənbə skaneri MODUL-SƏVİYYƏLİ dəyişənlə çağırılan
`pgettext(_CTX, …)` / `pgettext_lazy(_CTX, …)` cütlərini tanımır (kontekst
arqumenti `ast.Constant` deyil, `ast.Name`-dir):

  * `apps/registrar/catalog_actions.py`, `apps/registrar/catalog_registry.py`,
    `apps/accounts/views/profile/_sections/catalog_sections.py` —
    `_CTX = "accounts.catalog"` (59 çağırış, skaner görmür);
  * `apps/accounts/views/profile/_sections/teaching_office.py` —
    `_CTX = "accounts.chair_profile"` (18 çağırış, skaner görmür);
  * `apps/organizations/structure_actions.py`,
    `apps/organizations/structure_views/tree.py` —
    `_CTX = "accounts.structure_tree"` (24 çağırış, skaner görmür);
  * `apps/organizations/permissions.py` — `_PERM_CTX =
    "organizations.permission.label"` (skaner 0 tapır — BÜTÜN kontekst
    dəyişənlədir; 4-ü YENİ, qalanı mövcud kataloqda artıq var);
  * `core/ui/status_catalog.py` — `_CTX = "ui.status"`, ÜSTƏLİK ikiqat
    dolayı (`_t(text)` → `pgettext_lazy(_CTX, text)`) — skaner 0 tapır.

  Şablonlarda ({% trans … context "…" %}) kontekst LİTERAL olduğu üçün
  skaner onları tapır (83 cüt) — qalan 102 cüt yuxarıdakı Python
  kor-nöqtələrindən (əl ilə AST gəzintisi + qrep ilə təsdiqlənib).
  Cəmi: 83 + 102 = 185 — audit sənədinin CƏMİsi ilə TAM üst-üstə düşür,
  əlavə/əskik yoxdur (yoxlanılıb, bax audit qeydləri).

  `organizations.permission.label`-da əl ilə AST gəzintisi 185-dən KƏNAR
  daha 10 boşluq da aşkar etdi (məs. "Dərs yükünü müəllimlərə bölmək") —
  bunlar `apps/workload` icazələridir, `6c028efe`-dən ƏVVƏL mövcud idi
  (`git show 6c028efe -- apps/organizations/permissions.py` ilə təsdiqlənib,
  bu commit yalnız 4 `unit.tree_manage`/`unit.assign_head`/`catalog.*`
  açarını əlavə edib) — bu skriptin ƏHATƏSİNDƏN KƏNARDIR, ayrıca borcdur.

AZ identity DOĞRUDUR bu faylda — bütün 185 msgid artıq Azərbaycanca UI
mətnidir (texniki/xam açar yoxdur, `AZ_OVERRIDES` lazım deyil).

⚠️ PARALEL AGENT TƏHLÜKƏSİZLİYİ (bax `i18n_fill_question_chair_review.py`):
   eyni sessiyada başqa agentlər eyni 4 `.po` faylına ƏLAVƏ edə bilər.
     * mövcudluq yoxlaması `polib` ilə (bax `existing_pairs`);
     * YAZMADAN DƏRHAL ƏVVƏL fayl YENİDƏN oxunur (`fill()` daxilində);
     * yazma xam mətn ƏLAVƏSİ ilə — `polib.save()` İŞLƏDİLMİR (bütün
       kataloqu yenidən serializasiya edib mövcud sətirləri poza bilər).
       Yalnız ƏLAVƏ olunur — mövcud sətirlərə TOXUNULMUR, fuzzy flag-lar
       dəyişdirilmir.

⚠️ `makemessages` İŞLƏDİLMİR (əl ilə yazılmış blokları silə bilər).

İstifadə:  python scripts/i18n_fill_design_stage1.py
Sonra:     django-admin compilemessages && python scripts/check_i18n_catalogs.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def _e(en, ru, tr):
    return {"en": en, "ru": ru, "tr": tr}


# ─────────────────────────────────────────────────────────────────────────────
# accounts.catalog — Fənn kataloqu + İxtisaslar reyestri (dizayn ekran 03/04)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_CATALOG = {
    "AD DUBLİKATI": _e("NAME DUPLICATE", "ДУБЛИКАТ НАЗВАНИЯ", "AD TEKRARI"),
    "ARXİVDƏ": _e("ARCHIVED", "В АРХИВЕ", "ARŞİVDE"),
    "Ad və ya rəsmi şifr": _e("Name or official code", "Название или официальный код", "Ad veya resmi kod"),
    "Aktiv təşkilat konteksti yoxdur.": _e(
        "There is no active organization context.",
        "Нет активного контекста организации.",
        "Aktif kurum bağlamı yok.",
    ),
    "Aktivlər": _e("Active", "Активные", "Aktifler"),
    "Arxiv": _e("Archive", "Архив", "Arşiv"),
    "Arxivdəkilər": _e("Archived", "Архивные", "Arşivdekiler"),
    "Arxivdən qaytar": _e("Restore from archive", "Восстановить из архива", "Arşivden geri getir"),
    "Arxivlə": _e("Archive", "Архивировать", "Arşivle"),
    "Axtarış": _e("Search", "Поиск", "Arama"),
    "Bu kodla fənn artıq mövcuddur.": _e(
        "A subject with this code already exists.",
        "Дисциплина с этим кодом уже существует.",
        "Bu kodla bir ders zaten mevcut.",
    ),
    "Bu kodla ixtisas artıq mövcuddur.": _e(
        "A programme with this code already exists.",
        "Специальность с этим кодом уже существует.",
        "Bu kodla bir program zaten mevcut.",
    ),
    "Bəli": _e("Yes", "Да", "Evet"),
    "Bərpa səbəbi audit jurnalına aktor və vaxtla yazılır.": _e(
        "The restore reason is recorded in the audit log with the actor and timestamp.",
        "Причина восстановления записывается в журнал аудита с указанием исполнителя и времени.",
        "Geri getirme gerekçesi işlemi yapan kişi ve zamanla birlikte denetim günlüğüne yazılır.",
    ),
    "ECTS": _e("ECTS", "ECTS", "ECTS"),
    "Eyni adlı fənlər aşkarlandı": _e(
        "Subjects with the same name were detected",
        "Обнаружены дисциплины с одинаковым названием",
        "Aynı adlı dersler tespit edildi",
    ),
    "Eyni adlı fənlər birləşdirilmir — birləşdirmə (merge) destruktiv əməldir və plan sətirləri ilə "
    "sillabusların köçürülməsini tələb edir (növbəti mərhələ).": _e(
        "Subjects with the same name are not merged — merging is a destructive operation and requires "
        "migrating curriculum lines and syllabi (a future phase).",
        "Дисциплины с одинаковым названием не объединяются — объединение (merge) является деструктивной "
        "операцией и требует переноса строк учебного плана и силлабусов (следующий этап).",
        "Aynı adlı dersler birleştirilmez — birleştirme (merge) yıkıcı bir işlemdir ve müfredat "
        "satırlarının ve silabusların taşınmasını gerektirir (sonraki aşama).",
    ),
    "Eyni adlı yazılar": _e("Records with the same name", "Записи с одинаковым названием", "Aynı adlı kayıtlar"),
    "FƏNN": _e("SUBJECT", "ДИСЦИПЛИНА", "DERS"),
    "Fənn kodu boş ola bilməz.": _e(
        "The subject code cannot be empty.", "Код дисциплины не может быть пустым.", "Ders kodu boş olamaz."
    ),
    "Fənn kodu tenant daxilində unikaldır; saat bölgüsü tədris planı sətrində saxlanılır.": _e(
        "The subject code is unique within the tenant; the hour breakdown is stored on the curriculum line.",
        "Код дисциплины уникален в пределах арендатора; распределение часов хранится в строке учебного плана.",
        "Ders kodu kiracı (tenant) içinde benzersizdir; saat dağılımı müfredat satırında saklanır.",
    ),
    "Fənn kodu və ya adı": _e("Subject code or name", "Код или название дисциплины", "Ders kodu veya adı"),
    "Fənn növü": _e("Subject type", "Тип дисциплины", "Ders türü"),
    "Fənn növü seçilməyib.": _e(
        "The subject type has not been selected.", "Тип дисциплины не выбран.", "Ders türü seçilmedi."
    ),
    "Fənn tapılmadı": _e("Subject not found", "Дисциплина не найдена", "Ders bulunamadı"),
    "Fənn tapılmadı.": _e("Subject not found.", "Дисциплина не найдена.", "Ders bulunamadı."),
    "Fənnin adı": _e("Subject name", "Название дисциплины", "Ders adı"),
    "Fənnin adı boş ola bilməz.": _e(
        "The subject name cannot be empty.", "Название дисциплины не может быть пустым.", "Ders adı boş olamaz."
    ),
    "Hamısı": _e("All", "Все", "Tümü"),
    "Kafedra": _e("Department", "Кафедра", "Bölüm"),
    "Kafedra / fakültə": _e("Department / faculty", "Кафедра / факультет", "Bölüm / fakülte"),
    "Kataloq yazısını arxivlə": _e(
        "Archive the catalog entry", "Архивировать запись каталога", "Katalog kaydını arşivle"
    ),
    "Kataloqa baxış üçün səlahiyyətiniz yoxdur. Administratora müraciət edin.": _e(
        "You do not have permission to view the catalog. Contact your administrator.",
        "У вас нет прав для просмотра каталога. Обратитесь к администратору.",
        "Kataloğu görüntüleme yetkiniz yok. Yöneticinize başvurun.",
    ),
    "Kataloqu idarə etmək səlahiyyətiniz yoxdur.": _e(
        "You do not have permission to manage the catalog.",
        "У вас нет прав для управления каталогом.",
        "Kataloğu yönetme yetkiniz yok.",
    ),
    "Kredit (ECTS)": _e("Credits (ECTS)", "Кредиты (ECTS)", "Kredi (ECTS)"),
    "Məzuniyyət üçün ECTS": _e("ECTS required for graduation", "ECTS для выпуска", "Mezuniyet için ECTS"),
    "Naməlum kataloq növü.": _e("Unknown catalog type.", "Неизвестный тип каталога.", "Bilinmeyen katalog türü."),
    "Naməlum əməl.": _e("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
    "Növ": _e("Type", "Тип", "Tür"),
    "Nəticə: %(count)d sətir": _e("Result: %(count)d rows", "Результат: %(count)d строк", "Sonuç: %(count)d satır"),
    "PLAN YOXDUR": _e("NO PLAN", "НЕТ ПЛАНА", "PLAN YOK"),
    "PLANDA İSTİFADƏDƏ": _e("IN USE IN PLANS", "ИСПОЛЬЗУЕТСЯ В ПЛАНАХ", "PLANDA KULLANILIYOR"),
    "Planlarda istifadə": _e("Used in curricula", "Использование в планах", "Planlarda kullanım"),
    # DİQQƏT: `{% trans %}` şablon taginin daxilindəki HƏRFİ `%` Django-nun
    # TranslateNode-u tərəfindən `%%`-ə İKİQATLANIR (parse zamanı) və YALNIZ
    # render-dən SONRA geri `%`-ə çevrilir (bax `django/templatetags/i18n.py`
    # `TranslateNode.render` — "Percent signs in template text are doubled").
    # Runtime `pgettext()` axtarışı da HƏMİN ikiqatlanmış açarla gedir, ona
    # görə msgid/msgstr BURADA da `%%` olmalıdır (mövcud kataloqda eyni nümunə:
    # "İmtahandan kəsilib — 25%% təkrar imtahan"). Eyni HƏRFİ mətn Python
    # `pgettext_lazy(...)`-dən (`registrar.console` konteksti, `forms.py`)
    # gələndə İKİQATLANMIR — o, tək `%` saxlayır; iki fərqli kontekst, iki
    # fərqli açar formatı, ziddiyyət YOXDUR.
    "Qayıb limiti (%%)": _e("Absence limit (%%)", "Лимит пропусков (%%)", "Devamsızlık limiti (%%)"),
    "Qrup": _e("Group", "Группа", "Grup"),
    "REYESTRDƏ CƏMİ": _e("TOTAL IN THE REGISTRY", "ВСЕГО В РЕЕСТРЕ", "KAYITTA TOPLAM"),
    "Redaktə": _e("Edit", "Редактировать", "Düzenle"),
    "Reyestr kodu": _e("Registry code", "Код реестра", "Sicil kodu"),
    "Rəsmi şifr (NK 503)": _e("Official code (NK 503)", "Официальный код (NK 503)", "Resmi kod (NK 503)"),
    "Rəsmi şifr NK 503/2024 kataloqundan götürülür; daxili kod avtomatik yaranır.": _e(
        "The official code is taken from the NK 503/2024 catalog; the internal code is generated automatically.",
        "Официальный код берётся из каталога NK 503/2024; внутренний код формируется автоматически.",
        "Resmi kod NK 503/2024 kataloğundan alınır; iç kod otomatik olarak oluşturulur.",
    ),
    "Sahibi kafedra": _e("Owning department", "Кафедра-владелец", "Sahip bölüm"),
    "Süzgəcləri dəyişin və ya yeni fənn əlavə edin.": _e(
        "Change the filters or add a new subject.",
        "Измените фильтры или добавьте новую дисциплину.",
        "Filtreleri değiştirin veya yeni bir ders ekleyin.",
    ),
    "Süzgəcləri dəyişin və ya yeni ixtisas əlavə edin.": _e(
        "Change the filters or add a new programme.",
        "Измените фильтры или добавьте новую специальность.",
        "Filtreleri değiştirin veya yeni bir program ekleyin.",
    ),
    "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.": _e(
        "The reason must be at least 20 characters — a short note is not enough for the audit.",
        "Причина должна содержать не менее 20 символов — краткая заметка недостаточна для аудита.",
        "Gerekçe en az 20 karakter olmalı — kısa bir not denetim için yeterli değildir.",
    ),
    "Tabe olduğu kafedra": _e("Reporting department", "Подведомственная кафедра", "Bağlı olduğu bölüm"),
    "Tam ad": _e("Full name", "Полное название", "Tam ad"),
    "Tədris planı təsdiqlənməyib": _e(
        "The curriculum has not been approved", "Учебный план не утверждён", "Müfredat onaylanmamış"
    ),
    "Təhsil forması": _e("Mode of study", "Форма обучения", "Öğretim şekli"),
    "Təhsil forması seçilməyib.": _e(
        "The mode of study has not been selected.", "Форма обучения не выбрана.", "Öğretim şekli seçilmedi."
    ),
    "Təhsil pilləsi": _e("Degree level", "Уровень образования", "Öğretim derecesi"),
    "Təhsil pilləsi seçilməyib.": _e(
        "The degree level has not been selected.", "Уровень образования не выбран.", "Öğretim derecesi seçilmedi."
    ),
    "Təyin edilməyib": _e("Not assigned", "Не назначено", "Atanmamış"),
    "Universitetin təhsil proqramları: rəsmi şifr, pillə, forma, tabe olduğu kafedra və tədris planının "
    "vəziyyəti.": _e(
        "The university's degree programmes: official code, level, mode, reporting department, and "
        "curriculum status.",
        "Образовательные программы университета: официальный код, уровень, форма, подведомственная "
        "кафедра и статус учебного плана.",
        "Üniversitenin eğitim programları: resmi kod, derece, öğretim şekli, bağlı olduğu bölüm ve "
        "müfredat durumu.",
    ),
    "Universitetin vahid fənn reyestri: kod, kredit, növ, sahibi kafedra və planlarda istifadə.": _e(
        "The university's unified subject registry: code, credits, type, owning department, and use in "
        "curricula.",
        "Единый реестр дисциплин университета: код, кредиты, тип, кафедра-владелец и использование в планах.",
        "Üniversitenin birleşik ders sicili: kod, kredi, tür, sahip bölüm ve planlarda kullanım.",
    ),
    "Vəziyyət": _e("Status", "Статус", "Durum"),
    "Yalnız dublikatlar": _e("Duplicates only", "Только дубликаты", "Yalnızca tekrarlar"),
    "Yalnız «Plan yoxdur»": _e('Only "No plan"', "Только «Нет плана»", "Yalnızca “Plan yok”"),
    "Yazı SİLİNMİR — arxivlənir; plan sətirləri, jurnal və qiymət tarixçəsi qalır.": _e(
        "The record is NOT DELETED — it is archived; curriculum lines, the journal, and the grade "
        "history are preserved.",
        "Запись НЕ УДАЛЯЕТСЯ — она архивируется; строки плана, журнал и история оценок сохраняются.",
        "Kayıt SİLİNMEZ — arşivlenir; plan satırları, jurnal ve not geçmişi korunur.",
    ),
    "Yazı tapılmadı.": _e("Record not found.", "Запись не найдена.", "Kayıt bulunamadı."),
    "Yeni fənn": _e("New subject", "Новая дисциплина", "Yeni ders"),
    "Yeni ixtisas": _e("New programme", "Новая специальность", "Yeni program"),
    "İXTİSAS": _e("PROGRAMME", "СПЕЦИАЛЬНОСТЬ", "PROGRAM"),
    "İxtisas kodu": _e("Programme code", "Код специальности", "Program kodu"),
    "İxtisas tapılmadı": _e("Programme not found", "Специальность не найдена", "Program bulunamadı"),
    "İxtisas tapılmadı.": _e("Programme not found.", "Специальность не найдена.", "Program bulunamadı."),
    "İxtisasın adı boş ola bilməz.": _e(
        "The programme name cannot be empty.",
        "Название специальности не может быть пустым.",
        "Program adı boş olamaz.",
    ),
    "Əməllər": _e("Actions", "Действия", "İşlemler"),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.chair_profile — Kafedra profili: ştat, müəllim heyəti, illik yük
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_CHAIR_PROFILE = {
    "Aktiv təşkilat konteksti yoxdur": _e(
        "There is no active organization context",
        "Нет активного контекста организации",
        "Aktif kurum bağlamı yok",
    ),
    "Bu kafedraya hələ müəllim təyin edilməyib və ya süzgəc nəticəni boşaldıb.": _e(
        "No teacher has been assigned to this department yet, or the filter has emptied the result.",
        "Этой кафедре ещё не назначен преподаватель, либо фильтр обнулил результат.",
        "Bu bölüme henüz öğretmen atanmamış ya da filtre sonucu boşalttı.",
    ),
    "Bəli": _e("Yes", "Да", "Evet"),
    "Hamısı": _e("All", "Все", "Tümü"),
    "Kafedra": _e("Department", "Кафедра", "Bölüm"),
    "Kafedranın ştat cədvəli, müəllim heyəti və illik yük riski. Norma dəyərləri müəllim yük profilindən "
    "oxunur.": _e(
        "The department's staffing table, teaching staff, and annual workload risk. Norm values are read "
        "from the teacher workload profile.",
        "Штатное расписание кафедры, преподавательский состав и риск годовой нагрузки. Нормативные "
        "значения считываются из профиля нагрузки преподавателя.",
        "Bölümün kadro çizelgesi, öğretim kadrosu ve yıllık yük riski. Norm değerleri öğretmen yük "
        "profilinden okunur.",
    ),
    "MÜƏLLİM": _e("TEACHER", "ПРЕПОДАВАТЕЛЬ", "ÖĞRETMEN"),
    "Müdir": _e("Head", "Заведующий", "Başkan"),
    "Müdir təyin edilməyib": _e("No head assigned", "Заведующий не назначен", "Başkan atanmamış"),
    "Müəllim": _e("Teacher", "Преподаватель", "Öğretmen"),
    "Müəllim tapılmadı": _e("Teacher not found", "Преподаватель не найден", "Öğretmen bulunamadı"),
    "Norma": _e("Norm", "Норма", "Norm"),
    "Norma dəyərləri müəllim yük profilindən oxunur (NK №215 default: 500 saat). Nazirlik/Universitet "
    "norma dəstlərinin ayrılması sahib qərarını gözləyir.": _e(
        "Norm values are read from the teacher workload profile (NK No. 215 default: 500 hours). "
        "Separating Ministry/University norm sets is pending an owner decision.",
        "Нормативные значения считываются из профиля нагрузки преподавателя (NK №215 по умолчанию: "
        "500 часов). Разделение наборов норм Министерства/Университета ожидает решения владельца.",
        "Norm değerleri öğretmen yük profilinden okunur (NK №215 varsayılan: 500 saat). Bakanlık/Üniversite "
        "norm setlerinin ayrılması sahibinin kararını bekliyor.",
    ),
    "Normaya nisbətdə": _e("Relative to the norm", "По отношению к норме", "Norma göre"),
    "Nəticə: %(count)d müəllim": _e(
        "Result: %(count)d teachers", "Результат: %(count)d преподавателей", "Sonuç: %(count)d öğretmen"
    ),
    "Qrup": _e("Group", "Группа", "Grup"),
    "Saathesabı": _e("Hourly paid", "Почасовая оплата", "Saat ücretli"),
    "Sillabus": _e("Syllabus", "Силлабус", "Ders izlencesi"),
    "Struktur əhatəniz təyin edilməyib. Kafedra təyinatı üçün Tədris şöbəsinə və ya administratora "
    "müraciət edin.": _e(
        "Your structural scope has not been assigned. Contact the Teaching Office or the administrator "
        "for department assignment.",
        "Ваш структурный охват не назначен. Для назначения кафедры обратитесь в Учебный отдел или к "
        "администратору.",
        "Yapısal kapsamınız atanmamış. Bölüm ataması için Öğretim İşleri Dairesine veya yöneticinize "
        "başvurun.",
    ),
    "SİLLABUS ƏHATƏSİ": _e("SYLLABUS COVERAGE", "ОХВАТ СИЛЛАБУСОМ", "SİLABUS KAPSAMI"),
    "Tədris ili": _e("Academic year", "Учебный год", "Öğretim yılı"),
    "Tələbə": _e("Student", "Студент", "Öğrenci"),
    "Təşkilat seçin və ya administratora müraciət edin.": _e(
        "Select an organization or contact the administrator.",
        "Выберите организацию или обратитесь к администратору.",
        "Bir kurum seçin veya yöneticinize başvurun.",
    ),
    "Vəzifə": _e("Position", "Должность", "Görev"),
    "Yalnız yüklü / risk": _e("Overloaded / at risk only", "Только с нагрузкой / риском", "Yalnızca yüklü / riskli"),
    "Yük vəziyyəti": _e("Workload status", "Статус нагрузки", "Yük durumu"),
    "saat": _e("hours", "часов", "saat"),
    "İLLİK SAAT": _e("ANNUAL HOURS", "ГОДОВЫЕ ЧАСЫ", "YILLIK SAAT"),
    "İllik saat": _e("Annual hours", "Годовые часы", "Yıllık saat"),
    "İxtisas": _e("Programme", "Специальность", "Program"),
    "ŞTAT VAHİDİ CƏMİ": _e("TOTAL STAFF UNITS", "ВСЕГО ШТАТНЫХ ЕДИНИЦ", "TOPLAM KADRO BİRİMİ"),
    "Ştat": _e("Staff", "Штат", "Kadro"),
    "Ştat növü": _e("Staff type", "Тип штата", "Kadro türü"),
    "Ştat payı": _e("Staff share", "Штатная доля", "Kadro payı"),
    "Ştat payının cəmi": _e("Total staff share", "Сумма штатных долей", "Toplam kadro payı"),
    "Əhatənizdə kafedra yoxdur": _e(
        "There is no department in your scope", "В вашем охвате нет кафедры", "Kapsamınızda bölüm yok"
    ),
    "Əvəzçilik": _e("Concurrent position", "Совместительство", "Ek görev"),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.structure_tree — Universitetin struktur ağacı (dizayn ekran 01)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_STRUCTURE_TREE = {
    "Adını dəyiş": _e("Rename", "Переименовать", "Adını değiştir"),
    "Aktiv alt bölməsi olan vahid arxivlənə bilməz — əvvəlcə alt bölmələri arxivləyin.": _e(
        "A unit with active sub-units cannot be archived — archive its sub-units first.",
        "Единица с активными подразделениями не может быть архивирована — сначала архивируйте "
        "подразделения.",
        "Aktif alt birimi olan birim arşivlenemez — önce alt birimleri arşivleyin.",
    ),
    "Alt bölmə əlavə et": _e("Add sub-unit", "Добавить подразделение", "Alt birim ekle"),
    "Arxivlə": _e("Archive", "Архивировать", "Arşivle"),
    "Axtarış": _e("Search", "Поиск", "Arama"),
    "Ağacdan bölmə seçin — heyət, qrup və tələbə göstəriciləri burada açılır.": _e(
        "Select a unit from the tree — staff, group, and student indicators open here.",
        "Выберите подразделение из дерева — здесь откроются показатели персонала, групп и студентов.",
        "Ağaçtan bir birim seçin — personel, grup ve öğrenci göstergeleri burada açılır.",
    ),
    "Bu bölməyə baxış üçün struktur əhatəniz yoxdur. Administratora müraciət edin.": _e(
        "Your structural scope does not include viewing this unit. Contact the administrator.",
        "Ваш структурный охват не позволяет просматривать это подразделение. Обратитесь к администратору.",
        "Yapısal kapsamınız bu birimi görüntülemeye izin vermiyor. Yöneticinize başvurun.",
    ),
    "BÖLMƏ": _e("UNIT", "ПОДРАЗДЕЛЕНИЕ", "BİRİM"),
    "Bölmə SİLİNMİR — arxivlənir. Əlaqəli tələbə, jurnal və qiymət tarixçəsi olduğu kimi qalır.": _e(
        "The unit is NOT DELETED — it is archived. Related students, the journal, and the grade history "
        "remain as is.",
        "Подразделение НЕ УДАЛЯЕТСЯ — оно архивируется. Связанные студенты, журнал и история оценок "
        "остаются без изменений.",
        "Birim SİLİNMEZ — arşivlenir. İlgili öğrenciler, jurnal ve not geçmişi olduğu gibi kalır.",
    ),
    "Bölmə SİLİNMİR — arxivlənir; tələbə, jurnal və qiymət tarixçəsi qalır.": _e(
        "The unit is NOT DELETED — it is archived; students, the journal, and the grade history are "
        "preserved.",
        "Подразделение НЕ УДАЛЯЕТСЯ — оно архивируется; студенты, журнал и история оценок сохраняются.",
        "Birim SİLİNMEZ — arşivlenir; öğrenciler, jurnal ve not geçmişi korunur.",
    ),
    "Bölmə adı və ya kodu": _e("Unit name or code", "Название или код подразделения", "Birim adı veya kodu"),
    "Bölmə seçilmiş vahidin altında yaradılır.": _e(
        "The unit is created under the selected entity.",
        "Подразделение создаётся внутри выбранной единицы.",
        "Birim, seçilen birimin altında oluşturulur.",
    ),
    "Bölmə seçilməyib": _e("No unit selected", "Подразделение не выбрано", "Birim seçilmedi"),
    "Bölmə tapılmadı": _e("Unit not found", "Подразделение не найдено", "Birim bulunamadı"),
    "Bölmə tapılmadı.": _e("Unit not found.", "Подразделение не найдено.", "Birim bulunamadı."),
    "Bölmə tipi": _e("Unit type", "Тип подразделения", "Birim türü"),
    "Bölmə tipi bu təşkilat üçün keçərli deyil.": _e(
        "The unit type is not valid for this organization.",
        "Тип подразделения недопустим для этой организации.",
        "Birim türü bu kurum için geçerli değil.",
    ),
    "Bölməni arxivlə": _e("Archive the unit", "Архивировать подразделение", "Birimi arşivle"),
    "Bölmənin adı": _e("Unit name", "Название подразделения", "Birim adı"),
    "Bölmənin adı boş ola bilməz.": _e(
        "The unit name cannot be empty.", "Название подразделения не может быть пустым.", "Birim adı boş olamaz."
    ),
    "Bütün tiplər": _e("All types", "Все типы", "Tüm türler"),
    "FAKÜLTƏ": _e("FACULTY", "ФАКУЛЬТЕТ", "FAKÜLTE"),
    "KAFEDRA": _e("DEPARTMENT", "КАФЕДРА", "BÖLÜM"),
    "Kod": _e("Code", "Код", "Kod"),
    "Müəllim": _e("Teacher", "Преподаватель", "Öğretmen"),
    "Naməlum əməl.": _e("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
    "Nəticə: %(count)d bölmə": _e(
        "Result: %(count)d units", "Результат: %(count)d подразделений", "Sonuç: %(count)d birim"
    ),
    "Qrup": _e("Group", "Группа", "Grup"),
    "Rektorat → fakültə → dekanlıq → kafedra → ixtisas → qrup iyerarxiyası. Bölmə silinmir — arxivlənir.": _e(
        "The rectorate → faculty → dean's office → department → programme → group hierarchy. Units are "
        "not deleted — they are archived.",
        "Иерархия ректорат → факультет → деканат → кафедра → специальность → группа. Подразделение не "
        "удаляется — оно архивируется.",
        "Rektörlük → fakülte → dekanlık → bölüm → program → grup hiyerarşisi. Birim silinmez — arşivlenir.",
    ),
    "RƏHBƏRİ YOXDUR": _e("NO HEAD", "НЕТ РУКОВОДИТЕЛЯ", "BAŞKANI YOK"),
    "Rəhbər": _e("Head", "Руководитель", "Yönetici"),
    "Rəhbər təyin et": _e("Assign head", "Назначить руководителя", "Yönetici ata"),
    "Rəhbər təyini üçün səlahiyyətiniz yoxdur.": _e(
        "You do not have permission to assign a head.",
        "У вас нет прав для назначения руководителя.",
        "Yönetici atama yetkiniz yok.",
    ),
    "Rəhbəri götür (boş)": _e(
        "Remove the head (leave empty)", "Снять руководителя (оставить пустым)", "Yöneticiyi kaldır (boş bırak)"
    ),
    "Seçilmiş şəxs bu təşkilatın aktiv üzvü deyil.": _e(
        "The selected person is not an active member of this organization.",
        "Выбранное лицо не является активным членом этой организации.",
        "Seçilen kişi bu kurumun aktif üyesi değil.",
    ),
    "Seçin…": _e("Select…", "Выберите…", "Seçin…"),
    "Struktur ağacı": _e("Structure tree", "Дерево структуры", "Yapı ağacı"),
    "Struktur ağacını idarə etmək səlahiyyətiniz yoxdur.": _e(
        "You do not have permission to manage the structure tree.",
        "У вас нет прав для управления деревом структуры.",
        "Yapı ağacını yönetme yetkiniz yok.",
    ),
    "Struktur əhatəniz yoxdur.": _e(
        "You have no structural scope.", "У вас нет структурного охвата.", "Yapısal kapsamınız yok."
    ),
    "Süzgəcləri dəyişin və ya yeni bölmə əlavə edin.": _e(
        "Change the filters or add a new unit.",
        "Измените фильтры или добавьте новое подразделение.",
        "Filtreleri değiştirin veya yeni bir birim ekleyin.",
    ),
    "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.": _e(
        "The reason must be at least 20 characters — a short note is not enough for the audit.",
        "Причина должна содержать не менее 20 символов — краткая заметка недостаточна для аудита.",
        "Gerekçe en az 20 karakter olmalı — kısa bir not denetim için yeterli değildir.",
    ),
    "Tələbə": _e("Student", "Студент", "Öğrenci"),
    "Təyin edilməyib": _e("Not assigned", "Не назначено", "Atanmamış"),
    "Təyin et": _e("Assign", "Назначить", "Ata"),
    "Təyinat gözləyir": _e("Awaiting assignment", "Ожидает назначения", "Atama bekliyor"),
    "Təyinat səbəbi audit jurnalına aktor və vaxtla yazılır.": _e(
        "The assignment reason is recorded in the audit log with the actor and timestamp.",
        "Причина назначения записывается в журнал аудита с указанием исполнителя и времени.",
        "Atama gerekçesi işlemi yapan kişi ve zamanla birlikte denetim günlüğüne yazılır.",
    ),
    "Universitetin struktur ağacı": _e(
        "The university's structure tree", "Дерево структуры университета", "Üniversitenin yapı ağacı"
    ),
    "Valideyn bölmə tapılmadı.": _e(
        "Parent unit not found.", "Родительское подразделение не найдено.", "Üst birim bulunamadı."
    ),
    "Yeni alt bölmə": _e("New sub-unit", "Новое подразделение", "Yeni alt birim"),
    "İxtisas": _e("Programme", "Специальность", "Program"),
}

# ─────────────────────────────────────────────────────────────────────────────
# organizations.permission.label — YENİ icazə etiketləri (bax modul başlığı:
# skaner bu kontekstdə 0 tapır, çünki BÜTÜN çağırışlar `_PERM_CTX` dəyişənilədir)
# ─────────────────────────────────────────────────────────────────────────────
ORGANIZATIONS_PERMISSION_LABEL = {
    "Bölməyə rəhbər təyin etmək": _e(
        "Assign a head to a unit", "Назначать руководителя подразделения", "Birime yönetici atamak"
    ),
    "Struktur ağacını idarə etmək (yaratmaq/adını dəyişmək/arxivləmək)": _e(
        "Manage the structure tree (create/rename/archive)",
        "Управлять деревом структуры (создание/переименование/архивирование)",
        "Yapı ağacını yönetmek (oluşturma/yeniden adlandırma/arşivleme)",
    ),
    "İxtisas və fənn kataloquna baxış": _e(
        "View the programme and subject catalog",
        "Просмотр каталога специальностей и дисциплин",
        "Program ve ders kataloğunu görüntüleme",
    ),
    "İxtisas və fənn kataloqunu idarə etmək": _e(
        "Manage the programme and subject catalog",
        "Управление каталогом специальностей и дисциплин",
        "Program ve ders kataloğunu yönetmek",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# profile.sidebar — yeni profil menyu bəndləri (Tədris şöbəsi qrupu)
# ─────────────────────────────────────────────────────────────────────────────
PROFILE_SIDEBAR = {
    "Fənn kataloqu": _e("Subject catalog", "Каталог дисциплин", "Ders kataloğu"),
    "Kafedra profili": _e("Department profile", "Профиль кафедры", "Bölüm profili"),
    "Tədris şöbəsi": _e("Teaching Office", "Учебный отдел", "Öğretim İşleri Dairesi"),
    "Universitet strukturu": _e("University structure", "Структура университета", "Üniversite yapısı"),
    "İxtisaslar": _e("Programmes", "Специальности", "Programlar"),
}

# ─────────────────────────────────────────────────────────────────────────────
# registrar.education_form — Program.education_form TextChoices
# ─────────────────────────────────────────────────────────────────────────────
REGISTRAR_EDUCATION_FORM = {
    "Distant": _e("Distance", "Дистанционная", "Uzaktan öğretim"),
    "Qiyabi": _e("Part-time", "Заочная", "İkinci öğretim"),
    "Əyani": _e("Full-time", "Очная", "Örgün öğretim"),
}

# ─────────────────────────────────────────────────────────────────────────────
# registrar.subject_kind — Subject.kind TextChoices
# ─────────────────────────────────────────────────────────────────────────────
REGISTRAR_SUBJECT_KIND = {
    "Seçmə fənn": _e("Elective subject", "Дисциплина по выбору", "Seçmeli ders"),
    "Təcrübə": _e("Practice", "Практика", "Uygulama"),
    "Ümumi fənn": _e("General subject", "Общая дисциплина", "Genel ders"),
    "İxtisas fənni": _e("Core subject", "Профильная дисциплина", "Alan dersi"),
}

# ─────────────────────────────────────────────────────────────────────────────
# ui.status — GENERAL status ailəsinə əlavə (kataloq yazısı vəziyyəti).
# `core/ui/status_catalog.py`-də `_t(text)` → `pgettext_lazy(_CTX, text)`
# ikiqat dolayı çağırışdır (bax modul başlığı) — skaner 0 tapır.
# ─────────────────────────────────────────────────────────────────────────────
UI_STATUS = {
    "Ad dublikatı": _e("Duplicate name", "Дубликат названия", "Ad tekrarı"),
    "Aktiv": _e("Active", "Активен", "Aktif"),
    "Arxivdə": _e("Archived", "В архиве", "Arşivde"),
    "Plan yoxdur": _e("No plan", "Нет плана", "Plan yok"),
    "Planda istifadə olunmur": _e("Not used in a plan", "Не используется в плане", "Planda kullanılmıyor"),
}

ENTRIES = {
    "accounts.catalog": ACCOUNTS_CATALOG,
    "accounts.chair_profile": ACCOUNTS_CHAIR_PROFILE,
    "accounts.structure_tree": ACCOUNTS_STRUCTURE_TREE,
    "organizations.permission.label": ORGANIZATIONS_PERMISSION_LABEL,
    "profile.sidebar": PROFILE_SIDEBAR,
    "registrar.education_form": REGISTRAR_EDUCATION_FORM,
    "registrar.subject_kind": REGISTRAR_SUBJECT_KIND,
    "ui.status": UI_STATUS,
}

_expected_total = 185
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
        for msgid, translations in messages.items():
            key = (ctx, msgid)
            if key in existing:
                continue
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            # AZ identity DOĞRUDUR bu faylda (bax modul başlığı).
            msgstr = msgid if lang == "az" else translations[lang]
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
