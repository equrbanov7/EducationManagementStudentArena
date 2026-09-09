#!/usr/bin/env python3
"""EMSArena i18n — «Rol təyin et», «Rolları idarə et», «İcazələr» yenidən
dizaynının mətnləri (4 dil). İdempotent.

2026-09-09 sahib rəyi ilə üç RBAC ekranı `ems_ui` üzərində yenidən quruldu və
hər iki rol reyestri EYNİ kataloqdan (`organizations.Role`) oxumağa keçdi. Yeni
səth çoxlu yeni mətn gətirdi:

* `accounts.role_assignment` — «Rol təyin et» (KPI, filtr, cədvəl, təsdiq
  dialoqu, gözləyən müraciətlər);
* `accounts.manage_roles` + `.message` — «Rolları idarə et» (rol vermə/geri
  alma dialoqları, izah, server mesajları);
* `accounts.permission_editor` — «İcazələr» (kateqoriya başlıqları, axtarış,
  toplu əməllər, delegasiya);
* `ui.filters` — ortaq filtr panelinin canlı axtarış mətnləri (əvvəldən kodda
  vardı, kataloqda yox idi).

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir. Yer tutucular (`%(n)d`, `%(role)s`) tərcümədə də EYNİ qalmalıdır
(`scripts/check_i18n_catalogs.py` bunu yoxlayır).

İstifadə:  python scripts/i18n_fill_roles_ui_2026_09_09.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# ── «Rol təyin et» ───────────────────────────────────────────────────────────

_ROLE_ASSIGNMENT = {
    "%(person)s — veriləcək rol": {
        "en": "%(person)s — role to grant",
        "ru": "%(person)s — назначаемая роль",
        "tr": "%(person)s — verilecek rol",
    },
    "%(person)s — yeni rol": {
        "en": "%(person)s — new role",
        "ru": "%(person)s — новая роль",
        "tr": "%(person)s için yeni rol",
    },
    "Ad": {"en": "Name", "ru": "Имя", "tr": "İsim"},
    "Ad, istifadəçi adı və ya e-poçt": {
        "en": "Name, username or email",
        "ru": "Имя, логин или эл. почта",
        "tr": "Ad, kullanıcı adı veya e-posta",
    },
    "Aktiv təşkilat tapılmadı.": {
        "en": "No active organization found.",
        "ru": "Активная организация не найдена.",
        "tr": "Aktif kurum bulunamadı.",
    },
    "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama"},
    "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.": {
        "en": "Change the search or use “Reset” to return to the full list.",
        "ru": "Измените запрос или нажмите «Сбросить», чтобы вернуться ко всему списку.",
        "tr": "Aramayı değiştirin ya da “Sıfırla” ile tüm listeye dönün.",
    },
    "Aşağıdakı «Gözləyən müraciətlər» siyahısından şəxsi təşkilata əlavə edin.": {
        "en": "Add a person to the organization from the “Pending requests” list below.",
        "ru": "Добавьте человека в организацию из списка «Ожидающие заявки» ниже.",
        "tr": "Aşağıdaki “Bekleyen başvurular” listesinden kişiyi kuruma ekleyin.",
    },
    "Bu bölmə nə edir?": {
        "en": "What does this section do?",
        "ru": "Что делает этот раздел?",
        "tr": "Bu bölüm ne yapar?",
    },
    "Bu bölmə üçün minimum müəllim və ya daha yüksək səviyyə tələb olunur.": {
        "en": "This section requires at least teacher level or higher.",
        "ru": "Для этого раздела требуется уровень преподавателя или выше.",
        "tr": "Bu bölüm için en az öğretmen ya da üzeri seviye gerekir.",
    },
    "Bütün rollar": {"en": "All roles", "ru": "Все роли", "tr": "Tüm roller"},
    "Cari rol": {"en": "Current role", "ru": "Текущая роль", "tr": "Mevcut rol"},
    "Cari rollar": {"en": "Current roles", "ru": "Текущие роли", "tr": "Mevcut roller"},
    "Dəyişəcək rol": {"en": "New role", "ru": "Новая роль", "tr": "Değişecek rol"},
    "E-poçt": {"en": "Email", "ru": "Эл. почта", "tr": "E-posta"},
    "Filtrə uyğun üzv yoxdur": {
        "en": "No member matches the filter",
        "ru": "Нет участников по фильтру",
        "tr": "Filtreye uyan üye yok",
    },
    "Göndərilir…": {"en": "Submitting…", "ru": "Отправка…", "tr": "Gönderiliyor…"},
    "Gözləyən": {"en": "Pending", "ru": "Ожидают", "tr": "Bekleyen"},
    "Gözləyən müraciət yoxdur": {
        "en": "No pending requests",
        "ru": "Ожидающих заявок нет",
        "tr": "Bekleyen başvuru yok",
    },
    "Gözləyən müraciətlər": {
        "en": "Pending requests",
        "ru": "Ожидающие заявки",
        "tr": "Bekleyen başvurular",
    },
    "Heyət": {"en": "Staff", "ru": "Персонал", "tr": "Personel"},
    "Hələ üzv yoxdur": {"en": "No members yet", "ru": "Участников пока нет", "tr": "Henüz üye yok"},
    "Hər dəyişiklik təsdiq tələb edir və audit jurnalına yazılır.": {
        "en": "Every change requires confirmation and is written to the audit log.",
        "ru": "Каждое изменение требует подтверждения и записывается в журнал аудита.",
        "tr": "Her değişiklik onay ister ve denetim günlüğüne yazılır.",
    },
    "Müraciət etdiyi təşkilat": {
        "en": "Requested organization",
        "ru": "Запрошенная организация",
        "tr": "Başvurduğu kurum",
    },
    "Nəticə: %(n)d nəfər": {
        "en": "Result: %(n)d people",
        "ru": "Результат: %(n)d чел.",
        "tr": "Sonuç: %(n)d kişi",
    },
    "Rol": {"en": "Role", "ru": "Роль", "tr": "Rol filtresi"},
    "Rol dəyişikliyi audit jurnalına yazılır — məlumatları yoxlayın.": {
        "en": "The role change is written to the audit log — check the details.",
        "ru": "Смена роли записывается в журнал аудита — проверьте данные.",
        "tr": "Rol değişikliği denetim günlüğüne yazılır — bilgileri kontrol edin.",
    },
    "Rol kataloqu": {"en": "Role catalogue", "ru": "Каталог ролей", "tr": "Rol kataloğu"},
    "Rolları idarə et": {"en": "Manage roles", "ru": "Управление ролями", "tr": "Rolleri yönet"},
    "Rolu yenilə": {"en": "Update role", "ru": "Обновить роль", "tr": "Rolü güncelle"},
    "Səviyyə": {"en": "Level", "ru": "Уровень", "tr": "Seviye"},
    "Tələbə səviyyəsi": {"en": "Student level", "ru": "Уровень студента", "tr": "Öğrenci seviyesi"},
    "Təsdiqlə": {"en": "Confirm", "ru": "Подтвердить", "tr": "Onayla"},
    "Təşkilat": {"en": "Organization", "ru": "Организация", "tr": "Kurum"},
    (
        "Təşkilat daxili rol (səviyyəli rol) — şəxsin əsas rolunu dəyişin və ya yeni şəxsi təşkilata "
        "əlavə edin. Əlavə rollar «Rolları idarə et» bölməsindədir."
    ): {
        "en": (
            "The in-organization (levelled) role — change a person's primary role or add a new person to "
            "the organization. Additional roles live in “Manage roles”."
        ),
        "ru": (
            "Роль внутри организации (с уровнем) — измените основную роль человека или добавьте нового "
            "человека в организацию. Дополнительные роли — в разделе «Управление ролями»."
        ),
        "tr": (
            "Kurum içi (seviyeli) rol — kişinin birincil rolünü değiştirin ya da kuruma yeni kişi ekleyin. "
            "Ek roller “Rolleri yönet” bölümündedir."
        ),
    },
    "Təşkilata qoşulmaq istəyən, hələ üzvlüyü olmayan şəxslər. Rol seçib «Təşkilata əlavə et» ilə qəbul edin.": {
        "en": (
            "People who want to join the organization but have no membership yet. Pick a role and accept "
            "with “Add to organization”."
        ),
        "ru": (
            "Люди, желающие вступить в организацию, но ещё не имеющие членства. Выберите роль и примите "
            "кнопкой «Добавить в организацию»."
        ),
        "tr": ("Kuruma katılmak isteyen, henüz üyeliği olmayan kişiler. Rol seçip “Kuruma ekle” ile kabul edin."),
    },
    "Təşkilata qoşulmaq üçün müraciət edən şəxs olmadıqda bu siyahı boş qalır.": {
        "en": "This list stays empty when nobody has requested to join the organization.",
        "ru": "Этот список остаётся пустым, если никто не подавал заявку на вступление.",
        "tr": "Kuruma katılmak için başvuran kimse yoksa bu liste boş kalır.",
    },
    "Təşkilata əlavə et": {
        "en": "Add to organization",
        "ru": "Добавить в организацию",
        "tr": "Kuruma ekle",
    },
    "Veriləcək rol": {"en": "Role to grant", "ru": "Назначаемая роль", "tr": "Verilecek rol"},
    "Yalnız öz səviyyənizdən aşağı şəxs və rollar görünür.": {
        "en": "Only people and roles below your own level are visible.",
        "ru": "Видны только люди и роли ниже вашего уровня.",
        "tr": "Yalnızca kendi seviyenizin altındaki kişiler ve roller görünür.",
    },
    "müəllim və yuxarı": {
        "en": "teacher and above",
        "ru": "преподаватель и выше",
        "tr": "öğretmen ve üzeri",
    },
    "təşkilata qoşulmaq istəyir": {
        "en": "wants to join the organization",
        "ru": "хочет вступить в организацию",
        "tr": "kuruma katılmak istiyor",
    },
    "«Rol təyin et» şəxsin ƏSAS təşkilat rolunu dəyişir və yeni şəxsi təşkilata əlavə edir.": {
        "en": "“Assign role” changes a person's PRIMARY organization role and adds new people to the organization.",
        "ru": "«Назначить роль» меняет ОСНОВНУЮ роль человека в организации и добавляет новых людей.",
        "tr": "“Rol ata” kişinin BİRİNCİL kurum rolünü değiştirir ve kuruma yeni kişi ekler.",
    },
    "Üzvlük yoxdur": {"en": "No membership", "ru": "Членства нет", "tr": "Üyelik yok"},
    "İdarə edilə bilən üzv": {
        "en": "Manageable members",
        "ru": "Управляемые участники",
        "tr": "Yönetilebilir üye",
    },
    "İstifadəçi adı": {"en": "Username", "ru": "Логин", "tr": "Kullanıcı adı"},
    "İstifadəçini təşkilata əlavə etməyi təsdiqləyin.": {
        "en": "Confirm adding the user to the organization.",
        "ru": "Подтвердите добавление пользователя в организацию.",
        "tr": "Kullanıcıyı kuruma eklemeyi onaylayın.",
    },
    "İstifadəçinin rolunu yeniləməyi təsdiqləyin.": {
        "en": "Confirm updating the user's role.",
        "ru": "Подтвердите обновление роли пользователя.",
        "tr": "Kullanıcının rolünü güncellemeyi onaylayın.",
    },
    "Şəxs": {"en": "Person", "ru": "Человек", "tr": "Kişi"},
    (
        "Əlavə rollar («həm koordinator, həm müəllim») «Rolları idarə et» bölməsindən verilir — hər iki "
        "siyahı eyni rol kataloqundan gəlir."
    ): {
        "en": (
            "Additional roles (“coordinator and teacher at once”) are granted in “Manage roles” — both lists "
            "come from the same role catalogue."
        ),
        "ru": (
            "Дополнительные роли («и координатор, и преподаватель») выдаются в разделе «Управление ролями» — "
            "оба списка берутся из одного каталога ролей."
        ),
        "tr": (
            "Ek roller (“hem koordinatör hem öğretmen”) “Rolleri yönet” bölümünden verilir — iki liste de aynı "
            "rol kataloğundan gelir."
        ),
    },
    "Əməliyyat tamamlanmadı. Yenidən cəhd edin.": {
        "en": "The operation did not complete. Please try again.",
        "ru": "Операция не завершена. Попробуйте ещё раз.",
        "tr": "İşlem tamamlanmadı. Yeniden deneyin.",
    },
    "Əməliyyatı təsdiqlə": {
        "en": "Confirm the operation",
        "ru": "Подтвердите операцию",
        "tr": "İşlemi onayla",
    },
}

# ── «Rolları idarə et» ───────────────────────────────────────────────────────

_MANAGE_ROLES = {
    "%(person)s — «%(role)s» rolunu geri al": {
        "en": "%(person)s — revoke the “%(role)s” role",
        "ru": "%(person)s — отозвать роль «%(role)s»",
        "tr": "%(person)s — “%(role)s” rolünü geri al",
    },
    "(istəyə bağlı)": {"en": "(optional)", "ru": "(необязательно)", "tr": "(isteğe bağlı)"},
    "Ad, istifadəçi adı və ya e-poçt": _ROLE_ASSIGNMENT["Ad, istifadəçi adı və ya e-poçt"],
    "Axtarış": _ROLE_ASSIGNMENT["Axtarış"],
    "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.": _ROLE_ASSIGNMENT[
        "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın."
    ],
    (
        "Bir şəxsin bütün təşkilat rolları — məsələn həm «Proqram koordinatoru», həm «Müəllim». "
        "Rol vermək və geri almaq buradan aparılır; hər əməl audit jurnalına yazılır."
    ): {
        "en": (
            "All organization roles of one person — for example both “Program coordinator” and “Teacher”. "
            "Granting and revoking roles happens here; every action is written to the audit log."
        ),
        "ru": (
            "Все роли человека в организации — например, «Координатор программы» и «Преподаватель» "
            "одновременно. Выдача и отзыв ролей выполняются здесь; каждое действие пишется в журнал аудита."
        ),
        "tr": (
            "Bir kişinin tüm kurum rolleri — örneğin hem “Program koordinatörü” hem “Öğretmen”. Rol verme ve "
            "geri alma buradan yapılır; her işlem denetim günlüğüne yazılır."
        ),
    },
    "Birdən çox rolu olanlar": {
        "en": "People with more than one role",
        "ru": "С несколькими ролями",
        "tr": "Birden çok rolü olanlar",
    },
    "Bu bölmə nə edir?": _ROLE_ASSIGNMENT["Bu bölmə nə edir?"],
    (
        "Bu bölmə şəxsin təşkilat rollarını idarə edir: bir nəfər eyni anda həm «Proqram koordinatoru», "
        "həm «Müəllim» ola bilər."
    ): {
        "en": (
            "This section manages a person's organization roles: one person can be both “Program coordinator” "
            "and “Teacher” at the same time."
        ),
        "ru": (
            "Этот раздел управляет ролями человека в организации: один человек может быть одновременно "
            "«Координатором программы» и «Преподавателем»."
        ),
        "tr": (
            "Bu bölüm kişinin kurum rollerini yönetir: bir kişi aynı anda hem “Program koordinatörü” hem "
            "“Öğretmen” olabilir."
        ),
    },
    "Bölmə": {"en": "Unit", "ru": "Подразделение", "tr": "Birim"},
    "Bölmə seçilsə rol yalnız həmin bölmənin alt-ağacında işləyir.": {
        "en": "If a unit is selected, the role applies only within that unit's subtree.",
        "ru": "Если выбрано подразделение, роль действует только в его поддереве.",
        "tr": "Birim seçilirse rol yalnızca o birimin alt ağacında geçerlidir.",
    },
    "Bütün bölmələr": {"en": "All units", "ru": "Все подразделения", "tr": "Tüm birimler"},
    "Bütün rollar": _ROLE_ASSIGNMENT["Bütün rollar"],
    "Bütün üzvlər": {"en": "All members", "ru": "Все участники", "tr": "Tüm üyeler"},
    "Filtrə uyğun üzv yoxdur": _ROLE_ASSIGNMENT["Filtrə uyğun üzv yoxdur"],
    "Geri al": {"en": "Revoke", "ru": "Отозвать", "tr": "Geri çek"},
    "Geri alınacaq rol": {"en": "Role to revoke", "ru": "Отзываемая роль", "tr": "Geri alınacak rol"},
    "Heyət": _ROLE_ASSIGNMENT["Heyət"],
    "Hələ idarə ediləcək üzv yoxdur": {
        "en": "No members to manage yet",
        "ru": "Пока нет участников для управления",
        "tr": "Henüz yönetilecek üye yok",
    },
    "Köhnə ad: Profil rolları (multi-role / checkbox).": {
        "en": "Former name: Profile roles (multi-role / checkbox).",
        "ru": "Прежнее название: роли профиля (мульти-роль / чекбоксы).",
        "tr": "Eski adı: Profil rolleri (çoklu rol / onay kutusu).",
    },
    "Mövcud rollara toxunulmur — seçilmiş rol əlavə olunur.": {
        "en": "Existing roles are untouched — the selected role is added.",
        "ru": "Существующие роли не затрагиваются — выбранная роль добавляется.",
        "tr": "Mevcut rollere dokunulmaz — seçilen rol eklenir.",
    },
    "Nişanın yanındakı × — həmin rolu geri alır; şəxsin son üzvlüyü silinmir.": {
        "en": "The × next to a badge revokes that role; a person's last membership is never removed.",
        "ru": "Крестик × рядом со значком отзывает эту роль; последнее членство человека не удаляется.",
        "tr": "Rozetin yanındaki × o rolü geri alır; kişinin son üyeliği silinmez.",
    },
    "Nəticə: %(n)d nəfər": _ROLE_ASSIGNMENT["Nəticə: %(n)d nəfər"],
    "Qeyd": {"en": "Note", "ru": "Примечание", "tr": "Not"},
    "Redaktə bağlı": {"en": "Locked for editing", "ru": "Редактирование закрыто", "tr": "Düzenleme kapalı"},
    "Rol": {"en": "Role", "ru": "Роль", "tr": "Rol seçimi"},
    "Rol idarəetməsi üçün aktiv təşkilat tapılmadı.": {
        "en": "No active organization found for role management.",
        "ru": "Для управления ролями активная организация не найдена.",
        "tr": "Rol yönetimi için aktif kurum bulunamadı.",
    },
    "Rol kataloqu": _ROLE_ASSIGNMENT["Rol kataloqu"],
    "Rol sayı": {"en": "Role count", "ru": "Количество ролей", "tr": "Rol sayısı"},
    "Rol seçin": {"en": "Select a role", "ru": "Выберите роль", "tr": "Bir rol seçin"},
    "Rol siyahısı təşkilatın öz rol kataloqundan gəlir — «Rol təyin et» bölməsindəki siyahı ilə eynidir.": {
        "en": "The role list comes from the organization's own role catalogue — the same list as in “Assign role”.",
        "ru": "Список ролей берётся из каталога ролей самой организации — он совпадает с разделом «Назначить роль».",
        "tr": "Rol listesi kurumun kendi rol kataloğundan gelir — “Rol ata” bölümündeki listeyle aynıdır.",
    },
    "Rol təyin et": {"en": "Assign role", "ru": "Назначить роль", "tr": "Rol ata"},
    "Rol ver": {"en": "Grant role", "ru": "Выдать роль", "tr": "Rol ekle"},
    "Rol yoxdur": {"en": "No role", "ru": "Роли нет", "tr": "Rol yok"},
    "Rollar necə işləyir?": {
        "en": "How do roles work?",
        "ru": "Как работают роли?",
        "tr": "Roller nasıl çalışır?",
    },
    "Rolu geri al": {"en": "Revoke role", "ru": "Отозвать роль", "tr": "Rolü geri al"},
    "Səviyyə": _ROLE_ASSIGNMENT["Səviyyə"],
    "Tək rolu olanlar": {
        "en": "People with a single role",
        "ru": "С одной ролью",
        "tr": "Tek rolü olanlar",
    },
    "Təşkilat rolları": {"en": "Organization roles", "ru": "Роли в организации", "tr": "Kurum rolleri"},
    "Təşkilata üzv əlavə edildikcə siyahı burada görünəcək.": {
        "en": "The list appears here as members are added to the organization.",
        "ru": "Список появится здесь по мере добавления участников в организацию.",
        "tr": "Kuruma üye eklendikçe liste burada görünecek.",
    },
    "Yalnız seçilmiş üzvlük söndürülür.": {
        "en": "Only the selected membership is deactivated.",
        "ru": "Отключается только выбранное членство.",
        "tr": "Yalnızca seçilen üyelik kapatılır.",
    },
    "Yalnız öz səviyyənizdən aşağı rollar siyahıdadır; mövcud rollar toxunulmadan qalır.": {
        "en": "Only roles below your own level are listed; existing roles stay untouched.",
        "ru": "В списке только роли ниже вашего уровня; существующие роли не затрагиваются.",
        "tr": "Listede yalnızca kendi seviyenizin altındaki roller var; mevcut roller değişmez.",
    },
    "birdən çox təşkilat rolu": {
        "en": "more than one organization role",
        "ru": "более одной роли в организации",
        "tr": "birden çok kurum rolü",
    },
    "müəllim və yuxarı səviyyə": {
        "en": "teacher level and above",
        "ru": "уровень преподавателя и выше",
        "tr": "öğretmen ve üzeri seviye",
    },
    "sizin səviyyənizdən yuxarı": {
        "en": "above your own level",
        "ru": "выше вашего уровня",
        "tr": "sizin seviyenizin üstünde",
    },
    "«Rol ver» — mövcud rollara toxunmadan yeni rol əlavə edir.": {
        "en": "“Grant role” adds a new role without touching the existing ones.",
        "ru": "«Выдать роль» добавляет новую роль, не затрагивая существующие.",
        "tr": "“Rol ver” mevcut rollere dokunmadan yeni rol ekler.",
    },
    "Çoxlu rollu": {"en": "Multi-role", "ru": "С несколькими ролями", "tr": "Çoklu rollü"},
    "Üzv": {"en": "Members", "ru": "Участники", "tr": "Üye"},
    "Şəxs": _ROLE_ASSIGNMENT["Şəxs"],
    "Şəxsin digər rolları toxunulmadan qalır. Əməl audit jurnalına yazılır.": {
        "en": "The person's other roles stay untouched. The action is written to the audit log.",
        "ru": "Остальные роли человека не затрагиваются. Действие пишется в журнал аудита.",
        "tr": "Kişinin diğer rolleri değişmeden kalır. İşlem denetim günlüğüne yazılır.",
    },
    "Əhatə": {"en": "Scope", "ru": "Охват", "tr": "Kapsam"},
    "Əmr nömrəsi, tarix və ya səbəb — audit jurnalına yazılır": {
        "en": "Order number, date or reason — written to the audit log",
        "ru": "Номер приказа, дата или причина — пишется в журнал аудита",
        "tr": "Emir numarası, tarih ya da gerekçe — denetim günlüğüne yazılır",
    },
    "Əməllər": {"en": "Actions", "ru": "Действия", "tr": "İşlemler"},
    "Əsas rol": {"en": "Primary role", "ru": "Основная роль", "tr": "Birincil rol"},
    "ən yüksək səviyyəli roldur və naviqasiyada əsas rol kimi işlənir.": {
        "en": "is the highest-level role and is used as the primary role in navigation.",
        "ru": "— это роль с наивысшим уровнем, она используется как основная в навигации.",
        "tr": "en yüksek seviyeli roldür ve gezinmede birincil rol olarak kullanılır.",
    },
}

# ── «Rolları idarə et» server mesajları ──────────────────────────────────────

_MANAGE_ROLES_MESSAGE = {
    "Rol tapılmadı və ya deaktivdir.": {
        "en": "The role was not found or is inactive.",
        "ru": "Роль не найдена или неактивна.",
        "tr": "Rol bulunamadı ya da pasif.",
    },
    "Təşkilatda ən az bir sahib qalmalıdır.": {
        "en": "The organization must keep at least one owner.",
        "ru": "В организации должен остаться хотя бы один владелец.",
        "tr": "Kurumda en az bir sahip kalmalıdır.",
    },
    "Yalnız öz səviyyənizdən aşağı rolları verə bilərsiniz.": {
        "en": "You can only grant roles below your own level.",
        "ru": "Вы можете выдавать только роли ниже вашего уровня.",
        "tr": "Yalnızca kendi seviyenizin altındaki rolleri verebilirsiniz.",
    },
    "«%(role)s» rolu %(user)s hesabına verildi.": {
        "en": "The “%(role)s” role was granted to %(user)s.",
        "ru": "Роль «%(role)s» выдана пользователю %(user)s.",
        "tr": "“%(role)s” rolü %(user)s hesabına verildi.",
    },
    "«%(role)s» rolu %(user)s hesabından geri alındı.": {
        "en": "The “%(role)s” role was revoked from %(user)s.",
        "ru": "Роль «%(role)s» отозвана у пользователя %(user)s.",
        "tr": "“%(role)s” rolü %(user)s hesabından geri alındı.",
    },
    "«Administrator» səviyyəli rol üçün `org.admin.assign` icazəsi tələb olunur.": {
        "en": "An “Administrator” level role requires the `org.admin.assign` permission.",
        "ru": "Для роли уровня «Администратор» требуется разрешение `org.admin.assign`.",
        "tr": "“Yönetici” seviyesindeki rol için `org.admin.assign` izni gerekir.",
    },
    "«Sahib» səviyyəli rol üçün `org.owner.assign` icazəsi tələb olunur.": {
        "en": "An “Owner” level role requires the `org.owner.assign` permission.",
        "ru": "Для роли уровня «Владелец» требуется разрешение `org.owner.assign`.",
        "tr": "“Sahip” seviyesindeki rol için `org.owner.assign` izni gerekir.",
    },
    "Öz rollarınızı dəyişmək üçün təşkilat sahibi və ya superadmin olmalısınız.": {
        "en": "To change your own roles you must be the organization owner or a superadmin.",
        "ru": "Чтобы менять свои роли, нужно быть владельцем организации или суперадмином.",
        "tr": "Kendi rollerinizi değiştirmek için kurum sahibi ya da süper yönetici olmalısınız.",
    },
    "Üzvlük tapılmadı.": {
        "en": "Membership not found.",
        "ru": "Членство не найдено.",
        "tr": "Üyelik bulunamadı.",
    },
    "Şəxsin son üzvlüyü buradan silinmir — «Rol təyin et» bölməsindən idarə edin.": {
        "en": "A person's last membership cannot be removed here — manage it in “Assign role”.",
        "ru": "Последнее членство человека здесь не удаляется — управляйте им в разделе «Назначить роль».",
        "tr": "Kişinin son üyeliği buradan silinmez — “Rol ata” bölümünden yönetin.",
    },
}

# ── «İcazələr» ───────────────────────────────────────────────────────────────

_PERMISSION_EDITOR = {
    "%(key)s seç": {"en": "Select %(key)s", "ru": "Выбрать %(key)s", "tr": "%(key)s öğesini seç"},
    "%(total)d açardan": {"en": "of %(total)d keys", "ru": "из %(total)d ключей", "tr": "%(total)d anahtardan"},
    "Akademik kataloq": {
        "en": "Academic catalogue",
        "ru": "Академический каталог",
        "tr": "Akademik katalog",
    },
    "Aktiv": {"en": "Active", "ru": "Активно", "tr": "Aktif"},
    "Aktiv icazə": {"en": "Active permissions", "ru": "Активные разрешения", "tr": "Aktif izin"},
    "Aktiv təşkilat tapılmadı.": _ROLE_ASSIGNMENT["Aktiv təşkilat tapılmadı."],
    "Aktiv: %(count)s / %(total)s": {
        "en": "Active: %(count)s / %(total)s",
        "ru": "Активно: %(count)s / %(total)s",
        "tr": "Aktif: %(count)s / %(total)s",
    },
    "Aktiv: icazə açıqdır.": {
        "en": "Active: the permission is granted.",
        "ru": "Активно: разрешение открыто.",
        "tr": "Aktif: izin açıktır.",
    },
    "Analitik hesabat və göstəricilər": {
        "en": "Analytical reports and metrics",
        "ru": "Аналитические отчёты и показатели",
        "tr": "Analitik raporlar ve göstergeler",
    },
    "Analitika": {"en": "Analytics", "ru": "Аналитика", "tr": "Analitik"},
    "Apellyasiya": {"en": "Appeals", "ru": "Апелляции", "tr": "İtiraz"},
    "Apellyasiya müraciətləri": {
        "en": "Appeal requests",
        "ru": "Апелляционные заявления",
        "tr": "İtiraz başvuruları",
    },
    "Audit jurnalı": {"en": "Audit log", "ru": "Журнал аудита", "tr": "Denetim günlüğü"},
    "Axtar": {"en": "Search", "ru": "Найти", "tr": "Ara"},
    "Axtarışı təmizlə": {"en": "Clear the search", "ru": "Очистить поиск", "tr": "Aramayı temizle"},
    "Açar, ad və ya izah üzrə axtar (məs: view, üzv)": {
        "en": "Search by key, name or description (e.g. view, member)",
        "ru": "Поиск по ключу, названию или описанию (напр. view, участник)",
        "tr": "Anahtar, ad ya da açıklamaya göre ara (örn. view, üye)",
    },
    "Bu bölmə nə üçündür?": {
        "en": "What is this section for?",
        "ru": "Для чего этот раздел?",
        "tr": "Bu bölüm ne için?",
    },
    "Bu bölmə üçün icazələr": {
        "en": "Permissions for this section",
        "ru": "Разрешения для этого раздела",
        "tr": "Bu bölüm için izinler",
    },
    "Bu rol hazırda icazəni başqalarına paylaya bilir. Delegasiyanı geri al.": {
        "en": "This role can currently pass the permission on to others. Revoke the delegation.",
        "ru": "Сейчас эта роль может передавать разрешение другим. Отозвать делегирование.",
        "tr": "Bu rol şu anda izni başkalarına dağıtabiliyor. Yetki devrini geri alın.",
    },
    "Bu rola icazəni daha aşağı rollara paylamaq hüququ ver.": {
        "en": "Let this role pass the permission on to lower roles.",
        "ru": "Разрешить этой роли передавать разрешение более низким ролям.",
        "tr": "Bu role, izni daha alt rollere dağıtma hakkı verin.",
    },
    "Bu təşkilatda idarə edə biləcəyiniz rol yoxdur.": {
        "en": "There is no role you can manage in this organization.",
        "ru": "В этой организации нет ролей, доступных вам для управления.",
        "tr": "Bu kurumda yönetebileceğiniz rol yok.",
    },
    "Deaktiv": {"en": "Inactive", "ru": "Неактивно", "tr": "Pasif"},
    "Deaktiv: icazə bağlıdır.": {
        "en": "Inactive: the permission is closed.",
        "ru": "Неактивно: разрешение закрыто.",
        "tr": "Pasif: izin kapalıdır.",
    },
    "Delegasiya": {"en": "Delegation", "ru": "Делегирование", "tr": "Yetki devri"},
    "Delegasiya et": {"en": "Delegate", "ru": "Делегировать", "tr": "Devret"},
    "Delegasiyanı al": {
        "en": "Revoke delegation",
        "ru": "Отозвать делегирование",
        "tr": "Devri geri al",
    },
    "Digər rollarda:": {"en": "In other roles:", "ru": "В других ролях:", "tr": "Diğer rollerde:"},
    "Fakültə, şöbə və struktur vahidləri": {
        "en": "Faculties, departments and structural units",
        "ru": "Факультеты, отделы и структурные подразделения",
        "tr": "Fakülte, bölüm ve yapısal birimler",
    },
    "Hamısını seç": {"en": "Select all", "ru": "Выбрать все", "tr": "Tümünü seç"},
    "Jurnal": {"en": "Journal", "ru": "Журнал", "tr": "Yoklama defteri"},
    "Jurnal baxışı və sənədli düzəlişlər": {
        "en": "Journal review and documented corrections",
        "ru": "Просмотр журнала и документальные исправления",
        "tr": "Defter görüntüleme ve belgeli düzeltmeler",
    },
    "Kateqoriya": {"en": "Categories", "ru": "Категории", "tr": "Kategori"},
    "Keyfiyyət": {"en": "Quality", "ru": "Качество", "tr": "Kalite"},
    "Keyfiyyət yoxlaması əməliyyatları": {
        "en": "Quality assurance operations",
        "ru": "Операции контроля качества",
        "tr": "Kalite kontrol işlemleri",
    },
    "Kurs yaradılması və kurs idarəetməsi": {
        "en": "Course creation and course management",
        "ru": "Создание и управление курсами",
        "tr": "Ders oluşturma ve ders yönetimi",
    },
    "Kurslar": {"en": "Courses", "ru": "Курсы", "tr": "Dersler"},
    "Nəticə tapılmadı.": {"en": "No results found.", "ru": "Ничего не найдено.", "tr": "Sonuç bulunamadı."},
    "Permission idarəetməsi üçün `role.assign` səlahiyyəti tələb olunur.": {
        "en": "Managing permissions requires the `role.assign` authority.",
        "ru": "Для управления разрешениями требуется полномочие `role.assign`.",
        "tr": "İzin yönetimi için `role.assign` yetkisi gerekir.",
    },
    "Qiymətləndirmə": {"en": "Grading", "ru": "Оценивание", "tr": "Değerlendirme"},
    "Qiymətləndirmə və nəticə axınları": {
        "en": "Grading and result flows",
        "ru": "Процессы оценивания и результатов",
        "tr": "Değerlendirme ve sonuç akışları",
    },
    "Qruplar": {"en": "Groups", "ru": "Группы", "tr": "Gruplar"},
    "Qısa izah": {"en": "Short explanation", "ru": "Краткое пояснение", "tr": "Kısa açıklama"},
    "Rol": {"en": "Role", "ru": "Роль", "tr": "Rol seçimi"},
    "Rol təyini və rol səviyyələri": {
        "en": "Role assignment and role levels",
        "ru": "Назначение ролей и уровни ролей",
        "tr": "Rol atama ve rol seviyeleri",
    },
    "Rollar": {"en": "Roles", "ru": "Роли", "tr": "Roller"},
    (
        "Rolun hansı funksiyaları aça biləcəyini buradan idarə edin. Açarlar bölmələr üzrə qruplaşdırılıb; "
        "hər sətir həmin icazənin başqa hansı rollarda olduğunu da göstərir."
    ): {
        "en": (
            "Manage here which features a role can open. Keys are grouped by section; each row also shows "
            "which other roles hold that permission."
        ),
        "ru": (
            "Здесь настраивается, какие функции открывает роль. Ключи сгруппированы по разделам; в каждой "
            "строке видно, у каких ещё ролей есть это разрешение."
        ),
        "tr": (
            "Rolün hangi işlevleri açabileceğini buradan yönetin. Anahtarlar bölümlere göre gruplanmıştır; her "
            "satır o iznin başka hangi rollerde olduğunu da gösterir."
        ),
    },
    "Seçilmiş rol": {"en": "Selected role", "ru": "Выбранная роль", "tr": "Seçili rol"},
    "Seçilmiş rola hansı funksiyaların açıq olacağını buradan idarə edirsiniz.": {
        "en": "Here you control which features are open to the selected role.",
        "ru": "Здесь вы управляете тем, какие функции открыты выбранной роли.",
        "tr": "Seçili role hangi işlevlerin açık olacağını buradan yönetirsiniz.",
    },
    "Seçilənləri sil": {
        "en": "Remove selected",
        "ru": "Удалить выбранные",
        "tr": "Seçilenleri sil",
    },
    "Seçilənləri əlavə et": {"en": "Add selected", "ru": "Добавить выбранные", "tr": "Seçilenleri ekle"},
    "Seçimi sıfırla": {"en": "Clear selection", "ru": "Сбросить выбор", "tr": "Seçimi temizle"},
    "Sil": {"en": "Remove", "ru": "Удалить", "tr": "Kaldır"},
    "Struktur": {"en": "Structure", "ru": "Структура", "tr": "Yapı"},
    "Tarixçə və audit log baxışı": {
        "en": "History and audit-log review",
        "ru": "Просмотр истории и журнала аудита",
        "tr": "Geçmiş ve denetim günlüğü görüntüleme",
    },
    "Toplu: seçilənləri bir anda dəyişir.": {
        "en": "Bulk: changes everything selected at once.",
        "ru": "Массово: меняет всё выбранное сразу.",
        "tr": "Toplu: seçilenleri bir anda değiştirir.",
    },
    "Tələbə qruplarının yaradılması və idarəsi": {
        "en": "Creating and managing student groups",
        "ru": "Создание студенческих групп и управление ими",
        "tr": "Öğrenci gruplarının oluşturulması ve yönetimi",
    },
    "Təşkilat": _ROLE_ASSIGNMENT["Təşkilat"],
    "Təşkilat ayarları və idarəetmə əməliyyatları": {
        "en": "Organization settings and management operations",
        "ru": "Настройки организации и операции управления",
        "tr": "Kurum ayarları ve yönetim işlemleri",
    },
    "aşağı rollara paylana bilir": {
        "en": "can be passed on to lower roles",
        "ru": "может передаваться более низким ролям",
        "tr": "alt rollere dağıtılabilir",
    },
    "səviyyə %(level)d": {"en": "level %(level)d", "ru": "уровень %(level)d", "tr": "seviye %(level)d"},
    "Üzvlər": {"en": "Members", "ru": "Участники", "tr": "Üyeler"},
    "İcazə axtar": {"en": "Search permissions", "ru": "Поиск разрешений", "tr": "İzin ara"},
    "İdarə edilə bilən rol": {
        "en": "Manageable roles",
        "ru": "Управляемые роли",
        "tr": "Yönetilebilir rol",
    },
    "İmtahan idarəetməsi və nəzarət": {
        "en": "Exam management and supervision",
        "ru": "Управление экзаменами и надзор",
        "tr": "Sınav yönetimi ve gözetim",
    },
    "İmtahanlar": {"en": "Exams", "ru": "Экзамены", "tr": "Sınavlar"},
    "İstifadəçilər və üzvlüklə bağlı əməliyyatlar": {
        "en": "User and membership operations",
        "ru": "Операции с пользователями и членством",
        "tr": "Kullanıcı ve üyelikle ilgili işlemler",
    },
    "İxtisas və fənn reyestrləri": {
        "en": "Programme and subject registries",
        "ru": "Реестры специальностей и предметов",
        "tr": "Program ve ders kayıtları",
    },
    "Əlavə et": {"en": "Add", "ru": "Добавить", "tr": "Ekle"},
}

# ── Ortaq filtr paneli (əvvəldən kodda idi, kataloqda yox) ───────────────────

_UI_FILTERS = {
    "Axtar…": {"en": "Search…", "ru": "Поиск…", "tr": "Ara…"},
    "Uyğun nəticə yoxdur": {
        "en": "No matching results",
        "ru": "Совпадений нет",
        "tr": "Eşleşen sonuç yok",
    },
}

ENTRIES = {
    "accounts.role_assignment": _ROLE_ASSIGNMENT,
    "accounts.manage_roles": _MANAGE_ROLES,
    "accounts.manage_roles.message": _MANAGE_ROLES_MESSAGE,
    "accounts.permission_editor": _PERMISSION_EDITOR,
    "ui.filters": _UI_FILTERS,
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
