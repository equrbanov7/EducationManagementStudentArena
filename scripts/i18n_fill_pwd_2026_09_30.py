#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-30 «Parol sıfırlama» bölməsi (PWD, `account.password_reset`).

Əlavə olunan mətnlər:
  * `accounts.password_reset` — bölmə paneli (şablon), JS mətnləri (`json_script`),
    servis xəta mesajları, uğur mesajı, status etiketləri;
  * `organizations.permission.label` — icazə redaktorunda açarın etiketi;
  * `profile.sidebar` — qabıq başlığı «Parol sıfırlama» (NAV menyu bəndi ilə eyni mətn).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_pwd_2026_09_30.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

P = "accounts.password_reset"
PERM = "organizations.permission.label"
SB = "profile.sidebar"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    PERM: {
        "Parolu sıfırlamaq (müvəqqəti parol vermək, ilk girişdə dəyişmək məcburi)": {
            "az": "Parolu sıfırlamaq (müvəqqəti parol vermək, ilk girişdə dəyişmək məcburi)",
            "en": "Reset passwords (issue a temporary password; change required at first login)",
            "ru": "Сбрасывать пароли (выдавать временный пароль, смена при первом входе обязательна)",
            "tr": "Parola sıfırlama (geçici parola verme, ilk girişte değiştirmek zorunlu)",
        },
    },
    SB: {
        "Parol sıfırlama": {
            "az": "Parol sıfırlama",
            "en": "Password reset",
            "ru": "Сброс пароля",
            "tr": "Parola sıfırlama",
        },
    },
    P: {
        # ── Servis xəta mesajları ────────────────────────────────────────────
        "Parol sıfırlamaq üçün icazəniz yoxdur.": {
            "az": "Parol sıfırlamaq üçün icazəniz yoxdur.",
            "en": "You do not have permission to reset passwords.",
            "ru": "У вас нет права сбрасывать пароли.",
            "tr": "Parola sıfırlama yetkiniz yok.",
        },
        "Başqasının adından baxış rejimində parol sıfırlamaq olmaz. Əvvəlcə baxış rejimindən çıxın.": {
            "az": "Başqasının adından baxış rejimində parol sıfırlamaq olmaz. Əvvəlcə baxış rejimindən çıxın.",
            "en": "Passwords cannot be reset while viewing as another user. Exit view-as mode first.",
            "ru": "Нельзя сбрасывать пароли в режиме просмотра от имени другого пользователя. "
            "Сначала выйдите из этого режима.",
            "tr": "Başka bir kullanıcı adına görüntüleme modunda parola sıfırlanamaz. Önce bu moddan çıkın.",
        },
        "Təşkilatınız hələ təsdiqlənməyib — parol sıfırlamaq olmaz.": {
            "az": "Təşkilatınız hələ təsdiqlənməyib — parol sıfırlamaq olmaz.",
            "en": "Your organization has not been approved yet — passwords cannot be reset.",
            "ru": "Ваша организация ещё не одобрена — сбрасывать пароли нельзя.",
            "tr": "Kurumunuz henüz onaylanmadı — parola sıfırlanamaz.",
        },
        "Aktiv təşkilat seçilməyib.": {
            "az": "Aktiv təşkilat seçilməyib.",
            "en": "No active organization is selected.",
            "ru": "Активная организация не выбрана.",
            "tr": "Etkin kurum seçilmedi.",
        },
        "İstifadəçi seçilməyib.": {
            "az": "İstifadəçi seçilməyib.",
            "en": "No user selected.",
            "ru": "Пользователь не выбран.",
            "tr": "Kullanıcı seçilmedi.",
        },
        "İstifadəçi tapılmadı.": {
            "az": "İstifadəçi tapılmadı.",
            "en": "User not found.",
            "ru": "Пользователь не найден.",
            "tr": "Kullanıcı bulunamadı.",
        },
        "Superadmin hesabının parolu bu bölmədən sıfırlana bilməz.": {
            "az": "Superadmin hesabının parolu bu bölmədən sıfırlana bilməz.",
            "en": "A superadmin account's password cannot be reset here.",
            "ru": "Пароль учётной записи суперадминистратора нельзя сбросить здесь.",
            "tr": "Süper yönetici hesabının parolası buradan sıfırlanamaz.",
        },
        "Öz parolunuzu bu bölmədən sıfırlaya bilməzsiniz — «Parolu dəyiş» bölməsindən istifadə edin.": {
            "az": "Öz parolunuzu bu bölmədən sıfırlaya bilməzsiniz — «Parolu dəyiş» bölməsindən istifadə edin.",
            "en": "You cannot reset your own password here — use the “Change password” section.",
            "ru": "Нельзя сбросить собственный пароль здесь — воспользуйтесь разделом «Сменить пароль».",
            "tr": "Kendi parolanızı buradan sıfırlayamazsınız — «Parolayı değiştir» bölümünü kullanın.",
        },
        "Təşkilat sahibinin parolunu yalnız superadmin sıfırlaya bilər.": {
            "az": "Təşkilat sahibinin parolunu yalnız superadmin sıfırlaya bilər.",
            "en": "Only a superadmin can reset the organization owner's password.",
            "ru": "Пароль владельца организации может сбросить только суперадминистратор.",
            "tr": "Kurum sahibinin parolasını yalnızca süper yönetici sıfırlayabilir.",
        },
        "Özünüzlə eyni və ya daha yüksək səlahiyyətli istifadəçinin parolunu sıfırlaya bilməzsiniz.": {
            "az": "Özünüzlə eyni və ya daha yüksək səlahiyyətli istifadəçinin parolunu sıfırlaya bilməzsiniz.",
            "en": "You cannot reset the password of a user with the same or a higher role level than yours.",
            "ru": "Нельзя сбросить пароль пользователя с таким же или более высоким уровнем полномочий.",
            "tr": "Sizinle aynı veya daha yüksek yetkiye sahip kullanıcının parolasını sıfırlayamazsınız.",
        },
        "Hesab silinib — əvvəlcə RİM mərkəzindən bərpa olunmalıdır.": {
            "az": "Hesab silinib — əvvəlcə RİM mərkəzindən bərpa olunmalıdır.",
            "en": "The account has been deleted — restore it in the RİM centre first.",
            "ru": "Учётная запись удалена — сначала восстановите её в центре RİM.",
            "tr": "Hesap silinmiş — önce RİM merkezinden geri yüklenmelidir.",
        },
        "Hesab bloklanıb — əvvəlcə RİM mərkəzindən blokdan çıxarılmalıdır.": {
            "az": "Hesab bloklanıb — əvvəlcə RİM mərkəzindən blokdan çıxarılmalıdır.",
            "en": "The account is blocked — unblock it in the RİM centre first.",
            "ru": "Учётная запись заблокирована — сначала разблокируйте её в центре RİM.",
            "tr": "Hesap engellenmiş — önce RİM merkezinden engeli kaldırılmalıdır.",
        },
        "Bu hesabla sistemə giriş bağlıdır (məzun/xaric arxivi və ya tamamlanmamış idxal).": {
            "az": "Bu hesabla sistemə giriş bağlıdır (məzun/xaric arxivi və ya tamamlanmamış idxal).",
            "en": "Sign-in is closed for this account (graduate/expelled archive or an unfinished import).",
            "ru": "Вход для этой учётной записи закрыт (архив выпускников/отчисленных или незавершённый импорт).",
            "tr": "Bu hesapla giriş kapalı (mezun/kaydı silinmiş arşivi veya tamamlanmamış içe aktarma).",
        },
        "Çox sayda sorğu göndərildi. Bir az sonra yenidən cəhd edin.": {
            "az": "Çox sayda sorğu göndərildi. Bir az sonra yenidən cəhd edin.",
            "en": "Too many requests. Please try again a little later.",
            "ru": "Слишком много запросов. Повторите попытку немного позже.",
            "tr": "Çok fazla istek gönderildi. Biraz sonra tekrar deneyin.",
        },
        "Ən azı 2 simvol daxil edin.": {
            "az": "Ən azı 2 simvol daxil edin.",
            "en": "Enter at least 2 characters.",
            "ru": "Введите не менее 2 символов.",
            "tr": "En az 2 karakter girin.",
        },
        "Parol yaradıla bilmədi. Yenidən cəhd edin.": {
            "az": "Parol yaradıla bilmədi. Yenidən cəhd edin.",
            "en": "The password could not be generated. Please try again.",
            "ru": "Не удалось сгенерировать пароль. Повторите попытку.",
            "tr": "Parola oluşturulamadı. Tekrar deneyin.",
        },
        # ── Status etiketləri / kart ─────────────────────────────────────────
        "Aktiv": {"az": "Aktiv", "en": "Active", "ru": "Активна", "tr": "Etkin"},
        "Bloklanıb": {"az": "Bloklanıb", "en": "Blocked", "ru": "Заблокирована", "tr": "Engellendi"},
        "Silinib": {"az": "Silinib", "en": "Deleted", "ru": "Удалена", "tr": "Silindi"},
        "Giriş bağlıdır": {"az": "Giriş bağlıdır", "en": "Sign-in closed", "ru": "Вход закрыт", "tr": "Giriş kapalı"},
        "Heç vaxt daxil olmayıb": {
            "az": "Heç vaxt daxil olmayıb",
            "en": "Never signed in",
            "ru": "Ни разу не входил(а)",
            "tr": "Hiç giriş yapmadı",
        },
        "Müvəqqəti parol yaradıldı. İstifadəçi ilk girişdə öz parolunu qurmağa məcbur olacaq.": {
            "az": "Müvəqqəti parol yaradıldı. İstifadəçi ilk girişdə öz parolunu qurmağa məcbur olacaq.",
            "en": "A temporary password has been created. The user will have to set their own password at first sign-in.",
            "ru": "Временный пароль создан. При первом входе пользователь будет обязан задать собственный пароль.",
            "tr": "Geçici parola oluşturuldu. Kullanıcı ilk girişte kendi parolasını belirlemek zorunda kalacak.",
        },
        # ── JS mətnləri (json_script) ────────────────────────────────────────
        "Axtarılır…": {"az": "Axtarılır…", "en": "Searching…", "ru": "Поиск…", "tr": "Aranıyor…"},
        "Heç kim tapılmadı. İstifadəçi adını yoxlayın və ya ad və soyadla axtarın.": {
            "az": "Heç kim tapılmadı. İstifadəçi adını yoxlayın və ya ad və soyadla axtarın.",
            "en": "No one found. Check the username or search by first and last name.",
            "ru": "Никто не найден. Проверьте имя пользователя или ищите по имени и фамилии.",
            "tr": "Kimse bulunamadı. Kullanıcı adını kontrol edin veya ad ve soyadla arayın.",
        },
        "Nəticə çoxdur — yalnız ilk 8-i göstərilir. Sorğunu dəqiqləşdirin.": {
            "az": "Nəticə çoxdur — yalnız ilk 8-i göstərilir. Sorğunu dəqiqləşdirin.",
            "en": "Too many results — only the first 8 are shown. Refine your search.",
            "ru": "Слишком много результатов — показаны только первые 8. Уточните запрос.",
            "tr": "Çok fazla sonuç — yalnızca ilk 8'i gösteriliyor. Aramanızı daraltın.",
        },
        "Şəxsiyyəti sənədlə yoxlayın və yalnız sonra parolu sıfırlayın.": {
            "az": "Şəxsiyyəti sənədlə yoxlayın və yalnız sonra parolu sıfırlayın.",
            "en": "Verify the person's identity with a document before resetting the password.",
            "ru": "Проверьте личность по документу и только затем сбрасывайте пароль.",
            "tr": "Kimliği bir belgeyle doğrulayın ve ancak ondan sonra parolayı sıfırlayın.",
        },
        "İstifadəçi adı": {"az": "İstifadəçi adı", "en": "Username", "ru": "Имя пользователя", "tr": "Kullanıcı adı"},
        "Rol": {"az": "Rol", "en": "Role", "ru": "Роль", "tr": "Rol"},
        "Qrup / bölmə": {
            "az": "Qrup / bölmə",
            "en": "Group / unit",
            "ru": "Группа / подразделение",
            "tr": "Grup / birim",
        },
        "Son giriş": {"az": "Son giriş", "en": "Last sign-in", "ru": "Последний вход", "tr": "Son giriş"},
        "Əvvəlki müvəqqəti parol hələ dəyişdirilməyib": {
            "az": "Əvvəlki müvəqqəti parol hələ dəyişdirilməyib",
            "en": "The previous temporary password has not been changed yet",
            "ru": "Предыдущий временный пароль ещё не изменён",
            "tr": "Önceki geçici parola henüz değiştirilmedi",
        },
        "Parolu sıfırla": {
            "az": "Parolu sıfırla",
            "en": "Reset password",
            "ru": "Сбросить пароль",
            "tr": "Parolayı sıfırla",
        },
        "Sıfırlanır…": {"az": "Sıfırlanır…", "en": "Resetting…", "ru": "Сброс…", "tr": "Sıfırlanıyor…"},
        "Parol sıfırlansın?": {
            "az": "Parol sıfırlansın?",
            "en": "Reset the password?",
            "ru": "Сбросить пароль?",
            "tr": "Parola sıfırlansın mı?",
        },
        (
            "{name} ({username}) üçün yeni müvəqqəti parol yaradılacaq.\n"
            "Köhnə parol dərhal etibarsız olacaq, istifadəçinin bütün açıq sessiyaları bağlanacaq.\n"
            "İstifadəçinin şəxsiyyətini yoxladınız?"
        ): {
            "az": "{name} ({username}) üçün yeni müvəqqəti parol yaradılacaq.\n"
            "Köhnə parol dərhal etibarsız olacaq, istifadəçinin bütün açıq sessiyaları bağlanacaq.\n"
            "İstifadəçinin şəxsiyyətini yoxladınız?",
            "en": "A new temporary password will be created for {name} ({username}).\n"
            "The old password stops working immediately and all of the user's open sessions will be closed.\n"
            "Have you verified the user's identity?",
            "ru": "Для {name} ({username}) будет создан новый временный пароль.\n"
            "Старый пароль сразу перестанет действовать, все открытые сеансы пользователя будут закрыты.\n"
            "Вы проверили личность пользователя?",
            "tr": "{name} ({username}) için yeni bir geçici parola oluşturulacak.\n"
            "Eski parola hemen geçersiz olacak ve kullanıcının tüm açık oturumları kapatılacak.\n"
            "Kullanıcının kimliğini doğruladınız mı?",
        },
        "Bəli, sıfırla": {"az": "Bəli, sıfırla", "en": "Yes, reset", "ru": "Да, сбросить", "tr": "Evet, sıfırla"},
        "{name} ({username}) üçün müvəqqəti parol:": {
            "az": "{name} ({username}) üçün müvəqqəti parol:",
            "en": "Temporary password for {name} ({username}):",
            "ru": "Временный пароль для {name} ({username}):",
            "tr": "{name} ({username}) için geçici parola:",
        },
        "Parol kopyalandı.": {
            "az": "Parol kopyalandı.",
            "en": "Password copied.",
            "ru": "Пароль скопирован.",
            "tr": "Parola kopyalandı.",
        },
        "Kopyalamaq alınmadı — parolu əl ilə yazın.": {
            "az": "Kopyalamaq alınmadı — parolu əl ilə yazın.",
            "en": "Copying failed — write the password down manually.",
            "ru": "Не удалось скопировать — перепишите пароль вручную.",
            "tr": "Kopyalanamadı — parolayı elle yazın.",
        },
        "Xəta baş verdi. Yenidən cəhd edin.": {
            "az": "Xəta baş verdi. Yenidən cəhd edin.",
            "en": "Something went wrong. Please try again.",
            "ru": "Произошла ошибка. Повторите попытку.",
            "tr": "Bir hata oluştu. Tekrar deneyin.",
        },
        # ── Şablon (bölmə paneli) ────────────────────────────────────────────
        (
            "Parolunu unudan istifadəçiyə müvəqqəti parol verin. İstifadəçi ilk girişdə öz parolunu "
            "qurmağa məcbur olacaq. Hər sıfırlama audit jurnalına yazılır."
        ): {
            "az": "Parolunu unudan istifadəçiyə müvəqqəti parol verin. İstifadəçi ilk girişdə öz parolunu "
            "qurmağa məcbur olacaq. Hər sıfırlama audit jurnalına yazılır.",
            "en": "Give a user who forgot their password a temporary one. They will have to set their own "
            "password at first sign-in. Every reset is recorded in the audit log.",
            "ru": "Выдайте пользователю, забывшему пароль, временный пароль. При первом входе он будет обязан "
            "задать собственный пароль. Каждый сброс записывается в журнал аудита.",
            "tr": "Parolasını unutan kullanıcıya geçici bir parola verin. Kullanıcı ilk girişte kendi parolasını "
            "belirlemek zorunda kalacak. Her sıfırlama denetim günlüğüne kaydedilir.",
        },
        "İstifadəçini tapın": {
            "az": "İstifadəçini tapın",
            "en": "Find the user",
            "ru": "Найдите пользователя",
            "tr": "Kullanıcıyı bulun",
        },
        "İstifadəçi adını dəqiq yazın (məs. ad.soyad) və ya ad və soyadla axtarın.": {
            "az": "İstifadəçi adını dəqiq yazın (məs. ad.soyad) və ya ad və soyadla axtarın.",
            "en": "Type the exact username (e.g. name.surname) or search by first and last name.",
            "ru": "Введите точное имя пользователя (напр. имя.фамилия) или ищите по имени и фамилии.",
            "tr": "Kullanıcı adını tam yazın (ör. ad.soyad) veya ad ve soyadla arayın.",
        },
        "Axtarış yalnız «%(org)s» daxilindədir.": {
            "az": "Axtarış yalnız «%(org)s» daxilindədir.",
            "en": "The search covers “%(org)s” only.",
            "ru": "Поиск ведётся только в «%(org)s».",
            "tr": "Arama yalnızca «%(org)s» içinde yapılır.",
        },
        "İstifadəçi adı və ya ad, soyad": {
            "az": "İstifadəçi adı və ya ad, soyad",
            "en": "Username or first and last name",
            "ru": "Имя пользователя или имя и фамилия",
            "tr": "Kullanıcı adı veya ad, soyad",
        },
        "məs. aysel.quliyeva və ya Quliyeva Aysel": {
            "az": "məs. aysel.quliyeva və ya Quliyeva Aysel",
            "en": "e.g. aysel.quliyeva or Quliyeva Aysel",
            "ru": "напр. aysel.quliyeva или Quliyeva Aysel",
            "tr": "ör. aysel.quliyeva veya Quliyeva Aysel",
        },
        "Axtar": {"az": "Axtar", "en": "Search", "ru": "Найти", "tr": "Ara"},
        "Müvəqqəti parol": {
            "az": "Müvəqqəti parol",
            "en": "Temporary password",
            "ru": "Временный пароль",
            "tr": "Geçici parola",
        },
        "Kopyala": {"az": "Kopyala", "en": "Copy", "ru": "Копировать", "tr": "Kopyala"},
        "Bu parol bir daha göstərilməyəcək": {
            "az": "Bu parol bir daha göstərilməyəcək",
            "en": "This password will not be shown again",
            "ru": "Этот пароль больше не будет показан",
            "tr": "Bu parola bir daha gösterilmeyecek",
        },
        (
            "Parolu istifadəçiyə indi verin. İlk girişdə istifadəçi email ünvanını təsdiqləyib öz parolunu "
            "quracaq — o vaxta qədər sistemin heç bir bölməsi açılmayacaq."
        ): {
            "az": "Parolu istifadəçiyə indi verin. İlk girişdə istifadəçi email ünvanını təsdiqləyib öz parolunu "
            "quracaq — o vaxta qədər sistemin heç bir bölməsi açılmayacaq.",
            "en": "Give the password to the user now. At first sign-in they will confirm their email address and "
            "set their own password — until then no part of the system will open.",
            "ru": "Передайте пароль пользователю сейчас. При первом входе он подтвердит адрес электронной почты "
            "и задаст собственный пароль — до этого ни один раздел системы не откроется.",
            "tr": "Parolayı kullanıcıya şimdi verin. İlk girişte kullanıcı e-posta adresini doğrulayıp kendi "
            "parolasını belirleyecek — o zamana kadar sistemin hiçbir bölümü açılmayacak.",
        },
        "Verdim — parolu gizlət": {
            "az": "Verdim — parolu gizlət",
            "en": "Handed over — hide the password",
            "ru": "Передал(а) — скрыть пароль",
            "tr": "Verdim — parolayı gizle",
        },
    },
}

#: Mövcud, lakin səhv tərcümələri üstələmək üçün (bu dalğada yoxdur).
FORCE = set()


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
