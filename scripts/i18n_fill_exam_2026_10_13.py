#!/usr/bin/env python3
"""EMSArena i18n — rol auditi 2026-10-13 B1 «imtahan mərkəzinin qərarları açarla» (exam).

İmtahan mərkəzi işçisi / RİM əməkdaşı apellyasiya, ikinci şans, midterm pəncərəsi və sual
göndərişi bölmələrini YALNIZ GÖRÜR; qərar `appeal.respond` + `appeal.decide` və
`exam_center.decide` açarları ilədir. Əlavə olunan mətnlər: yalnız-baxış bannerləri + 403 mesajları
(msgid AZ cümlədir → az msgstr = msgid).

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir.
Orkestrator serial işlədir; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_exam_2026_10_13.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    "appeals.template": {
        (
            "Apellyasiyaya baxa bilərsiniz, amma qərarı yalnız «Apellyasiya qərarı vermək» səlahiyyəti olan "
            "istifadəçi (imtahan mərkəzi rəhbəri) verir."
        ): {
            "en": (
                "You can view this appeal, but only a user with the “Decide appeals” permission "
                "(the exam centre head) can decide it."
            ),
            "ru": (
                "Вы можете просматривать апелляцию, но решение принимает только пользователь с правом "
                "«Принимать решение по апелляции» (руководитель экзаменационного центра)."
            ),
            "tr": (
                "İtirazı görüntüleyebilirsiniz, ancak kararı yalnızca «İtiraz kararı verme» yetkisine sahip "
                "kullanıcı (sınav merkezi başkanı) verir."
            ),
        },
    },
    "appeals.view.message": {
        "Apellyasiya qərarı vermək icazəniz yoxdur.": {
            "en": "You do not have permission to decide appeals.",
            "ru": "У вас нет права принимать решения по апелляциям.",
            "tr": "İtiraz kararı verme yetkiniz yok.",
        },
    },
    "accounts.exam_chance": {
        "İmtahan şansı vermək üçün qərar səlahiyyətiniz yoxdur.": {
            "en": "You do not have the decision permission required to grant exam chances.",
            "ru": "У вас нет права принимать решения, чтобы предоставлять дополнительную попытку.",
            "tr": "Sınav hakkı vermek için karar yetkiniz yok.",
        },
        (
            "Yalnız baxış: imtahan şansını «İmtahan mərkəzinin qərarları» səlahiyyəti olan istifadəçi "
            "(imtahan mərkəzi rəhbəri) verir."
        ): {
            "en": (
                "View only: exam chances are granted by a user with the “Exam centre decisions” permission "
                "(the exam centre head)."
            ),
            "ru": (
                "Только просмотр: дополнительную попытку предоставляет пользователь с правом «Решения "
                "экзаменационного центра» (руководитель экзаменационного центра)."
            ),
            "tr": (
                "Yalnızca görüntüleme: sınav hakkını «Sınav merkezi kararları» yetkisine sahip kullanıcı "
                "(sınav merkezi başkanı) verir."
            ),
        },
    },
    "accounts.kollokvium_windows": {
        "Pəncərələri dəyişmək üçün qərar səlahiyyətiniz yoxdur.": {
            "en": "You do not have the decision permission required to change the windows.",
            "ru": "У вас нет права принимать решения, чтобы изменять окна.",
            "tr": "Pencereleri değiştirmek için karar yetkiniz yok.",
        },
    },
    "registrar.kollokvium_window": {
        (
            "Yalnız baxış: pəncərələri «İmtahan mərkəzinin qərarları» səlahiyyəti olan istifadəçi "
            "(imtahan mərkəzi rəhbəri) təyin edir və dəyişir."
        ): {
            "en": (
                "View only: the windows are set and changed by a user with the “Exam centre decisions” "
                "permission (the exam centre head)."
            ),
            "ru": (
                "Только просмотр: окна назначает и изменяет пользователь с правом «Решения экзаменационного "
                "центра» (руководитель экзаменационного центра)."
            ),
            "tr": (
                "Yalnızca görüntüleme: pencereleri «Sınav merkezi kararları» yetkisine sahip kullanıcı "
                "(sınav merkezi başkanı) belirler ve değiştirir."
            ),
        },
    },
    "exams.view.question_submission.permission": {
        "Göndərişə qərar vermək səlahiyyətiniz yoxdur.": {
            "en": "You do not have permission to decide on this submission.",
            "ru": "У вас нет права принимать решение по этой отправке.",
            "tr": "Bu gönderim hakkında karar verme yetkiniz yok.",
        },
    },
    "exams.template.question_submission": {
        (
            "Yalnız baxış: göndərişə qərarı «İmtahan mərkəzinin qərarları» səlahiyyəti olan istifadəçi "
            "(imtahan mərkəzi rəhbəri) verir."
        ): {
            "en": (
                "View only: the decision on this submission is made by a user with the “Exam centre "
                "decisions” permission (the exam centre head)."
            ),
            "ru": (
                "Только просмотр: решение по отправке принимает пользователь с правом «Решения "
                "экзаменационного центра» (руководитель экзаменационного центра)."
            ),
            "tr": (
                "Yalnızca görüntüleme: gönderim hakkındaki kararı «Sınav merkezi kararları» yetkisine sahip "
                "kullanıcı (sınav merkezi başkanı) verir."
            ),
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
