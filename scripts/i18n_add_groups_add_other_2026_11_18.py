#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-18: «Tələbəni qrupa əlavə et» başqa qrupdakı tələbə (əlavə olaraq / məcburi köçür).

Sahib: «axtardıqca bütün tələbələr görünsün; başqa qrupdadırsa göstərin — əlavə olaraq (əcnəbi tələbə 2 qrupda
ola bilər) və ya məcburi keçid». ``django`` kataloquna beş dildə; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_groups_add_other_2026_11_18.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_G = "accounts.groups"
_R = "registrar.group_extra_member"

#: (kontekst, msgid, python-format) → (en, ru, tr, de)
STRINGS = {
    (_G, "%%d əlavə üzv (öz qrupu başqadır)", False): (
        "%%d extra members (home group is different)",
        "%%d доп. участников (основная группа другая)",
        "%%d ek üye (kendi grubu farklı)",
        "%%d zusätzliche Mitglieder (eigene Gruppe ist eine andere)",
    ),
    (_G, "%d tələbə bu qrupa köçürüldü", True): (
        "%d students transferred to this group",
        "%d студентов переведено в эту группу",
        "%d öğrenci bu gruba aktarıldı",
        "%d Studierende in diese Gruppe versetzt",
    ),
    (_G, "%d tələbə qrupa əlavə olundu", True): (
        "%d students added to the group",
        "%d студентов добавлено в группу",
        "%d öğrenci gruba eklendi",
        "%d Studierende zur Gruppe hinzugefügt",
    ),
    (_G, "%d tələbə öz qrupunda qalaraq bu qrupun jurnallarına əlavə olundu", True): (
        "%d students added to this group's journals while staying in their own group",
        "%d студентов добавлено в журналы этой группы, оставаясь в своей группе",
        "%d öğrenci kendi grubunda kalarak bu grubun dersliklerine eklendi",
        "%d Studierende bleiben in ihrer Gruppe und wurden den Journalen dieser Gruppe hinzugefügt",
    ),
    (_G, "Başqa qrupdakı tələbə üçün seçin: əlavə olaraq (öz qrupunda qalır) və ya məcburi köçür.", False): (
        "For a student from another group choose: add as extra (stays in own group) or force transfer.",
        "Для студента из другой группы выберите: добавить дополнительно (остаётся в своей группе) или перевести.",
        "Başka gruptaki öğrenci için seçin: ek olarak (kendi grubunda kalır) veya zorunlu aktar.",
        "Für Studierende einer anderen Gruppe wählen: zusätzlich (bleibt in eigener Gruppe) oder zwangsweise versetzen.",
    ),
    (_G, "Heç bir tələbə əlavə olunmadı.", False): (
        "No student was added.",
        "Ни один студент не добавлен.",
        "Hiçbir öğrenci eklenmedi.",
        "Es wurde niemand hinzugefügt.",
    ),
    (_G, "Məcburi köçür", False): (
        "Force transfer",
        "Перевести принудительно",
        "Zorunlu aktar",
        "Zwangsweise versetzen",
    ),
    (_G, "Qrup reyestrindən məcburi köçürmə: %(old)s → %(new)s", True): (
        "Forced transfer from the group registry: %(old)s → %(new)s",
        "Принудительный перевод из реестра групп: %(old)s → %(new)s",
        "Grup kaydından zorunlu aktarma: %(old)s → %(new)s",
        "Zwangsversetzung aus dem Gruppenregister: %(old)s → %(new)s",
    ),
    (_G, "Qrup reyestrindən əlavə üzv (öz qrupu: %s)", True): (
        "Extra member from the group registry (own group: %s)",
        "Дополнительный участник из реестра групп (своя группа: %s)",
        "Grup kaydından ek üye (kendi grubu: %s)",
        "Zusätzliches Mitglied aus dem Gruppenregister (eigene Gruppe: %s)",
    ),
    (
        _G,
        "Qrupsuz tələbələr birbaşa əlavə olunur. Başqa qrupdakı tələbəni ya əlavə olaraq (öz qrupunda qalır), "
        "ya da məcburi köçürə bilərsiniz — tarixçə silinmir.",
        False,
    ): (
        "Students without a group are added directly. A student from another group can be added as extra "
        "(stays in own group) or force-transferred — history is kept.",
        "Студенты без группы добавляются сразу. Студента из другой группы можно добавить дополнительно "
        "(остаётся в своей группе) или перевести принудительно — история сохраняется.",
        "Grubu olmayan öğrenciler doğrudan eklenir. Başka gruptaki öğrenci ek olarak (kendi grubunda kalır) "
        "eklenebilir veya zorunlu aktarılabilir — geçmiş silinmez.",
        "Studierende ohne Gruppe werden direkt hinzugefügt. Studierende einer anderen Gruppe können zusätzlich "
        "(bleiben in eigener Gruppe) aufgenommen oder zwangsweise versetzt werden — der Verlauf bleibt erhalten.",
    ),
    (_G, "Seçilmiş tələbələr arasında qrupa əlavə edilə bilən (qeydiyyatlı) tələbə yoxdur.", False): (
        "None of the selected students can be added to the group (enrolled).",
        "Среди выбранных нет студентов (зачисленных), которых можно добавить в группу.",
        "Seçilen öğrenciler arasında gruba eklenebilecek (kayıtlı) öğrenci yok.",
        "Unter den Ausgewählten ist niemand (eingeschrieben), der hinzugefügt werden kann.",
    ),
    (_G, "Seçilənlər arasında başqa qrupda olan tələbə var. Nə edilsin?", False): (
        "Some selected students are in another group. What should be done?",
        "Среди выбранных есть студенты из другой группы. Что сделать?",
        "Seçilenler arasında başka grupta olan öğrenci var. Ne yapılsın?",
        "Einige Ausgewählte sind in einer anderen Gruppe. Was soll geschehen?",
    ),
    (_G, "başqa qrupdadır: %s", True): (
        "in another group: %s",
        "в другой группе: %s",
        "başka grupta: %s",
        "in anderer Gruppe: %s",
    ),
    (_G, "Öz qrupunda qalır, bu qrupun cari jurnallarına da əlavə olunur (məs. əcnəbi tələbələr).", False): (
        "Stays in own group and is also added to this group's current journals (e.g. international students).",
        "Остаётся в своей группе и добавляется в текущие журналы этой группы (напр. иностранные студенты).",
        "Kendi grubunda kalır, bu grubun mevcut dersliklerine de eklenir (ör. yabancı öğrenciler).",
        "Bleibt in der eigenen Gruppe und kommt zusätzlich in die aktuellen Journale dieser Gruppe "
        "(z. B. internationale Studierende).",
    ),
    (_G, "Öz qrupundan çıxıb bu qrupa keçir (rəsmi köçürmə, tarixçə qalır).", False): (
        "Leaves own group and moves to this group (official transfer, history is kept).",
        "Покидает свою группу и переходит в эту (официальный перевод, история сохраняется).",
        "Kendi grubundan çıkıp bu gruba geçer (resmi aktarma, geçmiş kalır).",
        "Verlässt die eigene Gruppe und wechselt in diese (offizielle Versetzung, Verlauf bleibt).",
    ),
    (_G, "öz qrupu", False): ("own group", "своя группа", "kendi grubu", "eigene Gruppe"),
    (_G, "Əlavə olaraq", False): ("As extra", "Дополнительно", "Ek olarak", "Zusätzlich"),
    (_G, "Əlavə üzv", False): ("Extra member", "Доп. участник", "Ek üye", "Zusätzliches Mitglied"),
    (
        _G,
        "Əvvəl qrupsuz tələbələr göstərilir. Ad yazıb axtaranda başqa qrupdakı tələbələr də çıxır — yanında "
        "hansı qrupda olduğu yazılır.",
        False,
    ): (
        "Students without a group are shown first. When you search by name, students of other groups also "
        "appear — with their group shown next to them.",
        "Сначала показываются студенты без группы. При поиске по имени появляются и студенты других групп — "
        "рядом указана их группа.",
        "Önce grubu olmayan öğrenciler gösterilir. Adla arayınca başka gruplardaki öğrenciler de çıkar — "
        "yanında hangi grupta olduğu yazılır.",
        "Zuerst werden Studierende ohne Gruppe angezeigt. Bei der Namenssuche erscheinen auch Studierende "
        "anderer Gruppen — mit ihrer Gruppe daneben.",
    ),
    (
        _R,
        "Bu qrupun cari semestrdə jurnalı yoxdur. Əvvəl dərs yükündə qrupa fənn yazılsın (jurnal açılsın), "
        "sonra tələbəni əlavə edin.",
        False,
    ): (
        "This group has no journal in the current semester. First add a subject for the group in the teaching "
        "load (so a journal opens), then add the student.",
        "У этой группы нет журнала в текущем семестре. Сначала добавьте группе предмет в учебной нагрузке "
        "(чтобы открылся журнал), затем добавьте студента.",
        "Bu grubun mevcut dönemde derslik kaydı yok. Önce ders yükünde gruba ders yazılsın (derslik açılsın), "
        "sonra öğrenciyi ekleyin.",
        "Diese Gruppe hat im aktuellen Semester kein Journal. Zuerst in der Lehrbelastung ein Fach für die "
        "Gruppe anlegen (Journal öffnen), dann die Person hinzufügen.",
    ),
    (_R, "Qrup reyestrindən əlavə üzv (öz qrupu: %s)", True): (
        "Extra member from the group registry (own group: %s)",
        "Дополнительный участник из реестра групп (своя группа: %s)",
        "Grup kaydından ek üye (kendi grubu: %s)",
        "Zusätzliches Mitglied aus dem Gruppenregister (eigene Gruppe: %s)",
    ),
    (_R, "Tələbə onsuz da bu qrupdadır.", False): (
        "The student is already in this group.",
        "Студент уже в этой группе.",
        "Öğrenci zaten bu grupta.",
        "Die Person ist bereits in dieser Gruppe.",
    ),
    (_R, "Tələbənin aktiv akademik qeydi (qrupu) yoxdur.", False): (
        "The student has no active academic record (group).",
        "У студента нет активной академической записи (группы).",
        "Öğrencinin aktif akademik kaydı (grubu) yok.",
        "Die Person hat keinen aktiven Studiendatensatz (Gruppe).",
    ),
    (_R, "onsuz da bu jurnaldadır", False): (
        "already in this journal",
        "уже в этом журнале",
        "zaten bu derslikte",
        "bereits in diesem Journal",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt or "", e.msgid) for e in po}
        added = 0
        for (ctx, msgid, fmt), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            entry = polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=msgstr)
            if fmt:
                entry.flags.append("python-format")
            po.append(entry)
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
