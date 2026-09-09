#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-09 redizayn sessiyasının mətnləri (4 dil). İdempotent.

Bu sessiyada bitmiş bölmələr kodda YENİ mətnlər gətirdi, kataloqlarda isə onların
heç biri yox idi (`check_i18n_catalogs.py`: `django.source_missing` 373 → 417).
Skript həmin boşluğu bağlayır:

* `organizations.registry` + `accounts.structure_tree` — struktur reyestrləri
  (fakültə/kafedra kartları, rəhbər/heyət təyinatı, arxivləmə);
* `organizations.members` — üzv kartı çekmecəsi;
* `accounts.people`, `.page`, `.detail` — şəxslər kataloqu və şəxs səhifəsi;
* `accounts.groups` — qrup çekmecəsi (tələbə əlavəsi, qrup dəyişikliyi);
* `audit.section` — audit jurnalı və hadisə detalı;
* `profile.publish_notification`, `.notifications` — bildiriş dərci və qutusu;
* `profile.rim`, `profile.sidebar`, `appeals.template`, qəbul sehrbazları.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir; mövcud giriş (msgctxt + msgid) varsa ötürülür. `az` kataloqunda
msgstr = msgid (mənbə mətni azərbaycancadır); `en`/`ru`/`tr` üçün əsl tərcümə
verilir, çünki qapının `identity` ratcheti msgstr == msgid-i borc sayır. Yer
tutucular (`%(name)s`, `%%d`, `%%s`) tərcümədə də EYNİ qalmalıdır.

İstifadə::

    python scripts/i18n_fill_session_redesign_2026_09_09.py
    # sonra YALNIZ django domeni üçün .mo yenilənir (djangojs.mo toxunulmur)
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# ── «Struktur reyestrləri» — fakültə/kafedra kartları, rəhbər və heyət təyinatı ───

