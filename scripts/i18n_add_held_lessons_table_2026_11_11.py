#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-11: «Keçilmiş dərslər» redizaynı + «Cədvəl formasında bax» (müəllim cədvəli, Excel).

Beş kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_held_lessons_table_2026_11_11.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")

_A = "accounts.lessons_log"
_R = "registrar.lessons_log"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("ui.filters", "Daha çox süzgəc"): ("More filters", "Ещё фильтры", "Daha fazla filtre", "Weitere Filter"),
    (_A, "Akademik saat"): ("Academic hours", "Академические часы", "Akademik ders saati", "Akademische Stunden"),
    (_A, "Bu müəllimin dərsləri əhatənizdə deyil."): (
        "This teacher's lessons are outside your scope.",
        "Занятия этого преподавателя вне вашей области доступа.",
        "Bu öğretmenin dersleri kapsamınızda değil.",
        "Die Stunden dieser Lehrkraft liegen außerhalb Ihres Bereichs.",
    ),
    (_A, "Bölmə üzrə (tədris dili)"): (
        "By sector (language of instruction)",
        "По секторам (язык обучения)",
        "Bölüme göre (öğretim dili)",
        "Nach Sektor (Unterrichtssprache)",
    ),
    (_A, "Cədvəl formasında bax"): (
        "View as a table",
        "Показать таблицей",
        "Tablo olarak görüntüle",
        "Als Tabelle anzeigen",
    ),
    (_A, "Cədvəl jurnalla tutuşdurulur…"): (
        "Comparing the timetable with the journal…",
        "Расписание сверяется с журналом…",
        "Ders programı defterle karşılaştırılıyor…",
        "Stundenplan wird mit dem Journal abgeglichen…",
    ),
    (_A, "Cədvəl yüklənmədi. Yenidən cəhd edin."): (
        "The table could not be loaded. Please try again.",
        "Не удалось загрузить таблицу. Повторите попытку.",
        "Tablo yüklenemedi. Tekrar deneyin.",
        "Die Tabelle konnte nicht geladen werden. Bitte erneut versuchen.",
    ),
    (_A, "Cəmi"): ("Total", "Итого", "Toplam", "Gesamt"),
    (_A, "Cəmi %(total)s dərs — siyahı yeni tarixdən köhnəyə doğru hissə-hissə açılır."): (
        "%(total)s lessons in total — the list opens in parts, newest first.",
        "Всего занятий: %(total)s — список открывается частями, от новых к старым.",
        "Toplam %(total)s ders — liste yeniden eskiye doğru parça parça açılır.",
        "Insgesamt %(total)s Stunden — die Liste wird abschnittsweise geöffnet, neueste zuerst.",
    ),
    (_A, "Daha çox göstər"): ("Show more", "Показать ещё", "Daha fazla göster", "Mehr anzeigen"),
    (_A, "Dərs növü"): ("Lesson type", "Вид занятия", "Ders türü", "Unterrichtsart"),
    (_A, "Dərs növü üzrə"): ("By lesson type", "По видам занятий", "Ders türüne göre", "Nach Unterrichtsart"),
    (_A, "Dərslər"): ("Lessons", "Занятия", "Dersler", "Stunden"),
    (_A, "Excel kimi yüklə"): ("Download as Excel", "Скачать в Excel", "Excel olarak indir", "Als Excel herunterladen"),
    (_A, "Keçilmiş saat"): ("Hours held", "Проведено часов", "İşlenen saat", "Gehaltene Stunden"),
    (_A, "Müəllimin keçdiyi dərslər"): (
        "Lessons held by the teacher",
        "Занятия, проведённые преподавателем",
        "Öğretmenin işlediği dersler",
        "Von der Lehrkraft gehaltene Stunden",
    ),
    (_A, "Məlumat yüklənmədi. Səhifəni yeniləyib yenidən cəhd edin."): (
        "The data could not be loaded. Refresh the page and try again.",
        "Не удалось загрузить данные. Обновите страницу и повторите попытку.",
        "Veriler yüklenemedi. Sayfayı yenileyip tekrar deneyin.",
        "Die Daten konnten nicht geladen werden. Seite aktualisieren und erneut versuchen.",
    ),
    (_A, "Otaq"): ("Room", "Аудитория", "Derslik", "Raum"),
    (
        _A,
        "Patok (bir neçə qrupa birgə keçilən) dərs bir dəfə sayılır: eyni fənn, eyni dərs növü, eyni tarix və saat "
        "— bir dərs.",
    ): (
        "A stream lesson (held jointly for several groups) is counted once: same subject, same lesson type, same "
        "date and time — one lesson.",
        "Потоковое занятие (проведённое совместно для нескольких групп) считается один раз: тот же предмет, тот же "
        "вид занятия, та же дата и время — одно занятие.",
        "Ortak (birkaç gruba birlikte işlenen) ders bir kez sayılır: aynı ders, aynı ders türü, aynı tarih ve saat "
        "— tek ders.",
        "Eine Sammelstunde (gemeinsam für mehrere Gruppen) wird einmal gezählt: gleiches Fach, gleiche "
        "Unterrichtsart, gleiches Datum und gleiche Uhrzeit — eine Stunde.",
    ),
    (_A, "Seçilmiş dövrdə bu müəllimin keçilmiş dərsi yoxdur."): (
        "This teacher has no lessons held in the selected period.",
        "У этого преподавателя нет проведённых занятий за выбранный период.",
        "Seçilen dönemde bu öğretmenin işlenmiş dersi yok.",
        "Diese Lehrkraft hat im gewählten Zeitraum keine gehaltenen Stunden.",
    ),
    (_A, "Yüklənir…"): ("Loading…", "Загрузка…", "Yükleniyor…", "Wird geladen…"),
    (_A, "hesablanır…"): ("calculating…", "вычисляется…", "hesaplanıyor…", "wird berechnet…"),
    (_A, "patok"): ("stream", "поток", "ortak", "Sammelgruppe"),
    (_A, "Ətraflı bax"): ("View details", "Подробнее", "Ayrıntıları gör", "Details anzeigen"),
    (_R, "%(hours)s saat (%(lessons)s dərs)"): (
        "%(hours)s hours (%(lessons)s lessons)",
        "%(hours)s ч. (%(lessons)s занятий)",
        "%(hours)s saat (%(lessons)s ders)",
        "%(hours)s Std. (%(lessons)s Einheiten)",
    ),
    (_R, "Azərbaycan bölməsi"): (
        "Azerbaijani sector",
        "Азербайджанский сектор",
        "Azerbaycanca bölümü",
        "Aserbaidschanischer Sektor",
    ),
    (_R, "İngilis bölməsi"): ("English sector", "Английский сектор", "İngilizce bölümü", "Englischer Sektor"),
    (_R, "Rus bölməsi"): ("Russian sector", "Русский сектор", "Rusça bölümü", "Russischer Sektor"),
    (_R, "Qarışıq bölmə (birgə dərs)"): (
        "Mixed sectors (joint lesson)",
        "Смешанный сектор (совместное занятие)",
        "Karma bölüm (ortak ders)",
        "Gemischter Sektor (gemeinsame Stunde)",
    ),
    (_R, "Bölməsi göstərilməyib"): (
        "Sector not specified",
        "Сектор не указан",
        "Bölüm belirtilmemiş",
        "Sektor nicht angegeben",
    ),
    (_R, "Bölmə"): ("Sector", "Сектор", "Bölüm", "Sektor"),
    (_R, "Bölmə üzrə"): ("By sector", "По секторам", "Bölüme göre", "Nach Sektor"),
    (_R, "Cəmi"): ("Total", "Итого", "Toplam", "Gesamt"),
    (_R, "Dərs növü"): ("Lesson type", "Вид занятия", "Ders türü", "Unterrichtsart"),
    (_R, "Dərs növü üzrə"): ("By lesson type", "По видам занятий", "Ders türüne göre", "Nach Unterrichtsart"),
    (_R, "Dərs sayı"): ("Number of lessons", "Количество занятий", "Ders sayısı", "Anzahl der Stunden"),
    (_R, "Dərslər"): ("Lessons", "Занятия", "Dersler", "Stunden"),
    (_R, "Həftənin günü"): ("Day of the week", "День недели", "Haftanın günü", "Wochentag"),
    (_R, "Keçilmiş saat"): ("Hours held", "Проведено часов", "İşlenen saat", "Gehaltene Stunden"),
    (_R, "Qeyd olunan"): ("Marked", "Отмечено", "İşaretlenen", "Erfasst"),
    (_R, "Yekun"): ("Summary", "Итог", "Özet", "Ergebnis"),
    (_R, "İcmal"): ("Summary", "Сводка", "Özet", "Übersicht"),
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
