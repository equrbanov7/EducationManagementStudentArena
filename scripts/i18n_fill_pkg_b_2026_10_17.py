#!/usr/bin/env python3
"""EMSArena i18n — Paket B: müəllimin imtahan iş sahəsi (yoxlama, detal, statistika), 2026-10-17.

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
`{n}` / `{done}` / `{total}` yer tutucuları JS-də əvəz olunur (python-format deyil); `%(n)s` blocktrans-dır.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

GR = "exams.teacher.grading"
ST = "exams.teacher.statistics"
DT = "exams.teacher.exam_detail"

ENTRIES = {
    # `{% trans 'Sual %(n)s' %}` (JS sətri, teacher_check_attempt.html) — trans teqi «%»-i kataloqda «%%» saxlayır.
    "exams.attempt_review": {
        "Sual %%(n)s": {"en": "Question %%(n)s", "ru": "Вопрос %%(n)s", "tr": "Soru %%(n)s", "de": "Frage %%(n)s"},
    },
    GR: {
        "Balı tam ədədlə yazın (məs. 4).": {
            "en": "Enter the score as a whole number (e.g. 4).",
            "ru": "Введите балл целым числом (напр. 4).",
            "tr": "Puanı tam sayı olarak yazın (ör. 4).",
            "de": "Punkte als ganze Zahl eingeben (z. B. 4).",
        },
        "Maksimum bal": {
            "en": "Maximum points",
            "ru": "Максимальный балл",
            "tr": "Azami puan",
            "de": "Höchstpunktzahl",
        },
        "Bu cəhddə yoxlanılacaq sual yoxdur.": {
            "en": "This attempt has no questions to review.",
            "ru": "В этой попытке нет вопросов для проверки.",
            "tr": "Bu denemede değerlendirilecek soru yok.",
            "de": "Dieser Versuch enthält keine zu prüfenden Fragen.",
        },
        "Bütün suallar qiymətləndirilib": {
            "en": "All questions are graded",
            "ru": "Все вопросы оценены",
            "tr": "Tüm sorular puanlandı",
            "de": "Alle Fragen sind bewertet",
        },
        "Cəmi bal": {
            "en": "Total score",
            "ru": "Итоговый балл",
            "tr": "Toplam puan",
            "de": "Gesamtpunktzahl",
        },
        "Dəyişiklik yoxdur": {
            "en": "No changes",
            "ru": "Изменений нет",
            "tr": "Değişiklik yok",
            "de": "Keine Änderungen",
        },
        "Enter — tətbiq et və növbəti sual": {
            "en": "Enter — apply and go to the next question",
            "ru": "Enter — применить и перейти к следующему вопросу",
            "tr": "Enter — uygula ve sonraki soruya geç",
            "de": "Enter — übernehmen und zur nächsten Frage",
        },
        "Klaviatura qısayolları": {
            "en": "Keyboard shortcuts",
            "ru": "Сочетания клавиш",
            "tr": "Klavye kısayolları",
            "de": "Tastenkürzel",
        },
        "Növbəti qiymətləndirilməmiş": {
            "en": "Next ungraded",
            "ru": "Следующий неоценённый",
            "tr": "Sıradaki puanlanmamış",
            "de": "Nächste unbewertete",
        },
        "Növbəti sual": {
            "en": "Next question",
            "ru": "Следующий вопрос",
            "tr": "Sonraki soru",
            "de": "Nächste Frage",
        },
        "Qiymətləndirilib": {
            "en": "Graded",
            "ru": "Оценено",
            "tr": "Puanlandı",
            "de": "Bewertet",
        },
        "Qiymətləndirilib: {done} / {total}": {
            "en": "Graded: {done} / {total}",
            "ru": "Оценено: {done} / {total}",
            "tr": "Puanlandı: {done} / {total}",
            "de": "Bewertet: {done} / {total}",
        },
        "Sual %(n)s: ətraflı bax və AI ilə qiymətləndir": {
            "en": "Question %(n)s: open details and grade with AI",
            "ru": "Вопрос %(n)s: подробнее и оценка с помощью ИИ",
            "tr": "Soru %(n)s: ayrıntıları aç ve yapay zekâ ile puanla",
            "de": "Frage %(n)s: Details öffnen und mit KI bewerten",
        },
        "Tez bal": {
            "en": "Quick score",
            "ru": "Быстрый балл",
            "tr": "Hızlı puan",
            "de": "Schnellbewertung",
        },
        "Tələbənin cavabı": {
            "en": "Student's answer",
            "ru": "Ответ студента",
            "tr": "Öğrencinin cevabı",
            "de": "Antwort des Studierenden",
        },
        "Tətbiq et": {
            "en": "Apply",
            "ru": "Применить",
            "tr": "Uygula",
            "de": "Übernehmen",
        },
        "Yadda saxla": {
            "en": "Save",
            "ru": "Сохранить",
            "tr": "Kaydet",
            "de": "Speichern",
        },
        "Yadda saxlanmamış dəyişiklik: {n} sual": {
            "en": "Unsaved changes: {n} question(s)",
            "ru": "Несохранённые изменения: вопросов — {n}",
            "tr": "Kaydedilmemiş değişiklik: {n} soru",
            "de": "Ungespeicherte Änderungen: {n} Frage(n)",
        },
        "Yadda saxlanılır…": {
            "en": "Saving…",
            "ru": "Сохранение…",
            "tr": "Kaydediliyor…",
            "de": "Wird gespeichert…",
        },
        "dialoqu bağla": {
            "en": "close the dialog",
            "ru": "закрыть окно",
            "tr": "pencereyi kapat",
            "de": "Dialog schließen",
        },
        "istəyə bağlı": {
            "en": "optional",
            "ru": "необязательно",
            "tr": "isteğe bağlı",
            "de": "optional",
        },
        "növbəti sualın balı": {
            "en": "score of the next question",
            "ru": "балл следующего вопроса",
            "tr": "sonraki sorunun puanı",
            "de": "Punkte der nächsten Frage",
        },
        "yadda saxla": {
            "en": "save",
            "ru": "сохранить",
            "tr": "kaydet",
            "de": "speichern",
        },
        "Ətraflı": {
            "en": "Details",
            "ru": "Подробнее",
            "tr": "Ayrıntılar",
            "de": "Details",
        },
        "Əvvəlki sual": {
            "en": "Previous question",
            "ru": "Предыдущий вопрос",
            "tr": "Önceki soru",
            "de": "Vorherige Frage",
        },
        "əvvəlki sual": {
            "en": "previous question",
            "ru": "предыдущий вопрос",
            "tr": "önceki soru",
            "de": "vorherige Frage",
        },
    },
    ST: {
        "Daha çox filtr": {
            "en": "More filters",
            "ru": "Больше фильтров",
            "tr": "Daha fazla filtre",
            "de": "Weitere Filter",
        },
        "Növbəti səhifə": {
            "en": "Next page",
            "ru": "Следующая страница",
            "tr": "Sonraki sayfa",
            "de": "Nächste Seite",
        },
        "Əvvəlki səhifə": {
            "en": "Previous page",
            "ru": "Предыдущая страница",
            "tr": "Önceki sayfa",
            "de": "Vorherige Seite",
        },
    },
    DT: {
        "%(n)s aktiv": {
            "en": "%(n)s active",
            "ru": "активных: %(n)s",
            "tr": "%(n)s etkin",
            "de": "davon %(n)s aktiv",
        },
        "Canlı sessiya": {
            "en": "Live session",
            "ru": "Живая сессия",
            "tr": "Canlı oturum",
            "de": "Live-Sitzung",
        },
        "Digər": {
            "en": "More",
            "ru": "Ещё",
            "tr": "Diğer",
            "de": "Mehr",
        },
        "Testi auditoriyada canlı keçirin — tələbələr PIN ilə qoşulur, nəticələr dərhal görünür.": {
            "en": "Run the test live in class — students join with a PIN and results appear instantly.",
            "ru": "Проведите тест вживую в аудитории — студенты подключаются по PIN, результаты видны сразу.",
            "tr": "Testi sınıfta canlı yapın — öğrenciler PIN ile katılır, sonuçlar anında görünür.",
            "de": "Führen Sie den Test live im Hörsaal durch — Studierende treten per PIN bei, Ergebnisse erscheinen sofort.",
        },
        "İmtahan bölmələri": {
            "en": "Exam sections",
            "ru": "Разделы экзамена",
            "tr": "Sınav bölümleri",
            "de": "Prüfungsbereiche",
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
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
