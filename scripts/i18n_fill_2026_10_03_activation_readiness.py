#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-03: hesab aktivləşdirmə kampaniyası + «Semestr hazırlığı».

Əlavə olunan mətnlər:
  * `accounts.activation_sheet`: qrupun «ilk giriş» çap vərəqi (təlimat, QR, siyahı);
  * `accounts.student_registry`: reyestrin «Hesab aktivləşdirmə» (qruplar üzrə) görünüşü;
  * `accounts.semester`: «Semestr hazırlığı» paneli, problem nişanları, «Xatırlat» əməli.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_03_activation_readiness.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


AS = "accounts.activation_sheet"
SR = "accounts.student_registry"
SEM = "accounts.semester"

_SHEET = [
    _t(
        "1–2 dəqiqə gözləyin və «Spam» / «Promotions» qovluğuna baxın. Ünvanı səhv yazmısınızsa, «E-poçtu dəyiş» "
        "ilə düzəldin.",
        "Wait 1–2 minutes and check the “Spam” / “Promotions” folder. If you mistyped the address, fix it with "
        "“Change email”.",
        "Подождите 1–2 минуты и проверьте папку «Спам» / «Промоакции». Если адрес введён с ошибкой, исправьте его "
        "кнопкой «Изменить e-mail».",
        "1–2 dakika bekleyin ve «Spam» / «Promosyonlar» klasörüne bakın. Adresi yanlış yazdıysanız «E-postayı "
        "değiştir» ile düzeltin.",
    ),
    _t("Aktivləşdirib", "Activated", "Активировали", "Etkinleştirdi"),
    _t(
        "Açılan səhifədə hər gün baxdığınız ÖZ e-poçtunuzu yazın (məs. adiniz@gmail.com) və «Təsdiq kodu göndər» "
        "düyməsini basın.",
        "On the next page enter YOUR OWN email that you check every day (e.g. yourname@gmail.com) and press “Send "
        "verification code”.",
        "На открывшейся странице введите СВОЙ e-mail, который вы проверяете каждый день (например, imya@gmail.com), "
        "и нажмите «Отправить код подтверждения».",
        "Açılan sayfada her gün baktığınız KENDİ e-postanızı yazın (ör. adiniz@gmail.com) ve «Doğrulama kodu "
        "gönder» düğmesine basın.",
    ),
    _t("Başlayıb, tamamlamayıb", "Started, not finished", "Начал(а), не завершил(а)", "Başladı, tamamlamadı"),
    _t(
        "Bu qrupun bütün tələbələri hesabını aktivləşdirib.",
        "All students of this group have activated their accounts.",
        "Все студенты этой группы активировали свои аккаунты.",
        "Bu grubun tüm öğrencileri hesabını etkinleştirdi.",
    ),
    _t(
        "Bu vərəqdə parol yoxdur.",
        "This sheet contains no passwords.",
        "На этом листе нет паролей.",
        "Bu sayfada parola yer verilmez.",
    ),
    _t(
        "E-poçtunuza gələn 6 rəqəmli kodu yazın və yalnız sizin bildiyiniz yeni parol qurun. Parolu heç kimə "
        "deməyin.",
        "Enter the 6-digit code sent to your email and set a new password that only you know. Never share it.",
        "Введите 6-значный код из письма и задайте новый пароль, который знаете только вы. Никому его не сообщайте.",
        "E-postanıza gelen 6 haneli kodu yazın ve yalnızca sizin bildiğiniz yeni bir parola belirleyin. Parolayı "
        "kimseyle paylaşmayın.",
    ),
    _t(
        "Elektron universitetə ilk giriş",
        "First sign-in to the e-university",
        "Первый вход в электронный университет",
        "Elektronik üniversiteye ilk giriş",
    ),
    _t(
        "Hazırdır! Ballarınızı, davamiyyətinizi və dərs cədvəlinizi kabinetinizdə görəcəksiniz.",
        "Done! You will see your scores, attendance and timetable in your cabinet.",
        "Готово! Баллы, посещаемость и расписание вы увидите в своём кабинете.",
        "Hazır! Puanlarınızı, devam durumunuzu ve ders programınızı kabinenizde göreceksiniz.",
    ),
    _t("Heç girməyib", "Never signed in", "Ни разу не входил(а)", "Hiç giriş yapmadı"),
    _t(
        "Hələ hesabını aktivləşdirməyən tələbələr",
        "Students who have not activated their account yet",
        "Студенты, ещё не активировавшие аккаунт",
        "Hesabını henüz etkinleştirmeyen öğrenciler",
    ),
    _t("Kod gəlmir?", "No code?", "Код не приходит?", "Kod gelmiyor mu?"),
    _t(
        "Nə etməli? — 5 addım, 3 dəqiqə",
        "What to do — 5 steps, 3 minutes",
        "Что делать? — 5 шагов, 3 минуты",
        "Ne yapmalı? — 5 adım, 3 dakika",
    ),
    _t("Qeyd", "Note", "Примечание", "Not"),
    _t("Qrup", "Group", "Группа", "Grup"),
    _t("Reyestrə qayıt", "Back to the registry", "Вернуться в реестр", "Kayıtlara dön"),
    _t("Soyad, ad", "Surname, name", "Фамилия, имя", "Soyadı, adı"),
    _t(
        "Telefonun kamerası ilə QR kodu oxudun və ya brauzerdə <b>%(host)s</b> yazın, «Tələbə girişi»ni seçin.",
        "Scan the QR code with your phone camera or type <b>%(host)s</b> in the browser and choose “Student "
        "sign-in”.",
        "Отсканируйте QR-код камерой телефона или введите в браузере <b>%(host)s</b> и выберите «Вход для "
        "студентов».",
        "Telefon kamerasıyla QR kodu okutun veya tarayıcıya <b>%(host)s</b> yazıp «Öğrenci girişi»ni seçin.",
    ),
    _t("Çap et", "Print", "Печать", "Yazdır"),
    _t("Çap tarixi", "Printed on", "Дата печати", "Yazdırma tarihi"),
    _t("İlk giriş təlimatı", "First sign-in guide", "Инструкция первого входа", "İlk giriş kılavuzu"),
    _t(
        "İlkin parolu bilmirsiniz?",
        "Don't know your initial password?",
        "Не знаете начальный пароль?",
        "İlk parolanızı bilmiyor musunuz?",
    ),
    _t("İmza", "Signature", "Подпись", "İmza"),
    _t("İstifadəçi adı", "Username", "Имя пользователя", "Kullanıcı adı"),
    _t(
        "İstifadəçi adınızı (aşağıdakı cədvəldə) və sizə verilmiş ilkin parolu yazın.",
        "Enter your username (in the table below) and the initial password you were given.",
        "Введите своё имя пользователя (в таблице ниже) и выданный вам начальный пароль.",
        "Kullanıcı adınızı (aşağıdaki tabloda) ve size verilen ilk parolayı yazın.",
    ),
    _t(
        "Şəxsiyyət vəsiqəniz ilə RİM mərkəzinə müraciət edin — parolunuzu yerində sıfırlayacaqlar.",
        "Visit the Digital Development Centre (RİM) with your ID card — they will reset your password on the spot.",
        "Обратитесь с удостоверением личности в центр RİM — пароль сбросят на месте.",
        "Kimlik kartınızla RİM merkezine başvurun — parolanızı yerinde sıfırlayacaklar.",
    ),
]

