#!/usr/bin/env python3
"""EMSArena i18n — «Bir sillabus — bir neçə jurnal» + köhnə il qapısı (sahib 2026-10-27).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "syllabus.model": {
        "Müəllimin seçimi": t("Teacher's choice", "Выбор преподавателя", "Öğretmenin seçimi", "Wahl der Lehrkraft"),
        "Köhnə sistem (bir sillabus bir neçə jurnalda)": t(
            "Legacy system (one syllabus in several journals)",
            "Старая система (один силлабус в нескольких журналах)",
            "Eski sistem (bir müfredat birkaç yoklama defterinde)",
            "Altsystem (ein Syllabus in mehreren Kursbüchern)",
        ),
        "paylaşılan sillabus": t("shared syllabus", "общий силлабус", "paylaşılan müfredat", "geteilter Syllabus"),
        "paylaşılan sillabuslar": t("shared syllabi", "общие силлабусы", "paylaşılan müfredatlar", "geteilte Syllabi"),
    },
    "accounts.syllabus": {
        "eyni sillabusu istifadə edir": t(
            "uses the same syllabus",
            "использует тот же силлабус",
            "aynı müfredatı kullanıyor",
            "nutzt denselben Syllabus",
        ),
        "köhnə sistemdən": t("from the legacy system", "из старой системы", "eski sistemden", "aus dem Altsystem"),
        "Bu qrup da %(group)s qrupunun sillabusunu istifadə edir — bir sillabus: təsdiq və dəyişikliklər hər iki jurnal "
        "üçün ortaqdır.": t(
            "This group now uses the syllabus of group %(group)s — one syllabus: approval and changes are shared by "
            "both journals.",
            "Эта группа теперь использует силлабус группы %(group)s — один силлабус: утверждение и изменения общие "
            "для обоих журналов.",
            "Bu grup artık %(group)s grubunun müfredatını kullanıyor — tek müfredat: onay ve değişiklikler her iki "
            "defter için ortaktır.",
            "Diese Gruppe nutzt jetzt den Syllabus der Gruppe %(group)s — ein Syllabus: Freigabe und Änderungen "
            "gelten für beide Kursbücher.",
        ),
        "Paylaşım ayrıldı — bu qrupun jurnalı üçün ayrıca sillabus yaradın.": t(
            "Sharing removed — create a separate syllabus for this group's journal.",
            "Связь снята — создайте отдельный силлабус для журнала этой группы.",
            "Paylaşım kaldırıldı — bu grubun defteri için ayrı bir müfredat oluşturun.",
            "Freigabe entfernt — legen Sie für das Kursbuch dieser Gruppe einen eigenen Syllabus an.",
        ),
        "Həmçinin bu qruplarda istifadə olunur: %(groups)s": t(
            "Also used in these groups: %(groups)s",
            "Также используется в группах: %(groups)s",
            "Şu gruplarda da kullanılıyor: %(groups)s",
            "Wird auch in diesen Gruppen genutzt: %(groups)s",
        ),
        "Keçmiş tədris illərinin sillabusu mənbə kimi istifadə olunmur — cari ilin sillabusunu seçin.": t(
            "Syllabi from past academic years cannot be used as a source — choose a syllabus of the current year.",
            "Силлабусы прошлых учебных лет нельзя использовать как источник — выберите силлабус текущего года.",
            "Geçmiş eğitim yıllarının müfredatı kaynak olarak kullanılamaz — bu yılın müfredatını seçin.",
            "Syllabi früherer Studienjahre können nicht als Quelle dienen — wählen Sie einen Syllabus des laufenden "
            "Jahres.",
        ),
        "Bu qrupun öz sillabusu var — eyni sillabusu yalnız sillabusu olmayan qrupda istifadə etmək olar.": t(
            "This group already has its own syllabus — the same syllabus can only be used in a group without one.",
            "У этой группы уже есть свой силлабус — общий силлабус можно использовать только в группе без силлабуса.",
            "Bu grubun kendi müfredatı var — aynı müfredat yalnızca müfredatı olmayan grupta kullanılabilir.",
            "Diese Gruppe hat bereits einen eigenen Syllabus — derselbe Syllabus kann nur in einer Gruppe ohne "
            "Syllabus genutzt werden.",
        ),
        "Bu qrup artıq başqa sillabusu istifadə edir.": t(
            "This group already uses another syllabus.",
            "Эта группа уже использует другой силлабус.",
            "Bu grup zaten başka bir müfredat kullanıyor.",
            "Diese Gruppe nutzt bereits einen anderen Syllabus.",
        ),
        "Bu qrup artıq bu sillabusu istifadə edir.": t(
            "This group already uses this syllabus.",
            "Эта группа уже использует этот силлабус.",
            "Bu grup zaten bu müfredatı kullanıyor.",
            "Diese Gruppe nutzt diesen Syllabus bereits.",
        ),
        "Bu qrup bu sillabusu istifadə etmir.": t(
            "This group does not use this syllabus.",
            "Эта группа не использует этот силлабус.",
            "Bu grup bu müfredatı kullanmıyor.",
            "Diese Gruppe nutzt diesen Syllabus nicht.",
        ),
        "Bir sillabus — bir neçə jurnal": t(
            "One syllabus — several journals",
            "Один силлабус — несколько журналов",
            "Tek müfredat — birkaç defter",
            "Ein Syllabus — mehrere Kursbücher",
        ),
        "Bu sillabus aşağıdakı qrupların jurnalında da öz yerində istifadə olunur. Təsdiq, dəyişikliklər və həftəlik "
        "plan hamısı üçün ortaqdır.": t(
            "This syllabus is also used as is in the journals of the groups below. Approval, changes and the weekly "
            "plan are shared by all of them.",
            "Этот силлабус также используется в журналах групп ниже. Утверждение, изменения и недельный план общие "
            "для всех.",
            "Bu müfredat aşağıdaki grupların defterlerinde de olduğu gibi kullanılıyor. Onay, değişiklikler ve "
            "haftalık plan hepsi için ortaktır.",
            "Dieser Syllabus wird auch in den Kursbüchern der folgenden Gruppen genutzt. Freigabe, Änderungen und "
            "Wochenplan gelten für alle.",
        ),
        "Bu fənn üzrə başqa qrupunuzun jurnalında da eyni sillabusu öz yerində istifadə edə bilərsiniz (məsələn, "
        "potok dərsi) — yeni sillabus yaradılmır.": t(
            "You can use the same syllabus as is in the journal of another of your groups for this subject (for "
            "example, a stream lecture) — no new syllabus is created.",
            "Этот же силлабус можно использовать в журнале другой вашей группы по этому предмету (например, "
            "потоковая лекция) — новый силлабус не создаётся.",
            "Aynı müfredatı bu dersin başka bir grubunuzun defterinde de kullanabilirsiniz (örneğin ortak ders) — "
            "yeni müfredat oluşturulmaz.",
            "Sie können denselben Syllabus auch im Kursbuch einer anderen Ihrer Gruppen in diesem Fach nutzen (z. B. "
            "gemeinsame Vorlesung) — es wird kein neuer Syllabus angelegt.",
        ),
        "Qrup seçin": t("Choose a group", "Выберите группу", "Grup seçin", "Gruppe wählen"),
        "Qrup axtar…": t("Search group…", "Найти группу…", "Grup ara…", "Gruppe suchen…"),
        "Uyğun qrup yoxdur": t("No matching group", "Нет подходящих групп", "Uygun grup yok", "Keine passende Gruppe"),
        "Bu qrupda da istifadə et": t(
            "Use in this group too",
            "Использовать и в этой группе",
            "Bu grupta da kullan",
            "Auch in dieser Gruppe nutzen",
        ),
        "Eyni sillabusu bu qrupda da istifadə et (bir sillabus)": t(
            "Use the same syllabus in this group too (one syllabus)",
            "Использовать тот же силлабус и в этой группе (один силлабус)",
            "Aynı müfredatı bu grupta da kullan (tek müfredat)",
            "Denselben Syllabus auch in dieser Gruppe nutzen (ein Syllabus)",
        ),
        "Yeni sillabus yaradılmır — bu qrupun jurnalı eyni sillabusu öz yerində istifadə edir. Təsdiq, dəyişikliklər "
        "və həftəlik plan hər iki qrup üçün ortaqdır.": t(
            "No new syllabus is created — this group's journal uses the same syllabus as is. Approval, changes and the "
            "weekly plan are shared by both groups.",
            "Новый силлабус не создаётся — журнал этой группы использует тот же силлабус. Утверждение, изменения и "
            "недельный план общие для обеих групп.",
            "Yeni müfredat oluşturulmaz — bu grubun defteri aynı müfredatı olduğu gibi kullanır. Onay, değişiklikler "
            "ve haftalık plan her iki grup için ortaktır.",
            "Es wird kein neuer Syllabus angelegt — das Kursbuch dieser Gruppe nutzt denselben Syllabus. Freigabe, "
            "Änderungen und Wochenplan gelten für beide Gruppen.",
        ),
        "Paylaşım ayrılsın?": t("Remove sharing?", "Снять связь?", "Paylaşım kaldırılsın mı?", "Freigabe entfernen?"),
        "Bu qrupun jurnalı artıq bu sillabusu göstərməyəcək və «Sillabus yoxdur» vəziyyətinə qayıdacaq. Sillabusun "
        "özü və digər qruplar dəyişmir.": t(
            "This group's journal will no longer show this syllabus and returns to «No syllabus». The syllabus itself "
            "and the other groups do not change.",
            "Журнал этой группы больше не будет показывать этот силлабус и вернётся в состояние «Нет силлабуса». Сам "
            "силлабус и другие группы не меняются.",
            "Bu grubun defteri artık bu müfredatı göstermeyecek ve «Müfredat yok» durumuna dönecek. Müfredatın kendisi "
            "ve diğer gruplar değişmez.",
            "Das Kursbuch dieser Gruppe zeigt diesen Syllabus nicht mehr und kehrt zu «Kein Syllabus» zurück. Der "
            "Syllabus selbst und die anderen Gruppen bleiben unverändert.",
        ),
        "Ayır": t("Detach", "Отвязать", "Ayır", "Trennen"),
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
