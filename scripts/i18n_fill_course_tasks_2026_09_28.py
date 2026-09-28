#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-28 «kurs tapşırıqları: sərbəst iş / lab / layihə düzəlişləri».

Kurs dashboard-unun tapşırıq bölmələri (assignments / labs / projects) və
imtahan bölməsindəki ad-hoc sətirlər:

  * `{% trans 'Cavablarım (' %}{{ n }})` fraqmentləri → `Cavablarım (%(attempts)s)`
    (blocktrans, hər bölmə öz kontekstində);
  * `remove_student_from_assignment` JSON mesajları (əvvəl sabit AZ/EN mətn);
  * lab modalı: «Sil» düyməsi (JS-də sabit 'Sil' idi), «heç nə seçilməsə — bütün kurs» ipucu;
  * manage_blocks.js bildiriş toast-ının «Bağla» aria-label-i;
  * exam_section / _exam_modals kontekstsiz AZ msgid-ləri → öz kontekstində.

msgid-lər AZ cümlədir (az msgstr = msgid) — `compilemessages`-dən əvvəl də
az mətn düzgün görünür və mövcud testlərin AZ mətn yoxlamaları pozulmur.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Orkestrator serial işlədir; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_course_tasks_2026_09_28.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

MY_ANSWERS = {
    "en": "My answers (%(attempts)s)",
    "ru": "Мои ответы (%(attempts)s)",
    "tr": "Cevaplarım (%(attempts)s)",
}

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    "assignment.section": {
        "Cavablarım (%(attempts)s)": MY_ANSWERS,
        "Hələ başlamayıb": {"en": "Not started yet", "ru": "Ещё не началось", "tr": "Henüz başlamadı"},
    },
    "projects.section": {
        "Cavablarım (%(attempts)s)": MY_ANSWERS,
    },
    "labs.template.lab_section": {
        "Cavablarım (%(attempts)s)": MY_ANSWERS,
    },
    "exams.partial.exam_section": {
        "Cavablarım (%(attempts)s)": MY_ANSWERS,
        "Detallı imtahana bax": {
            "en": "View exam details",
            "ru": "Подробнее об экзамене",
            "tr": "Sınav ayrıntılarını görüntüle",
        },
    },
    "exams.partial.exam_modals": {
        "Form yüklənmədi. Yenidən cəhd edin.": {
            "en": "The form could not be loaded. Please try again.",
            "ru": "Не удалось загрузить форму. Попробуйте ещё раз.",
            "tr": "Form yüklenemedi. Lütfen tekrar deneyin.",
        },
        "Yadda saxlanılır...": {"en": "Saving...", "ru": "Сохранение...", "tr": "Kaydediliyor..."},
    },
    "assignments.views.message": {
        "Bu sorğu üsuluna icazə verilmir.": {
            "en": "This request method is not allowed.",
            "ru": "Этот метод запроса не разрешён.",
            "tr": "Bu istek yöntemine izin verilmiyor.",
        },
        "Düzgün tələbə ID-si göndərilməlidir.": {
            "en": "A valid student ID is required.",
            "ru": "Требуется корректный ID студента.",
            "tr": "Geçerli bir öğrenci kimliği gerekli.",
        },
        "Tələbə bu kursda tapılmadı.": {
            "en": "The student was not found in this course.",
            "ru": "Студент не найден в этом курсе.",
            "tr": "Öğrenci bu derste bulunamadı.",
        },
        "%(name)s sərbəst işdən çıxarıldı.": {
            "en": "%(name)s was removed from the assignment.",
            "ru": "Студент %(name)s исключён из самостоятельной работы.",
            "tr": "%(name)s ödevden çıkarıldı.",
        },
    },
    "labs.js.lab_modals": {
        "Sil": {"en": "Delete", "ru": "Удалить", "tr": "Sil"},
    },
    "labs.template.lab_modals": {
        "Heç bir qrup və ya tələbə seçilməsə, lab kursun bütün tələbələrinə açıq olur.": {
            "en": "If no group or student is selected, the lab is open to every student in the course.",
            "ru": "Если не выбрана ни одна группа и ни один студент, лабораторная открыта всем студентам курса.",
            "tr": "Hiçbir grup veya öğrenci seçilmezse laboratuvar dersin tüm öğrencilerine açık olur.",
        },
    },
    "labs.js.manage_blocks": {
        "Bağla": {"en": "Close", "ru": "Закрыть", "tr": "Kapat"},
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
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
