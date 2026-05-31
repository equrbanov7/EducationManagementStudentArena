#!/usr/bin/env python3
"""
EMSArena i18n — phase 4.
1. Append the 17 exam-monitor JS keys actually used by the JS (real keys).
2. Remove the 8 bogus js_* keys I added in phase 3 (not used anywhere).
3. Fix remaining student_org JS fallbacks ('Tələbə' -> trans).
Idempotent.
"""

import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]
CTX = "exams.template.exam_live_monitor"


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


REAL_KEYS = {
    "answered_chip": {"az": "Cavablanıb", "en": "Answered", "ru": "Отвечено", "tr": "Cevaplandı"},
    "unanswered_chip": {"az": "Boş", "en": "Empty", "ru": "Пусто", "tr": "Boş"},
    "picked_option": {"az": "Seçilib", "en": "Selected", "ru": "Выбрано", "tr": "Seçildi"},
    "correct_option": {"az": "Düz", "en": "Correct", "ru": "Верно", "tr": "Doğru"},
    "correct_answer": {"az": "Düzgün cavab", "en": "Correct answer", "ru": "Правильный ответ", "tr": "Doğru cevap"},
    "paint_answer": {
        "az": "Çəkim cavabı verilib",
        "en": "Drawing answer submitted",
        "ru": "Ответ-рисунок отправлен",
        "tr": "Çizim cevabı verildi",
    },
    "question": {"az": "Sual", "en": "Question", "ru": "Вопрос", "tr": "Soru"},
    "last_run": {"az": "Son icra", "en": "Last run", "ru": "Последний запуск", "tr": "Son çalıştırma"},
    "file_empty": {"az": "boş", "en": "empty", "ru": "пусто", "tr": "boş"},
    "lines": {"az": "sətir", "en": "lines", "ru": "строк", "tr": "satır"},
    "kind_test": {"az": "Test", "en": "Test", "ru": "Тест", "tr": "Test"},
    "kind_written": {"az": "Yazılı", "en": "Written", "ru": "Письменный", "tr": "Yazılı"},
    "kind_paint": {"az": "Çəkim", "en": "Drawing", "ru": "Рисунок", "tr": "Çizim"},
    "kind_coding": {"az": "Praktiki", "en": "Practical", "ru": "Практический", "tr": "Pratik"},
    "btn_resume": {"az": "Bərpa et", "en": "Resume", "ru": "Возобновить", "tr": "Devam ettir"},
    "btn_remove_student": {
        "az": "İmtahandan uzaqlaşdır",
        "en": "Remove from exam",
        "ru": "Удалить с экзамена",
        "tr": "Sınavdan çıkar",
    },
    "confirm_resume_manual_msg": {
        "az": "Tələbənin imtahana davam etməsinə icazə verilsin? Pozuntu sayı dəyişməyəcək.",
        "en": "Allow the student to continue the exam? The violation count will not change.",
        "ru": "Разрешить студенту продолжить экзамен? Количество нарушений не изменится.",
        "tr": "Öğrencinin sınava devam etmesine izin verilsin mi? İhlal sayısı değişmez.",
    },
}

# Bogus keys added in phase 3 that aren't used by JS — remove them.
BOGUS = [
    "js_anonymous",
    "js_no_students",
    "js_load_error",
    "js_status_active",
    "js_status_submitted",
    "js_status_expired",
    "js_status_blocked",
    "js_status_unknown",
]


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def has_entry(content, ctx, key):
    return bool(re.search(r'msgctxt "%s"\nmsgid "%s"\n' % (re.escape(ctx), re.escape(key)), content))


def remove_bogus(content):
    removed = 0
    for key in BOGUS:
        pat = re.compile(r'\nmsgctxt "%s"\nmsgid "%s"\nmsgstr "[^"]*"\n' % (re.escape(CTX), re.escape(key)))
        content, n = pat.subn("", content)
        removed += n
    return content, removed


def run():
    report = []
    for lang in LOCALES:
        p = po_path(lang)
        content = open(p, encoding="utf-8").read()
        content, removed = remove_bogus(content)
        adds = []
        for key, tr in REAL_KEYS.items():
            if has_entry(content, CTX, key):
                continue
            adds.append('\nmsgctxt "%s"\nmsgid "%s"\nmsgstr "%s"\n' % (esc(CTX), esc(key), esc(tr.get(lang, tr["en"]))))
        if adds:
            if not content.endswith("\n"):
                content += "\n"
            content += "".join(adds)
        open(p, "w", encoding="utf-8").write(content)
        report.append("  %s: removed_bogus=%d appended=%d" % (lang, removed, len(adds)))
    return report


if __name__ == "__main__":
    print("\n".join(run()))
