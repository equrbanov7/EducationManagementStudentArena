#!/usr/bin/env python3
"""EMSArena i18n — «Müəllimlər» / «Tələbələr» kataloqunun sətirləri. İdempotent.

Yeni bölmələrin (people-teachers / people-students) bütün UI mətnləri, filtr
etiketləri, cədvəl başlıqları və yeni `people.*` icazə etiketləri 4 dildə
doldurulur.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silə bilir) — skript
yalnız ƏLAVƏ edir və mövcud girişə toxunmur.

İstifadə:  python scripts/i18n_fill_people_directory.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "organizations.permission.label": {
        "Müəllim kataloquna baxış": {
            "en": "View the teacher directory",
            "ru": "Просмотр каталога преподавателей",
            "tr": "Öğretim elemanı kataloğunu görüntüleme",
        },
        "Tələbə kataloquna baxış": {
            "en": "View the student directory",
            "ru": "Просмотр каталога студентов",
            "tr": "Öğrenci kataloğunu görüntüleme",
        },
        "Kataloqda əlaqə məlumatını görmək": {
            "en": "See contact details in the directory",
            "ru": "Видеть контактные данные в каталоге",
            "tr": "Katalogda iletişim bilgilerini görme",
        },
        "Kataloqda cins və yaş məlumatını görmək": {
            "en": "See gender and age in the directory",
            "ru": "Видеть пол и возраст в каталоге",
            "tr": "Katalogda cinsiyet ve yaş bilgisini görme",
        },
        "Kataloqdan hesabı dayandırmaq / bərpa etmək": {
            "en": "Suspend / restore an account from the directory",
            "ru": "Приостановить / восстановить учётную запись из каталога",
            "tr": "Katalogdan hesabı askıya alma / geri yükleme",
        },
        "Müəllim statusunu vermək / çıxarmaq": {
            "en": "Grant / revoke teacher status",
            "ru": "Назначить / снять статус преподавателя",
            "tr": "Öğretim elemanı statüsü verme / kaldırma",
        },
    },
    "profile.sidebar": {
        "Müəllimlər": {"en": "Teachers", "ru": "Преподаватели", "tr": "Öğretim elemanları"},
        "Tələbələr": {"en": "Students", "ru": "Студенты", "tr": "Öğrenciler"},
    },
    "accounts.people": {
        # sıralama
        "Ad üzrə (A→Z)": {"en": "By name (A→Z)", "ru": "По имени (А→Я)", "tr": "Ada göre (A→Z)"},
        "Ad üzrə (Z→A)": {"en": "By name (Z→A)", "ru": "По имени (Я→А)", "tr": "Ada göre (Z→A)"},
        "Struktur üzrə": {"en": "By structure", "ru": "По структуре", "tr": "Yapıya göre"},
        "Qrup üzrə": {"en": "By group", "ru": "По группе", "tr": "Gruba göre"},
        "Qəbul ili üzrə": {"en": "By admission year", "ru": "По году приёма", "tr": "Kayıt yılına göre"},
        "Ən yeni": {"en": "Newest", "ru": "Самые новые", "tr": "En yeni"},
        "Ən köhnə": {"en": "Oldest", "ru": "Самые старые", "tr": "En eski"},
        # status
        "Bütün statuslar": {"en": "All statuses", "ru": "Все статусы", "tr": "Tüm durumlar"},
        "Aktiv": {"en": "Active", "ru": "Активен", "tr": "Aktif"},
        "Dayandırılıb": {"en": "Suspended", "ru": "Приостановлен", "tr": "Askıya alındı"},
        "Arxiv (məzun/xaric)": {
            "en": "Archived (graduate/expelled)",
            "ru": "Архив (выпускник/отчислен)",
            "tr": "Arşiv (mezun/ilişiği kesilmiş)",
        },
        "Silinib": {"en": "Deleted", "ru": "Удалён", "tr": "Silindi"},
        # demoqrafiya
        "Kişi": {"en": "Male", "ru": "Мужской", "tr": "Erkek"},
        "Qadın": {"en": "Female", "ru": "Женский", "tr": "Kadın"},
        "Cinsi göstərilməyib": {"en": "Gender not specified", "ru": "Пол не указан", "tr": "Cinsiyet belirtilmemiş"},
        "Doğum tarixi göstərilməyib": {
            "en": "Date of birth not specified",
            "ru": "Дата рождения не указана",
            "tr": "Doğum tarihi belirtilmemiş",
        },
        "Cins": {"en": "Gender", "ru": "Пол", "tr": "Cinsiyet"},
        "Cins / yaş": {"en": "Gender / age", "ru": "Пол / возраст", "tr": "Cinsiyet / yaş"},
        "Yaş": {"en": "Age", "ru": "Возраст", "tr": "Yaş"},
        "Minimum yaş": {"en": "Minimum age", "ru": "Минимальный возраст", "tr": "En küçük yaş"},
        "Maksimum yaş": {"en": "Maximum age", "ru": "Максимальный возраст", "tr": "En büyük yaş"},
        "min": {"en": "min", "ru": "мин", "tr": "min"},
        "maks": {"en": "max", "ru": "макс", "tr": "maks"},
        # filtr çərçivəsi
        "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama"},
        "ad, soyad, ata adı, istifadəçi adı və ya FİN": {
            "en": "first name, surname, patronymic, username or PIN",
            "ru": "имя, фамилия, отчество, логин или ПИН",
            "tr": "ad, soyad, baba adı, kullanıcı adı veya kimlik no",
        },
        "Fakültə": {"en": "Faculty", "ru": "Факультет", "tr": "Fakülte"},
        "Kafedra": {"en": "Department", "ru": "Кафедра", "tr": "Bölüm"},
        "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup"},
        "İxtisas": {"en": "Specialty", "ru": "Специальность", "tr": "Bölüm programı"},
        "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
        "Dərs dediyi fənn": {"en": "Subject taught", "ru": "Преподаваемый предмет", "tr": "Verdiği ders"},
        "Keçdiyi fənn": {"en": "Subject taken", "ru": "Изучаемый предмет", "tr": "Aldığı ders"},
        "Tədris ili": {"en": "Academic year", "ru": "Учебный год", "tr": "Öğretim yılı"},
        "Semestr": {"en": "Semester", "ru": "Семестр", "tr": "Yarıyıl"},
        "Status": {"en": "Status", "ru": "Статус", "tr": "Durum"},
        "Sıralama": {"en": "Sorting", "ru": "Сортировка", "tr": "Sıralama"},
        "Filtrləri sıfırla": {"en": "Reset filters", "ru": "Сбросить фильтры", "tr": "Filtreleri sıfırla"},
        # cədvəl
        "Şəxs": {"en": "Person", "ru": "Человек", "tr": "Kişi"},
        "Vəzifə / rol": {"en": "Position / role", "ru": "Должность / роль", "tr": "Görev / rol"},
        "Əlaqə": {"en": "Contact", "ru": "Контакты", "tr": "İletişim"},
        "Əməllər": {"en": "Actions", "ru": "Действия", "tr": "İşlemler"},
        "Müəllim kataloqu": {
            "en": "Teacher directory",
            "ru": "Каталог преподавателей",
            "tr": "Öğretim elemanı kataloğu",
        },
        "Tələbə kataloqu": {"en": "Student directory", "ru": "Каталог студентов", "tr": "Öğrenci kataloğu"},
        "Nəticə tapılmadı.": {"en": "No results found.", "ru": "Ничего не найдено.", "tr": "Sonuç bulunamadı."},
        "Səhifələmə": {"en": "Pagination", "ru": "Постраничная навигация", "tr": "Sayfalama"},
        "Əvvəlki": {"en": "Previous", "ru": "Предыдущая", "tr": "Önceki"},
        "Sonrakı": {"en": "Next", "ru": "Следующая", "tr": "Sonraki"},
        "Şəxs kartı": {"en": "Person card", "ru": "Карточка человека", "tr": "Kişi kartı"},
        "Bağla": {"en": "Close", "ru": "Закрыть", "tr": "Kapat"},
        "Yüklənir…": {"en": "Loading…", "ru": "Загрузка…", "tr": "Yükleniyor…"},
        # çərçivə mətnləri
        "Görünüş sahənizdəki müəllimlər. Hər kəs yalnız öz strukturunun altını görür.": {
            "en": "Teachers within your visibility scope. Everyone sees only their own structure.",
            "ru": "Преподаватели в зоне вашей видимости. Каждый видит только свою структуру.",
            "tr": "Görüş alanınızdaki öğretim elemanları. Herkes yalnızca kendi yapısını görür.",
        },
        "Görünüş sahənizdəki tələbələr. Hər kəs yalnız öz strukturunun altını görür.": {
            "en": "Students within your visibility scope. Everyone sees only their own structure.",
            "ru": "Студенты в зоне вашей видимости. Каждый видит только свою структуру.",
            "tr": "Görüş alanınızdaki öğrenciler. Herkes yalnızca kendi yapısını görür.",
        },
        "Bu bölmədəki səlahiyyətləriniz": {
            "en": "Your permissions in this section",
            "ru": "Ваши права в этом разделе",
            "tr": "Bu bölümdeki yetkileriniz",
        },
        "Bu bölmə üçün icazəniz yoxdur.": {
            "en": "You do not have permission for this section.",
            "ru": "У вас нет прав доступа к этому разделу.",
            "tr": "Bu bölüm için yetkiniz yok.",
        },
    },
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
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
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
