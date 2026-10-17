#!/usr/bin/env python3
"""EMSArena i18n — məcburi profil məlumatları (FİN, telefon, e-poçt) 2026-10-17.

Sahib: «Daxil olan hər kəsə ilk dəfə — kimdəsə FİN kod xanası ya da hansı xana məlumatı vacibdir, yoxdursa —
məcburi doldurma et. Və izahda yaz ki nəyə görə lazımdır.» Əlavə olunan mətnlər:
  * `accounts.profile_completion` — siyasət (sahə adları, «nəyə lazımdır» izahları, xəta mətnləri),
    yazma servisi, səhifə (`accounts/profile_completion.html`);
  * `core.runtime_settings` — «Sistem tənzimləmələri»ndə yeni qrup və açarlar (`profile.*`);
  * `profile.rim` — RİM mərkəzində «Məlumat natamam» filtri.

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir (mövcudluq `polib`
ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_profile_completion_2026_10_17.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

PC = "accounts.profile_completion"
RS = "core.runtime_settings"
RIM = "profile.rim"

FIN_WHY = (
    "Rəsmi sənədlər (arayış, diplom əlavəsi), dövlət sistemləri (ATİS/DİM) ilə uyğunlaşdırma və hesabınızın "
    "bərpasında kimliyinizi təsdiqləmək üçün. Şəxsiyyət vəsiqəsinin arxa üzündəki 7 simvoldur."
)
EMAIL_WHY = "Parol bərpası kodu bu ünvana göndərilir. Hər gün istifadə etdiyiniz ünvanı yazın (məs. Gmail)."
FIN_CONFLICT = (
    "Bu FİN kod başqa hesabda qeydə alınıb. Düzgün yazdığınıza əminsinizsə, RİM-ə müraciət edin — "
    "hesablarınız yoxlanılıb birləşdiriləcək."
)
SUBHEADING = (
    "hesabınızda bəzi vacib məlumatlar yoxdur. Davam etmək üçün aşağıdakı xanaları doldurun — bu bir dəfəlik addımdır."
)
PRIVACY = (
    "Bu məlumatlar ictimai profilinizdə göstərilmir və kənar şəxslərlə paylaşılmır. Onları yalnız siz və iş zərurəti "
    "olan səlahiyyətli əməkdaşlar (RİM, dekanlıq, kadrlar şöbəsi) görə bilər."
)
GATE_HELP = (
    "Yanılıda FİN kodu, mobil telefonu və ya şəxsi e-poçtu boş olan tələbə və əməkdaş girişdən sonra "
    "«Məlumatlarınızı tamamlayın» səhifəsinə yönlənir və onları doldurmadan sistemdən istifadə edə bilmir. "
    "Söndürülüdə (qəza halı) heç kim dayandırılmır."
)

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    PC: {
        "FİN kod": {"en": "FIN code", "ru": "Код FIN", "tr": "FİN kodu", "de": "FIN-Code"},
        FIN_WHY: {
            "en": "For official documents (certificates, diploma supplement), matching with state systems (ATIS/DIM) "
            "and confirming your identity when your account is recovered. It is the 7 characters on the back of "
            "your ID card.",
            "ru": "Для официальных документов (справки, приложение к диплому), сверки с государственными системами "
            "(ATİS/DİM) и подтверждения вашей личности при восстановлении аккаунта. Это 7 символов на обороте "
            "удостоверения личности.",
            "tr": "Resmî belgeler (belge, diploma eki), devlet sistemleriyle (ATİS/DİM) eşleştirme ve hesabınız "
            "kurtarılırken kimliğinizi doğrulamak için. Kimlik kartınızın arka yüzündeki 7 karakterdir.",
            "de": "Für amtliche Dokumente (Bescheinigungen, Diploma Supplement), den Abgleich mit staatlichen "
            "Systemen (ATİS/DİM) und die Bestätigung Ihrer Identität bei der Kontowiederherstellung. Es sind die "
            "7 Zeichen auf der Rückseite Ihres Personalausweises.",
        },
        "məs: 5ABC12D": {"en": "e.g. 5ABC12D", "ru": "напр.: 5ABC12D", "tr": "örn: 5ABC12D", "de": "z. B. 5ABC12D"},
        "Mobil telefon": {"en": "Mobile phone", "ru": "Мобильный телефон", "tr": "Cep telefonu", "de": "Mobiltelefon"},
        "Təcili xəbərdarlıqlar və hesabın bərpası üçün.": {
            "en": "For urgent notices and account recovery.",
            "ru": "Для срочных уведомлений и восстановления аккаунта.",
            "tr": "Acil bildirimler ve hesap kurtarma için.",
            "de": "Für dringende Benachrichtigungen und die Kontowiederherstellung.",
        },
        "məs: 050 123 45 67": {
            "en": "e.g. 050 123 45 67",
            "ru": "напр.: 050 123 45 67",
            "tr": "örn: 050 123 45 67",
            "de": "z. B. 050 123 45 67",
        },
        "Şəxsi e-poçt": {
            "en": "Personal e-mail",
            "ru": "Личная эл. почта",
            "tr": "Kişisel e-posta",
            "de": "Private E-Mail",
        },
        EMAIL_WHY: {
            "en": "The password recovery code is sent to this address. Enter the address you use every day "
            "(e.g. Gmail).",
            "ru": "Код восстановления пароля отправляется на этот адрес. Укажите адрес, которым пользуетесь каждый "
            "день (напр. Gmail).",
            "tr": "Şifre kurtarma kodu bu adrese gönderilir. Her gün kullandığınız adresi yazın (örn. Gmail).",
            "de": "Der Code zur Passwortwiederherstellung wird an diese Adresse gesendet. Geben Sie die Adresse an, "
            "die Sie täglich nutzen (z. B. Gmail).",
        },
        "məs: adiniz@gmail.com": {
            "en": "e.g. yourname@gmail.com",
            "ru": "напр.: vashe_imya@gmail.com",
            "tr": "örn: adiniz@gmail.com",
            "de": "z. B. ihrname@gmail.com",
        },
        "FİN kodunu yazın.": {
            "en": "Enter your FIN code.",
            "ru": "Введите код FIN.",
            "tr": "FİN kodunu yazın.",
            "de": "Geben Sie Ihren FIN-Code ein.",
        },
        "FİN kod 7 simvoldur: yalnız latın hərfləri və rəqəmlər (məs. 5ABC12D).": {
            "en": "The FIN code has 7 characters: Latin letters and digits only (e.g. 5ABC12D).",
            "ru": "Код FIN состоит из 7 символов: только латинские буквы и цифры (напр. 5ABC12D).",
            "tr": "FİN kodu 7 karakterdir: yalnızca Latin harfleri ve rakamlar (örn. 5ABC12D).",
            "de": "Der FIN-Code hat 7 Zeichen: nur lateinische Buchstaben und Ziffern (z. B. 5ABC12D).",
        },
        "Mobil telefon nömrəsini yazın.": {
            "en": "Enter your mobile phone number.",
            "ru": "Введите номер мобильного телефона.",
            "tr": "Cep telefonu numaranızı yazın.",
            "de": "Geben Sie Ihre Mobilnummer ein.",
        },
        "Telefon nömrəsi düzgün deyil (məs. 050 123 45 67).": {
            "en": "The phone number is not valid (e.g. 050 123 45 67).",
            "ru": "Неверный номер телефона (напр. 050 123 45 67).",
            "tr": "Telefon numarası geçerli değil (örn. 050 123 45 67).",
            "de": "Die Telefonnummer ist ungültig (z. B. 050 123 45 67).",
        },
        "E-poçt ünvanını yazın.": {
            "en": "Enter your e-mail address.",
            "ru": "Введите адрес эл. почты.",
            "tr": "E-posta adresinizi yazın.",
            "de": "Geben Sie Ihre E-Mail-Adresse ein.",
        },
        "Etibarlı e-poçt ünvanı yazın.": {
            "en": "Enter a valid e-mail address.",
            "ru": "Введите действительный адрес эл. почты.",
            "tr": "Geçerli bir e-posta adresi yazın.",
            "de": "Geben Sie eine gültige E-Mail-Adresse ein.",
        },
        FIN_CONFLICT: {
            "en": "This FIN code is registered to another account. If you are sure you typed it correctly, contact "
            "the RİM — your accounts will be checked and merged.",
            "ru": "Этот код FIN зарегистрирован в другом аккаунте. Если вы уверены, что ввели его верно, обратитесь "
            "в RİM — ваши аккаунты будут проверены и объединены.",
            "tr": "Bu FİN kodu başka bir hesapta kayıtlı. Doğru yazdığınızdan eminseniz RİM'e başvurun — "
            "hesaplarınız kontrol edilip birleştirilecek.",
            "de": "Dieser FIN-Code ist bei einem anderen Konto hinterlegt. Wenn Sie sicher sind, dass er stimmt, "
            "wenden Sie sich an das RİM — Ihre Konten werden geprüft und zusammengeführt.",
        },
        "Bu e-poçt ünvanı istifadə oluna bilməz. Başqa ünvan yazın.": {
            "en": "This e-mail address cannot be used. Enter another address.",
            "ru": "Этот адрес эл. почты нельзя использовать. Укажите другой адрес.",
            "tr": "Bu e-posta adresi kullanılamaz. Başka bir adres yazın.",
            "de": "Diese E-Mail-Adresse kann nicht verwendet werden. Geben Sie eine andere Adresse ein.",
        },
        "Məlumatlarınız saxlanıldı. Təşəkkür edirik!": {
            "en": "Your details have been saved. Thank you!",
            "ru": "Ваши данные сохранены. Спасибо!",
            "tr": "Bilgileriniz kaydedildi. Teşekkür ederiz!",
            "de": "Ihre Angaben wurden gespeichert. Vielen Dank!",
        },
        "Məlumatlarınızı tamamlayın": {
            "en": "Complete your details",
            "ru": "Заполните ваши данные",
            "tr": "Bilgilerinizi tamamlayın",
            "de": "Vervollständigen Sie Ihre Angaben",
        },
        SUBHEADING: {
            "en": "some important details are missing from your account. Fill in the fields below to continue — "
            "this is a one-time step.",
            "ru": "в вашем аккаунте не хватает важных данных. Чтобы продолжить, заполните поля ниже — это "
            "одноразовый шаг.",
            "tr": "hesabınızda bazı önemli bilgiler eksik. Devam etmek için aşağıdaki alanları doldurun — bu tek "
            "seferlik bir adımdır.",
            "de": "in Ihrem Konto fehlen einige wichtige Angaben. Füllen Sie die folgenden Felder aus, um "
            "fortzufahren — dieser Schritt ist einmalig.",
        },
        "Bəzi xanalarda səhv var — aşağıda qeyd olunub.": {
            "en": "Some fields contain errors — they are marked below.",
            "ru": "В некоторых полях есть ошибки — они отмечены ниже.",
            "tr": "Bazı alanlarda hata var — aşağıda belirtilmiştir.",
            "de": "Einige Felder enthalten Fehler — sie sind unten markiert.",
        },
        "Nəyə lazımdır:": {"en": "Why we need it:", "ru": "Зачем это нужно:", "tr": "Neden gerekli:", "de": "Wozu:"},
        "Məlumatlarınız qorunur": {
            "en": "Your data is protected",
            "ru": "Ваши данные защищены",
            "tr": "Bilgileriniz korunur",
            "de": "Ihre Daten sind geschützt",
        },
        PRIVACY: {
            "en": "These details are not shown on your public profile and are not shared with outsiders. Only you and "
            "authorised staff with a work need (RİM, dean's office, HR department) can see them.",
            "ru": "Эти данные не показываются в вашем публичном профиле и не передаются посторонним. Их видите только "
            "вы и уполномоченные сотрудники по служебной необходимости (RİM, деканат, отдел кадров).",
            "tr": "Bu bilgiler herkese açık profilinizde gösterilmez ve dışarıdan kişilerle paylaşılmaz. Bunları "
            "yalnızca siz ve iş gereği yetkili personel (RİM, dekanlık, personel dairesi) görebilir.",
            "de": "Diese Angaben werden nicht in Ihrem öffentlichen Profil angezeigt und nicht an Dritte "
            "weitergegeben. Nur Sie und befugte Mitarbeitende mit dienstlichem Bedarf (RİM, Dekanat, "
            "Personalabteilung) können sie sehen.",
        },
        "Səhv yazdığınızı sonra görsəniz, düzəliş üçün RİM-ə müraciət edin.": {
            "en": "If you later notice a mistake, contact the RİM to have it corrected.",
            "ru": "Если позже заметите ошибку, обратитесь в RİM для исправления.",
            "tr": "Daha sonra bir hata fark ederseniz düzeltme için RİM'e başvurun.",
            "de": "Wenn Sie später einen Fehler bemerken, wenden Sie sich zur Korrektur an das RİM.",
        },
        "Saxla və davam et": {
            "en": "Save and continue",
            "ru": "Сохранить и продолжить",
            "tr": "Kaydet ve devam et",
            "de": "Speichern und fortfahren",
        },
        "Çıxış": {"en": "Log out", "ru": "Выйти", "tr": "Çıkış", "de": "Abmelden"},
    },
    RS: {
        "Məcburi profil məlumatları": {
            "en": "Required profile details",
            "ru": "Обязательные данные профиля",
            "tr": "Zorunlu profil bilgileri",
            "de": "Pflichtangaben im Profil",
        },
        "Girişdən sonra vacib məlumatları məcburi doldurmaq": {
            "en": "Require important details after login",
            "ru": "Обязательное заполнение важных данных после входа",
            "tr": "Girişten sonra önemli bilgilerin doldurulması zorunlu",
            "de": "Wichtige Angaben nach der Anmeldung verpflichtend",
        },
        GATE_HELP: {
            "en": "When on, a student or staff member whose FIN code, mobile phone or personal e-mail is empty is "
            "sent to the «Complete your details» page after login and cannot use the system until they fill them "
            "in. When off (emergency), nobody is stopped.",
            "ru": "Если включено, студент или сотрудник с пустым кодом FIN, мобильным телефоном или личной почтой "
            "после входа направляется на страницу «Заполните ваши данные» и не может пользоваться системой, пока "
            "не заполнит их. Если выключено (экстренный случай), никто не останавливается.",
            "tr": "Açıkken FİN kodu, cep telefonu veya kişisel e-postası boş olan öğrenci ve personel girişten sonra "
            "«Bilgilerinizi tamamlayın» sayfasına yönlendirilir ve bunları doldurmadan sistemi kullanamaz. "
            "Kapalıyken (acil durum) kimse durdurulmaz.",
            "de": "Wenn aktiviert, werden Studierende und Mitarbeitende ohne FIN-Code, Mobilnummer oder private "
            "E-Mail nach der Anmeldung auf die Seite «Vervollständigen Sie Ihre Angaben» geleitet und können das "
            "System erst nach dem Ausfüllen nutzen. Wenn deaktiviert (Notfall), wird niemand aufgehalten.",
        },
        "FİN kod məcburidir": {
            "en": "FIN code is required",
            "ru": "Код FIN обязателен",
            "tr": "FİN kodu zorunlu",
            "de": "FIN-Code ist Pflicht",
        },
        "Mobil telefon məcburidir": {
            "en": "Mobile phone is required",
            "ru": "Мобильный телефон обязателен",
            "tr": "Cep telefonu zorunlu",
            "de": "Mobiltelefon ist Pflicht",
        },
        "Şəxsi e-poçt məcburidir": {
            "en": "Personal e-mail is required",
            "ru": "Личная эл. почта обязательна",
            "tr": "Kişisel e-posta zorunlu",
            "de": "Private E-Mail ist Pflicht",
        },
    },
    RIM: {
        "Məlumat natamam (FİN, telefon, e-poçt)": {
            "en": "Details incomplete (FIN, phone, e-mail)",
            "ru": "Данные неполные (FIN, телефон, эл. почта)",
            "tr": "Bilgiler eksik (FİN, telefon, e-posta)",
            "de": "Angaben unvollständig (FIN, Telefon, E-Mail)",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
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