_ORG_REGISTRY = {
    "%%d nəfər": {
        "en": "%%d people",
        "ru": "%%d чел.",
        "tr": "%%d kişi",
    },
    "%%s üçün «%%s» təyinatı silinsin? Əməl audit jurnalına yazılır.": {
        "en": "For %%s, remove the “%%s” assignment? The action is written to the audit log.",
        "ru": "Для %%s удалить назначение «%%s»? Действие записывается в журнал аудита.",
        "tr": "%%s için «%%s» ataması silinsin mi? İşlem denetim günlüğüne yazılır.",
    },
    "%(n)s müəllim": {
        "en": "%(n)s teachers",
        "ru": "%(n)s преподавателей",
        "tr": "%(n)s öğretmen",
    },
    "%(name)s — arxivlə": {
        "en": "%(name)s — archive",
        "ru": "%(name)s — архивировать",
        "tr": "%(name)s — arşivle",
    },
    "%(name)s — redaktə": {
        "en": "%(name)s — edit",
        "ru": "%(name)s — изменить",
        "tr": "%(name)s — düzenle",
    },
    "(istəyə bağlı)": {
        "en": "(optional)",
        "ru": "(необязательно)",
        "tr": "(isteğe bağlı)",
    },
    "Ad": {
        "en": "Name",
        "ru": "Имя",
        "tr": "İsim",
    },
    "Ad eyni növ bölmələr arasında unikaldır.": {
        "en": "The name is unique among units of the same type.",
        "ru": "Название уникально среди подразделений одного типа.",
        "tr": "Ad, aynı türdeki birimler arasında benzersizdir.",
    },
    "Ad eyni növ bölmələr arasında unikaldır; kafedra mütləq bir fakültəyə bağlanır.": {
        "en": "The name is unique among units of the same type; a department must belong to a faculty.",
        "ru": "Название уникально среди подразделений одного типа; кафедра обязательно относится к факультету.",
        "tr": "Ad, aynı türdeki birimler arasında benzersizdir; bölüm mutlaka bir fakülteye bağlanır.",
    },
    "Ad eyni növ bölmələr arasında unikaldır; kod sənədlərdə və filtrdə işlənir.": {
        "en": "The name is unique among units of the same type; the code is used in documents and filters.",
        "ru": "Название уникально среди подразделений одного типа; код используется в документах и фильтрах.",
        "tr": "Ad, aynı türdeki birimler arasında benzersizdir; kod belgelerde ve filtrelerde kullanılır.",
    },
    "Ad və ya istifadəçi adı ilə axtar…": {
        "en": "Search by name or username…",
        "ru": "Поиск по имени или логину…",
        "tr": "Ad veya kullanıcı adına göre ara…",
    },
    "Alt bölmə yoxdur": {
        "en": "No sub-units",
        "ru": "Нет подразделений",
        "tr": "Alt birim yok",
    },
    "Arxivlə": {
        "en": "Archive",
        "ru": "Архивировать",
        "tr": "Arşivle",
    },
    "Bu qrupda təyinat yoxdur.": {
        "en": "There are no assignments in this group.",
        "ru": "В этой группе нет назначений.",
        "tr": "Bu grupta atama yok.",
    },
    "Bölmə": {
        "en": "Unit",
        "ru": "Подразделение",
        "tr": "Birim",
    },
    "Bütün bölmə": {
        "en": "Entire unit",
        "ru": "Всё подразделение",
        "tr": "Tüm birim",
    },
    "Dekan": {
        "en": "Dean",
        "ru": "Декан",
        "tr": "Fakülte dekanı",
    },
    "Dekan müavini əlavə et": {
        "en": "Add a vice-dean",
        "ru": "Добавить заместителя декана",
        "tr": "Dekan yardımcısı ekle",
    },
    "Dekan təyin et": {
        "en": "Assign a dean",
        "ru": "Назначить декана",
        "tr": "Dekan ata",
    },
    "Dəyiş": {
        "en": "Change",
        "ru": "Изменить",
        "tr": "Değiştir",
    },
    "Fakültə": {
        "en": "Faculty",
        "ru": "Факультет",
        "tr": "Fakülte",
    },
    "Fakültə SİLİNMİR — arxivlənir. Aktiv kafedrası və ya təyinatlı üzvü olan fakültə arxivlənə bilməz.": {
        "en": "A faculty is NOT deleted — it is archived. A faculty that still has an active department or an assigned member cannot be archived.",
        "ru": "Факультет НЕ удаляется — он архивируется. Факультет с активной кафедрой или назначенным сотрудником архивировать нельзя.",
        "tr": "Fakülte SİLİNMEZ — arşivlenir. Aktif bölümü ya da atanmış üyesi olan fakülte arşivlenemez.",
    },
    "Fakültələr": {
        "en": "Faculties",
        "ru": "Факультеты",
        "tr": "Fakülteler",
    },
    "Fakültəni arxivlə": {
        "en": "Archive the faculty",
        "ru": "Архивировать факультет",
        "tr": "Fakülteyi arşivle",
    },
    "Fakültəni redaktə et": {
        "en": "Edit the faculty",
        "ru": "Изменить факультет",
        "tr": "Fakülteyi düzenle",
    },
    "Heyət": {
        "en": "Staff",
        "ru": "Персонал",
        "tr": "Kadro",
    },
    "Heyət təyin edilməyib": {
        "en": "No staff assigned",
        "ru": "Персонал не назначен",
        "tr": "Kadro atanmamış",
    },
    "Heyət yüklənir…": {
        "en": "Loading staff…",
        "ru": "Загрузка персонала…",
        "tr": "Kadro yükleniyor…",
    },
    "Heyət üzvü əlavə et": {
        "en": "Add a staff member",
        "ru": "Добавить сотрудника",
        "tr": "Kadro üyesi ekle",
    },
    "Kafedra": {
        "en": "Department",
        "ru": "Кафедра",
        "tr": "Bölüm",
    },
    "Kafedra SİLİNMİR — arxivlənir. Təyinatlı müəllimi/üzvü və ya aktiv alt bölməsi olan kafedra arxivlənə bilməz.": {
        "en": "A department is NOT deleted — it is archived. A department that still has an assigned teacher/member or an active sub-unit cannot be archived.",
        "ru": "Кафедра НЕ удаляется — она архивируется. Кафедру с назначенным преподавателем/сотрудником или активным подразделением архивировать нельзя.",
        "tr": "Bölüm SİLİNMEZ — arşivlenir. Atanmış öğretmeni/üyesi ya da aktif alt birimi olan bölüm arşivlenemez.",
    },
    "Kafedra müdiri təyin et": {
        "en": "Assign a head of department",
        "ru": "Назначить заведующего кафедрой",
        "tr": "Bölüm başkanı ata",
    },
    "Kafedranı arxivlə": {
        "en": "Archive the department",
        "ru": "Архивировать кафедру",
        "tr": "Bölümü arşivle",
    },
    "Kafedranı redaktə et": {
        "en": "Edit the department",
        "ru": "Изменить кафедру",
        "tr": "Bölümü düzenle",
    },
    "Kafedraya müəllim əlavə et": {
        "en": "Add a teacher to the department",
        "ru": "Добавить преподавателя на кафедру",
        "tr": "Bölüme öğretmen ekle",
    },
    "Kod": {
        "en": "Code",
        "ru": "Код",
        "tr": "Kısa kod",
    },
    "Koordinator": {
        "en": "Coordinator",
        "ru": "Координатор",
        "tr": "Koordinatör",
    },
    "Koordinator adətən bir ixtisasa bağlanır — onun qrupları və tələbələri onun əhatəsinə düşür.": {
        "en": "A coordinator is normally attached to one programme — its groups and students fall within their scope.",
        "ru": "Координатор обычно закрепляется за одной специальностью — её группы и студенты входят в его охват.",
        "tr": "Koordinatör genellikle tek bir programa bağlanır — o programın grupları ve öğrencileri onun kapsamına girer.",
    },
    "Mövcud müəllim üzvlüyü bu kafedraya bağlanır (başqa kafedradadırsa köçürülür); jurnal və qiymət izi qalır.": {
        "en": "The existing teacher membership is attached to this department (moved if it is on another one); the journal and grade trail is kept.",
        "ru": "Существующее членство преподавателя привязывается к этой кафедре (при необходимости переносится с другой); записи журнала и оценок сохраняются.",
        "tr": "Mevcut öğretmen üyeliği bu bölüme bağlanır (başka bölümdeyse taşınır); yoklama ve not izi korunur.",
    },
    "Müavin": {
        "en": "Deputy",
        "ru": "Заместитель",
        "tr": "Yardımcı",
    },
    "Müdir": {
        "en": "Head",
        "ru": "Заведующий",
        "tr": "Başkan",
    },
    "Müdir, müəllimlər və ixtisaslar. Təyinatı silmək təsdiq tələb edir və auditə düşür.": {
        "en": "Head, teachers and programmes. Removing an assignment requires confirmation and is recorded in the audit log.",
        "ru": "Заведующий, преподаватели и специальности. Удаление назначения требует подтверждения и попадает в журнал аудита.",
        "tr": "Başkan, öğretmenler ve programlar. Atamayı silmek onay gerektirir ve denetim günlüğüne yazılır.",
    },
    "Müəllim": {
        "en": "Teacher",
        "ru": "Преподаватель",
        "tr": "Öğretmen",
    },
    "Müəllim yoxdur": {
        "en": "No teachers",
        "ru": "Преподавателей нет",
        "tr": "Öğretmen yok",
    },
    "Məs.: İnformasiya texnologiyaları kafedrası": {
        "en": "E.g.: Department of Information Technology",
        "ru": "Напр.: кафедра информационных технологий",
        "tr": "Örn.: Bilgi Teknolojileri Bölümü",
    },
    "Məs.: İqtisadiyyat və idarəetmə fakültəsi": {
        "en": "E.g.: Faculty of Economics and Management",
        "ru": "Напр.: факультет экономики и управления",
        "tr": "Örn.: İktisat ve İşletme Fakültesi",
    },
    "Məs.: İİF": {
        "en": "E.g.: FEM",
        "ru": "Напр.: ФЭУ",
        "tr": "Örn.: İİF",
    },
    "Namizədlər idarəetmə/müəllim səviyyəli aktiv üzvlərdir; tələbə hesabı seçilə bilməz. Boş saxlayıb yadda saxlasanız cari təyinat silinir.": {
        "en": "Candidates are active members at management/teaching level; a student account cannot be selected. If you save the field empty, the current assignment is removed.",
        "ru": "Кандидаты — активные сотрудники управленческого/преподавательского уровня; учётную запись студента выбрать нельзя. Если сохранить поле пустым, текущее назначение снимается.",
        "tr": "Adaylar yönetim/öğretim düzeyindeki aktif üyelerdir; öğrenci hesabı seçilemez. Alanı boş bırakıp kaydederseniz mevcut atama silinir.",
    },
    "Profilə bax": {
        "en": "View profile",
        "ru": "Открыть профиль",
        "tr": "Profili görüntüle",
    },
    "Proqram koordinatoru əlavə et": {
        "en": "Add a programme coordinator",
        "ru": "Добавить координатора специальности",
        "tr": "Program koordinatörü ekle",
    },
    "Qeyd": {
        "en": "Note",
        "ru": "Примечание",
        "tr": "Not",
    },
    "Qısa kod — sənədlərdə və filtrdə işlənir (boş buraxıla bilər).": {
        "en": "Short code — used in documents and filters (may be left empty).",
        "ru": "Краткий код — используется в документах и фильтрах (можно оставить пустым).",
        "tr": "Kısa kod — belgelerde ve filtrelerde kullanılır (boş bırakılabilir).",
    },
    "Redaktə": {
        "en": "Edit",
        "ru": "Изменить",
        "tr": "Düzenle",
    },
    "Rəhbər": {
        "en": "Head",
        "ru": "Руководитель",
        "tr": "Yönetici",
    },
    "Rəhbər təyin edilməyib": {
        "en": "No head assigned",
        "ru": "Руководитель не назначен",
        "tr": "Yönetici atanmamış",
    },
    "Rəhbər təyinatı həmin bölməyə əhatəli «Dekan» / «Kafedra müdiri» rol üzvlüyünü də yaradır; əvvəlki rəhbərin eyni bölmədəki rolu bağlanır.": {
        "en": "Assigning a head also creates a “Dean” / “Head of department” role membership scoped to that unit; the previous head’s role in the same unit is closed.",
        "ru": "Назначение руководителя также создаёт членство в роли «Декан» / «Заведующий кафедрой» с охватом этого подразделения; роль прежнего руководителя в том же подразделении закрывается.",
        "tr": "Yönetici ataması, o birimi kapsayan «Dekan» / «Bölüm başkanı» rol üyeliğini de oluşturur; önceki yöneticinin aynı birimdeki rolü kapatılır.",
    },
    "Rəhbər, dekanlıq heyəti və kafedralar. Təyinatı silmək təsdiq tələb edir və auditə düşür.": {
        "en": "Head, dean’s office staff and departments. Removing an assignment requires confirmation and is recorded in the audit log.",
        "ru": "Руководитель, сотрудники деканата и кафедры. Удаление назначения требует подтверждения и попадает в журнал аудита.",
        "tr": "Yönetici, dekanlık kadrosu ve bölümler. Atamayı silmek onay gerektirir ve denetim günlüğüne yazılır.",
    },
    "Seçilmiş şəxs fakültənin rəhbəri olur; əməl audit jurnalına yazılır.": {
        "en": "The selected person becomes the head of the faculty; the action is written to the audit log.",
        "ru": "Выбранный человек становится руководителем факультета; действие записывается в журнал аудита.",
        "tr": "Seçilen kişi fakültenin yöneticisi olur; işlem denetim günlüğüne yazılır.",
    },
    "Seçilmiş şəxs kafedranın rəhbəri olur; əməl audit jurnalına yazılır.": {
        "en": "The selected person becomes the head of the department; the action is written to the audit log.",
        "ru": "Выбранный человек становится заведующим кафедрой; действие записывается в журнал аудита.",
        "tr": "Seçilen kişi bölümün başkanı olur; işlem denetim günlüğüne yazılır.",
    },
    "Seçin": {
        "en": "Select",
        "ru": "Выберите",
        "tr": "Seçiniz",
    },
    "Siyahı yüklənmədi — yenidən cəhd edin.": {
        "en": "The list could not be loaded — please try again.",
        "ru": "Список не загрузился — попробуйте ещё раз.",
        "tr": "Liste yüklenemedi — yeniden deneyin.",
    },
    "Siyahıda müəllimin hazırkı kafedrası görünür; başqa kafedradan seçsəniz oraya köçürülür.": {
        "en": "The list shows the teacher’s current department; if you pick another one, they are moved there.",
        "ru": "В списке отображается текущая кафедра преподавателя; при выборе другой он переводится туда.",
        "tr": "Listede öğretmenin mevcut bölümü görünür; başka bir bölüm seçerseniz oraya taşınır.",
    },
    "Struktur ağacı": {
        "en": "Structure tree",
        "ru": "Дерево структуры",
        "tr": "Yapı ağacı",
    },
    "Təyin edilməyib": {
        "en": "Not assigned",
        "ru": "Не назначено",
        "tr": "Atanmamış",
    },
    "Təyin et": {
        "en": "Assign",
        "ru": "Назначить",
        "tr": "Ata",
    },
    "Təyinatı sil": {
        "en": "Remove the assignment",
        "ru": "Удалить назначение",
        "tr": "Atamayı sil",
    },
    "Uyğun müəllim tapılmadı": {
        "en": "No matching teacher found",
        "ru": "Подходящий преподаватель не найден",
        "tr": "Eşleşen öğretmen bulunamadı",
    },
    "Uyğun namizəd tapılmadı": {
        "en": "No matching candidate found",
        "ru": "Подходящий кандидат не найден",
        "tr": "Eşleşen aday bulunamadı",
    },
    "Yalnız təşkilatın aktiv, idarəetmə/müəllim səviyyəli üzvləri; tələbə hesabına heyət rolu verilmir.": {
        "en": "Only active members of the organization at management/teaching level; a student account is not given a staff role.",
        "ru": "Только активные сотрудники организации управленческого/преподавательского уровня; учётной записи студента роль персонала не выдаётся.",
        "tr": "Yalnızca kurumun yönetim/öğretim düzeyindeki aktif üyeleri; öğrenci hesabına kadro rolü verilmez.",
    },
    "Yeni fakültə": {
        "en": "New faculty",
        "ru": "Новый факультет",
        "tr": "Yeni fakülte",
    },
    "Yeni kafedra": {
        "en": "New department",
        "ru": "Новая кафедра",
        "tr": "Yeni bölüm",
    },
    "Şəxs": {
        "en": "Person",
        "ru": "Человек",
        "tr": "Kişi",
    },
    "Şəxsə bu fakültəyə (və ya seçilmiş ixtisasa) əhatəli rol üzvlüyü yaradılır.": {
        "en": "The person is given a role membership scoped to this faculty (or to the selected programme).",
        "ru": "Человеку создаётся членство в роли с охватом этого факультета (или выбранной специальности).",
        "tr": "Kişiye bu fakülteyi (veya seçilen programı) kapsayan bir rol üyeliği oluşturulur.",
    },
    "Əhatə": {
        "en": "Scope",
        "ru": "Охват",
        "tr": "Kapsam",
    },
    "Əlavə et": {
        "en": "Add",
        "ru": "Добавить",
        "tr": "Ekle",
    },
    "Əmr nömrəsi, tarix və ya səbəb — audit jurnalına yazılır": {
        "en": "Order number, date or reason — written to the audit log",
        "ru": "Номер приказа, дата или причина — записывается в журнал аудита",
        "tr": "Emir numarası, tarih veya gerekçe — denetim günlüğüne yazılır",
    },
}

