#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-28 audit remediasiyası, iş paketi B2.

Əlavə olunan mətnlər:
  * `registrar.enrollment_status` / «Suspended» — Audit 2026-09-28 S1: xaric
    edilmiş / akademik məzuniyyətdəki tələbənin cari dövr qeydiyyatı dondurulur.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_b2_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

ES = "registrar.enrollment_status"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    ES: {
        "Suspended": {
            "az": "Dondurulub",
            "en": "Suspended",
            "ru": "Приостановлено",
            "tr": "Donduruldu",
        },
    },
}

# Mövcud olan, amma yanlış/qarışıq dildə olan tərcümələr — həmişə üstələnir.
FORCE: set = set()


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
