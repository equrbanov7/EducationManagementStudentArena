#!/usr/bin/env python3
"""EMSArena i18n — imtahan zalları (superadmin zal/kompüter idarəsi). İdempotent.

2026-07 redesign: bölmə template-i (modallar, cədvəl, idarəçilər), view
mesajları, room_admin servis xətaları və final_center forma sətirləri
kataloqlarda yox idi — 4 dildə doldurulur.

İstifadə:  python scripts/i18n_fill_exam_rooms.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

SAR_CTX = "accounts.superadmin_exam_rooms"

ENTRIES = {
    SAR_CTX: {
        "%(n)s kompüter əlavə edildi.": {
            "en": "%(n)s computers added.",
            "ru": "Добавлено компьютеров: %(n)s.",
            "tr": "%(n)s bilgisayar eklendi.",
        },
        "%(u)s zal idarəçiliyindən çıxarıldı.": {
            "en": "%(u)s was removed from room managers.",
            "ru": "%(u)s исключён из управляющих залами.",
            "tr": "%(u)s salon yöneticiliğinden çıkarıldı.",
        },
        "%(u)s zal idarəçisi təyin edildi.": {
            "en": "%(u)s was assigned as a room manager.",
            "ru": "%(u)s назначен управляющим залами.",
            "tr": "%(u)s salon yöneticisi olarak atandı.",
        },
        "Ad": {"en": "Name", "ru": "Название", "tr": "Ad"},
        "Aktiv": {"en": "Active", "ru": "Активен", "tr": "Etkin"},
        "Aktiv et": {"en": "Activate", "ru": "Активировать", "tr": "Etkinleştir"},
        "Aktiv təşkilat tapılmadı. Zal yaratmaq üçün əvvəlcə təşkilat seçin.": {
            "en": "No active organization found. Select an organization before creating a room.",
            "ru": "Активная организация не найдена. Сначала выберите организацию.",
            "tr": "Etkin kuruluş bulunamadı. Salon oluşturmadan önce kuruluş seçin.",
        },
        "Bağla": {"en": "Close", "ru": "Закрыть", "tr": "Kapat"},
        "Bina": {"en": "Building", "ru": "Корпус", "tr": "Bina"},
        "Bu bölmə yalnız zal idarəçiləri üçündür.": {
            "en": "This section is only for room managers.",
            "ru": "Этот раздел доступен только управляющим залами.",
            "tr": "Bu bölüm yalnızca salon yöneticileri içindir.",
        },
        "Bu istifadəçilər superadmin olmadan da öz təşkilatlarının zallarını idarə edə bilər.": {
            "en": "These users can manage their organization's rooms without being a superadmin.",
            "ru": "Эти пользователи могут управлять залами своей организации без прав суперадмина.",
            "tr": "Bu kullanıcılar süper yönetici olmadan kendi kuruluşlarının salonlarını yönetebilir.",
        },
        "Bu təşkilatda hələ zal yoxdur — «Yeni zal» ilə başlayın.": {
            "en": "This organization has no rooms yet — start with “New room”.",
            "ru": "В этой организации пока нет залов — начните с «Новый зал».",
            "tr": "Bu kuruluşta henüz salon yok — «Yeni salon» ile başlayın.",
        },
        "Deaktiv": {"en": "Inactive", "ru": "Неактивен", "tr": "Devre dışı"},
        "Deaktiv et": {"en": "Deactivate", "ru": "Деактивировать", "tr": "Devre dışı bırak"},
        "Form məlumatları düzgün deyil.": {
            "en": "The form data is invalid.",
            "ru": "Данные формы недействительны.",
            "tr": "Form verileri geçersiz.",
        },
        "Geri al": {"en": "Revoke", "ru": "Отозвать", "tr": "Geri al"},
        "Hələ kompüter əlavə edilməyib — «Kompüter əlavə et» ilə başlayın.": {
            "en": "No computers added yet — start with “Add computer”.",
            "ru": "Компьютеры ещё не добавлены — начните с «Добавить компьютер».",
            "tr": "Henüz bilgisayar eklenmedi — «Bilgisayar ekle» ile başlayın.",
        },
        "Hələ təyin olunmuş idarəçi yoxdur.": {
            "en": "No managers assigned yet.",
            "ru": "Управляющие пока не назначены.",
            "tr": "Henüz atanmış yönetici yok.",
        },
        "Hər sətir: Ad, MAC[, IP][, Yer]": {
            "en": "Each line: Name, MAC[, IP][, Seat]",
            "ru": "Каждая строка: Название, MAC[, IP][, Место]",
            "tr": "Her satır: Ad, MAC[, IP][, Koltuk]",
        },
        "IP ilə": {"en": "with IP", "ru": "с IP", "tr": "IP ile"},
        "Kod": {"en": "Code", "ru": "Код", "tr": "Kod"},
        "Kompüter silindi.": {"en": "Computer deleted.", "ru": "Компьютер удалён.", "tr": "Bilgisayar silindi."},
        "Kompüter yeniləndi.": {
            "en": "Computer updated.",
            "ru": "Компьютер обновлён.",
            "tr": "Bilgisayar güncellendi.",
        },
        "Kompüter əlavə edildi.": {"en": "Computer added.", "ru": "Компьютер добавлен.", "tr": "Bilgisayar eklendi."},
        "Kompüter əlavə et": {"en": "Add computer", "ru": "Добавить компьютер", "tr": "Bilgisayar ekle"},
        "Kompüteri redaktə et": {
            "en": "Edit computer",
            "ru": "Редактировать компьютер",
            "tr": "Bilgisayarı düzenle",
        },
        "MAC identifikasiya üçün saxlanır; girişə icazə IP üzərindən verilir (brauzer MAC-ı serverə göndərə bilmir).": {
            "en": "The MAC is stored for identification; access is enforced by IP (browsers cannot send the MAC to the server).",
            "ru": "MAC хранится для идентификации; доступ контролируется по IP (браузер не может передать MAC серверу).",
            "tr": "MAC kimlik için saklanır; erişim izni IP üzerinden verilir (tarayıcı MAC'i sunucuya gönderemez).",
        },
        "MAC-ı kopyala": {"en": "Copy MAC", "ru": "Скопировать MAC", "tr": "MAC'i kopyala"},
        "Mərtəbə": {"en": "Floor", "ru": "Этаж", "tr": "Kat"},
        "Naməlum əməliyyat.": {"en": "Unknown action.", "ru": "Неизвестное действие.", "tr": "Bilinmeyen işlem."},
        "Planlaşdırılan kompüter": {
            "en": "Planned computers",
            "ru": "Планируемое число компьютеров",
            "tr": "Planlanan bilgisayar",
        },
        "Qeyd": {"en": "Notes", "ru": "Примечание", "tr": "Not"},
        "Qeydiyyatdan keçən kompüter sayı planla üst-üstə düşmür": {
            "en": "The number of registered computers does not match the plan",
            "ru": "Число зарегистрированных компьютеров не совпадает с планом",
            "tr": "Kayıtlı bilgisayar sayısı planla eşleşmiyor",
        },
        "Redaktə et": {"en": "Edit", "ru": "Редактировать", "tr": "Düzenle"},
        "Sil": {"en": "Delete", "ru": "Удалить", "tr": "Sil"},
        "Status": {"en": "Status", "ru": "Статус", "tr": "Durum"},
        "Söndürülüb": {"en": "Disabled", "ru": "Отключён", "tr": "Kapalı"},
        "Toplu əlavə": {"en": "Bulk add", "ru": "Массовое добавление", "tr": "Toplu ekle"},
        "Toplu əlavə (MAC siyahısı)": {
            "en": "Bulk add (MAC list)",
            "ru": "Массовое добавление (список MAC)",
            "tr": "Toplu ekleme (MAC listesi)",
        },
        "Toplu əlavə et": {"en": "Add in bulk", "ru": "Добавить списком", "tr": "Toplu ekle"},
        "Tutum (yer)": {"en": "Capacity (seats)", "ru": "Вместимость (мест)", "tr": "Kapasite (koltuk)"},
        "Təşkilat": {"en": "Organization", "ru": "Организация", "tr": "Kuruluş"},
        "Təşkilat konteksti tapılmadı.": {
            "en": "No organization context found.",
            "ru": "Контекст организации не найден.",
            "tr": "Kuruluş bağlamı bulunamadı.",
        },
        "Uğursuz sətirlər atlanır və səbəbi mesajla bildirilir (qismən uğur).": {
            "en": "Failed lines are skipped and the reason is reported (partial success).",
            "ru": "Неудачные строки пропускаются, причина сообщается (частичный успех).",
            "tr": "Başarısız satırlar atlanır ve nedeni mesajla bildirilir (kısmi başarı).",
        },
        "Yadda saxla": {"en": "Save", "ru": "Сохранить", "tr": "Kaydet"},
        "Yeni zal": {"en": "New room", "ru": "Новый зал", "tr": "Yeni salon"},
        "Yeni zal yarat": {"en": "Create a new room", "ru": "Создать новый зал", "tr": "Yeni salon oluştur"},
        "Yer": {"en": "Seat", "ru": "Место", "tr": "Koltuk"},
        "Yer nömrəsi": {"en": "Seat number", "ru": "Номер места", "tr": "Koltuk numarası"},
        "Zal idarəçiləri": {"en": "Room managers", "ru": "Управляющие залами", "tr": "Salon yöneticileri"},
        "Zal statusu dəyişdirildi.": {
            "en": "Room status changed.",
            "ru": "Статус зала изменён.",
            "tr": "Salon durumu değiştirildi.",
        },
        "Zal yaradıldı.": {"en": "Room created.", "ru": "Зал создан.", "tr": "Salon oluşturuldu."},
        "Zal yeniləndi.": {"en": "Room updated.", "ru": "Зал обновлён.", "tr": "Salon güncellendi."},
        "Zalları, kompüterləri və MAC/IP qeydlərini idarə edin. Bu bölmə yalnız superadmin (və ya təyin olunmuş zal idarəçisi) üçündür.": {
            "en": "Manage rooms, computers and MAC/IP records. This section is only for superadmins (or assigned room managers).",
            "ru": "Управляйте залами, компьютерами и записями MAC/IP. Раздел доступен только суперадмину (или назначенному управляющему).",
            "tr": "Salonları, bilgisayarları ve MAC/IP kayıtlarını yönetin. Bu bölüm yalnızca süper yönetici (veya atanmış salon yöneticisi) içindir.",
        },
        "Zalı redaktə et": {"en": "Edit room", "ru": "Редактировать зал", "tr": "Salonu düzenle"},
        "Zalı sil": {"en": "Delete room", "ru": "Удалить зал", "tr": "Salonu sil"},
        "Zalı yarat": {"en": "Create room", "ru": "Создать зал", "tr": "Salonu oluştur"},
        "canlı": {"en": "live", "ru": "идёт", "tr": "canlı"},
        "kompüter": {"en": "computers", "ru": "комп.", "tr": "bilgisayar"},
        "nəzarətçi": {"en": "invigilators", "ru": "наблюд.", "tr": "gözetmen"},
        "plan:": {"en": "plan:", "ru": "план:", "tr": "plan:"},
        "yer": {"en": "seats", "ru": "мест", "tr": "koltuk"},
        "«%(label)s» (%(mac)s) silinsin?": {
            "en": "Delete “%(label)s” (%(mac)s)?",
            "ru": "Удалить «%(label)s» (%(mac)s)?",
            "tr": "«%(label)s» (%(mac)s) silinsin mi?",
        },
        "«%(label)s» kompüterini redaktə et": {
            "en": "Edit computer “%(label)s”",
            "ru": "Редактировать компьютер «%(label)s»",
            "tr": "«%(label)s» bilgisayarını düzenle",
        },
        "«%(label)s» kompüterini sil": {
            "en": "Delete computer “%(label)s”",
            "ru": "Удалить компьютер «%(label)s»",
            "tr": "«%(label)s» bilgisayarını sil",
        },
        "«%(name)s» zalı və %(count_c)s kompüter qeydi həmişəlik silinəcək. Davam edilsin?": {
            "en": "Room “%(name)s” and %(count_c)s computer records will be permanently deleted. Continue?",
            "ru": "Зал «%(name)s» и записи компьютеров (%(count_c)s) будут удалены безвозвратно. Продолжить?",
            "tr": "«%(name)s» salonu ve %(count_c)s bilgisayar kaydı kalıcı olarak silinecek. Devam edilsin mi?",
        },
        "«%(room)s» zalı silindi.": {
            "en": "Room “%(room)s” deleted.",
            "ru": "Зал «%(room)s» удалён.",
            "tr": "«%(room)s» salonu silindi.",
        },
        "İcazə geri alınsın?": {
            "en": "Revoke this permission?",
            "ru": "Отозвать это разрешение?",
            "tr": "Bu izin geri alınsın mı?",
        },
        "İcazə vermək yalnız superadminə məxsusdur.": {
            "en": "Only a superadmin can grant permissions.",
            "ru": "Выдавать разрешения может только суперадмин.",
            "tr": "İzin vermek yalnızca süper yöneticiye aittir.",
        },
        "İdarəçi təyin et": {"en": "Assign manager", "ru": "Назначить управляющего", "tr": "Yönetici ata"},
        "İmtahan zalları": {"en": "Exam rooms", "ru": "Экзаменационные залы", "tr": "Sınav salonları"},
        "İmtina": {"en": "Cancel", "ru": "Отмена", "tr": "Vazgeç"},
        "İstifadəçi adı və ya email": {
            "en": "Username or email",
            "ru": "Имя пользователя или email",
            "tr": "Kullanıcı adı veya e-posta",
        },
        "İstifadəçi göstərilməyib.": {
            "en": "No user specified.",
            "ru": "Пользователь не указан.",
            "tr": "Kullanıcı belirtilmedi.",
        },
        "İstifadəçi profili yoxdur.": {
            "en": "The user has no profile.",
            "ru": "У пользователя нет профиля.",
            "tr": "Kullanıcının profili yok.",
        },
        "İstifadəçi tapılmadı: %(u)s": {
            "en": "User not found: %(u)s",
            "ru": "Пользователь не найден: %(u)s",
            "tr": "Kullanıcı bulunamadı: %(u)s",
        },
        "Əlavə ediləcək sətir tapılmadı.": {
            "en": "No lines to add were found.",
            "ru": "Строк для добавления не найдено.",
            "tr": "Eklenecek satır bulunamadı.",
        },
        "Əlavə et": {"en": "Add", "ru": "Добавить", "tr": "Ekle"},
    },
    "exams.final_center.room_admin": {
        "Bu MAC artıq bu zalda qeydlidir: %(mac)s": {
            "en": "This MAC is already registered in this room: %(mac)s",
            "ru": "Этот MAC уже зарегистрирован в этом зале: %(mac)s",
            "tr": "Bu MAC bu salonda zaten kayıtlı: %(mac)s",
        },
        "Bu MAC artıq «%(room)s» zalında qeydlidir (%(label)s). Kompüteri əvvəlcə oradan silin və ya redaktə edin.": {
            "en": "This MAC is already registered in room “%(room)s” (%(label)s). Delete or edit that computer there first.",
            "ru": "Этот MAC уже зарегистрирован в зале «%(room)s» (%(label)s). Сначала удалите или отредактируйте его там.",
            "tr": "Bu MAC zaten «%(room)s» salonunda kayıtlı (%(label)s). Önce bilgisayarı oradan silin veya düzenleyin.",
        },
        "Bu adla kompüter artıq var: %(label)s": {
            "en": "A computer with this name already exists: %(label)s",
            "ru": "Компьютер с таким названием уже существует: %(label)s",
            "tr": "Bu adla bilgisayar zaten var: %(label)s",
        },
        "Bu yer nömrəsi artıq tutulub: %(seat)s": {
            "en": "This seat number is already taken: %(seat)s",
            "ru": "Этот номер места уже занят: %(seat)s",
            "tr": "Bu koltuk numarası zaten dolu: %(seat)s",
        },
        "IP ünvanı düzgün deyil: %(ip)s": {
            "en": "Invalid IP address: %(ip)s",
            "ru": "Недопустимый IP-адрес: %(ip)s",
            "tr": "IP adresi geçersiz: %(ip)s",
        },
        "Kompüter adı boş ola bilməz.": {
            "en": "Computer name cannot be empty.",
            "ru": "Название компьютера не может быть пустым.",
            "tr": "Bilgisayar adı boş olamaz.",
        },
        "MAC ünvanı düzgün deyil: %(mac)s": {
            "en": "Invalid MAC address: %(mac)s",
            "ru": "Недопустимый MAC-адрес: %(mac)s",
            "tr": "MAC adresi geçersiz: %(mac)s",
        },
        "Sətir %(n)s: %(err)s": {
            "en": "Line %(n)s: %(err)s",
            "ru": "Строка %(n)s: %(err)s",
            "tr": "Satır %(n)s: %(err)s",
        },
        "Sətir %(n)s: ad və MAC lazımdır.": {
            "en": "Line %(n)s: name and MAC are required.",
            "ru": "Строка %(n)s: требуются название и MAC.",
            "tr": "Satır %(n)s: ad ve MAC gereklidir.",
        },
        "Yer nömrəsi müsbət olmalıdır.": {
            "en": "Seat number must be positive.",
            "ru": "Номер места должен быть положительным.",
            "tr": "Koltuk numarası pozitif olmalıdır.",
        },
        "Yer nömrəsi rəqəm olmalıdır: %(seat)s": {
            "en": "Seat number must be a number: %(seat)s",
            "ru": "Номер места должен быть числом: %(seat)s",
            "tr": "Koltuk numarası sayı olmalıdır: %(seat)s",
        },
        "«%(room)s» zalının oturum tarixçəsi var — silinə bilməz. Zalı deaktiv edin.": {
            "en": "Room “%(room)s” has session history — it cannot be deleted. Deactivate it instead.",
            "ru": "У зала «%(room)s» есть история сессий — его нельзя удалить. Деактивируйте зал.",
            "tr": "«%(room)s» salonunun oturum geçmişi var — silinemez. Salonu devre dışı bırakın.",
        },
    },
    "exams.final_center.form": {
        "Başlama vaxtı keçmişdə ola bilməz.": {
            "en": "Start time cannot be in the past.",
            "ru": "Время начала не может быть в прошлом.",
            "tr": "Başlama zamanı geçmişte olamaz.",
        },
        "Bitmə vaxtı başlama vaxtından sonra olmalıdır.": {
            "en": "End time must be after the start time.",
            "ru": "Время окончания должно быть позже времени начала.",
            "tr": "Bitiş zamanı başlama zamanından sonra olmalıdır.",
        },
        "Bu kod ilə zal artıq mövcuddur.": {
            "en": "A room with this code already exists.",
            "ru": "Зал с таким кодом уже существует.",
            "tr": "Bu kodla salon zaten mevcut.",
        },
        "Final imtahanı": {"en": "Final exam", "ru": "Финальный экзамен", "tr": "Final sınavı"},
        "Qrup seçin və ya istifadəçi adlarını daxil edin.": {
            "en": "Select a group or enter usernames.",
            "ru": "Выберите группу или введите имена пользователей.",
            "tr": "Grup seçin veya kullanıcı adlarını girin.",
        },
        "Tələbə qrupu": {"en": "Student group", "ru": "Студенческая группа", "tr": "Öğrenci grubu"},
        "Vergül və ya yeni sətirlə ayrılmış istifadəçi adları.": {
            "en": "Usernames separated by commas or new lines.",
            "ru": "Имена пользователей через запятую или с новой строки.",
            "tr": "Virgül veya yeni satırla ayrılmış kullanıcı adları.",
        },
        "İstifadəçi adları": {"en": "Usernames", "ru": "Имена пользователей", "tr": "Kullanıcı adları"},
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
