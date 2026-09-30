#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-01 təşkilat səhifələrinin redizaynı (sahib: «Panel / Üzvlər / Rollar»).

Əlavə olunan mətnlər:
  * `organizations.overview` — yeni kabinet bölməsi «Təşkilat paneli» (`org-overview`):
    `_sections/org_overview.py` + `sections/_org_overview.html` və `org_overview/*.html`;
  * `profile.sidebar` — «Təşkilat paneli» (menyu bəndi, bölmə başlığı);
  * `organizations.members` — hesab statusu süzgəci, CSV ixracı (başlıqlar + audit səbəbi),
    «Panel» keçidi, müstəqil səhifənin başlığı;
  * `organizations.roles_registry` — rol kartları («Xüsusi», «səviyyə», «N icazə», «Üzvlər»).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_org_2026_10_01.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

OV = "organizations.overview"
SB = "profile.sidebar"
MB = "organizations.members"
RR = "organizations.roles_registry"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_OVERVIEW = [
    # Sürətli keçidlər (başlıq + izah)
    _t("Universitet strukturu", "University structure", "Структура университета", "Üniversite yapısı"),
    _t(
        "Fakültə, kafedra və ixtisas ağacı",
        "Faculty, department and programme tree",
        "Дерево факультетов, кафедр и специальностей",
        "Fakülte, bölüm ve program ağacı",
    ),
    _t("Fakültələr", "Faculties", "Факультеты", "Fakülteler"),
    _t(
        "Dekanlar, kafedralar, tələbə sayı",
        "Deans, departments, student counts",
        "Деканы, кафедры, число студентов",
        "Dekanlar, bölümler, öğrenci sayısı",
    ),
    _t("Kafedralar", "Departments", "Кафедры", "Bölümler"),
    _t(
        "Müdirlər və müəllim heyəti",
        "Heads and teaching staff",
        "Заведующие и преподаватели",
        "Başkanlar ve öğretim kadrosu",
    ),
    _t("Qruplar", "Groups", "Группы", "Gruplar"),
    _t(
        "Akademik qruplar və tələbələr",
        "Academic groups and students",
        "Академические группы и студенты",
        "Akademik gruplar ve öğrenciler",
    ),
    _t("Üzvlər", "Members", "Участники", "Üyeler"),
    _t(
        "Rol, vəzifə və bölmə ilə üzv reyestri",
        "Member registry with role, position and unit",
        "Реестр участников с ролью, должностью и подразделением",
        "Rol, pozisyon ve birimle üye kaydı",
    ),
    _t("Rollar", "Roles", "Роли", "Roller"),
    _t(
        "Rol kataloqu və icazələr",
        "Role catalogue and permissions",
        "Каталог ролей и разрешения",
        "Rol kataloğu ve izinler",
    ),
    _t("Rolları idarə et", "Manage roles", "Управление ролями", "Rolleri yönet"),
    _t("Rol vermək və geri almaq", "Grant and revoke roles", "Назначение и отзыв ролей", "Rol verme ve geri alma"),
    _t("İcazələr", "Permissions", "Разрешения", "İzinler"),
    _t(
        "Rolların icazə açarlarını redaktə et",
        "Edit the permission keys of roles",
        "Редактировать ключи разрешений ролей",
        "Rollerin izin anahtarlarını düzenle",
    ),
    _t("Audit jurnalı", "Audit log", "Журнал аудита", "Denetim günlüğü"),
    _t(
        "Kim, nə vaxt, nəyi dəyişdi",
        "Who changed what, and when",
        "Кто, когда и что изменил",
        "Kim, ne zaman, neyi değiştirdi",
    ),
    _t("Təşkilat ayarları", "Organisation settings", "Настройки организации", "Kurum ayarları"),
    _t(
        "Əlaqə məlumatı, ünvan və sayt",
        "Contact details, address and website",
        "Контакты, адрес и сайт",
        "İletişim bilgileri, adres ve web sitesi",
    ),
    # Status / kimlik
    _t("Aktiv", "Active", "Активна", "Aktif"),
    _t("Gözləmədə", "Pending", "На рассмотрении", "Beklemede"),
    _t("Dayandırılıb", "Suspended", "Приостановлен", "Askıya alındı"),
    _t(
        "Aktiv təşkilat seçilməyib",
        "No active organisation selected",
        "Активная организация не выбрана",
        "Aktif kurum seçilmedi",
    ),
    _t("Cari dövr", "Current term", "Текущий период", "Mevcut dönem"),
    _t("Növbəti dövr", "Next term", "Следующий период", "Sonraki dönem"),
    _t("Son dövr", "Latest term", "Последний период", "Son dönem"),
    _t(
        "Akademik dövr təyin edilməyib",
        "No academic term set up",
        "Учебный период не задан",
        "Akademik dönem tanımlanmamış",
    ),
    _t("Yaradılıb", "Created", "Создана", "Oluşturuldu"),
    # KPI
    _t("Üzv", "Members", "Участники", "Üye"),
    _t("Tələbə", "Students", "Студенты", "Öğrenci"),
    _t("Müəllim", "Teachers", "Преподаватели", "Öğretmen"),
    _t("Heyət", "Staff", "Сотрудники", "Personel"),
    _t("fərqli şəxs", "distinct people", "уникальных человек", "farklı kişi"),
    _t("sizin əhatənizdə", "within your scope", "в вашей зоне", "kapsamınızda"),
    _t("tələbə olmayan rollar", "non-student roles", "роли, кроме студентов", "öğrenci dışı roller"),
    _t("Fakültə", "Faculties", "Факультеты", "Fakülte"),
    _t("Kafedra", "Departments", "Кафедры", "Bölüm"),
    _t("İxtisas", "Programmes", "Специальности", "Program"),
    _t("Qrup", "Groups", "Группы", "Grup"),
    _t("Sizin əhatəniz üzrə", "Within your scope", "В пределах вашей зоны", "Kapsamınıza göre"),
    _t(
        "Son 30 gündə yeni üzv: %(n)s",
        "New members in the last 30 days: %(n)s",
        "Новых участников за 30 дней: %(n)s",
        "Son 30 günde yeni üye: %(n)s",
    ),
    _t(
        "Dayandırılmış hesab: %(n)s",
        "Suspended accounts: %(n)s",
        "Приостановленных аккаунтов: %(n)s",
        "Askıya alınmış hesap: %(n)s",
    ),
    _t("Əhatəniz təyin edilməyib", "Your scope is not set", "Ваша зона не назначена", "Kapsamınız tanımlanmamış"),
    _t(
        "Rolunuz bölməyə bağlıdır, amma bölmə təyin edilməyib — üzv rəqəmləri göstərilmir.",
        "Your role is tied to a unit, but no unit is assigned — member figures are hidden.",
        "Ваша роль привязана к подразделению, но оно не назначено — данные об участниках скрыты.",
        "Rolünüz bir birime bağlı, ancak birim atanmamış — üye sayıları gösterilmiyor.",
    ),
    _t("Struktur", "Structure", "Структура", "Yapı"),
    _t("Sürətli keçidlər", "Quick links", "Быстрые ссылки", "Hızlı bağlantılar"),
    # Kartlar
    _t("Rol paylanması", "Role distribution", "Распределение ролей", "Rol dağılımı"),
    _t("Digər rollar (%(n)s)", "Other roles (%(n)s)", "Другие роли (%(n)s)", "Diğer roller (%(n)s)"),
    _t(
        "Say — rolu daşıyan fərqli şəxslərdir; bir nəfərin bir neçə rolu ola bilər.",
        "Counts are distinct people holding the role; one person may hold several roles.",
        "Число — это уникальные люди с ролью; у одного человека может быть несколько ролей.",
        "Sayı, rolü taşıyan farklı kişilerdir; bir kişinin birden fazla rolü olabilir.",
    ),
    _t(
        "Hələ aktiv üzvlük yoxdur.",
        "No active memberships yet.",
        "Активных членств пока нет.",
        "Henüz aktif üyelik yok.",
    ),
    _t("Son qoşulanlar", "Recently joined", "Недавно присоединились", "Son katılanlar"),
    _t("Hamısı", "All", "Все", "Tümü"),
    _t(
        "Əhatənizdə hələ üzv yoxdur.",
        "No members in your scope yet.",
        "В вашей зоне пока нет участников.",
        "Kapsamınızda henüz üye yok.",
    ),
    _t("Son dəyişikliklər", "Recent changes", "Последние изменения", "Son değişiklikler"),
    _t("Sistem", "System", "Система", "Sistem (otomatik)"),
    _t(
        "Son dövrdə üzvlük və ya rol dəyişikliyi qeydə alınmayıb.",
        "No membership or role changes recorded recently.",
        "В последнее время изменений членства или ролей не зафиксировано.",
        "Son dönemde üyelik veya rol değişikliği kaydedilmedi.",
    ),
]

