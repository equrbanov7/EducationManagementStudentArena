#!/usr/bin/env python3
"""
EMSArena i18n cleanup — phase 2.
Adds catalog entries for pending_review_detail and re-uses the appender from
i18n_fix.py. Also processes additional templates with targeted replacements.
Idempotent.
"""

import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


CATALOG = {
    # ---- pending_review_detail ----
    ("accounts.pending_review_detail", "title"): {
        "az": "Yoxlama",
        "en": "Review",
        "ru": "Проверка",
        "tr": "Değerlendirme",
    },
    ("accounts.pending_review_detail", "subtitle"): {
        "az": "Yoxlama detalları",
        "en": "Review details",
        "ru": "Детали проверки",
        "tr": "Değerlendirme ayrıntıları",
    },
    ("accounts.pending_review_detail", "back"): {"az": "Geri", "en": "Back", "ru": "Назад", "tr": "Geri"},
    ("accounts.pending_review_detail", "student_answer"): {
        "az": "Tələbə cavabı",
        "en": "Student answer",
        "ru": "Ответ студента",
        "tr": "Öğrenci cevabı",
    },
    ("accounts.pending_review_detail", "student"): {"az": "Tələbə", "en": "Student", "ru": "Студент", "tr": "Öğrenci"},
    ("accounts.pending_review_detail", "exam"): {"az": "İmtahan", "en": "Exam", "ru": "Экзамен", "tr": "Sınav"},
    ("accounts.pending_review_detail", "date"): {"az": "Tarix", "en": "Date", "ru": "Дата", "tr": "Tarih"},
    ("accounts.pending_review_detail", "grading"): {
        "az": "Qiymətləndirmə",
        "en": "Grading",
        "ru": "Оценивание",
        "tr": "Değerlendirme",
    },
    ("accounts.pending_review_detail", "score_per_question"): {
        "az": "Sual üzrə bal",
        "en": "Score per question",
        "ru": "Балл за вопрос",
        "tr": "Soru başına puan",
    },
    ("accounts.pending_review_detail", "feedback"): {
        "az": "Rəy",
        "en": "Feedback",
        "ru": "Отзыв",
        "tr": "Geri bildirim",
    },
    ("accounts.pending_review_detail", "feedback_ph"): {
        "az": "Tələbə üçün qısa və aydın rəy yazın",
        "en": "Write short, clear feedback for the student",
        "ru": "Напишите краткий и понятный отзыв для студента",
        "tr": "Öğrenci için kısa ve net bir geri bildirim yazın",
    },
    ("accounts.pending_review_detail", "save_grade"): {
        "az": "Qiyməti yadda saxla",
        "en": "Save grade",
        "ru": "Сохранить оценку",
        "tr": "Notu kaydet",
    },
    # ---- category_management (extra hardcoded bits; title/subtitle already trans) ----
    ("profile.category_management", "search_ph"): {
        "az": "Kateqoriya axtar...",
        "en": "Search categories...",
        "ru": "Поиск категорий...",
        "tr": "Kategori ara...",
    },
    ("profile.category_management", "search"): {"az": "Axtar", "en": "Search", "ru": "Поиск", "tr": "Ara"},
    ("profile.category_management", "search_clear"): {
        "az": "Axtarışı təmizlə",
        "en": "Clear search",
        "ru": "Очистить поиск",
        "tr": "Aramayı temizle",
    },
    ("profile.category_management", "edit"): {"az": "Düzəliş et", "en": "Edit", "ru": "Редактировать", "tr": "Düzenle"},
    ("profile.category_management", "delete"): {"az": "Sil", "en": "Delete", "ru": "Удалить", "tr": "Sil"},
    ("profile.category_management", "empty"): {
        "az": "Hələ kateqoriya yoxdur.",
        "en": "No categories yet.",
        "ru": "Категорий пока нет.",
        "tr": "Henüz kategori yok.",
    },
    ("profile.category_management", "save"): {"az": "Yadda saxla", "en": "Save", "ru": "Сохранить", "tr": "Kaydet"},
    ("profile.category_management", "cancel"): {"az": "Ləğv et", "en": "Cancel", "ru": "Отмена", "tr": "İptal"},
    ("profile.category_management", "delete_confirm"): {
        "az": "Silməni təsdiqlə",
        "en": "Confirm deletion",
        "ru": "Подтвердить удаление",
        "tr": "Silmeyi onayla",
    },
}


# Template targeted replacements
def make_T(ctx, quote="dq"):
    if quote == "dq":
        return lambda k: '{%% trans "%s" context "%s" %%}' % (k, ctx)
    return lambda k: "{%% trans '%s' context '%s' %%}" % (k, ctx)


TEMPLATE_EDITS = {
    "apps/accounts/templates/accounts/profile/sections/_category_management.html": (
        "profile.category_management",
        [
            (
                'placeholder="Kateqoriya axtar..."',
                "placeholder=\"{% trans 'search_ph' context 'profile.category_management' %}\"",
            ),
            (
                'aria-label="Axtarışı təmizlə"',
                "aria-label=\"{% trans 'search_clear' context 'profile.category_management' %}\"",
            ),
            (
                '<button type="submit" class="btn btn-primary">Axtar</button>',
                '<button type="submit" class="btn btn-primary">{% trans "search" context "profile.category_management" %}</button>',
            ),
            ('aria-label="Düzəliş et"', "aria-label=\"{% trans 'edit' context 'profile.category_management' %}\""),
            ('aria-label="Sil"', "aria-label=\"{% trans 'delete' context 'profile.category_management' %}\""),
            ("<p>Hələ kateqoriya yoxdur.</p>", '<p>{% trans "empty" context "profile.category_management" %}</p>'),
        ],
    ),
}


def apply_template_edits():
    report = []
    for rel, (ctx, edits) in TEMPLATE_EDITS.items():
        p = os.path.join(BASE, rel)
        with open(p, encoding="utf-8") as f:
            content = f.read()
        orig = content
        for old, new in edits:
            if old in content:
                content = content.replace(old, new)
            elif new not in content:
                report.append("  ! NOT FOUND %s: %r" % (rel, old[:55]))
        if content != orig:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            report.append("  ~ edited " + rel)
    return report


def po_has_entry(content, ctx, key):
    pat = re.compile(r'msgctxt "%s"\nmsgid "%s"\n' % (re.escape(ctx), re.escape(key)))
    return bool(pat.search(content))


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def append_po_entries():
    report = []
    for lang in LOCALES:
        p = po_path(lang)
        with open(p, encoding="utf-8") as f:
            content = f.read()
        adds = []
        for (ctx, key), tr in CATALOG.items():
            if po_has_entry(content, ctx, key):
                continue
            msgstr = tr.get(lang, tr["en"])
            adds.append('\nmsgctxt "%s"\nmsgid "%s"\nmsgstr "%s"\n' % (esc(ctx), esc(key), esc(msgstr)))
        if adds:
            if not content.endswith("\n"):
                content += "\n"
            content += "".join(adds)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            report.append("  + %s: appended %d" % (lang, len(adds)))
        else:
            report.append("  = %s: nothing" % lang)
    return report


if __name__ == "__main__":
    lines = ["== template edits =="]
    lines += apply_template_edits()
    lines += ["== po appends =="]
    lines += append_po_entries()
    out = "\n".join(lines)
    with open(os.path.join(BASE, "scripts", "_phase2_out.txt"), "w", encoding="utf-8") as f:
        f.write(out)
    print("done")
