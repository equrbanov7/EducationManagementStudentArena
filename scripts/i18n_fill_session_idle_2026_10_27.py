#!/usr/bin/env python3
"""EMSArena i18n — sessiya pingi, brauzer bağlananda çıxış, hərəkətsiz jurnalın bağlanması (sahib 2026-10-27).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "core.runtime_settings": {
        "Söndürülü (sessiya brauzer bağlandıqdan sonra da qalır)": t(
            "Off (the session survives closing the browser)",
            "Выключено (сессия сохраняется после закрытия браузера)",
            "Kapalı (oturum tarayıcı kapatıldıktan sonra da sürer)",
            "Aus (die Sitzung bleibt nach dem Schließen des Browsers bestehen)",
        ),
        "Müəllim və əməkdaşlar (tələbələr xaric)": t(
            "Teachers and staff (students excluded)",
            "Преподаватели и сотрудники (кроме студентов)",
            "Öğretmenler ve personel (öğrenciler hariç)",
            "Lehrkräfte und Mitarbeitende (ohne Studierende)",
        ),
        "Hamı (imtahan gedişində olan tələbə çıxarılmır)": t(
            "Everyone (a student in the middle of an exam is never signed out)",
            "Все (студент во время экзамена не выводится из системы)",
            "Herkes (sınavdaki öğrencinin oturumu kapatılmaz)",
            "Alle (Studierende in einer laufenden Prüfung werden nie abgemeldet)",
        ),
        "Brauzer bağlananda və ya kompüter sönəndə çıxış": t(
            "Sign out when the browser is closed or the computer is turned off",
            "Выход при закрытии браузера или выключении компьютера",
            "Tarayıcı kapatılınca veya bilgisayar kapanınca oturumu kapat",
            "Abmelden, wenn der Browser geschlossen oder der Computer ausgeschaltet wird",
        ),
        (
            "Seçilmiş istifadəçilərin sessiyası brauzer bağlananda bitir; brauzer «qaldığım yerdən davam et» ilə "
            "açılsa belə, aşağıdakı «brauzer açıq deyil» limiti keçibsə yenidən giriş tələb olunur. Tələbələr "
            "daxil edilsə də, imtahan gedişində (zal bileti, başlanmış cəhd, canlı imtahan) heç kim çıxarılmır."
        ): t(
            "The session of the selected users ends when the browser is closed; even if the browser reopens with "
            "“continue where you left off”, a new sign-in is required once the “browser not open” limit below has "
            "passed. Even when students are included, nobody is signed out during an exam (hall ticket, started "
            "attempt, live exam).",
            "Сессия выбранных пользователей завершается при закрытии браузера; даже если браузер откроется с "
            "функцией «продолжить с того же места», после истечения указанного ниже лимита «браузер не открыт» "
            "потребуется повторный вход. Даже если студенты включены, во время экзамена (билет зала, начатая "
            "попытка, живой экзамен) никто не выводится из системы.",
            "Seçilen kullanıcıların oturumu tarayıcı kapatılınca sona erer; tarayıcı «kaldığım yerden devam et» ile "
            "açılsa bile aşağıdaki «tarayıcı açık değil» sınırı geçtiyse yeniden giriş gerekir. Öğrenciler dahil "
            "edilse de sınav sırasında (salon bileti, başlamış deneme, canlı sınav) kimsenin oturumu kapatılmaz.",
            "Die Sitzung der ausgewählten Benutzer endet beim Schließen des Browsers; selbst wenn der Browser mit "
            "„Dort weitermachen, wo ich aufgehört habe“ wieder öffnet, ist nach Ablauf des unten stehenden Limits "
            "„Browser nicht geöffnet“ eine neue Anmeldung nötig. Auch wenn Studierende einbezogen sind, wird während "
            "einer Prüfung (Saalticket, begonnener Versuch, Live-Prüfung) niemand abgemeldet.",
        ),
        "Brauzer açıq deyilsə çıxış": t(
            "Sign out when the browser is not open",
            "Выход, если браузер не открыт",
            "Tarayıcı açık değilse oturumu kapat",
            "Abmelden, wenn der Browser nicht geöffnet ist",
        ),
        (
            "Açıq səhifə serverə mütəmadi «buradayam» siqnalı göndərir. Bu qədər dəqiqə heç bir siqnal gəlməsə "
            "(brauzer bağlanıb, kompüter sönüb və ya yuxu rejimindədir) sessiya bitir. Yalnız yuxarıda seçilmiş "
            "istifadəçilərə aiddir. 0 — söndürülü."
        ): t(
            "An open page regularly sends an “I am here” signal to the server. If no signal arrives for this many "
            "minutes (the browser was closed, the computer was turned off or is asleep), the session ends. Applies "
            "only to the users selected above. 0 — off.",
            "Открытая страница регулярно отправляет серверу сигнал «я здесь». Если сигнал не поступает столько "
            "минут (браузер закрыт, компьютер выключен или в спящем режиме), сессия завершается. Относится только "
            "к выбранным выше пользователям. 0 — выключено.",
            "Açık sayfa sunucuya düzenli olarak «buradayım» sinyali gönderir. Bu kadar dakika hiç sinyal gelmezse "
            "(tarayıcı kapatıldı, bilgisayar kapandı veya uyku modunda) oturum sona erer. Yalnızca yukarıda seçilen "
            "kullanıcılar için geçerlidir. 0 — kapalı.",
            "Eine geöffnete Seite sendet regelmäßig ein „Ich bin da“-Signal an den Server. Kommt so viele Minuten "
            "lang kein Signal (Browser geschlossen, Computer ausgeschaltet oder im Ruhezustand), endet die Sitzung. "
            "Gilt nur für die oben ausgewählten Benutzer. 0 — aus.",
        ),
        "Hərəkətsiz jurnalın bağlanması": t(
            "Closing an idle journal",
            "Закрытие неактивного журнала",
            "Hareketsiz yoklama defterinin kapatılması",
            "Schließen eines inaktiven Journals",
        ),
        (
            "Açıq jurnalda bu qədər dəqiqə heç bir hərəkət (klik, yazı, sürüşdürmə) olmasa, yadda saxlanmamış "
            "xanalar əvvəlcə yadda saxlanılır, sonra jurnal bağlanır; «Davam et» onu təzə məlumatla açır. "
            "0 — söndürülü."
        ): t(
            "If there is no activity (click, typing, scrolling) in an open journal for this many minutes, unsaved "
            "cells are saved first and then the journal is closed; “Continue” reopens it with fresh data. 0 — off.",
            "Если в открытом журнале столько минут нет никаких действий (клик, ввод, прокрутка), несохранённые "
            "ячейки сначала сохраняются, затем журнал закрывается; «Продолжить» открывает его со свежими данными. "
            "0 — выключено.",
            "Açık yoklama defterinde bu kadar dakika hiçbir hareket (tıklama, yazma, kaydırma) olmazsa, "
            "kaydedilmemiş hücreler önce kaydedilir, ardından yoklama defteri kapanır; «Devam et» onu güncel verilerle açar. "
            "0 — kapalı.",
            "Gibt es in einem geöffneten Journal so viele Minuten lang keine Aktivität (Klick, Eingabe, Scrollen), "
            "werden ungespeicherte Zellen zuerst gespeichert und dann wird das Journal geschlossen; „Weiter“ "
            "öffnet es mit aktuellen Daten. 0 — aus.",
        ),
    },
    "accounts.session": {
        (
            "Brauzer bağlandığı və ya kompüter söndüyü üçün sessiyanız təhlükəsizlik məqsədilə başa çatdı. "
            "Davam etmək üçün yenidən daxil olun."
        ): t(
            "Your session ended for security reasons because the browser was closed or the computer was turned off. "
            "Sign in again to continue.",
            "Ваша сессия завершена в целях безопасности, так как браузер был закрыт или компьютер выключен. "
            "Чтобы продолжить, войдите снова.",
            "Tarayıcı kapatıldığı veya bilgisayar kapandığı için oturumunuz güvenlik amacıyla sona erdi. "
            "Devam etmek için yeniden giriş yapın.",
            "Ihre Sitzung wurde aus Sicherheitsgründen beendet, weil der Browser geschlossen oder der Computer "
            "ausgeschaltet wurde. Melden Sie sich erneut an, um fortzufahren.",
        ),
        "Uzun müddət heç bir əməliyyat edilmədiyi üçün sessiyanız başa çatdı. Davam etmək üçün yenidən daxil olun.": t(
            "Your session ended because there was no activity for a long time. Sign in again to continue.",
            "Ваша сессия завершена из-за длительного отсутствия активности. Чтобы продолжить, войдите снова.",
            "Uzun süre hiçbir işlem yapılmadığı için oturumunuz sona erdi. Devam etmek için yeniden giriş yapın.",
            "Ihre Sitzung wurde beendet, weil längere Zeit keine Aktivität stattfand. Melden Sie sich erneut an, "
            "um fortzufahren.",
        ),
        "Sessiyanız başa çatdı": t(
            "Your session has ended",
            "Ваша сессия завершена",
            "Oturumunuz sona erdi",
            "Ihre Sitzung ist beendet",
        ),
        (
            "Yadda saxlanmamış dəyişiklik varsa, yenidən daxil olduqdan sonra yoxlayın — jurnal xanaları bu "
            "brauzerdə qaralama kimi saxlanılır və bərpa olunur."
        ): t(
            "If there were unsaved changes, check them after signing in again — journal cells are kept as a draft in "
            "this browser and restored.",
            "Если были несохранённые изменения, проверьте их после повторного входа — ячейки журнала хранятся в этом "
            "браузере как черновик и восстанавливаются.",
            "Kaydedilmemiş değişiklik varsa yeniden giriş yaptıktan sonra kontrol edin — yoklama defteri hücreleri bu "
            "tarayıcıda taslak olarak saklanır ve geri yüklenir.",
            "Falls es ungespeicherte Änderungen gab, prüfen Sie sie nach der erneuten Anmeldung — Journalzellen "
            "werden in diesem Browser als Entwurf gespeichert und wiederhergestellt.",
        ),
        "Yenidən daxil ol": t("Sign in again", "Войти снова", "Yeniden giriş yap", "Erneut anmelden"),
        "Bu səhifədə qal": t("Stay on this page", "Остаться на странице", "Bu sayfada kal", "Auf dieser Seite bleiben"),
    },
    "registrar.journal_autosave": {
        (
            "Sessiya başa çatıb — yenidən daxil olun. Yazılmamış xanalar bu brauzerdə qaralama kimi saxlanılıb və "
            "girişdən sonra jurnalda bərpa olunacaq."
        ): t(
            "The session has ended — sign in again. Unsaved cells are kept as a draft in this browser and will be "
            "restored in the journal after you sign in.",
            "Сессия завершена — войдите снова. Несохранённые ячейки сохранены в этом браузере как черновик и будут "
            "восстановлены в журнале после входа.",
            "Oturum sona erdi — yeniden giriş yapın. Kaydedilmemiş hücreler bu tarayıcıda taslak olarak saklandı ve "
            "girişten sonra yoklama defterinde geri yüklenecek.",
            "Die Sitzung ist beendet — melden Sie sich erneut an. Ungespeicherte Zellen sind in diesem Browser als "
            "Entwurf gesichert und werden nach der Anmeldung im Journal wiederhergestellt.",
        ),
    },
    "registrar.journal_idle": {
        "Dəyişikliklər yadda saxlanılır…": t(
            "Saving changes…", "Изменения сохраняются…", "Değişiklikler kaydediliyor…", "Änderungen werden gespeichert…"
        ),
        "Bütün dəyişikliklər yadda saxlanılıb.": t(
            "All changes have been saved.",
            "Все изменения сохранены.",
            "Tüm değişiklikler kaydedildi.",
            "Alle Änderungen wurden gespeichert.",
        ),
        (
            "Bəzi xanalar yadda saxlanılmadı — onlar bu brauzerdə qaralama kimi qalıb və «Davam et» basanda bərpa "
            "olunacaq."
        ): t(
            "Some cells were not saved — they remain as a draft in this browser and will be restored when you press "
            "“Continue”.",
            "Некоторые ячейки не сохранены — они остались в этом браузере как черновик и будут восстановлены при "
            "нажатии «Продолжить».",
            "Bazı hücreler kaydedilmedi — bu tarayıcıda taslak olarak kaldılar ve «Devam et»e basınca geri "
            "yüklenecek.",
            "Einige Zellen wurden nicht gespeichert — sie bleiben als Entwurf in diesem Browser und werden "
            "wiederhergestellt, wenn Sie „Weiter“ drücken.",
        ),
        "Jurnal bağlandı": t("Journal closed", "Журнал закрыт", "Yoklama defteri kapatıldı", "Journal geschlossen"),
        "%(minutes)s dəqiqə heç bir əməliyyat edilmədiyi üçün jurnal təhlükəsizlik məqsədilə bağlandı.": t(
            "The journal was closed for security reasons because there was no activity for %(minutes)s minutes.",
            "Журнал закрыт в целях безопасности, так как %(minutes)s мин. не было никаких действий.",
            "%(minutes)s dakika hiçbir işlem yapılmadığı için yoklama defteri güvenlik amacıyla kapatıldı.",
            "Das Journal wurde aus Sicherheitsgründen geschlossen, da %(minutes)s Minuten lang keine Aktivität "
            "stattfand.",
        ),
        "Davam et": t("Continue", "Продолжить", "Devam et", "Weiter"),
        "Jurnallar siyahısı": t("Journal list", "Список журналов", "Yoklama defterleri listesi", "Journalliste"),
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
