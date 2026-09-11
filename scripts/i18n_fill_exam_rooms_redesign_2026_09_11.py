#!/usr/bin/env python3
"""EMSArena i18n — «İmtahan zalları» redizaynı (kabinet, 2026-09-11), 4 dil.

Sahib tələbi: «İmtahan zalları səhifəsini yenidən, daha təkmil formada redizayn
et; 2 ədəd title var — onlar da olmasın.» Bölmə `ems_ui` dilinə keçirildi:
KPI sırası, avto filtr (ad/kod, status, bina), zallar cədvəli (sıralama +
səhifələmə), zalın kompüterləri və əməlləri çekmecədə.

Yeni mətnlər:
* `accounts.superadmin_exam_rooms` — KPI etiketləri/qeydləri, filtr, sütun
  başlıqları, boş vəziyyətlər, dialoq alt başlıqları və ipucları, «Ətraflı»;
* `ui.status` — `exam_room` / `exam_room_computer` status ailələri
  («Deaktiv», «Söndürülüb»; «Aktiv» artıq var).

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir və idempotentdir. TR qarşılıqları QƏSDƏN AZ mənbədən fərqlidir —
i18n qapısı `msgstr == msgid` sətrini «tərcümə olunmamış» sayır.

İstifadə:  python scripts/i18n_fill_exam_rooms_redesign_2026_09_11.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

SAR = "accounts.superadmin_exam_rooms"

ENTRIES = {
    SAR: {
        "%(ip)d IP ilə": {"en": "%(ip)d with IP", "ru": "с IP: %(ip)d", "tr": "%(ip)d IP'li"},
        "%(ip)d IP ilə · plan %(plan)d": {
            "en": "%(ip)d with IP · plan %(plan)d",
            "ru": "с IP: %(ip)d · план %(plan)d",
            "tr": "%(ip)d IP'li · plan %(plan)d",
        },
        "%(n)d deaktiv": {"en": "%(n)d inactive", "ru": "неактивных: %(n)d", "tr": "%(n)d devre dışı"},
        "Aktiv zal": {"en": "Active rooms", "ru": "Активные залы", "tr": "Etkin salon"},
        "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama"},
        "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.": {
            "en": "Change the search or press “Reset” to return to the full list.",
            "ru": "Измените поиск или нажмите «Сбросить», чтобы вернуться к полному списку.",
            "tr": "Aramayı değiştirin veya «Sıfırla» ile tam listeye dönün.",
        },
        "Bu təşkilatda hələ zal yoxdur": {
            "en": "This organization has no rooms yet",
            "ru": "В этой организации пока нет залов",
            "tr": "Bu kuruluşta henüz salon yok",
        },
        "Canlı oturum": {"en": "Live sessions", "ru": "Идущие сеансы", "tr": "Süren oturumlar"},
        "Filtrə uyğun zal yoxdur": {
            "en": "No rooms match the filter",
            "ru": "Нет залов, соответствующих фильтру",
            "tr": "Filtreye uyan salon yok",
        },
        "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
        "Hələ kompüter əlavə edilməyib": {
            "en": "No computers added yet",
            "ru": "Компьютеры ещё не добавлены",
            "tr": "Henüz bilgisayar eklenmedi",
        },
        "Kod təşkilat daxilində unikaldır; tutum və planlaşdırılan kompüter sayı hesabatlarda görünür.": {
            "en": "The code is unique within the organization; capacity and planned computer count appear in reports.",
            "ru": "Код уникален в пределах организации; вместимость и плановое число компьютеров видны в отчётах.",
            "tr": "Kod kuruluş içinde benzersizdir; kapasite ve planlanan bilgisayar sayısı raporlarda görünür.",
        },
        "Kompüter": {"en": "Computers", "ru": "Компьютеры", "tr": "Bilgisayar"},
        "Kompüterlər": {"en": "Computers", "ru": "Компьютеры", "tr": "Bilgisayarlar"},
        "Nəticə: %(n)d zal": {
            "en": "Result: %(n)d rooms",
            "ru": "Результат: залов — %(n)d",
            "tr": "Sonuç: %(n)d salon",
        },
        "Nəzarətçi": {"en": "Invigilators", "ru": "Наблюдатели", "tr": "Gözetmen"},
        "Qeydiyyatdakı say plandan fərqlənəndə sətirdə xəbərdarlıq görünür.": {
            "en": "A warning appears on the row when the registered count differs from the plan.",
            "ru": "Если число зарегистрированных отличается от плана, в строке появляется предупреждение.",
            "tr": "Kayıtlı sayı plandan farklıysa satırda uyarı görünür.",
        },
        "Söndürülmüş kompüterin IP-si giriş yoxlamasında nəzərə alınmır.": {
            "en": "The IP of a disabled computer is ignored by the entry check.",
            "ru": "IP отключённого компьютера не учитывается при проверке входа.",
            "tr": "Kapatılmış bilgisayarın IP'si giriş denetiminde dikkate alınmaz.",
        },
        "Zal": {"en": "Room", "ru": "Зал", "tr": "Salon"},
        "Zal adı və ya kodu": {"en": "Room name or code", "ru": "Название или код зала", "tr": "Salon adı veya kodu"},
        "aktiv zallarda %(n)d": {
            "en": "%(n)d in active rooms",
            "ru": "в активных залах: %(n)d",
            "tr": "etkin salonlarda %(n)d",
        },
        "hamısı aktivdir": {"en": "all active", "ru": "все активны", "tr": "tümü etkin"},
        "hazırda imtahan gedən zal": {
            "en": "rooms with an exam in progress",
            "ru": "залы, где сейчас идёт экзамен",
            "tr": "şu anda sınav yapılan salon",
        },
        "«Kompüter əlavə et» ilə tək-tək, «Toplu əlavə» ilə MAC siyahısından əlavə edin.": {
            "en": "Add one at a time with “Add computer” or from a MAC list with “Bulk add”.",
            "ru": "Добавляйте по одному через «Добавить компьютер» или списком MAC через «Массовое добавление».",
            "tr": "«Bilgisayar ekle» ile tek tek, «Toplu ekle» ile MAC listesinden ekleyin.",
        },
        "«Yeni zal» ilə ilk zalı yaradın; kompüterlər zalın çekmecəsindən əlavə olunur.": {
            "en": "Create the first room with “New room”; computers are added from the room drawer.",
            "ru": "Создайте первый зал через «Новый зал»; компьютеры добавляются из панели зала.",
            "tr": "«Yeni salon» ile ilk salonu oluşturun; bilgisayarlar salon çekmecesinden eklenir.",
        },
        "«%(name)s» zalını redaktə et": {
            "en": "Edit room “%(name)s”",
            "ru": "Редактировать зал «%(name)s»",
            "tr": "«%(name)s» salonunu düzenle",
        },
        "Ümumi yer": {"en": "Total seats", "ru": "Всего мест", "tr": "Toplam yer"},
        "İmtahan mərkəzinə giriş bu IP üzərindən yoxlanılır.": {
            "en": "Entry to the exam center is verified by this IP.",
            "ru": "Вход в экзаменационный центр проверяется по этому IP.",
            "tr": "Sınav merkezine giriş bu IP üzerinden denetlenir.",
        },
        "Əməllər": {"en": "Actions", "ru": "Действия", "tr": "İşlemler"},
        "Ətraflı": {"en": "Details", "ru": "Подробнее", "tr": "Ayrıntılar"},
    },
    "ui.status": {
        "Deaktiv": {"en": "Inactive", "ru": "Неактивен", "tr": "Devre dışı"},
        "Söndürülüb": {"en": "Disabled", "ru": "Отключён", "tr": "Kapalı"},
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
