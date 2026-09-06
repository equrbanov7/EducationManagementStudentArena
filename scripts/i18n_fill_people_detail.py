#!/usr/bin/env python3
"""EMSArena i18n — «Şəxs kartı» drawer-inin (people_detail.js) sətirləri. İdempotent.

QA 2026-09-05 P1-2: kataloqda ada klik açan detal pəncərəsi tam render olundu;
JS mətnləri `_people_directory.html`-dəki JSON blokundan gəlir. 4 dil doldurulur.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir, mövcud girişə toxunmur.
İstifadə:  python scripts/i18n_fill_people_detail.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "accounts.people": {
        "Şəxs kartı": {"en": "Person card", "ru": "Карточка лица", "tr": "Kişi kartı"},
        "Bağla": {"en": "Close", "ru": "Закрыть", "tr": "Kapat"},
    },
    "accounts.people.detail": {
        "Tələbə": {"en": "Student", "ru": "Студент", "tr": "Öğrenci"},
        "Müəllim": {"en": "Teacher", "ru": "Преподаватель", "tr": "Öğretim elemanı"},
        "İstifadəçi adı": {"en": "Username", "ru": "Имя пользователя", "tr": "Kullanıcı adı"},
        "E-poçt": {"en": "Email", "ru": "Эл. почта", "tr": "E-posta"},
        "Telefon": {"en": "Phone", "ru": "Телефон", "tr": "Telefon numarası"},
        "FİN": {"en": "FIN", "ru": "FIN", "tr": "FIN kodu"},
        "Cins": {"en": "Gender", "ru": "Пол", "tr": "Cinsiyet"},
        "Doğum tarixi / yaş": {
            "en": "Date of birth / age",
            "ru": "Дата рождения / возраст",
            "tr": "Doğum tarihi / yaş",
        },
        "yaş": {"en": "y.o.", "ru": "лет", "tr": "yaşında"},
        "Son giriş": {"en": "Last sign-in", "ru": "Последний вход", "tr": "Son oturum açma"},
        "Heç vaxt": {"en": "Never", "ru": "Никогда", "tr": "Hiç"},
        "Qeydiyyat": {"en": "Registered", "ru": "Регистрация", "tr": "Kayıt"},
        "Üzvlüklər": {"en": "Memberships", "ru": "Членства", "tr": "Üyelikler"},
        "Aktiv üzvlük yoxdur": {"en": "No active membership", "ru": "Нет активного членства", "tr": "Aktif üyelik yok"},
        "Akademik qeydlər": {"en": "Academic records", "ru": "Академические записи", "tr": "Akademik kayıtlar"},
        "Akademik qeyd yoxdur": {
            "en": "No academic record",
            "ru": "Нет академических записей",
            "tr": "Akademik kayıt yok",
        },
        "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup"},
        "Qəbul ili": {"en": "Admission year", "ru": "Год поступления", "tr": "Kabul yılı"},
        "Tədris": {"en": "Teaching", "ru": "Преподавание", "tr": "Öğretim"},
        "Cari dövrdə açılış yoxdur": {
            "en": "No course offering in the current period",
            "ru": "Нет открытых курсов в текущем периоде",
            "tr": "Mevcut dönemde ders açılışı yok",
        },
        "Profil səhifəsi": {"en": "Profile page", "ru": "Страница профиля", "tr": "Profil sayfası"},
        "Yüklənir…": {"en": "Loading…", "ru": "Загрузка…", "tr": "Yükleniyor…"},
        "Məlumat yüklənmədi.": {
            "en": "Could not load the data.",
            "ru": "Не удалось загрузить данные.",
            "tr": "Veri yüklenemedi.",
        },
        "Kişi": {"en": "Male", "ru": "Мужской", "tr": "Erkek"},
        "Qadın": {"en": "Female", "ru": "Женский", "tr": "Kadın"},
        "Göstərilməyib": {"en": "Not specified", "ru": "Не указано", "tr": "Belirtilmemiş"},
        "Aktiv": {"en": "Active", "ru": "Активен", "tr": "Aktif"},
        "Bloklanıb": {"en": "Blocked", "ru": "Заблокирован", "tr": "Engellendi"},
        "Passiv": {"en": "Inactive", "ru": "Неактивен", "tr": "Pasif"},
        "Arxiv": {"en": "Archived", "ru": "В архиве", "tr": "Arşiv"},
        "Gözləmədə": {"en": "Pending", "ru": "В ожидании", "tr": "Beklemede"},
        "Oxuyur": {"en": "Enrolled", "ru": "Обучается", "tr": "Okuyor"},
        "Akademik məzuniyyət": {"en": "Academic leave", "ru": "Академический отпуск", "tr": "Akademik izin"},
        "Xaric edilib": {"en": "Expelled", "ru": "Отчислен", "tr": "İlişiği kesildi"},
        "Məzun": {"en": "Graduated", "ru": "Выпускник", "tr": "Mezun"},
        "Köçürülüb": {"en": "Transferred", "ru": "Переведён", "tr": "Nakil"},
        "Dayandırılıb": {"en": "Suspended", "ru": "Приостановлен", "tr": "Askıya alındı"},
        "Hesabı dayandır": {"en": "Suspend account", "ru": "Приостановить учётную запись", "tr": "Hesabı askıya al"},
        "Hesabı bərpa et": {"en": "Restore account", "ru": "Восстановить учётную запись", "tr": "Hesabı geri yükle"},
        "Müəllim statusu ver": {
            "en": "Grant teacher status",
            "ru": "Выдать статус преподавателя",
            "tr": "Öğretim elemanı statüsü ver",
        },
        "Müəllim statusunu çıxar": {
            "en": "Revoke teacher status",
            "ru": "Снять статус преподавателя",
            "tr": "Öğretim elemanı statüsünü kaldır",
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
