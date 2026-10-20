#!/usr/bin/env python3
"""EMSArena i18n — midterm imtahan mərkəzi axını (/exams/midterm/, sahib 2026-10-20).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RS = "core.runtime_settings"
CE = "exams.center_exams"
ENTRY = "exams.final_center.entry"
DEVICE = "exams.final_center.device"
REMINDER = "exams.final_center.reminder"
REPORT = "exams.final_center.report"
TPL_ENTRY = "exams.template.final_entry"
TPL_GATE = "exams.template.final_gate"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


AZ_OVERRIDES = {}

ENTRIES = {
    RS: {
        "Midterm imtahan mərkəzi vasitəsilə (/exams/midterm/)": t(
            "Midterm through the exam centre (/exams/midterm/)",
            "Промежуточный экзамен через экзаменационный центр (/exams/midterm/)",
            "Ara sınav sınav merkezi üzerinden (/exams/midterm/)",
            "Zwischenprüfung über das Prüfungszentrum (/exams/midterm/)",
        ),
        "Yandırılıbsa midterm final kimi yalnız imtahan zalında /exams/midterm/ ünvanından verilir: istifadəçi "
        "adı + PIN, imtahan qaydaları, gözləmə otağı, nəzarətçinin startı, cihaz bağlantısı və 5 dəqiqəlik "
        "nəticə baxışı. Kabinetdən midterm başlamaq olmur. Söndürüləndə midterm əvvəlki kimi kabinetdən fərdi "
        "PIN ilə başlayır. Artıq başlamış midterm cəhdləri hər iki halda normal bitir.": t(
            "When on, the midterm is taken like the final — only in the exam hall at /exams/midterm/: username + "
            "PIN, exam rules, waiting room, start by the invigilator, device binding and the 5-minute result view. "
            "The midterm cannot be started from the cabinet. When off, the midterm starts from the cabinet with "
            "the personal PIN as before. Midterm attempts that have already started finish normally either way.",
            "Если включено, промежуточный экзамен проходит как итоговый — только в экзаменационном зале по адресу "
            "/exams/midterm/: логин + PIN, правила экзамена, комната ожидания, старт наблюдателем, привязка к "
            "устройству и 5-минутный просмотр результата. Начать его из кабинета нельзя. Если выключено, экзамен, "
            "как и раньше, начинается из кабинета с личным PIN. Уже начатые попытки в любом случае завершаются "
            "обычным образом.",
            "Açıksa ara sınav final gibi yalnızca sınav salonunda /exams/midterm/ adresinden yapılır: kullanıcı "
            "adı + PIN, sınav kuralları, bekleme odası, gözetmenin başlatması, cihaz bağlantısı ve 5 dakikalık "
            "sonuç görüntüleme. Ara sınav kabinetten başlatılamaz. Kapalıysa ara sınav eskisi gibi kabinetten "
            "kişisel PIN ile başlar. Başlamış ara sınav denemeleri her iki durumda da normal şekilde biter.",
            "Wenn aktiviert, wird die Zwischenprüfung wie die Abschlussprüfung nur im Prüfungssaal unter "
            "/exams/midterm/ abgelegt: Benutzername + PIN, Prüfungsregeln, Warteraum, Start durch die Aufsicht, "
            "Gerätebindung und 5-minütige Ergebnisansicht. Ein Start aus dem Kabinett ist nicht möglich. Wenn "
            "deaktiviert, beginnt die Zwischenprüfung wie bisher im Kabinett mit der persönlichen PIN. Bereits "
            "begonnene Versuche werden in beiden Fällen normal beendet.",
        ),
    },
    CE: {
        "Midterm": t("Midterm", "Промежуточный", "Ara sınav", "Zwischenprüfung"),
        "Final": t("Final", "Итоговый", "Final", "Abschlussprüfung"),
        "Bu imtahana imtahan zalında /exams/midterm/ ünvanından istifadəçi adınız və PIN ilə daxil olun.": t(
            "Enter this exam in the exam hall at /exams/midterm/ with your username and PIN.",
            "Войдите в этот экзамен в экзаменационном зале по адресу /exams/midterm/ с логином и PIN.",
            "Bu sınava sınav salonunda /exams/midterm/ adresinden kullanıcı adınız ve PIN ile girin.",
            "Melden Sie sich zu dieser Prüfung im Prüfungssaal unter /exams/midterm/ mit Benutzername und PIN an.",
        ),
        "Bu imtahana imtahan zalında /exams/final/ ünvanından istifadəçi adınız və PIN ilə daxil olun.": t(
            "Enter this exam in the exam hall at /exams/final/ with your username and PIN.",
            "Войдите в этот экзамен в экзаменационном зале по адресу /exams/final/ с логином и PIN.",
            "Bu sınava sınav salonunda /exams/final/ adresinden kullanıcı adınız ve PIN ile girin.",
            "Melden Sie sich zu dieser Prüfung im Prüfungssaal unter /exams/final/ mit Benutzername und PIN an.",
        ),
        "Bu, midterm imtahanıdır. İmtahana imtahan zalında /exams/midterm/ ünvanından istifadəçi adı və PIN ilə "
        "daxil olun. Kabinetdən birbaşa başlamaq mümkün deyil.": t(
            "This is a midterm exam. Enter it in the exam hall at /exams/midterm/ with your username and PIN. It "
            "cannot be started directly from the cabinet.",
            "Это промежуточный экзамен. Войдите в него в экзаменационном зале по адресу /exams/midterm/ с логином "
            "и PIN. Начать его прямо из кабинета нельзя.",
            "Bu bir ara sınavdır. Sınava sınav salonunda /exams/midterm/ adresinden kullanıcı adı ve PIN ile girin. "
            "Doğrudan kabinetten başlatılamaz.",
            "Dies ist eine Zwischenprüfung. Melden Sie sich im Prüfungssaal unter /exams/midterm/ mit Benutzername "
            "und PIN an. Ein direkter Start aus dem Kabinett ist nicht möglich.",
        ),
        "Bu, final imtahanıdır. İmtahan yalnız təyin olunmuş vaxt aralığında, imtahan giriş səhifəsindən "
        "istifadəçi adı və PIN ilə verilir. Kabinetdən birbaşa başlamaq mümkün deyil.": t(
            "This is a final exam. It is taken only within the scheduled time window, from the exam entry page "
            "with your username and PIN. It cannot be started directly from the cabinet.",
            "Это итоговый экзамен. Он сдаётся только в назначенное время на странице входа на экзамен с логином и "
            "PIN. Начать его прямо из кабинета нельзя.",
            "Bu bir final sınavıdır. Sınav yalnızca belirlenen zaman aralığında, sınav giriş sayfasından kullanıcı "
            "adı ve PIN ile yapılır. Doğrudan kabinetten başlatılamaz.",
            "Dies ist eine Abschlussprüfung. Sie wird nur im festgelegten Zeitfenster über die Prüfungsanmeldeseite "
            "mit Benutzername und PIN abgelegt. Ein direkter Start aus dem Kabinett ist nicht möglich.",
        ),
    },
    ENTRY: {
        "Məlumatlar yanlışdır və ya aktiv midterm imtahanınız yoxdur.": t(
            "The details are incorrect or you have no active midterm exam.",
            "Данные неверны или у вас нет активного промежуточного экзамена.",
            "Bilgiler hatalı veya aktif ara sınavınız yok.",
            "Die Angaben sind falsch oder Sie haben keine aktive Zwischenprüfung.",
        ),
        "Bu PIN final imtahanına aiddir. Final imtahanına /exams/final/ ünvanından daxil olun.": t(
            "This PIN belongs to a final exam. Enter the final exam at /exams/final/.",
            "Этот PIN относится к итоговому экзамену. Войдите в итоговый экзамен по адресу /exams/final/.",
            "Bu PIN bir final sınavına aittir. Final sınavına /exams/final/ adresinden girin.",
            "Diese PIN gehört zu einer Abschlussprüfung. Melden Sie sich unter /exams/final/ an.",
        ),
        "Bu PIN midterm imtahanına aiddir. Midterm imtahanına /exams/midterm/ ünvanından daxil olun.": t(
            "This PIN belongs to a midterm exam. Enter the midterm exam at /exams/midterm/.",
            "Этот PIN относится к промежуточному экзамену. Войдите в него по адресу /exams/midterm/.",
            "Bu PIN bir ara sınava aittir. Ara sınava /exams/midterm/ adresinden girin.",
            "Diese PIN gehört zu einer Zwischenprüfung. Melden Sie sich unter /exams/midterm/ an.",
        ),
        "Midterm imtahanları hazırda imtahan mərkəzi vasitəsilə keçirilmir — imtahana kabinetinizdəki "
        "«Təyin olunmuş imtahanlar» bölməsindən başlayın.": t(
            "Midterm exams are currently not held through the exam centre — start the exam from the “Assigned "
            "exams” section of your cabinet.",
            "Промежуточные экзамены сейчас не проводятся через экзаменационный центр — начните экзамен в разделе "
            "«Назначенные экзамены» вашего кабинета.",
            "Ara sınavlar şu anda sınav merkezi üzerinden yapılmıyor — sınava kabinetinizdeki «Atanmış sınavlar» "
            "bölümünden başlayın.",
            "Zwischenprüfungen werden derzeit nicht über das Prüfungszentrum durchgeführt — starten Sie die Prüfung "
            "im Bereich „Zugewiesene Prüfungen“ Ihres Kabinetts.",
        ),
    },
    DEVICE: {
        "Bu midterm imtahanı başqa cihazda davam edir. Cihazı dəyişmək lazımdırsa, nəzarətçidən və ya "
        "imtahan mərkəzindən «cihaz dəyişikliyi» təsdiqi istəyin, sonra səhifəni yeniləyin.": t(
            "This midterm exam is continuing on another device. If you need to switch devices, ask the invigilator "
            "or the exam centre to approve a “device change”, then reload the page.",
            "Этот промежуточный экзамен продолжается на другом устройстве. Если нужно сменить устройство, попросите "
            "наблюдателя или экзаменационный центр подтвердить «смену устройства», затем обновите страницу.",
            "Bu ara sınav başka bir cihazda devam ediyor. Cihaz değiştirmeniz gerekiyorsa gözetmenden veya sınav "
            "merkezinden «cihaz değişikliği» onayı isteyin, ardından sayfayı yenileyin.",
            "Diese Zwischenprüfung wird auf einem anderen Gerät fortgesetzt. Wenn Sie das Gerät wechseln müssen, "
            "bitten Sie die Aufsicht oder das Prüfungszentrum um Freigabe eines „Gerätewechsels“ und laden Sie die "
            "Seite neu.",
        ),
        "Tələbənin davam edən imtahan cəhdi yoxdur.": t(
            "The student has no exam attempt in progress.",
            "У студента нет текущей попытки экзамена.",
            "Öğrencinin devam eden sınav denemesi yok.",
            "Die studierende Person hat keinen laufenden Prüfungsversuch.",
        ),
    },
    REMINDER: {
        "Midterm imtahanınız sabah keçiriləcək": t(
            "Your midterm exam is tomorrow",
            "Ваш промежуточный экзамен состоится завтра",
            "Ara sınavınız yarın yapılacak",
            "Ihre Zwischenprüfung findet morgen statt",
        ),
        "Midterm imtahanınız yaxınlaşır": t(
            "Your midterm exam is approaching",
            "Приближается ваш промежуточный экзамен",
            "Ara sınavınız yaklaşıyor",
            "Ihre Zwischenprüfung rückt näher",
        ),
        "{exam} midterm imtahanı {start} tarixində keçiriləcək. İmtahan zalındakı "
        "kompüterdən /exams/midterm/ ünvanından istifadəçi adınız və PIN ilə daxil olun.": t(
            "The {exam} midterm exam takes place on {start}. Sign in from a computer in the exam hall at "
            "/exams/midterm/ with your username and PIN.",
            "Промежуточный экзамен {exam} состоится {start}. Войдите с компьютера в экзаменационном зале по адресу "
            "/exams/midterm/ с логином и PIN.",
            "{exam} ara sınavı {start} tarihinde yapılacak. Sınav salonundaki bilgisayardan /exams/midterm/ "
            "adresinden kullanıcı adınız ve PIN ile girin.",
            "Die Zwischenprüfung {exam} findet am {start} statt. Melden Sie sich an einem Computer im Prüfungssaal "
            "unter /exams/midterm/ mit Benutzername und PIN an.",
        ),
    },
    REPORT: {
        "İmtahan növü": t("Exam type", "Тип экзамена", "Sınav türü", "Prüfungsart"),
    },
    TPL_ENTRY: {
        "Midterm imtahan girişi": t(
            "Midterm exam entry",
            "Вход на промежуточный экзамен",
            "Ara sınav girişi",
            "Anmeldung zur Zwischenprüfung",
        ),
    },
    TPL_GATE: {
        "Midterm imtahanı": t("Midterm exam", "Промежуточный экзамен", "Ara sınav", "Zwischenprüfung"),
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
                msgstr = AZ_OVERRIDES.get((ctx, msgid), msgid)
            else:
                msgstr = translations.get(lang) or msgid
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
