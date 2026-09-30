#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-01 AI çatbot: bütün sistem üzrə gündəlik limit mesajı (sahib).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_ai_2026_10_01.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

MSG = "AI assistent bu gün üçün ümumi limitə çatıb. Sabah yenidən cəhd edin."

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    "ai_assistant.limit_exceeded": {
        MSG: {
            "az": MSG,
            "en": "The AI assistant has reached today's overall limit. Please try again tomorrow.",
            "ru": "AI-ассистент исчерпал общий лимит на сегодня. Попробуйте завтра.",
            "tr": "AI asistan bugünkü genel sınıra ulaştı. Lütfen yarın tekrar deneyin.",
        }
    }
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
