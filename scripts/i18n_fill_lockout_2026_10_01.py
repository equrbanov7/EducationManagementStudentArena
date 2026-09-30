#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-01 giriş bloku geri sayımı və xəta səhifələri (sahib).

Əlavə olunan mətnlər:
  * `accounts.login.lockout` (`accounts/login.html`): blok banneri, geri sayım, «vaxt bitdi», ipucu;
  * kontekstsiz «Menyudan davam edin» (`errors/404.html` — əvvəl tərcüməsiz sabit mətn idi).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_lockout_2026_10_01.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

LO = "accounts.login.lockout"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_LOCKOUT = [
    _t(
        "Giriş müvəqqəti dayandırıldı",
        "Sign-in temporarily paused",
        "Вход временно приостановлен",
        "Giriş geçici olarak durduruldu",
    ),
    _t(
        "Təhlükəsizlik üçün yenidən cəhd etməzdən əvvəl gözləyin:",
        "For security, please wait before trying again:",
        "В целях безопасности подождите перед следующей попыткой:",
        "Güvenlik için tekrar denemeden önce bekleyin:",
    ),
    _t(
        "Vaxt bitdi — indi yenidən daxil olmağa cəhd edə bilərsiniz.",
        "Time is up — you can try to sign in again now.",
        "Время вышло — теперь можно снова попробовать войти.",
        "Süre doldu — şimdi yeniden giriş yapmayı deneyebilirsiniz.",
    ),
    _t(
        "Parolu xatırlamırsınızsa, «Parolu unutdum» keçidindən istifadə edin və ya RİM mərkəzinə müraciət edin.",
        "If you don't remember your password, use “Forgot password” or contact the Digital Development "
        "Centre (RİM).",
        "Если не помните пароль, воспользуйтесь ссылкой «Забыли пароль» или обратитесь в Центр цифрового "
        "развития (RİM).",
        "Şifrenizi hatırlamıyorsanız «Şifremi unuttum» bağlantısını kullanın veya RİM merkezine başvurun.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    LO: {row["az"]: row for row in _LOCKOUT},
    "": {
        "Menyudan davam edin": _t(
            "Menyudan davam edin", "Continue from the menu", "Продолжите через меню", "Menüden devam edin"
        )
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
