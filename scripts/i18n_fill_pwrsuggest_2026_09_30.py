#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-30 «Parol sıfırlama»: yazdıqca təklif siyahısı (sahib).

Əlavə olunan mətnlər (`accounts.password_reset`, `apps/accounts/views/account_password_reset.py`
`_js_strings` → `json_script`): boş nəticə və klaviatura ipucu.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_pwrsuggest_2026_09_30.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

PR = "accounts.password_reset"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_ROWS = [
    _t(
        "Uyğun istifadəçi yoxdur — adı və ya soyadı yoxlayın.",
        "No matching users — check the name or surname.",
        "Подходящих пользователей нет — проверьте имя или фамилию.",
        "Eşleşen kullanıcı yok — adı veya soyadı kontrol edin.",
    ),
    _t(
        "Seçmək üçün klikləyin və ya ↑ ↓ və Enter istifadə edin.",
        "Click to choose, or use ↑ ↓ and Enter.",
        "Нажмите, чтобы выбрать, или используйте ↑ ↓ и Enter.",
        "Seçmek için tıklayın veya ↑ ↓ ve Enter kullanın.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {PR: {row["az"]: row for row in _ROWS}}

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
