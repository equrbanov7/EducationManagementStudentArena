#!/usr/bin/env python3
"""EMSArena i18n — zal monitoru modalı: imtahan mərkəzinin «PIN-i göstər» / «Yeni PIN ver» /
«Başqa kompüterdə davam et» düymələri (sahib 2026-10-26, canlı imtahan).

Bax ``apps/exams/views/exam_center/ticket_pin.py`` + ``_snapshot_modal.html``. msgid AZ cümlədir →
az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur); sonra
`compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ENTRIES = {
    "exams.final_center.monitor_pin": {
        "Çox tez-tez sorğu — bir az sonra yenidən cəhd edin.": {
            "en": "Too many requests — please try again in a moment.",
            "ru": "Слишком частые запросы — повторите попытку чуть позже.",
            "tr": "Çok sık istek — lütfen biraz sonra yeniden deneyin.",
            "de": "Zu viele Anfragen – bitte versuchen Sie es gleich noch einmal.",
        },
        "Tələbə bu imtahana artıq təyin olunmayıb (qrupu dəyişdirilib və ya imtahandan çıxarılıb) — "
        "PIN ilə girsə də imtahana başlaya bilməyəcək. İmtahan mərkəzində təyinatı yoxlayın.": {
            "en": "The student is no longer assigned to this exam (group changed or excluded from the exam) — "
            "even with the PIN they will not be able to start. Check the assignment in the exam centre.",
            "ru": "Студент больше не назначен на этот экзамен (сменилась группа или исключён из экзамена) — "
            "даже войдя по PIN, он не сможет начать. Проверьте назначение в экзаменационном центре.",
            "tr": "Öğrenci artık bu sınava atanmamış (grubu değişmiş veya sınavdan çıkarılmış) — "
            "PIN ile girse bile sınava başlayamaz. Sınav merkezinde atamayı kontrol edin.",
            "de": "Der Studierende ist dieser Prüfung nicht mehr zugeordnet (Gruppe gewechselt oder von der "
            "Prüfung ausgeschlossen) – auch mit der PIN kann er nicht beginnen. Prüfen Sie die Zuordnung "
            "im Prüfungszentrum.",
        },
        "Bu tələbə üçün PIN göstərilə bilməz (imtahan bitib və ya oturum bağlıdır).": {
            "en": "The PIN cannot be shown for this student (the exam has finished or the session is closed).",
            "ru": "PIN для этого студента показать нельзя (экзамен завершён или сеанс закрыт).",
            "tr": "Bu öğrenci için PIN gösterilemez (sınav bitti veya oturum kapalı).",
            "de": "Die PIN kann für diesen Studierenden nicht angezeigt werden (Prüfung beendet oder Sitzung "
            "geschlossen).",
        },
        "PIN tapılmadı — «Yeni PIN ver» ilə tələbəyə təzə PIN verin.": {
            "en": "No PIN found — issue a fresh PIN with “Issue new PIN”.",
            "ru": "PIN не найден — выдайте студенту новый PIN кнопкой «Выдать новый PIN».",
            "tr": "PIN bulunamadı — «Yeni PIN ver» ile öğrenciye yeni PIN verin.",
            "de": "Keine PIN gefunden – geben Sie mit „Neue PIN ausgeben“ eine neue PIN aus.",
        },
        "Yeni PIN yalnız imtahana hələ başlamamış tələbəyə verilir. İmtahanda olan tələbə üçün "
        "«Yenidən giriş ver» və ya «Başqa kompüterdə davam et» düyməsindən istifadə edin.": {
            "en": "A new PIN can only be issued to a student who has not started the exam yet. For a student "
            "already in the exam use “Grant re-entry” or “Continue on another computer”.",
            "ru": "Новый PIN выдаётся только студенту, который ещё не начал экзамен. Для студента на экзамене "
            "используйте «Разрешить повторный вход» или «Продолжить на другом компьютере».",
            "tr": "Yeni PIN yalnızca sınava henüz başlamamış öğrenciye verilir. Sınavdaki öğrenci için "
            "«Yeniden giriş ver» veya «Başka bilgisayarda devam et» düğmesini kullanın.",
            "de": "Eine neue PIN wird nur an Studierende ausgegeben, die die Prüfung noch nicht begonnen haben. "
            "Für Studierende in der Prüfung verwenden Sie „Wiedereintritt gewähren“ oder „Auf anderem "
            "Computer fortsetzen“.",
        },
        "Tələbənin davam edən imtahan cəhdi yoxdur.": {
            "en": "The student has no exam attempt in progress.",
            "ru": "У студента нет незавершённой попытки экзамена.",
            "tr": "Öğrencinin devam eden sınav denemesi yok.",
            "de": "Der Studierende hat keinen laufenden Prüfungsversuch.",
        },
        "Hazırdır — tələbə %(minutes)d dəqiqə ərzində başqa qeydli kompüterdən öz PIN-i ilə daxil olub "
        "imtahanı qaldığı yerdən davam etdirə bilər (vaxt dayanmır, cavablar qorunur).": {
            "en": "Done — within %(minutes)d minutes the student can sign in on another registered computer "
            "with their own PIN and continue the exam where they left off (the timer keeps running, "
            "answers are kept).",
            "ru": "Готово — в течение %(minutes)d минут студент может войти со своим PIN на другом "
            "зарегистрированном компьютере и продолжить экзамен с того же места (время идёт, ответы "
            "сохраняются).",
            "tr": "Hazır — öğrenci %(minutes)d dakika içinde kayıtlı başka bir bilgisayardan kendi PIN'i ile "
            "girip sınava kaldığı yerden devam edebilir (süre durmaz, cevaplar korunur).",
            "de": "Fertig – innerhalb von %(minutes)d Minuten kann sich der Studierende an einem anderen "
            "registrierten Computer mit seiner eigenen PIN anmelden und die Prüfung dort fortsetzen, wo er "
            "aufgehört hat (die Zeit läuft weiter, Antworten bleiben erhalten).",
        },
        "Cəhd hələ heç bir kompüterə bağlanmayıb — tələbə öz PIN-i ilə istənilən qeydli kompüterdən davam "
        "edə bilər.": {
            "en": "The attempt is not bound to any computer yet — the student can continue from any registered "
            "computer with their own PIN.",
            "ru": "Попытка ещё не привязана к компьютеру — студент может продолжить со своим PIN на любом "
            "зарегистрированном компьютере.",
            "tr": "Deneme henüz hiçbir bilgisayara bağlanmadı — öğrenci kendi PIN'i ile kayıtlı herhangi bir "
            "bilgisayardan devam edebilir.",
            "de": "Der Versuch ist noch an keinen Computer gebunden – der Studierende kann mit seiner eigenen "
            "PIN an jedem registrierten Computer fortfahren.",
        },
        "Tələbəyə yeni PIN verilsin? Köhnə PIN dərhal etibarsız olacaq.": {
            "en": "Issue a new PIN to the student? The old PIN will stop working immediately.",
            "ru": "Выдать студенту новый PIN? Старый PIN сразу станет недействительным.",
            "tr": "Öğrenciye yeni PIN verilsin mi? Eski PIN hemen geçersiz olacak.",
            "de": "Dem Studierenden eine neue PIN ausgeben? Die alte PIN wird sofort ungültig.",
        },
        "Tələbə başqa kompüterdən davam etsin? Köhnə kompüterdəki sessiya dayanacaq; vaxt və cavablar "
        "qorunur.": {
            "en": "Let the student continue on another computer? The session on the old computer will stop; "
            "time and answers are kept.",
            "ru": "Разрешить студенту продолжить на другом компьютере? Сеанс на старом компьютере "
            "остановится; время и ответы сохраняются.",
            "tr": "Öğrenci başka bir bilgisayardan devam etsin mi? Eski bilgisayardaki oturum duracak; süre ve "
            "cevaplar korunur.",
            "de": "Soll der Studierende auf einem anderen Computer fortfahren? Die Sitzung auf dem alten "
            "Computer wird beendet; Zeit und Antworten bleiben erhalten.",
        },
        "Əməliyyat mümkün olmadı.": {
            "en": "The action could not be completed.",
            "ru": "Не удалось выполнить действие.",
            "tr": "İşlem gerçekleştirilemedi.",
            "de": "Die Aktion konnte nicht ausgeführt werden.",
        },
        "PIN-i göstər": {
            "en": "Show PIN",
            "ru": "Показать PIN",
            "tr": "PIN'i göster",
            "de": "PIN anzeigen",
        },
        "Gizlət": {
            "en": "Hide",
            "ru": "Скрыть",
            "tr": "Gizle",
            "de": "Ausblenden",
        },
        "Yeni PIN verildi — tələbəyə deyin.": {
            "en": "New PIN issued — tell it to the student.",
            "ru": "Новый PIN выдан — сообщите его студенту.",
            "tr": "Yeni PIN verildi — öğrenciye söyleyin.",
            "de": "Neue PIN ausgegeben – teilen Sie sie dem Studierenden mit.",
        },
        "Giriş PIN-i:": {
            "en": "Entry PIN:",
            "ru": "PIN для входа:",
            "tr": "Giriş PIN'i:",
            "de": "Zugangs-PIN:",
        },
        "Yeni PIN ver": {
            "en": "Issue new PIN",
            "ru": "Выдать новый PIN",
            "tr": "Yeni PIN tanımla",
            "de": "Neue PIN ausgeben",
        },
        "Başqa kompüterdə davam et": {
            "en": "Continue on another computer",
            "ru": "Продолжить на другом компьютере",
            "tr": "Başka bilgisayarda devam et",
            "de": "Auf anderem Computer fortsetzen",
        },
        "Kompüter xarab olubsa: tələbə başqa qeydli kompüterdən /exams/final/ (və ya /exams/midterm/) "
        "səhifəsində istifadəçi adı + bu PIN ilə daxil olur.": {
            "en": "If the computer has failed: the student signs in on another registered computer at "
            "/exams/final/ (or /exams/midterm/) with their username + this PIN.",
            "ru": "Если компьютер вышел из строя: студент входит на другом зарегистрированном компьютере на "
            "странице /exams/final/ (или /exams/midterm/) с логином и этим PIN.",
            "tr": "Bilgisayar arızalandıysa: öğrenci kayıtlı başka bir bilgisayardan /exams/final/ (veya "
            "/exams/midterm/) sayfasında kullanıcı adı + bu PIN ile giriş yapar.",
            "de": "Falls der Computer ausgefallen ist: Der Studierende meldet sich an einem anderen "
            "registrierten Computer unter /exams/final/ (oder /exams/midterm/) mit Benutzername + dieser "
            "PIN an.",
        },
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
            msgstr = translations.get("az", msgid) if lang == "az" else (translations.get(lang) or msgid)
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