# ── Struktur ağacı (sol panel) ───────────────────────────────────────────────

_STRUCTURE_TREE = {
    "Ada klik — bölməni açır və sağda göstərir; oxa klik — yalnız aç/bağla.": {
        "en": "Clicking the name opens the unit and shows it on the right; clicking the arrow only expands/collapses it.",
        "ru": "Клик по названию открывает подразделение и показывает его справа; клик по стрелке только разворачивает/сворачивает.",
        "tr": "Ada tıklamak birimi açar ve sağda gösterir; oka tıklamak yalnızca açar/kapatır.",
    },
    "Alt bölmə": {
        "en": "Sub-unit",
        "ru": "Подразделение",
        "tr": "Alt birim",
    },
    "Alt bölmələr:": {
        "en": "Sub-units:",
        "ru": "Подразделения:",
        "tr": "Alt birimler:",
    },
    "Bağla": {
        "en": "Close",
        "ru": "Закрыть",
        "tr": "Kapat",
    },
    "Bölmə məlumatı yüklənmədi — yenidən cəhd edin.": {
        "en": "The unit details could not be loaded — please try again.",
        "ru": "Данные подразделения не загрузились — попробуйте ещё раз.",
        "tr": "Birim bilgileri yüklenemedi — yeniden deneyin.",
    },
    "Bölmə tipləri": {
        "en": "Unit types",
        "ru": "Типы подразделений",
        "tr": "Birim türleri",
    },
    "Hamısını aç": {
        "en": "Expand all",
        "ru": "Развернуть все",
        "tr": "Tümünü aç",
    },
    "Struktur yolu": {
        "en": "Structure path",
        "ru": "Путь по структуре",
        "tr": "Yapı yolu",
    },
}

# ── Təşkilat üzvləri — üzv kartı çekmecəsi ───────────────────────────────────

_ORG_MEMBERS = {
    "%(name)s — ətraflı": {
        "en": "%(name)s — details",
        "ru": "%(name)s — подробно",
        "tr": "%(name)s — ayrıntılar",
    },
    "Aktiv rol yoxdur.": {
        "en": "There are no active roles.",
        "ru": "Активных ролей нет.",
        "tr": "Aktif rol yok.",
    },
    "Açıq profil": {
        "en": "Public profile",
        "ru": "Открытый профиль",
        "tr": "Açık profil",
    },
    "Açıq profil səhifəsi": {
        "en": "Public profile page",
        "ru": "Страница открытого профиля",
        "tr": "Açık profil sayfası",
    },
    "Bölmə təyin edilməyib": {
        "en": "No unit assigned",
        "ru": "Подразделение не назначено",
        "tr": "Birim atanmamış",
    },
    "Bütün təşkilat": {
        "en": "Entire organization",
        "ru": "Вся организация",
        "tr": "Tüm kurum",
    },
    "Dayandırılıb": {
        "en": "Suspended",
        "ru": "Приостановлен",
        "tr": "Askıya alındı",
    },
    "E-poçt": {
        "en": "Email",
        "ru": "Эл. почта",
        "tr": "E-posta",
    },
    "Fakültələr": {
        "en": "Faculties",
        "ru": "Факультеты",
        "tr": "Fakülteler",
    },
    "Hesab dayandırılıb": {
        "en": "The account is suspended",
        "ru": "Учётная запись приостановлена",
        "tr": "Hesap askıya alındı",
    },
    "Kafedralar": {
        "en": "Departments",
        "ru": "Кафедры",
        "tr": "Bölümler",
    },
    "Məlumat yüklənmədi — yenidən cəhd edin.": {
        "en": "The data could not be loaded — please try again.",
        "ru": "Данные не загрузились — попробуйте ещё раз.",
        "tr": "Veriler yüklenemedi — yeniden deneyin.",
    },
    "Profil": {
        "en": "Profile",
        "ru": "Профиль",
        "tr": "Kullanıcı profili",
    },
    "Qoşulma": {
        "en": "Joined",
        "ru": "Присоединение",
        "tr": "Katılım",
    },
    "Rollar": {
        "en": "Roles",
        "ru": "Роли",
        "tr": "Roller",
    },
    "Rəhbər heyət": {
        "en": "Leadership staff",
        "ru": "Руководящий состав",
        "tr": "Yönetim kadrosu",
    },
    "Rəhbərlik etdiyi bölmə yoxdur.": {
        "en": "They do not head any unit.",
        "ru": "Возглавляемых подразделений нет.",
        "tr": "Yönettiği birim yok.",
    },
    "Rəhbərlik etdiyi bölmələr": {
        "en": "Units they head",
        "ru": "Возглавляемые подразделения",
        "tr": "Yönettiği birimler",
    },
    "Tabel nömrəsi": {
        "en": "Staff ID number",
        "ru": "Табельный номер",
        "tr": "Sicil numarası",
    },
    "Tabel №": {
        "en": "Staff ID",
        "ru": "Табельный №",
        "tr": "Sicil no",
    },
    "Təyinat": {
        "en": "Assignment",
        "ru": "Назначение",
        "tr": "Atama",
    },
    "Vəzifə": {
        "en": "Position",
        "ru": "Должность",
        "tr": "Görev",
    },
    "Üzv kartı": {
        "en": "Member card",
        "ru": "Карточка участника",
        "tr": "Üye kartı",
    },
    "Üzv kartı yüklənir…": {
        "en": "Loading the member card…",
        "ru": "Загрузка карточки участника…",
        "tr": "Üye kartı yükleniyor…",
    },
    "İstifadəçi adı": {
        "en": "Username",
        "ru": "Имя пользователя",
        "tr": "Kullanıcı adı",
    },
    "Şəxsin bu təşkilatdakı bütün rolları, rəhbərlik etdiyi bölmələr və əlaqə.": {
        "en": "All of the person’s roles in this organization, the units they head and their contact details.",
        "ru": "Все роли человека в этой организации, возглавляемые подразделения и контакты.",
        "tr": "Kişinin bu kurumdaki tüm rolleri, yönettiği birimler ve iletişim bilgileri.",
    },
    "Əsas rol": {
        "en": "Primary role",
        "ru": "Основная роль",
        "tr": "Birincil rol",
    },
    "Ətraflı": {
        "en": "Details",
        "ru": "Подробно",
        "tr": "Ayrıntılar",
    },
}

# ── «Şəxslər» kataloqu — filtr, toplu əməllər, köçürmə dialoqları ────────────

