#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-30 ilk girişdə e-poçtu dəyişmək, «Kod gəlmir?» köməyi (sahib).

Əlavə olunan mətnlər (`accounts.first_login`, `accounts/first_login_set_password.html`):
e-poçtu xatırlamayan üçün ipucu, «Ünvan səhvdir? E-poçtu dəyiş», «Kod gəlmir?» siyahısı.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_email_2026_09_30.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

FL = "accounts.first_login"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_ROWS = [
    _t(
        "Universitet e-poçtunuzu xatırlamırsınızsa, istifadə etdiyiniz istənilən şəxsi e-poçtu (məs. Gmail) yazın — "
        "kod ora gələcək və parolu unutsanız bərpa da bu ünvanla olacaq.",
        "If you don't remember your university e-mail, enter any personal e-mail you use (e.g. Gmail) — the code "
        "will be sent there, and it will also be used to recover your password.",
        "Если вы не помните университетскую почту, укажите любую личную почту, которой пользуетесь (например, "
        "Gmail), — код придёт туда, и она же будет использоваться для восстановления пароля.",
        "Üniversite e-postanızı hatırlamıyorsanız kullandığınız herhangi bir kişisel e-postayı (ör. Gmail) yazın — "
        "kod oraya gelecek ve şifrenizi unutursanız kurtarma da bu adresle yapılacak.",
    ),
    _t("Ünvan səhvdir?", "Wrong address?", "Неверный адрес?", "Adres yanlış mı?"),
    _t("E-poçtu dəyiş", "Change e-mail", "Изменить почту", "E-postayı değiştir"),
    _t("Kod gəlmir?", "No code?", "Код не пришёл?", "Kod gelmedi mi?"),
    _t(
        "1–2 dəqiqə gözləyin və «Spam» / «Promotions» qovluğuna baxın.",
        "Wait 1–2 minutes and check the Spam / Promotions folder.",
        "Подождите 1–2 минуты и проверьте папки «Спам» / «Промоакции».",
        "1–2 dakika bekleyin ve «Spam» / «Promosyonlar» klasörüne bakın.",
    ),
    _t(
        "Ünvanı səhv yazmısınızsa, «E-poçtu dəyiş» ilə düzəldin.",
        "If you mistyped the address, fix it with “Change e-mail”.",
        "Если адрес введён с ошибкой, исправьте его через «Изменить почту».",
        "Adresi yanlış yazdıysanız «E-postayı değiştir» ile düzeltin.",
    ),
    _t(
        "Problem qalırsa, RİM mərkəzinə müraciət edin — parolunuzu yerində sıfırlaya bilərlər.",
        "If the problem persists, contact the Digital Development Centre (RİM) — they can reset your password on "
        "the spot.",
        "Если проблема не решается, обратитесь в Центр цифрового развития (RİM) — там могут сразу сбросить пароль.",
        "Sorun devam ederse RİM merkezine başvurun — şifrenizi yerinde sıfırlayabilirler.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {FL: {row["az"]: row for row in _ROWS}}

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
