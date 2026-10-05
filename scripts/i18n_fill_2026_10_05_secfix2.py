#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-05 (təhlükəsizlik auditi, 2-ci dalğa).

Əlavə olunan mətnlər:
  * `surveys.results`: sərbəst mətn (şərh/təklif) daraldıcı filtr altında göstərilmir —
    müəllim kartı və «Ümumi» tabının izah mətnləri;
  * `surveys.campaigns`: kampaniyanın k-həddi nəticə dərc olunandan sonra dəyişmir.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_05_secfix2.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


SR = "surveys.results"
SC = "surveys.campaigns"

_RESULTS = [
    _t(
        "Anonimlik üçün şərhlər yalnız fənn, qrup, ixtisas və kurs filtrləri seçilmədikdə göstərilir.",
        "For anonymity, comments are shown only when no subject, group, programme or year filter is selected.",
        "Для анонимности комментарии показываются только без фильтров по предмету, группе, специальности и курсу.",
        "Anonimlik için yorumlar yalnızca ders, grup, program ve sınıf filtresi seçilmediğinde gösterilir.",
    ),
    _t(
        "Anonimlik üçün təkliflər yalnız fənn, qrup, ixtisas və kurs filtrləri seçilmədikdə göstərilir.",
        "For anonymity, suggestions are shown only when no subject, group, programme or year filter is selected.",
        "Для анонимности предложения показываются только без фильтров по предмету, группе, специальности и курсу.",
        "Anonimlik için öneriler yalnızca ders, grup, program ve sınıf filtresi seçilmediğinde gösterilir.",
    ),
]

_CAMPAIGNS = [
    _t(
        "Nəticələr dərc olunandan sonra k-həddi dəyişmir.",
        "The k threshold cannot change after results are published.",
        "Порог k нельзя менять после публикации результатов.",
        "Sonuçlar yayımlandıktan sonra k eşiği değişmez.",
    ),
]

ENTRIES = {
    SR: {row["az"]: row for row in _RESULTS},
    SC: {row["az"]: row for row in _CAMPAIGNS},
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