_PEOPLE_DIRECTORY = {
    "%%a / %%b əməl uğurla tamamlandı.": {
        "en": "%%a of %%b actions completed successfully.",
        "ru": "Успешно выполнено действий: %%a из %%b.",
        "tr": "%%a / %%b işlem başarıyla tamamlandı.",
    },
    "%%d nəfər": {
        "en": "%%d people",
        "ru": "%%d чел.",
        "tr": "%%d kişi",
    },
    "%%d nəfər seçilib": {
        "en": "%%d people selected",
        "ru": "Выбрано человек: %%d",
        "tr": "%%d kişi seçildi",
    },
    "Aktiv müəllim təyinatı deaktiv ediləcək (sətir silinmir, tarixçə qalır).": {
        "en": "The active teacher assignment will be deactivated (the row is not deleted, the history is kept).",
        "ru": "Активное назначение преподавателя будет деактивировано (строка не удаляется, история сохраняется).",
        "tr": "Aktif öğretmen ataması devre dışı bırakılacak (satır silinmez, geçmiş korunur).",
    },
    "Axtar…": {
        "en": "Search…",
        "ru": "Поиск…",
        "tr": "Ara…",
    },
    "Dayandır": {
        "en": "Suspend",
        "ru": "Приостановить",
        "tr": "Askıya al",
    },
    "Demoqrafiya: cins %%a/%%c, doğum tarixi %%b/%%c": {
        "en": "Demographics: gender %%a/%%c, date of birth %%b/%%c",
        "ru": "Демография: пол %%a/%%c, дата рождения %%b/%%c",
        "tr": "Demografi: cinsiyet %%a/%%c, doğum tarihi %%b/%%c",
    },
    "Hesab bərpa olunacaq və şəxs yenidən daxil ola biləcək.": {
        "en": "The account will be restored and the person will be able to sign in again.",
        "ru": "Учётная запись будет восстановлена, и человек снова сможет войти.",
        "tr": "Hesap geri yüklenecek ve kişi yeniden oturum açabilecek.",
    },
    "Hesab dayandırılacaq — şəxs sistemə daxil ola bilməyəcək. Səbəb audit jurnalına yazılır.": {
        "en": "The account will be suspended — the person will not be able to sign in. The reason is written to the audit log.",
        "ru": "Учётная запись будет приостановлена — человек не сможет войти в систему. Причина записывается в журнал аудита.",
        "tr": "Hesap askıya alınacak — kişi sisteme giriş yapamayacak. Gerekçe denetim günlüğüne yazılır.",
    },
    "Hesabı bərpa et": {
        "en": "Restore account",
        "ru": "Восстановить учётную запись",
        "tr": "Hesabı geri yükle",
    },
    "Hesabı dayandır": {
        "en": "Suspend account",
        "ru": "Приостановить учётную запись",
        "tr": "Hesabı askıya al",
    },
    "Hədəf qrup": {
        "en": "Target group",
        "ru": "Целевая группа",
        "tr": "Hedef grup",
    },
    "Hədəf qrup seçilməlidir.": {
        "en": "A target group must be selected.",
        "ru": "Необходимо выбрать целевую группу.",
        "tr": "Hedef grup seçilmelidir.",
    },
    "Kafedra adı ilə axtar…": {
        "en": "Search by department name…",
        "ru": "Поиск по названию кафедры…",
        "tr": "Bölüm adına göre ara…",
    },
    "Kafedra seçilməlidir.": {
        "en": "A department must be selected.",
        "ru": "Необходимо выбрать кафедру.",
        "tr": "Bölüm seçilmelidir.",
    },
    "Kafedraya təyin et": {
        "en": "Assign to a department",
        "ru": "Назначить на кафедру",
        "tr": "Bölüme ata",
    },
    "Kartı aç": {
        "en": "Open the card",
        "ru": "Открыть карточку",
        "tr": "Kartı görüntüle",
    },
    "Köçür": {
        "en": "Transfer",
        "ru": "Перевести",
        "tr": "Taşı",
    },
    "Ləğv et": {
        "en": "Cancel",
        "ru": "Отмена",
        "tr": "İptal et",
    },
    "Müəllim statusunu çıxar": {
        "en": "Revoke teacher status",
        "ru": "Снять статус преподавателя",
        "tr": "Öğretmen statüsünü kaldır",
    },
    "Müəllimin aktiv təyinatı seçilmiş kafedraya köçürülür — üzvlük silinmir, tarixçə qalır. Dəyişiklik audit jurnalına yazılır.": {
        "en": "The teacher’s active assignment is moved to the selected department — the membership is not deleted and the history is kept. The change is written to the audit log.",
        "ru": "Активное назначение преподавателя переносится на выбранную кафедру — членство не удаляется, история сохраняется. Изменение записывается в журнал аудита.",
        "tr": "Öğretmenin aktif ataması seçilen bölüme taşınır — üyelik silinmez, geçmiş korunur. Değişiklik denetim günlüğüne yazılır.",
    },
    "Məs.: dekanlığın 12/T saylı əmri ilə qrup dəyişikliyi": {
        "en": "E.g.: group change by dean’s office order no. 12/T",
        "ru": "Напр.: смена группы по приказу деканата № 12/Т",
        "tr": "Örn.: dekanlığın 12/T sayılı emriyle grup değişikliği",
    },
    "Opsional — auditə yazılır": {
        "en": "Optional — written to the audit log",
        "ru": "Необязательно — записывается в журнал аудита",
        "tr": "İsteğe bağlı — denetim günlüğüne yazılır",
    },
    "Qeyd": {
        "en": "Note",
        "ru": "Примечание",
        "tr": "Not",
    },
    "Qrup adı ilə axtar…": {
        "en": "Search by group name…",
        "ru": "Поиск по названию группы…",
        "tr": "Grup adına göre ara…",
    },
    "Qrupa köçür": {
        "en": "Transfer to a group",
        "ru": "Перевести в группу",
        "tr": "Gruba taşı",
    },
    "Qrupsuz": {
        "en": "Without a group",
        "ru": "Без группы",
        "tr": "Grupsuz",
    },
    "Qrupu dəyiş": {
        "en": "Change group",
        "ru": "Изменить группу",
        "tr": "Grubu değiştir",
    },
    "Qəbul": {
        "en": "Accepted",
        "ru": "Принято",
        "tr": "Kabul",
    },
    "Rəsmi köçürmə: köhnə qrupdakı jurnal qeydiyyatı tarixçəyə keçir, silinmir. Səbəb məcburidir və audit jurnalında görünür. Ətraflı ön baxış üçün sətirdəki «İdarə et»i açın.": {
        "en": "Official transfer: the journal enrollment in the old group moves to history, it is not deleted. A reason is mandatory and appears in the audit log. Open “Manage” on the row for a detailed preview.",
        "ru": "Официальный перевод: регистрация в журнале прежней группы уходит в историю, а не удаляется. Причина обязательна и отображается в журнале аудита. Для подробного предпросмотра откройте «Управление» в строке.",
        "tr": "Resmî nakil: eski gruptaki yoklama kaydı geçmişe aktarılır, silinmez. Gerekçe zorunludur ve denetim günlüğünde görünür. Ayrıntılı ön izleme için satırdaki «Yönet» bağlantısını açın.",
    },
    "Seçilmiş sətirlərdə akademik qeyd yoxdur.": {
        "en": "The selected rows contain no academic records.",
        "ru": "В выбранных строках нет академических записей.",
        "tr": "Seçilen satırlarda akademik kayıt yok.",
    },
    "Seçimi təmizlə": {
        "en": "Clear selection",
        "ru": "Очистить выбор",
        "tr": "Seçimi temizle",
    },
    "Seçin": {
        "en": "Select",
        "ru": "Выберите",
        "tr": "Seçiniz",
    },
    "Səbəb": {
        "en": "Reason",
        "ru": "Причина",
        "tr": "Gerekçe",
    },
    "Səbəb ən azı %%d simvol olmalıdır.": {
        "en": "The reason must be at least %%d characters long.",
        "ru": "Причина должна содержать не менее %%d символов.",
        "tr": "Gerekçe en az %%d karakter olmalıdır.",
    },
    "Səhifə %%a / %%b": {
        "en": "Page %%a of %%b",
        "ru": "Страница %%a из %%b",
        "tr": "Sayfa %%a / %%b",
    },
    "Səhifədəki hamısını seç": {
        "en": "Select all on this page",
        "ru": "Выбрать все на странице",
        "tr": "Sayfadaki tümünü seç",
    },
    "Sətri seç": {
        "en": "Select the row",
        "ru": "Выбрать строку",
        "tr": "Satırı seç",
    },
    "Toplu əməllər": {
        "en": "Bulk actions",
        "ru": "Массовые действия",
        "tr": "Toplu işlemler",
    },
    "Təhsil forması": {
        "en": "Mode of study",
        "ru": "Форма обучения",
        "tr": "Öğretim şekli",
    },
    "Təyin et": {
        "en": "Assign",
        "ru": "Назначить",
        "tr": "Ata",
    },
    "Uyğun kafedra tapılmadı": {
        "en": "No matching department found",
        "ru": "Подходящая кафедра не найдена",
        "tr": "Eşleşen bölüm bulunamadı",
    },
    "Uyğun nəticə yoxdur": {
        "en": "No matching results",
        "ru": "Совпадений нет",
        "tr": "Eşleşen sonuç yok",
    },
    "Uyğun qrup tapılmadı": {
        "en": "No matching group found",
        "ru": "Подходящая группа не найдена",
        "tr": "Eşleşen grup bulunamadı",
    },
    "Yeni hesab": {
        "en": "New account",
        "ru": "Новая учётная запись",
        "tr": "Yeni hesap",
    },
    "Yeni müəllim": {
        "en": "New teacher",
        "ru": "Новый преподаватель",
        "tr": "Yeni öğretmen",
    },
    "Yeni tələbə": {
        "en": "New student",
        "ru": "Новый студент",
        "tr": "Yeni öğrenci",
    },
    "yaş": {
        "en": "y.o.",
        "ru": "лет",
        "tr": "yaşında",
    },
    "Ödəniş forması": {
        "en": "Payment type",
        "ru": "Форма оплаты",
        "tr": "Ödeme şekli",
    },
    "Əlavə filtrlər": {
        "en": "More filters",
        "ru": "Дополнительные фильтры",
        "tr": "Ek filtreler",
    },
    "Əməliyyat alınmadı.": {
        "en": "The operation failed.",
        "ru": "Операция не выполнена.",
        "tr": "İşlem gerçekleştirilemedi.",
    },
}

# ── Şəxsin səhifəsi — yan panel, akademik qeydlər, tədris ────────────────────