_REGISTRY = [
    _t(
        "%(done)d / %(total)d tələbə",
        "%(done)d / %(total)d students",
        "%(done)d / %(total)d студентов",
        "%(done)d / %(total)d öğrenci",
    ),
    _t("AKTİVLƏŞDİRİB", "ACTIVATED", "АКТИВИРОВАЛИ", "ETKİNLEŞTİRDİ"),
    _t("Aktivləşdirib", "Activated", "Активировали", "Etkinleştirdi"),
    _t("Fakültələr üzrə", "By faculty", "По факультетам", "Fakülteye göre"),
    _t("HEÇ GİRMƏYİB", "NEVER SIGNED IN", "НИ РАЗУ НЕ ВХОДИЛИ", "HİÇ GİRİŞ YAPMADI"),
    _t("Hesab aktivləşdirmə", "Account activation", "Активация аккаунтов", "Hesap etkinleştirme"),
    _t("Heç girməyib", "Never signed in", "Ни разу не входили", "Hiç giriş yapmadı"),
    _t("Nəticə: %(count)d qrup", "Result: %(count)d groups", "Результат: %(count)d групп", "Sonuç: %(count)d grup"),
    _t("QRUP", "GROUPS", "ГРУПП", "GRUP"),
    _t(
        "Qruplar üzrə — ən geri qalan birinci",
        "By group — lowest first",
        "По группам — сначала отстающие",
        "Gruplara göre — en geride olan önce",
    ),
    _t("Qrupsuz", "No group", "Без группы", "Grupsuz"),
    _t(
        "Sistemə bir dəfə də daxil olmayıb",
        "Has never signed in to the system",
        "Ни разу не входил(а) в систему",
        "Sisteme bir kez bile giriş yapmadı",
    ),
    _t("Siyahı", "List", "Список", "Liste"),
    _t("Tələbə siyahısı", "Student list", "Список студентов", "Öğrenci listesi"),
    _t(
        "«Aktivləşdirib» — tələbə ilkin parolla daxil olub, öz e-poçtunu təsdiqləyib və öz parolunu qurub. Ballar, "
        "davamiyyət, sorğu və bildirişlər yalnız aktiv hesabda görünür. Qrupun çap vərəqini kuratora və ya qrup "
        "nümayəndəsinə verin — orada addım-addım təlimat və QR kod var.",
        "“Activated” — the student signed in with the initial password, verified their own email and set their own "
        "password. Scores, attendance, surveys and notifications are visible only on an active account. Give the "
        "group's printable sheet to the curator or the group representative — it has step-by-step instructions and "
        "a QR code.",
        "«Активировали» — студент вошёл с начальным паролем, подтвердил свой e-mail и задал свой пароль. Баллы, "
        "посещаемость, опросы и уведомления видны только в активном аккаунте. Передайте печатный лист группы "
        "куратору или старосте — там пошаговая инструкция и QR-код.",
        "«Etkinleştirdi» — öğrenci ilk parolayla giriş yaptı, kendi e-postasını doğruladı ve kendi parolasını "
        "belirledi. Puanlar, devam, anketler ve bildirimler yalnızca etkin hesapta görünür. Grubun yazdırılabilir "
        "sayfasını danışmana veya grup temsilcisine verin — adım adım talimat ve QR kod içerir.",
    ),
    _t("Çap vərəqi", "Printable sheet", "Лист для печати", "Yazdırma sayfası"),
    _t("İlkin parolda", "On initial password", "С начальным паролем", "İlk parolada"),
]

