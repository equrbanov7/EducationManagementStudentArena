#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-13 audit düzəlişlərinin yeni mesajları.

Audit EX-02: `/exams/code-check/` final imtahanı üçün rədd mesajı.
⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız əlavə edir və idempotentdir.
İstifadə:  python scripts/i18n_fill_audit_2026_09_13.py && python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "": {
        "delete_account_academic_history": {
            "az": "Bu hesabın akademik tarixçəsi (qeydiyyat, qiymət, imtahan cəhdi) var — tam silinə bilməz, yalnız arxivlənə bilər.",
            "en": "This account has academic history (enrolments, grades, exam attempts) — it cannot be hard-deleted, only archived.",
            "ru": "У этой учётной записи есть академическая история (зачисления, оценки, попытки экзаменов) — её нельзя удалить полностью, только архивировать.",
            "tr": "Bu hesabın akademik geçmişi (kayıt, not, sınav denemesi) var — tamamen silinemez, yalnızca arşivlenebilir.",
        },
    },
    "exams.view.access.message": {
        "final_exam_requires_center_entry": {
            "az": "Final imtahanına yalnız imtahan mərkəzinin giriş səhifəsindən (istifadəçi adı + PIN) daxil olmaq olar.",
            "en": "A final exam can only be entered from the exam-centre entry page (username + PIN).",
            "ru": "Войти на итоговый экзамен можно только со страницы входа экзаменационного центра (имя пользователя + PIN).",
            "tr": "Final sınavına yalnızca sınav merkezi giriş sayfasından (kullanıcı adı + PIN) girilebilir.",
        },
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
            ctx_line = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            if f'{ctx_line}msgid "{esc(msgid)}"\n' in text:
                continue
            msgstr = translations.get(lang) or translations["az"]
            blocks.append(f'{ctx_line}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
