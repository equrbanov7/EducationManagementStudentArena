#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-28 audit F2 (DB-03 admission control).

Əlavə olunan mətn:
  * `core.middleware.concurrency_limit.message` — proses başına in-flight sorğu
    tavanı dolanda 503 cavabının gövdəsi (core/middleware_concurrency.py).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_f2_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

CL = "core.middleware.concurrency_limit.message"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    CL: {
        "Server hazırda çox yüklüdür. Bir neçə saniyədən sonra yenidən cəhd edin.": {
            "az": "Server hazırda çox yüklüdür. Bir neçə saniyədən sonra yenidən cəhd edin.",
            "en": "The server is busy right now. Please try again in a few seconds.",
            "ru": "Сервер сейчас перегружен. Повторите попытку через несколько секунд.",
            "tr": "Sunucu şu anda çok yoğun. Lütfen birkaç saniye sonra tekrar deneyin.",
        },
    },
}

# Mövcud (səhv) tərcümə olsa belə üstələnən açarlar.
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
