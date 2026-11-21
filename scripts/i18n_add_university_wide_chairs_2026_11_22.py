#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-22: Xarici dillər kafedrası — tələbə seçimi bütün universitet üzrə (Sistem tənzimləmələri).

Sahib (RİM rəhbəri): «Xarici dil kafedrasında tyutorlar və dekanlıq işçiləri qrup yaradanda və ya alt qrupa tələbə
əlavə edəndə bütün universitetdən qrupları götürürlər». ``django`` kataloquna (``core.runtime_settings``) beş dildə
əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_university_wide_chairs_2026_11_22.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_RS = "core.runtime_settings"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _RS, "Xarici dillər kafedrası: tələbələr bütün universitetdən"): (
        "Foreign languages chair: students from the whole university",
        "Кафедра иностранных языков: студенты со всего университета",
        "Yabancı diller bölümü: tüm üniversiteden öğrenciler",
        "Lehrstuhl für Fremdsprachen: Studierende der ganzen Universität",
    ),
    (
        "django",
        _RS,
        "Yandırılıbsa Xarici dillər kafedrasının qrupunda və ya səviyyə qrupunda tyutor və dekanlıq işçiləri tələbə "
        "əlavə edəndə bütün universitetin qruplarını və tələbələrini görür. Kim qrup yarada və tələbə əlavə edə "
        "bilər — dəyişmir. Söndürüləndə əvvəlki qayda: yalnız öz məktəbinin (fakültəsinin) tələbələri.",
    ): (
        "When on, tutors and dean's office staff adding students to a group or level group of the Foreign languages "
        "chair see the groups and students of the whole university. Who may create groups and add students does not "
        "change. When off, the previous rule applies: only students of their own school (faculty).",
        "Если включено, тьюторы и сотрудники деканата, добавляя студентов в группу или группу уровня кафедры "
        "иностранных языков, видят группы и студентов всего университета. Кто может создавать группы и добавлять "
        "студентов — не меняется. Если выключено, действует прежнее правило: только студенты своей школы "
        "(факультета).",
        "Açıksa Yabancı diller bölümünün grubuna veya seviye grubuna öğrenci ekleyen danışmanlar ve dekanlık "
        "çalışanları tüm üniversitenin gruplarını ve öğrencilerini görür. Kimin grup oluşturup öğrenci "
        "ekleyebileceği değişmez. Kapalıysa önceki kural geçerlidir: yalnızca kendi okulunun (fakültesinin) "
        "öğrencileri.",
        "Wenn aktiviert, sehen Tutoren und Mitarbeitende des Dekanats beim Hinzufügen von Studierenden zu einer Gruppe "
        "oder Niveaugruppe des Lehrstuhls für Fremdsprachen die Gruppen und Studierenden der ganzen Universität. Wer "
        "Gruppen anlegen und Studierende hinzufügen darf, ändert sich nicht. Wenn deaktiviert, gilt die bisherige "
        "Regel: nur Studierende der eigenen Schule (Fakultät).",
    ),
}


def main():
    for domain in ("django",):
        for lang in LOCALES:
            path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            po = polib.pofile(path)
            existing = {(e.msgctxt, e.msgid) for e in po}
            added = 0
            for (dom, ctx, msgid), (en, ru, tr, de) in STRINGS.items():
                if dom != domain or (ctx, msgid) in existing:
                    continue
                msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
                entry = polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr)
                if "%(" in msgid:
                    entry.flags.append("python-format")
                po.append(entry)
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()
