#!/usr/bin/env python3
"""EMSArena i18n — «Dəyərləndirilmiş nəticələr» + «Bax» (cəhd baxışı) yenidən dizaynı (2026-10-17).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RR = "accounts.review_results"
AR = "exams.attempt_review"

ENTRIES = {
    RR: {
        "Apellyasiya": {
            "en": "Appeal",
            "ru": "Апелляция",
            "tr": "İtiraz",
            "de": "Einspruch",
        },
        "Apellyasiya: %(status)s": {
            "en": "Appeal: %(status)s",
            "ru": "Апелляция: %(status)s",
            "tr": "İtiraz: %(status)s",
            "de": "Einspruch: %(status)s",
        },
        "Axtarış": {
            "en": "Search",
            "ru": "Поиск",
            "tr": "Arama",
            "de": "Suche",
        },
        "Axtarışı qısaldın və ya «Sıfırla» ilə bütün nəticələrə qayıdın.": {
            "en": "Shorten the search or use “Reset” to return to all results.",
            "ru": "Сократите запрос или нажмите «Сбросить», чтобы вернуться ко всем результатам.",
            "tr": "Aramayı kısaltın veya «Sıfırla» ile tüm sonuçlara dönün.",
            "de": "Kürzen Sie die Suche oder kehren Sie mit „Zurücksetzen“ zu allen Ergebnissen zurück.",
        },
        "Açıq: %(n)s": {
            "en": "Open: %(n)s",
            "ru": "Открыто: %(n)s",
            "tr": "Açık: %(n)s",
            "de": "Offen: %(n)s",
        },
        "Bax: %(student)s — %(title)s": {
            "en": "View: %(student)s — %(title)s",
            "ru": "Открыть: %(student)s — %(title)s",
            "tr": "Görüntüle: %(student)s — %(title)s",
            "de": "Ansehen: %(student)s — %(title)s",
        },
        "Bütün qruplar": {
            "en": "All groups",
            "ru": "Все группы",
            "tr": "Tüm gruplar",
            "de": "Alle Gruppen",
        },
        "Bütün vaxtlar": {
            "en": "All time",
            "ru": "За всё время",
            "tr": "Tüm zamanlar",
            "de": "Gesamter Zeitraum",
        },
        "Dövr": {
            "en": "Period",
            "ru": "Период",
            "tr": "Dönem",
            "de": "Zeitraum",
        },
        "Dəyərləndirilib": {
            "en": "Reviewed",
            "ru": "Оценено",
            "tr": "Değerlendirildi",
            "de": "Bewertet",
        },
        "Dəyərləndirilmiş nəticələr": {
            "en": "Reviewed results",
            "ru": "Оценённые результаты",
            "tr": "Değerlendirilmiş sonuçlar",
            "de": "Bewertete Ergebnisse",
        },
        "Filtrə uyğun nəticə tapılmadı": {
            "en": "No results match the filters",
            "ru": "Нет результатов по фильтрам",
            "tr": "Filtrelere uyan sonuç bulunamadı",
            "de": "Keine Ergebnisse für diese Filter",
        },
        "Hələ dəyərləndirilmiş nəticə yoxdur": {
            "en": "No reviewed results yet",
            "ru": "Оценённых результатов пока нет",
            "tr": "Henüz değerlendirilmiş sonuç yok",
            "de": "Noch keine bewerteten Ergebnisse",
        },
        "Növ": {
            "en": "Type",
            "ru": "Тип",
            "tr": "Tür",
            "de": "Art",
        },
        "Nəticə": {
            "en": "Result",
            "ru": "Результат",
            "tr": "Sonuç",
            "de": "Ergebnis",
        },
        "Nəticə: %(n)s": {
            "en": "Results: %(n)s",
            "ru": "Результатов: %(n)s",
            "tr": "Sonuç: %(n)s",
            "de": "Ergebnisse: %(n)s",
        },
        "Qrup": {
            "en": "Group",
            "ru": "Группа",
            "tr": "Grup",
            "de": "Gruppe",
        },
        "Qrup: %(n)s": {
            "en": "Groups: %(n)s",
            "ru": "Групп: %(n)s",
            "tr": "Grup: %(n)s",
            "de": "Gruppen: %(n)s",
        },
        "Son 30 gün": {
            "en": "Last 30 days",
            "ru": "Последние 30 дней",
            "tr": "Son 30 günde",
            "de": "Letzte 30 Tage",
        },
        "Son 7 gün": {
            "en": "Last 7 days",
            "ru": "Последние 7 дней",
            "tr": "Son 7 günde",
            "de": "Letzte 7 Tage",
        },
        "Son 90 gün": {
            "en": "Last 90 days",
            "ru": "Последние 90 дней",
            "tr": "Son 90 günde",
            "de": "Letzte 90 Tage",
        },
        "Sıralama": {
            "en": "Sort",
            "ru": "Сортировка",
            "tr": "Sıralama düzeni",
            "de": "Sortierung",
        },
        "Tapşırıq": {
            "en": "Task",
            "ru": "Задание",
            "tr": "Görev",
            "de": "Aufgabe",
        },
        "Tarix": {
            "en": "Date",
            "ru": "Дата",
            "tr": "Tarih",
            "de": "Datum",
        },
        "Tələbə": {
            "en": "Student",
            "ru": "Студент",
            "tr": "Öğrenci",
            "de": "Studierende",
        },
        "Tələbə, imtahan və ya fənn": {
            "en": "Student, exam or course",
            "ru": "Студент, экзамен или предмет",
            "tr": "Öğrenci, sınav veya ders",
            "de": "Studierende, Prüfung oder Fach",
        },
        "Yoxlama pəncərəsi bağlanmış imtahan, lab və tapşırıq nəticələri. «Bax» cavabları sual-sual açır.": {
            "en": "Exam, lab and task results whose review window has closed. “View” opens the answers question by question.",
            "ru": "Результаты экзаменов, лабораторных и заданий с закрытым окном проверки. «Открыть» показывает ответы по вопросам.",
            "tr": "İnceleme süresi kapanmış sınav, laboratuvar ve görev sonuçları. «Görüntüle» cevapları soru soru açar.",
            "de": "Prüfungs-, Labor- und Aufgabenergebnisse mit geschlossenem Prüffenster. „Ansehen“ öffnet die Antworten Frage für Frage.",
        },
        "Yoxlanılan işlər redaktə pəncərəsi bağlandıqdan sonra burada görünür; test imtahanları — təhvil verilən kimi.": {
            "en": "Checked work appears here once its edit window closes; test exams appear as soon as they are submitted.",
            "ru": "Проверенные работы появляются здесь после закрытия окна редактирования; тестовые экзамены — сразу после сдачи.",
            "tr": "Kontrol edilen işler düzenleme süresi kapandıktan sonra burada görünür; test sınavları teslim edilir edilmez.",
            "de": "Geprüfte Arbeiten erscheinen hier, sobald das Bearbeitungsfenster schließt; Testprüfungen sofort nach der Abgabe.",
        },
        "Yoxlayan": {
            "en": "Reviewer",
            "ru": "Проверяющий",
            "tr": "Değerlendiren",
            "de": "Prüfer/in",
        },
        "bu həftə qiymətləndirilən": {
            "en": "reviewed this week",
            "ru": "оценено за неделю",
            "tr": "bu hafta değerlendirilen",
            "de": "diese Woche bewertet",
        },
        "İmtahan — test": {
            "en": "Exam — test",
            "ru": "Экзамен — тест",
            "tr": "Sınav — test",
            "de": "Prüfung — Test",
        },
        "İmtahan — yazılı": {
            "en": "Exam — written",
            "ru": "Экзамен — письменный",
            "tr": "Sınav — yazılı",
            "de": "Prüfung — schriftlich",
        },
        "İmtahan: %(exams)s · digər iş: %(other)s": {
            "en": "Exams: %(exams)s · other work: %(other)s",
            "ru": "Экзамены: %(exams)s · другие работы: %(other)s",
            "tr": "Sınav: %(exams)s · diğer iş: %(other)s",
            "de": "Prüfungen: %(exams)s · andere Arbeiten: %(other)s",
        },
        "İmtahanlar (hamısı)": {
            "en": "Exams (all)",
            "ru": "Экзамены (все)",
            "tr": "Sınavlar (tümü)",
            "de": "Prüfungen (alle)",
        },
        "Əməliyyat": {
            "en": "Action",
            "ru": "Действие",
            "tr": "İşlem",
            "de": "Aktion",
        },
        "Ən köhnəsi əvvəl": {
            "en": "Oldest first",
            "ru": "Сначала старые",
            "tr": "Önce en eski",
            "de": "Älteste zuerst",
        },
        "Ən yenisi əvvəl": {
            "en": "Newest first",
            "ru": "Сначала новые",
            "tr": "Önce en yeni",
            "de": "Neueste zuerst",
        },
    },
    AR: {
        "0 bal": {
            "en": "0 points",
            "ru": "0 баллов",
            "tr": "0 puan",
            "de": "0 Punkte",
        },
        "Apellyasiya ilə düzəldilib": {
            "en": "Adjusted by appeal",
            "ru": "Исправлено по апелляции",
            "tr": "İtirazla düzeltildi",
            "de": "Durch Einspruch korrigiert",
        },
        "Avtomatik qiymətləndirilib": {
            "en": "Auto-graded",
            "ru": "Оценено автоматически",
            "tr": "Otomatik puanlandı",
            "de": "Automatisch bewertet",
        },
        "Bal": {
            "en": "Score",
            "ru": "Балл",
            "tr": "Puan",
            "de": "Punkte",
        },
        "Başlayıb": {
            "en": "Started",
            "ru": "Начато",
            "tr": "Başladı",
            "de": "Begonnen",
        },
        "Bitirib": {
            "en": "Finished",
            "ru": "Завершено",
            "tr": "Bitirdi",
            "de": "Beendet",
        },
        "Cavablar": {
            "en": "Answers",
            "ru": "Ответы",
            "tr": "Cevaplar",
            "de": "Antworten",
        },
        "Cavabsız": {
            "en": "Unanswered",
            "ru": "Без ответа",
            "tr": "Cevapsız",
            "de": "Unbeantwortet",
        },
        "Cəhd haqqında": {
            "en": "About the attempt",
            "ru": "О попытке",
            "tr": "Deneme hakkında",
            "de": "Zum Versuch",
        },
        "Düzgün cavab": {
            "en": "Correct answer",
            "ru": "Правильный ответ",
            "tr": "Doğru cevap",
            "de": "Richtige Antwort",
        },
        "Düzgün": {
            "en": "Correct",
            "ru": "Верно",
            "tr": "Doğru",
            "de": "Richtig",
        },
        "Geri": {
            "en": "Back",
            "ru": "Назад",
            "tr": "Geri dön",
            "de": "Zurück",
        },
        "Müəllimin ümumi rəyi": {
            "en": "Teacher's overall feedback",
            "ru": "Общий отзыв преподавателя",
            "tr": "Öğretmenin genel yorumu",
            "de": "Gesamtfeedback der Lehrkraft",
        },
        "Naviqasiya": {
            "en": "Navigation",
            "ru": "Навигация",
            "tr": "Gezinme",
            "de": "Navigation",
        },
        "Nümunə (gözlənilən) cavab": {
            "en": "Model (expected) answer",
            "ru": "Образец (ожидаемый) ответа",
            "tr": "Örnek (beklenen) cevap",
            "de": "Musterlösung (erwartete Antwort)",
        },
        "Nəticə xülasəsi": {
            "en": "Result summary",
            "ru": "Сводка результата",
            "tr": "Sonuç özeti",
            "de": "Ergebnisübersicht",
        },
        "Qazanılan / maksimum bal": {
            "en": "Earned / maximum points",
            "ru": "Набрано / максимум баллов",
            "tr": "Kazanılan / azami puan",
            "de": "Erreicht / maximale Punkte",
        },
        "Qismən": {
            "en": "Partial",
            "ru": "Частично",
            "tr": "Kısmen",
            "de": "Teilweise",
        },
        "Qismən bal": {
            "en": "Partial credit",
            "ru": "Частичный балл",
            "tr": "Kısmi puan",
            "de": "Teilpunkte",
        },
        "Qiymətləndirilməyib": {
            "en": "Not graded",
            "ru": "Не оценено",
            "tr": "Puanlanmadı",
            "de": "Nicht bewertet",
        },
        "Sual": {
            "en": "Questions",
            "ru": "Вопросы",
            "tr": "Soru",
            "de": "Fragen",
        },
        "Sual %(n)s": {
            "en": "Question %(n)s",
            "ru": "Вопрос %(n)s",
            "tr": "Soru %(n)s",
            "de": "Frage %(n)s",
        },
        "Sual %(n)s: %(state)s": {
            "en": "Question %(n)s: %(state)s",
            "ru": "Вопрос %(n)s: %(state)s",
            "tr": "Soru %(n)s: %(state)s",
            "de": "Frage %(n)s: %(state)s",
        },
        "Sual xəritəsi": {
            "en": "Question map",
            "ru": "Карта вопросов",
            "tr": "Soru haritası",
            "de": "Fragenübersicht",
        },
        "Səhv": {
            "en": "Wrong",
            "ru": "Неверно",
            "tr": "Yanlış",
            "de": "Falsch",
        },
        "Tam bal": {
            "en": "Full marks",
            "ru": "Полный балл",
            "tr": "Tam puan",
            "de": "Volle Punktzahl",
        },
        "Tələbənin seçimi": {
            "en": "Student's choice",
            "ru": "Выбор студента",
            "tr": "Öğrencinin seçimi",
            "de": "Auswahl der/des Studierenden",
        },
        "Təqdimat haqqında": {
            "en": "About the submission",
            "ru": "О работе",
            "tr": "Teslim hakkında",
            "de": "Zur Abgabe",
        },
        "Variantlar": {
            "en": "Options",
            "ru": "Варианты",
            "tr": "Seçenekler",
            "de": "Antwortoptionen",
        },
        "Yoxlanılacaq işlər": {
            "en": "Work to review",
            "ru": "Работы на проверку",
            "tr": "İncelenecek işler",
            "de": "Zu prüfende Arbeiten",
        },
        "Yoxlanılmayıb": {
            "en": "Not checked",
            "ru": "Не проверено",
            "tr": "Kontrol edilmedi",
            "de": "Nicht geprüft",
        },
        "Yoxlanılıb": {
            "en": "Checked",
            "ru": "Проверено",
            "tr": "Kontrol edildi",
            "de": "Geprüft",
        },
        "Yoxlayan müəllim": {
            "en": "Reviewing teacher",
            "ru": "Проверяющий преподаватель",
            "tr": "Değerlendiren öğretmen",
            "de": "Prüfende Lehrkraft",
        },
        "Çap et": {
            "en": "Print",
            "ru": "Печать",
            "tr": "Yazdır",
            "de": "Drucken",
        },
        "Ümumi müddət": {
            "en": "Total duration",
            "ru": "Общая длительность",
            "tr": "Toplam süre",
            "de": "Gesamtdauer",
        },
        "İmtahanın bütün nəticələri": {
            "en": "All results of this exam",
            "ru": "Все результаты экзамена",
            "tr": "Sınavın tüm sonuçları",
            "de": "Alle Ergebnisse der Prüfung",
        },
        "Əvvəlki bal": {
            "en": "Original score",
            "ru": "Исходный балл",
            "tr": "Önceki puan",
            "de": "Ursprüngliche Punkte",
        },
    },
}


#: Mövcud səhv tərcümələrin düzəlişi (yalnız msgstr hələ köhnə səhv dəyərdirsə — idempotent).
#: «label_student_answer» en/ru/tr kataloqlarında «Students / Студенты / Öğrenciler» idi; yeni baxış
#: səhifəsində blok başlığıdır («Tələbənin cavabı»).
FIXES = {
    ("exams.template.teacher_view_attempt", "label_student_answer"): {
        "en": ("Students", "Student's answer"),
        "ru": ("Студенты", "Ответ студента"),
        "tr": ("Öğrenciler", "Öğrencinin cevabı"),
    },
}


def apply_fixes(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    fixed = 0
    for (ctx, msgid), per_lang in FIXES.items():
        if lang not in per_lang:
            continue
        bad, good = per_lang[lang]
        old = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(bad)}"\n'
        if old in text:
            text = text.replace(old, f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(good)}"\n')
            fixed += 1
    if fixed:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: {fixed} fix")


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
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
        apply_fixes(locale)
