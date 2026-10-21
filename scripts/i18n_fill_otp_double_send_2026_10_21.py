#!/usr/bin/env python3
"""EMSArena i18n — OTP ikiqat göndərişi, dəqiq xəta mətnləri və kodun müddəti (sahib 2026-10-21).

Mənbələr: ``apps/accounts/services/otp_messages.py`` (``accounts.otp``),
``accounts/first_login_set_password.html`` + parol bərpası şablonları (``accounts.first_login``,
``accounts.otp``). msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra
`compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

OTP = "accounts.otp"
FL = "accounts.first_login"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    OTP: {
        "Kod hələ %(minutes)s dəq. etibarlıdır (%(time)s-ə qədər).": t(
            "The code is valid for another %(minutes)s min (until %(time)s).",
            "Код действителен ещё %(minutes)s мин. (до %(time)s).",
            "Kod %(minutes)s dk. daha geçerli (%(time)s'e kadar).",
            "Der Code ist noch %(minutes)s Min. gültig (bis %(time)s).",
        ),
        "Kod səhvdir. Məktubdakı 6 rəqəmli kodu yoxlayıb yenidən daxil edin.": t(
            "The code is incorrect. Check the 6-digit code in the e-mail and enter it again.",
            "Неверный код. Проверьте 6-значный код в письме и введите его снова.",
            "Kod yanlış. E-postadaki 6 haneli kodu kontrol edip tekrar girin.",
            "Der Code ist falsch. Prüfen Sie den 6-stelligen Code in der E-Mail und geben Sie ihn erneut ein.",
        ),
        "Qalan cəhd: %(left)s.": t(
            "Attempts left: %(left)s.",
            "Осталось попыток: %(left)s.",
            "Kalan deneme: %(left)s.",
            "Verbleibende Versuche: %(left)s.",
        ),
        "Bu kod artıq etibarsızdır — ondan sonra yeni kod göndərilib. Ən son məktubdakı kodu daxil edin.": t(
            "This code is no longer valid — a newer code was sent after it. Enter the code from the latest e-mail.",
            "Этот код больше не действителен — после него был отправлен новый. Введите код из последнего письма.",
            "Bu kod artık geçerli değil — ondan sonra yeni bir kod gönderildi. En son e-postadaki kodu girin.",
            "Dieser Code ist nicht mehr gültig – danach wurde ein neuer Code gesendet. "
            "Geben Sie den Code aus der neuesten E-Mail ein.",
        ),
        "Kodun vaxtı keçib. Yeni kod istəyin.": t(
            "The code has expired. Request a new code.",
            "Срок действия кода истёк. Запросите новый код.",
            "Kodun süresi doldu. Yeni bir kod isteyin.",
            "Der Code ist abgelaufen. Fordern Sie einen neuen Code an.",
        ),
        "Bu kod artıq istifadə olunub. Lazımdırsa yeni kod istəyin.": t(
            "This code has already been used. Request a new code if needed.",
            "Этот код уже использован. При необходимости запросите новый код.",
            "Bu kod zaten kullanıldı. Gerekirse yeni bir kod isteyin.",
            "Dieser Code wurde bereits verwendet. Fordern Sie bei Bedarf einen neuen Code an.",
        ),
        "Çox sayda səhv cəhd edildi — kod bağlandı. Yeni kod istəyin.": t(
            "Too many wrong attempts — the code has been blocked. Request a new code.",
            "Слишком много неверных попыток — код заблокирован. Запросите новый код.",
            "Çok fazla hatalı deneme yapıldı — kod kapatıldı. Yeni bir kod isteyin.",
            "Zu viele Fehlversuche – der Code wurde gesperrt. Fordern Sie einen neuen Code an.",
        ),
        "Aktiv təsdiq kodu yoxdur. Yeni kod istəyin.": t(
            "There is no active verification code. Request a new code.",
            "Активного кода подтверждения нет. Запросите новый код.",
            "Etkin doğrulama kodu yok. Yeni bir kod isteyin.",
            "Es gibt keinen aktiven Bestätigungscode. Fordern Sie einen neuen Code an.",
        ),
        "Kod 6 rəqəmdən ibarət olmalıdır.": t(
            "The code must consist of 6 digits.",
            "Код должен состоять из 6 цифр.",
            "Kod 6 haneden oluşmalıdır.",
            "Der Code muss aus 6 Ziffern bestehen.",
        ),
        "Kodu yoxlamaq mümkün olmadı. Yenidən cəhd edin.": t(
            "The code could not be checked. Please try again.",
            "Не удалось проверить код. Попробуйте ещё раз.",
            "Kod doğrulanamadı. Lütfen tekrar deneyin.",
            "Der Code konnte nicht geprüft werden. Bitte versuchen Sie es erneut.",
        ),
        "Təsdiq kodu artıq göndərilib — e-poçtunuzu (həm də «Spam» qovluğunu) yoxlayın.": t(
            "The verification code has already been sent — check your e-mail (including the Spam folder).",
            "Код подтверждения уже отправлен — проверьте почту (в том числе папку «Спам»).",
            "Doğrulama kodu zaten gönderildi — e-postanızı (Spam klasörü dahil) kontrol edin.",
            "Der Bestätigungscode wurde bereits gesendet – prüfen Sie Ihre E-Mails (auch den Spam-Ordner).",
        ),
        "Yeni kodu %(seconds)s san. sonra istəyə bilərsiniz.": t(
            "You can request a new code in %(seconds)s s.",
            "Новый код можно запросить через %(seconds)s с.",
            "Yeni kodu %(seconds)s sn. sonra isteyebilirsiniz.",
            "Einen neuen Code können Sie in %(seconds)s s anfordern.",
        ),
        "Bu e-poçt üçün saatlıq kod limiti dolub. %(minutes)s dəq. sonra yenidən cəhd edin.": t(
            "The hourly code limit for this e-mail has been reached. Try again in %(minutes)s min.",
            "Часовой лимит кодов для этого адреса исчерпан. Повторите через %(minutes)s мин.",
            "Bu e-posta için saatlik kod sınırına ulaşıldı. %(minutes)s dk. sonra tekrar deneyin.",
            "Das stündliche Code-Limit für diese E-Mail ist erreicht. Versuchen Sie es in %(minutes)s Min. erneut.",
        ),
        "Yeni kod istə": t("Request a new code", "Запросить новый код", "Yeni kod iste", "Neuen Code anfordern"),
    },
    FL: {
        "Göndərilir…": t("Sending…", "Отправка…", "Gönderiliyor…", "Wird gesendet…"),
        "Yoxlanılır…": t("Checking…", "Проверка…", "Kontrol ediliyor…", "Wird geprüft…"),
        "Kodun vaxtı keçib": t(
            "The code has expired", "Срок действия кода истёк", "Kodun süresi doldu", "Der Code ist abgelaufen"
        ),
        "Kod %(minutes)s dəqiqə etibarlıdır — %(time)s-ə qədər.": t(
            "The code is valid for %(minutes)s minutes — until %(time)s.",
            "Код действителен %(minutes)s мин. — до %(time)s.",
            "Kod %(minutes)s dakika geçerlidir — %(time)s'e kadar.",
            "Der Code ist %(minutes)s Minuten gültig – bis %(time)s.",
        ),
        "Qalan vaxt:": t("Time left:", "Осталось:", "Kalan süre:", "Verbleibende Zeit:"),
        "Aşağıdakı «Kodu yenidən göndər» düyməsi ilə yeni kod istəyin.": t(
            "Request a new code with the «Resend code» button below.",
            "Запросите новый код кнопкой «Отправить код повторно» ниже.",
            "Aşağıdaki «Kodu yeniden gönder» düğmesiyle yeni bir kod isteyin.",
            "Fordern Sie mit der Schaltfläche «Code erneut senden» unten einen neuen Code an.",
        ),
        "Kodu yenidən göndər ({s} san.)": t(
            "Resend code ({s} s)",
            "Отправить код повторно ({s} с)",
            "Kodu yeniden gönder ({s} sn.)",
            "Code erneut senden ({s} s)",
        ),
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
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
