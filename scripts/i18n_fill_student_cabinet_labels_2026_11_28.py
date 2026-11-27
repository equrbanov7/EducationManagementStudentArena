#!/usr/bin/env python3
"""Tələbə kabineti (sahib 2026-11-28): «Aktivlik» əvəzinə Seminar / Laboratoriya, «Dərs materiallarım» adı və
«Fənlərim» kartından «Dərs materialları» keçidi — yalnız yeni msgid-ləri əlavə edir."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")

ENTRIES = {
    "django": {
        "registrar.activity_label": {
            "Seminar": {"en": "Seminars", "ru": "Семинар", "tr": "Seminer", "de": "Seminare"},
            "Laboratoriya": {"en": "Laboratory", "ru": "Лаборатория", "tr": "Laboratuvar", "de": "Labor"},
            "Seminar / Laboratoriya": {
                "en": "Seminar / Laboratory",
                "ru": "Семинар / Лаборатория",
                "tr": "Seminer / Laboratuvar",
                "de": "Seminar / Labor",
            },
            "Praktiki məşğələ": {
                "en": "Practical class",
                "ru": "Практическое занятие",
                "tr": "Uygulama dersi",
                "de": "Praktische Übung",
            },
        },
        "profile.sidebar": {
            "Dərs materiallarım": {
                "en": "My course materials",
                "ru": "Мои учебные материалы",
                "tr": "Ders materyallerim",
                "de": "Meine Lehrmaterialien",
            },
        },
        "subject_folder.ui": {
            "Dərs materiallarım": {
                "en": "My course materials",
                "ru": "Мои учебные материалы",
                "tr": "Ders materyallerim",
                "de": "Meine Lehrmaterialien",
            },
        },
        "profile.subjects": {
            "Dərs materialları": {
                "en": "Course materials",
                "ru": "Учебные материалы",
                "tr": "Ders materyalleri",
                "de": "Lehrmaterialien",
            },
            "Giriş balı = davamiyyət + seminar / laboratoriya + midterm + sərbəst iş (imtahana qədər toplanan hissə); yekun bal = giriş balı + yekun imtahan.": {
                "en": "Entry score = attendance + seminar / laboratory + midterm + independent work (the part earned before the exam); final score = entry score + final exam.",
                "ru": "Входной балл = посещаемость + семинар / лаборатория + мидтерм + самостоятельная работа (часть, набранная до экзамена); итоговый балл = входной балл + итоговый экзамен.",
                "tr": "Giriş puanı = devam + seminer / laboratuvar + ara sınav + bireysel çalışma (sınava kadar toplanan kısım); final puanı = giriş puanı + final sınavı.",
                "de": "Eingangspunktzahl = Anwesenheit + Seminar / Labor + Midterm + Selbststudium (vor der Prüfung erreichter Teil); Endnote = Eingangspunktzahl + Abschlussprüfung.",
            },
            "Giriş balı = davamiyyət + seminar / laboratoriya + midterm (imtahana qədər toplanan hissə); yekun bal = giriş balı + yekun imtahan. Fəndə həm seminar, həm laboratoriya varsa hər biri 5 bal sayılır (5 + 5).": {
                "en": "Entry score = attendance + seminar / laboratory + midterm (the part earned before the exam); final score = entry score + final exam. If a subject has both seminars and laboratories, each counts for 5 points (5 + 5).",
                "ru": "Входной балл = посещаемость + семинар / лаборатория + мидтерм (часть, набранная до экзамена); итоговый балл = входной балл + итоговый экзамен. Если в предмете есть и семинар, и лаборатория, каждый даёт 5 баллов (5 + 5).",
                "tr": "Giriş puanı = devam + seminer / laboratuvar + ara sınav (sınava kadar toplanan kısım); final puanı = giriş puanı + final sınavı. Derste hem seminer hem laboratuvar varsa her biri 5 puan sayılır (5 + 5).",
                "de": "Eingangspunktzahl = Anwesenheit + Seminar / Labor + Midterm (vor der Prüfung erreichter Teil); Endnote = Eingangspunktzahl + Abschlussprüfung. Hat ein Fach Seminar und Labor, zählt jedes 5 Punkte (5 + 5).",
            },
        },
    },
}


def quote(text):
    return json.dumps(text, ensure_ascii=False)


def fill():
    counts = {}
    for domain, contexts in ENTRIES.items():
        for lang in LANGS:
            path = BASE / "locale" / lang / "LC_MESSAGES" / f"{domain}.po"
            existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
            blocks = []
            for context, messages in contexts.items():
                for msgid, translations in messages.items():
                    if (context, msgid) in existing:
                        continue
                    value = msgid if lang == "az" else translations[lang]
                    lines = ["msgctxt " + quote(context)] if context else []
                    lines += ["msgid " + quote(msgid), "msgstr " + quote(value)]
                    blocks.append("\n".join(lines) + "\n")
            if blocks:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(blocks))
            counts[f"{domain}/{lang}"] = len(blocks)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    fill()
