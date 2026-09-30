#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-30 naviqasiya qabığı (NAV).

Əlavə olunan mətnlər (`profile.sidebar`):
  * «Tənzimləmələr» — sol menyunun sonundakı hesab ayarları qrupu
    (`accounts/profile/sidebar/_group_settings.html`);
  * «Parol sıfırlama» — icazə ilə görünən bənd (`items/_password_reset.html`,
    bölməni PWD qurur: `account-password-reset`);
  * «Sorğular» — doldurulmalı sorğular (`items/_surveys_inbox.html`, SRV bölməsi
    `surveys-inbox`).

«Profili redaktə et» / «Şifrəni dəyiş» mövcud tərcümələrdən (`profile.sidebar/edit_profile`,
`profile.section/change_password`) istifadə edir — yeni mətn deyil.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_nav_2026_09_30.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

SB = "profile.sidebar"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    SB: {
        "Tənzimləmələr": {
            "az": "Tənzimləmələr",
            "en": "Settings",
            "ru": "Настройки",
            "tr": "Ayarlar",
        },
        "Parol sıfırlama": {
            "az": "Parol sıfırlama",
            "en": "Password reset",
            "ru": "Сброс пароля",
            "tr": "Şifre sıfırlama",
        },
        "Sorğular": {
            "az": "Sorğular",
            "en": "Surveys",
            "ru": "Опросы",
            "tr": "Anketler",
        },
    },
}

# Mövcud, lakin yanlış dildə olan tərcümələr — həmişə üstələnir (hələlik yoxdur).
FORCE = set()


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
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
