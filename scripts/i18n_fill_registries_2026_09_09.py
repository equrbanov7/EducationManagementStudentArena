#!/usr/bin/env python3
"""EMSArena i18n — «Təşkilat rolları» reyestri + «Registrar (kataloq)» bölməsi.

2026-09-09 sahib rəyi ilə iki ekran yenidən quruldu:

* `organizations.roles_registry` — rol kataloqu kart torundan `ems_ui`
  reyestrinə keçdi (KPI, süzgəc, cədvəl, çekmecə);
* `registrar.catalog` — akademik kataloq konsolu MÜSTƏQİL səhifədən kabinet
  bölməsinə köçdü (tab-lar + dialoqlar).

Hər ikisinin mətnləri Python tərəfdə `pgettext(_CTX, …)` ilə yazılıb; layihənin
mənbə skaneri (`scripts/i18n_source_scan.py`) `_CTX` modul dəyişəni olduğuna
görə onları GÖRMÜR — yəni qapı yaşıl olsa da EN/RU/TR istifadəçi azərbaycanca
mətn görərdi. Bu skript həmin boşluğu bağlayır.

⚠️ `makemessages` İŞLƏDİLMİR (əl ilə yazılmış blokları silir) — yalnız ƏLAVƏ
edilir, mövcud açar toxunulmur. Yer tutucular (`%(n)s`, `%%`) tərcümədə də EYNİ
qalmalıdır (`scripts/check_i18n_catalogs.py` yoxlayır).

İstifadə:  python scripts/i18n_fill_registries_2026_09_09.py
           (sonra `.mo` yenilənir — skript özü edir)
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

ROLES = {
    "%(n)s açar": ("%(n)s key(s)", "ключей: %(n)s", "%(n)s anahtar"),
    "Ad (A→Z)": ("Name (A→Z)", "Название (А→Я)", "Ada göre (A→Z)"),
    "Aktiv təşkilat tapılmadı.": (
        "No active organization found.",
        "Активная организация не найдена.",
        "Etkin kurum bulunamadı.",
    ),
    "Axtarış": ("Search", "Поиск", "Arama"),
    "Bu rol bütün icazələri daşıyır (*) — ayrıca açar siyahısı saxlanmır.": (
        "This role carries every permission (*) — no separate key list is stored.",
        "Эта роль имеет все права (*) — отдельный список ключей не хранится.",
        "Bu rol tüm yetkileri taşır (*) — ayrı bir anahtar listesi tutulmaz.",
    ),
    "Bu rola heç bir icazə açarı verilməyib.": (
        "No permission key has been granted to this role.",
        "Этой роли не выдано ни одного ключа прав.",
        "Bu role hiçbir yetki anahtarı verilmemiş.",
    ),
    "Bu rolu daşıyan üzv": ("People holding this role", "Участники с этой ролью", "Bu role sahip üyeler"),
    "Bu rəqəm kataloqun öz səviyyəsidir. Konkret şəxsin RBAC səviyyəsi üzvlüyündən asılı olaraq fərqlənə bilər"
    " — «Rolları idarə et» ekranında görünən rəqəm odur.": (
        "This number is the catalogue's own level. A given person's RBAC level may differ depending on their "
        "membership — that is the number shown on the «Manage roles» screen.",
        "Это собственный уровень каталога. Уровень RBAC конкретного человека может отличаться в зависимости от "
        "его членства — именно он показан на экране «Управление ролями».",
        "Bu sayı katalogun kendi düzeyidir. Bir kişinin RBAC düzeyi üyeliğine göre farklı olabilir — «Rolleri "
        "yönet» ekranında görünen sayı odur.",
    ),
    "Bütün icazələr": ("All permissions", "Все права", "Tüm yetkiler"),
    "Bütün icazələr (*)": ("All permissions (*)", "Все права (*)", "Tüm yetkiler (*)"),
    "Bütün kateqoriyalar": ("All categories", "Все категории", "Tüm kategoriler"),
    "Bütün təşkilat": ("Organization-wide", "Вся организация", "Tüm kurum"),
    "Bütün əhatələr": ("All scopes", "Все области", "Tüm kapsamlar"),
    "Deaktiv": ("Inactive", "Неактивна", "Pasif"),
    "Digər": ("Other", "Прочее", "Diğer"),
    "Dərs": ("Course", "Курс", "Ders"),
    "Hamısı": ("All", "Все", "Tümü"),
    "Heç kimə verilməyib": ("Granted to nobody", "Никому не назначена", "Kimseye verilmemiş"),
    "Kataloq səviyyəsi": ("Catalogue level", "Уровень каталога", "Katalog düzeyi"),
    "Kataloqda hələ rol yoxdur": (
        "There are no roles in the catalogue yet",
        "В каталоге пока нет ролей",
        "Katalogda henüz rol yok",
    ),
    "Nəticə: %(n)s rol": ("Result: %(n)s role(s)", "Результат: ролей — %(n)s", "Sonuç: %(n)s rol"),
    "Rol": ("Role", "Роль", "Rol adı"),
    "Rol adı, izah və ya icazə": (
        "Role name, description or permission",
        "Название роли, описание или право",
        "Rol adı, açıklama veya yetki",
    ),
    "Rol haqqında": ("About the role", "О роли", "Rol hakkında"),
    "Rollar universitet şablonundan miqrasiya ilə gəlir.": (
        "Roles arrive by migration from the university template.",
        "Роли поступают миграцией из университетского шаблона.",
        "Roller üniversite şablonundan göçle gelir.",
    ),
    "Rolları idarə et": ("Manage roles", "Управление ролями", "Rolleri yönet"),
    "Sistem": ("System", "Системная", "Yerleşik"),
    "Sistem rolu": ("System role", "Системная роль", "Sistem rolü"),
    "Struktur bölməsi": ("Structural unit", "Структурное подразделение", "Yapısal birim"),
    "Süzgəcləri sıfırlayıb yenidən yoxlayın.": (
        "Reset the filters and try again.",
        "Сбросьте фильтры и попробуйте снова.",
        "Filtreleri sıfırlayıp tekrar deneyin.",
    ),
    "Sıralama": ("Sorting", "Сортировка", "Sıralama ölçütü"),
    "Səviyyə (aşağıdan)": ("Level (lowest first)", "Уровень (по возрастанию)", "Düzey (düşükten)"),
    "Səviyyə (yuxarıdan)": ("Level (highest first)", "Уровень (по убыванию)", "Düzey (yüksekten)"),
    "Təyinat": ("Assignments", "Назначения", "Atamalar"),
    "Təşkilat rolları": ("Organization roles", "Роли организации", "Kurum rolleri"),
    "Təşkilatın rol kataloqu: hər rolun səviyyəsi, əhatəsi, neçə nəfərdə olduğu və hansı icazələri daşıdığı."
    " Rola klik edib icazələri kateqoriya üzrə açın.": (
        "The organization's role catalogue: each role's level, scope, how many people hold it and which "
        "permissions it carries. Click a role to open its permissions by category.",
        "Каталог ролей организации: уровень и область каждой роли, сколько человек её имеют и какие права она "
        "несёт. Нажмите на роль, чтобы раскрыть права по категориям.",
        "Kurumun rol katalogu: her rolün düzeyi, kapsamı, kaç kişide olduğu ve hangi yetkileri taşıdığı. "
        "Yetkileri kategoriye göre açmak için role tıklayın.",
    ),
    "Təşkilatın öz rolu": ("Organization's own role", "Собственная роль организации", "Kurumun kendi rolü"),
    "Uyğun rol tapılmadı": ("No matching role found", "Подходящая роль не найдена", "Uygun rol bulunamadı"),
    "Verilməyib": ("Not granted", "Не назначена", "Verilmemiş"),
    "Vəziyyət": ("State", "Состояние", "Durum"),
    "aktiv üzvlük (bir nəfər bir neçə dəfə sayıla bilər)": (
        "active memberships (one person may be counted more than once)",
        "активные членства (один человек может считаться несколько раз)",
        "etkin üyelikler (bir kişi birden çok kez sayılabilir)",
    ),
    "heç bir üzvdə yoxdur": ("held by nobody", "нет ни у одного участника", "hiçbir üyede yok"),
    "kataloqda, süzgəcdən asılı deyil": (
        "in the catalogue, regardless of filters",
        "в каталоге, независимо от фильтров",
        "katalogda, filtreden bağımsız",
    ),
    "miqrasiya ilə gəlir, silinmir": (
        "arrives by migration, cannot be deleted",
        "поступает миграцией, не удаляется",
        "göçle gelir, silinmez",
    ),
    "rol var, açar yoxdur": ("the role exists but has no keys", "роль есть, ключей нет", "rol var, anahtar yok"),
    "Üzv": ("Members", "Участники", "Üyeler"),
    "Üzv sayı": ("Member count", "Число участников", "Üye sayısı"),
    "İcazə kateqoriyası": ("Permission category", "Категория прав", "Yetki kategorisi"),
    "İcazə verilməyib": ("No permission granted", "Права не выданы", "Yetki verilmemiş"),
    "İcazələr": ("Permissions", "Права", "Yetkiler"),
    "İcazələr kateqoriya üzrə qruplaşdırılıb.": (
        "Permissions are grouped by category.",
        "Права сгруппированы по категориям.",
        "Yetkiler kategoriye göre gruplanmıştır.",
    ),
    "İcazələri redaktə et": ("Edit permissions", "Редактировать права", "Yetkileri düzenle"),
    "İcazəsi yoxdur": ("Has no permissions", "Без прав", "Yetkisi yok"),
    "İcazəsiz": ("Without permissions", "Без прав", "Yetkisiz"),
    "Əhatə": ("Scope", "Область", "Kapsam"),
    "Əməl": ("Action", "Действие", "İşlem"),
    "Əməllər": ("Actions", "Действия", "İşlemler"),
    "Ətraflı": ("Details", "Подробно", "Ayrıntı"),
}

CATALOG = {
    "%(n)s-i boşdur": ("%(n)s of them are empty", "из них пустых: %(n)s", "%(n)s tanesi boş"),
    "7 rəqəm, məsələn 6006004. İxtisas yeni təsnifatda yoxdursa boş qalır.": (
        "7 digits, e.g. 6006004. Left empty if the programme is absent from the new classification.",
        "7 цифр, например 6006004. Остаётся пустым, если специальности нет в новой классификации.",
        "7 rakam, örneğin 6006004. Program yeni sınıflandırmada yoksa boş bırakılır.",
    ),
    "Ad, kod və ya şifr": ("Name, code or cipher", "Название, код или шифр", "Ad, kod veya şifre"),
    "Akademik kataloq: ixtisaslar, fənlər, tədris planları, semestr açılışları, qiymətləndirmə rubrikləri və"
    " tələbə təyinatları. Hər əməl bu səhifədə, dialoqda aparılır — kabinetdən çıxmır.": (
        "The academic catalogue: programmes, subjects, curricula, semester offerings, grading rubrics and "
        "student assignments. Every action happens on this page, in a dialog — you never leave the cabinet.",
        "Академический каталог: специальности, предметы, учебные планы, открытия семестра, рубрики оценивания "
        "и назначения студентов. Каждое действие выполняется на этой странице, в диалоге — не покидая кабинет.",
        "Akademik katalog: programlar, dersler, öğretim planları, dönem açılışları, değerlendirme rubrikleri ve "
        "öğrenci atamaları. Her işlem bu sayfada, bir iletişim kutusunda yapılır — kabinetten çıkılmaz.",
    ),
    "Akademik kataloqu idarə etmək üçün icazəniz yoxdur — bu bölmə təşkilat üzrə `course.edit` açarı olan"
    " rollar üçündür.": (
        "You have no permission to manage the academic catalogue — this section is for roles holding the "
        "organization-wide `course.edit` key.",
        "У вас нет прав на управление академическим каталогом — этот раздел для ролей с ключом `course.edit` "
        "на уровне организации.",
        "Akademik katalogu yönetme yetkiniz yok — bu bölüm kurum genelinde `course.edit` anahtarına sahip "
        "roller içindir.",
    ),
    "Aktiv": ("Active", "Активна", "Etkin"),
    "Aktiv semestr yoxdur": ("There is no active semester", "Нет активного семестра", "Etkin dönem yok"),
    "Aktiv — siyahılarda və seçicilərdə görünür": (
        "Active — appears in lists and pickers",
        "Активна — видна в списках и выборе",
        "Etkin — listelerde ve seçicilerde görünür",
    ),
    "Axtarış": ("Search", "Поиск", "Arama"),
    "Boş qalsa ixtisasın adı işlədilir.": (
        "If left empty the programme name is used.",
        "Если оставить пустым, используется название специальности.",
        "Boş bırakılırsa program adı kullanılır.",
    ),
    "Bu siyahıda sətir yoxdur": ("This list has no rows", "В этом списке нет строк", "Bu listede satır yok"),
    "Bütün ixtisaslar": ("All programmes", "Все специальности", "Tüm programlar"),
    "Bütün statuslar": ("All statuses", "Все статусы", "Tüm durumlar"),
    "Daxili kod": ("Internal code", "Внутренний код", "Dahili kod"),
    "Deaktiv": ("Inactive", "Неактивна", "Pasif"),
    "Dərs saatı": ("Lesson hours", "Учебных часов", "Ders saati"),
    "ECTS": ("ECTS credits", "Кредиты ECTS", "AKTS"),
    "ECTS krediti": ("ECTS credit", "Кредит ECTS", "AKTS kredisi"),
    "Fənlər": ("Subjects", "Предметы", "Dersler"),
    "Fənn": ("Subject", "Предмет", "Ders"),
    "Fənn axtar…": ("Search a subject…", "Найти предмет…", "Ders ara…"),
    "Fənn aç": ("Open a subject", "Открыть предмет", "Ders aç"),
    "Fənn kodu": ("Subject code", "Код предмета", "Ders kodu"),
    "Fənn sətri": ("Subject rows", "Строк предметов", "Ders satırı"),
    "Fənnin adı": ("Subject name", "Название предмета", "Dersin adı"),
    "Hamısı": ("All", "Все", "Tümü"),
    "Hər sətir bir meyardır: «ad: bal». Mövcud meyarların balı ad dəyişmədikcə qorunur.": (
        "One criterion per line: «name: score». Existing criteria keep their score while the name is unchanged.",
        "По одному критерию в строке: «название: балл». Существующие критерии сохраняют балл, пока не изменено "
        "название.",
        "Her satır bir ölçüttür: «ad: puan». Adı değişmedikçe mevcut ölçütlerin puanı korunur.",
    ),
    "Kataloq bölmələri": ("Catalogue sections", "Разделы каталога", "Katalog bölümleri"),
    "Köhnə şifr (050/060)": ("Legacy cipher (050/060)", "Прежний шифр (050/060)", "Eski şifre (050/060)"),
    "Meyar": ("Criteria", "Критериев", "Ölçüt"),
    "Meyarlar": ("Criteria", "Критерии", "Ölçütler"),
    "Müəllim": ("Teacher", "Преподаватель", "Öğretim elemanı"),
    "Müəllim axtar…": ("Search a teacher…", "Найти преподавателя…", "Öğretim elemanı ara…"),
    "Müəllim jurnalın sahibidir. Sonradan dəyişmək «Fənn təhvili» bölməsindən aparılır.": (
        "The teacher owns the gradebook. Changing it later is done from the «Subject handover» section.",
        "Преподаватель — владелец журнала. Последующая смена выполняется в разделе «Передача предмета».",
        "Öğretim elemanı not defterinin sahibidir. Sonradan değiştirme «Ders devri» bölümünden yapılır.",
    ),
    "Müəllim təyin edilməyib": ("No teacher assigned", "Преподаватель не назначен", "Öğretim elemanı atanmamış"),
    "Müəllimi var": ("Has a teacher", "Преподаватель назначен", "Öğretim elemanı var"),
    "Müəllimsiz açılış": ("Offerings without a teacher", "Открытия без преподавателя", "Öğretim elemanısız açılış"),
    "Nəticə: %(n)s sətir": ("Result: %(n)s row(s)", "Результат: строк — %(n)s", "Sonuç: %(n)s satır"),
    "Planın adı": ("Curriculum name", "Название плана", "Plan adı"),
    "Qayıb limiti": ("Absence limit", "Лимит пропусков", "Devamsızlık sınırı"),
    "Qayıb limiti (%%)": ("Absence limit (%%)", "Лимит пропусков (%%)", "Devamsızlık sınırı (%%)"),
    "Qrup": ("Group", "Группа", "Grup"),
    "Qrup axtar…": ("Search a group…", "Найти группу…", "Grup ara…"),
    "Qəbul ili": ("Admission year", "Год приёма", "Kabul yılı"),
    "Redaktə et": ("Edit", "Редактировать", "Düzenle"),
    "Reyestrdə aç": ("Open in the registry", "Открыть в реестре", "Kayıtta aç"),
    "Rubrik": ("Rubric", "Рубрика", "Değerlendirme rubriği"),
    "Rubrikin adı": ("Rubric name", "Название рубрики", "Rubrik adı"),
    "Rubriklər": ("Rubrics", "Рубрики", "Rubrikler"),
    "Rəsmi şifr (NK 503)": ("Official cipher (CM 503)", "Официальный шифр (КМ 503)", "Resmî şifre (BK 503)"),
    "Saat": ("Hours", "Часов", "Ders saati"),
    "Semestr": ("Semester", "Семестр", "Dönem"),
    "Semestr açılışları": ("Semester offerings", "Открытия семестра", "Dönem açılışları"),
    "Semestr açılışı": ("Semester offerings", "Открытий семестра", "Dönem açılışı"),
    "Status": ("Academic status", "Статус", "Durum"),
    "Süzgəci sıfırlayın və ya sağ yuxarıdakı düymə ilə yenisini əlavə edin.": (
        "Reset the filter, or add a new one with the button at the top right.",
        "Сбросьте фильтр или добавьте новую запись кнопкой справа вверху.",
        "Filtreyi sıfırlayın ya da sağ üstteki düğmeyle yenisini ekleyin.",
    ),
    "Səviyyə": ("Level", "Уровень", "Düzey"),
    "Tədris planları": ("Curricula", "Учебные планы", "Öğretim planları"),
    "Tədris planı": ("Curriculum", "Учебный план", "Öğretim planı"),
    "Təhsil səviyyəsi": ("Degree level", "Уровень образования", "Eğitim düzeyi"),
    "Tələbə": ("Student", "Студент", "Öğrenci"),
    "Tələbə reyestrinə keç": ("Go to the student registry", "Перейти в реестр студентов", "Öğrenci kaydına git"),
    "Tələbə təyin et": ("Assign a student", "Назначить студента", "Öğrenci ata"),
    "Tələbə təyinatları": ("Student assignments", "Назначения студентов", "Öğrenci atamaları"),
    "Tələbə təyinatları burada YALNIZ oxunur. Yeni təyinat və köçürmə «Tələbə reyestri» bölməsindən aparılır"
    " — orada axtarışlı tələbə seçicisi var.": (
        "Student assignments are READ-ONLY here. New assignments and transfers are done in the «Student "
        "registry» section — it has a searchable student picker.",
        "Назначения студентов здесь ТОЛЬКО для чтения. Новые назначения и переводы выполняются в разделе "
        "«Реестр студентов» — там есть выбор студента с поиском.",
        "Öğrenci atamaları burada YALNIZCA okunur. Yeni atama ve nakil «Öğrenci kaydı» bölümünden yapılır — "
        "orada aramalı öğrenci seçici vardır.",
    ),
    "Təsvir": ("Description", "Описание", "Açıklama"),
    "Təyin edilməyib": ("Not assigned", "Не назначен", "Atanmamış"),
    "Uyğun fənn yoxdur": ("No matching subject", "Подходящих предметов нет", "Uygun ders yok"),
    "Uyğun ixtisas yoxdur": ("No matching programme", "Подходящих специальностей нет", "Uygun program yok"),
    "Uyğun müəllim yoxdur": ("No matching teacher", "Подходящих преподавателей нет", "Uygun öğretim elemanı yok"),
    "Uyğun qrup yoxdur": ("No matching group", "Подходящих групп нет", "Uygun grup yok"),
    "Vəziyyət": ("State", "Состояние", "Durum"),
    "Yadda saxla": ("Save", "Сохранить", "Kaydet"),
    "Yeni fənn": ("New subject", "Новый предмет", "Yeni ders"),
    "Yeni ixtisas": ("New programme", "Новая специальность", "Yeni program"),
    "Yeni rubrik": ("New rubric", "Новая рубрика", "Yeni değerlendirme rubriği"),
    "Yeni tədris planı": ("New curriculum", "Новый учебный план", "Yeni öğretim planı"),
    "aktiv semestr yoxdur": ("no active semester", "нет активного семестра", "etkin dönem yok"),
    "jurnal sahibi yoxdur": ("no gradebook owner", "нет владельца журнала", "not defteri sahibi yok"),
    "Ümumi ECTS": ("Total ECTS", "Всего ECTS", "Toplam AKTS"),
    "İxtisas": ("Programme", "Специальность", "Program"),
    "İxtisas axtar…": ("Search a programme…", "Найти специальность…", "Program ara…"),
    "İxtisaslar": ("Programmes", "Специальности", "Programlar"),
    "İxtisasın adı": ("Programme name", "Название специальности", "Programın adı"),
    "Əməl": ("Action", "Действие", "İşlem"),
    "Məzmun: 40&#10;Struktur: 30&#10;Təqdimat: 30": (
        "Content: 40&#10;Structure: 30&#10;Delivery: 30",
        "Содержание: 40&#10;Структура: 30&#10;Подача: 30",
        "İçerik: 40&#10;Yapı: 30&#10;Sunum: 30",
    ),
}

RIM = {
    "Tək müəllim əlavə et": ("Add a single teacher", "Добавить одного преподавателя", "Tek öğretim elemanı ekle"),
    "Tək tələbə əlavə et": ("Add a single student", "Добавить одного студента", "Tek öğrenci ekle"),
}

SIDEBAR = {
    "Rolları idarə et": ("Manage roles", "Управление ролями", "Rolleri yönet"),
    "İcazələr": ("Permissions", "Права", "Yetkiler"),
}

#: Konteksti OLMAYAN mətn (apellyasiya reyestrinin izahı) — `msgctxt` sətri
#: ümumiyyətlə yazılmır; `msgctxt ""` BAŞQA açardır və runtime-da tapılmaz.
NO_CONTEXT = {
    "Bütün apellyasiya müraciətləri — fənn, müəllim, qrup, imtahan tipi, status və dövr üzrə süzün;"
    " sütun başlığı sıralayır.": (
        "All appeal requests — filter by subject, teacher, group, exam type, status and period; the column "
        "header sorts.",
        "Все апелляции — фильтруйте по предмету, преподавателю, группе, типу экзамена, статусу и периоду; "
        "заголовок столбца сортирует.",
        "Tüm itiraz başvuruları — ders, öğretim elemanı, grup, sınav türü, durum ve döneme göre süzün; sütun "
        "başlığı sıralar.",
    ),
}

GROUPS = (
    ("organizations.roles_registry", ROLES),
    ("registrar.catalog", CATALOG),
    ("profile.rim", RIM),
    ("profile.sidebar", SIDEBAR),
    (None, NO_CONTEXT),
)


def main() -> int:
    index = {"az": 0, "en": 0, "ru": 1, "tr": 2}
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        have = {(entry.msgctxt or "", entry.msgid) for entry in po}
        added = 0
        for ctx, table in GROUPS:
            for msgid, translations in table.items():
                if (ctx or "", msgid) in have:
                    continue
                msgstr = msgid if lang == "az" else translations[index[lang]]
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
                added += 1
        if added:
            po.save(path)
            po.save_as_mofile(os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.mo"))
        print(f"{lang}: +{added}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
