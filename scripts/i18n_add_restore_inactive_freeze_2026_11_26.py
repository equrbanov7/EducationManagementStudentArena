#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-26: «Tələbəni bərpa et» 08.11 aktivlik dondurulmasını bərpa edir.

``django`` kataloquna beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_restore_inactive_freeze_2026_11_26.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_R = "registrar.roster_restore"
_J = "registrar.journal_removal"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_R, "Sistem (08.11 aktivlik yoxlaması)"): (
        "System (08.11 activity check)",
        "Система (проверка активности 08.11)",
        "Sistem (08.11 etkinlik kontrolü)",
        "System (Aktivitätsprüfung 08.11)",
    ),
    (
        _R,
        "Heç bir fəndə i/e, bal və midterm olmadığı üçün dondurulub. «Bərpa et» hesabı açır və tələbəni dondurulduğu "
        "bütün fənlərin jurnallarına qaytarır.",
    ): (
        "Frozen because there was no attendance, score or midterm in any subject. “Restore” unblocks the account and "
        "returns the student to the journals of all subjects that were frozen.",
        "Заморожен, так как ни по одному предмету не было посещаемости, баллов и мидтерма. «Восстановить» "
        "разблокирует аккаунт и вернёт студента в журналы всех замороженных предметов.",
        "Hiçbir derste devam, puan ve ara sınav olmadığı için donduruldu. «Geri yükle» hesabı açar ve öğrenciyi "
        "dondurulduğu tüm derslerin yoklama defterlerine geri döndürür.",
        "Eingefroren, weil in keinem Fach Anwesenheit, Punkte oder Zwischenprüfung vorlagen. „Wiederherstellen“ "
        "entsperrt das Konto und bringt die Person in die Journale aller eingefrorenen Fächer zurück.",
    ),
    (_R, "Tələbə bərpa olunmadı."): (
        "The student was not restored.",
        "Студент не восстановлен.",
        "Öğrenci geri yüklenmedi.",
        "Die Person wurde nicht wiederhergestellt.",
    ),
    (_J, "Aktivlik yoxlaması (dondurulma)"): (
        "Activity check (freeze)",
        "Проверка активности (заморозка)",
        "Etkinlik kontrolü (dondurma)",
        "Aktivitätsprüfung (Einfrieren)",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        if added:
            po.save(path)
            subprocess.run(["msgfmt", "-o", path[:-2] + "mo", path], check=True)
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