_MEMBERS = [
    _t("Hesab", "Account", "Аккаунт", "Hesap"),
    _t("Aktiv hesab", "Active account", "Активный аккаунт", "Aktif hesap"),
    _t("Dayandırılmış hesab", "Suspended account", "Приостановленный аккаунт", "Askıya alınmış hesap"),
    _t("Ad Soyad", "Full name", "ФИО", "Adı Soyadı"),
    _t("Üst bölmə", "Parent units", "Вышестоящие подразделения", "Üst birim"),
    _t("Aktiv", "Active", "Активен", "Aktif"),
    _t(
        "İxrac üçün icazəniz yoxdur.",
        "You are not allowed to export.",
        "У вас нет права на экспорт.",
        "Dışa aktarma izniniz yok.",
    ),
    _t(
        "Üzv reyestri CSV ixracı: %(n)d sətir",
        "Member registry CSV export: %(n)d rows",
        "Экспорт реестра участников в CSV: %(n)d строк",
        "Üye kaydı CSV dışa aktarımı: %(n)d satır",
    ),
    _t(
        "Cari süzgəcə uyğun üzvləri CSV faylı kimi yüklə",
        "Download the members matching the current filters as a CSV file",
        "Скачать участников по текущим фильтрам в CSV",
        "Geçerli filtrelere uyan üyeleri CSV dosyası olarak indir",
    ),
    _t("CSV ixracı", "CSV export", "Экспорт CSV", "CSV dışa aktar"),
    _t("Panel", "Overview", "Панель", "Genel bakış"),
    _t("Struktur üzvləri", "Structure members", "Участники структуры", "Yapı üyeleri"),
]

_ROLES = [
    _t("Xüsusi", "Custom", "Пользовательская", "Özel"),
    _t("səviyyə", "level", "уровень", "seviye"),
    _t("İcazə", "Permissions", "Разрешения", "İzin"),
    _t("%(n)s icazə", "%(n)s permissions", "Разрешений: %(n)s", "%(n)s izin"),
    _t("Üzvlər", "Members", "Участники", "Üyeler"),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    OV: {row["az"]: row for row in _OVERVIEW},
    SB: {"Təşkilat paneli": _t("Təşkilat paneli", "Organisation overview", "Панель организации", "Kurum paneli")},
    MB: {row["az"]: row for row in _MEMBERS},
    RR: {row["az"]: row for row in _ROLES},
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
                flags = ["python-format"] if "%(" in msgid else []
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want, flags=flags))
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
