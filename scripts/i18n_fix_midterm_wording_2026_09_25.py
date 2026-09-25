#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: mövcud tərcümələrdə «kollokvium» → «midterm» (2026/2027 qaydası).

Yeni msgid əlavə ETMİR — yalnız msgstr-i «final/kollokvium» deyən paylaşılan girişləri yeniləyir
(dəyişən hər dəyər çap olunur). İdempotent: ikinci icra heç nə dəyişmir.
İstifadə:  python scripts/i18n_fix_midterm_wording_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: {(msgctxt, msgid): {lang: (köhnə alt-sətir, yeni alt-sətir)}}
REPLACEMENTS = {
    ("exams.model.access", "already_examined_today"): {
        "az": ("final/kollokvium", "final/midterm"),
        "ru": ("финал/коллоквиум", "финал/мидтерм"),
    },
}


#: YENİ girişlər (şablonda msgid dəyişdi): {(msgctxt, az_msgid): (en, ru, tr)}; AZ msgstr = msgid.
ADDITIONS = {
    (
        "registrar.journal_close",
        "Müəllimlərin jurnalında sürüşən zolaqda görünür — İmtahan Mərkəzinin midterm bildirişi kimi.",
    ): (
        "It appears in the sliding banner of the teachers' journal — like the Exam Centre's midterm notice.",
        "Отображается в бегущей строке журнала преподавателей — как уведомление экзаменационного центра о мидтерме.",
        "Öğretmenlerin defterinde kayan şeritte görünür — Sınav Merkezinin vize bildirimi gibi.",
    ),
}


def _add_missing():
    for index, lang in enumerate(("az", "en", "ru", "tr")):
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid) for e in po}
        added = 0
        for (ctx, msgid), translations in ADDITIONS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else translations[index - 1]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        if added:
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added} yeni giriş")


def main():
    _add_missing()
    touched = {}
    for (ctx, msgid), per_lang in REPLACEMENTS.items():
        for lang, (old, new) in per_lang.items():
            touched.setdefault(lang, []).append((ctx, msgid, old, new))
    for lang, items in touched.items():
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        index = {(e.msgctxt, e.msgid): e for e in po}
        changed = 0
        for ctx, msgid, old, new in items:
            entry = index.get((ctx, msgid))
            if entry is None or old not in entry.msgstr:
                continue
            entry.msgstr = entry.msgstr.replace(old, new)
            changed += 1
            print(f"{lang}: [{ctx}] {msgid}: «{old}» → «{new}»")
        if changed:
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: {changed} dəyişiklik")


if __name__ == "__main__":
    main()
