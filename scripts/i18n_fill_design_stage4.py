#!/usr/bin/env python3
"""EMSArena i18n — Dizayn Faza-4 (Stage-4) mətnləri (4 dil). İdempotent.

Mənbə: `docs/audits/2026-09-02/DESIGN_STAGE4_MSGIDS.txt` (282 sətir, 10
kontekst) — dərs yükü zənciri: TŞ mərkəzi, koordinator vizası, dekanlıq
təsdiqi, rektor baxışı, müəllim təsdiq/etiraz (commit `7de8926c`), + `apps/
workload`-un daha ƏVVƏLKI (commit `0d9e2b50`, "F0+F3+F4") baza modulundan
gələn `workload` / `workload.model` seçim və model-etiket kontekstləri —
onlar Stage-4-dən ƏVVƏL yazılıb, amma HEÇ VAXT kataloqa doldurulmayıb.

Yoxlama metodu: eyni «avtomatik skan (`i18n_source_scan.collect_source_msgids`)
+ əl ilə AST gəzintisi (modul-səviyyəli `_CTX`/`_CTX_OVERVIEW` və s. Name→str
həlli)» birləşməsi, AZ kataloqu ilə tutuşdurulub (bax
`i18n_fill_design_stage5_6.py` başlığındakı eyni metod). Nəticə 9 kontekstdə
(`accounts.workload*` 5 ədəd + `organizations.permission.label` + `profile.
sidebar` + `workload` + `workload.model`) CƏMİ 355 giriş verdi:

    accounts.workload            20
    accounts.workload_approval   48
    accounts.workload_center    117
    accounts.workload_overview   38
    accounts.workload_visa       43
    organizations.permission.label 11
    profile.sidebar               4   (Stage-6 skriptinin QƏSDƏN buraxdığı 4-ü)
    workload                     55   (0d9e2b50-dən — seçim etiketləri)
    workload.model                19   (0d9e2b50-dən — verbose_name cütləri)
    ─────────────────────────────────
    CƏMİ                         355

Bu ədəd audit sənədinin elan etdiyi 282-dən çoxdur, çünki sənəd YALNIZ Stage-4
commit-inin (`7de8926c`) əlavələrini sadalayır; `workload`/`workload.model`
kontekstləri isə DAHA ƏVVƏLKİ `0d9e2b50` commit-indən qalma, heç vaxt
tərcümə edilməmiş borcdur — `check_i18n_catalogs.py`-nin `source_missing`
ölçüsü committən asılı olmayıb yalnız "kodda var / kataloqda yoxdur" sualına
baxdığı üçün bu fərq HƏQİQİ, gizlədilməli borc deyil (bax modul aşağı hissəsi
— `--update` YOXDUR, hamısı doldurulur).

AZ: bütün 9 kontekstdə msgid ARTIQ Azərbaycanca UI/etiket mətnidir (heç biri
Django-nun avtomatik ingiliscə `verbose_name`/choice-key konvensiyası ilə
YAZILMAYIB) → `az_override` YOXDUR (identity: az msgstr == msgid). Bu,
`organizations.permission.label` üçün STAGE-2/3 skriptindəki presedentlə
eynidir (bax mövcud kataloqda: "Sillabuslara baxış" → az "Sillabuslara
baxış", en "View syllabi").

⚠️ PARALEL AGENT TƏHLÜKƏSİZLİYİ (bax `i18n_fill_design_stage2_3.py`):
     * mövcudluq yoxlaması `polib` ilə (bax `existing_pairs`);
     * YAZMADAN DƏRHAL ƏVVƏL fayl YENİDƏN oxunur (`fill()` daxilində);
     * yazma xam mətn ƏLAVƏSİ ilə — `polib.save()` İŞLƏDİLMİR. Yalnız
       ƏLAVƏ olunur — mövcud sətirlərə TOXUNULMUR, fuzzy flag-lar
       dəyişdirilmir.

⚠️ `makemessages` İŞLƏDİLMİR (əl ilə yazılmış blokları silə bilər).

İstifadə:  python scripts/i18n_fill_design_stage4.py
Sonra:     django-admin compilemessages && python scripts/check_i18n_catalogs.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def _e(en, ru, tr):
    return {"en": en, "ru": ru, "tr": tr}


# ─────────────────────────────────────────────────────────────────────────────
# accounts.workload — müəllim təsdiq/etiraz (ekran 12)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_WORKLOAD = {
    "Bölgü yalnız fakültə dilimlərinin hamısı təsdiqləndikdən sonra açılır.": _e(
        "Distribution opens only after all faculty slices have been approved.",
        "Распределение открывается только после утверждения всех факультетских долей.",
        "Dağıtım, yalnızca tüm fakülte dilimleri onaylandıktan sonra açılır.",
    ),
    "Etiraz bildir": _e("File an objection", "Подать возражение", "İtiraz bildir"),
    "Etiraz bölgünü dayandırmır — sətri yenidən bölün və ya etirazı qərarla bağlayın (qərar audit "
    "jurnalına yazılır).": _e(
        "An objection does not stop the distribution — either re-split the row or close the "
        "objection with a decision (the decision is recorded in the audit log).",
        "Возражение не останавливает распределение — перераспределите строку заново или закройте "
        "возражение решением (решение записывается в журнал аудита).",
        "İtiraz dağıtımı durdurmaz — satırı yeniden bölün veya itirazı bir kararla kapatın (karar "
        "denetim günlüğüne yazılır).",
    ),
    "Etiraz kafedra müdirinə və dekanlığa göndərilir. Mətn sonradan dəyişdirilmir.": _e(
        "The objection is sent to the department head and the dean's office. The text cannot be " "changed afterwards.",
        "Возражение отправляется заведующему кафедрой и деканату. Текст впоследствии не может быть " "изменён.",
        "İtiraz, bölüm başkanına ve dekanlığa gönderilir. Metin daha sonra değiştirilemez.",
    ),
    "Etiraz qəbul edilsin? Sətri yenidən bölməyi unutmayın.": _e(
        "Accept the objection? Remember to re-split the row.",
        "Принять возражение? Не забудьте перераспределить строку заново.",
        "İtiraz kabul edilsin mi? Satırı yeniden bölmeyi unutmayın.",
    ),
    "Etiraz rədd edilsin?": _e("Reject the objection?", "Отклонить возражение?", "İtiraz reddedilsin mi?"),
    "Etirazlarım": _e("My objections", "Мои возражения", "İtirazlarım"),
    "Fənn / iş": _e("Subject / task", "Дисциплина / работа", "Ders / iş"),
    "Göndər": _e("Send", "Отправить", "Gönder"),
    "Kafedra müdiri 3 iş günü ərzində cavab verir.": _e(
        "The department head responds within 3 business days.",
        "Заведующий кафедрой отвечает в течение 3 рабочих дней.",
        "Bölüm başkanı 3 iş günü içinde yanıt verir.",
    ),
    "Müəllim etirazları": _e("Teacher objections", "Возражения преподавателей", "Öğretmen itirazları"),
    "Qəbul et": _e("Accept", "Принять", "Kabul et"),
    "Rədd et": _e("Reject", "Отклонить", "Reddet"),
    "Seçin": _e("Select", "Выберите", "Seçin"),
    "Tapşırıq dekanlıq təsdiqini gözləyir": _e(
        "The task is awaiting the dean's office approval",
        "Задание ожидает утверждения деканата",
        "Görev dekanlık onayını bekliyor",
    ),
    "Yük üzrə etiraz bildir": _e(
        "File an objection about the load",
        "Подать возражение по нагрузке",
        "Yük hakkında itiraz bildir",
    ),
    "Yükü təsdiqlə": _e("Approve the load", "Утвердить нагрузку", "Yükü onayla"),
    "Yükü təsdiqləmisiniz": _e("You have approved the load", "Вы утвердили нагрузку", "Yükü onayladınız"),
    "İllik dərs yükünüzü təsdiqləyirsiniz? Təsdiq audit jurnalına yazılır.": _e(
        "Are you approving your annual teaching load? The approval is recorded in the audit log.",
        "Вы утверждаете свою годовую учебную нагрузку? Утверждение записывается в журнал аудита.",
        "Yıllık ders yükünüzü onaylıyor musunuz? Onay denetim günlüğüne yazılır.",
    ),
    "İzah": _e("Explanation", "Пояснение", "Açıklama"),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.workload_approval — koordinator vizası + dekanlıq təsdiqi (ekran 13/15)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_WORKLOAD_APPROVAL = {
    "%%d sətir seçilib": _e("%%d rows selected", "Выбрано строк: %%d", "%%d satır seçildi"),
    "%(name)s sətrini seç": _e("Select the %(name)s row", "Выбрать строку %(name)s", "%(name)s satırını seç"),
    "Arxiv rejimi": _e("Archive mode", "Режим архива", "Arşiv modu"),
    "Baxılıb": _e("Reviewed", "Рассмотрено", "İncelendi"),
    "Bu fakültə üçün göndərilmiş tapşırıq sətri tapılmadı.": _e(
        "No submitted task rows were found for this faculty.",
        "Для этого факультета не найдено отправленных строк задания.",
        "Bu fakülte için gönderilmiş görev satırı bulunamadı.",
    ),
    "Bu fakültə üçün sətir yoxdur.": _e(
        "There are no rows for this faculty.",
        "Для этого факультета нет строк.",
        "Bu fakülte için satır yok.",
    ),
    "CƏMİ KREDİT": _e("TOTAL CREDITS", "ВСЕГО КРЕДИТОВ", "TOPLAM KREDİ"),
    "Dilim qərarlarının tarixçəsi": _e(
        "History of slice decisions", "История решений по доле", "Dilim kararlarının geçmişi"
    ),
    "Dilim təsdiqlənsin? Təsdiqdən sonra dilim yalnız oxunuş rejimində qalır və kafedra bölgüsü "
    "açılır.": _e(
        "Approve the slice? After approval, the slice remains read-only and the department " "distribution opens.",
        "Утвердить долю? После утверждения доля остаётся доступной только для чтения, и "
        "открывается распределение по кафедрам.",
        "Dilim onaylansın mı? Onaydan sonra dilim salt okunur kalır ve bölüm dağıtımı açılır.",
    ),
    "Dilimdə sətir yoxdur": _e("There are no rows in the slice", "В доле нет строк", "Dilimde satır yok"),
    "Dilimi TƏSDİQLƏ": _e("APPROVE the slice", "УТВЕРДИТЬ долю", "Dilimi ONAYLA"),
    "DİLİMİN CƏMİ SAATI": _e("TOTAL HOURS OF THE SLICE", "ВСЕГО ЧАСОВ ДОЛИ", "DİLİMİN TOPLAM SAATİ"),
    "Fakültə": _e("Faculty", "Факультет", "Fakülte"),
    "Fakültə yükü": _e("Faculty load", "Нагрузка факультета", "Fakülte yükü"),
    "Fənn": _e("Subject", "Дисциплина", "Ders"),
    "Gözləyir": _e("Pending", "Ожидает", "Bekliyor"),
    "Hamısı": _e("All", "Все", "Tümü"),
    "Hələ qərar verilməyib": _e("No decision has been made yet", "Решение ещё не принято", "Henüz karar verilmedi"),
    "Hərəkət jurnalı": _e("Action log", "Журнал действий", "İşlem günlüğü"),
    "Kafedra": _e("Department", "Кафедра", "Bölüm"),
    "Kafedralar üzrə yekun": _e("Summary by department", "Итог по кафедрам", "Bölümlere göre özet"),
    "Kafedraların yük paketlərini fakültə dilimi üzrə təsdiqləyin və ya səbəblə qaytarın.": _e(
        "Approve the departments' load packages under the faculty slice, or return them with a " "reason.",
        "Утвердите пакеты нагрузки кафедр в рамках факультетской доли или верните их с указанием " "причины.",
        "Bölümlerin yük paketlerini fakülte dilimi kapsamında onaylayın veya bir gerekçeyle geri " "gönderin.",
    ),
    "Keçmiş tədris ili yalnız oxunuş üçün açıqdır.": _e(
        "A past academic year is open for reading only.",
        "Прошедший учебный год открыт только для чтения.",
        "Geçmiş akademik yıl yalnızca okumaya açıktır.",
    ),
    "Koordinator vizası": _e("Coordinator's visa", "Виза координатора", "Koordinatör vizesi"),
    "Kredit": _e("Credit", "Кредит", "Kredi"),
    "Nəticə: %(count)d sətir": _e("Result: %(count)d rows", "Результат: %(count)d строк", "Sonuç: %(count)d satır"),
    "Qaytar": _e("Return", "Вернуть", "Geri gönder"),
    "Qaytarma səbəbi": _e("Reason for returning", "Причина возврата", "Geri gönderme nedeni"),
    "Qaytarma səbəbi tədris şöbəsinə və kafedra rəhbərinə bildiriş kimi gedir və audit jurnalına "
    "yazılır.": _e(
        "The return reason is sent as a notification to the teaching office and the department "
        "head, and is recorded in the audit log.",
        "Причина возврата отправляется в виде уведомления в учебный отдел и заведующему кафедрой "
        "и записывается в журнал аудита.",
        "Geri gönderme nedeni öğretim işleri dairesine ve bölüm başkanına bildirim olarak gider ve "
        "denetim günlüğüne yazılır.",
    ),
    "Qruplar": _e("Groups", "Группы", "Gruplar"),
    "Saat": _e("Hour", "Час", "Saat"),
    "Semestr": _e("Semester", "Семестр", "Dönem"),
    "Seç": _e("Select", "Выбрать", "Seç"),
    "Seçilmiş sətirləri qaytar": _e(
        "Return the selected rows", "Вернуть выбранные строки", "Seçilen satırları geri gönder"
    ),
    "Seçilmişləri qaytar": _e("Return the selected", "Вернуть выбранные", "Seçilenleri geri gönder"),
    "Status": _e("Status", "Статус", "Durum"),
    "Sətir": _e("Row", "Строка", "Satır"),
    "Sətir seçilməyib": _e("No row selected", "Строка не выбрана", "Satır seçilmedi"),
    "Tarixçə": _e("History", "История", "Geçmiş"),
    "Tədris ili": _e("Academic year", "Учебный год", "Akademik yıl"),
    "Təsdiq görünüşləri": _e("Approval views", "Представления утверждения", "Onay görünümleri"),
    "Təsdiq növbəsi": _e("Approval queue", "Очередь на утверждение", "Onay sırası"),
    "Viza": _e("Visa", "Виза", "Vize"),
    "Yük təsdiqi üçün «Tapşırığı təsdiqləmək» səlahiyyəti tələb olunur.": _e(
        'The "Approve the task" permission is required for load approval.',
        "Для утверждения нагрузки требуется полномочие «Утвердить задание».",
        'Yük onayı için "Görevi onayla" yetkisi gereklidir.',
    ),
    "İRADLI SƏTİR": _e("FLAGGED ROW", "СТРОКА С ЗАМЕЧАНИЕМ", "SORUNLU SATIR"),
    "İXTİSAS SAYI": _e("NUMBER OF PROGRAMMES", "КОЛИЧЕСТВО СПЕЦИАЛЬНОСТЕЙ", "PROGRAM SAYISI"),
    "İradlı": _e("Flagged", "С замечанием", "Sorunlu"),
    "İxtisas": _e("Programme", "Специальность", "Program"),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.workload_center — TŞ mərkəzi (ekran 12: yaratmaq, paylamaq, idxal)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_WORKLOAD_CENTER = {
    ".xlsx və ya .xlsm · maksimum 10 MB · sütun adları dəyişdirilməməlidir.": _e(
        ".xlsx or .xlsm · maximum 10 MB · column names must not be changed.",
        ".xlsx или .xlsm · максимум 10 МБ · названия столбцов менять нельзя.",
        ".xlsx veya .xlsm · maksimum 10 MB · sütun adları değiştirilmemelidir.",
    ),
    "Arxiv rejimi": _e("Archive mode", "Режим архива", "Arşiv modu"),
    "Bax": _e("View", "Просмотр", "Görüntüle"),
    "Birl.": _e("Comb.", "Объед.", "Birl."),
    "Boş buraxsanız kafedranın bütün ixtisasları götürülür.": _e(
        "If left empty, all of the department's programmes are taken.",
        "Если оставить пустым, будут взяты все специальности кафедры.",
        "Boş bırakırsanız bölümün tüm programları alınır.",
    ),
    "Bu bölmədə hələ məlumat yoxdur": _e(
        "There is no data in this section yet",
        "В этом разделе пока нет данных",
        "Bu bölümde henüz veri yok",
    ),
    "Bu sətirlərdə ixtisas göstərilməyib — dekanlıq dilimi yaranmır və sənəd göndərilmir.": _e(
        "No programme is specified on these rows — a dean's-office slice is not created and the "
        "document is not sent.",
        "В этих строках не указана специальность — доля деканата не создаётся, и документ не " "отправляется.",
        "Bu satırlarda program belirtilmemiş — dekanlık dilimi oluşturulmaz ve belge gönderilmez.",
    ),
    "Buraxılış": _e("Graduation", "Выпуск", "Mezuniyet"),
    "Bölüşdürülüb": _e("Distributed", "Распределено", "Dağıtıldı"),
    "CƏMİ KAFEDRA": _e("TOTAL DEPARTMENTS", "ВСЕГО КАФЕДР", "TOPLAM BÖLÜM"),
    "CƏMİ KREDİT": _e("TOTAL CREDITS", "ВСЕГО КРЕДИТОВ", "TOPLAM KREDİ"),
    "CƏMİ SAAT": _e("TOTAL HOURS", "ВСЕГО ЧАСОВ", "TOPLAM SAAT"),
    "Cəmi": _e("Total", "Всего", "Toplam"),
    "Dekan qərarı": _e("Dean's decision", "Решение декана", "Dekan kararı"),
    "Dekanlıqlara göndər": _e("Send to the deans' offices", "Отправить в деканаты", "Dekanlıklara gönder"),
    "Doktorant": _e("Doctoral student", "Докторант", "Doktora öğrencisi"),
    "Dərs yükü mərkəzinin görünüşləri": _e(
        "Views of the teaching load center",
        "Представления центра учебной нагрузки",
        "Ders yükü merkezinin görünümleri",
    ),
    "Dərs yükü mərkəzinə giriş üçün «Tədris tapşırığını idarə etmək» səlahiyyəti tələb olunur.": _e(
        'The "Manage the teaching task" permission is required to access the teaching load center.',
        "Для доступа к центру учебной нагрузки требуется полномочие «Управлять учебным заданием».",
        'Ders yükü merkezine erişim için "Öğretim görevini yönet" yetkisi gereklidir.',
    ),
    "Excel faylı": _e("Excel file", "Файл Excel", "Excel dosyası"),
    "Excel faylı yüklə": _e("Upload an Excel file", "Загрузить файл Excel", "Excel dosyası yükle"),
    "Excel idxalının mərhələləri": _e("Steps of the Excel import", "Этапы импорта Excel", "Excel içe aktarma adımları"),
    "Excel import": _e("Excel import", "Импорт Excel", "Excel içe aktarma"),
    "FAKÜLTƏ DİLİMİ": _e("FACULTY SLICE", "ДОЛЯ ФАКУЛЬТЕТА", "FAKÜLTE DİLİMİ"),
    "Fakültə": _e("Faculty", "Факультет", "Fakülte"),
    "Fakültə dilimləri": _e("Faculty slices", "Доли факультетов", "Fakülte dilimleri"),
    "Fayl yüklə": _e("Upload a file", "Загрузить файл", "Dosya yükle"),
    "Fayldakı ad": _e("Name in the file", "Имя в файле", "Dosyadaki ad"),
    "Faylı oxu": _e("Read the file", "Прочитать файл", "Dosyayı oku"),
    "Forma": _e("Form", "Форма", "Form"),
    "Fənn": _e("Subject", "Дисциплина", "Ders"),
    "GÖNDƏRİLMİŞ": _e("SENT", "ОТПРАВЛЕНО", "GÖNDERİLDİ"),
    "GÖZLƏYİR": _e("PENDING", "ОЖИДАЕТ", "BEKLİYOR"),
    "Göndərilib": _e("Sent", "Отправлено", "Gönderildi"),
    "Göndərmədən əvvəl yoxlama": _e("Check before sending", "Проверка перед отправкой", "Göndermeden önce kontrol"),
    "Hamısı": _e("All", "Все", "Tümü"),
    "Hesabatlar": _e("Reports", "Отчёты", "Raporlar"),
    "Kafedra": _e("Department", "Кафедра", "Bölüm"),
    "Kafedra tapılmadı": _e("Department not found", "Кафедра не найдена", "Bölüm bulunamadı"),
    "Kafedra tapşırıqları": _e("Department tasks", "Задания кафедры", "Bölüm görevleri"),
    "Kafedra üçün seçilmiş tədris ilinin sənədi yaradılır (kafedraya ildə bir sənəd).": _e(
        "A document for the selected academic year is created for the department (one document "
        "per department per year).",
        "Для кафедры создаётся документ на выбранный учебный год (один документ на кафедру в " "год).",
        "Bölüm için seçilen akademik yılın belgesi oluşturulur (bölüm başına yılda bir belge).",
    ),
    "Kataloq uyğunluğu": _e("Catalog matching", "Соответствие каталогу", "Katalog eşleşmesi"),
    "Keçmiş tədris ili yalnız oxunuş üçün açıqdır — yazma əməlləri bağlıdır.": _e(
        "A past academic year is open for reading only — write operations are disabled.",
        "Прошедший учебный год открыт только для чтения — операции записи отключены.",
        "Geçmiş akademik yıl yalnızca okumaya açıktır — yazma işlemleri kapalıdır.",
    ),
    "Koordinator vizası": _e("Coordinator's visa", "Виза координатора", "Koordinatör vizesi"),
    "Kredit": _e("Credit", "Кредит", "Kredi"),
    "Laboratoriya (plan/cəmi)": _e("Laboratory (plan/total)", "Лаборатория (план/итого)", "Laboratuvar (plan/toplam)"),
    "Ləğv et": _e("Cancel", "Отменить", "İptal et"),
    "Marşrutsuz sətirlər": _e("Unrouted rows", "Строки без маршрута", "Yönlendirilmemiş satırlar"),
    "Mühazirə (plan/cəmi)": _e("Lecture (plan/total)", "Лекция (план/итого)", "Teorik ders (plan/toplam)"),
    "MƏTN KİMİ QALAN": _e("LEFT AS TEXT", "ОСТАВЛЕНО КАК ТЕКСТ", "METİN OLARAK KALAN"),
    "Məsləhət": _e("Consultation", "Консультация", "Danışma"),
    "Mətn kimi qalacaq": _e("Will remain as text", "Останется как текст", "Metin olarak kalacak"),
    "Növ": _e("Type", "Тип", "Tür"),
    "Nəticə": _e("Result", "Результат", "Sonuç"),
    "Nəticə: %(count)d kafedra": _e(
        "Result: %(count)d departments", "Результат: %(count)d кафедр", "Sonuç: %(count)d bölüm"
    ),
    "Nəticə: %(count)d sətir": _e("Result: %(count)d rows", "Результат: %(count)d строк", "Sonuç: %(count)d satır"),
    "PAYIZ CƏMİ": _e("FALL TOTAL", "ИТОГО ОСЕНЬ", "GÜZ TOPLAMI"),
    "Parametrlər": _e("Parameters", "Параметры", "Parametreler"),
    "Payız": _e("Fall", "Осень", "Güz"),
    "QAYTARILIB": _e("RETURNED", "ВОЗВРАЩЕНО", "GERİ GÖNDERİLDİ"),
    "QAYTARILMIŞ": _e("RETURNED", "ВОЗВРАЩЁННЫЕ", "GERİ GÖNDERİLMİŞ"),
    "Qaralama": _e("Draft", "Черновик", "Taslak"),
    "Qaytarılan sətirlər": _e("Returned rows", "Возвращённые строки", "Geri gönderilen satırlar"),
    "Qaytarılıb": _e("Returned", "Возвращено", "Geri gönderildi"),
    "Qruplar": _e("Groups", "Группы", "Gruplar"),
    "Rəsmi TAPŞIRIQ şablonu (.xlsx / .xlsm, ≤10 MB). Kataloqda tapılmayan fənn və qruplar MƏTN "
    "kimi saxlanılır və sonradan bağlana bilər.": _e(
        "The official TASK template (.xlsx / .xlsm, ≤10 MB). Subjects and groups not found in the "
        "catalog are kept as TEXT and can be linked later.",
        "Официальный шаблон ЗАДАНИЯ (.xlsx / .xlsm, ≤10 МБ). Дисциплины и группы, не найденные в "
        "каталоге, сохраняются как ТЕКСТ и могут быть привязаны позже.",
        "Resmi GÖREV şablonu (.xlsx / .xlsm, ≤10 MB). Katalogda bulunamayan ders ve gruplar METİN "
        "olarak saklanır ve daha sonra bağlanabilir.",
    ),
    "Semestr": _e("Semester", "Семестр", "Dönem"),
    "Seminar (plan/cəmi)": _e("Seminar (plan/total)", "Семинар (план/итого)", "Seminer (plan/toplam)"),
    "Seçilmiş filtrlərə uyğun kafedra yoxdur — «Sıfırla» ilə filtrləri təmizləyin.": _e(
        'No department matches the selected filters — clear the filters with "Reset".',
        "Нет кафедры, соответствующей выбранным фильтрам — очистите фильтры с помощью «Сбросить».",
        'Seçilen filtrelere uyan bölüm yok — "Sıfırla" ile filtreleri temizleyin.',
    ),
    "Seçilmiş filtrlərə uyğun sətir tapılmadı": _e(
        "No row matches the selected filters",
        "Не найдено строк, соответствующих выбранным фильтрам",
        "Seçilen filtrelere uyan satır bulunamadı",
    ),
    "Seçilmiş ixtisasların TƏSDİQLƏNMİŞ planından sətirlər yaradılır. Əməl idempotentdir — mövcud "
    "sətir təkrarlanmır və heç nə əzilmir.": _e(
        "Rows are created from the APPROVED curriculum of the selected programmes. The action is "
        "idempotent — existing rows are not duplicated and nothing is overwritten.",
        "Строки создаются из УТВЕРЖДЁННОГО учебного плана выбранных специальностей. Действие "
        "идемпотентно — существующие строки не дублируются, ничего не перезаписывается.",
        "Satırlar, seçilen programların ONAYLANMIŞ müfredatından oluşturulur. İşlem idempotenttir "
        "— mevcut satır tekrarlanmaz ve hiçbir şey üzerine yazılmaz.",
    ),
    "Seçilmiş kafedra və tədris ili üçün sənəd yaradılmayıb — «Yeni tapşırıq».": _e(
        'No document has been created for the selected department and academic year — "New task".',
        "Для выбранной кафедры и учебного года документ не создан — «Новое задание».",
        'Seçilen bölüm ve akademik yıl için belge oluşturulmamış — "Yeni görev".',
    ),
    "Seçin": _e("Select", "Выберите", "Seçin"),
    "Status": _e("Status", "Статус", "Durum"),
    "SƏTİR": _e("ROW", "СТРОКА", "SATIR"),
    "Səhifələmə": _e("Pagination", "Постраничная навигация", "Sayfalama"),
    "Sənəd dekanlıqlara göndərilsin? Göndərişdən sonra sətirlər yalnız qaytarıldıqda redaktə "
    "olunur.": _e(
        "Send the document to the deans' offices? After sending, rows can only be edited once " "returned.",
        "Отправить документ в деканаты? После отправки строки редактируются только после " "возврата.",
        "Belge dekanlıklara gönderilsin mi? Gönderimden sonra satırlar yalnızca geri " "gönderildiğinde düzenlenir.",
    ),
    "Sənəd hələ göndərilməyib — dilim yoxdur.": _e(
        "The document has not been sent yet — there is no slice.",
        "Документ ещё не отправлен — доли нет.",
        "Belge henüz gönderilmemiş — dilim yok.",
    ),
    "Sətirləri gətir": _e("Bring in rows", "Загрузить строки", "Satırları getir"),
    "Səviyyə": _e("Level", "Уровень", "Seviye"),
    "Tapşırıq dövriyyəsi başlayandan sonra buradakı hesabatlar avtomatik dolacaq.": _e(
        "Once the task cycle begins, the reports here will fill in automatically.",
        "После начала цикла задания отчёты здесь будут заполняться автоматически.",
        "Görev döngüsü başladıktan sonra buradaki raporlar otomatik olarak dolacaktır.",
    ),
    "Tapşırıq görünüşləri": _e("Task views", "Представления задания", "Görev görünümleri"),
    "Tapşırıq redaktoru": _e("Task editor", "Редактор задания", "Görev düzenleyici"),
    "Tapşırıq yarat": _e("Create a task", "Создать задание", "Görev oluştur"),
    "Tapşırıq yoxdur": _e("There is no task", "Задания нет", "Görev yok"),
    "Tapşırıqlar": _e("Tasks", "Задания", "Görevler"),
    "TƏSDİQLƏNMİŞ": _e("APPROVED", "УТВЕРЖДЕНО", "ONAYLANMIŞ"),
    "TƏSDİQLƏNİB": _e("APPROVED", "УТВЕРЖДЕНО", "ONAYLANDI"),
    "Təcrübə": _e("Practicum", "Практика", "Staj"),
    "Tədris ili": _e("Academic year", "Учебный год", "Akademik yıl"),
    "Tədris planından gətir": _e("Bring in from the curriculum", "Загрузить из учебного плана", "Müfredattan getir"),
    "Tələbə": _e("Student", "Студент", "Öğrenci"),
    "Təsdiqlənib": _e("Approved", "Утверждено", "Onaylandı"),
    "UYĞUNLAŞDI": _e("MATCHED", "СОПОСТАВЛЕНО", "EŞLEŞTİ"),
    "Uyğunlaşdı": _e("Matched", "Сопоставлено", "Eşleşti"),
    "Uyğunlaşdırma": _e("Matching", "Сопоставление", "Eşleştirme"),
    "Viza": _e("Visa", "Виза", "Vize"),
    "YAZ CƏMİ": _e("SPRING TOTAL", "ИТОГО ВЕСНА", "BAHAR TOPLAMI"),
    "Yarımq.": _e("Subgr.", "Подгр.", "Alt gr."),
    "Yaz": _e("Spring", "Весна", "Bahar"),
    "Yeni tapşırıq": _e("New task", "Новое задание", "Yeni görev"),
    "kr": _e("cr", "кр", "kr"),
    "plan yoxdur": _e("no plan", "плана нет", "plan yok"),
    "redaktə dövrü %(n)s": _e("edit cycle %(n)s", "цикл редактирования %(n)s", "düzenleme döngüsü %(n)s"),
    "saat": _e("hour", "час", "saat"),
    "sətir": _e("row", "строка", "satır"),
    "«Sıfırla» ilə filtrləri təmizləyin və ya plandan sətir gətirin.": _e(
        'Clear the filters with "Reset", or bring in rows from the curriculum.',
        "Очистите фильтры с помощью «Сбросить» или загрузите строки из учебного плана.",
        'Filtreleri "Sıfırla" ile temizleyin veya müfredattan satır getirin.',
    ),
    "ÜMUMİ SAAT": _e("TOTAL HOURS", "ВСЕГО ЧАСОВ", "TOPLAM SAAT"),
    "İdarə paneli": _e("Dashboard", "Панель управления", "Kontrol paneli"),
    "İdxal et": _e("Import", "Импортировать", "İçe aktar"),
    "İdxal sətirləri mövcud QARALAMA sənədə əlavə olunur — «Tapşırıqlar» görünüşündən kafedra "
    "seçin.": _e(
        "Imported rows are added to the existing DRAFT document — select the department from the " '"Tasks" view.',
        "Импортированные строки добавляются в существующий документ-ЧЕРНОВИК — выберите кафедру в "
        "представлении «Задания».",
        'İçe aktarılan satırlar mevcut TASLAK belgeye eklenir — bölümü "Görevler" görünümünden ' "seçin.",
    ),
    "İlin tapşırıq sətirlərini yaradın, kafedralara paylayın, plandan və ya Excel-dən gətirin, "
    "dekanlıq təsdiqini izləyin.": _e(
        "Create the year's task rows, distribute them to departments, bring them in from the "
        "curriculum or from Excel, and track the dean's office approval.",
        "Создавайте строки задания на год, распределяйте их по кафедрам, загружайте из учебного "
        "плана или Excel, отслеживайте утверждение деканатом.",
        "Yılın görev satırlarını oluşturun, bölümlere dağıtın, müfredattan veya Excel'den getirin, "
        "dekanlık onayını takip edin.",
    ),
    "İmtahan": _e("Exam", "Экзамен", "Sınav"),
    "İxtisas": _e("Programme", "Специальность", "Program"),
    "İxtisaslar": _e("Programmes", "Специальности", "Programlar"),
    "İzləmə": _e("Tracking", "Отслеживание", "İzleme"),
    "Şərh": _e("Comment", "Комментарий", "Yorum"),
    "Əvvəlcə tapşırıq seçin": _e("Select a task first", "Сначала выберите задание", "Önce bir görev seçin"),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.workload_overview — rektor/TŞ ümumi baxış (ekran 17)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_WORKLOAD_OVERVIEW = {
    "%(fac)d fakültə · %(chair)d kafedra · %(teacher)d müəllim": _e(
        "%(fac)d faculties · %(chair)d departments · %(teacher)d teachers",
        "%(fac)d факультетов · %(chair)d кафедр · %(teacher)d преподавателей",
        "%(fac)d fakülte · %(chair)d bölüm · %(teacher)d öğretmen",
    ),
    "%(n)s vakant saat": _e("%(n)s vacant hours", "%(n)s вакантных часов", "%(n)s boş saat"),
    "%(pct)d%% bölünüb": _e("%(pct)d%% distributed", "%(pct)d%% распределено", "%(pct)d%% dağıtıldı"),
    "Bu bölmədə hələ məlumat yoxdur": _e(
        "There is no data in this section yet",
        "В этом разделе пока нет данных",
        "Bu bölümde henüz veri yok",
    ),
    "Bu tədris ili üçün tapşırıq yoxdur": _e(
        "There is no task for this academic year",
        "Для этого учебного года нет задания",
        "Bu akademik yıl için görev yok",
    ),
    "BÖLÜNMÜŞ YÜK": _e("DISTRIBUTED LOAD", "РАСПРЕДЕЛЁННАЯ НАГРУЗКА", "DAĞITILAN YÜK"),
    "Bölgü": _e("Distribution", "Распределение", "Dağıtım"),
    "Bölünmüş": _e("Distributed", "Распределено", "Dağıtılmış"),
    "Diqqət tələb edən kafedralar": _e(
        "Departments requiring attention",
        "Кафедры, требующие внимания",
        "Dikkat gerektiren bölümler",
    ),
    "Elmi Şura və nazirlik formatında hazır hesabatlar növbəti mərhələdə əlavə olunacaq.": _e(
        "Ready-made reports in the Academic Council and ministry format will be added in the next " "phase.",
        "Готовые отчёты в формате Учёного совета и министерства будут добавлены на следующем " "этапе.",
        "Bilim Kurulu ve bakanlık formatında hazır raporlar bir sonraki aşamada eklenecektir.",
    ),
    "Fakültə": _e("Faculty", "Факультет", "Fakülte"),
    "Fakültələr": _e("Faculties", "Факультеты", "Fakülteler"),
    "Fakültələr üzrə bölgü": _e("Distribution by faculty", "Распределение по факультетам", "Fakültelere göre dağıtım"),
    "Fakültələr üzrə yük mənzərəsi": _e(
        "Load picture by faculty",
        "Картина нагрузки по факультетам",
        "Fakültelere göre yük görünümü",
    ),
    "Gediş": _e("Outflow", "Отток", "Çıkış"),
    "Hamısı": _e("All", "Все", "Tümü"),
    "Hesabatlar": _e("Reports", "Отчёты", "Raporlar"),
    "Kafedra": _e("Department", "Кафедра", "Bölüm"),
    "Kafedra bölgüsünün vəziyyəti": _e(
        "Status of the department distribution",
        "Статус распределения по кафедрам",
        "Bölüm dağıtımının durumu",
    ),
    "Kafedralar": _e("Departments", "Кафедры", "Bölümler"),
    "Müəllim": _e("Teacher", "Преподаватель", "Öğretmen"),
    "NORMA AŞIMI": _e("OVER-NORM", "ПРЕВЫШЕНИЕ НОРМЫ", "NORM AŞIMI"),
    "Norma üstü": _e("Over the norm", "Сверх нормы", "Norm üstü"),
    "Nəticə: %(count)d kafedra": _e(
        "Result: %(count)d departments", "Результат: %(count)d кафедр", "Sonuç: %(count)d bölüm"
    ),
    "Risk siqnalı yoxdur.": _e("There is no risk signal.", "Сигналов риска нет.", "Risk sinyali yok."),
    "Status": _e("Status", "Статус", "Durum"),
    "Tapşırıq": _e("Task", "Задание", "Görev"),
    "Tapşırıqdan müəllim təsdiqinə qədər bütün mərhələlərin universitet üzrə vəziyyəti.": _e(
        "The university-wide status of all stages, from the task to teacher approval.",
        "Общеуниверситетский статус всех этапов, от задания до утверждения преподавателем.",
        "Görevden öğretmen onayına kadar tüm aşamaların üniversite genelindeki durumu.",
    ),
    "Tədris ili": _e("Academic year", "Учебный год", "Akademik yıl"),
    "Tədris şöbəsi tapşırıqları yaradandan sonra rəqəmlər burada görünəcək.": _e(
        "Once the teaching office creates the tasks, the figures will appear here.",
        "После того как учебный отдел создаст задания, здесь появятся цифры.",
        "Öğretim işleri dairesi görevleri oluşturduktan sonra rakamlar burada görünecektir.",
    ),
    "Təsdiq axını": _e("Approval flow", "Поток утверждения", "Onay akışı"),
    "VAKANT SAAT": _e("VACANT HOURS", "ВАКАНТНЫЕ ЧАСЫ", "BOŞ SAAT"),
    "Vakant": _e("Vacant", "Вакантно", "Boş"),
    "müəllim sayı": _e("number of teachers", "количество преподавателей", "öğretmen sayısı"),
    "ÜMUMİ TƏDRİS YÜKÜ": _e("TOTAL TEACHING LOAD", "ОБЩАЯ УЧЕБНАЯ НАГРУЗКА", "TOPLAM ÖĞRETİM YÜKÜ"),
    "Ümumi baxış": _e("Overview", "Обзор", "Genel bakış"),
    "Ümumi baxış üçün «Dərs yükü hesabatları» səlahiyyəti tələb olunur.": _e(
        'The "Teaching load reports" permission is required for the overview.',
        "Для обзора требуется полномочие «Отчёты по учебной нагрузке».",
        'Genel bakış için "Ders yükü raporları" yetkisi gereklidir.',
    ),
    "Ümumi baxışın görünüşləri": _e("Views of the overview", "Представления обзора", "Genel bakışın görünümleri"),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.workload_visa — kafedra müdiri/ixtisas vizası (ekran 16)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_WORKLOAD_VISA = {
    "%(pct)d%% baxılıb": _e("%(pct)d%% reviewed", "%(pct)d%% рассмотрено", "%(pct)d%% incelendi"),
    "Arxiv rejimi": _e("Archive mode", "Режим архива", "Arşiv modu"),
    "Axtarış": _e("Search", "Поиск", "Ara"),
    "BAXILIB": _e("REVIEWED", "РАССМОТРЕНО", "İNCELENDİ"),
    "Baxdım": _e("Reviewed", "Просмотрено", "İnceledim"),
    "Baxılıb": _e("Reviewed", "Рассмотрено", "İncelendi"),
    "Fənn": _e("Subject", "Дисциплина", "Ders"),
    "Fənn və ya qrup": _e("Subject or group", "Дисциплина или группа", "Ders veya grup"),
    "GÖZLƏYİR": _e("PENDING", "ОЖИДАЕТ", "BEKLİYOR"),
    "Gözləyir": _e("Pending", "Ожидает", "Bekliyor"),
    "Gözləyən bütün sətirlərə viza verilsin? İradlı sətirlərə toxunulmayacaq.": _e(
        "Give visa to all pending rows? Flagged rows will not be touched.",
        "Выдать визу всем ожидающим строкам? Строки с замечаниями затронуты не будут.",
        "Bekleyen tüm satırlara vize verilsin mi? Sorunlu satırlara dokunulmayacak.",
    ),
    "Hamısı": _e("All", "Все", "Tümü"),
    "Hamısına viza ver": _e("Give visa to all", "Выдать визу всем", "Hepsine vize ver"),
    "Hələ heç bir viza verməmisiniz.": _e(
        "You have not given any visa yet.",
        "Вы ещё не выдали ни одной визы.",
        "Henüz hiçbir vize vermediniz.",
    ),
    "Kafedra müdirinə çatmazdan əvvəl öz ixtisasınızın hər yük sətrini yoxlayın: viza verin və ya "
    "irad yazın.": _e(
        "Before it reaches the department head, review every load row of your programme: give a "
        "visa or write a note.",
        "Прежде чем это дойдёт до заведующего кафедрой, проверьте каждую строку нагрузки вашей "
        "специальности: выдайте визу или напишите замечание.",
        "Bölüm başkanına ulaşmadan önce kendi programınızın her yük satırını inceleyin: vize " "verin veya not yazın.",
    ),
    "Keçmiş tədris ili yalnız oxunuş üçün açıqdır — viza mərhələsi bağlıdır.": _e(
        "A past academic year is open for reading only — the visa stage is closed.",
        "Прошедший учебный год открыт только для чтения — этап визирования закрыт.",
        "Geçmiş akademik yıl yalnızca okumaya açıktır — vize aşaması kapalıdır.",
    ),
    "Kredit": _e("Credit", "Кредит", "Kredi"),
    "Mənim hərəkətlərim": _e("My actions", "Мои действия", "Eylemlerim"),
    "Nəticə: %(count)d sətir": _e("Result: %(count)d rows", "Результат: %(count)d строк", "Sonuç: %(count)d satır"),
    "Qruplar": _e("Groups", "Группы", "Gruplar"),
    "Qərar": _e("Decision", "Решение", "Karar"),
    "Saat": _e("Hour", "Час", "Saat"),
    "Semestr": _e("Semester", "Семестр", "Dönem"),
    "Seçilmiş filtrlərə uyğun sətir tapılmadı": _e(
        "No row matches the selected filters",
        "Не найдено строк, соответствующих выбранным фильтрам",
        "Seçilen filtrelere uyan satır bulunamadı",
    ),
    "Sizin ixtisasınıza aid göndərilmiş tapşırıq sətri yoxdur.": _e(
        "There are no submitted task rows for your programme.",
        "Для вашей специальности нет отправленных строк задания.",
        "Programınıza ait gönderilmiş görev satırı yok.",
    ),
    "SƏTİR": _e("ROW", "СТРОКА", "SATIR"),
    "Səviyyə": _e("Level", "Уровень", "Seviye"),
    "Tarix": _e("Date", "Дата", "Tarih"),
    "Tədris ili": _e("Academic year", "Учебный год", "Akademik yıl"),
    "Viza": _e("Visa", "Виза", "Vize"),
    "Viza görünüşləri": _e("Visa views", "Представления визирования", "Vize görünümleri"),
    "Viza növbəsi": _e("Visa queue", "Очередь визирования", "Vize sırası"),
    "Viza vermək üçün «Tapşırıq sətirlərinə viza vermək» səlahiyyəti tələb olunur.": _e(
        'The "Give visa to task rows" permission is required to give a visa.',
        "Для выдачи визы требуется полномочие «Визировать строки задания».",
        'Vize vermek için "Görev satırlarına vize ver" yetkisi gereklidir.',
    ),
    "Üzvlüyünüzdə ixtisas əhatəsi təyin edilməyib — administrator ilə əlaqə saxlayın.": _e(
        "No programme scope has been assigned to your membership — contact the administrator.",
        "Для вашего членства не назначен охват по специальности — обратитесь к администратору.",
        "Üyeliğinizde program kapsamı atanmamış — yöneticiyle iletişime geçin.",
    ),
    "İRADLI": _e("FLAGGED", "С ЗАМЕЧАНИЕМ", "SORUNLU"),
    "İrad": _e("Note", "Замечание", "Not"),
    "İrad bildir": _e("Report a note", "Оставить замечание", "Not bildir"),
    "İradlı": _e("Flagged", "С замечанием", "Sorunlu"),
    "İradı göndər": _e("Send the note", "Отправить замечание", "Notu gönder"),
    "Şərh": _e("Comment", "Комментарий", "Yorum"),
    "Şərh kafedraya və dekana görünəcək. İrad yazılan sətir «vizalanmış» sayılmır.": _e(
        "The comment will be visible to the department and the dean. A row with a note is not " 'counted as "visaed".',
        "Комментарий будет виден кафедре и декану. Строка с замечанием не считается " "«завизированной».",
        'Yorum bölüme ve dekana görünecektir. Not yazılan satır "vizelenmiş" sayılmaz.',
    ),
    "Şərh yazılmadan irad göndərilə bilməz.": _e(
        "A note cannot be sent without writing a comment.",
        "Замечание нельзя отправить без комментария.",
        "Yorum yazılmadan not gönderilemez.",
    ),
    "Əməllər": _e("Actions", "Действия", "İşlemler"),
}

# ─────────────────────────────────────────────────────────────────────────────
# organizations.permission.label — Stage-4 dərs yükü icazələri (11)
# ─────────────────────────────────────────────────────────────────────────────
ORGANIZATIONS_PERMISSION_LABEL = {
    "Dərs yükü hesabatları və ixracı": _e(
        "Teaching load reports and export",
        "Отчёты и экспорт учебной нагрузки",
        "Ders yükü raporları ve dışa aktarma",
    ),
    "Dərs yükünü müəllimlərə bölmək": _e(
        "Distribute the teaching load to teachers",
        "Распределять учебную нагрузку между преподавателями",
        "Ders yükünü öğretmenlere dağıtmak",
    ),
    "Dərs yükünə baxış": _e("View the teaching load", "Просмотр учебной нагрузки", "Ders yükünü görüntülemek"),
    "Jurnala alt qrupdan tələbə əlavə etmək/çıxarmaq": _e(
        "Add/remove a student to/from the journal from a subgroup",
        "Добавлять/удалять студента в журнал из подгруппы",
        "Jurnala alt gruptan öğrenci eklemek/çıkarmak",
    ),
    "Sual dəstini kafedra adından təsdiqləmək": _e(
        "Approve a question set on behalf of the department",
        "Утверждать набор вопросов от имени кафедры",
        "Soru setini bölüm adına onaylamak",
    ),
    "Tapşırıq sətirlərinə viza vermək": _e(
        "Give visa to task rows", "Визировать строки задания", "Görev satırlarına vize vermek"
    ),
    "Tapşırığı dekanlığa göndərmək": _e(
        "Send the task to the dean's office",
        "Отправлять задание в деканат",
        "Görevi dekanlığa göndermek",
    ),
    "Tapşırığı təsdiqləmək": _e("Approve the task", "Утверждать задание", "Görevi onaylamak"),
    "Tədris tapşırığını yaratmaq/redaktə etmək": _e(
        "Create/edit the teaching task",
        "Создавать/редактировать учебное задание",
        "Öğretim görevini oluşturmak/düzenlemek",
    ),
    "Tələbənin qrupunu köçürmək və akademik statusunu dəyişmək": _e(
        "Transfer a student's group and change their academic status",
        "Переводить группу студента и изменять его академический статус",
        "Öğrencinin grubunu değiştirmek ve akademik durumunu değiştirmek",
    ),
    "Öz dərs yükünə etiraz bildirmək": _e(
        "File an objection about one's own teaching load",
        "Подавать возражение по своей учебной нагрузке",
        "Kendi ders yüküne itiraz etmek",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# profile.sidebar — Stage-6 skriptinin QƏSDƏN buraxdığı 4 dərs-yükü etiketi
# ─────────────────────────────────────────────────────────────────────────────
PROFILE_SIDEBAR = {
    "Dərs yükü mərkəzi": _e("Teaching load center", "Центр учебной нагрузки", "Ders yükü merkezi"),
    "Yük təsdiqi": _e("Load approval", "Утверждение нагрузки", "Yük onayı"),
    "Yük vizası": _e("Load visa", "Виза нагрузки", "Yük vizesi"),
    "Yük — ümumi baxış": _e("Load — overview", "Нагрузка — обзор", "Yük — genel bakış"),
}

# ─────────────────────────────────────────────────────────────────────────────
# workload — seçim etiketləri (0d9e2b50-dən, F0+F3+F4 baza modulu)
# ─────────────────────────────────────────────────────────────────────────────
WORKLOAD = {
    "Assistent": _e("Assistant", "Ассистент", "Asistan"),
    "Bakalavr": _e("Bachelor's", "Бакалавриат", "Lisans"),
    "Baxılıb": _e("Reviewed", "Рассмотрено", "İncelendi"),
    "Baxılır": _e("Under review", "На рассмотрении", "İnceleniyor"),
    "Baş müəllim": _e("Senior lecturer", "Старший преподаватель", "Baş öğretim görevlisi"),
    "Buraxılış işinə rəhbərlik": _e(
        "Supervising the graduation thesis",
        "Руководство выпускной работой",
        "Bitirme tezi danışmanlığı",
    ),
    "Buraxılış/dissertasiya işi": _e(
        "Graduation/dissertation work",
        "Выпускная/диссертационная работа",
        "Bitirme/tez çalışması",
    ),
    "Bölgü sətri": _e("Distribution row", "Строка распределения", "Dağıtım satırı"),
    "Bölüşdürülüb": _e("Distributed", "Распределено", "Dağıtıldı"),
    "Bölüşdürülür": _e("Being distributed", "Распределяется", "Dağıtılıyor"),
    "Dekanlığa göndərilib": _e("Sent to the dean's office", "Отправлено в деканат", "Dekanlığa gönderildi"),
    "Digər": _e("Other", "Другое", "Diğer"),
    "Dissertant rəhbərliyi": _e(
        "Doctoral candidate supervision",
        "Руководство диссертантом",
        "Doktora adayı danışmanlığı",
    ),
    "Dissertant/doktorant": _e(
        "Doctoral candidate / doctoral student",
        "Диссертант/докторант",
        "Tez adayı/doktora öğrencisi",
    ),
    "Distant": _e("Distance", "Дистанционная", "Uzaktan"),
    "Doktorantura": _e("Doctoral studies", "Докторантура", "Doktora"),
    "Dosent": _e("Associate professor", "Доцент", "Doçent"),
    "Düzəliş edilib": _e("Corrected", "Исправлено", "Düzeltildi"),
    "Dərs": _e("Lesson", "Занятие", "Ders"),
    "Elmi-tədqiqat təcrübəsi": _e(
        "Research practicum",
        "Научно-исследовательская практика",
        "Bilimsel araştırma stajı",
    ),
    "Fənn ixtisasım deyil": _e(
        "The subject is not my specialty",
        "Дисциплина не по моей специальности",
        "Ders alanım değil",
    ),
    "Göndərilib": _e("Sent", "Отправлено", "Gönderildi"),
    "Gözləyir": _e("Pending", "Ожидает", "Bekliyor"),
    "Kadr dəyişikliyi": _e("Staffing change", "Кадровое изменение", "Personel değişikliği"),
    "Laboratoriya": _e("Laboratory", "Лаборатория", "Laboratuvar"),
    "Ləğv edilib": _e("Cancelled", "Отменено", "İptal edildi"),
    "Magistr": _e("Master's", "Магистратура", "Yüksek lisans"),
    "Mühazirə": _e("Lecture", "Лекция", "Teorik ders"),
    "Müəllim": _e("Teacher", "Преподаватель", "Öğretmen"),
    "Məsləhət": _e("Consultation", "Консультация", "Danışma"),
    "Norma həddindən artıqdır": _e("Exceeds the norm limit", "Превышает предел нормы", "Norm sınırını aşıyor"),
    "Payız": _e("Fall", "Осень", "Güz"),
    "Professor": _e("Professor", "Профессор", "Profesör"),
    "Qaralama": _e("Draft", "Черновик", "Taslak"),
    "Qaytarılıb": _e("Returned", "Возвращено", "Geri gönderildi"),
    "Qiyabi": _e("Part-time", "Заочная", "İkinci öğretim"),
    "Qrup/tələbə sayı səhvdir": _e(
        "The group/student count is wrong",
        "Количество групп/студентов указано неверно",
        "Grup/öğrenci sayısı yanlış",
    ),
    "Qəbul edildi": _e("Accepted", "Принято", "Kabul edildi"),
    "Rədd edildi": _e("Rejected", "Отклонено", "Reddedildi"),
    "Rəsmi sərəncam/əmr": _e("Official directive/order", "Официальное распоряжение/приказ", "Resmi genelge/emir"),
    "Saat sayı düz deyil": _e("The hour count is wrong", "Количество часов указано неверно", "Saat sayısı yanlış"),
    "Seminar/təcrübi": _e("Seminar/practical", "Семинар/практическое", "Seminer/uygulama"),
    "Tapşırıq sətri": _e("Task row", "Строка задания", "Görev satırı"),
    "Texniki səhvin düzəlişi": _e(
        "Correction of a technical error",
        "Исправление технической ошибки",
        "Teknik hatanın düzeltilmesi",
    ),
    "Təcrübə": _e("Practicum", "Практика", "Staj"),
    "Tələbə sayının dəyişməsi": _e(
        "Change in student count",
        "Изменение количества студентов",
        "Öğrenci sayısındaki değişiklik",
    ),
    "Təsdiqlənib": _e("Approved", "Утверждено", "Onaylandı"),
    "Yay": _e("Summer", "Лето", "Yaz"),
    "Yaz": _e("Spring", "Весна", "Bahar"),
    "Yekun təsdiq gözləyir": _e(
        "Awaiting final approval", "Ожидает окончательного утверждения", "Nihai onayı bekliyor"
    ),
    "İmtahan": _e("Exam", "Экзамен", "Sınav"),
    "İntensiv": _e("Intensive", "Интенсивная", "Yoğun"),
    "İradlı": _e("Flagged", "С замечанием", "Sorunlu"),
    "İstehsalat təcrübəsi": _e("Industrial practicum", "Производственная практика", "Üretim stajı"),
    "Əyani": _e("Full-time", "Очная", "Örgün"),
}

# ─────────────────────────────────────────────────────────────────────────────
# workload.model — verbose_name cütləri (0d9e2b50-dən)
# ─────────────────────────────────────────────────────────────────────────────
WORKLOAD_MODEL = {
    "Düzəliş qeydi dəyişdirilə bilməz (append-only reyestr).": _e(
        "A correction entry cannot be changed (append-only registry).",
        "Запись исправления нельзя изменить (реестр только для добавления).",
        "Düzeltme kaydı değiştirilemez (yalnızca ekleme kaydı).",
    ),
    "Düzəliş qeydi silinə bilməz (append-only reyestr).": _e(
        "A correction entry cannot be deleted (append-only registry).",
        "Запись исправления нельзя удалить (реестр только для добавления).",
        "Düzeltme kaydı silinemez (yalnızca ekleme kaydı).",
    ),
    "Düzəliş üçün qeyd MƏCBURİDİR.": _e(
        "A note is MANDATORY for a correction.",
        "Для исправления ОБЯЗАТЕЛЬНА заметка.",
        "Düzeltme için not ZORUNLUDUR.",
    ),
    "bölgü sətirləri": _e("distribution rows", "строки распределения", "dağıtım satırları"),
    "bölgü sətri": _e("distribution row", "строка распределения", "dağıtım satırı"),
    "fakültə təsdiq dilimi": _e("faculty approval slice", "доля утверждения факультета", "fakülte onay dilimi"),
    "fakültə təsdiq dilimləri": _e("faculty approval slices", "доли утверждения факультета", "fakülte onay dilimleri"),
    "müəllim yük profili": _e("teacher load profile", "профиль нагрузки преподавателя", "öğretmen yük profili"),
    "müəllim yük profilləri": _e("teacher load profiles", "профили нагрузки преподавателя", "öğretmen yük profilleri"),
    "sətir vizaları": _e("row visas", "визы строк", "satır vizeleri"),
    "sətir vizası": _e("row visa", "виза строки", "satır vizesi"),
    "tapşırıq sətirləri": _e("task rows", "строки задания", "görev satırları"),
    "tapşırıq sətri": _e("task row", "строка задания", "görev satırı"),
    "tədris tapşırıqları": _e("teaching tasks", "учебные задания", "öğretim görevleri"),
    "tədris tapşırığı": _e("teaching task", "учебное задание", "öğretim görevi"),
    "yük düzəlişi": _e("load correction", "исправление нагрузки", "yük düzeltmesi"),
    "yük düzəlişləri": _e("load corrections", "исправления нагрузки", "yük düzeltmeleri"),
    "yük etirazları": _e("load objections", "возражения по нагрузке", "yük itirazları"),
    "yük etirazı": _e("load objection", "возражение по нагрузке", "yük itirazı"),
}

ENTRIES = {
    "accounts.workload": ACCOUNTS_WORKLOAD,
    "accounts.workload_approval": ACCOUNTS_WORKLOAD_APPROVAL,
    "accounts.workload_center": ACCOUNTS_WORKLOAD_CENTER,
    "accounts.workload_overview": ACCOUNTS_WORKLOAD_OVERVIEW,
    "accounts.workload_visa": ACCOUNTS_WORKLOAD_VISA,
    "organizations.permission.label": ORGANIZATIONS_PERMISSION_LABEL,
    "profile.sidebar": PROFILE_SIDEBAR,
    "workload": WORKLOAD,
    "workload.model": WORKLOAD_MODEL,
}

#: Bu Stage-də heç bir kontekst Django-nun avtomatik ingiliscə konvensiyası
#: ilə YAZILMAYIB (hamısı artıq Azərbaycanca insan-oxunaqlı mətndir) →
#: AZ hər yerdə identity (bax modul başlığı, `organizations.permission.label`
#: presedenti).
AZ_OVERRIDES: dict = {}

_expected_total = 355
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
