#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: «plan → qruplar» (plan2grp). «Semestr açılışı»
ekranının «Necə işləyir» kartının 1-ci addımı yeni qaydanı izah edir: açılış
yalnız həmin semestri oxuyan (kursu uyğun) qruplara, yalnız məcburi fənlərdən
yaranır, qrupun tələbələri dərhal qeydiyyata düşür, seçmə fənlər qrup seçimi ilə.
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_plan2grp_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

STRINGS = {
    (
        "accounts.semester",
        "Yuxarıdakı süzgəcdən semestri seçin. «Plandan açılış yarat» həmin semestri oxuyan (kursu uyğun) qruplar "
        "üçün təsdiqlənmiş tədris planının məcburi fənlərindən açılış yaradır və qrupun aktiv tələbələrini dərhal "
        "qeydiyyata alır; seçmə fənlər qrupun seçimi ilə açılır. Mövcud sətir təkrarlanmır, heç nə silinmir. "
        "«Plan yoxdur» ixtisaslar üçün sətir yaranmır — əvvəlcə «Tədris planı» bölməsində planı təsdiqləyin.",
    ): (
        "Pick the semester in the filter above. “Create offerings from plan” creates offerings from the mandatory "
        "subjects of the approved curriculum for the groups that study that semester (matching course year) and "
        "enrols the groups' active students right away; elective subjects open when the group makes its choice. "
        "Existing rows are not duplicated and nothing is deleted. No rows are created for “no plan” specialties — "
        "approve the plan in “Curriculum” first.",
        "Выберите семестр в фильтре выше. «Создать курсы из плана» создаёт курсы по обязательным предметам "
        "утверждённого учебного плана для групп, которые учатся в этом семестре (соответствующий курс), и сразу "
        "записывает активных студентов группы; элективные предметы открываются после выбора группы. Существующие "
        "строки не дублируются, ничего не удаляется. Для специальностей без плана строки не создаются — сначала "
        "утвердите план в разделе «Учебный план».",
        "Yukarıdaki filtreden dönemi seçin. «Plandan açılış oluştur», o dönemi okuyan (sınıfı uygun) gruplar için "
        "onaylanmış öğretim planının zorunlu derslerinden açılış oluşturur ve grubun aktif öğrencilerini hemen "
        "kaydeder; seçmeli dersler grubun seçimiyle açılır. Mevcut satır tekrarlanmaz, hiçbir şey silinmez. «Plan "
        "yok» olan uzmanlıklar için satır oluşturulmaz — önce «Öğretim planı» bölümünde planı onaylayın.",
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
