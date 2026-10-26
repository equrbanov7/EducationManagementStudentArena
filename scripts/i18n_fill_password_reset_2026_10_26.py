#!/usr/bin/env python3
"""EMSArena i18n — «Parol sıfırlama» səbəb dialoqu + view-as arxiv / «Giriş tarixçəsi» (2026-10-26).

msgid AZ cümlədir → az msgstr = msgid. Şablon `{% blocktrans %}` dəyişəni ``%(limit)s`` formasındadır.
İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "accounts.password_reset": {
        "Səbəb yazılmalıdır (ən azı 10 simvol).": t(
            "A reason is required (at least 10 characters).",
            "Укажите причину (не менее 10 символов).",
            "Bir neden yazılmalıdır (en az 10 karakter).",
            "Eine Begründung ist erforderlich (mindestens 10 Zeichen).",
        ),
        "Müvəqqəti parol yaradıldı. İstifadəçi ilk girişdə e-poçtunu təsdiqləyib öz parolunu qurmağa "
        "məcbur olacaq.": t(
            "A temporary password was created. On first sign-in the user must verify their email and set "
            "their own password.",
            "Временный пароль создан. При первом входе пользователь должен подтвердить e-mail и задать "
            "собственный пароль.",
            "Geçici parola oluşturuldu. Kullanıcı ilk girişte e-postasını doğrulayıp kendi parolasını "
            "belirlemek zorunda olacak.",
            "Ein temporäres Passwort wurde erstellt. Bei der ersten Anmeldung muss der Benutzer seine "
            "E-Mail bestätigen und ein eigenes Passwort festlegen.",
        ),
        "{name} ({username}) üçün yeni müvəqqəti parol yaradılacaq. Köhnə parol dərhal etibarsız olacaq, "
        "bütün açıq sessiyalar bağlanacaq; ilk girişdə istifadəçi e-poçtunu təsdiqləyib öz parolunu quracaq.": t(
            "A new temporary password will be created for {name} ({username}). The old password stops working "
            "immediately and all open sessions are closed; on first sign-in the user verifies their email and "
            "sets their own password.",
            "Для {name} ({username}) будет создан новый временный пароль. Старый пароль сразу перестанет "
            "действовать, все открытые сеансы будут закрыты; при первом входе пользователь подтвердит e-mail "
            "и задаст собственный пароль.",
            "{name} ({username}) için yeni bir geçici parola oluşturulacak. Eski parola hemen geçersiz olacak, "
            "tüm açık oturumlar kapanacak; kullanıcı ilk girişte e-postasını doğrulayıp kendi parolasını "
            "belirleyecek.",
            "Für {name} ({username}) wird ein neues temporäres Passwort erstellt. Das alte Passwort wird sofort "
            "ungültig und alle offenen Sitzungen werden beendet; bei der ersten Anmeldung bestätigt der Benutzer "
            "seine E-Mail und legt ein eigenes Passwort fest.",
        ),
        "Parolu yazmadan sıfırlayın: sistem müvəqqəti parol yaradır və onu bir dəfə göstərir. İstifadəçi ilk "
        "girişdə e-poçtunu təsdiqləyib öz parolunu quracaq. Hər sıfırlama səbəbi ilə audit jurnalına "
        "yazılır.": t(
            "Reset a password without typing one: the system generates a temporary password and shows it once. "
            "On first sign-in the user verifies their email and sets their own password. Every reset is written "
            "to the audit log with its reason.",
            "Сброс пароля без ввода: система создаёт временный пароль и показывает его один раз. При первом "
            "входе пользователь подтверждает e-mail и задаёт собственный пароль. Каждый сброс записывается в "
            "журнал аудита вместе с причиной.",
            "Parola yazmadan sıfırlayın: sistem geçici bir parola oluşturur ve onu bir kez gösterir. Kullanıcı "
            "ilk girişte e-postasını doğrulayıp kendi parolasını belirler. Her sıfırlama nedeniyle birlikte "
            "denetim günlüğüne yazılır.",
            "Passwort zurücksetzen, ohne eines einzugeben: Das System erzeugt ein temporäres Passwort und zeigt "
            "es einmal an. Bei der ersten Anmeldung bestätigt der Benutzer seine E-Mail und legt ein eigenes "
            "Passwort fest. Jedes Zurücksetzen wird mit Begründung im Audit-Protokoll erfasst.",
        ),
        "Səbəb": t("Reason", "Причина", "Neden", "Begründung"),
        "məs. Tələbə parolunu unudub, şəxsiyyət vəsiqəsi ilə yoxlanıldı": t(
            "e.g. Student forgot the password, identity checked with an ID card",
            "напр. Студент забыл пароль, личность проверена по удостоверению",
            "örn. Öğrenci parolasını unuttu, kimlik kartıyla doğrulandı",
            "z. B. Studierende/r hat das Passwort vergessen, Identität per Ausweis geprüft",
        ),
        "Səbəb audit jurnalına yazılır (parol yazılmır).": t(
            "The reason is written to the audit log (the password is not).",
            "Причина записывается в журнал аудита (пароль — нет).",
            "Neden denetim günlüğüne yazılır (parola yazılmaz).",
            "Die Begründung wird im Audit-Protokoll erfasst (das Passwort nicht).",
        ),
        "Səbəb ən azı 10 simvol olmalıdır.": t(
            "The reason must be at least 10 characters long.",
            "Причина должна содержать не менее 10 символов.",
            "Neden en az 10 karakter olmalıdır.",
            "Die Begründung muss mindestens 10 Zeichen lang sein.",
        ),
        "Parol sıfırlansın?": t(
            "Reset the password?", "Сбросить пароль?", "Parola sıfırlansın mı?", "Passwort zurücksetzen?"
        ),
        "Bəli, sıfırla": t("Yes, reset", "Да, сбросить", "Evet, sıfırla", "Ja, zurücksetzen"),
    },
    "accounts.people.page": {
        "Parolu sıfırla": t("Reset password", "Сбросить пароль", "Parolayı sıfırla", "Passwort zurücksetzen"),
    },
    "accounts.view_as": {
        "Məzun / arxiv": t("Graduate / archive", "Выпускник / архив", "Mezun / arşiv", "Absolvent / Archiv"),
        "Arxiv · yalnız baxış": t(
            "Archive · view only", "Архив · только просмотр", "Arşiv · yalnızca görüntüleme", "Archiv · nur Ansicht"
        ),
        "Giriş": t("Sign-in", "Вход", "Oturum açma", "Anmeldung"),
        "Çıxış": t("Sign-out", "Выход", "Çıkış", "Abmeldung"),
        "Giriş tarixçəsi": t("Sign-in history", "История входов", "Giriş geçmişi", "Anmeldeverlauf"),
        "Hesabın son %(limit)s giriş və çıxışı (vaxt, İP ünvanı, brauzer). Yalnız siz görürsünüz — "
        "istifadəçinin öz kabinetində bu panel yoxdur.": t(
            "The account's last %(limit)s sign-ins and sign-outs (time, IP address, browser). Only you can see "
            "this — the user's own cabinet has no such panel.",
            "Последние %(limit)s входов и выходов учётной записи (время, IP-адрес, браузер). Видите только вы — "
            "в кабинете самого пользователя этой панели нет.",
            "Hesabın son %(limit)s giriş ve çıkışı (zaman, IP adresi, tarayıcı). Yalnızca siz görürsünüz — "
            "kullanıcının kendi panelinde bu bölüm yoktur.",
            "Die letzten %(limit)s An- und Abmeldungen des Kontos (Zeit, IP-Adresse, Browser). Nur Sie sehen "
            "dies — im eigenen Bereich des Benutzers gibt es dieses Panel nicht.",
        ),
        "Son giriş:": t("Last sign-in:", "Последний вход:", "Son oturum açma:", "Letzte Anmeldung:"),
        "Vaxt": t("Time", "Время", "Zaman", "Zeit"),
        "Hadisə": t("Event", "Событие", "Olay", "Ereignis"),
        "İP ünvanı": t("IP address", "IP-адрес", "IP adresi", "IP-Adresse"),
        "Brauzer / cihaz": t("Browser / device", "Браузер / устройство", "Tarayıcı / cihaz", "Browser / Gerät"),
        "Bu hesabla sistemə giriş qeydə alınmayıb.": t(
            "No sign-ins have been recorded for this account.",
            "Входы в систему с этой учётной записью не зарегистрированы.",
            "Bu hesapla sisteme giriş kaydedilmemiş.",
            "Für dieses Konto wurden keine Anmeldungen erfasst.",
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
