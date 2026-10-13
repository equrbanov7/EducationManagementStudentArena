#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-13 (gecə): alman dili (``de``) interfeysə əlavə olundu.

Əlavə olunan mətnlər:
* ``language`` / ``name_de`` — dil seçicisində (``templates/partials/_language_switcher.html``)
  alman dilinin adı, hər interfeys dilində öz adı ilə (az/en/ru/tr/de).

Tam alman kataloqu (``locale/de/``) bu skriptlə YOX, ``scripts/i18n_locale_sync.py`` ilə
yaradılıb; bu skript yalnız yeni msgid-i beş kataloqun hamısına yazır.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_german_2026_10_13.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr", "de")


def _t(az, en, ru, tr, de):
    return {"az": az, "en": en, "ru": ru, "tr": tr, "de": de}


# ctx → msgid → {az, en, ru, tr, de}
ENTRIES = {
    "django": {
        "language": {
            "name_de": _t("Alman dili", "German", "Немецкий", "Almanca", "Deutsch"),
        },
    },
}

#: Hazırda məcburi düzəliş yoxdur (yalnız boş/fuzzy girişlər doldurulur).
FORCE: set = set()


def fill(lang, domain="django"):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
    if not os.path.exists(path):
        print(f"{lang}: {domain}.po yoxdur — ötürüldü")
        return
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES[domain].items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                flags = ["python-format"] if "%(" in msgid else []
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want, flags=flags))
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
