#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-14: vahid yazdıqca-axtarış qatı (sahib: «search-lərdə debounce
düzgün işləmir, çox sürətli olur; yazarkən search gedir, render olur, axtardığım itir»).

Əlavə olunan mətnlər (hamısı `djangojs.po`-dadır, kontekst `ui.search`):
  * «Axtarılır…» — `static/js/ems_search_input.js` `EMSSearchInput.busy()` nişanı
    (`pgettext("ui.search", …)`): sorğu gedərkən input-un altında görünən kiçik status.

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan / boş blokları doldurur,
idempotentdir. Sonra: `python manage.py compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_searchux_2026_10_14.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr", "de")

SEARCH = "ui.search"

# (kontekst, az, en, ru, tr, de)
ROWS = [
    (SEARCH, "Axtarılır…", "Searching…", "Поиск…", "Aranıyor…", "Suche läuft…"),
]  # fmt: skip

ENTRIES: dict = {}
for ctx, az, en, ru, tr, de in ROWS:
    ENTRIES.setdefault(ctx, {})[az] = {"az": az, "en": en, "ru": ru, "tr": tr, "de": de}


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "djangojs.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if stale and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
