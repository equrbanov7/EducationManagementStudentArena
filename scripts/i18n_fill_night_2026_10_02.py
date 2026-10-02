#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-02 gecə düzəlişləri (sahib yatarkən, «tap və düzəlt»).

Əlavə olunan mətnlər:
  * `exams.final_center.room_admin`: sıfır/yayım/multicast MAC rədd mesajı (EXAMQA R3).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_night_2026_10_02.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

RA = "exams.final_center.room_admin"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_MAC_SPECIAL = "Bu MAC ünvanı kompüterə aid ola bilməz (sıfır, yayım və ya multicast): %(mac)s"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    RA: {
        _MAC_SPECIAL: _t(
            _MAC_SPECIAL,
            "This MAC address cannot belong to a computer (zero, broadcast or multicast): %(mac)s",
            "Этот MAC-адрес не может принадлежать компьютеру (нулевой, широковещательный или multicast): %(mac)s",
            "Bu MAC adresi bir bilgisayara ait olamaz (sıfır, yayın veya multicast): %(mac)s",
        ),
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
