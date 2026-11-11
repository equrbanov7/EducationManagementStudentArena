#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-11: patokda eyni saatlı dərs (cədvəl toqquşmasının izahı + jurnal mesajı).

Beş kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_patok_same_slot_2026_11_11.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")

_C = "registrar.schedule_conflicts"
_L = "registrar.journal_lessons"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_C, "Patok (birgə dərs) yalnız eyni dərs növü üçündür: orada %(kind)s keçirilir."): (
        "A joint (stream) lesson is only possible for the same lesson type: a %(kind)s is held there.",
        "Поток (совместное занятие) возможен только для одного вида занятия: там проходит %(kind)s.",
        "Ortak ders (patok) yalnızca aynı ders türü için mümkündür: orada %(kind)s yapılıyor.",
        "Ein gemeinsamer Unterricht (Strom) ist nur für dieselbe Unterrichtsart möglich: dort findet %(kind)s statt.",
    ),
    (_C, "Bu, eyni fənnin patokudursa auditoriya eyni olmalıdır (%(room)s) və ya auditoriyanı boş saxlayın."): (
        "If this is a joint (stream) lesson of the same subject, the room must be the same (%(room)s), "
        "or leave the room empty.",
        "Если это поток по тому же предмету, аудитория должна совпадать (%(room)s) или оставьте аудиторию пустой.",
        "Bu aynı dersin ortak dersiyse (patok) derslik aynı olmalıdır (%(room)s) veya dersliği boş bırakın.",
        "Wenn dies ein gemeinsamer Unterricht desselben Fachs ist, muss der Raum gleich sein (%(room)s) "
        "oder lassen Sie den Raum leer.",
    ),
    (
        _L,
        "Bu jurnalda %(date)s, saat %(time)s üçün dərs artıq yazılıb. Patok dərsində hər qrupun dərsi öz "
        "jurnalına yazılır; alt qrupların (Lab / seminar) dərsi üçün alt qrupu seçin.",
    ): (
        "A lesson for %(date)s at %(time)s is already recorded in this journal. In a joint (stream) lesson each "
        "group's lesson is recorded in its own journal; for subgroup (Lab / seminar) lessons choose the subgroup.",
        "В этом журнале занятие на %(date)s, %(time)s уже записано. В потоке занятие каждой группы записывается "
        "в её собственный журнал; для занятий подгрупп (лаб. / семинар) выберите подгруппу.",
        "Bu defterde %(date)s, saat %(time)s için ders zaten kayıtlı. Ortak derste (patok) her grubun dersi kendi "
        "defterine yazılır; alt grup (Lab / seminer) dersleri için alt grubu seçin.",
        "In diesem Journal ist für %(date)s um %(time)s bereits eine Stunde eingetragen. Beim gemeinsamen "
        "Unterricht wird die Stunde jeder Gruppe in ihr eigenes Journal eingetragen; für Untergruppen "
        "(Labor / Seminar) wählen Sie die Untergruppe.",
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
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
