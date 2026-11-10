#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-10: «Fənn qovluqları» kartı (yaradan, yenilənmə) və avtomatik qrup təyinatı mətnləri
(``apps/subject_folder/services/auto_assign.py``). Beş kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_subject_folder_auto_groups_2026_11_10.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")

_U = "subject_folder.ui"

STRINGS = {
    (_U, "Yaradan"): ("Created by", "Создатель", "Oluşturan", "Erstellt von"),
    (_U, "Müəllim"): ("Teacher", "Преподаватель", "Öğretmen", "Lehrkraft"),
    (_U, "Yeniləndi"): ("Updated", "Обновлено", "Güncellendi", "Aktualisiert"),
    (_U, "avtomatik"): ("automatic", "автоматически", "otomatik", "automatisch"),
    (
        _U,
        "Fənni və semestri seçin. Qovluq həmin semestrdə bu fəndən dərs dediyiniz bütün qruplara avtomatik təyin olunur.",
    ): (
        "Choose the subject and semester. The folder is automatically assigned to every group you teach this subject "
        "to in that semester.",
        "Выберите предмет и семестр. Папка автоматически назначается всем группам, у которых вы ведёте этот предмет в "
        "этом семестре.",
        "Dersi ve dönemi seçin. Klasör, o dönemde bu dersi verdiğiniz tüm gruplara otomatik olarak atanır.",
        "Wählen Sie Fach und Semester. Der Ordner wird automatisch allen Gruppen zugewiesen, die Sie in diesem Semester "
        "in diesem Fach unterrichten.",
    ),
    (
        _U,
        "Bu fənn və semestrdə dərs dediyiniz qruplar avtomatik əlavə olunur — tələbələr yalnız təyin olunmuş qovluğu "
        "görür. Sərbəst iş balı yalnız bir qovluqdan qəbul edilir.",
    ): (
        "Groups you teach in this subject and semester are added automatically — students only see folders assigned "
        "to them. Independent-work points are accepted from one folder only.",
        "Группы, у которых вы ведёте этот предмет в этом семестре, добавляются автоматически — студенты видят только "
        "назначенную им папку. Баллы за самостоятельную работу принимаются только из одной папки.",
        "Bu ders ve dönemde ders verdiğiniz gruplar otomatik olarak eklenir — öğrenciler yalnızca kendilerine atanan "
        "klasörü görür. Bağımsız çalışma puanı yalnızca bir klasörden kabul edilir.",
        "Gruppen, die Sie in diesem Fach und Semester unterrichten, werden automatisch hinzugefügt — Studierende sehen "
        "nur den ihnen zugewiesenen Ordner. Punkte für Selbststudium werden nur aus einem Ordner übernommen.",
    ),
    (
        _U,
        "Bu fənn və semestrdə dərs dediyiniz qruplar avtomatik əlavə olunur — tələbələr yalnız təyin olunmuş qovluğu "
        "görür.",
    ): (
        "Groups you teach in this subject and semester are added automatically — students only see folders assigned "
        "to them.",
        "Группы, у которых вы ведёте этот предмет в этом семестре, добавляются автоматически — студенты видят только "
        "назначенную им папку.",
        "Bu ders ve dönemde ders verdiğiniz gruplar otomatik olarak eklenir — öğrenciler yalnızca kendilerine atanan "
        "klasörü görür.",
        "Gruppen, die Sie in diesem Fach und Semester unterrichten, werden automatisch hinzugefügt — Studierende sehen "
        "nur den ihnen zugewiesenen Ordner.",
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
