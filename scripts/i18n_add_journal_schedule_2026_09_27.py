#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-27: jurnal siyahısı dərs cədvəlinə görə sıralanır («İndi / Bu gün /
Sabah» nişanı) + «Yeni dərs» modalında otaq yaddaşı (eyni növ + gün → son otaq) ipucu +
struktur ekranında vahidin əvvəlki adı / yeri (struktur planı).
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_journal_schedule_2026_09_27.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

_S = "registrar.journal_list_schedule"
_J = "registrar.journal"

STRINGS = {
    (_S, "Bazar ertəsi"): ("Monday", "Понедельник", "Pazartesi"),
    (_S, "Çərşənbə axşamı"): ("Tuesday", "Вторник", "Salı"),
    (_S, "Çərşənbə"): ("Wednesday", "Среда", "Çarşamba"),
    (_S, "Cümə axşamı"): ("Thursday", "Четверг", "Perşembe"),
    (_S, "Cümə"): ("Friday", "Пятница", "Cuma"),
    (_S, "Şənbə"): ("Saturday", "Суббота", "Cumartesi"),
    (_S, "Bazar"): ("Sunday", "Воскресенье", "Pazar"),
    (_S, "İndi"): ("Now", "Сейчас", "Şimdi"),
    (_S, "Bu gün"): ("Today", "Сегодня", "Bugün"),
    (_S, "Sabah"): ("Tomorrow", "Завтра", "Yarın"),
    (_J, "Dərs cədvəlinə görə növbəti dərs"): (
        "Next class according to the timetable",
        "Следующее занятие по расписанию",
        "Ders programına göre sıradaki ders",
    ),
    (
        _J,
        "Korpus və otaq bu qrupun eyni gün və tipdəki əvvəlki dərsindən götürülüb — dəyişə bilərsiniz.",
    ): (
        "Building and room were taken from this group's previous class of the same day and type — you can change them.",
        "Корпус и аудитория взяты из предыдущего занятия этой группы в тот же день и того же типа — их можно изменить.",
        "Bina ve derslik bu grubun aynı gün ve türdeki önceki dersinden alındı — değiştirebilirsiniz.",
    ),
    ("accounts.structure_tree", "«%(name)s» %(date)s tarixində «%(target)s» ilə birləşdirilib."): (
        "«%(name)s» was merged into «%(target)s» on %(date)s.",
        "«%(name)s» объединена с «%(target)s» %(date)s.",
        "«%(name)s» %(date)s tarihinde «%(target)s» ile birleştirildi.",
    ),
    ("accounts.structure_tree", "%(date)s tarixinədək: «%(name)s» — «%(parent)s» tərkibində."): (
        "Until %(date)s: «%(name)s» — part of «%(parent)s».",
        "До %(date)s: «%(name)s» — в составе «%(parent)s».",
        "%(date)s tarihine kadar: «%(name)s» — «%(parent)s» bünyesinde.",
    ),
    ("accounts.structure_tree", "%(date)s tarixinədək adı: «%(name)s»."): (
        "Name until %(date)s: «%(name)s».",
        "Название до %(date)s: «%(name)s».",
        "%(date)s tarihine kadar adı: «%(name)s».",
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