_SEMESTER = [
    _t(
        "%(ready)s / %(total)s fənn tam hazırdır (%(pct)s%%)",
        "%(ready)s / %(total)s courses fully ready (%(pct)s%%)",
        "%(ready)s / %(total)s предметов полностью готовы (%(pct)s%%)",
        "%(ready)s / %(total)s ders tamamen hazır (%(pct)s%%)",
    ),
    _t(
        "Bu kafedranın müəllimlərinə (sillabus / jurnal) və rəhbərinə (xülasə) xatırlatma bildirişi göndərilsin? "
        "Eyni kafedraya 12 saatda bir dəfə göndərilir.",
        "Send a reminder to this department's teachers (syllabus / journal) and its head (summary)? A department "
        "can be reminded once every 12 hours.",
        "Отправить напоминание преподавателям кафедры (силлабус / журнал) и заведующему (сводка)? Одной кафедре — "
        "не чаще раза в 12 часов.",
        "Bu bölümün öğretim elemanlarına (izlence / yoklama defteri) ve başkanına (özet) hatırlatma gönderilsin mi? "
        "Aynı bölüme 12 saatte bir gönderilir.",
    ),
    _t(
        "Bu kafedraya son 12 saatda artıq xatırlatma göndərilib.",
        "This department has already been reminded in the last 12 hours.",
        "Этой кафедре уже отправляли напоминание за последние 12 часов.",
        "Bu bölüme son 12 saatte zaten hatırlatma gönderildi.",
    ),
    _t("Cədvəl", "Timetable", "Расписание", "Program"),
    _t("Cədvəl yoxdur", "No timetable", "Нет расписания", "Program yok"),
    _t("Hazırdır", "Ready", "Готово", "Hazır"),
    _t(
        "Hər fənn üçün dörd şərt yoxlanılır: müəllim təyin olunub, sillabus təsdiqlənib, dərs cədvəlində yeri var, "
        "jurnalda dərs yazılır (semestrin ilk həftəsindən sonra; 14 gün yazılmırsa — «jurnal yazılmır»). Rəqəmə "
        "klik edin — həmin fənlər aşağıdakı cədvəldə açılacaq.",
        "Four conditions are checked for every course: a teacher is assigned, the syllabus is approved, it has a "
        "slot in the timetable, lessons are recorded in the journal (after the first week of the semester; no "
        "lesson for 14 days means “journal not kept”). Click a number to open those courses in the table below.",
        "Для каждого предмета проверяются четыре условия: назначен преподаватель, силлабус утверждён, есть место в "
        "расписании, в журнале записываются занятия (после первой недели семестра; 14 дней без записей — «журнал не "
        "ведётся»). Нажмите на число — эти предметы откроются в таблице ниже.",
        "Her ders için dört koşul kontrol edilir: öğretim elemanı atanmış, izlence onaylanmış, ders programında yeri "
        "var, yoklama defterine ders yazılıyor (dönemin ilk haftasından sonra; 14 gün yazılmazsa — «defter "
        "tutulmuyor»). Sayıya tıklayın — bu dersler aşağıdaki tabloda açılır.",
    ),
    _t("Jurnal", "Journal", "Журнал", "Defter"),
    _t("Jurnal yazılmır", "Journal not kept", "Журнал не ведётся", "Defter tutulmuyor"),
    _t("Kafedra tapılmadı.", "Department not found.", "Кафедра не найдена.", "Bölüm bulunamadı."),
    _t("Kafedrası yazılmayıb", "No department set", "Кафедра не указана", "Bölüm belirtilmemiş"),
    _t("Müəllim", "Teacher", "Преподаватель", "Öğretim elemanı"),
    _t("Müəllim yoxdur", "No teacher", "Нет преподавателя", "Öğretim elemanı yok"),
    _t("Problem", "Issue", "Проблема", "Sorun"),
    _t(
        "Semestr hazırlığı — kafedralar üzrə",
        "Semester readiness — by department",
        "Готовность семестра — по кафедрам",
        "Dönem hazırlığı — bölümlere göre",
    ),
    _t("Sillabus", "Syllabus", "Силлабус", "İzlence"),
    _t("Sillabus yoxdur", "No syllabus", "Нет силлабуса", "İzlence yok"),
    _t("Xatırlat", "Remind", "Напомнить", "Hatırlat"),
    _t(
        "Xatırlatma göndərildi: %(teachers)d müəllimə, %(chair)d kafedra əməkdaşına.",
        "Reminder sent: %(teachers)d teachers, %(chair)d department staff.",
        "Напоминание отправлено: преподавателям — %(teachers)d, сотрудникам кафедры — %(chair)d.",
        "Hatırlatma gönderildi: %(teachers)d öğretim elemanına, %(chair)d bölüm personeline.",
    ),
    _t("Çatışmır", "Missing", "Не хватает", "Eksik"),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    AS: {row["az"]: row for row in _SHEET},
    SR: {row["az"]: row for row in _REGISTRY},
    SEM: {row["az"]: row for row in _SEMESTER},
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
