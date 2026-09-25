#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: heyət sidebar-ının redizaynı + sorğu bəndləri.

«Menyuda axtar» süzgəci (sahə adı + «Heç nə tapılmadı»), müəllim qiymətləndirmə
sorğusunun sidebar bəndləri (tələbə: «Anonim sorğu»; heyət: «Sorğu nəticələri»,
«Sorğu kampaniyaları») və yeni «Keyfiyyətə nəzarət» qrupu. Qrup başlıqlarının
qalanı MÖVCUD msgid-lərdir — kataloqa yenisi yazılmır.

Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_sidebar_staff_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

STRINGS = {
    # «Menyuda axtar» süzgəci (templates/accounts/profile/_sidebar.html).
    ("profile.sidebar", "Menyuda axtar"): ("Search menu", "Поиск по меню", "Menüde ara"),
    ("profile.sidebar", "Heç nə tapılmadı"): ("Nothing found", "Ничего не найдено", "Hiçbir şey bulunamadı"),
    # Müəllim qiymətləndirmə sorğusu — sidebar bəndləri və heyət qrupu.
    ("profile.sidebar", "Anonim sorğu"): ("Anonymous survey", "Анонимный опрос", "Anonim anket"),
    ("profile.sidebar", "Sorğu nəticələri"): ("Survey results", "Результаты опроса", "Anket sonuçları"),
    ("profile.sidebar", "Sorğu kampaniyaları"): ("Survey campaigns", "Кампании опросов", "Anket kampanyaları"),
    ("profile.sidebar", "Keyfiyyətə nəzarət"): ("Quality assurance", "Контроль качества", "Kalite güvencesi"),
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
