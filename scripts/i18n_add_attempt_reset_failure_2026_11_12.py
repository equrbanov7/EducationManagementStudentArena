#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-12: «Nəticəni sil» — gözlənilməz xəta artıq 500 deyil, mesajdır.

Beş kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_attempt_reset_failure_2026_11_12.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")

_R = "exams.attempt_reset"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_R, "gözlənilməz texniki xəta — cəhd dəyişmədi, xəta qeydə alındı; RİM-ə bildirin"): (
        "unexpected technical error — the attempt was not changed, the error was logged; please inform the RIM",
        "непредвиденная техническая ошибка — попытка не изменена, ошибка записана; сообщите в RİM",
        "beklenmeyen teknik hata — deneme değişmedi, hata kaydedildi; RİM'e bildirin",
        "unerwarteter technischer Fehler — der Versuch wurde nicht geändert, der Fehler wurde protokolliert; "
        "bitte das RİM informieren",
    ),
    (_R, "Sıfırlanmayan cəhdlər: %(ids)s."): (
        "Attempts not reset: %(ids)s.",
        "Не сброшенные попытки: %(ids)s.",
        "Sıfırlanmayan denemeler: %(ids)s.",
        "Nicht zurückgesetzte Versuche: %(ids)s.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            entry = polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr)
            if "%(" in msgid:
                entry.flags.append("python-format")
            po.append(entry)
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
