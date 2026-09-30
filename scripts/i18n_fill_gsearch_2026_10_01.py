#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-01 qlobal axtarış: telefonda «Bağla», «Son baxılanlar» (sahib).

Əlavə olunan mətnlər (`search`, `templates/partials/_global_search.html`): mobil bağla düyməsi və
istifadəçinin son açdığı menyu bölmələri qrupunun başlığı (data-atributla JS-ə ötürülür).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_gsearch_2026_10_01.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

SEARCH = "search"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_ROWS = [
    _t("Bağla", "Close", "Закрыть", "Kapat"),
    _t("Son baxılanlar", "Recently opened", "Недавно открытые", "Son açılanlar"),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {SEARCH: {row["az"]: row for row in _ROWS}}

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
