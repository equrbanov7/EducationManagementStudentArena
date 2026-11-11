#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-11: «Fənn təhvili» növ seçimi (seminar / lab / mühazirə) + «Yük bölgüsü» jurnal nəticəsi.

Beş kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_handover_kinds_2026_11_11.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")

_H = "accounts.handover"
_W = "workload"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_H, "Seçilmiş müəllim bu dərs növünü aparmır"): (
        "The selected teacher does not teach this lesson type",
        "Выбранный преподаватель не ведёт этот вид занятий",
        "Seçilen öğretmen bu ders türünü yürütmüyor",
        "Die ausgewählte Lehrkraft unterrichtet diese Unterrichtsart nicht",
    ),
    (
        _H,
        "Bu dərs növünü bir neçə müəllim aparır — hansı müəllimdən? «Hansı müəllimin fənləri?» süzgəcində "
        "həmin müəllimi seçib yenidən təhvil verin",
    ): (
        "Several teachers teach this lesson type — from which teacher? Pick that teacher in the “Whose courses?” "
        "filter and hand over again",
        "Этот вид занятий ведут несколько преподавателей — от кого передать? Выберите преподавателя в фильтре "
        "«Чьи предметы?» и повторите передачу",
        "Bu ders türünü birden fazla öğretmen yürütüyor — hangi öğretmenden? «Hangi öğretmenin dersleri?» "
        "filtresinde o öğretmeni seçip yeniden devredin",
        "Mehrere Lehrkräfte unterrichten diese Unterrichtsart — von welcher Lehrkraft? Wählen Sie sie im Filter "
        "„Wessen Fächer?“ und übergeben Sie erneut",
    ),
    (_H, "Dərs növü yanlışdır"): (
        "Invalid lesson type",
        "Неверный вид занятия",
        "Geçersiz ders türü",
        "Ungültige Unterrichtsart",
    ),
    (_H, "Dərs növü yanlışdır."): (
        "Invalid lesson type.",
        "Неверный вид занятия.",
        "Geçersiz ders türü.",
        "Ungültige Unterrichtsart.",
    ),
    (_H, "Ən azı bir dərs növü seçin."): (
        "Select at least one lesson type.",
        "Выберите хотя бы один вид занятий.",
        "En az bir ders türü seçin.",
        "Wählen Sie mindestens eine Unterrichtsart.",
    ),
    (_H, "Mühazirə"): ("Lecture", "Лекция", "Teorik ders", "Vorlesung"),
    (_H, "Seminar"): ("Seminar", "Семинар", "Seminer", "Seminar"),
    (_H, "Laboratoriya"): ("Laboratory", "Лабораторная", "Laboratuvar", "Labor"),
    (_H, "Bütün jurnal"): ("Whole journal", "Весь журнал", "Tüm not defteri", "Gesamtes Journal"),
    (_H, "%(count)d fənn: %(what)s → %(to)s."): (
        "%(count)d course(s): %(what)s → %(to)s.",
        "Предметов: %(count)d: %(what)s → %(to)s.",
        "%(count)d ders: %(what)s → %(to)s.",
        "%(count)d Fach/Fächer: %(what)s → %(to)s.",
    ),
    (_H, "seçilmiş müəllimlər"): (
        "the selected teachers",
        "выбранные преподаватели",
        "seçilen öğretmenler",
        "die ausgewählten Lehrkräfte",
    ),
    (_H, "Jurnalın sahibi dəyişmədi — yalnız seçilmiş dərs növü köçdü."): (
        "The journal owner did not change — only the selected lesson type was moved.",
        "Владелец журнала не изменился — передан только выбранный вид занятий.",
        "Defterin sahibi değişmedi — yalnızca seçilen ders türü aktarıldı.",
        "Der Journalinhaber bleibt — nur die gewählte Unterrichtsart wurde übertragen.",
    ),
    (_H, "Bal və davamiyyət olduğu kimi qaldı."): (
        "Grades and attendance stayed as they were.",
        "Оценки и посещаемость сохранены без изменений.",
        "Notlar ve devam durumu olduğu gibi kaldı.",
        "Noten und Anwesenheit bleiben unverändert.",
    ),
    (_H, "Təhvil tamamlandı."): (
        "Handover completed.",
        "Передача завершена.",
        "Devir tamamlandı.",
        "Übergabe abgeschlossen.",
    ),
    (_H, "Təhvil geri qaytarıldı — jurnal %(name)s adına qayıtdı."): (
        "Handover reverted — the journal is back with %(name)s.",
        "Передача отменена — журнал возвращён: %(name)s.",
        "Devir geri alındı — defter %(name)s adına döndü.",
        "Übergabe rückgängig gemacht — das Journal liegt wieder bei %(name)s.",
    ),
    (_H, "Kim aparır (növ üzrə)"): (
        "Who teaches (by lesson type)",
        "Кто ведёт (по видам занятий)",
        "Kim yürütüyor (ders türüne göre)",
        "Wer unterrichtet (nach Unterrichtsart)",
    ),
    (_H, "Yeni müəllim və dərs növü"): (
        "New teacher and lesson type",
        "Новый преподаватель и вид занятий",
        "Yeni öğretmen ve ders türü",
        "Neue Lehrkraft und Unterrichtsart",
    ),
    (_H, "bütün jurnal və ya yalnız seminar / lab / mühazirə"): (
        "whole journal or only seminar / lab / lecture",
        "весь журнал или только семинар / лаб. / лекция",
        "tüm defter veya yalnızca seminer / laboratuvar / teorik ders",
        "gesamtes Journal oder nur Seminar / Labor / Vorlesung",
    ),
    (_H, "fənn, kod, qrup və ya müəllim"): (
        "course, code, group or teacher",
        "предмет, код, группа или преподаватель",
        "ders, kod, grup veya öğretmen",
        "Fach, Code, Gruppe oder Lehrkraft",
    ),
    (_H, "Hansı dərslər təhvil verilir?"): (
        "Which lessons are handed over?",
        "Какие занятия передаются?",
        "Hangi dersler devrediliyor?",
        "Welche Stunden werden übergeben?",
    ),
    (
        _H,
        "Hamısı seçilibsə jurnal tam köçür. Yalnız «Seminar» seçsəniz mühazirəçi və jurnalın sahibi yerində qalır "
        "— seminarı aparan müəllimin payı yeni müəllimə keçir.",
    ): (
        "With everything selected the whole journal moves. If you select only “Seminar”, the lecturer and the "
        "journal owner stay — only the seminar teacher's part moves to the new teacher.",
        "Если выбрано всё, журнал передаётся полностью. Если выбрать только «Семинар», лектор и владелец журнала "
        "остаются — новому преподавателю переходит только часть семинариста.",
        "Hepsi seçiliyse defter tamamen aktarılır. Yalnızca «Seminer» seçerseniz teorik ders öğretmeni ve defterin "
        "sahibi yerinde kalır — yalnızca seminer öğretmeninin payı yeni öğretmene geçer.",
        "Ist alles ausgewählt, wird das ganze Journal übertragen. Wählen Sie nur „Seminar“, bleiben Dozent und "
        "Journalinhaber — nur der Anteil der Seminarlehrkraft geht an die neue Lehrkraft.",
    ),
    (_H, "Nə köçür — indiki → yeni"): (
        "What moves — current → new",
        "Что передаётся — текущий → новый",
        "Ne aktarılıyor — mevcut → yeni",
        "Was übertragen wird — aktuell → neu",
    ),
    (_H, "Yalnız seminar / lab seçilsə — yalnız həmin dərs növünün yazma hüququ keçir, sahib dəyişmir."): (
        "If only seminar / lab is selected, only that lesson type's write access moves; the owner stays.",
        "Если выбран только семинар / лаб., передаётся право записи только этого вида занятий; владелец остаётся.",
        "Yalnızca seminer / laboratuvar seçilirse yalnızca o ders türünün yazma yetkisi aktarılır, sahip değişmez.",
        "Ist nur Seminar / Labor gewählt, wird nur das Schreibrecht dieser Unterrichtsart übertragen; der Inhaber "
        "bleibt.",
    ),
    (
        _H,
        "Bütün jurnalı və ya yalnız bir dərs növünü (məs. seminarı) yeni müəllimə verin. Yazılmış bal və davamiyyət "
        "olduğu kimi qalır.",
    ): (
        "Hand the whole journal or just one lesson type (e.g. the seminar) to the new teacher. Recorded grades and "
        "attendance stay as they are.",
        "Передайте новому преподавателю весь журнал или только один вид занятий (например, семинар). Выставленные "
        "оценки и посещаемость сохраняются.",
        "Tüm defteri veya yalnızca bir ders türünü (ör. semineri) yeni öğretmene verin. Girilen notlar ve devam "
        "durumu olduğu gibi kalır.",
        "Übergeben Sie das ganze Journal oder nur eine Unterrichtsart (z. B. das Seminar) an die neue Lehrkraft. "
        "Eingetragene Noten und Anwesenheit bleiben erhalten.",
    ),
    (_H, "yeni müəllim"): ("new teacher", "новый преподаватель", "yeni öğretmen", "neue Lehrkraft"),
    (_H, "jurnalın sahibi dəyişmir"): (
        "journal owner stays",
        "владелец журнала не меняется",
        "defterin sahibi değişmez",
        "Journalinhaber bleibt",
    ),
    (_H, "jurnalın sahibi olur"): (
        "becomes the journal owner",
        "становится владельцем журнала",
        "defterin sahibi olur",
        "wird Journalinhaber",
    ),
    (
        _W,
        "Bölgü saxlanıldı, amma jurnal yeni müəllimə köçmədi (bal yazma səlahiyyəti yoxdur və ya jurnal dəyişib). "
        "«Fənn təhvili» bölməsindən yoxlayın.",
    ): (
        "The assignment was saved, but the journal did not move to the new teacher (no grading permission, or the "
        "journal has changed). Check the “Course handover” section.",
        "Распределение сохранено, но журнал не перешёл к новому преподавателю (нет права выставлять оценки или "
        "журнал изменился). Проверьте раздел «Передача предмета».",
        "Dağılım kaydedildi, ancak defter yeni öğretmene geçmedi (not girme yetkisi yok veya defter değişti). "
        "«Ders devri» bölümünü kontrol edin.",
        "Die Zuteilung wurde gespeichert, aber das Journal ging nicht an die neue Lehrkraft (keine Benotungsrechte "
        "oder das Journal wurde geändert). Prüfen Sie den Bereich „Fachübergabe“.",
    ),
    (_W, "Bölgü saxlanıldı — jurnal bütün balları ilə yeni müəllimə keçdi."): (
        "Assignment saved — the journal moved to the new teacher with all grades.",
        "Распределение сохранено — журнал со всеми оценками перешёл к новому преподавателю.",
        "Dağılım kaydedildi — defter tüm notlarıyla yeni öğretmene geçti.",
        "Zuteilung gespeichert — das Journal ging mit allen Noten an die neue Lehrkraft.",
    ),
    (_W, "Bölgü saxlanıldı — bu dərs növünün jurnal payı yeni müəllimə keçdi (bal itmir)."): (
        "Assignment saved — this lesson type's part of the journal moved to the new teacher (no grades are lost).",
        "Распределение сохранено — часть журнала по этому виду занятий перешла к новому преподавателю (оценки не "
        "теряются).",
        "Dağılım kaydedildi — bu ders türünün defter payı yeni öğretmene geçti (notlar kaybolmaz).",
        "Zuteilung gespeichert — der Journalanteil dieser Unterrichtsart ging an die neue Lehrkraft (keine Noten "
        "gehen verloren).",
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
