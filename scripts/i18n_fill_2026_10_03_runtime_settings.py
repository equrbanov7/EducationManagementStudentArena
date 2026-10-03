#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-03: «Sistem tənzimləmələri» (RİM rəhbəri) + jurnal pəncərəsi mətnləri.

Əlavə olunan mətnlər:
  * `core.runtime_settings`: parametr adları, izahlar, vahidlər, qruplar;
  * `accounts.runtime_settings`: bölmə, saxlama mesajları, xətalar;
  * `profile.section`: «Sistem tənzimləmələri»;
  * `registrar.journal`: «N saat pəncərəsi» mətnləri artıq tənzimləmədən gələn saatı göstərir.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_03_runtime_settings.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


AR = "accounts.runtime_settings"
CR = "core.runtime_settings"
PS = "profile.section"
RJ = "registrar.journal"

_ACCOUNTS = [
    _t("Avtomatik", "Automatic", "Автоматически", "Otomatik"),
    _t(
        "Bu əməl yalnız RİM rəhbəri üçündür.",
        "Only the RİM head can do this.",
        "Это действие доступно только руководителю RİM.",
        "Bu işlem yalnızca RİM başkanı içindir.",
    ),
    _t(
        "Bəzi dəyərlər yanlışdır.", "Some values are invalid.", "Некоторые значения неверны.", "Bazı değerler geçersiz."
    ),
    _t("Dəyişdirilib", "Changed", "Изменено", "Değiştirildi"),
    _t("Dəyişiklik yoxdur.", "No changes.", "Изменений нет.", "Değişiklik yok."),
    _t(
        "Dəyər %(min)s–%(max)s aralığında olmalıdır.",
        "The value must be between %(min)s and %(max)s.",
        "Значение должно быть в диапазоне %(min)s–%(max)s.",
        "Değer %(min)s–%(max)s aralığında olmalıdır.",
    ),
    _t("Pəncərə (dəqiqə)", "Window (minutes)", "Окно (минуты)", "Pencere (dakika)"),
    _t(
        "Sistem tənzimləmələri yalnız RİM rəhbəri üçündür.",
        "System settings are available only to the RİM head.",
        "Системные настройки доступны только руководителю RİM.",
        "Sistem ayarları yalnızca RİM başkanı içindir.",
    ),
    _t(
        "Sistemin limitləri bir yerdən: dəyişiklik bütün serverlərdə 10–15 saniyəyə qüvvəyə minir və audit jurnalına yazılır. Boş saxlanan və ya defolta qaytarılan dəyər üçün sistemin standart qaydası işləyir.",
        "System limits in one place: a change takes effect on all servers within 10–15 seconds and is written to the audit log. A value reset to its default uses the system's standard rule.",
        "Лимиты системы в одном месте: изменение вступает в силу на всех серверах за 10–15 секунд и записывается в журнал аудита. Для значения, возвращённого к стандарту, действует стандартное правило системы.",
        "Sistem limitleri tek yerden: değişiklik tüm sunucularda 10–15 saniye içinde yürürlüğe girer ve denetim günlüğüne yazılır. Varsayılana döndürülen değer için sistemin standart kuralı geçerlidir.",
    ),
    _t("Siyahıdan seçin.", "Choose from the list.", "Выберите из списка.", "Listeden seçin."),
    _t("Standart", "Default", "Стандарт", "Varsayılan"),
    _t("Standarta qaytar", "Reset to default", "Вернуть стандарт", "Varsayılana döndür"),
    _t("Yadda saxla", "Save", "Сохранить", "Kaydet"),
    _t(
        "Yadda saxlanıldı: %(n)d dəyişiklik. Bütün serverlərdə 10–15 saniyəyə qüvvəyə minir.",
        "Saved: %(n)d change(s). Takes effect on all servers within 10–15 seconds.",
        "Сохранено изменений: %(n)d. Вступит в силу на всех серверах за 10–15 секунд.",
        "Kaydedildi: %(n)d değişiklik. Tüm sunucularda 10–15 saniye içinde geçerli olur.",
    ),
    _t("dəfə /", "times /", "раз /", "kez /"),
    _t("dəq.", "min", "мин", "dk"),
    _t("dəqiqədə", "minutes", "минут", "dakikada"),
]

