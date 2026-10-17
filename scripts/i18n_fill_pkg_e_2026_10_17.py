#!/usr/bin/env python3
"""EMSArena i18n — Paket E: kurs paneli + laboratoriya səhifələri redizaynı (2026-10-17).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud (msgctxt, msgid) cütü atılır); sonra
`compilemessages -i .claude -i venv`. Yalnız Paket E şablonlarında YENİ yazılan sətirlər buradadır —
dəyişməyən köhnə açar-msgid-lər (məs. «heading_blocks_questions») öz kataloq girişlərini saxlayır.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ENTRIES = {
    # ── Lab «Bloklar və suallar» (manage_blocks.html) ───────────────────────────
    "labs.template.manage_blocks": {
        "Sual bloklarını yaradın və hər blokdan hər tələbəyə neçə sual düşəcəyini təyin edin.": {
            "en": "Create question blocks and set how many questions from each block each student gets.",
            "ru": "Создавайте блоки вопросов и задавайте, сколько вопросов из каждого блока получает студент.",
            "tr": "Soru blokları oluşturun ve her öğrencinin her bloktan kaç soru alacağını belirleyin.",
            "de": "Erstellen Sie Fragenblöcke und legen Sie fest, wie viele Fragen aus jedem Block jede Person erhält.",
        },
    },
    "labs.js.manage_blocks": {
        "Məcburi sahələri doldurun.": {
            "en": "Please fill in the required fields.",
            "ru": "Заполните обязательные поля.",
            "tr": "Lütfen zorunlu alanları doldurun.",
            "de": "Bitte füllen Sie die Pflichtfelder aus.",
        },
    },
    # ── Tələbənin lab səhifəsi (lab_detail.html) ────────────────────────────────
    "labs.template.lab_detail": {
        "Maksimum fayl ölçüsü %(mb)s MB": {
            "en": "Maximum file size: %(mb)s MB",
            "ru": "Максимальный размер файла: %(mb)s МБ",
            "tr": "Maksimum dosya boyutu: %(mb)s MB",
            "de": "Maximale Dateigröße: %(mb)s MB",
        },
        "Sualı aç/bağla": {
            "en": "Expand / collapse question",
            "ru": "Развернуть / свернуть вопрос",
            "tr": "Soruyu aç / kapat",
            "de": "Frage ein- / ausklappen",
        },
        "Faylı sil": {
            "en": "Remove file",
            "ru": "Удалить файл",
            "tr": "Dosyayı kaldır",
            "de": "Datei entfernen",
        },
    },
    # ── «Mənim cavablarım» (my_lab_answers.html) ────────────────────────────────
    "labs.template.my_lab_answers": {
        "Cavabı aç/bağla": {
            "en": "Expand / collapse answer",
            "ru": "Развернуть / свернуть ответ",
            "tr": "Cevabı aç / kapat",
            "de": "Antwort ein- / ausklappen",
        },
    },
    # ── Müəllimin qiymətləndirmə səhifəsi (grade_submission.html) ───────────────
    "labs.template.grade_submission": {
        "Bu suala bal": {
            "en": "Score for this question",
            "ru": "Балл за этот вопрос",
            "tr": "Bu soruya puan",
            "de": "Punkte für diese Frage",
        },
        "Bu suala bal (0 – %(max)s)": {
            "en": "Score for this question (0 – %(max)s)",
            "ru": "Балл за этот вопрос (0 – %(max)s)",
            "tr": "Bu soruya puan (0 – %(max)s)",
            "de": "Punkte für diese Frage (0 – %(max)s)",
        },
        "Tələbə adı qiymətləndirmə tamamlanana qədər gizlidir.": {
            "en": "The student's name stays hidden until grading is complete.",
            "ru": "Имя студента скрыто до завершения проверки.",
            "tr": "Öğrenci adı değerlendirme tamamlanana kadar gizlidir.",
            "de": "Der Name der Person bleibt bis zum Abschluss der Bewertung verborgen.",
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