_PEOPLE_PAGE = {
    "%(n)s fənn": {
        "en": "%(n)s subjects",
        "ru": "%(n)s предметов",
        "tr": "%(n)s ders",
    },
    "Akademik qeydlər": {
        "en": "Academic records",
        "ru": "Академические записи",
        "tr": "Akademik kayıtlar",
    },
    "Akademik qeydlərə baxış səlahiyyətiniz yoxdur.": {
        "en": "You do not have permission to view academic records.",
        "ru": "У вас нет прав на просмотр академических записей.",
        "tr": "Akademik kayıtları görüntüleme yetkiniz yok.",
    },
    "Aktiv": {
        "en": "Active",
        "ru": "Активен",
        "tr": "Aktif",
    },
    "Aktiv üzvlük yoxdur": {
        "en": "No active membership",
        "ru": "Нет активного членства",
        "tr": "Aktif üyelik yok",
    },
    "Açılış tapılmadı.": {
        "en": "Offering not found.",
        "ru": "Поток не найден.",
        "tr": "Ders açılışı bulunamadı.",
    },
    "Açıq profil": {
        "en": "Public profile",
        "ru": "Открытый профиль",
        "tr": "Açık profil",
    },
    "Bu təşkilatda akademik qeyd yoxdur.": {
        "en": "There are no academic records in this organization.",
        "ru": "В этой организации нет академических записей.",
        "tr": "Bu kurumda akademik kayıt yok.",
    },
    "Davam edir": {
        "en": "In progress",
        "ru": "В процессе",
        "tr": "Devam ediyor",
    },
    "Dayandırılıb": {
        "en": "Suspended",
        "ru": "Приостановлен",
        "tr": "Askıya alındı",
    },
    "Doğum tarixi": {
        "en": "Date of birth",
        "ru": "Дата рождения",
        "tr": "Doğum tarihi",
    },
    "Dövr": {
        "en": "Period",
        "ru": "Период",
        "tr": "Dönem",
    },
    "E-poçt": {
        "en": "Email",
        "ru": "Эл. почта",
        "tr": "E-posta",
    },
    "Fakültə / kafedra": {
        "en": "Faculty / department",
        "ru": "Факультет / кафедра",
        "tr": "Fakülte / bölüm",
    },
    "Forma": {
        "en": "Study form",
        "ru": "Форма",
        "tr": "Öğrenim biçimi",
    },
    "FİN": {
        "en": "PIN",
        "ru": "ПИН",
        "tr": "Kimlik no",
    },
    "Fənn": {
        "en": "Subject",
        "ru": "Предмет",
        "tr": "Ders",
    },
    "Hələ fənn qeydiyyatı yoxdur.": {
        "en": "There are no subject enrollments yet.",
        "ru": "Регистраций на предметы пока нет.",
        "tr": "Henüz ders kaydı yok.",
    },
    "Hərf": {
        "en": "Letter",
        "ru": "Буква",
        "tr": "Harf",
    },
    "Kataloqa qayıt": {
        "en": "Back to the catalog",
        "ru": "Вернуться к каталогу",
        "tr": "Kataloğa dön",
    },
    "Keçib": {
        "en": "Passed",
        "ru": "Сдано",
        "tr": "Geçti",
    },
    "Kredit": {
        "en": "Credit",
        "ru": "Кредит",
        "tr": "Kredi",
    },
    "Kurs": {
        "en": "Year of study",
        "ru": "Курс",
        "tr": "Sınıf",
    },
    "Kəsilib": {
        "en": "Failed",
        "ru": "Не сдано",
        "tr": "Kaldı",
    },
    "Kəsilmiş fənn yoxdur.": {
        "en": "There are no failed subjects.",
        "ru": "Несданных предметов нет.",
        "tr": "Kalınan ders yok.",
    },
    "Kəsrlər": {
        "en": "Failures",
        "ru": "Незачёты",
        "tr": "Kalınan dersler",
    },
    "Maliyyə": {
        "en": "Funding",
        "ru": "Финансирование",
        "tr": "Finansman",
    },
    "Müəllim": {
        "en": "Teacher",
        "ru": "Преподаватель",
        "tr": "Öğretmen",
    },
    "Müəllimlər": {
        "en": "Teachers",
        "ru": "Преподаватели",
        "tr": "Öğretmenler",
    },
    "Naviqasiya": {
        "en": "Navigation",
        "ru": "Навигация",
        "tr": "Gezinme",
    },
    "Nəticə": {
        "en": "Result",
        "ru": "Результат",
        "tr": "Sonuç",
    },
    "Qeydiyyat": {
        "en": "Enrollments",
        "ru": "Регистрация",
        "tr": "Kayıt",
    },
    "Qrup": {
        "en": "Group",
        "ru": "Группа",
        "tr": "Grup",
    },
    "Qəbul": {
        "en": "Accepted",
        "ru": "Принято",
        "tr": "Kabul",
    },
    "Rəhbərlik etdiyi bölmələr": {
        "en": "Units they head",
        "ru": "Возглавляемые подразделения",
        "tr": "Yönettiği birimler",
    },
    "Saat": {
        "en": "Hours",
        "ru": "Часы",
        "tr": "Ders saati",
    },
    "Son giriş": {
        "en": "Last sign-in",
        "ru": "Последний вход",
        "tr": "Son oturum açma",
    },
    "Status": {
        "en": "Record status",
        "ru": "Статус",
        "tr": "Durum",
    },
    "Tabel №": {
        "en": "Staff ID",
        "ru": "Табельный №",
        "tr": "Sicil no",
    },
    "Telefon": {
        "en": "Phone",
        "ru": "Телефон",
        "tr": "Telefon numarası",
    },
    "Transkript": {
        "en": "Transcript",
        "ru": "Транскрипт",
        "tr": "Not durum belgesi",
    },
    "Tədris": {
        "en": "Teaching",
        "ru": "Преподавание",
        "tr": "Öğretim",
    },
    "Tədris siyahısına baxış üçün struktur əhatəniz yoxdur.": {
        "en": "You have no structural scope for viewing the teaching list.",
        "ru": "У вас нет структурного охвата для просмотра списка преподавания.",
        "tr": "Öğretim listesini görüntülemek için yapısal kapsamınız yok.",
    },
    "Tələbə": {
        "en": "Student",
        "ru": "Студент",
        "tr": "Öğrenci",
    },
    "Tələbələr": {
        "en": "Students",
        "ru": "Студенты",
        "tr": "Öğrenciler",
    },
    "Yekun bal": {
        "en": "Final score",
        "ru": "Итоговый балл",
        "tr": "Nihai puan",
    },
    "açılış": {
        "en": "offerings",
        "ru": "потоков",
        "tr": "ders açılışı",
    },
    "cari": {
        "en": "current",
        "ru": "текущий",
        "tr": "güncel",
    },
    "fənn": {
        "en": "subjects",
        "ru": "предметов",
        "tr": "ders",
    },
    "idmançı": {
        "en": "athlete",
        "ru": "спортсмен",
        "tr": "sporcu",
    },
    "il": {
        "en": "years",
        "ru": "лет",
        "tr": "yıl",
    },
    "kredit": {
        "en": "credits",
        "ru": "кредитов",
        "tr": "kredi",
    },
    "köçürülüb": {
        "en": "transferred",
        "ru": "перенесено",
        "tr": "aktarıldı",
    },
    "qrup": {
        "en": "group",
        "ru": "группа",
        "tr": "grup",
    },
    "saat": {
        "en": "hours",
        "ru": "часов",
        "tr": "ders saati",
    },
    "yaş": {
        "en": "y.o.",
        "ru": "лет",
        "tr": "yaşında",
    },
    "ÜOMG": {
        "en": "GPA",
        "ru": "Ср. балл",
        "tr": "GNO",
    },
    "Üzvlüklər və vəzifə": {
        "en": "Memberships and position",
        "ru": "Членства и должность",
        "tr": "Üyelikler ve görev",
    },
    "İlk üzvlük": {
        "en": "First membership",
        "ru": "Первое членство",
        "tr": "İlk üyelik",
    },
    "İstifadəçi adı": {
        "en": "Username",
        "ru": "Имя пользователя",
        "tr": "Kullanıcı adı",
    },
    "İxtisas": {
        "en": "Programme",
        "ru": "Специальность",
        "tr": "Program",
    },
    "Əlaqə və hesab": {
        "en": "Contact and account",
        "ru": "Контакты и учётная запись",
        "tr": "İletişim ve hesap",
    },
    "əsas": {
        "en": "primary",
        "ru": "основная",
        "tr": "birincil",
    },
}

# ── Şəxsin detal çekmecəsi (kataloqdan açılan) ───────────────────────────────