_CORE = [
    _t(
        "AI köməkçiyə bir istifadəçinin sual sayı",
        "AI assistant questions per user",
        "Число вопросов к ИИ-помощнику от одного пользователя",
        "Bir kullanıcının yapay zekâ asistanına soru sayısı",
    ),
    _t(
        "AI modeli (köməkçi, xülasə, yoxlama)",
        "AI model (assistant, summary, grading)",
        "Модель ИИ (помощник, сводка, проверка)",
        "Yapay zekâ modeli (asistan, özet, değerlendirme)",
    ),
    _t(
        "Avtomatik (cari tənzimləmə)",
        "Automatic (current configuration)",
        "Автоматически (текущая настройка)",
        "Otomatik (mevcut yapılandırma)",
    ),
    _t(
        "Bir cihazdan səhv parol cəhdi",
        "Wrong password attempts from one device",
        "Попытки неверного пароля с одного устройства",
        "Bir cihazdan yanlış parola denemesi",
    ),
    _t(
        "Bir e-poçta saatda göndərilən kod sayı",
        "Codes sent to one email per hour",
        "Кодов на один e-mail в час",
        "Bir e-postaya saatte gönderilen kod sayısı",
    ),
    _t(
        "Bir hesaba səhv parol cəhdi (bütün cihazlardan)",
        "Wrong password attempts on one account (all devices)",
        "Попытки неверного пароля для одного аккаунта (со всех устройств)",
        "Bir hesaba yanlış parola denemesi (tüm cihazlardan)",
    ),
    _t(
        "Bir kod üçün səhv yazma cəhdi",
        "Wrong attempts per code",
        "Неверных попыток на один код",
        "Bir kod için yanlış giriş denemesi",
    ),
    _t(
        "Bir İP ünvanından giriş cəhdi",
        "Sign-in attempts from one IP address",
        "Попытки входа с одного IP-адреса",
        "Bir IP adresinden giriş denemesi",
    ),
    _t(
        "Bir İP-dən parol bərpa kodu göndərmə",
        "Password-reset codes sent from one IP",
        "Отправка кодов восстановления пароля с одного IP",
        "Bir IP'den parola sıfırlama kodu gönderme",
    ),
    _t(
        "Bir İP-dən parol bərpa kodunu yoxlama",
        "Password-reset code checks from one IP",
        "Проверка кодов восстановления пароля с одного IP",
        "Bir IP'den parola sıfırlama kodu doğrulama",
    ),
    _t(
        "Dərs sətrini (tarix, mövzu, saat) düzəltmə / silmə müddəti",
        "Time to edit / delete a lesson row (date, topic, time)",
        "Срок исправления / удаления строки занятия (дата, тема, время)",
        "Ders satırını (tarih, konu, saat) düzeltme / silme süresi",
    ),
    _t("E-poçt kodu (OTP)", "Email code (OTP)", "Код по e-mail (OTP)", "E-posta kodu (OTP)"),
    _t(
        "E-poçta gələn 6 rəqəmli kod bu qədər dəqiqə işləyir.",
        "The 6-digit email code stays valid for this many minutes.",
        "6-значный код из письма действует столько минут.",
        "E-postaya gelen 6 haneli kod bu kadar dakika geçerlidir.",
    ),
    _t("Elektron jurnal", "Electronic journal", "Электронный журнал", "Elektronik yoklama defteri"),
    _t(
        "Final imtahan PIN-ini səhv yazma cəhdi",
        "Wrong final-exam PIN attempts",
        "Попытки неверного PIN финального экзамена",
        "Final sınavı PIN'ini yanlış yazma denemesi",
    ),
    _t("Final imtahan girişi", "Final exam entry", "Вход на финальный экзамен", "Final sınavı girişi"),
    _t(
        "Giriş və parol cəhdləri",
        "Sign-in and password attempts",
        "Вход и попытки пароля",
        "Giriş ve parola denemeleri",
    ),
    _t(
        "Hərəkətsizlikdən sonra avtomatik çıxış",
        "Automatic sign-out after inactivity",
        "Автоматический выход после бездействия",
        "Hareketsizlikten sonra otomatik çıkış",
    ),
    _t(
        "Kodu yenidən göndərmə fasiləsi",
        "Wait before resending a code",
        "Пауза перед повторной отправкой кода",
        "Kodu yeniden gönderme bekleme süresi",
    ),
    _t(
        "Kodu yenidən istəmə (ilk giriş / qeydiyyat)",
        "Code resend requests (first sign-in / sign-up)",
        "Повторный запрос кода (первый вход / регистрация)",
        "Kodu yeniden isteme (ilk giriş / kayıt)",
    ),
    _t(
        "Kodu yoxlama cəhdi (qeydiyyat)",
        "Code check attempts (sign-up)",
        "Попытки проверки кода (регистрация)",
        "Kod doğrulama denemesi (kayıt)",
    ),
    _t("Kodun etibarlılıq müddəti", "Code validity", "Срок действия кода", "Kodun geçerlilik süresi"),
    _t(
        "Müəllim dərsi yaratdıqdan sonra bu qədər saat ərzində dəyişə bilər.",
        "The teacher can change the lesson for this many hours after creating it.",
        "Преподаватель может изменить занятие в течение стольких часов после создания.",
        "Öğretim elemanı dersi oluşturduktan sonra bu kadar saat içinde değiştirebilir.",
    ),
    _t(
        "PIN səhvlərindən sonra kilid müddəti",
        "Lock time after PIN errors",
        "Время блокировки после ошибок PIN",
        "PIN hatalarından sonra kilit süresi",
    ),
    _t(
        "Pəncərə ərzində icazə verilən say; keçəndə istifadəçi gözləməli olur.",
        "Allowed count within the window; above it the user has to wait.",
        "Допустимое число в пределах окна; при превышении пользователь ждёт.",
        "Pencere içinde izin verilen sayı; aşılırsa kullanıcı beklemek zorunda kalır.",
    ),
    _t("Sessiya", "Session", "Сессия", "Oturum"),
    _t("Süni intellekt", "Artificial intelligence", "Искусственный интеллект", "Yapay zekâ"),
    _t(
        "Universitet Wi-Fi-ında yüzlərlə tələbə EYNİ İP-dən çıxır — çox aşağı saxlamayın.",
        "On the university Wi-Fi hundreds of students share ONE IP — do not set this too low.",
        "В Wi-Fi университета сотни студентов выходят с ОДНОГО IP — не ставьте слишком низко.",
        "Üniversite Wi-Fi'ında yüzlerce öğrenci AYNI IP'den çıkar — çok düşük tutmayın.",
    ),
    _t(
        "Yazılmış qeyd bu qədər saatdan sonra donur (sonra yalnız rəsmi düzəliş yolu).",
        "A recorded mark freezes after this many hours (then only the official correction path).",
        "Записанная отметка замораживается через столько часов (далее — только официальная корректировка).",
        "Yazılan kayıt bu kadar saatten sonra donar (sonra yalnızca resmî düzeltme yolu).",
    ),
    _t("cəhd", "attempts", "попыток", "deneme"),
    _t("dəqiqə", "minutes", "минут", "dakika"),
    _t("kod", "codes", "кодов", "kod"),
    _t(
        "q/b, i/e və balı dəyişmə müddəti",
        "Time to change absent / present marks and scores",
        "Срок изменения «н/б», «пр» и балла",
        "Devamsızlık / katılım ve puanı değiştirme süresi",
    ),
    _t("saat", "hours", "часов", "saat"),
    _t("saniyə", "seconds", "секунд", "saniye"),
    _t(
        "«Avtomatik» — mövcud server tənzimləməsi; seçilən model hamısında birinci yoxlanılır.",
        "“Automatic” — the current server configuration; a chosen model is tried first everywhere.",
        "«Автоматически» — текущая настройка сервера; выбранная модель везде пробуется первой.",
        "«Otomatik» — mevcut sunucu yapılandırması; seçilen model her yerde ilk denenir.",
    ),
    _t(
        "İstifadəçi bu qədər saat heç nə etməsə, sistemdən çıxarılır (sessiya ən çox 24 saat yaşayır).",
        "If the user does nothing for this many hours they are signed out (a session lives at most 24 hours).",
        "Если пользователь бездействует столько часов, его выводят из системы (сессия живёт не более 24 часов).",
        "Kullanıcı bu kadar saat hiçbir şey yapmazsa oturumu kapatılır (oturum en fazla 24 saat sürer).",
    ),
]

