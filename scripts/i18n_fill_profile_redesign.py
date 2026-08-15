#!/usr/bin/env python3
"""EMSArena i18n — 2026-08-15 profil redizaynı sətirləri. İdempotent.

Akademik profil (elmi ad/dərəcə, «Akademik fəaliyyət» qeydləri), rol-yönlü
redaktə, OTP-li şifrə dəyişmə, açıq profil önizləməsi və əlaqə kartı — bütün
yeni UI/servis sətirləri 4 dildə doldurulur.

İstifadə:  python scripts/i18n_fill_profile_redesign.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "accounts.academic_title": {
        "Assistent": {"en": "Assistant", "ru": "Ассистент", "tr": "Asistan"},
        "Müəllim": {"en": "Lecturer", "ru": "Преподаватель", "tr": "Öğretim görevlisi"},
        "Baş müəllim": {"en": "Senior lecturer", "ru": "Старший преподаватель", "tr": "Baş öğretim görevlisi"},
        "Dosent": {"en": "Associate professor", "ru": "Доцент", "tr": "Doçent"},
        "Professor": {"en": "Professor", "ru": "Профессор", "tr": "Profesör"},
    },
    "accounts.academic_degree": {
        "Fəlsəfə doktoru (PhD)": {"en": "PhD", "ru": "Доктор философии (PhD)", "tr": "Doktora (PhD)"},
        "Elmlər doktoru": {"en": "Doctor of Sciences", "ru": "Доктор наук", "tr": "Bilim doktoru"},
    },
    "accounts.academic_item_kind": {
        "Tədris etdiyi fənn": {"en": "Subject taught", "ru": "Преподаваемый предмет", "tr": "Verdiği ders"},
        "Sertifikat": {"en": "Certificate", "ru": "Сертификат", "tr": "Sertifika"},
        "Məqalə": {"en": "Article", "ru": "Статья", "tr": "Makale"},
        "Konfrans materialı": {
            "en": "Conference paper",
            "ru": "Материал конференции",
            "tr": "Konferans bildirisi",
        },
    },
    "profile.edit_v2": {
        "Şəxsi məlumatlar": {"en": "Personal information", "ru": "Личные данные", "tr": "Kişisel bilgiler"},
        "Akademik məlumat": {"en": "Academic information", "ru": "Академические данные", "tr": "Akademik bilgiler"},
        "Bu məlumatlar universitet tərəfindən idarə olunur və buradan dəyişdirilə bilməz.": {
            "en": "This information is managed by the university and cannot be changed here.",
            "ru": "Эти данные управляются университетом и не могут быть изменены здесь.",
            "tr": "Bu bilgiler üniversite tarafından yönetilir ve buradan değiştirilemez.",
        },
        "Elmi ad / vəzifə": {"en": "Academic title", "ru": "Учёное звание / должность", "tr": "Akademik unvan"},
        "Elmi dərəcə": {"en": "Academic degree", "ru": "Учёная степень", "tr": "Akademik derece"},
        "Seçilməyib": {"en": "Not selected", "ru": "Не выбрано", "tr": "Seçilmedi"},
        "Akademik fəaliyyət": {
            "en": "Academic activity",
            "ru": "Академическая деятельность",
            "tr": "Akademik faaliyet",
        },
        "Tədris etdiyiniz fənləri, sertifikatlarınızı, məqalə və konfrans materiallarınızı əlavə edin — bunlar profil səhifənizdə görünəcək.": {
            "en": "Add the subjects you teach, your certificates, articles and conference papers — they will appear on your profile page.",
            "ru": "Добавьте преподаваемые предметы, сертификаты, статьи и материалы конференций — они появятся на странице вашего профиля.",
            "tr": "Verdiğiniz dersleri, sertifikalarınızı, makale ve konferans bildirilerinizi ekleyin — profil sayfanızda görünecekler.",
        },
        "Nömrələr yalnız əməkdaş səviyyəli baxanlara görünür, tələbələrə yox.": {
            "en": "Phone numbers are visible only to staff-level viewers, not to students.",
            "ru": "Номера видны только сотрудникам, студентам они не показываются.",
            "tr": "Numaralar yalnızca personel düzeyindeki kullanıcılara görünür, öğrencilere görünmez.",
        },
        "Əlavə telefon": {"en": "Additional phone", "ru": "Дополнительный телефон", "tr": "Ek telefon"},
        "Yadda saxlanmamış dəyişikliklər var": {
            "en": "You have unsaved changes",
            "ru": "Есть несохранённые изменения",
            "tr": "Kaydedilmemiş değişiklikler var",
        },
        "Önizləmə": {"en": "Preview", "ru": "Предпросмотр", "tr": "Önizleme"},
        "Dəyişikliklər yadda saxlanmayıb": {
            "en": "Changes are not saved",
            "ru": "Изменения не сохранены",
            "tr": "Değişiklikler kaydedilmedi",
        },
        "Səhifədən çıxsanız, etdiyiniz dəyişikliklər itəcək. Nə etmək istəyirsiniz?": {
            "en": "If you leave this page, your changes will be lost. What would you like to do?",
            "ru": "Если вы покинете страницу, изменения будут потеряны. Что вы хотите сделать?",
            "tr": "Sayfadan çıkarsanız değişiklikleriniz kaybolacak. Ne yapmak istersiniz?",
        },
        "Saxlamadan çıx": {"en": "Leave without saving", "ru": "Выйти без сохранения", "tr": "Kaydetmeden çık"},
        "Yadda saxla": {"en": "Save", "ru": "Сохранить", "tr": "Kaydet"},
    },
    "profile.academic_items": {
        "Yeni qeyd": {"en": "New entry", "ru": "Новая запись", "tr": "Yeni kayıt"},
        "Qeydi redaktə et": {"en": "Edit entry", "ru": "Редактировать запись", "tr": "Kaydı düzenle"},
        "Əməliyyat alınmadı. Yenidən cəhd edin.": {
            "en": "The operation failed. Please try again.",
            "ru": "Операция не удалась. Попробуйте ещё раз.",
            "tr": "İşlem başarısız oldu. Lütfen tekrar deneyin.",
        },
        "Bağla": {"en": "Close", "ru": "Закрыть", "tr": "Kapat"},
        "Başlıq": {"en": "Title", "ru": "Название", "tr": "Başlık"},
        "Məs.: Verilənlər bazası sistemləri": {
            "en": "E.g.: Database systems",
            "ru": "Напр.: Системы баз данных",
            "tr": "Örn.: Veritabanı sistemleri",
        },
        "Ətraflı": {"en": "Details", "ru": "Подробности", "tr": "Ayrıntı"},
        "Jurnal / konfrans / qurum adı və s.": {
            "en": "Journal / conference / issuing body, etc.",
            "ru": "Журнал / конференция / организация и т.д.",
            "tr": "Dergi / konferans / kurum adı vb.",
        },
        "İl": {"en": "Year", "ru": "Год", "tr": "Yıl"},
        "Keçid (URL)": {"en": "Link (URL)", "ru": "Ссылка (URL)", "tr": "Bağlantı (URL)"},
        "Yadda saxla": {"en": "Save", "ru": "Сохранить", "tr": "Kaydet"},
        "Qeydi sil": {"en": "Delete entry", "ru": "Удалить запись", "tr": "Kaydı sil"},
        "Bu qeyd silinsin?": {
            "en": "Delete this entry?",
            "ru": "Удалить эту запись?",
            "tr": "Bu kayıt silinsin mi?",
        },
        "Sil": {"en": "Delete", "ru": "Удалить", "tr": "Sil"},
        "Əlavə et": {"en": "Add", "ru": "Добавить", "tr": "Ekle"},
        "Redaktə et": {"en": "Edit", "ru": "Редактировать", "tr": "Düzenle"},
        "Keçidi aç": {"en": "Open link", "ru": "Открыть ссылку", "tr": "Bağlantıyı aç"},
        "Hələ qeyd əlavə edilməyib.": {
            "en": "No entries added yet.",
            "ru": "Записей пока нет.",
            "tr": "Henüz kayıt eklenmedi.",
        },
        "Qeydlərdə axtar...": {"en": "Search entries...", "ru": "Поиск по записям...", "tr": "Kayıtlarda ara..."},
        "Qeydlərdə axtar": {"en": "Search entries", "ru": "Поиск по записям", "tr": "Kayıtlarda ara"},
        "Daha çox göstər": {"en": "Show more", "ru": "Показать ещё", "tr": "Daha fazla göster"},
        "Daha az göstər": {"en": "Show less", "ru": "Показать меньше", "tr": "Daha az göster"},
        "Axtarışa uyğun qeyd tapılmadı.": {
            "en": "No entries match your search.",
            "ru": "По запросу записей не найдено.",
            "tr": "Aramaya uygun kayıt bulunamadı.",
        },
    },
    "profile.password_otp": {
        "Şifrə dəyişmə üsulu": {
            "en": "Password change method",
            "ru": "Способ смены пароля",
            "tr": "Şifre değiştirme yöntemi",
        },
        "Mövcud şifrə ilə": {"en": "With current password", "ru": "С текущим паролем", "tr": "Mevcut şifre ile"},
        "Email kodu ilə": {"en": "With email code", "ru": "По коду из email", "tr": "E-posta kodu ile"},
        "Mövcud şifrənizi unutmusunuz?": {
            "en": "Forgot your current password?",
            "ru": "Забыли текущий пароль?",
            "tr": "Mevcut şifrenizi mi unuttunuz?",
        },
        "Email kodu ilə dəyişin": {
            "en": "Change it with an email code",
            "ru": "Смените по коду из email",
            "tr": "E-posta koduyla değiştirin",
        },
        "Kodu göndər": {"en": "Send code", "ru": "Отправить код", "tr": "Kodu gönder"},
        "Yenidən göndər": {"en": "Resend", "ru": "Отправить снова", "tr": "Yeniden gönder"},
        "Kod göndərilə bilmədi. Yenidən cəhd edin.": {
            "en": "The code could not be sent. Please try again.",
            "ru": "Не удалось отправить код. Попробуйте ещё раз.",
            "tr": "Kod gönderilemedi. Lütfen tekrar deneyin.",
        },
        "Emailə gələn kod": {"en": "Code from email", "ru": "Код из письма", "tr": "E-postaya gelen kod"},
        "Birdəfəlik kod <strong>%(email)s</strong> ünvanına göndəriləcək.": {
            "en": "A one-time code will be sent to <strong>%(email)s</strong>.",
            "ru": "Одноразовый код будет отправлен на <strong>%(email)s</strong>.",
            "tr": "Tek kullanımlık kod <strong>%(email)s</strong> adresine gönderilecek.",
        },
    },
    "accounts.password_otp": {
        "Hesabınızda email ünvanı yoxdur. Əvvəlcə profilə email əlavə edin.": {
            "en": "Your account has no email address. Add an email to your profile first.",
            "ru": "У вашей учётной записи нет email. Сначала добавьте email в профиль.",
            "tr": "Hesabınızda e-posta adresi yok. Önce profile bir e-posta ekleyin.",
        },
        "Yeni kod üçün bir az gözləyin.": {
            "en": "Please wait a moment before requesting a new code.",
            "ru": "Подождите немного перед запросом нового кода.",
            "tr": "Yeni kod için biraz bekleyin.",
        },
        "Bu email üçün saatlıq kod limiti dolub. Daha sonra yenidən cəhd edin.": {
            "en": "The hourly code limit for this email has been reached. Try again later.",
            "ru": "Часовой лимит кодов для этого email исчерпан. Попробуйте позже.",
            "tr": "Bu e-posta için saatlik kod limiti doldu. Daha sonra tekrar deneyin.",
        },
        "Kod göndərilə bilmədi. Bir az sonra yenidən cəhd edin.": {
            "en": "The code could not be sent. Try again shortly.",
            "ru": "Не удалось отправить код. Попробуйте чуть позже.",
            "tr": "Kod gönderilemedi. Kısa süre sonra tekrar deneyin.",
        },
        "Kod %(email)s ünvanına göndərildi.": {
            "en": "The code was sent to %(email)s.",
            "ru": "Код отправлен на %(email)s.",
            "tr": "Kod %(email)s adresine gönderildi.",
        },
    },
    "accounts.academic_items.error": {
        "Qeyd tapılmadı.": {"en": "Entry not found.", "ru": "Запись не найдена.", "tr": "Kayıt bulunamadı."},
        "Bu qeyd növü sizin rolunuz üçün mövcud deyil.": {
            "en": "This entry type is not available for your role.",
            "ru": "Этот тип записи недоступен для вашей роли.",
            "tr": "Bu kayıt türü rolünüz için kullanılamaz.",
        },
        "Başlıq boş ola bilməz.": {
            "en": "The title cannot be empty.",
            "ru": "Название не может быть пустым.",
            "tr": "Başlık boş olamaz.",
        },
        "Başlıq %(limit)s simvoldan uzun ola bilməz.": {
            "en": "The title cannot exceed %(limit)s characters.",
            "ru": "Название не может быть длиннее %(limit)s символов.",
            "tr": "Başlık %(limit)s karakterden uzun olamaz.",
        },
        "Ətraflı sahəsi %(limit)s simvoldan uzun ola bilməz.": {
            "en": "The details field cannot exceed %(limit)s characters.",
            "ru": "Поле подробностей не может быть длиннее %(limit)s символов.",
            "tr": "Ayrıntı alanı %(limit)s karakterden uzun olamaz.",
        },
        "İl rəqəmlə yazılmalıdır.": {
            "en": "The year must be a number.",
            "ru": "Год должен быть числом.",
            "tr": "Yıl rakamla yazılmalıdır.",
        },
        "İl %(low)s–%(high)s aralığında olmalıdır.": {
            "en": "The year must be between %(low)s and %(high)s.",
            "ru": "Год должен быть в диапазоне %(low)s–%(high)s.",
            "tr": "Yıl %(low)s–%(high)s aralığında olmalıdır.",
        },
        "Keçid %(limit)s simvoldan uzun ola bilməz.": {
            "en": "The link cannot exceed %(limit)s characters.",
            "ru": "Ссылка не может быть длиннее %(limit)s символов.",
            "tr": "Bağlantı %(limit)s karakterden uzun olamaz.",
        },
        "Keçid http:// və ya https:// ilə başlamalıdır.": {
            "en": "The link must start with http:// or https://.",
            "ru": "Ссылка должна начинаться с http:// или https://.",
            "tr": "Bağlantı http:// veya https:// ile başlamalıdır.",
        },
        "Bu növ üzrə maksimum %(limit)s qeyd əlavə etmək olar.": {
            "en": "You can add at most %(limit)s entries of this type.",
            "ru": "Можно добавить не более %(limit)s записей этого типа.",
            "tr": "Bu türde en fazla %(limit)s kayıt eklenebilir.",
        },
        "Naməlum əməliyyat.": {"en": "Unknown operation.", "ru": "Неизвестная операция.", "tr": "Bilinmeyen işlem."},
    },
    "accounts.public_profile": {
        "Önizləmə rejimi: profiliniz kənar baxana məhz belə görünür.": {
            "en": "Preview mode: this is exactly how your profile looks to an outside viewer.",
            "ru": "Режим предпросмотра: именно так ваш профиль видят посторонние.",
            "tr": "Önizleme modu: profiliniz dışarıdan bakan birine tam olarak böyle görünür.",
        },
        "Redaktəyə qayıt": {"en": "Back to editing", "ru": "Вернуться к редактированию", "tr": "Düzenlemeye dön"},
        "Əlaqə": {"en": "Contact", "ru": "Контакты", "tr": "İletişim"},
        "Telefon": {"en": "Phone", "ru": "Телефон", "tr": "Telefon"},
        "Nömrələr yalnız əməkdaş səviyyəli istifadəçilərə görünür.": {
            "en": "Phone numbers are visible only to staff-level users.",
            "ru": "Номера видны только пользователям уровня сотрудника.",
            "tr": "Numaralar yalnızca personel düzeyindeki kullanıcılara görünür.",
        },
    },
    "exams.template.question_bank_list": {
        "Şəxsi müəllim bankı yalnız Quiz təyinatı ilə yaradılır.": {
            "en": "A personal teacher bank is created with the Quiz designation only.",
            "ru": "Личный банк преподавателя создаётся только с назначением «Quiz».",
            "tr": "Kişisel öğretmen bankası yalnızca Quiz atamasıyla oluşturulur.",
        },
        "Bank yalnız sizə görünür — şəxsi istifadəniz üçündür.": {
            "en": "The bank is visible only to you — for your personal use.",
            "ru": "Банк виден только вам — для личного использования.",
            "tr": "Banka yalnızca size görünür — kişisel kullanımınız içindir.",
        },
        "Bank digər müəllimlərə görünmür — yalnız siz və imtahan mərkəzi görə bilir.": {
            "en": "The bank is not visible to other teachers — only you and the exam centre can see it.",
            "ru": "Банк не виден другим преподавателям — его видите только вы и экзаменационный центр.",
            "tr": "Banka diğer öğretmenlere görünmez — yalnızca siz ve sınav merkezi görebilir.",
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
            msgstr = translations.get(lang) if lang != "az" else translations.get("az", msgid)
            if msgstr is None:
                msgstr = msgid
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
