#!/usr/bin/env python3
"""EMSArena i18n — «Profil redaktə → İstifadəçi adı» kartı + «Sistem tənzimləmələri» açarları (2026-10-20).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RS = "core.runtime_settings"
UC = "accounts.username_change"
UCE = "accounts.username_change.email"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    RS: {
        "İstifadəçi öz istifadəçi adını dəyişə bilər": t(
            "Users can change their own username",
            "Пользователь может сам изменить своё имя пользователя",
            "Kullanıcı kendi kullanıcı adını değiştirebilir",
            "Benutzer können ihren Benutzernamen selbst ändern",
        ),
        "Yandırılanda tələbə və əməkdaş «Profil redaktə» bölməsində mövcud parolu ilə təsdiqləyərək öz "
        "istifadəçi adını dəyişə bilir; köhnə ad dərhal işləməz olur. Söndürüləndə həmin hissə gizlənir və "
        "server dəyişikliyi qəbul etmir.": t(
            "When turned on, students and staff can change their own username in the “Edit profile” section by "
            "confirming with their current password; the old name stops working immediately. When turned off, "
            "the card is hidden and the server rejects the change.",
            "Если включено, студенты и сотрудники могут изменить своё имя пользователя в разделе «Редактирование "
            "профиля», подтвердив текущим паролем; старое имя сразу перестаёт работать. Если выключено, блок "
            "скрывается, а сервер отклоняет изменение.",
            "Açıldığında öğrenciler ve personel “Profili düzenle” bölümünde mevcut parolalarıyla onaylayarak kendi "
            "kullanıcı adlarını değiştirebilir; eski ad hemen geçersiz olur. Kapatıldığında bu bölüm gizlenir ve "
            "sunucu değişikliği kabul etmez.",
            "Wenn eingeschaltet, können Studierende und Mitarbeitende im Bereich „Profil bearbeiten“ ihren "
            "Benutzernamen nach Bestätigung mit dem aktuellen Passwort ändern; der alte Name funktioniert sofort "
            "nicht mehr. Wenn ausgeschaltet, wird der Bereich ausgeblendet und der Server lehnt die Änderung ab.",
        ),
        "İstifadəçi adı dəyişmələri arasındakı müddət": t(
            "Waiting period between username changes",
            "Интервал между изменениями имени пользователя",
            "Kullanıcı adı değişiklikleri arasındaki süre",
            "Wartezeit zwischen Änderungen des Benutzernamens",
        ),
        "Uğurlu dəyişiklikdən sonra neçə gün keçməlidir ki, istifadəçi adını yenidən dəyişmək mümkün olsun. "
        "0 — məhdudiyyət yoxdur.": t(
            "How many days must pass after a successful change before the username can be changed again. "
            "0 — no limit.",
            "Сколько дней должно пройти после успешного изменения, прежде чем имя пользователя можно будет "
            "изменить снова. 0 — без ограничений.",
            "Başarılı bir değişiklikten sonra kullanıcı adının yeniden değiştirilebilmesi için kaç gün geçmesi "
            "gerektiği. 0 — sınır yok.",
            "Wie viele Tage nach einer erfolgreichen Änderung vergehen müssen, bevor der Benutzername erneut "
            "geändert werden kann. 0 — keine Begrenzung.",
        ),
        "gün": t("days", "дн.", "gün", "Tage"),
    },
    UC: {
        # ── Servis xətaları / uğur ──
        "Yeni istifadəçi adını yazın.": t(
            "Enter the new username.",
            "Введите новое имя пользователя.",
            "Yeni kullanıcı adını girin.",
            "Geben Sie den neuen Benutzernamen ein.",
        ),
        "İstifadəçi adı %(min)s–%(max)s simvol olmalıdır.": t(
            "The username must be %(min)s–%(max)s characters long.",
            "Имя пользователя должно содержать %(min)s–%(max)s символов.",
            "Kullanıcı adı %(min)s–%(max)s karakter olmalıdır.",
            "Der Benutzername muss %(min)s–%(max)s Zeichen lang sein.",
        ),
        "İstifadəçi adında yalnız latın hərfləri (a–z), rəqəmlər, nöqtə, alt xətt və defis ola bilər; ad "
        "hərflə başlamalı, hərf və ya rəqəmlə bitməlidir, iki ayırıcı yan-yana gələ bilməz.": t(
            "A username may contain only Latin letters (a–z), digits, dots, underscores and hyphens; it must start "
            "with a letter, end with a letter or digit, and two separators cannot follow each other.",
            "Имя пользователя может содержать только латинские буквы (a–z), цифры, точку, подчёркивание и дефис; "
            "оно должно начинаться с буквы, заканчиваться буквой или цифрой, два разделителя подряд недопустимы.",
            "Kullanıcı adı yalnızca Latin harfleri (a–z), rakamlar, nokta, alt çizgi ve kısa çizgi içerebilir; harfle "
            "başlamalı, harf veya rakamla bitmelidir ve iki ayırıcı yan yana gelemez.",
            "Ein Benutzername darf nur lateinische Buchstaben (a–z), Ziffern, Punkte, Unterstriche und Bindestriche "
            "enthalten; er muss mit einem Buchstaben beginnen, mit einem Buchstaben oder einer Ziffer enden, und "
            "zwei Trennzeichen dürfen nicht aufeinander folgen.",
        ),
        "Bu istifadəçi adı sistem üçün ayrılıb, başqasını seçin.": t(
            "This username is reserved for the system; choose another one.",
            "Это имя пользователя зарезервировано системой, выберите другое.",
            "Bu kullanıcı adı sistem için ayrılmıştır, başka bir ad seçin.",
            "Dieser Benutzername ist für das System reserviert; wählen Sie einen anderen.",
        ),
        "İstifadəçi adını yenidən %(date)s tarixindən sonra dəyişə bilərsiniz.": t(
            "You can change your username again after %(date)s.",
            "Вы сможете снова изменить имя пользователя после %(date)s.",
            "Kullanıcı adınızı %(date)s tarihinden sonra yeniden değiştirebilirsiniz.",
            "Sie können Ihren Benutzernamen nach dem %(date)s erneut ändern.",
        ),
        "Çox sayda cəhd edildi. %(minutes)s dəqiqə sonra yenidən yoxlayın.": t(
            "Too many attempts. Try again in %(minutes)s minutes.",
            "Слишком много попыток. Повторите через %(minutes)s мин.",
            "Çok fazla deneme yapıldı. %(minutes)s dakika sonra tekrar deneyin.",
            "Zu viele Versuche. Versuchen Sie es in %(minutes)s Minuten erneut.",
        ),
        "Bu istifadəçi adı artıq istifadə olunur.": t(
            "This username is already taken.",
            "Это имя пользователя уже занято.",
            "Bu kullanıcı adı zaten kullanılıyor.",
            "Dieser Benutzername ist bereits vergeben.",
        ),
        "İstifadəçi adını dəyişmək hazırda mümkün deyil.": t(
            "Changing the username is currently not possible.",
            "Изменение имени пользователя сейчас недоступно.",
            "Kullanıcı adını değiştirmek şu anda mümkün değil.",
            "Das Ändern des Benutzernamens ist derzeit nicht möglich.",
        ),
        "Yeni istifadəçi adı cari addan fərqli olmalıdır.": t(
            "The new username must differ from the current one.",
            "Новое имя пользователя должно отличаться от текущего.",
            "Yeni kullanıcı adı mevcut addan farklı olmalıdır.",
            "Der neue Benutzername muss sich vom aktuellen unterscheiden.",
        ),
        "Cari parol yanlışdır.": t(
            "The current password is incorrect.",
            "Текущий пароль неверен.",
            "Mevcut parola yanlış.",
            "Das aktuelle Passwort ist falsch.",
        ),
        "İstifadəçi adınız «%(new)s» olaraq dəyişdirildi. Bundan sonra sistemə bu adla (və ya e-poçtunuzla) daxil "
        "olun — köhnə ad artıq işləmir.": t(
            "Your username has been changed to “%(new)s”. From now on, sign in with this name (or your email) — "
            "the old name no longer works.",
            "Ваше имя пользователя изменено на «%(new)s». Теперь входите в систему с этим именем (или своей "
            "эл. почтой) — старое имя больше не работает.",
            "Kullanıcı adınız “%(new)s” olarak değiştirildi. Bundan sonra sisteme bu adla (veya e-postanızla) giriş "
            "yapın — eski ad artık çalışmıyor.",
            "Ihr Benutzername wurde in „%(new)s“ geändert. Melden Sie sich ab jetzt mit diesem Namen (oder Ihrer "
            "E-Mail-Adresse) an — der alte Name funktioniert nicht mehr.",
        ),
        # ── Bildiriş / e-poçt mətni ──
        "İstifadəçi adınız dəyişdirildi": t(
            "Your username has been changed",
            "Ваше имя пользователя изменено",
            "Kullanıcı adınız değiştirildi",
            "Ihr Benutzername wurde geändert",
        ),
        "İstifadəçi adınız dəyişdirildi: %(old)s → %(new)s.": t(
            "Your username has been changed: %(old)s → %(new)s.",
            "Ваше имя пользователя изменено: %(old)s → %(new)s.",
            "Kullanıcı adınız değiştirildi: %(old)s → %(new)s.",
            "Ihr Benutzername wurde geändert: %(old)s → %(new)s.",
        ),
        "Bundan sonra sistemə yeni adla və ya e-poçtunuzla daxil olun; köhnə ad artıq işləmir.": t(
            "From now on, sign in with the new name or your email; the old name no longer works.",
            "Теперь входите в систему с новым именем или своей эл. почтой; старое имя больше не работает.",
            "Bundan sonra sisteme yeni adla veya e-postanızla giriş yapın; eski ad artık çalışmıyor.",
            "Melden Sie sich ab jetzt mit dem neuen Namen oder Ihrer E-Mail-Adresse an; der alte Name funktioniert "
            "nicht mehr.",
        ),
        "Bu dəyişikliyi siz etməmisinizsə, dərhal RİM-ə müraciət edin.": t(
            "If you did not make this change, contact the RİM office immediately.",
            "Если это изменение сделали не вы, немедленно обратитесь в RİM.",
            "Bu değişikliği siz yapmadıysanız hemen RİM’e başvurun.",
            "Wenn Sie diese Änderung nicht vorgenommen haben, wenden Sie sich sofort an das RİM.",
        ),
        # ── Kart (şablon) ──
        "İstifadəçi adı": t("Username", "Имя пользователя", "Kullanıcı adı", "Benutzername"),
        "%(min)s–%(max)s simvol: latın hərfləri (a–z), rəqəmlər, nöqtə, alt xətt və defis; hərflə başlayır. "
        "Dəyişiklikdən sonra sistemə yeni adla və ya e-poçtunuzla daxil olursunuz, köhnə ad işləmir.": t(
            "%(min)s–%(max)s characters: Latin letters (a–z), digits, dots, underscores and hyphens; starts with a "
            "letter. After the change you sign in with the new name or your email; the old name stops working.",
            "%(min)s–%(max)s символов: латинские буквы (a–z), цифры, точка, подчёркивание и дефис; начинается с "
            "буквы. После изменения вы входите с новым именем или своей эл. почтой, старое имя не работает.",
            "%(min)s–%(max)s karakter: Latin harfleri (a–z), rakamlar, nokta, alt çizgi ve kısa çizgi; harfle "
            "başlar. Değişiklikten sonra sisteme yeni adla veya e-postanızla giriş yaparsınız, eski ad çalışmaz.",
            "%(min)s–%(max)s Zeichen: lateinische Buchstaben (a–z), Ziffern, Punkte, Unterstriche und Bindestriche; "
            "beginnt mit einem Buchstaben. Nach der Änderung melden Sie sich mit dem neuen Namen oder Ihrer "
            "E-Mail-Adresse an; der alte Name funktioniert nicht mehr.",
        ),
        "Növbəti dəyişikliyə qədər gözləmə müddəti: %(days)s gün.": t(
            "Waiting period before the next change: %(days)s day(s).",
            "Интервал до следующего изменения: %(days)s дн.",
            "Bir sonraki değişikliğe kadar bekleme süresi: %(days)s gün.",
            "Wartezeit bis zur nächsten Änderung: %(days)s Tag(e).",
        ),
        "İstifadəçi adınız dəyişdiriləcək. Bundan sonra sistemə yalnız yeni adla və ya e-poçtunuzla daxil ola "
        "biləcəksiniz. Davam edilsin?": t(
            "Your username will be changed. From then on you can sign in only with the new name or your email. "
            "Continue?",
            "Ваше имя пользователя будет изменено. После этого вы сможете войти только с новым именем или своей "
            "эл. почтой. Продолжить?",
            "Kullanıcı adınız değiştirilecek. Bundan sonra sisteme yalnızca yeni adla veya e-postanızla giriş "
            "yapabileceksiniz. Devam edilsin mi?",
            "Ihr Benutzername wird geändert. Danach können Sie sich nur noch mit dem neuen Namen oder Ihrer "
            "E-Mail-Adresse anmelden. Fortfahren?",
        ),
        "Cari istifadəçi adı": t(
            "Current username", "Текущее имя пользователя", "Mevcut kullanıcı adı", "Aktueller Benutzername"
        ),
        "Yeni istifadəçi adı": t("New username", "Новое имя пользователя", "Yeni kullanıcı adı", "Neuer Benutzername"),
        "məs.: ad.soyad": t("e.g. name.surname", "напр.: imya.familiya", "örn.: ad.soyad", "z. B. vorname.nachname"),
        "Cari parol": t("Current password", "Текущий пароль", "Mevcut parola", "Aktuelles Passwort"),
        "Dəyişikliyi təsdiqləmək üçün mövcud parolunuzu yazın.": t(
            "Enter your current password to confirm the change.",
            "Введите текущий пароль, чтобы подтвердить изменение.",
            "Değişikliği onaylamak için mevcut parolanızı girin.",
            "Geben Sie Ihr aktuelles Passwort ein, um die Änderung zu bestätigen.",
        ),
        "İstifadəçi adını dəyiş": t(
            "Change username", "Изменить имя пользователя", "Kullanıcı adını değiştir", "Benutzernamen ändern"
        ),
    },
    UCE: {
        "Hörmətli": t("Dear", "Уважаемый(-ая)", "Sayın", "Guten Tag"),
        "Kabinetə keç": t("Go to your account", "Перейти в кабинет", "Hesabıma git", "Zum Benutzerkonto"),
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
