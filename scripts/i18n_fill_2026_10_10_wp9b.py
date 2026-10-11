#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-10 WP9b: URL auditi (registrar/exams/accounts) + rubrik bayrağı.

Əlavə olunan mətnlər:
  * `registrar.catalog`: rubriklər gizli ikən (REGISTRAR_RUBRICS_ENABLED=False) kataloq
    bölməsinin alt-başlığı — «qiymətləndirmə rubrikləri» sözü olmadan.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_10_wp9b.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


RC = "registrar.catalog"

_CATALOG = [
    _t(
        "Akademik kataloq: ixtisaslar, fənlər, tədris planları, semestr açılışları "
        "və tələbə təyinatları. Hər əməl bu səhifədə, dialoqda aparılır — kabinetdən çıxmır.",
        "The academic catalogue: programmes, subjects, curricula, semester offerings "
        "and student assignments. Every action happens on this page, in a dialog — you never leave the cabinet.",
        "Академический каталог: специальности, предметы, учебные планы, открытия семестра "
        "и назначения студентов. Каждое действие выполняется на этой странице, в диалоге — не покидая кабинет.",
        "Akademik katalog: programlar, dersler, öğretim planları, dönem açılışları "
        "ve öğrenci atamaları. Her işlem bu sayfada, bir iletişim kutusunda yapılır — kabinetten çıkılmaz.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    RC: {row["az"]: row for row in _CATALOG},
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
