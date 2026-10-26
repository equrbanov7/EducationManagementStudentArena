#!/usr/bin/env python3
"""EMSArena i18n — «İstifadəçi adını dəyiş» (operator, parolu bilmədən; sahib 2026-10-26).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


RENAME = t("Change username", "Изменить имя пользователя", "Kullanıcı adını değiştir", "Benutzernamen ändern")

ENTRIES = {
    "accounts.username_change_admin": {
        "İstifadəçi adını dəyişmək üçün icazəniz yoxdur.": t(
            "You do not have permission to change usernames.",
            "У вас нет прав на изменение имени пользователя.",
            "Kullanıcı adını değiştirme yetkiniz yok.",
            "Sie haben keine Berechtigung, Benutzernamen zu ändern.",
        ),
        "Başqasının adından baxış rejimində istifadəçi adını dəyişmək olmaz. Əvvəlcə baxış rejimindən "
        "çıxın.": t(
            "Usernames cannot be changed while viewing as another user. Leave view-as mode first.",
            "Нельзя менять имя пользователя в режиме просмотра от чужого имени. Сначала выйдите из этого режима.",
            "Başka bir kullanıcı adına görüntüleme modunda kullanıcı adı değiştirilemez. Önce bu moddan çıkın.",
            "Im Modus „Als anderer Benutzer ansehen“ können keine Benutzernamen geändert werden. Verlassen Sie "
            "zuerst diesen Modus.",
        ),
        "Təşkilatınız hələ təsdiqlənməyib — istifadəçi adını dəyişmək olmaz.": t(
            "Your organization has not been approved yet — usernames cannot be changed.",
            "Ваша организация ещё не подтверждена — менять имя пользователя нельзя.",
            "Kurumunuz henüz onaylanmadı — kullanıcı adı değiştirilemez.",
            "Ihre Organisation ist noch nicht bestätigt — Benutzernamen können nicht geändert werden.",
        ),
        "Superadmin hesabının istifadəçi adı bu bölmədən dəyişdirilə bilməz.": t(
            "A superadmin account's username cannot be changed from this section.",
            "Имя пользователя суперадминистратора нельзя изменить в этом разделе.",
            "Süper yönetici hesabının kullanıcı adı bu bölümden değiştirilemez.",
            "Der Benutzername eines Superadmin-Kontos kann in diesem Bereich nicht geändert werden.",
        ),
        "Öz istifadəçi adınızı bu bölmədən dəyişə bilməzsiniz — «Profil redaktə» bölməsindən istifadə edin.": t(
            "You cannot change your own username here — use the “Edit profile” section.",
            "Свое имя пользователя здесь изменить нельзя — используйте раздел «Редактировать профиль».",
            "Kendi kullanıcı adınızı burada değiştiremezsiniz — «Profili düzenle» bölümünü kullanın.",
            "Ihren eigenen Benutzernamen können Sie hier nicht ändern — nutzen Sie „Profil bearbeiten“.",
        ),
        "Təşkilat sahibinin istifadəçi adını yalnız superadmin dəyişə bilər.": t(
            "Only a superadmin can change the organization owner's username.",
            "Имя пользователя владельца организации может изменить только суперадминистратор.",
            "Kurum sahibinin kullanıcı adını yalnızca süper yönetici değiştirebilir.",
            "Nur ein Superadmin kann den Benutzernamen des Organisationsinhabers ändern.",
        ),
        "Özünüzlə eyni və ya daha yüksək səlahiyyətli istifadəçinin adını dəyişə bilməzsiniz.": t(
            "You cannot change the username of a user with the same or higher authority than yours.",
            "Нельзя изменить имя пользователя с такими же или более высокими полномочиями, чем у вас.",
            "Sizinle aynı veya daha yüksek yetkiye sahip bir kullanıcının adını değiştiremezsiniz.",
            "Sie können den Benutzernamen eines Benutzers mit gleicher oder höherer Berechtigung nicht ändern.",
        ),
        "Səbəb yazılmalıdır (ən azı 10 simvol).": t(
            "A reason is required (at least 10 characters).",
            "Укажите причину (не менее 10 символов).",
            "Bir neden yazılmalıdır (en az 10 karakter).",
            "Eine Begründung ist erforderlich (mindestens 10 Zeichen).",
        ),
        "Yeni istifadəçi adı cari addan fərqli olmalıdır.": t(
            "The new username must differ from the current one.",
            "Новое имя пользователя должно отличаться от текущего.",
            "Yeni kullanıcı adı mevcut addan farklı olmalıdır.",
            "Der neue Benutzername muss sich vom aktuellen unterscheiden.",
        ),
        "Bu istifadəçi adı artıq istifadə olunur.": t(
            "This username is already taken.",
            "Это имя пользователя уже занято.",
            "Bu kullanıcı adı zaten kullanılıyor.",
            "Dieser Benutzername ist bereits vergeben.",
        ),
        "Ad və soyaddan standart istifadəçi adı qurmaq alınmadı — adı əl ilə yazın.": t(
            "Could not build a standard username from the first and last name — type it manually.",
            "Не удалось составить стандартное имя пользователя из имени и фамилии — введите его вручную.",
            "Ad ve soyaddan standart kullanıcı adı oluşturulamadı — adı elle yazın.",
            "Aus Vor- und Nachname konnte kein Standard-Benutzername gebildet werden — bitte manuell eingeben.",
        ),
        "İstifadəçi adı «%(old)s» → «%(new)s» olaraq dəyişdirildi. Parol dəyişmədi; istifadəçi bundan sonra yeni "
        "adla daxil olur.": t(
            "Username changed «%(old)s» → «%(new)s». The password was not changed; the user now signs in with the "
            "new name.",
            "Имя пользователя изменено: «%(old)s» → «%(new)s». Пароль не изменён; теперь пользователь входит под "
            "новым именем.",
            "Kullanıcı adı «%(old)s» → «%(new)s» olarak değiştirildi. Parola değişmedi; kullanıcı artık yeni adla "
            "giriş yapar.",
            "Benutzername geändert: „%(old)s“ → „%(new)s“. Das Passwort wurde nicht geändert; der Benutzer meldet "
            "sich ab jetzt mit dem neuen Namen an.",
        ),
        "İstifadəçi adını dəyiş": RENAME,
        "Dəyişdirilir…": t("Changing…", "Изменение…", "Değiştiriliyor…", "Wird geändert…"),
        "{name} — cari istifadəçi adı: {username}. Parol, açıq sessiyalar və e-poçt təsdiqi dəyişmir; köhnə adla "
        "giriş dərhal işləməz olur.": t(
            "{name} — current username: {username}. The password, open sessions and email verification stay "
            "unchanged; signing in with the old name stops working immediately.",
            "{name} — текущее имя пользователя: {username}. Пароль, открытые сеансы и подтверждение e-mail не "
            "меняются; вход со старым именем сразу перестанет работать.",
            "{name} — mevcut kullanıcı adı: {username}. Parola, açık oturumlar ve e-posta doğrulaması değişmez; "
            "eski adla giriş hemen çalışmaz olur.",
            "{name} — aktueller Benutzername: {username}. Passwort, offene Sitzungen und E-Mail-Bestätigung "
            "bleiben unverändert; die Anmeldung mit dem alten Namen funktioniert sofort nicht mehr.",
        ),
        "Cari ad artıq standart formadadır: {username}.": t(
            "The current name is already in the standard form: {username}.",
            "Текущее имя уже в стандартной форме: {username}.",
            "Mevcut ad zaten standart biçimde: {username}.",
            "Der aktuelle Name hat bereits die Standardform: {username}.",
        ),
        "İstifadəçi adı dəyişdirilsin?": t(
            "Change the username?",
            "Изменить имя пользователя?",
            "Kullanıcı adı değiştirilsin mi?",
            "Benutzernamen ändern?",
        ),
        "məs. Soyad sənəddə fərqli yazılıb, düzəliş tələbənin müraciəti ilə": t(
            "e.g. Surname is spelled differently in the ID document; corrected at the student's request",
            "напр. Фамилия в документе написана иначе, исправлено по заявлению студента",
            "örn. Soyadı belgede farklı yazılmış, öğrencinin başvurusuyla düzeltildi",
            "z. B. Nachname im Ausweis anders geschrieben, auf Antrag des Studierenden korrigiert",
        ),
        "Səbəb audit jurnalına köhnə və yeni adla birlikdə yazılır.": t(
            "The reason is written to the audit log together with the old and new name.",
            "Причина записывается в журнал аудита вместе со старым и новым именем.",
            "Neden, eski ve yeni adla birlikte denetim günlüğüne yazılır.",
            "Die Begründung wird zusammen mit altem und neuem Namen ins Audit-Protokoll geschrieben.",
        ),
        "Bəli, dəyiş": t("Yes, change", "Да, изменить", "Evet, değiştir", "Ja, ändern"),
        "Yeni istifadəçi adı": t("New username", "Новое имя пользователя", "Yeni kullanıcı adı", "Neuer Benutzername"),
        "məs. ad.soyad": t("e.g. name.surname", "напр. ad.soyad", "örn. ad.soyad", "z. B. vorname.nachname"),
        "Avtomatik təklif": t("Auto-suggest", "Предложить автоматически", "Otomatik öneri", "Automatisch vorschlagen"),
        "3–30 simvol: latın hərfləri (a–z), rəqəmlər, nöqtə, alt xətt, defis. Böyük hərflər kiçiyə "
        "çevrilir.": t(
            "3–30 characters: Latin letters (a–z), digits, dot, underscore, hyphen. Capitals are lowercased.",
            "3–30 символов: латинские буквы (a–z), цифры, точка, подчёркивание, дефис. Заглавные буквы "
            "переводятся в строчные.",
            "3–30 karakter: Latin harfleri (a–z), rakamlar, nokta, alt çizgi, kısa çizgi. Büyük harfler küçüğe "
            "çevrilir.",
            "3–30 Zeichen: lateinische Buchstaben (a–z), Ziffern, Punkt, Unterstrich, Bindestrich. "
            "Großbuchstaben werden kleingeschrieben.",
        ),
    },
    "accounts.username_change": {
        "Dəyişikliyi RİM əməkdaşı etdi; parolunuz dəyişməyib. Sualınız varsa, RİM-ə müraciət edin.": t(
            "The change was made by RİM staff; your password has not changed. If you have questions, contact RİM.",
            "Изменение внёс сотрудник RİM; ваш пароль не изменился. Если есть вопросы, обратитесь в RİM.",
            "Değişikliği RİM çalışanı yaptı; parolanız değişmedi. Sorunuz varsa RİM'e başvurun.",
            "Die Änderung wurde von RİM-Mitarbeitenden vorgenommen; Ihr Passwort ist unverändert. Bei Fragen "
            "wenden Sie sich an RİM.",
        ),
    },
    "profile.sidebar": {
        "Parol və istifadəçi adı": t(
            "Password & username", "Пароль и имя пользователя", "Parola ve kullanıcı adı", "Passwort & Benutzername"
        ),
    },
    "accounts.people.page": {
        "İstifadəçi adını dəyiş": RENAME,
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