_PEOPLE_DETAIL = {
    "Akademik xülasə": {
        "en": "Academic summary",
        "ru": "Академическая сводка",
        "tr": "Akademik özet",
    },
    "Fakültə / kafedra": {
        "en": "Faculty / department",
        "ru": "Факультет / кафедра",
        "tr": "Fakülte / bölüm",
    },
    "Fənn / qrup / açılış": {
        "en": "Subject / group / offering",
        "ru": "Предмет / группа / поток",
        "tr": "Ders / grup / ders açılışı",
    },
    "Kafedraya təyin et": {
        "en": "Assign to a department",
        "ru": "Назначить на кафедру",
        "tr": "Bölüme ata",
    },
    "Kredit (qazanılıb / qəti)": {
        "en": "Credits (earned / final)",
        "ru": "Кредиты (набрано / итого)",
        "tr": "Kredi (kazanılan / kesin)",
    },
    "Kəsr": {
        "en": "Failures",
        "ru": "Незачёты",
        "tr": "Kalma",
    },
    "Rəhbərlik": {
        "en": "Leadership",
        "ru": "Руководство",
        "tr": "Yönetim",
    },
    "Saat (cari il)": {
        "en": "Hours (current year)",
        "ru": "Часы (текущий год)",
        "tr": "Saat (bu yıl)",
    },
    "Tədris xülasəsi": {
        "en": "Teaching summary",
        "ru": "Сводка по преподаванию",
        "tr": "Öğretim özeti",
    },
    "Təhsil forması": {
        "en": "Mode of study",
        "ru": "Форма обучения",
        "tr": "Öğretim şekli",
    },
    "Vəzifə": {
        "en": "Position",
        "ru": "Должность",
        "tr": "Görev",
    },
    "il": {
        "en": "years",
        "ru": "лет",
        "tr": "yıl",
    },
    "ÜOMG": {
        "en": "GPA",
        "ru": "Ср. балл",
        "tr": "GNO",
    },
    "İxtisas": {
        "en": "Programme",
        "ru": "Специальность",
        "tr": "Program",
    },
    "İş stajı": {
        "en": "Length of service",
        "ru": "Стаж работы",
        "tr": "Hizmet süresi",
    },
    "Ətraflı səhifə": {
        "en": "Full page",
        "ru": "Подробная страница",
        "tr": "Ayrıntılı sayfa",
    },
}

# ── Qrup çekmecəsi — tələbə əlavəsi və qrup dəyişikliyi ──────────────────────

_GROUPS = {
    "%%d tələbə seçilib": {
        "en": "%%d students selected",
        "ru": "Выбрано студентов: %%d",
        "tr": "%%d öğrenci seçildi",
    },
    "%%s seçimdən çıxar": {
        "en": "Remove %%s from the selection",
        "ru": "Убрать %%s из выбора",
        "tr": "%%s öğesini seçimden çıkar",
    },
    "%(name)s qrupuna tələbə əlavə et": {
        "en": "Add a student to group %(name)s",
        "ru": "Добавить студента в группу %(name)s",
        "tr": "%(name)s grubuna öğrenci ekle",
    },
    "Ad unikal olmalıdır — eyni adda ikinci qrup yaradılmır.": {
        "en": "The name must be unique — a second group with the same name is not created.",
        "ru": "Название должно быть уникальным — вторая группа с тем же названием не создаётся.",
        "tr": "Ad benzersiz olmalıdır — aynı adla ikinci bir grup oluşturulmaz.",
    },
    "Ad, istifadəçi adı və ya ixtisas kodu ilə axtar…": {
        "en": "Search by name, username or programme code…",
        "ru": "Поиск по имени, логину или коду специальности…",
        "tr": "Ad, kullanıcı adı veya program koduna göre ara…",
    },
    "Forma": {
        "en": "Study form",
        "ru": "Форма",
        "tr": "Öğrenim biçimi",
    },
    "Hələ tələbə seçilməyib": {
        "en": "No student selected yet",
        "ru": "Студент ещё не выбран",
        "tr": "Henüz öğrenci seçilmedi",
    },
    "Kod da unikaldır (boş buraxıla bilər).": {
        "en": "The code is unique as well (it may be left empty).",
        "ru": "Код также уникален (можно оставить пустым).",
        "tr": "Kod da benzersizdir (boş bırakılabilir).",
    },
    "Məs.: 582A1": {
        "en": "E.g.: 582A1",
        "ru": "Напр.: 582A1",
        "tr": "Örn.: 582A1",
    },
    "Məs.: tələbənin ərizəsi ilə qrup dəyişikliyi": {
        "en": "E.g.: group change at the student’s request",
        "ru": "Напр.: смена группы по заявлению студента",
        "tr": "Örn.: öğrencinin dilekçesiyle grup değişikliği",
    },
    "Profilə bax": {
        "en": "View profile",
        "ru": "Открыть профиль",
        "tr": "Profili görüntüle",
    },
    "Qrupa əlavə et": {
        "en": "Add to the group",
        "ru": "Добавить в группу",
        "tr": "Gruba ekle",
    },
    "Qrupu dəyiş": {
        "en": "Change group",
        "ru": "Изменить группу",
        "tr": "Grubu değiştir",
    },
    "Səbəb": {
        "en": "Reason",
        "ru": "Причина",
        "tr": "Gerekçe",
    },
    "Təhsil forması": {
        "en": "Mode of study",
        "ru": "Форма обучения",
        "tr": "Öğretim şekli",
    },
    "Tələbə seçilmiş qrupa köçürülür; köhnə qrupdakı jurnal qeydiyyatı tarixçəyə keçir, silinmir. Səbəb audit jurnalına yazılır.": {
        "en": "The student is moved to the selected group; the journal enrollment in the old group moves to history, it is not deleted. The reason is written to the audit log.",
        "ru": "Студент переводится в выбранную группу; регистрация в журнале прежней группы уходит в историю, а не удаляется. Причина записывается в журнал аудита.",
        "tr": "Öğrenci seçilen gruba taşınır; eski gruptaki yoklama kaydı geçmişe aktarılır, silinmez. Gerekçe denetim günlüğüne yazılır.",
    },
    "Tələbə əlavə et": {
        "en": "Add student",
        "ru": "Добавить студента",
        "tr": "Öğrenci ekle",
    },
    "Tələbəni qrupa əlavə et": {
        "en": "Add the student to the group",
        "ru": "Добавить студента в группу",
        "tr": "Öğrenciyi gruba ekle",
    },
    "Tələbənin qrupunu dəyiş": {
        "en": "Change the student’s group",
        "ru": "Изменить группу студента",
        "tr": "Öğrencinin grubunu değiştir",
    },
    "Uyğun qrupsuz tələbə tapılmadı": {
        "en": "No matching student without a group was found",
        "ru": "Подходящий студент без группы не найден",
        "tr": "Grubu olmayan eşleşen öğrenci bulunamadı",
    },
    "Yalnız hazırda qrupu olmayan (qeydiyyatlı) tələbələr göstərilir. Başqa qrupdakı tələbəni köçürmək üçün həmin qrupun çekmecəsində tələbənin yanındakı «Qrupu dəyiş» əməlini işlədin.": {
        "en": "Only (enrolled) students who currently have no group are shown. To move a student from another group, use the “Change group” action next to the student in that group’s drawer.",
        "ru": "Показаны только (зачисленные) студенты, у которых сейчас нет группы. Чтобы перевести студента из другой группы, используйте действие «Изменить группу» рядом со студентом в панели той группы.",
        "tr": "Yalnızca şu anda grubu olmayan (kayıtlı) öğrenciler gösterilir. Başka bir gruptaki öğrenciyi taşımak için o grubun çekmecesinde öğrencinin yanındaki «Grubu değiştir» işlemini kullanın.",
    },
    "Yalnız hazırda qrupu olmayan qeydiyyatlı tələbələr seçilir. Əlavə rəsmi köçürmə kimi yazılır — tarixçə silinmir.": {
        "en": "Only enrolled students who currently have no group can be selected. The addition is recorded as an official transfer — the history is not deleted.",
        "ru": "Выбрать можно только зачисленных студентов, у которых сейчас нет группы. Добавление фиксируется как официальный перевод — история не удаляется.",
        "tr": "Yalnızca şu anda grubu olmayan kayıtlı öğrenciler seçilebilir. Ekleme resmî nakil olarak kaydedilir — geçmiş silinmez.",
    },
}

# ── Audit jurnalı — siyahı, hadisə detalı, əvvəl → sonra fərqi ───────────────

