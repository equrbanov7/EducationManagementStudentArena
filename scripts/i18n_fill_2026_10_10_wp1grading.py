#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-10 (WP1): yeni semestr düsturu — midterm 30, sərbəst iş söndürülə bilər, aktivlik 5 + 5.

Əlavə olunan mətnlər:
  * `registrar.journal`: «Yekun» tabının seminar/lab ortası sütunları və düstur cümlələri, giriş balı nişanları,
    midterm şkalası («0–%(max)s» — tavan RİM qaydasından gəlir);
  * `registrar.interim`: «Midterm — aralıq imtahan (0–%(max)s bal)»;
  * `profile.subjects`: «Fənlərim» qiymətləndirmə strukturu zolağı (10 / 10 / 30 / 50).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_10_wp1grading.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


RJ = "registrar.journal"
RI = "registrar.interim"
PS = "profile.subjects"

_JOURNAL = [
    _t("Seminar ortası", "Seminar average", "Средний за семинары", "Seminer ortalaması"),
    _t("Lab ortası", "Lab average", "Средний за лабораторные", "Laboratuvar ortalaması"),
    _t("Bal (5 + 5)", "Score (5 + 5)", "Балл (5 + 5)", "Puan (5 + 5)"),
    _t("lab", "lab", "лаб.", "lab"),
    _t(
        "Fəndə seminar və laboratoriya var: hər növün ədədi ortasının yarısı toplanır (5 + 5); balı olmayan növ 0 sayılır.",
        "The subject has both seminars and labs: half of each type's arithmetic mean is added (5 + 5); a type with no scores counts as 0.",
        "В предмете есть и семинары, и лабораторные: складывается половина среднего арифметического каждого вида (5 + 5); вид без оценок считается 0.",
        "Derste hem seminer hem laboratuvar var: her türün aritmetik ortalamasının yarısı toplanır (5 + 5); puanı olmayan tür 0 sayılır.",
    ),
    _t(
        "Giriş balı = davamiyyət + aktivlik + Midterm; tam ədədə yuvarlaqlaşdırılır (tavan",
        "Entry score = attendance + activity + Midterm; rounded to a whole number (cap",
        "Входной балл = посещаемость + активность + Midterm; округляется до целого (максимум",
        "Giriş puanı = devam + etkinlik + Midterm; tam sayıya yuvarlanır (üst sınır",
    ),
    _t(
        "Aktivlik = seminar ortasının yarısı + laboratoriya ortasının yarısı (5 + 5); balı olmayan növ 0 sayılır.",
        "Activity = half of the seminar average + half of the lab average (5 + 5); a type with no scores counts as 0.",
        "Активность = половина среднего за семинары + половина среднего за лабораторные (5 + 5); вид без оценок считается 0.",
        "Etkinlik = seminer ortalamasının yarısı + laboratuvar ortalamasının yarısı (5 + 5); puanı olmayan tür 0 sayılır.",
    ),
    _t(
        "Midterm — aralıq imtahandır, 0–%(max)s bal. Bal-yazma aralığını İmtahan Mərkəzi təyin edir. Pəncərə açıq "
        "olduqca balı sərbəst yaza/dəyişə bilərsiniz; bağlanandan sonra kilidlənir. Boş buraxılan bal 0 sayılır.",
        "The midterm is the mid-semester exam, 0–%(max)s points. The Exam Centre sets the score-entry interval. While "
        "the window is open you can enter or change scores freely; once it closes they are locked. An empty score "
        "counts as 0.",
        "Мидтерм — промежуточный экзамен, 0–%(max)s баллов. Интервал ввода баллов устанавливает Экзаменационный "
        "центр. Пока окно открыто, баллы можно свободно вводить и менять; после закрытия они блокируются. Пустой "
        "балл считается 0.",
        "Vize ara sınavdır, 0–%(max)s puan. Puan giriş aralığını Sınav Merkezi belirler. Pencere açıkken puanı "
        "serbestçe girebilir/değiştirebilirsiniz; kapandıktan sonra kilitlenir. Boş bırakılan puan 0 sayılır.",
    ),
    _t("şkala 0–%(max)s", "scale 0–%(max)s", "шкала 0–%(max)s", "ölçek 0–%(max)s"),
]

_INTERIM = [
    _t(
        "Midterm — aralıq imtahan (0–%(max)s bal)",
        "Midterm — mid-semester exam (0–%(max)s points)",
        "Мидтерм — промежуточный экзамен (0–%(max)s баллов)",
        "Vize — ara sınav (0–%(max)s puan)",
    ),
]

_SUBJECTS = [
    _t(
        "Aktivlik (seminar / laboratoriya)",
        "Activity (seminar / lab)",
        "Активность (семинар / лабораторная)",
        "Etkinlik (seminer / laboratuvar)",
    ),
    _t("Midterm", "Midterm", "Мидтерм", "Vize"),
    _t(
        "Giriş balı = davamiyyət + aktivlik + midterm + sərbəst iş (imtahana qədər toplanan hissə); yekun bal = "
        "giriş balı + yekun imtahan.",
        "Entry score = attendance + activity + midterm + independent work (the part accumulated before the exam); "
        "final score = entry score + final exam.",
        "Входной балл = посещаемость + активность + мидтерм + самостоятельная работа (часть, набранная до экзамена); "
        "итоговый балл = входной балл + итоговый экзамен.",
        "Giriş puanı = devam + etkinlik + vize + serbest çalışma (sınava kadar toplanan kısım); nihai puan = giriş "
        "puanı + final sınavı.",
    ),
    _t(
        "Giriş balı = davamiyyət + aktivlik + midterm (imtahana qədər toplanan hissə); yekun bal = giriş balı + "
        "yekun imtahan. Fəndə seminar və laboratoriya varsa aktivlik 5 + 5 hesablanır.",
        "Entry score = attendance + activity + midterm (the part accumulated before the exam); final score = entry "
        "score + final exam. If the subject has both seminars and labs, activity is calculated as 5 + 5.",
        "Входной балл = посещаемость + активность + мидтерм (часть, набранная до экзамена); итоговый балл = входной "
        "балл + итоговый экзамен. Если в предмете есть семинары и лабораторные, активность считается как 5 + 5.",
        "Giriş puanı = devam + etkinlik + vize (sınava kadar toplanan kısım); nihai puan = giriş puanı + final "
        "sınavı. Derste seminer ve laboratuvar varsa etkinlik 5 + 5 olarak hesaplanır.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    RJ: {row["az"]: row for row in _JOURNAL},
    RI: {row["az"]: row for row in _INTERIM},
    PS: {row["az"]: row for row in _SUBJECTS},
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
                flags = ["python-format"] if "%(" in msgid else []
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want, flags=flags))
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
