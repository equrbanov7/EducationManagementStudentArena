#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: cədvəl slotunun REAL müəllimi (bölünmüş tədris).

Cədvəl redaktorunun «Dərsi aparan müəllim» seçicisi (default «Jurnal sahibi»), sahibin
seçicisinin yeni etiketi, serverin seçim yoxlaması (registrar.schedule_editor) və toplu
dərcin müəllim üzvlüyü yoxlaması (registrar.schedule_publish).
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_slotinst_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

_M = "accounts.schedule_manage"

STRINGS = {
    (_M, "Müəllim (jurnal sahibi)"): (
        "Teacher (journal owner)",
        "Преподаватель (владелец журнала)",
        "Öğretmen (yoklama defteri sahibi)",
    ),
    (_M, "Dərsi aparan müəllim"): (
        "Teacher conducting the class",
        "Преподаватель, ведущий занятие",
        "Dersi yürüten öğretmen",
    ),
    (_M, "Jurnal sahibi"): ("Journal owner", "Владелец журнала", "Yoklama defteri sahibi"),
    (
        _M,
        "Seminarı və ya laboratoriyanı jurnal sahibindən başqa müəllim aparırsa seçin — dərs onun cədvəlinə düşür "
        "və toqquşma onun üçün yoxlanır. Siyahı fənnin dərs yükü bölgüsündən və jurnalında dərs aparmış "
        "müəllimlərdən gəlir.",
    ): (
        "Choose this when a seminar or lab is taught by someone other than the journal owner — the class then "
        "appears in that teacher's timetable and clashes are checked for them. The list comes from the course's "
        "teaching-load distribution and the teachers who have already taught in its journal.",
        "Выберите, если семинар или лабораторную ведёт не владелец журнала — занятие попадёт в расписание этого "
        "преподавателя, и конфликты проверяются для него. Список берётся из распределения учебной нагрузки по "
        "предмету и преподавателей, уже проводивших занятия в журнале.",
        "Semineri veya laboratuvarı yoklama defteri sahibinden başka bir öğretmen yürütüyorsa seçin — ders o "
        "öğretmenin programına düşer ve çakışmalar onun için kontrol edilir. Liste dersin yük dağılımından ve "
        "yoklama defterinde ders yürütmüş öğretmenlerden gelir.",
    ),
    (
        "registrar.schedule_editor",
        "Bu müəllim bu fənnin dərsini apara bilməz — yalnız jurnal sahibi, fənnin dərs yükü bölgüsündəki "
        "və ya jurnalında dərs aparmış aktiv müəllim seçilə bilər.",
    ): (
        "This teacher cannot teach this course — only the journal owner or an active teacher from the course's "
        "teaching-load distribution or its journal can be selected.",
        "Этот преподаватель не может вести этот предмет — можно выбрать только владельца журнала или активного "
        "преподавателя из распределения нагрузки по предмету либо из его журнала.",
        "Bu öğretmen bu dersi yürütemez — yalnızca yoklama defteri sahibi ya da dersin yük dağılımındaki veya "
        "yoklama defterinde ders yürütmüş aktif bir öğretmen seçilebilir.",
    ),
    (
        "registrar.schedule_publish",
        "Qaralamadakı bəzi müəllimlərin bu təşkilatda aktiv müəllim üzvlüyü yoxdur — "
        "dərs yükünü yoxlayıb qaralamanı yenidən yaradın.",
    ): (
        "Some teachers in the draft have no active teaching membership in this organization — check the teaching "
        "load and generate the draft again.",
        "У некоторых преподавателей в черновике нет активного преподавательского членства в этой организации — "
        "проверьте нагрузку и создайте черновик заново.",
        "Taslaktaki bazı öğretmenlerin bu kurumda aktif öğretmen üyeliği yok — ders yükünü kontrol edip taslağı "
        "yeniden oluşturun.",
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
