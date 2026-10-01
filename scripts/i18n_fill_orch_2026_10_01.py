#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-01 orkestrator düzəlişləri (dalğa MON/PROC/EXAMQA/HALLS sonrası).

Əlavə olunan mətnlər:
  * `exams.template.teacher_exam_detail`: «Deaktiv et» təsdiqi (EXAMQA R8 — canlı imtahanda bir klik
    bütün tələbələrin yazısını bloklayırdı).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_orch_2026_10_01.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

TED = "exams.template.teacher_exam_detail"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_DEACTIVATE = (
    "Deactivating stops the exam for everyone: students who are taking it right now will not be able to save "
    "or submit answers. Continue?"
)

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    TED: {
        _DEACTIVATE: _t(
            "Deaktiv etsəniz, imtahan hamı üçün dayanır: hazırda imtahan verən tələbələr cavablarını saxlaya və "
            "təhvil verə bilməyəcək. Davam edilsin?",
            _DEACTIVATE,
            "Деактивация останавливает экзамен для всех: студенты, которые сейчас его сдают, не смогут сохранить "
            "или отправить ответы. Продолжить?",
            "Devre dışı bırakmak sınavı herkes için durdurur: şu anda sınava giren öğrenciler cevaplarını "
            "kaydedemez ve teslim edemez. Devam edilsin mi?",
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
