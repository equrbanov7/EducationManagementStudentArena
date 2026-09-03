#!/usr/bin/env python3
"""EMSArena i18n — Dizayn Faza-2/3 (Stage-2/3) mətnləri (4 dil). İdempotent.

Mənbə: `docs/audits/2026-09-02/DESIGN_STAGE2_MSGIDS.txt` (295, 9 kontekst) və
`DESIGN_STAGE3_MSGIDS.txt` (134, 8 kontekst) — commit `63007671` ilə əlavə
olunan tədris planı təsdiq zənciri, qruplar reyestri, semestr açılışı, ATİS
qəbulu, tələbə reyestri və 6 hərəkət növü.

Yoxlama metodu (audit tələbi): `scripts/i18n_source_scan.py` HƏMİN skanerin
bilinən kor-nöqtəsi ilə (bax `i18n_fill_design_stage1.py` başlığı) — modul-
səviyyəli dəyişənlə çağırılan `pgettext(_CTX, …)` / `pgettext_lazy(_CTX, …)`
cütlərini görmür (kontekst arqumenti `ast.Constant` deyil, `ast.Name`-dir).
Bu faylın ENTRIES-i avtomatik skaner NƏTİCƏSİ + ƏL İLƏ AST gəzintisi
(module-level `_CTX`/`_PERM_CTX` təyinatlarını tapıb `pgettext(_CTX, "…")`
çağırışlarına həll edən köməkçi skript) BİRLƏŞMƏSİ ilə əldə olunub, sonra
mövcud AZ kataloqu ilə fərq çıxarılıb (`gap = source − catalog`). Bu, İKİ
audit sənədini əl ilə köçürməkdən daha etibarlıdır, çünki sənədlər bir neçə
YERDƏ mənbədən fərqlənirdi:

  * `accounts.curriculum` / `accounts.groups`: sənəddə `{% blocktrans %}`
    daxilindəki `{{ n }}` / `{{ name }}` / `{{ target }}` HƏRFİ göstərilib,
    amma Django-nun `templatize`-i onları `%(n)s` / `%(name)s` / `%(target)s`
    formatına ÇEVİRİR — runtime axtarışı da bu formatladır. Bu faylda DOĞRU
    (çevrilmiş) forma işlədilir.
  * `accounts.groups`: `{% trans '%d qrup seçilib' %}` — HƏRFİ `%` TranslateNode
    tərəfindən `%%`-ə ikiqatlanır (bax `i18n_fill_design_stage1.py` şərhi,
    "Qayıb limiti (%%)" nümunəsi) — msgid/msgstr BURADA da `%%d qrup seçilib`.
  * `organizations.permission.label`: audit sənədində 11+3=14 YENİ etiket
    sadalanıb, amma bu kontekstdə HƏQİQƏTƏN mənbədə olub kataloqda OLMAYAN
    daha 11 cüt də var — onlar `apps/organizations/permissions.py`-dəki
    ÖNCƏDƏN mövcud (bu commit-dən ƏVVƏL yazılmış) dərs-yükü/sual-bankı
    icazələridir (məs. "Dərs yükünü müəllimlərə bölmək", "Tapşırığı
    təsdiqləmək") — `apps/workload` sahəsinə aiddir, BU SKRİPTİN ƏHATƏSİNDƏN
    KƏNARDIR (ayrıca borc, `i18n_fill_design_stage1.py`-dəki eyni qeydə bax).
  * `student_intake`: audit sənədində 19 msgid var, amma
    `apps/accounts/views/student_intake.py`-də HƏMİN COMMIT-lə əlavə olunmuş
    daha 3 çağırış sənəddə YOXDUR ("İxtisas tapılmadı.", "Qrupun adı boş ola
    bilməz.", "Bu adla qrup artıq var." — `group_name_*`/`specialty_*` xəta
    xəritəsi) — BURADA əlavə olunub.
  * `ui.dialog`: sənəddə YOXDUR, amma mənbədə (səbəb dialoqlarının ÜMUMİ
    "Yadda saxla" düyməsi) var — BURADA əlavə olunub.
  * `accounts.student_admission`: sənəddə YOXDUR, amma
    `_student_admission.html`-dəki `data-t-*` JS-mətn körpüsündə (AJAX-safe
    naxış, bax CLAUDE.md) 15 əlavə açar var (Cəmi/Xəta/Yaradıldı/Ötürüldü/
    dolu/Yaradılacaq/… — tətbiq addımının vəziyyət etiketləri) — BURADA
    əlavə olunub.

  Bütün fərqlər `git show 63007671` diff-i və birbaşa şablon/mənbə oxunması
  ilə TƏSDİQLƏNİB (aşağıdakı ENTRIES yalnız TƏSDİQLƏNMİŞ cütləri saxlayır).

AZ: əksər msgid artıq Azərbaycanca UI mətnidir → `az_override` YOXDUR (identity).
İSTİSNA: `registrar.model.student_movement.meta` — Django `Meta.verbose_name`
konvensiyası ilə msgid İNGİLİSCƏDİR ("student movement"/"student movements"),
bacı kontekstlər (`registrar.model.curriculum_subject.meta` və s.) kimi AZ
üçün HƏQİQİ tərcümə lazımdır (bax `AZ_OVERRIDES`).

⚠️ PARALEL AGENT TƏHLÜKƏSİZLİYİ (bax `i18n_fill_design_stage1.py`): eyni
   sessiyada `apps/workload` və `apps/syllabus` üzərində işləyən agentlər
   eyni 4 `.po` faylına ƏLAVƏ edə bilər (özləri `.po`-ya TOXUNMUR, sadəcə
   mənbədə yeni `pgettext` çağırışları yaza bilərlər — bu skriptin ƏHATƏSİNƏ
   girmir, çünki ENTRIES yalnız Stage-2/3 kontekstlərini əhatə edir).
     * mövcudluq yoxlaması `polib` ilə (bax `existing_pairs`);
     * YAZMADAN DƏRHAL ƏVVƏL fayl YENİDƏN oxunur (`fill()` daxilində);
     * yazma xam mətn ƏLAVƏSİ ilə — `polib.save()` İŞLƏDİLMİR. Yalnız
       ƏLAVƏ olunur — mövcud sətirlərə TOXUNULMUR, fuzzy flag-lar
       dəyişdirilmir.

⚠️ `makemessages` İŞLƏDİLMİR (əl ilə yazılmış blokları silə bilər).

İstifadə:  python scripts/i18n_fill_design_stage2_3.py
Sonra:     django-admin compilemessages && python scripts/check_i18n_catalogs.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def _e(en, ru, tr):
    return {"en": en, "ru": ru, "tr": tr}


# ─────────────────────────────────────────────────────────────────────────────
# accounts.curriculum — Tədris planı redaktoru + təsdiq zənciri (ekran 05)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_CURRICULUM = {
    "%(sem)d-ci semestr: %(credits)d kredit (hədəf %(target)d)": _e(
        "Semester %(sem)d: %(credits)d credits (target %(target)d)",
        "%(sem)d-й семестр: %(credits)d кредитов (цель %(target)d)",
        "%(sem)d. dönem: %(credits)d kredi (hedef %(target)d)",
    ),
    "Aktiv təşkilat konteksti yoxdur.": _e(
        "There is no active organization context.",
        "Нет активного контекста организации.",
        "Aktif kurum bağlamı yok.",
    ),
    "Auditoriya": _e("Contact hours", "Аудиторные часы", "Sınıf saati"),
    "Açıq xəbərdarlıq var — əvvəlcə kredit/saat balansını bağlayın.": _e(
        "There is an open warning — close the credit/hour balance first.",
        "Есть открытое предупреждение — сначала закройте баланс кредитов/часов.",
        "Açık bir uyarı var — önce kredi/saat dengesini kapatın.",
    ),
    "Açıq xəbərdarlıqlar — təsdiqə göndərmə bağlıdır": _e(
        "Open warnings — submitting for approval is blocked",
        "Открытые предупреждения — отправка на утверждение заблокирована",
        "Açık uyarılar — onaya gönderme engelli",
    ),
    "Balans — semestr üzrə": _e("Balance — by semester", "Баланс — по семестрам", "Denge — döneme göre"),
    "Boş buraxılsa kredit × 30 yazılır.": _e(
        "If left empty, credits × 30 is used.",
        "Если оставить пустым, будет записано кредиты × 30.",
        "Boş bırakılırsa kredi × 30 yazılır.",
    ),
    "Boş buraxılsa ümumi − auditoriya yazılır.": _e(
        "If left empty, total − contact hours is used.",
        "Если оставить пустым, будет записано всего − аудиторные часы.",
        "Boş bırakılırsa toplam − sınıf saati yazılır.",
    ),
    "Bu fənn həmin semestrdə artıq plandadır.": _e(
        "This subject is already in the plan for that semester.",
        "Эта дисциплина уже есть в плане на этот семестр.",
        "Bu ders o dönem için planda zaten var.",
    ),
    "Bu ixtisas və qəbul ili üçün plan artıq mövcuddur.": _e(
        "A curriculum already exists for this programme and admission year.",
        "План для этой специальности и года приёма уже существует.",
        "Bu program ve kabul yılı için müfredat zaten mevcut.",
    ),
    "Bu mərhələnin təsdiqi başqa səlahiyyətdədir.": _e(
        "Approving this stage requires a different permission.",
        "Утверждение этого этапа относится к другому полномочию.",
        "Bu aşamanın onayı başka bir yetkiye aittir.",
    ),
    "Bu plan üzrə hələ qeyd yoxdur.": _e(
        "There is no entry for this plan yet.", "По этому плану записей пока нет.", "Bu plana ait henüz kayıt yok."
    ),
    "Bu versiya qüvvədədir və semestr açılışının mənbəyidir. Dəyişiklik üçün «Yeni versiya» yaradın — köhnə versiya "
    "tarixçə kimi qalır.": _e(
        "This version is in force and is the source for semester opening. To make changes, create a "
        '"New version" — the old version remains as history.',
        "Эта версия действует и является источником для открытия семестра. Для изменений создайте "
        "«Новую версию» — старая версия остаётся в истории.",
        'Bu sürüm yürürlüktedir ve dönem açılışının kaynağıdır. Değişiklik için "Yeni sürüm" oluşturun — '
        "eski sürüm geçmiş olarak kalır.",
    ),
    "Dəyişiklik tarixçəsi": _e("Change history", "История изменений", "Değişiklik geçmişi"),
    "Elmi Şura protokolu": _e("Academic Council protocol", "Протокол Учёного совета", "Bilim Kurulu tutanağı"),
    "Fakültə şurası adından təsdiqlə": _e(
        "Approve on behalf of the faculty council",
        "Утвердить от имени совета факультета",
        "Fakülte kurulu adına onayla",
    ),
    "Fənn": _e("Subject", "Дисциплина", "Ders"),
    "Fənn seçilməyib.": _e("No subject selected.", "Дисциплина не выбрана.", "Ders seçilmedi."),
    "Geri qaytar": _e("Send back", "Вернуть", "Geri gönder"),
    "Hamısı": _e("All", "Все", "Tümü"),
    "Kafedra adından təsdiqlə": _e(
        "Approve on behalf of the department", "Утвердить от имени кафедры", "Bölüm adına onayla"
    ),
    "Kafedra baxışına göndər": _e(
        "Send for department review", "Отправить на рассмотрение кафедры", "Bölüm incelemesine gönder"
    ),
    "Kataloqdan seçin": _e("Select from the catalog", "Выберите из каталога", "Katalogdan seçin"),
    "Kredit": _e("Credit", "Кредит", "Kredi"),
    "Kredit təyin edilməyib": _e("Credits not assigned", "Кредиты не назначены", "Kredi atanmamış"),
    "Kredit yazıldıqda ümumi saat (kredit × 30) və həftəlik yük avtomatik hesablanır.": _e(
        "When credits are entered, total hours (credits × 30) and the weekly load are calculated automatically.",
        "При вводе кредитов общее число часов (кредиты × 30) и недельная нагрузка рассчитываются автоматически.",
        "Kredi girildiğinde toplam saat (kredi × 30) ve haftalık yük otomatik hesaplanır.",
    ),
    "Laboratoriya": _e("Laboratory", "Лаборатория", "Laboratuvar"),
    "Mühazirə": _e("Lecture", "Лекция", "Teorik ders"),
    "Mühazirə + seminar + laboratoriya + sərbəst iş ümumi saatla uyğun gəlmir": _e(
        "Lecture + seminar + laboratory + independent work does not match the total hours",
        "Лекция + семинар + лаборатория + самостоятельная работа не совпадает с общим числом часов",
        "Teorik ders + seminer + laboratuvar + serbest çalışma toplam saatle uyuşmuyor",
    ),
    "Naməlum əməl.": _e("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
    "Plan geri qaytarılıb": _e("The plan has been sent back", "План возвращён", "Plan geri gönderildi"),
    "Plan qaralama kimi yaranır; təsdiq zənciri sonra başlayır.": _e(
        "The plan is created as a draft; the approval chain starts afterwards.",
        "План создаётся как черновик; цепочка утверждения начинается позже.",
        "Plan taslak olarak oluşturulur; onay zinciri daha sonra başlar.",
    ),
    "Plan redaktəsi üçün səlahiyyətiniz yoxdur.": _e(
        "You do not have permission to edit the plan.",
        "У вас нет прав для редактирования плана.",
        "Planı düzenleme yetkiniz yok.",
    ),
    "Plan sətri": _e("Curriculum line", "Строка плана", "Plan satırı"),
    "Plan sətri tapılmadı.": _e("Curriculum line not found.", "Строка плана не найдена.", "Plan satırı bulunamadı."),
    "Plan sətrini sil": _e("Delete the curriculum line", "Удалить строку плана", "Plan satırını sil"),
    "Plan tapılmadı.": _e("Plan not found.", "План не найден.", "Plan bulunamadı."),
    "Plan şifri": _e("Plan code", "Код плана", "Plan kodu"),
    "Planı geri qaytar": _e("Send the plan back", "Вернуть план", "Planı geri gönder"),
    "Planın adı": _e("Plan name", "Название плана", "Plan adı"),
    "Proqram ECTS": _e("Programme ECTS", "ECTS программы", "Program ECTS"),
    "Qaytar": _e("Return", "Вернуть", "Geri gönder"),
    "Qaytarma cari mərhələnin təsdiqçisinə aiddir.": _e(
        "Returning belongs to the approver of the current stage.",
        "Возврат относится к утверждающему текущего этапа.",
        "Geri gönderme, mevcut aşamanın onaylayıcısına aittir.",
    ),
    "Qiymətləndirmə forması": _e("Assessment form", "Форма оценивания", "Değerlendirme şekli"),
    "Qəbul ili": _e("Year of admission", "Год поступления", "Kabul yılı"),
    "Qəbul ili düzgün deyil.": _e(
        "The admission year is invalid.", "Год поступления указан неверно.", "Kabul yılı geçerli değil."
    ),
    "Redaktə": _e("Edit", "Редактировать", "Düzenle"),
    "Semestr": _e("Semester", "Семестр", "Dönem"),
    "Semestr 1–16 aralığında olmalıdır.": _e(
        "The semester must be between 1 and 16.",
        "Семестр должен быть в диапазоне 1–16.",
        "Dönem 1–16 aralığında olmalıdır.",
    ),
    "Semestr hədəfi: %(target)s kredit (NK 348 b. 3.2.2). Fərq açıq xəbərdarlıq sayılır.": _e(
        "Semester target: %(target)s credits (NK 348 cl. 3.2.2). A difference counts as an open warning.",
        "Цель семестра: %(target)s кредитов (NK 348 п. 3.2.2). Разница считается открытым предупреждением.",
        "Dönem hedefi: %(target)s kredi (NK 348 md. 3.2.2). Fark açık uyarı sayılır.",
    ),
    "Semestrlər": _e("Semesters", "Семестры", "Dönemler"),
    "Seminar": _e("Seminar", "Семинар", "Seminer"),
    "Seçin": _e("Select", "Выберите", "Seçin"),
    "Sil": _e("Delete", "Удалить", "Sil"),
    "Status": _e("Status", "Статус", "Durum"),
    "Səbəb müəllifə göndərilir və audit jurnalına yazılır.": _e(
        "The reason is sent to the author and recorded in the audit log.",
        "Причина отправляется автору и записывается в журнал аудита.",
        "Gerekçe yazara gönderilir ve denetim günlüğüne yazılır.",
    ),
    "Sərbəst": _e("Independent", "Самостоятельная", "Serbest"),
    "Sərbəst iş": _e("Independent work", "Самостоятельная работа", "Serbest çalışma"),
    "Sətir yalnız QARALAMA planından silinir; təsdiqlənmiş plan toxunulmazdır.": _e(
        "A line can only be deleted from a DRAFT plan; an approved plan is untouched.",
        "Строка удаляется только из ЧЕРНОВОГО плана; утверждённый план остаётся неизменным.",
        "Satır yalnızca TASLAK plandan silinir; onaylanmış plan değiştirilmez.",
    ),
    "Sətir əlavə et": _e("Add a line", "Добавить строку", "Satır ekle"),
    "Tədris dili": _e("Language of instruction", "Язык обучения", "Öğretim dili"),
    "Tədris edən kafedra": _e("Teaching department", "Кафедра, ведущая дисциплину", "Dersi veren bölüm"),
    "Tədris planı seçilməyib": _e("No curriculum selected", "Учебный план не выбран", "Müfredat seçilmedi"),
    "Tədris planına baxış üçün səlahiyyətiniz yoxdur. Administratora müraciət edin.": _e(
        "You do not have permission to view the curriculum. Contact the administrator.",
        "У вас нет прав для просмотра учебного плана. Обратитесь к администратору.",
        "Müfredatı görüntüleme yetkiniz yok. Yöneticinize başvurun.",
    ),
    "Tədris planına səlahiyyətiniz yoxdur.": _e(
        "You do not have permission for the curriculum.",
        "У вас нет прав в отношении учебного плана.",
        "Müfredat için yetkiniz yok.",
    ),
    "Tədris şöbəsi adından təsdiqlə": _e(
        "Approve on behalf of the Teaching Office",
        "Утвердить от имени Учебного отдела",
        "Öğretim İşleri Dairesi adına onayla",
    ),
    "Təsdiqlənmiş plan dəyişdirilmir": _e(
        "An approved plan cannot be changed", "Утверждённый план не изменяется", "Onaylanmış plan değiştirilmez"
    ),
    "Təsdiqlənmiş plandan yeni qaralama versiya yaradılsın? Köhnə versiya toxunulmaz qalır.": _e(
        "Create a new draft version from the approved plan? The old version remains untouched.",
        "Создать новую черновую версию из утверждённого плана? Старая версия останется без изменений.",
        "Onaylanmış plandan yeni bir taslak sürüm oluşturulsun mu? Eski sürüm değişmeden kalır.",
    ),
    "Təyin edilməyib": _e("Not assigned", "Не назначено", "Atanmamış"),
    "Versiya": _e("Version", "Версия", "Sürüm"),
    "Yeni plan": _e("New plan", "Новый план", "Yeni plan"),
    "Yeni tədris planı": _e("New curriculum", "Новый учебный план", "Yeni müfredat"),
    "Yeni versiya": _e("New version", "Новая версия", "Yeni sürüm"),
    "Yeni versiya yalnız təsdiqlənmiş plandan yaradılır.": _e(
        "A new version can only be created from an approved plan.",
        "Новая версия создаётся только из утверждённого плана.",
        "Yeni sürüm yalnızca onaylanmış plandan oluşturulur.",
    ),
    "Yenidən işlə (qaralamaya qaytar)": _e(
        "Rework (return to draft)", "Доработать (вернуть в черновик)", "Yeniden işle (taslağa döndür)"
    ),
    "kr": _e("cr", "кр", "kr"),
    "Çıxarılıb: %(n)s sətir": _e("Removed: %(n)s line(s)", "Удалено: %(n)s строк(и)", "Çıkarıldı: %(n)s satır"),
    "Ümumi": _e("Total", "Всего", "Toplam"),
    "Ümumi saat": _e("Total hours", "Всего часов", "Toplam saat"),
    "Ümumi saat kredit × 30 ilə uyğun gəlmir": _e(
        "Total hours does not match credits × 30",
        "Общее число часов не совпадает с кредиты × 30",
        "Toplam saat kredi × 30 ile uyuşmuyor",
    ),
    "İxtisas": _e("Programme", "Специальность", "Program"),
    "İxtisas seçin və ya «Yeni plan» düyməsi ilə qaralama yaradın.": _e(
        'Select a programme, or create a draft with the "New plan" button.',
        "Выберите специальность или создайте черновик кнопкой «Новый план».",
        'Bir program seçin veya "Yeni plan" düğmesiyle bir taslak oluşturun.',
    ),
    "İxtisas tapılmadı.": _e("Programme not found.", "Специальность не найдена.", "Program bulunamadı."),
    "İxtisasın çoxillik tədris planı: kredit balansı, saat bölgüsü və təsdiq zənciri. Dərs yükü məhz bu plandan "
    "törəyir.": _e(
        "The programme's multi-year curriculum: credit balance, hour breakdown, and the approval chain. "
        "Teaching load is derived precisely from this plan.",
        "Многолетний учебный план специальности: баланс кредитов, распределение часов и цепочка "
        "утверждения. Учебная нагрузка формируется именно из этого плана.",
        "Programın çok yıllı müfredatı: kredi dengesi, saat dağılımı ve onay zinciri. Ders yükü tam olarak "
        "bu plandan türer.",
    ),
    "Əlavə olunub: %(n)s sətir": _e("Added: %(n)s line(s)", "Добавлено: %(n)s строк(и)", "Eklendi: %(n)s satır"),
    "Əvvəlki versiya ilə fərq": _e(
        "Difference from the previous version", "Отличие от предыдущей версии", "Önceki sürümle fark"
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.groups — Qruplar reyestri (ekran 06)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_GROUPS = {
    "%%d qrup seçilib": _e("%%d groups selected", "Выбрано групп: %%d", "%%d grup seçildi"),
    "%(name)s qrupunu seç": _e("Select the %(name)s group", "Выбрать группу %(name)s", "%(name)s grubunu seç"),
    "Arxivdən qaytar": _e("Restore from archive", "Восстановить из архива", "Arşivden geri getir"),
    "Arxivlə": _e("Archive", "Архивировать", "Arşivle"),
    "Bərpa səbəbi audit jurnalına aktor və vaxtla yazılır.": _e(
        "The restore reason is recorded in the audit log with the actor and timestamp.",
        "Причина восстановления записывается в журнал аудита с указанием исполнителя и времени.",
        "Geri getirme gerekçesi işlemi yapan kişi ve zamanla birlikte denetim günlüğüne yazılır.",
    ),
    "Dil sektoru": _e("Language sector", "Языковой сектор", "Dil sektörü"),
    "Dərs cədvəli": _e("Class schedule", "Расписание занятий", "Ders programı"),
    "Hər qrup üçün ayrıca audit yazısı düşür (köhnə kurs → yeni kurs). Son kursdakı qruplar toxunulmur — "
    "məzunluq ayrı əməldir.": _e(
        "A separate audit entry is recorded for each group (old year → new year). Groups in the final "
        "year are untouched — graduation is a separate action.",
        "Для каждой группы записывается отдельная запись аудита (старый курс → новый курс). Группы "
        "последнего курса не затрагиваются — выпуск является отдельным действием.",
        "Her grup için ayrı bir denetim kaydı düşer (eski sınıf → yeni sınıf). Son sınıftaki gruplar "
        "değişmez — mezuniyet ayrı bir işlemdir.",
    ),
    "Kurs": _e("Year of study", "Курс", "Sınıf"),
    "Kursa keçir": _e("Move to the next year", "Перевести на курс", "Sınıfa geçir"),
    "Naməlum əməl.": _e("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
    "Plan üzrə yer sayı": _e("Places under the plan", "Количество мест по плану", "Plana göre yer sayısı"),
    "Qrup": _e("Group", "Группа", "Grup"),
    "Qrup SİLİNMİR — arxivlənir; tələbə qeydiyyatı, jurnal və qiymət tarixçəsi qalır.": _e(
        "The group is NOT DELETED — it is archived; student enrollment, the journal, and the grade "
        "history are preserved.",
        "Группа НЕ УДАЛЯЕТСЯ — она архивируется; регистрация студентов, журнал и история оценок " "сохраняются.",
        "Grup SİLİNMEZ — arşivlenir; öğrenci kaydı, jurnal ve not geçmişi korunur.",
    ),
    "Qrup kodu": _e("Group code", "Код группы", "Grup kodu"),
    "Qrup reyestrinə baxış üçün səlahiyyətiniz yoxdur. Administratora müraciət edin.": _e(
        "You do not have permission to view the group registry. Contact the administrator.",
        "У вас нет прав для просмотра реестра групп. Обратитесь к администратору.",
        "Grup siciline erişim yetkiniz yok. Yöneticinize başvurun.",
    ),
    "Qrup reyestrinə səlahiyyətiniz yoxdur.": _e(
        "You do not have permission for the group registry.",
        "У вас нет прав в отношении реестра групп.",
        "Grup sicili için yetkiniz yok.",
    ),
    "Qrup seçilməyib": _e("No group selected", "Группа не выбрана", "Grup seçilmedi"),
    "Qrup seçilməyib.": _e("No group selected.", "Группа не выбрана.", "Grup seçilmedi."),
    "Qrup tapılmadı.": _e("Group not found.", "Группа не найдена.", "Grup bulunamadı."),
    "Qrupları idarə etmək səlahiyyətiniz yoxdur.": _e(
        "You do not have permission to manage groups.",
        "У вас нет прав для управления группами.",
        "Grupları yönetme yetkiniz yok.",
    ),
    "Qrupu arxivlə": _e("Archive the group", "Архивировать группу", "Grubu arşivle"),
    "Qrupun adı": _e("Group name", "Название группы", "Grup adı"),
    "Qrupun adı boş ola bilməz.": _e(
        "The group name cannot be empty.", "Название группы не может быть пустым.", "Grup adı boş olamaz."
    ),
    "Qrupun kursu və dil sektoru bölmə metadatasında saxlanılır — sxem tenantdan asılı deyil.": _e(
        "The group's year and language sector are stored in unit metadata — the schema does not depend "
        "on the tenant.",
        "Курс и языковой сектор группы хранятся в метаданных подразделения — схема не зависит от " "арендатора.",
        "Grubun sınıfı ve dil sektörü birim meta verisinde saklanır — şema kiracıya (tenant) bağlı değildir.",
    ),
    "Qəbul ili": _e("Year of admission", "Год поступления", "Kabul yılı"),
    "Redaktə": _e("Edit", "Редактировать", "Düzenle"),
    "Seçilmiş qrupları növbəti kursa keçir": _e(
        "Move the selected groups to the next year",
        "Перевести выбранные группы на следующий курс",
        "Seçilen grupları bir sonraki sınıfa geçir",
    ),
    "Seçilmiş şəxs bu təşkilatın aktiv üzvü deyil.": _e(
        "The selected person is not an active member of this organization.",
        "Выбранное лицо не является активным членом этой организации.",
        "Seçilen kişi bu kurumun aktif üyesi değil.",
    ),
    "Seçin": _e("Select", "Выберите", "Seçin"),
    "Struktur əhatəniz yoxdur.": _e(
        "You have no structural scope.", "У вас нет структурного охвата.", "Yapısal kapsamınız yok."
    ),
    "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.": _e(
        "The reason must be at least 20 characters — a short note is not enough for the audit.",
        "Причина должна содержать не менее 20 символов — краткая заметка недостаточна для аудита.",
        "Gerekçe en az 20 karakter olmalı — kısa bir not denetim için yeterli değildir.",
    ),
    "Tələbə qrupları: ixtisas, kurs, dil sektoru, kurator və tələbə tərkibi. Cədvəl və imtahan kohortları ayrı "
    "bölmələrdədir.": _e(
        "Student groups: programme, year, language sector, curator, and student composition. The "
        "schedule and exam cohorts are in separate sections.",
        "Студенческие группы: специальность, курс, языковой сектор, куратор и состав студентов. "
        "Расписание и экзаменационные когорты находятся в отдельных разделах.",
        "Öğrenci grupları: program, sınıf, dil sektörü, danışman ve öğrenci bileşimi. Program ve sınav "
        "kohortları ayrı bölümlerdedir.",
    ),
    "Tələbəsi olan qrup arxivlənmir — əvvəlcə tələbələri köçürün.": _e(
        "A group with students cannot be archived — move the students first.",
        "Группа со студентами не архивируется — сначала переведите студентов.",
        "Öğrencisi olan grup arşivlenmez — önce öğrencileri taşıyın.",
    ),
    "Yeni qrup": _e("New group", "Новая группа", "Yeni grup"),
    "Yeni qrup üçün ixtisas seçilməlidir.": _e(
        "A programme must be selected for the new group.",
        "Для новой группы должна быть выбрана специальность.",
        "Yeni grup için program seçilmelidir.",
    ),
    "İmtahan kohortları": _e("Exam cohorts", "Экзаменационные когорты", "Sınav kohortları"),
    "İxtisas / kafedra": _e("Programme / department", "Специальность / кафедра", "Program / bölüm"),
    "İxtisas bölməsi tapılmadı.": _e(
        "The programme section was not found.", "Раздел специальности не найден.", "Program bölümü bulunamadı."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.semester — Semestr açılışı (ekran 07)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_SEMESTER = {
    "%(n)d açılış müəllim gözləyir": _e(
        "%(n)d openings are waiting for a teacher",
        "%(n)d открытий ожидают преподавателя",
        "%(n)d açılış öğretmen bekliyor",
    ),
    "%(n)d açılış sətri": _e("%(n)d opening lines", "%(n)d строк открытия", "%(n)d açılış satırı"),
    "%(n)d açılışın jurnalı açılmayıb": _e(
        "%(n)d openings do not have the journal opened",
        "У %(n)d открытий не открыт журнал",
        "%(n)d açılışın jurnalı açılmadı",
    ),
    "Aktiv təşkilat konteksti yoxdur.": _e(
        "There is no active organization context.",
        "Нет активного контекста организации.",
        "Aktif kurum bağlamı yok.",
    ),
    "Açılış": _e("Opening", "Открытие", "Açılış"),
    "Açılış SİLİNMİR — ləğv olunur; jurnal, qeydiyyat və qiymət tarixçəsi qalır.": _e(
        "The opening is NOT DELETED — it is cancelled; the journal, enrollment, and grade history are " "preserved.",
        "Открытие НЕ УДАЛЯЕТСЯ — оно отменяется; журнал, регистрация и история оценок сохраняются.",
        "Açılış SİLİNMEZ — iptal edilir; jurnal, kayıt ve not geçmişi korunur.",
    ),
    "Açılış tapılmadı.": _e("Opening not found.", "Открытие не найдено.", "Açılış bulunamadı."),
    "Açılış yoxdur.": _e("There is no opening.", "Открытия нет.", "Açılış yok."),
    "Açılışlar kafedralara göndərilsin? Kafedra rəhbərlərinə bildiriş gedəcək.": _e(
        "Send the openings to the departments? Department heads will be notified.",
        "Отправить открытия на кафедры? Заведующим кафедрами будет отправлено уведомление.",
        "Açılışlar bölümlere gönderilsin mi? Bölüm başkanlarına bildirim gidecek.",
    ),
    "Açılışlar təsdiqlənmiş plandan gəlir": _e(
        "Openings come from the approved plan",
        "Открытия формируются из утверждённого плана",
        "Açılışlar onaylanmış plandan gelir",
    ),
    "Açılışları yarat": _e("Create the openings", "Создать открытия", "Açılışları oluştur"),
    "Açılışı ləğv et": _e("Cancel the opening", "Отменить открытие", "Açılışı iptal et"),
    "Başlama tarixi": _e("Start date", "Дата начала", "Başlama tarihi"),
    "Başlama tarixi bitmə tarixindən əvvəl olmalıdır.": _e(
        "The start date must be before the end date.",
        "Дата начала должна быть раньше даты окончания.",
        "Başlama tarihi bitiş tarihinden önce olmalıdır.",
    ),
    "Başlama və bitmə tarixi tələb olunur.": _e(
        "The start and end dates are required.",
        "Требуются дата начала и дата окончания.",
        "Başlama ve bitiş tarihi gereklidir.",
    ),
    "Bitmə tarixi": _e("End date", "Дата окончания", "Bitiş tarihi"),
    "Boş buraxılsa bütün aktiv ixtisaslar götürülür; təsdiqlənmiş planı olmayanlar atlanır.": _e(
        "If left empty, all active programmes are taken; those without an approved plan are skipped.",
        "Если оставить пустым, берутся все активные специальности; специальности без утверждённого "
        "плана пропускаются.",
        "Boş bırakılırsa tüm aktif programlar alınır; onaylanmış planı olmayanlar atlanır.",
    ),
    "Bu ad və tədris ili ilə dövr artıq mövcuddur.": _e(
        "A period with this name and academic year already exists.",
        "Период с этим названием и учебным годом уже существует.",
        "Bu ad ve öğretim yılı ile dönem zaten mevcut.",
    ),
    "Bu dövr «cari» edilsin? Köhnə cari dövr avtomatik söndürüləcək və əməl audit jurnalına yazılacaq.": _e(
        'Make this period "current"? The old current period will be switched off automatically and the '
        "action will be recorded in the audit log.",
        "Сделать этот период «текущим»? Старый текущий период будет автоматически отключён, и действие "
        "будет записано в журнал аудита.",
        'Bu dönem "cari" yapılsın mı? Eski cari dönem otomatik olarak kapatılacak ve işlem denetim '
        "günlüğüne yazılacak.",
    ),
    "Bu əməl üçün səlahiyyətiniz yoxdur.": _e(
        "You do not have permission for this action.",
        "У вас нет прав для этого действия.",
        "Bu işlem için yetkiniz yok.",
    ),
    "Bütün açılışlara müəllim təyin olunub": _e(
        "A teacher has been assigned to all openings",
        "Преподаватель назначен на все открытия",
        "Tüm açılışlara öğretmen atandı",
    ),
    "Cari dövr et": _e("Make current", "Сделать текущим", "Cari yap"),
    "Dövr tapılmadı.": _e("Period not found.", "Период не найден.", "Dönem bulunamadı."),
    "Dövrün adı boş ola bilməz.": _e(
        "The period name cannot be empty.", "Название периода не может быть пустым.", "Dönem adı boş olamaz."
    ),
    "Elektron jurnallar açılıb": _e(
        "Electronic journals have been opened", "Электронные журналы открыты", "Elektronik jurnallar açıldı"
    ),
    "Hansı ixtisaslar üçün?": _e("For which programmes?", "Для каких специальностей?", "Hangi programlar için?"),
    "Jurnal açıldı": _e("The journal has been opened", "Журнал открыт", "Jurnal açıldı"),
    "Kafedra": _e("Department", "Кафедра", "Bölüm"),
    "Kafedralar müəllim təyinatına başlaya bilər": _e(
        "Departments can start assigning teachers",
        "Кафедры могут начать назначение преподавателей",
        "Bölümler öğretmen atamasına başlayabilir",
    ),
    "Kafedralar üzrə açılış": _e("Opening by department", "Открытие по кафедрам", "Bölümlere göre açılış"),
    "Kafedraya göndər": _e("Send to the department", "Отправить на кафедру", "Bölüme gönder"),
    "Kafedraya göndərildi": _e("Sent to the department", "Отправлено на кафедру", "Bölüme gönderildi"),
    "Kilid geri qaytarılmır — açmaq üçün ayrıca səlahiyyət lazımdır": _e(
        "The lock is not reversible — unlocking requires a separate permission",
        "Блокировка не отменяется — для снятия требуется отдельное полномочие",
        "Kilit geri alınamaz — açmak için ayrı bir yetki gerekir",
    ),
    "Kilid şərtləri": _e("Lock conditions", "Условия блокировки", "Kilit koşulları"),
    "Kilidi aç": _e("Unlock", "Снять блокировку", "Kilidi aç"),
    "Kilidi açmaq səlahiyyətiniz yoxdur.": _e(
        "You do not have permission to unlock.", "У вас нет прав для снятия блокировки.", "Kilidi açma yetkiniz yok."
    ),
    "Kilidlənmiş semestr redaktə olunmur — əvvəlcə kilidi açın.": _e(
        "A locked semester cannot be edited — unlock it first.",
        "Заблокированный семестр не редактируется — сначала снимите блокировку.",
        "Kilitli dönem düzenlenemez — önce kilidi açın.",
    ),
    "Kilidlənmiş semestrdə açılış dəyişmir.": _e(
        "Openings cannot be changed in a locked semester.",
        "Открытия не изменяются в заблокированном семестре.",
        "Kilitli dönemde açılış değişmez.",
    ),
    "Ləğv et": _e("Cancel", "Отменить", "İptal et"),
    "Müəllim təyin olundu": _e("A teacher has been assigned", "Преподаватель назначен", "Öğretmen atandı"),
    "Müəllim təyin olunub": _e("A teacher has been assigned", "Преподаватель назначен", "Öğretmen atanmış"),
    "Müəllimi olmayan açılış var — semestr kilidlənmir.": _e(
        "There is an opening without a teacher — the semester cannot be locked.",
        "Есть открытие без преподавателя — семестр не блокируется.",
        "Öğretmeni olmayan açılış var — dönem kilitlenmiyor.",
    ),
    "Naməlum əməl.": _e("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
    "Payız semestri": _e("Fall semester", "Осенний семестр", "Güz dönemi"),
    "Plandan açılış yaradıldı": _e(
        "Openings created from the plan", "Открытия созданы из плана", "Plandan açılış oluşturuldu"
    ),
    "Plandan açılış yarat": _e("Create openings from the plan", "Создать открытия из плана", "Plandan açılış oluştur"),
    "Planın neçənci semestri?": _e("Which semester of the plan?", "Какой семестр плана?", "Planın kaçıncı dönemi?"),
    "Saat": _e("Hour", "Час", "Saat"),
    "Semestr 1–16 aralığında olmalıdır.": _e(
        "The semester must be between 1 and 16.",
        "Семестр должен быть в диапазоне 1–16.",
        "Dönem 1–16 aralığında olmalıdır.",
    ),
    "Semestr artıq kilidlidir.": _e(
        "The semester is already locked.", "Семестр уже заблокирован.", "Dönem zaten kilitli."
    ),
    "Semestr açmaq üçün səlahiyyətiniz yoxdur.": _e(
        "You do not have permission to open the semester.",
        "У вас нет прав для открытия семестра.",
        "Dönemi açma yetkiniz yok.",
    ),
    "Semestr açılışına baxış üçün səlahiyyətiniz yoxdur. Administratora müraciət edin.": _e(
        "You do not have permission to view semester opening. Contact the administrator.",
        "У вас нет прав для просмотра открытия семестра. Обратитесь к администратору.",
        "Dönem açılışını görüntüleme yetkiniz yok. Yöneticinize başvurun.",
    ),
    "Semestr açılışına səlahiyyətiniz yoxdur.": _e(
        "You do not have permission for semester opening.",
        "У вас нет прав в отношении открытия семестра.",
        "Dönem açılışı için yetkiniz yok.",
    ),
    "Semestr açılışının mərhələləri": _e(
        "Stages of semester opening", "Этапы открытия семестра", "Dönem açılışının aşamaları"
    ),
    "Semestr kilidli deyil.": _e("The semester is not locked.", "Семестр не заблокирован.", "Dönem kilitli değil."),
    "Semestr kilidlidir": _e("The semester is locked", "Семестр заблокирован", "Dönem kilitli"),
    "Semestr kilidlidir — açılış yaradıla bilməz.": _e(
        "The semester is locked — an opening cannot be created.",
        "Семестр заблокирован — открытие не может быть создано.",
        "Dönem kilitli — açılış oluşturulamaz.",
    ),
    "Semestr kilidlidir.": _e("The semester is locked.", "Семестр заблокирован.", "Dönem kilitli."),
    "Semestr kilidləndi": _e("The semester has been locked", "Семестр заблокирован", "Dönem kilitlendi"),
    "Semestr kilidlənsin? Kilid geri qaytarılmır — açmaq ayrıca səlahiyyət və səbəb tələb edir.": _e(
        "Lock the semester? The lock is not reversible — unlocking requires a separate permission and " "a reason.",
        "Заблокировать семестр? Блокировка необратима — снятие требует отдельного полномочия и причины.",
        "Dönem kilitlensin mi? Kilit geri alınamaz — açmak ayrı bir yetki ve gerekçe gerektirir.",
    ),
    "Semestr nömrəsi seçilməyib.": _e(
        "The semester number has not been selected.",
        "Номер семестра не выбран.",
        "Dönem numarası seçilmedi.",
    ),
    "Semestrdə açılış yoxdur — kilidləmək mümkün deyil.": _e(
        "There is no opening in the semester — it cannot be locked.",
        "В семестре нет открытий — заблокировать невозможно.",
        "Dönemde açılış yok — kilitlemek mümkün değil.",
    ),
    "Semestri kilidlə": _e("Lock the semester", "Заблокировать семестр", "Dönemi kilitle"),
    "Semestri kilidləmək səlahiyyətiniz yoxdur.": _e(
        "You do not have permission to lock the semester.",
        "У вас нет прав для блокировки семестра.",
        "Dönemi kilitleme yetkiniz yok.",
    ),
    "Semestrin adı": _e("Semester name", "Название семестра", "Dönem adı"),
    "Semestrin adı və tarixləri; «cari dövr» ayrıca əməldir.": _e(
        'The semester name and dates; "current period" is a separate action.',
        "Название и даты семестра; «текущий период» — отдельное действие.",
        'Dönem adı ve tarihleri; "cari dönem" ayrı bir işlemdir.',
    ),
    "Semestrin kilidini aç": _e("Unlock the semester", "Снять блокировку с семестра", "Dönemin kilidini aç"),
    "Seçilmiş ixtisasların TƏSDİQLƏNMİŞ planından hər qrup üçün açılış sətirləri yaradılır. Əməl idempotentdir — "
    "mövcud açılış təkrarlanmır və heç nə silinmir.": _e(
        "Opening lines are created for each group from the APPROVED plan of the selected programmes. "
        "The action is idempotent — existing openings are not duplicated and nothing is deleted.",
        "Строки открытия создаются для каждой группы из УТВЕРЖДЁННОГО плана выбранных специальностей. "
        "Действие идемпотентно — существующие открытия не дублируются, ничего не удаляется.",
        "Seçilen programların ONAYLANMIŞ planından her grup için açılış satırları oluşturulur. İşlem "
        "idempotenttir — mevcut açılış tekrarlanmaz ve hiçbir şey silinmez.",
    ),
    "Səbəb audit jurnalına aktor və vaxtla yazılır.": _e(
        "The reason is recorded in the audit log with the actor and timestamp.",
        "Причина записывается в журнал аудита с указанием исполнителя и времени.",
        "Gerekçe işlemi yapan kişi ve zamanla birlikte denetim günlüğüne yazılır.",
    ),
    "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.": _e(
        "The reason must be at least 20 characters — a short note is not enough for the audit.",
        "Причина должна содержать не менее 20 символов — краткая заметка недостаточна для аудита.",
        "Gerekçe en az 20 karakter olmalı — kısa bir not denetim için yeterli değildir.",
    ),
    "Tədris dövrü": _e("Academic period", "Учебный период", "Öğretim dönemi"),
    "Tədris dövrü yoxdur": _e("There is no academic period", "Учебного периода нет", "Öğretim dönemi yok"),
    "Tədris ili": _e("Academic year", "Учебный год", "Öğretim yılı"),
    "Tədris ili boş ola bilməz.": _e(
        "The academic year cannot be empty.", "Учебный год не может быть пустым.", "Öğretim yılı boş olamaz."
    ),
    "Tədris planından açılış yarat": _e(
        "Create openings from the curriculum", "Создать открытия из учебного плана", "Müfredattan açılış oluştur"
    ),
    "Təsdiqlənmiş tədris planından hər qrup üçün fənn açılışı yaradılır, kafedra müəllim təyin edir, sonra jurnal "
    "açılır. Dərs yükü məhz bu açılışlardan hesablanır.": _e(
        "A subject opening is created for each group from the approved curriculum, the department "
        "assigns a teacher, then the journal is opened. Teaching load is calculated precisely from "
        "these openings.",
        "Из утверждённого учебного плана для каждой группы создаётся открытие дисциплины, кафедра "
        "назначает преподавателя, затем открывается журнал. Учебная нагрузка рассчитывается именно из "
        "этих открытий.",
        "Onaylanmış müfredattan her grup için ders açılışı oluşturulur, bölüm öğretmen atar, ardından "
        "jurnal açılır. Ders yükü tam olarak bu açılışlardan hesaplanır.",
    ),
    "Yeni dövr": _e("New period", "Новый период", "Yeni dönem"),
    "gözləyir": _e("pending", "ожидает", "bekliyor"),
    "«Plan yoxdur» — bu ixtisaslar üçün semestr açıla bilməz": _e(
        '"No plan" — the semester cannot be opened for these programmes',
        "«Нет плана» — семестр не может быть открыт для этих специальностей",
        '"Plan yok" — bu programlar için dönem açılamaz',
    ),
    "ödənilib": _e("paid", "оплачено", "ödendi"),
    "İxtisas seçilməyib.": _e("No programme selected.", "Специальность не выбрана.", "Program seçilmedi."),
    "Əvvəlcə semestr dövrü yaradın (ad, tədris ili, başlama və bitmə tarixi).": _e(
        "First create the semester period (name, academic year, start and end date).",
        "Сначала создайте период семестра (название, учебный год, дата начала и окончания).",
        "Önce dönem periyodu oluşturun (ad, öğretim yılı, başlama ve bitiş tarihi).",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.student_admission — ATİS qəbulu (ekran 08)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_STUDENT_ADMISSION = {
    "1 · ATİS şablonunu endirin": _e(
        "1 · Download the ATİS template", "1 · Скачайте шаблон АТИС", "1 · ATİS şablonunu indirin"
    ),
    "2 · Faylı yükləyin və yoxlayın": _e(
        "2 · Upload the file and validate it", "2 · Загрузите файл и проверьте", "2 · Dosyayı yükleyin ve doğrulayın"
    ),
    "ATİS qəbul faylı": _e("ATİS admission file", "Файл приёма АТИС", "ATİS kabul dosyası"),
    "ATİS sütunları": _e("ATİS columns", "Столбцы АТИС", "ATİS sütunları"),
    "ATİS-dən gələn qəbul siyahısı yüklənir, sistem sətirləri yoxlayır (FİN təkrarı, ixtisas kodunun uyğunluğu, "
    "sənəd tamlığı), sonra tələbələr ixtisasın qruplarına təyin edilir. Qrup təklifi avtomatikdir — dil bölməsi "
    "və boş yerə görə; operator onu dəyişə bilər.": _e(
        "The admission list from ATİS is uploaded, the system validates the rows (duplicate PIN, "
        "programme code match, document completeness), then students are assigned to the programme's "
        "groups. The group suggestion is automatic — based on the language section and vacancies; the "
        "operator can change it.",
        "Загружается список приёма из АТИС, система проверяет строки (дубликаты ПИН, соответствие кода "
        "специальности, полнота документов), затем студенты распределяются по группам специальности. "
        "Предложение группы автоматическое — по языковому сектору и наличию мест; оператор может его "
        "изменить.",
        "ATİS'ten gelen kabul listesi yüklenir, sistem satırları doğrular (Kimlik No tekrarı, program "
        "kodu uyumu, belge eksiksizliği), ardından öğrenciler programın gruplarına atanır. Grup önerisi "
        "otomatiktir — dil sektörüne ve boş yere göre; operatör bunu değiştirebilir.",
    ),
    "Avtomatik təklif — əl ilə dəyişilə bilər": _e(
        "Automatic suggestion — can be changed manually",
        "Автоматическое предложение — можно изменить вручную",
        "Otomatik öneri — elle değiştirilebilir",
    ),
    "BLOKLAYAN XƏTA": _e("BLOCKING ERROR", "БЛОКИРУЮЩАЯ ОШИБКА", "ENGELLEYİCİ HATA"),
    "Birdəfəlik parollar YALNIZ indi görünür — nə bazada, nə də audit jurnalında saxlanılmır. CSV-ni endirib qrup "
    "üzrə tələbələrə çatdırın; ilk girişdə hər tələbə e-poçt təsdiqi (OTP) və yeni parol tələb olunacaq.": _e(
        "One-time passwords are shown ONLY now — they are stored neither in the database nor in the "
        "audit log. Download the CSV and deliver it to students by group; on first login each student "
        "will need an email confirmation (OTP) and a new password.",
        "Одноразовые пароли отображаются ТОЛЬКО сейчас — они не сохраняются ни в базе данных, ни в "
        "журнале аудита. Скачайте CSV и передайте его студентам по группам; при первом входе каждому "
        "студенту потребуется подтверждение по электронной почте (OTP) и новый пароль.",
        "Tek seferlik parolalar YALNIZCA şimdi görünür — ne veritabanında ne de denetim günlüğünde "
        "saklanır. CSV'yi indirip gruplara göre öğrencilere ulaştırın; ilk girişte her öğrenci e-posta "
        "onayı (OTP) ve yeni bir parola gerektirecek.",
    ),
    "Bloklayan xəta olan sətir qrupa təyin edilə bilmir": _e(
        "A row with a blocking error cannot be assigned to a group",
        "Строка с блокирующей ошибкой не может быть назначена в группу",
        "Engelleyici hatası olan satır gruba atanamaz",
    ),
    "Boş şablonu endir": _e("Download the empty template", "Скачать пустой шаблон", "Boş şablonu indir"),
    "CƏMİ SƏTİR": _e("TOTAL ROWS", "ВСЕГО СТРОК", "TOPLAM SATIR"),
    "Cəmi": _e("Total", "Всего", "Toplam"),
    "Emal olunur…": _e("Processing…", "Обработка…", "İşleniyor…"),
    "Fayl seçilməyib": _e("No file selected", "Файл не выбран", "Dosya seçilmedi"),
    "Forma / dil": _e("Mode / language", "Форма / язык", "Şekil / dil"),
    "Parolları CSV kimi endir": _e(
        "Download passwords as CSV", "Скачать пароли в формате CSV", "Parolaları CSV olarak indir"
    ),
    "Qrup adı": _e("Group name", "Название группы", "Grup adı"),
    "Qrup ixtisasın altında yaranır; tutum və dil bölməsi sonradan struktur ağacından dəyişdirilə bilər.": _e(
        "The group is created under the programme; the capacity and language section can be changed "
        "later from the structure tree.",
        "Группа создаётся в рамках специальности; вместимость и языковой сектор можно изменить позже "
        "из дерева структуры.",
        "Grup, programın altında oluşturulur; kapasite ve dil sektörü daha sonra yapı ağacından " "değiştirilebilir.",
    ),
    "Qrup kodu": _e("Group code", "Код группы", "Grup kodu"),
    "Qrup seçilməyib": _e("No group selected", "Группа не выбрана", "Grup seçilmedi"),
    "Qrup təyinatı": _e("Group assignment", "Назначение в группу", "Grup ataması"),
    "Qrupu yarat": _e("Create the group", "Создать группу", "Grubu oluştur"),
    "Quru icra nəticəsi (heç nə yazılmadı)": _e(
        "Dry-run result (nothing was written)",
        "Результат сухого прогона (ничего не записано)",
        "Deneme sonucu (hiçbir şey yazılmadı)",
    ),
    "Qəbul axınının addımları": _e("Admission flow steps", "Этапы процесса приёма", "Kabul akışının adımları"),
    "Qəbul balı": _e("Admission score", "Балл приёма", "Kabul puanı"),
    "Qəbul olduğu ixtisas": _e("Admitted programme", "Специальность зачисления", "Kabul edildiği program"),
    "Seçilmiş sətirlər üçün hesab yaradılacaq. Davam edilsin?": _e(
        "Accounts will be created for the selected rows. Continue?",
        "Для выбранных строк будут созданы учётные записи. Продолжить?",
        "Seçilen satırlar için hesap oluşturulacak. Devam edilsin mi?",
    ),
    "Sütunların sırası sərbəstdir — başlıq adına görə tanınır. Bir faylda ən çox %(limit)s sətir, ölçü limiti "
    "%(size)s MB.": _e(
        "The column order is free — columns are recognized by header name. A file can have at most "
        "%(limit)s rows, with a size limit of %(size)s MB.",
        "Порядок столбцов свободный — они распознаются по названию заголовка. В файле не более "
        "%(limit)s строк, ограничение размера %(size)s МБ.",
        "Sütun sırası serbesttir — başlık adına göre tanınır. Bir dosyada en fazla %(limit)s satır, "
        "boyut sınırı %(size)s MB.",
    ),
    "Sətir": _e("Row", "Строка", "Satır"),
    "Tədris dili": _e("Language of instruction", "Язык обучения", "Öğretim dili"),
    "Təhsil haqqı": _e("Tuition fee", "Плата за обучение", "Öğrenim ücreti"),
    "Tələbə": _e("Student", "Студент", "Öğrenci"),
    "Tələbə Xidmətləri Mərkəzi": _e(
        "Student Services Center", "Центр обслуживания студентов", "Öğrenci Hizmetleri Merkezi"
    ),
    "Tələbə qəbulu üçün icazəniz yoxdur — `user.import` açarı tələb olunur.": _e(
        "You do not have permission for student admission — the `user.import` key is required.",
        "У вас нет прав для приёма студентов — требуется ключ `user.import`.",
        "Öğrenci kabulü için izniniz yok — `user.import` anahtarı gereklidir.",
    ),
    "Tətbiq et": _e("Apply", "Применить", "Uygula"),
    "Tətbiq nəticəsi": _e("Application result", "Результат применения", "Uygulama sonucu"),
    "Universitetin öz adlandırma qaydası tətbiq olunur — təklif yalnız ilkin dəyərdir.": _e(
        "The university's own naming convention is applied — the suggestion is only a starting value.",
        "Применяется собственное правило именования университета — предложение является лишь начальным " "значением.",
        "Üniversitenin kendi adlandırma kuralı uygulanır — öneri yalnızca bir başlangıç değeridir.",
    ),
    "XƏBƏRDARLIQ": _e("WARNING", "ПРЕДУПРЕЖДЕНИЕ", "UYARI"),
    "Xəta": _e("Error", "Ошибка", "Hata"),
    "YOXLAMADAN KEÇDİ": _e("PASSED VALIDATION", "ПРОШЛА ПРОВЕРКУ", "DOĞRULAMADAN GEÇTİ"),
    "Yaradılacaq": _e("Will be created", "Будет создано", "Oluşturulacak"),
    "Yaradıldı": _e("Created", "Создано", "Oluşturuldu"),
    "Yeni qrup": _e("New group", "Новая группа", "Yeni grup"),
    "Yeni qrup yarat": _e("Create a new group", "Создать новую группу", "Yeni grup oluştur"),
    "Yer limiti": _e("Place limit", "Лимит мест", "Yer limiti"),
    "Yoxla (quru icra)": _e("Validate (dry run)", "Проверить (сухой прогон)", "Doğrula (deneme)"),
    "Yoxlamanın nəticəsi": _e("Validation result", "Результат проверки", "Doğrulama sonucu"),
    "dolu": _e("full", "заполнено", "dolu"),
    "Ötürüldü": _e("Skipped", "Пропущено", "Atlandı"),
    "İxtisas kodu ilə fakültəyə düşür": _e(
        "Falls under the faculty by the programme code",
        "Определяется на факультет по коду специальности",
        "Program koduyla fakülteye düşer",
    ),
    "İzah": _e("Explanation", "Пояснение", "Açıklama"),
    "Əməliyyat alınmadı. Yenidən cəhd edin.": _e(
        "The operation failed. Please try again.",
        "Операция не выполнена. Попробуйте снова.",
        "İşlem başarısız oldu. Tekrar deneyin.",
    ),
    "Əvvəlcə fayl seçin.": _e("Select a file first.", "Сначала выберите файл.", "Önce bir dosya seçin."),
}

# ─────────────────────────────────────────────────────────────────────────────
# accounts.student_registry — Tələbə reyestri (ekran 09)
# ─────────────────────────────────────────────────────────────────────────────
ACCOUNTS_STUDENT_REGISTRY = {
    "ATİS nömrəsi": _e("ATİS number", "Номер АТИС", "ATİS numarası"),
    "Ad Soyad": _e("Full name", "ФИО", "Ad Soyad"),
    "Ad, FİN və ya tələbə kodu": _e(
        "Name, PIN, or student code", "Имя, ПИН или код студента", "Ad, Kimlik No veya öğrenci kodu"
    ),
    "Axtarış": _e("Search", "Поиск", "Arama"),
    "Bu tələbə üzrə hərəkət əmri yoxdur.": _e(
        "There is no movement order for this student.",
        "По этому студенту нет приказа о движении.",
        "Bu öğrenci için hareket emri yok.",
    ),
    "CSV ixracı": _e("CSV export", "Экспорт CSV", "CSV dışa aktarımı"),
    "CƏMİ TƏLƏBƏ": _e("TOTAL STUDENTS", "ВСЕГО СТУДЕНТОВ", "TOPLAM ÖĞRENCİ"),
    "Dil bölməsi": _e("Language section", "Языковой сектор", "Dil bölümü"),
    "DÖVLƏT SİFARİŞİ": _e("STATE-FUNDED", "ГОСУДАРСТВЕННЫЙ ЗАКАЗ", "DEVLET KONTENJANI"),
    "Fakültə": _e("Faculty", "Факультет", "Fakülte"),
    "Filtrə uyğun tələbə yoxdur": _e(
        "There are no students matching the filter",
        "Нет студентов, соответствующих фильтру",
        "Filtreye uygun öğrenci yok",
    ),
    "Forma": _e("Mode", "Форма", "Şekil"),
    "FİN": _e("PIN", "ПИН", "Kimlik No"),
    "Hamısı": _e("All", "Все", "Tümü"),
    "Hərəkət tarixçəsi": _e("Movement history", "История движений", "Hareket geçmişi"),
    "Hərəkət əmri": _e("Movement order", "Приказ о движении", "Hareket emri"),
    "Kart": _e("Card", "Карта", "Kart"),
    "Kurs": _e("Year of study", "Курс", "Sınıf"),
    "Məzuniyyət / xaric / məzun": _e(
        "Academic leave / expulsion / graduation",
        "Академический отпуск / отчисление / выпуск",
        "Akademik izin / ilişik kesme / mezuniyet",
    ),
    "Məzuniyyətin bitmə tarixi": _e("End date of the leave", "Дата окончания отпуска", "İznin bitiş tarihi"),
    "Nəticə: %(count)d sətir": _e("Result: %(count)d rows", "Результат: %(count)d строк", "Sonuç: %(count)d satır"),
    "Qrup": _e("Group", "Группа", "Grup"),
    "QİYABİ": _e("PART-TIME", "ЗАОЧНАЯ", "İKİNCİ ÖĞRETİM"),
    "Qəbul balı": _e("Admission score", "Балл приёма", "Kabul puanı"),
    "Qəbul ili": _e("Year of admission", "Год поступления", "Kabul yılı"),
    "Rolunuzda struktur əhatəsi (fakültə/ixtisas) təyin edilməyib — administratorla əlaqə saxlayın. Əhatəsiz rol "
    "bütün universiteti görmür.": _e(
        "Your role has no structural scope (faculty/programme) assigned — contact the administrator. "
        "A role without scope does not see the whole university.",
        "В вашей роли не задан структурный охват (факультет/специальность) — обратитесь к "
        "администратору. Роль без охвата не видит весь университет.",
        "Rolünüzde yapısal kapsam (fakülte/program) atanmamış — yöneticinizle iletişime geçin. Kapsamsız "
        "rol tüm üniversiteyi görmez.",
    ),
    "Seçin": _e("Select", "Выберите", "Seçin"),
    "Sizə təyin olunmuş əhatə yoxdur": _e(
        "You have no assigned scope", "Вам не назначен охват", "Size atanmış kapsam yok"
    ),
    "Status": _e("Status", "Статус", "Durum"),
    "Statusu": _e("Status", "Статус", "Durumu"),
    "Süzgəcləri dəyişin və ya axtarış sözünü qısaldın.": _e(
        "Change the filters or shorten the search term.",
        "Измените фильтры или сократите поисковый запрос.",
        "Filtreleri değiştirin veya arama sözcüğünü kısaltın.",
    ),
    "Toplanmış kredit": _e("Credits earned", "Набранные кредиты", "Kazanılan kredi"),
    "Təhsil forması": _e("Mode of study", "Форма обучения", "Öğretim şekli"),
    "Təhsil haqqı": _e("Tuition fee", "Плата за обучение", "Öğrenim ücreti"),
    "Tələbə": _e("Student", "Студент", "Öğrenci"),
    "Tələbə hərəkəti — əmr": _e("Student movement — order", "Движение студента — приказ", "Öğrenci hareketi — emir"),
    "Tələbə kartı": _e("Student card", "Карта студента", "Öğrenci kartı"),
    "Tələbə kodu": _e("Student code", "Код студента", "Öğrenci kodu"),
    "Tələbə reyestrinə baxış üçün icazəniz yoxdur — administratorla əlaqə saxlayın.": _e(
        "You do not have permission to view the student registry — contact the administrator.",
        "У вас нет прав для просмотра реестра студентов — обратитесь к администратору.",
        "Öğrenci siciline erişim izniniz yok — yöneticinizle iletişime geçin.",
    ),
    "Universitetin bütün tələbələri: ixtisas, qrup, kurs, forma, maliyyələşmə və akademik status. Hərəkət yalnız "
    "əmr nömrəsi, tarix və əsaslandırma ilə yazılır.": _e(
        "All students of the university: programme, group, year, mode, funding, and academic status. "
        "A movement is recorded only with an order number, date, and justification.",
        "Все студенты университета: специальность, группа, курс, форма, финансирование и академический "
        "статус. Движение записывается только с номером приказа, датой и обоснованием.",
        "Üniversitenin tüm öğrencileri: program, grup, sınıf, şekil, finansman ve akademik durum. "
        "Hareket yalnızca emir numarası, tarih ve gerekçe ile kaydedilir.",
    ),
    "XÜSUSİ STATUSLU": _e("SPECIAL STATUS", "СО СПЕЦИАЛЬНЫМ СТАТУСОМ", "ÖZEL DURUMLU"),
    "Yalnız sizin əhatənizdəki, boş yeri olan qruplar.": _e(
        "Only groups within your scope that have a vacancy.",
        "Только группы в вашем охвате, имеющие свободные места.",
        "Yalnızca kapsamınızdaki, boş yeri olan gruplar.",
    ),
    "Yeni ixtisas": _e("New programme", "Новая специальность", "Yeni program"),
    "Yeni ixtisasın həmin qəbul ili üçün tədris planı olmalıdır.": _e(
        "The new programme must have a curriculum for that admission year.",
        "Для новой специальности должен быть учебный план на этот год приёма.",
        "Yeni programın o kabul yılı için müfredatı olmalıdır.",
    ),
    "Yeni qrup": _e("New group", "Новая группа", "Yeni grup"),
    "Yeni təhsil forması": _e("New mode of study", "Новая форма обучения", "Yeni öğretim şekli"),
    "ÜOMG (GPA)": _e("CGPA (GPA)", "Средний балл (GPA)", "AGNO (GPA)"),
    "İmtahan növü": _e("Assessment form", "Форма оценивания", "Değerlendirme şekli"),
    "İxrac üçün icazəniz yoxdur.": _e(
        "You do not have permission to export.", "У вас нет прав для экспорта.", "Dışa aktarma izniniz yok."
    ),
    "İxtisas": _e("Programme", "Специальность", "Program"),
    "İxtisas və qrup": _e("Programme and group", "Специальность и группа", "Program ve grup"),
    "ƏYANİ": _e("FULL-TIME", "ОЧНАЯ", "ÖRGÜN ÖĞRETİM"),
    "Əmr": _e("Order", "Приказ", "Emir"),
    "Əmr nömrəsi": _e("Order number", "Номер приказа", "Emir numarası"),
    "Əmr yazıldıqdan sonra silinmir və dəyişdirilmir; tələbənin statusu dərhal dəyişir və tarixçəyə bir sətir "
    "əlavə olunur.": _e(
        "Once written, an order is not deleted or changed; the student's status changes immediately and "
        "a line is added to the history.",
        "После оформления приказ не удаляется и не изменяется; статус студента меняется немедленно и в "
        "историю добавляется строка.",
        "Emir yazıldıktan sonra silinmez ve değiştirilmez; öğrencinin durumu hemen değişir ve geçmişe "
        "bir satır eklenir.",
    ),
    "Əmri yaz": _e("Write the order", "Оформить приказ", "Emri yaz"),
    "Əmrin tarixi": _e("Order date", "Дата приказа", "Emir tarihi"),
    "Əməliyyatın növü": _e("Type of operation", "Тип операции", "İşlem türü"),
    "Əməllər": _e("Actions", "Действия", "İşlemler"),
    "Ərizə, arayış və ya protokol — opsional (ən çox 10 MB).": _e(
        "Application, certificate, or minutes — optional (at most 10 MB).",
        "Заявление, справка или протокол — необязательно (не более 10 МБ).",
        "Dilekçe, belge veya tutanak — opsiyonel (en fazla 10 MB).",
    ),
    "Əsas sənəd": _e("Supporting document", "Основной документ", "Dayanak belge"),
    "Əsas və əsaslandırma": _e("Basis and justification", "Основание и обоснование", "Dayanak ve gerekçe"),
}

# ─────────────────────────────────────────────────────────────────────────────
# organizations.permission.label — YENİ icazə etiketləri (Stage 2 + 3)
# ─────────────────────────────────────────────────────────────────────────────
ORGANIZATIONS_PERMISSION_LABEL = {
    "Akademik qrup yaratmaq/idarə etmək": _e(
        "Create/manage academic groups",
        "Создавать/управлять академическими группами",
        "Akademik grup oluşturmak/yönetmek",
    ),
    "Plandan semestr açılışı yaratmaq": _e(
        "Create semester opening from the plan",
        "Создавать открытие семестра из плана",
        "Plandan dönem açılışı oluşturmak",
    ),
    "Qəbulda tələbəni qrupa təyin etmək və qrup yaratmaq": _e(
        "Assign a student to a group and create groups during admission",
        "Назначать студента в группу и создавать группы при приёме",
        "Kabulde öğrenciyi gruba atamak ve grup oluşturmak",
    ),
    "Semestr açılışına baxış": _e("View semester opening", "Просмотр открытия семестра", "Dönem açılışını görüntüleme"),
    "Semestri kilidləmək": _e("Lock the semester", "Блокировать семестр", "Dönemi kilitlemek"),
    "Semestrin kilidini açmaq (səbəblə)": _e(
        "Unlock the semester (with a reason)",
        "Снимать блокировку семестра (с указанием причины)",
        "Dönemin kilidini açmak (gerekçeyle)",
    ),
    "Tədris planına baxış": _e("View the curriculum", "Просмотр учебного плана", "Müfredatı görüntüleme"),
    "Tədris planını Tədris şöbəsi adından təsdiqləmək": _e(
        "Approve the curriculum on behalf of the Teaching Office",
        "Утверждать учебный план от имени Учебного отдела",
        "Müfredatı Öğretim İşleri Dairesi adına onaylamak",
    ),
    "Tədris planını fakültə şurası adından təsdiqləmək": _e(
        "Approve the curriculum on behalf of the faculty council",
        "Утверждать учебный план от имени совета факультета",
        "Müfredatı fakülte kurulu adına onaylamak",
    ),
    "Tədris planını kafedra adından təsdiqləmək": _e(
        "Approve the curriculum on behalf of the department",
        "Утверждать учебный план от имени кафедры",
        "Müfredatı bölüm adına onaylamak",
    ),
    "Tədris planını təsdiqə göndərmək": _e(
        "Submit the curriculum for approval",
        "Отправлять учебный план на утверждение",
        "Müfredatı onaya göndermek",
    ),
    "Tədris planının qaralamasını redaktə etmək": _e(
        "Edit the curriculum draft", "Редактировать черновик учебного плана", "Müfredat taslağını düzenlemek"
    ),
    "Tələbə hərəkəti əmri yazmaq (köçürmə, məzuniyyət, bərpa, xaric)": _e(
        "Write a student movement order (transfer, academic leave, reinstatement, expulsion)",
        "Оформлять приказ о движении студента (перевод, академический отпуск, восстановление, " "отчисление)",
        "Öğrenci hareketi emri yazmak (nakil, akademik izin, kayıt yenileme, ilişik kesme)",
    ),
    "Tələbə reyestrinə baxış (hərəkət tarixçəsi və ixrac)": _e(
        "View the student registry (movement history and export)",
        "Просмотр реестра студентов (история движений и экспорт)",
        "Öğrenci sicilini görüntüleme (hareket geçmişi ve dışa aktarım)",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# organizations.semester_opening — Semestr açılışı vəziyyət kataloqu
# ─────────────────────────────────────────────────────────────────────────────
ORGANIZATIONS_SEMESTER_OPENING = {
    "Başlanmayıb": _e("Not started", "Не начато", "Başlamadı"),
    "Kafedraya göndərildi": _e("Sent to the department", "Отправлено на кафедру", "Bölüme gönderildi"),
    "Plandan açılış yaradıldı": _e(
        "Openings created from the plan", "Открытия созданы из плана", "Plandan açılış oluşturuldu"
    ),
    "Semestr kilidləndi": _e("The semester has been locked", "Семестр заблокирован", "Dönem kilitlendi"),
}

# ─────────────────────────────────────────────────────────────────────────────
# profile.sidebar — Stage 2/3 profil menyu bəndləri
# ─────────────────────────────────────────────────────────────────────────────
PROFILE_SIDEBAR = {
    "Qruplar": _e("Groups", "Группы", "Gruplar"),
    "Semestr açılışı": _e("Semester opening", "Открытие семестра", "Dönem açılışı"),
    "Tədris planı": _e("Curriculum", "Учебный план", "Müfredat"),
    "Tələbə Xidmətləri": _e("Student Services", "Обслуживание студентов", "Öğrenci Hizmetleri"),
    "Tələbə qəbulu": _e("Student admission", "Приём студентов", "Öğrenci kabulü"),
    "Tələbə reyestri": _e("Student registry", "Реестр студентов", "Öğrenci sicili"),
}

# ─────────────────────────────────────────────────────────────────────────────
# registrar.assessment_form — Program.assessment_form TextChoices
# ─────────────────────────────────────────────────────────────────────────────
REGISTRAR_ASSESSMENT_FORM = {
    "Buraxılış işi": _e("Thesis", "Дипломная работа", "Bitirme tezi"),
    "Hesabat": _e("Report", "Отчёт", "Rapor"),
    "Kurs işi": _e("Coursework", "Курсовая работа", "Dönem ödevi"),
    "Təcrübə": _e("Practice", "Практика", "Uygulama"),
    "İmtahan": _e("Exam", "Экзамен", "Sınav"),
}

# ─────────────────────────────────────────────────────────────────────────────
# registrar.funding_type — Student.funding_type TextChoices
# ─────────────────────────────────────────────────────────────────────────────
REGISTRAR_FUNDING_TYPE = {
    "Dövlət sifarişi": _e("State-funded", "Государственный заказ", "Devlet kontenjanı"),
    "Ödənişli": _e("Paid", "Платно", "Ücretli"),
}

# ─────────────────────────────────────────────────────────────────────────────
# registrar.plan_status — CurriculumPlan.status TextChoices
# ─────────────────────────────────────────────────────────────────────────────
REGISTRAR_PLAN_STATUS = {
    "Fakültə şurası": _e("Faculty council", "Совет факультета", "Fakülte kurulu"),
    "Kafedra baxışı": _e("Department review", "Рассмотрение кафедры", "Bölüm incelemesi"),
    "Qaralama": _e("Draft", "Черновик", "Taslak"),
    "Qaytarılıb": _e("Returned", "Возвращено", "İade edildi"),
    "Tədris şöbəsi": _e("Teaching Office", "Учебный отдел", "Öğretim İşleri Dairesi"),
    "Təsdiqlənib": _e("Approved", "Утверждено", "Onaylandı"),
}

# ─────────────────────────────────────────────────────────────────────────────
# student_intake — ATİS qəbul emalı (servis qatı)
# ─────────────────────────────────────────────────────────────────────────────
STUDENT_INTAKE = {
    "ATİS nömrəsi": _e("ATİS number", "Номер АТИС", "ATİS numarası"),
    "ATİS siyahısındakı sətir nömrəsi": _e(
        "Row number in the ATİS list", "Номер строки в списке АТИС", "ATİS listesindeki satır numarası"
    ),
    "Bu adla qrup artıq var.": _e(
        "A group with this name already exists.",
        "Группа с таким названием уже существует.",
        "Bu adla bir grup zaten var.",
    ),
    "Bu şifrlə birdən çox ixtisas var — dəqiqləşdirin: %s": _e(
        "There is more than one programme with this code — clarify: %s",
        "С этим кодом есть более одной специальности — уточните: %s",
        "Bu kodla birden fazla program var — netleştirin: %s",
    ),
    "Məsələn 543,5": _e("E.g. 543.5", "Например 543,5", "Örneğin 543,5"),
    "Məsələn «I qrup»": _e('E.g. "Group I"', "Например «I группа»", 'Örneğin "I. grup"'),
    "Qrup avtomatik təklif olundu: %s — tətbiqdən əvvəl dəyişə bilərsiniz.": _e(
        "The group was suggested automatically: %s — you can change it before applying.",
        "Группа предложена автоматически: %s — вы можете изменить её перед применением.",
        "Grup otomatik olarak önerildi: %s — uygulamadan önce değiştirebilirsiniz.",
    ),
    "Qrupun adı boş ola bilməz.": _e(
        "The group name cannot be empty.", "Название группы не может быть пустым.", "Grup adı boş olamaz."
    ),
    "Qəbul balı": _e("Admission score", "Балл приёма", "Kabul puanı"),
    "Qəbul balı tanınmadı — boş saxlanılır.": _e(
        "The admission score was not recognized — left empty.",
        "Балл приёма не распознан — оставлен пустым.",
        "Kabul puanı tanınmadı — boş bırakılıyor.",
    ),
    "Rəsmi şifr (NK 503) — qrup verilməyibsə MƏCBURİ": _e(
        "Official code (NK 503) — REQUIRED if no group is given",
        "Официальный код (NK 503) — ОБЯЗАТЕЛЕН, если группа не указана",
        "Resmi kod (NK 503) — grup verilmemişse ZORUNLU",
    ),
    "Təhsil forması": _e("Mode of study", "Форма обучения", "Öğretim şekli"),
    "Təhsil forması tanınmadı — «əyani» tətbiq olunur.": _e(
        'The mode of study was not recognized — "full-time" is applied.',
        "Форма обучения не распознана — применяется «очная».",
        'Öğretim şekli tanınmadı — "örgün öğretim" uygulanıyor.',
    ),
    "Təhsil haqqı": _e("Tuition fee", "Плата за обучение", "Öğrenim ücreti"),
    "Təhsil haqqı sütunu tanınmadı — «ödənişli» tətbiq olunur.": _e(
        'The tuition fee column was not recognized — "paid" is applied.',
        "Столбец платы за обучение не распознан — применяется «платное».",
        'Öğrenim ücreti sütunu tanınmadı — "ücretli" uygulanıyor.',
    ),
    "Uyğun boş qrup tapılmadı — tətbiqdən əvvəl qrup seçin və ya yeni qrup yaradın.": _e(
        "No matching group with a vacancy was found — select a group or create a new one before applying.",
        "Подходящая свободная группа не найдена — выберите группу или создайте новую перед применением.",
        "Uygun boş grup bulunamadı — uygulamadan önce bir grup seçin veya yeni grup oluşturun.",
    ),
    "dövlət sifarişi / ödənişli": _e("state-funded / paid", "гособеспечение / платно", "devlet kontenjanı / ücretli"),
    "İmtahan növü": _e("Assessment form", "Форма оценивания", "Değerlendirme şekli"),
    "İxtisas kodu": _e("Programme code", "Код специальности", "Program kodu"),
    "İxtisas kodu universitetdə tapılmadı": _e(
        "The programme code was not found at the university",
        "Код специальности не найден в университете",
        "Program kodu üniversitede bulunamadı",
    ),
    "İxtisas tapılmadı.": _e("Programme not found.", "Специальность не найдена.", "Program bulunamadı."),
    "əyani / qiyabi / distant": _e(
        "full-time / part-time / distance", "очная / заочная / дистанционная", "örgün / ikinci öğretim / uzaktan"
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# registrar.model.student_movement.meta — Model Meta verbose_name (msgid İNGİLİSCƏ)
# ─────────────────────────────────────────────────────────────────────────────
REGISTRAR_MODEL_STUDENT_MOVEMENT_META = {
    "student movement": _e("student movement", "движение студента", "öğrenci hareketi"),
    "student movements": _e("student movements", "движения студента", "öğrenci hareketleri"),
}
AZ_OVERRIDES_STUDENT_MOVEMENT_META = {
    "student movement": "tələbə hərəkəti",
    "student movements": "tələbə hərəkətləri",
}

# ─────────────────────────────────────────────────────────────────────────────
# ui.dialog — form dialoqlarının ümumi düyməsi
# ─────────────────────────────────────────────────────────────────────────────
UI_DIALOG = {
    "Yadda saxla": _e("Save", "Сохранить", "Kaydet"),
}

# ─────────────────────────────────────────────────────────────────────────────
# ui.status — tələbənin akademik statusu + offering/plan əlavələri (Stage 2/3)
# ─────────────────────────────────────────────────────────────────────────────
UI_STATUS = {
    "Ləğv edilib": _e("Cancelled", "Отменено", "İptal edildi"),
    "Məzun": _e("Graduated", "Выпускник", "Mezun"),
    "Xaric edilib": _e("Expelled", "Отчислен(а)", "İlişiği kesildi"),
}

ENTRIES = {
    "accounts.curriculum": ACCOUNTS_CURRICULUM,
    "accounts.groups": ACCOUNTS_GROUPS,
    "accounts.semester": ACCOUNTS_SEMESTER,
    "accounts.student_admission": ACCOUNTS_STUDENT_ADMISSION,
    "accounts.student_registry": ACCOUNTS_STUDENT_REGISTRY,
    "organizations.permission.label": ORGANIZATIONS_PERMISSION_LABEL,
    "organizations.semester_opening": ORGANIZATIONS_SEMESTER_OPENING,
    "profile.sidebar": PROFILE_SIDEBAR,
    "registrar.assessment_form": REGISTRAR_ASSESSMENT_FORM,
    "registrar.funding_type": REGISTRAR_FUNDING_TYPE,
    "registrar.plan_status": REGISTRAR_PLAN_STATUS,
    "student_intake": STUDENT_INTAKE,
    "registrar.model.student_movement.meta": REGISTRAR_MODEL_STUDENT_MOVEMENT_META,
    "ui.dialog": UI_DIALOG,
    "ui.status": UI_STATUS,
}

#: `az` msgstr identity DEYİL bu kontekstlərdə (bax modul başlığı).
AZ_OVERRIDES = {
    "registrar.model.student_movement.meta": AZ_OVERRIDES_STUDENT_MOVEMENT_META,
}

_expected_total = 387
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
