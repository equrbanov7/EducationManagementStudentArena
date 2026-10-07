#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-07 təhlükəsizlik auditi (onlayn imtahan bütövlüyü).

Əlavə olunan mətnlər:
  * `ai_assistant.blocked` — açıq imtahan cəhdi zamanı AI köməkçi rədd cavabı
    (`apps/ai_assistant/views.py::chat_view`).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_secaudit_2026_10_07.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    "ai_assistant.blocked": {
        "İmtahan gedərkən AI köməkçi əlçatan deyil. İmtahanı bitirdikdən sonra yenidən yazın.": _t(
            "İmtahan gedərkən AI köməkçi əlçatan deyil. İmtahanı bitirdikdən sonra yenidən yazın.",
            "The AI assistant is unavailable while you are taking an exam. Please write again after you finish it.",
            "AI-ассистент недоступен во время экзамена. Напишите снова после его завершения.",
            "Sınav sırasında yapay zekâ asistanı kullanılamaz. Sınavı bitirdikten sonra tekrar yazın.",
        ),
    },
}


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
            if stale and entry.msgstr != want:
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