_PROFILE = [
    _t("Sistem tənzimləmələri", "System settings", "Системные настройки", "Sistem ayarları"),
]

_JOURNAL = [
    _t(
        "%(h)s saat pəncərəsi bağlanıb",
        "%(h)s-hour window closed",
        "Окно %(h)s ч закрыто",
        "%(h)s saatlik pencere kapandı",
    ),
    _t(
        "Bu dərs kilidlənib (%(h)s saat keçib). Tarix/tip/saat/mövzu/müəllim dəyişikliyi VƏ YA dərsin silinməsi rəsmi sənədlə (təqdimat) audit olunur.",
        "This lesson is locked (%(h)s hours passed). Changing date/type/time/topic/teacher OR deleting the lesson is audited with an official document (submission).",
        "Занятие заблокировано (прошло %(h)s ч). Изменение даты/типа/времени/темы/преподавателя ИЛИ удаление занятия проводится с официальным документом (представление) и аудитом.",
        "Bu ders kilitlendi (%(h)s saat geçti). Tarih/tür/saat/konu/öğretim elemanı değişikliği VEYA dersin silinmesi resmî belgeyle (dilekçe) denetlenir.",
    ),
    _t(
        "Davamiyyət yalnız cari gün üzrə qeyd edilə bilər · yazılmış qeyd %(h)s saatdan sonra kilidlənir — düzəliş üçün Tyutor xidmətinə yazılı müraciət edilir.",
        "Attendance can be recorded only for the current day · a recorded mark locks after %(h)s hours — for a correction, apply in writing to the Tutor service.",
        "Посещаемость отмечается только за текущий день · запись блокируется через %(h)s ч — для исправления подаётся письменное обращение в службу тьюторов.",
        "Devam yalnızca bugün için girilebilir · yazılan kayıt %(h)s saatten sonra kilitlenir — düzeltme için Tutor hizmetine yazılı başvuru yapılır.",
    ),
    _t(
        "Dərs əlavə edildikdə davamiyyət cədvəlinə yeni tarix sütunu açılır və qeydlər həmin gün aparılır. Səhv açılmış dərsi %(h)s saat içində silmək/düzəltmək olar.",
        "Adding a lesson opens a new date column in the attendance grid and marks are recorded that day. A lesson opened by mistake can be deleted/fixed within %(h)s hours.",
        "При добавлении занятия в таблице посещаемости открывается новая колонка даты, отметки ставятся в тот же день. Ошибочно созданное занятие можно удалить/исправить в течение %(h)s ч.",
        "Ders eklendiğinde devam tablosunda yeni bir tarih sütunu açılır ve kayıtlar o gün yapılır. Yanlış açılan ders %(h)s saat içinde silinebilir/düzeltilebilir.",
    ),
    _t(
        "Kurs işi balı yekun cədvəldə ayrıca sütunda göstərilir. Yazılan qeyd %(h)s saat sonra kilidlənir.",
        "The coursework score is shown in a separate column of the final table. A recorded entry locks after %(h)s hours.",
        "Балл курсовой работы показывается в отдельной колонке итоговой таблицы. Запись блокируется через %(h)s ч.",
        "Dönem ödevi puanı final tablosunda ayrı bir sütunda gösterilir. Yazılan kayıt %(h)s saat sonra kilitlenir.",
    ),
    _t(
        "Redaktə (%(h)s saat pəncərəsi)",
        "Edit (%(h)s-hour window)",
        "Редактировать (окно %(h)s ч)",
        "Düzenle (%(h)s saatlik pencere)",
    ),
    _t(
        "Redaktə / sil (%(h)s saat pəncərəsi)",
        "Edit / delete (%(h)s-hour window)",
        "Изменить / удалить (окно %(h)s ч)",
        "Düzenle / sil (%(h)s saatlik pencere)",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    AR: {row["az"]: row for row in _ACCOUNTS},
    CR: {row["az"]: row for row in _CORE},
    PS: {row["az"]: row for row in _PROFILE},
    RJ: {row["az"]: row for row in _JOURNAL},
}

FORCE = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
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
