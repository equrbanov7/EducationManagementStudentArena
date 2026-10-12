#!/usr/bin/env python3
"""EMSArena i18n — rol auditi 2026-10-13 (roleaudit): yeni icazə açarlarının redaktor etiketləri.

`apps/organizations/permissions_role_audit.py`: `exam_center.decide`, `student.records_view`,
`user.import_staff`, `notification.publish` (msgid AZ cümlədir → az msgstr = msgid).

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir.

İstifadə:  python scripts/i18n_fill_roleaudit_2026_10_13.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CTX = "organizations.permission.label"

ENTRIES = {
    CTX: {
        "İmtahan mərkəzinin qərarları (ikinci şans, kollokvium pəncərəsi, sual göndərişi)": {
            "en": "Exam centre decisions (second chance, colloquium window, question submissions)",
            "ru": "Решения экзаменационного центра (вторая попытка, окно коллоквиума, заявки вопросов)",
            "tr": "Sınav merkezi kararları (ikinci hak, kolokyum penceresi, soru gönderimleri)",
        },
        "Akademik qeydlərə baxış (ÜOMG, transkript)": {
            "en": "View academic records (GPA, transcript)",
            "ru": "Просмотр академических записей (средний балл, транскрипт)",
            "tr": "Akademik kayıtları görüntüleme (GNO, transkript)",
        },
        "Müəllim/heyət hesablarının toplu idxalı": {
            "en": "Bulk import of teacher/staff accounts",
            "ru": "Массовый импорт учётных записей преподавателей/сотрудников",
            "tr": "Öğretmen/personel hesaplarının toplu içe aktarımı",
        },
        "Bildiriş göndərmək (alıcılar öz əhatəsində)": {
            "en": "Send notifications (recipients within own scope)",
            "ru": "Отправлять уведомления (получатели в пределах своей области)",
            "tr": "Bildirim göndermek (alıcılar kendi kapsamında)",
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
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
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
