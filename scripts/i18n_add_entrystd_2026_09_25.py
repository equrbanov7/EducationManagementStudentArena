#!/usr/bin/env python3
"""2026/2027 giriş balı standartının ekran mətnləri; idempotent kataloq yeniləməsi."""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

STRINGS = {
    ("registrar.journal", "Aktivlik"): ("Activity", "Активность", "Etkinlik"),
    ("registrar.journal", "Orta bal"): ("Average score", "Средний балл", "Ortalama puan"),
    ("registrar.journal", "Seminar və laboratoriya ballarının ədədi ortası; balsız dərslər sayılmır."): (
        "Arithmetic mean of seminar and lab scores; unscored lessons are excluded.",
        "Среднее арифметическое оценок за семинары и лабораторные; занятия без оценки не учитываются.",
        "Seminer ve laboratuvar puanlarının aritmetik ortalaması; puansız dersler sayılmaz.",
    ),
    (
        "registrar.journal",
        "Giriş balı = davamiyyət + aktivlik + Midterm + sərbəst iş; tam ədədə yuvarlaqlaşdırılır (tavan",
    ): (
        "Entry score = attendance + activity + Midterm + independent work; rounded to a whole number (cap",
        "Входной балл = посещаемость + активность + Midterm + самостоятельная работа; округляется до целого (максимум",
        "Giriş puanı = devam + etkinlik + Midterm + bağımsız çalışma; tam sayıya yuvarlanır (üst sınır",
    ),
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