_AUDIT_SECTION = {
    "%%d dəq əvvəl": {
        "en": "%%d min ago",
        "ru": "%%d мин назад",
        "tr": "%%d dk önce",
    },
    "%%d dəyişməyən sahəni göstər": {
        "en": "Show %%d unchanged fields",
        "ru": "Показать %%d неизменённых полей",
        "tr": "Değişmeyen %%d alanı göster",
    },
    "%%d gün əvvəl": {
        "en": "%%d days ago",
        "ru": "%%d дн. назад",
        "tr": "%%d gün önce",
    },
    "%%d saat əvvəl": {
        "en": "%%d hours ago",
        "ru": "%%d ч назад",
        "tr": "%%d saat önce",
    },
    "%%d sahə dəyişib": {
        "en": "%%d fields changed",
        "ru": "изменено полей: %%d",
        "tr": "%%d alan değişti",
    },
    "%(action)s — qeydi aç": {
        "en": "%(action)s — open the record",
        "ru": "%(action)s — открыть запись",
        "tr": "%(action)s — kaydı aç",
    },
    "Anonim / sistem": {
        "en": "Anonymous / system",
        "ru": "Аноним / система",
        "tr": "Anonim / sistem hesabı",
    },
    "Audit jurnalı": {
        "en": "Audit log",
        "ru": "Журнал аудита",
        "tr": "Denetim günlüğü",
    },
    "Brauzer / cihaz": {
        "en": "Browser / device",
        "ru": "Браузер / устройство",
        "tr": "Tarayıcı / cihaz",
    },
    "Bu icraçının hadisələri": {
        "en": "Events by this actor",
        "ru": "События этого исполнителя",
        "tr": "Bu işlemi yapanın olayları",
    },
    "Bu qeyddə dəyər dəyişikliyi yoxdur.": {
        "en": "This record contains no value changes.",
        "ru": "В этой записи нет изменений значений.",
        "tr": "Bu kayıtta değer değişikliği yok.",
    },
    "Bu qeyddə əvvəl → sonra fərqi var": {
        "en": "This record has a before → after diff",
        "ru": "В этой записи есть различие «было → стало»",
        "tr": "Bu kayıtta önce → sonra farkı var",
    },
    "Bu əməliyyat növü üçün səbəb tələb olunur.": {
        "en": "A reason is required for this type of operation.",
        "ru": "Для этого типа операции требуется причина.",
        "tr": "Bu işlem türü için gerekçe zorunludur.",
    },
    "CSV ixrac": {
        "en": "Export CSV",
        "ru": "Экспорт CSV",
        "tr": "CSV dışa aktar",
    },
    "Cari filtrə uyğun qeydləri CSV kimi yüklə (ən çox 10 000 sətir)": {
        "en": "Download the records matching the current filter as CSV (up to 10,000 rows)",
        "ru": "Скачать записи по текущему фильтру в формате CSV (не более 10 000 строк)",
        "tr": "Geçerli filtreye uyan kayıtları CSV olarak indir (en fazla 10 000 satır)",
    },
    "Detal": {
        "en": "Details",
        "ru": "Детали",
        "tr": "Detay",
    },
    "Dəyişikliklər": {
        "en": "Changes",
        "ru": "Изменения",
        "tr": "Değişiklikler",
    },
    "Dəyişməyənləri gizlət": {
        "en": "Hide unchanged",
        "ru": "Скрыть неизменённые",
        "tr": "Değişmeyenleri gizle",
    },
    "Eyni sorğunun hadisələri": {
        "en": "Events from the same request",
        "ru": "События того же запроса",
        "tr": "Aynı isteğin olayları",
    },
    "Hadisə qeydi": {
        "en": "Event record",
        "ru": "Запись события",
        "tr": "Olay kaydı",
    },
    "IP ünvanı": {
        "en": "IP address",
        "ru": "IP-адрес",
        "tr": "IP adresi",
    },
    "Kopyala": {
        "en": "Copy",
        "ru": "Скопировать",
        "tr": "Panoya kopyala",
    },
    "Kopyalandı": {
        "en": "Copied",
        "ru": "Скопировано",
        "tr": "Panoya kopyalandı",
    },
    "Obyekt": {
        "en": "Object",
        "ru": "Объект",
        "tr": "Nesne",
    },
    "Profilə bax": {
        "en": "View profile",
        "ru": "Открыть профиль",
        "tr": "Profili görüntüle",
    },
    "Qeyd ID": {
        "en": "Record ID",
        "ru": "ID записи",
        "tr": "Kayıt kimliği",
    },
    "Qeyd yüklənmədi — yenidən cəhd edin.": {
        "en": "The record could not be loaded — please try again.",
        "ru": "Запись не загрузилась — попробуйте ещё раз.",
        "tr": "Kayıt yüklenemedi — yeniden deneyin.",
    },
    "Resurs": {
        "en": "Resource",
        "ru": "Ресурс",
        "tr": "Kaynak",
    },
    "Resurs tipi": {
        "en": "Resource type",
        "ru": "Тип ресурса",
        "tr": "Kaynak türü",
    },
    "Sahə": {
        "en": "Field",
        "ru": "Поле",
        "tr": "Alan",
    },
    "Siyahını yenidən yüklə": {
        "en": "Reload the list",
        "ru": "Перезагрузить список",
        "tr": "Listeyi yeniden yükle",
    },
    "Sonra": {
        "en": "After",
        "ru": "Стало",
        "tr": "Sonraki değer",
    },
    "Sorğu ID": {
        "en": "Request ID",
        "ru": "ID запроса",
        "tr": "İstek kimliği",
    },
    "Səbəb": {
        "en": "Reason",
        "ru": "Причина",
        "tr": "Gerekçe",
    },
    "Səbəb göstərilməyib": {
        "en": "No reason given",
        "ru": "Причина не указана",
        "tr": "Gerekçe belirtilmemiş",
    },
    "Tam metadata, səbəb və əvvəl → sonra fərqi. Qeyd dəyişdirilə və silinə bilməz.": {
        "en": "Full metadata, the reason and the before → after diff. The record cannot be modified or deleted.",
        "ru": "Полные метаданные, причина и различие «было → стало». Запись нельзя изменить или удалить.",
        "tr": "Tam üstveri, gerekçe ve önce → sonra farkı. Kayıt değiştirilemez ve silinemez.",
    },
    "Təşkilat": {
        "en": "Organization",
        "ru": "Организация",
        "tr": "Kurum",
    },
    "Vaxt": {
        "en": "Time",
        "ru": "Время",
        "tr": "Zaman",
    },
    "Vəziyyət": {
        "en": "Status",
        "ru": "Статус",
        "tr": "Durum",
    },
    "Xam JSON": {
        "en": "Raw JSON",
        "ru": "Сырой JSON",
        "tr": "Ham JSON",
    },
    "Yenilə": {
        "en": "Refresh",
        "ru": "Обновить",
        "tr": "Yenile",
    },
    "boş": {
        "en": "empty",
        "ru": "пусто",
        "tr": "boş değer",
    },
    "boş sətir": {
        "en": "empty string",
        "ru": "пустая строка",
        "tr": "boş metin",
    },
    "bəli": {
        "en": "yes",
        "ru": "да",
        "tr": "evet",
    },
    "dəyişib": {
        "en": "changed",
        "ru": "изменено",
        "tr": "değişti",
    },
    "dəyişməyib": {
        "en": "unchanged",
        "ru": "без изменений",
        "tr": "değişmedi",
    },
    "indicə": {
        "en": "just now",
        "ru": "только что",
        "tr": "az önce",
    },
    "silinib": {
        "en": "deleted",
        "ru": "удалён",
        "tr": "silindi",
    },
    "xeyr": {
        "en": "no",
        "ru": "нет",
        "tr": "hayır",
    },
    "İcraçı": {
        "en": "Actor",
        "ru": "Исполнитель",
        "tr": "İşlemi yapan",
    },
    "Əməliyyat bölgüsü": {
        "en": "Operation breakdown",
        "ru": "Распределение операций",
        "tr": "İşlem dağılımı",
    },
    "Əvvəl": {
        "en": "Before",
        "ru": "Было",
        "tr": "Önceki değer",
    },
    "əlavə": {
        "en": "added",
        "ru": "добавлено",
        "tr": "eklendi",
    },
}

# ── Bildiriş dərci — alıcı qrupları, məzmun, əlavə fayllar ───────────────────

