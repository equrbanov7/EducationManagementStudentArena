#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-26: müəllimin öz yazdığı jurnal hissəsi jurnal kimi cədvəldə («Öz jurnal qeydlərim»,
geniş görünüşdə «Müəllimin yazdığı hissə»).

``django`` kataloquna (``registrar.own_history``) beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_own_history_table_2026_11_26.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_C = "registrar.own_history"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _C, "Müəllimin yazdığı hissə"): (
        "Part written by the teacher",
        "Часть, записанная преподавателем",
        "Öğretmenin yazdığı kısım",
        "Vom Lehrenden erfasster Teil",
    ),
    ("django", _C, "Müəllimin öz daxil etdiyi qeyd"): (
        "Entry made by the teacher",
        "Запись, внесённая преподавателем",
        "Öğretmenin kendi girdiği kayıt",
        "Vom Lehrenden selbst erfasster Eintrag",
    ),
    ("django", _C, "Xülasə"): ("Summary", "Сводка", "Özet", "Übersicht"),
    ("django", _C, "Dərs tipi"): ("Lesson type", "Тип занятия", "Ders türü", "Lehrveranstaltungsart"),
    ("django", _C, "Hamısı"): ("All", "Все", "Tümü", "Alle"),
    ("django", _C, "Jurnal"): ("Journal", "Журнал", "Yoklama defteri", "Kursbuch"),
    ("django", _C, "s."): ("h", "ч.", "sa.", "Std."),
    ("django", _C, "Müh."): ("Lect.", "Лек.", "Teo.", "Vorl."),
    ("django", _C, "Sem."): ("Sem.", "Сем.", "Sem.", "Sem."),
    ("django", _C, "Prak."): ("Pract.", "Практ.", "Uyg.", "Prakt."),
    ("django", _C, "Lab."): ("Lab.", "Лаб.", "Lab.", "Lab."),
    ("django", _C, "iştirak"): ("present", "присутствие", "katılım", "anwesend"),
    ("django", _C, "qayıb"): ("absent", "пропуск", "devamsız", "abwesend"),
    ("django", _C, "göstərilən qeyd yoxdur"): (
        "no entry shown",
        "нет показываемой записи",
        "gösterilen kayıt yok",
        "kein angezeigter Eintrag",
    ),
    ("django", _C, "köçürülmüş qeyd, daxil edəni bilinmir"): (
        "migrated entry, author unknown",
        "перенесённая запись, автор неизвестен",
        "aktarılmış kayıt, gireni bilinmiyor",
        "übernommener Eintrag, Urheber unbekannt",
    ),
    ("django", _C, "Bu dərslərdə görünən bal/davamiyyət qeydi yoxdur."): (
        "There are no visible score/attendance entries in these lessons.",
        "В этих занятиях нет видимых записей оценок/посещаемости.",
        "Bu derslerde görünen not/devam kaydı yok.",
        "In diesen Lehrveranstaltungen gibt es keine sichtbaren Noten-/Anwesenheitseinträge.",
    ),
    ("django", _C, "Nə vaxt, harada yazılıb"): (
        "When and where it was recorded",
        "Когда и где записано",
        "Ne zaman, nerede yazıldı",
        "Wann und wo erfasst",
    ),
    ("django", _C, "Vaxt"): ("Time", "Время", "Saat", "Uhrzeit"),
    ("django", _C, "Bölmə"): ("Section", "Подгруппа", "Şube", "Teilgruppe"),
    ("django", _C, "Mövzu"): ("Topic", "Тема", "Konu", "Thema"),
    ("django", _C, "Otaq"): ("Room", "Аудитория", "Derslik", "Raum"),
    ("django", _C, "Qeyd"): ("Entries", "Записи", "Kayıt", "Einträge"),
    ("django", _C, "Yazılıb"): ("Recorded", "Записано", "Yazıldı", "Erfasst"),
    ("django", _C, "Passiv"): ("Passive", "Пассивное", "Pasif", "Passiv"),
    ("django", _C, "Dərs"): ("Lesson", "Занятие", "Ders", "Lehrveranstaltung"),
    ("django", _C, "Son qeyd"): ("Last entry", "Последняя запись", "Son kayıt", "Letzter Eintrag"),
    ("django", _C, "Köhnə sistemdən"): (
        "From the old system",
        "Из старой системы",
        "Eski sistemden",
        "Aus dem Altsystem",
    ),
    ("django", _C, "Keçirib"): ("Taught", "Провёл(а)", "Dersi verdi", "Gehalten"),
    ("django", _C, "Dərsi yaradıb"): (
        "Created the lesson",
        "Создал(а) занятие",
        "Dersi oluşturdu",
        "Lehrveranstaltung angelegt",
    ),
    ("django", _C, "Yalnız qeyd daxil edib"): (
        "Entered marks only",
        "Только внёс(ла) записи",
        "Yalnızca kayıt girdi",
        "Nur Einträge erfasst",
    ),
    (
        "django",
        _C,
        "Yalnız sizin keçirdiyiniz və ya yazdığınız dərslər və öz daxil etdiyiniz qeydlər göstərilir. "
        "Saat yalnız adınıza keçirilmiş dərslərdən sayılır. Yalnız oxunur.",
    ): (
        "Only lessons you taught or recorded and the entries you made yourself are shown. "
        "Hours count only lessons held in your name. Read-only.",
        "Показаны только проведённые или записанные вами занятия и внесённые вами записи. "
        "Часы считаются только по занятиям, проведённым на ваше имя. Только просмотр.",
        "Yalnızca verdiğiniz veya yazdığınız dersler ve kendi girdiğiniz kayıtlar gösterilir. "
        "Saatler yalnızca adınıza işlenen derslerden sayılır. Salt okunur.",
        "Angezeigt werden nur von Ihnen gehaltene oder erfasste Lehrveranstaltungen und Ihre eigenen Einträge. "
        "Stunden zählen nur für auf Ihren Namen gehaltene Lehrveranstaltungen. Nur Lesezugriff.",
    ),
    (
        "django",
        _C,
        "Yalnız bu müəllimin keçirdiyi və ya yazdığı dərslər və onun daxil etdiyi qeydlər göstərilir. "
        "Saat yalnız müəllimin adına keçirilmiş dərslərdən sayılır. Yalnız oxunur.",
    ): (
        "Only lessons this teacher taught or recorded and the entries they made are shown. "
        "Hours count only lessons held in the teacher's name. Read-only.",
        "Показаны только проведённые или записанные этим преподавателем занятия и внесённые им записи. "
        "Часы считаются только по занятиям, проведённым на имя преподавателя. Только просмотр.",
        "Yalnızca bu öğretmenin verdiği veya yazdığı dersler ve girdiği kayıtlar gösterilir. "
        "Saatler yalnızca öğretmen adına işlenen derslerden sayılır. Salt okunur.",
        "Angezeigt werden nur von dieser Lehrkraft gehaltene oder erfasste Lehrveranstaltungen und ihre Einträge. "
        "Stunden zählen nur für auf den Namen der Lehrkraft gehaltene Lehrveranstaltungen. Nur Lesezugriff.",
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
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()
