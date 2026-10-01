#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-01 EXAMQA (test imtahanı axınının analizi) düzəlişləri.

Əlavə olunan mətnlər:
  * `exams.view.access.message` — nəzarət kilidi altında cavab yazısı rədd edilir
    (`apps/exams/views/student/attempts.py::_supervision_locked_response`);
  * `exams.view.student.result.message` — «nəticə müəllim tərəfindən gizlədilib»
    (`apps/exams/views/student/results.py` — əvvəl tərcüməsiz sabit mətn idi).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_examqa_2026_10_01.py
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
    "exams.view.access.message": {
        "İmtahanınız nəzarətçi tərəfindən dayandırılıb — kilid açılana qədər cavablar qəbul edilmir.": _t(
            "İmtahanınız nəzarətçi tərəfindən dayandırılıb — kilid açılana qədər cavablar qəbul edilmir.",
            "Your exam has been paused by the invigilator — answers are not accepted until it is unlocked.",
            "Ваш экзамен приостановлен наблюдателем — ответы не принимаются, пока блокировка не снята.",
            "Sınavınız gözetmen tarafından durduruldu — kilit açılana kadar cevaplar kabul edilmez.",
        ),
    },
    "exams.view.student.result.message": {
        "Bu imtahanın nəticəsi müəllim tərəfindən tələbələrdən gizlədilib.": _t(
            "Bu imtahanın nəticəsi müəllim tərəfindən tələbələrdən gizlədilib.",
            "The result of this exam has been hidden from students by the teacher.",
            "Результат этого экзамена скрыт преподавателем от студентов.",
            "Bu sınavın sonucu öğretmen tarafından öğrencilerden gizlenmiştir.",
        ),
    },
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
