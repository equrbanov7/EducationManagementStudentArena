#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-30 təhlükəsizlik baxışı düzəlişləri.

Əlavə olunan mətnlər:
  * `accounts.first_login` (`accounts/first_login_set_password.html`,
    `apps/accounts/views/auth/first_login.py`): e-poçtu artıq təsdiqli hesab administrasiya
    sıfırlamasından sonra OTP-siz yeni parol təyin edir;
  * `exams.service.lifecycle` (`apps/exams/services/question_invariants.py`): cavablı sual
    silinmir — deaktiv etmək təklif olunur.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_review_2026_09_30.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

FL = "accounts.first_login"
LC = "exams.service.lifecycle"
QB_MSG = (
    "Seçilmiş suallardan bəzilərinə tələbələrin cavabları və ya apellyasiyaları var. Silinsələr imtahan "
    "nəticələri və tarixçəsi itər. Bunun əvəzinə sualları deaktiv edin — imtahandan çıxarılırlar, amma "
    "cavablar və nəticələr qalır."
)

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    LC: {
        QB_MSG: {
            "az": QB_MSG,
            "en": "Some of the selected questions have student answers or appeals. Deleting them would erase exam "
            "results and history. Deactivate the questions instead — they are removed from the exam, but answers "
            "and results are kept.",
            "ru": "На некоторые из выбранных вопросов есть ответы студентов или апелляции. Их удаление сотрёт "
            "результаты и историю экзамена. Вместо этого деактивируйте вопросы — они будут убраны из экзамена, "
            "а ответы и результаты сохранятся.",
            "tr": "Seçilen soruların bazılarında öğrenci cevapları veya itirazlar var. Silinirlerse sınav sonuçları "
            "ve geçmişi kaybolur. Bunun yerine soruları devre dışı bırakın — sınavdan çıkarılırlar, ancak cevaplar "
            "ve sonuçlar korunur.",
        },
    },
    FL: {
        "Parolunuz administrasiya tərəfindən sıfırlanıb. Davam etmək üçün özünüzə yeni parol təyin edin.": {
            "az": "Parolunuz administrasiya tərəfindən sıfırlanıb. Davam etmək üçün özünüzə yeni parol təyin edin.",
            "en": "Your password was reset by the administration. Set a new password to continue.",
            "ru": "Ваш пароль был сброшен администрацией. Чтобы продолжить, задайте новый пароль.",
            "tr": "Şifreniz yönetim tarafından sıfırlandı. Devam etmek için yeni bir şifre belirleyin.",
        },
        "Yeni parol müvəqqəti paroldan fərqli olmalıdır.": {
            "az": "Yeni parol müvəqqəti paroldan fərqli olmalıdır.",
            "en": "The new password must be different from the temporary password.",
            "ru": "Новый пароль должен отличаться от временного.",
            "tr": "Yeni şifre geçici şifreden farklı olmalıdır.",
        },
    },
}

FORCE = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
