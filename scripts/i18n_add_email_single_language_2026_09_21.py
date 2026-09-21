#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-21: OTP / şifrə sıfırlama e-poçtları TƏK dildə.

Sahib: «Şablondakı dili düzəlt, 2 dil bir-birinə qarışıb». Mövzu, başlıq,
«… üçün» ifadəsi Python-da sabit AZ idi, şablonun qalan sətirləri aktiv dilə
tərcümə olunurdu. İndi hamısı kataloqdan keçir və məktub `translation.override`
ilə bir dildə render olunur. Bu skript yeni msgid-ləri 4 kataloqa əlavə edir
(AZ msgstr = msgid). İdempotent.
İstifadə:  python scripts/i18n_add_email_single_language_2026_09_21.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")
CTX = "accounts.email_otp"

STRINGS = {
    # ── Python (apps/accounts/services/auth.py) ──
    (CTX, "%(brand)s email təsdiqi"): (
        "%(brand)s email verification",
        "%(brand)s — подтверждение email",
        "%(brand)s e-posta doğrulama",
    ),
    (CTX, "%(brand)s giriş OTP kodu"): (
        "%(brand)s login OTP code",
        "%(brand)s — OTP-код для входа",
        "%(brand)s giriş için OTP kodu",
    ),
    (CTX, "%(brand)s şifrə sıfırlama OTP kodu"): (
        "%(brand)s password reset OTP code",
        "%(brand)s — OTP-код для сброса пароля",
        "%(brand)s şifre sıfırlama OTP kodu",
    ),
    (CTX, "%(brand)s admin giriş OTP kodu"): (
        "%(brand)s admin login OTP code",
        "%(brand)s — OTP-код для входа администратора",
        "%(brand)s yönetici giriş OTP kodu",
    ),
    (CTX, "%(brand)s OTP kodu"): ("%(brand)s OTP code", "%(brand)s — OTP-код", "%(brand)s tek kullanımlık kodu"),
    (CTX, "Email təsdiqi"): ("Email verification", "Подтверждение email", "E-posta doğrulama"),
    (CTX, "Giriş təsdiqi"): ("Login confirmation", "Подтверждение входа", "Giriş onayı"),
    (CTX, "Şifrə sıfırlama təsdiqi"): (
        "Password reset confirmation",
        "Подтверждение сброса пароля",
        "Şifre sıfırlama onayı",
    ),
    (CTX, "Admin giriş təsdiqi"): (
        "Admin login confirmation",
        "Подтверждение входа администратора",
        "Yönetici giriş onayı",
    ),
    (CTX, "OTP təsdiqi"): ("OTP confirmation", "Подтверждение OTP", "OTP onayı"),
    (CTX, "hesabınızı aktivləşdirmək"): (
        "activating your account",
        "активации вашей учётной записи",
        "hesabınızı etkinleştirmek",
    ),
    (CTX, "girişinizi təsdiqləmək"): ("confirming your login", "подтверждения входа", "girişinizi onaylamak"),
    (CTX, "şifrəni sıfırlama əməliyyatını təsdiqləmək"): (
        "confirming the password reset",
        "подтверждения сброса пароля",
        "şifre sıfırlama işlemini onaylamak",
    ),
    (CTX, "admin girişinizi təsdiqləmək"): (
        "confirming your admin login",
        "подтверждения входа администратора",
        "yönetici girişinizi onaylamak",
    ),
    (CTX, "əməliyyatı təsdiqləmək"): ("confirming the action", "подтверждения действия", "işlemi onaylamak"),
    (CTX, "Emaili təsdiqlə"): ("Confirm email", "Подтвердить email", "E-postayı onayla"),
    (CTX, "Girişi təsdiqlə"): ("Confirm login", "Подтвердить вход", "Girişi onayla"),
    (CTX, "Şifrəni sıfırla"): ("Reset password", "Сбросить пароль", "Şifreyi sıfırla"),
    (CTX, "Admin girişi təsdiqlə"): (
        "Confirm admin login",
        "Подтвердить вход администратора",
        "Yönetici girişini onayla",
    ),
    (CTX, "OTP-ni təsdiqlə"): ("Confirm OTP", "Подтвердить OTP", "OTP'yi onayla"),
    # ── Şablonlar (msgctxt yoxdur — mövcud e-poçt şablonları ilə eyni üslub) ──
    (None, "OTP kodu"): ("OTP code", "OTP-код", "Tek kullanımlık kod (OTP)"),
    (None, "Salam %(name)s,"): ("Hello %(name)s,", "Здравствуйте, %(name)s!", "Merhaba %(name)s,"),
    (None, "Salam <strong>%(name)s</strong>, hesabınız üçün şifrə yeniləmə sorğusu alındı."): (
        "Hello <strong>%(name)s</strong>, a password reset request was received for your account.",
        "Здравствуйте, <strong>%(name)s</strong>! Получен запрос на сброс пароля для вашей учётной записи.",
        "Merhaba <strong>%(name)s</strong>, hesabınız için şifre sıfırlama isteği alındı.",
    ),
    (None, "Aşağıdakı OTP kodu %(action)s üçündür:"): (
        "The OTP code below is for %(action)s:",
        "OTP-код ниже — для %(action)s:",
        "Aşağıdaki OTP kodu %(action)s içindir:",
    ),
    (None, "Kod %(minutes)s dəqiqə etibarlıdır."): (
        "The code is valid for %(minutes)s minutes.",
        "Код действителен %(minutes)s минут.",
        "Kod %(minutes)s dakika geçerlidir.",
    ),
    (None, "Bu əməliyyatı siz etməmisinizsə, bu emaili nəzərə almayın."): (
        "If you did not request this, please ignore this email.",
        "Если вы не выполняли это действие, проигнорируйте это письмо.",
        "Bu işlemi siz yapmadıysanız bu e-postayı dikkate almayın.",
    ),
    (None, "%(brand)s hesabınızı təsdiqləmək üçün aşağıdakı linki açın:"): (
        "Open the link below to confirm your %(brand)s account:",
        "Откройте ссылку ниже, чтобы подтвердить учётную запись %(brand)s:",
        "%(brand)s hesabınızı onaylamak için aşağıdaki bağlantıyı açın:",
    ),
    (None, "Kod və link %(minutes)s dəqiqə etibarlıdır."): (
        "The code and the link are valid for %(minutes)s minutes.",
        "Код и ссылка действительны %(minutes)s минут.",
        "Kod ve bağlantı %(minutes)s dakika geçerlidir.",
    ),
    (None, "%(brand)s hesabınız üçün şifrə sıfırlama sorğusu alındı."): (
        "A password reset request was received for your %(brand)s account.",
        "Получен запрос на сброс пароля для вашей учётной записи %(brand)s.",
        "%(brand)s hesabınız için şifre sıfırlama isteği alındı.",
    ),
    (
        None,
        "Şifrəni yeniləmək üçün bu linki aça və ya saytda açıq olan şifrə bərpa səhifəsində OTP kodunu daxil edə bilərsiniz:",
    ): (
        "To reset your password, open this link or enter the OTP code on the password recovery page that is open on the site:",
        "Чтобы обновить пароль, откройте эту ссылку или введите OTP-код на открытой на сайте странице восстановления пароля:",
        "Şifreyi yenilemek için bu bağlantıyı açabilir veya sitede açık olan şifre kurtarma sayfasına OTP kodunu girebilirsiniz:",
    ),
    (None, "Link və OTP kodu %(minutes)s dəqiqə etibarlıdır."): (
        "The link and the OTP code are valid for %(minutes)s minutes.",
        "Ссылка и OTP-код действительны %(minutes)s минут.",
        "Bağlantı ve OTP kodu %(minutes)s dakika geçerlidir.",
    ),
    (None, "Əgər bu sorğunu siz etməmisinizsə, bu e-maili nəzərə almayın."): (
        "If you did not make this request, please ignore this email.",
        "Если вы не отправляли этот запрос, проигнорируйте это письмо.",
        "Bu isteği siz yapmadıysanız bu e-postayı dikkate almayın.",
    ),
    (None, "Şifrə sıfırlama"): ("Password reset", "Сброс пароля", "Şifre sıfırlama"),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