_PUBLISH_NOTIFICATION = {
    "%%d fayl seçilib": {
        "en": "%%d files selected",
        "ru": "Выбрано файлов: %%d",
        "tr": "%%d dosya seçildi",
    },
    "%%d qrup seçilib": {
        "en": "%%d groups selected",
        "ru": "Выбрано групп: %%d",
        "tr": "%%d grup seçildi",
    },
    "%%s — seçimdən çıxar": {
        "en": "%%s — remove from the selection",
        "ru": "%%s — убрать из выбора",
        "tr": "%%s — seçimden çıkar",
    },
    "Alıcılar": {
        "en": "Recipients",
        "ru": "Получатели",
        "tr": "Alıcı grupları",
    },
    "Alıcının bildiriş qutusunda belə görünəcək": {
        "en": "This is how it will look in the recipient’s notification inbox",
        "ru": "Так это будет выглядеть в ящике уведомлений получателя",
        "tr": "Alıcının bildirim kutusunda böyle görünecek",
    },
    "Bildiriş başlığını yazın": {
        "en": "Enter the notification title",
        "ru": "Введите заголовок уведомления",
        "tr": "Bildirim başlığını yazın",
    },
    "Bu fayl tipi dəstəklənmir: %%s": {
        "en": "This file type is not supported: %%s",
        "ru": "Этот тип файла не поддерживается: %%s",
        "tr": "Bu dosya türü desteklenmiyor: %%s",
    },
    "Fayl 10 MB-dan böyükdür: %%s": {
        "en": "The file is larger than 10 MB: %%s",
        "ru": "Файл больше 10 МБ: %%s",
        "tr": "Dosya 10 MB’tan büyük: %%s",
    },
    "Fayl əlavə et": {
        "en": "Attach a file",
        "ru": "Добавить файл",
        "tr": "Dosya ekle",
    },
    "Faylları sil": {
        "en": "Remove the files",
        "ru": "Удалить файлы",
        "tr": "Dosyaları sil",
    },
    "Göndərilir…": {
        "en": "Sending…",
        "ru": "Отправка…",
        "tr": "Gönderiliyor…",
    },
    "Göndərməyə hazırdır": {
        "en": "Ready to send",
        "ru": "Готово к отправке",
        "tr": "Göndermeye hazır",
    },
    "Göndərən": {
        "en": "Sender",
        "ru": "Отправитель",
        "tr": "Gönderen",
    },
    "Keçid http:// və ya https:// ilə başlamalıdır": {
        "en": "The link must start with http:// or https://",
        "ru": "Ссылка должна начинаться с http:// или https://",
        "tr": "Bağlantı http:// veya https:// ile başlamalıdır",
    },
    "Mətn yazılmayıb": {
        "en": "No text entered",
        "ru": "Текст не введён",
        "tr": "Metin girilmedi",
    },
    "Məzmun": {
        "en": "Content",
        "ru": "Содержание",
        "tr": "İçerik",
    },
    "PDF, Word, Excel, PowerPoint, mətn, ZIP və şəkil faylları. Alıcılar faylları bildirişin detalından yükləyəcək.": {
        "en": "PDF, Word, Excel, PowerPoint, text, ZIP and image files. Recipients will download the files from the notification details.",
        "ru": "Файлы PDF, Word, Excel, PowerPoint, текстовые, ZIP и изображения. Получатели скачают файлы из подробностей уведомления.",
        "tr": "PDF, Word, Excel, PowerPoint, metin, ZIP ve görsel dosyaları. Alıcılar dosyaları bildirim ayrıntısından indirecek.",
    },
    "Qrup seçilməyib": {
        "en": "No group selected",
        "ru": "Группа не выбрана",
        "tr": "Grup seçilmedi",
    },
    "Seçdiyiniz qruplara sistem bildirişi göndərin — alıcılar onu bildiriş qutusunda görəcək.": {
        "en": "Send a system notification to the groups you select — recipients will see it in their notification inbox.",
        "ru": "Отправьте системное уведомление выбранным группам — получатели увидят его в ящике уведомлений.",
        "tr": "Seçtiğiniz gruplara sistem bildirimi gönderin — alıcılar bunu bildirim kutusunda görecek.",
    },
    "Seçimi təmizlə": {
        "en": "Clear selection",
        "ru": "Очистить выбор",
        "tr": "Seçimi temizle",
    },
    "Simvol sayı": {
        "en": "Character count",
        "ru": "Количество символов",
        "tr": "Karakter sayısı",
    },
    "Yalnız şəkil faylı seçilə bilər": {
        "en": "Only an image file can be selected",
        "ru": "Можно выбрать только файл изображения",
        "tr": "Yalnızca görsel dosyası seçilebilir",
    },
    "indi": {
        "en": "now",
        "ru": "сейчас",
        "tr": "şimdi",
    },
    "Şəkil 5 MB-dan böyükdür": {
        "en": "The image is larger than 5 MB",
        "ru": "Изображение больше 5 МБ",
        "tr": "Görsel 5 MB’tan büyük",
    },
    "Şəkil seç": {
        "en": "Choose an image",
        "ru": "Выбрать изображение",
        "tr": "Görsel seç",
    },
    "Əlavə fayllar": {
        "en": "Attachments",
        "ru": "Вложения",
        "tr": "Ekler",
    },
    "Ən azı bir alıcı qrup seçin": {
        "en": "Select at least one recipient group",
        "ru": "Выберите хотя бы одну группу-получателя",
        "tr": "En az bir alıcı grup seçin",
    },
    "Ən çox 5 fayl əlavə etmək olar": {
        "en": "At most 5 files can be attached",
        "ru": "Можно прикрепить не более 5 файлов",
        "tr": "En fazla 5 dosya eklenebilir",
    },
    "ən çox 5 fayl, hər biri 10 MB": {
        "en": "at most 5 files, 10 MB each",
        "ru": "не более 5 файлов, по 10 МБ каждый",
        "tr": "en fazla 5 dosya, her biri 10 MB",
    },
}

# ── Bildiriş qutusu ──────────────────────────────────────────────────────────

_PROFILE_NOTIFICATIONS = {
    "Əlavə fayllar": {
        "en": "Attachments",
        "ru": "Вложения",
        "tr": "Ekler",
    },
}

# ── RİM profil sahələri (elmi ad/dərəcə, ünvan) ──────────────────────────────

_RIM = {
    "Elmi ad": {
        "en": "Academic title",
        "ru": "Учёное звание",
        "tr": "Akademik unvan",
    },
    "Elmi dərəcə": {
        "en": "Academic degree",
        "ru": "Учёная степень",
        "tr": "Akademik derece",
    },
    "Maliyyələşmə": {
        "en": "Funding",
        "ru": "Финансирование",
        "tr": "Finansman",
    },
    "Məs.: baş müəllim, dosent": {
        "en": "E.g.: senior lecturer, associate professor",
        "ru": "Напр.: старший преподаватель, доцент",
        "tr": "Örn.: baş öğretim görevlisi, doçent",
    },
    "Məs.: dosent, professor": {
        "en": "E.g.: associate professor, professor",
        "ru": "Напр.: доцент, профессор",
        "tr": "Örn.: doçent, profesör",
    },
    "Məs.: fəlsəfə doktoru": {
        "en": "E.g.: Doctor of Philosophy",
        "ru": "Напр.: доктор философии",
        "tr": "Örn.: felsefe doktoru",
    },
    "Təhsil forması": {
        "en": "Mode of study",
        "ru": "Форма обучения",
        "tr": "Öğretim şekli",
    },
    "Vəzifə": {
        "en": "Position",
        "ru": "Должность",
        "tr": "Görev",
    },
    "Ünvan": {
        "en": "Address",
        "ru": "Адрес",
        "tr": "Adres",
    },
    "Şəhər, küçə, ev (istəyə bağlı)": {
        "en": "City, street, house (optional)",
        "ru": "Город, улица, дом (необязательно)",
        "tr": "Şehir, sokak, bina (isteğe bağlı)",
    },
}

# ── Profil yan menyusu ───────────────────────────────────────────────────────

_PROFILE_SIDEBAR = {
    "Fakültələr": {
        "en": "Faculties",
        "ru": "Факультеты",
        "tr": "Fakülteler",
    },
    "Kafedralar": {
        "en": "Departments",
        "ru": "Кафедры",
        "tr": "Bölümler",
    },
}

# ── Apellyasiya müraciətləri siyahısı ────────────────────────────────────────

_APPEALS = {
    "Müraciətləri status, imtahan, səbəb tipi və tarix üzrə süzün; qərar «Bax» ilə açılan paneldə verilir.": {
        "en": "Filter the appeals by status, exam, reason type and date; the decision is made in the panel opened with “View”.",
        "ru": "Фильтруйте апелляции по статусу, экзамену, типу причины и дате; решение принимается в панели, открываемой кнопкой «Смотреть».",
        "tr": "İtirazları duruma, sınava, gerekçe türüne ve tarihe göre süzün; karar «Görüntüle» ile açılan panelde verilir.",
    },
    "Nəticə: %(n)s": {
        "en": "Result: %(n)s",
        "ru": "Результат: %(n)s",
        "tr": "Sonuç: %(n)s",
    },
    "Status üzrə sürətli filtr": {
        "en": "Quick filter by status",
        "ru": "Быстрый фильтр по статусу",
        "tr": "Duruma göre hızlı filtre",
    },
}

# ── Tələbə qəbulu sehrbazı ───────────────────────────────────────────────────

_STUDENT_INTAKE = {
    "Birdəfəlik parollar YALNIZ indi görünür — nə bazada, nə də audit jurnalında saxlanılmır. CSV-ni endirib müəllimlərə çatdırın; ilk girişdə hər müəllim e-poçt təsdiqi (OTP) və yeni parol tələb olunacaq.": {
        "en": "The one-time passwords are shown ONLY now — they are stored neither in the database nor in the audit log. Download the CSV and hand it to the teachers; at first sign-in every teacher will be asked for email confirmation (OTP) and a new password.",
        "ru": "Одноразовые пароли отображаются ТОЛЬКО сейчас — они не хранятся ни в базе данных, ни в журнале аудита. Скачайте CSV и передайте преподавателям; при первом входе у каждого преподавателя будут запрошены подтверждение по эл. почте (OTP) и новый пароль.",
        "tr": "Tek kullanımlık parolalar YALNIZCA şimdi görünür — ne veritabanında ne de denetim günlüğünde saklanır. CSV’yi indirip öğretmenlere ulaştırın; ilk girişte her öğretmenden e-posta doğrulaması (OTP) ve yeni parola istenecek.",
    },
}

# ── Müəllim qəbulu sehrbazı ──────────────────────────────────────────────────

_TEACHER_INTAKE = {
    "Kafedra": {
        "en": "Department",
        "ru": "Кафедра",
        "tr": "Bölüm",
    },
}

ENTRIES = {
    "organizations.registry": _ORG_REGISTRY,
    "accounts.structure_tree": _STRUCTURE_TREE,
    "organizations.members": _ORG_MEMBERS,
    "accounts.people": _PEOPLE_DIRECTORY,
    "accounts.people.page": _PEOPLE_PAGE,
    "accounts.people.detail": _PEOPLE_DETAIL,
    "accounts.groups": _GROUPS,
    "audit.section": _AUDIT_SECTION,
    "profile.publish_notification": _PUBLISH_NOTIFICATION,
    "profile.notifications": _PROFILE_NOTIFICATIONS,
    "profile.rim": _RIM,
    "profile.sidebar": _PROFILE_SIDEBAR,
    "appeals.template": _APPEALS,
    "student_intake": _STUDENT_INTAKE,
    "teacher_intake": _TEACHER_INTAKE,
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def existing_keys(path):
    """Kataloqdakı (msgctxt, msgid) cütləri — sətir axtarışı sarılmış girişi görmür."""
    return {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}


def fill(lang):
    path = po_path(lang)
    known = existing_keys(path)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in known:
                continue
            known.add((ctx, msgid))
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
