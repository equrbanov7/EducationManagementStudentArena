#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: kabinet sol menyusunun redizaynı.

Tələbə/müəllimin düz menyusu (bölmə etiketləri «Tapşırıq və imtahanlar»,
«Ünsiyyət»), düzümə görə sidebar başlığı («Tələbə kabineti» / «Müəllim
kabineti» / «Şəxsi kabinet») və `<nav>` landmark-ının adı. Qalan etiketlər
(«Təhsil», «Tədris işi», «Sillabus və sual», «İmtahan və qiymətləndirmə»,
«Profil», hesab bloku) MÖVCUD msgid-lərdir — kataloqa yenisi yazılmır.

Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_sidebar_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

STRINGS = {
    # Sidebar başlığı — düzümə görə (templates/accounts/profile/_sidebar.html).
    ("profile.sidebar", "Tələbə kabineti"): ("Student portal", "Кабинет студента", "Öğrenci paneli"),
    ("profile.sidebar", "Müəllim kabineti"): ("Teacher portal", "Кабинет преподавателя", "Öğretmen paneli"),
    ("profile.sidebar", "Şəxsi kabinet"): ("My portal", "Личный кабинет", "Kişisel panel"),
    # `<nav aria-label>` — ekran oxuyucu landmark adı.
    ("profile.sidebar", "Kabinet menyusu"): ("Portal menu", "Меню кабинета", "Panel menüsü"),
    # Düz menyunun bölmə etiketləri (sidebar/compact/_student.html, _teacher.html).
    ("profile.sidebar", "Tapşırıq və imtahanlar"): ("Tasks & exams", "Задания и экзамены", "Görevler ve sınavlar"),
    ("profile.sidebar", "Ünsiyyət"): ("Communication", "Общение", "İletişim"),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
