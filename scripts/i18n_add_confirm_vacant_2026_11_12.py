#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-12: «Bölgünü təsdiqlə» natamam sətirlər + «Aydındır, Vakant saxla və təsdiqlə».

Sahib: «kimsə təyin olunmasa, mən bölgünü təsdiqləyəndə aydın info versin və "aydındır" deyəndən sonra
təsdiqlənsin, onda vakantda qalsın». Server (``django``: ``workload`` və ``accounts.workload``) və JS
(``djangojs``, kontekstsiz) kataloqlarına beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_confirm_vacant_2026_11_12.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_W = "workload"
_AW = "accounts.workload"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (
        "django",
        _W,
        "%(count)s sətirdə bölünmüş saat sətrin cəmindən çoxdur: %(names)s. Artıq bölgünü azaldın və ya "
        "sətrin cəmini «Redaktə» ilə artırın — «Vakant» bunu düzəltmir.",
    ): (
        "In %(count)s row(s) more hours are assigned than the row total: %(names)s. Reduce the extra assignment "
        "or raise the row total with “Edit” — “Vacant” does not fix this.",
        "В %(count)s строк(ах) распределено больше часов, чем итог строки: %(names)s. Уменьшите лишнее "
        "распределение или увеличьте итог строки через «Редактировать» — «Вакансия» это не исправляет.",
        "%(count)s satırda dağıtılan saat satır toplamından fazla: %(names)s. Fazla dağıtımı azaltın veya satır "
        "toplamını «Düzenle» ile artırın — «Boş» bunu düzeltmez.",
        "In %(count)s Zeile(n) sind mehr Stunden verteilt als die Zeilensumme: %(names)s. Kürzen Sie die "
        "überzählige Zuteilung oder erhöhen Sie die Zeilensumme über „Bearbeiten“ — „Unbesetzt“ behebt das nicht.",
    ),
    (
        "django",
        _W,
        "%(count)s sətirdə %(hours)s saat heç kimə bölünməyib. Bu saatları «Vakant» saxlayıb təsdiqləyə "
        "və ya əvvəlcə müəllim təyin edə bilərsiniz.",
    ): (
        "In %(count)s row(s) %(hours)s hours are not assigned to anyone. You can keep these hours as “Vacant” "
        "and confirm, or assign teachers first.",
        "В %(count)s строк(ах) %(hours)s ч никому не распределены. Можно оставить эти часы как «Вакансия» и "
        "утвердить или сначала назначить преподавателей.",
        "%(count)s satırda %(hours)s saat kimseye dağıtılmamış. Bu saatleri «Boş» bırakıp onaylayabilir veya "
        "önce öğretim elemanı atayabilirsiniz.",
        "In %(count)s Zeile(n) sind %(hours)s Std. niemandem zugeteilt. Sie können diese Stunden als „Unbesetzt“ "
        "belassen und bestätigen oder zuerst Lehrkräfte zuweisen.",
    ),
    (
        "django",
        _W,
        "İntensiv kurs sətri natamamdır: %(names)s. Onun müəllimi «İntensiv kurs» dialoqundan təyin "
        "olunur — «Vakant» burada yazılmır.",
    ): (
        "An intensive course row is incomplete: %(names)s. Its teacher is assigned in the “Intensive course” "
        "dialog — “Vacant” is not written here.",
        "Строка интенсивного курса не заполнена: %(names)s. Её преподаватель назначается в диалоге «Интенсивный "
        "курс» — «Вакансия» здесь не записывается.",
        "Yoğun kurs satırı eksik: %(names)s. Öğretim elemanı «Yoğun kurs» penceresinden atanır — «Boş» burada "
        "yazılmaz.",
        "Eine Intensivkurs-Zeile ist unvollständig: %(names)s. Ihre Lehrkraft wird im Dialog „Intensivkurs“ "
        "zugewiesen — „Unbesetzt“ wird hier nicht eingetragen.",
    ),
    (
        "django",
        _AW,
        "Bu saatlar heç kimə bölünməyib. Təsdiqləsəniz «Vakant» kimi qalacaq — sonra müəllim təyin edə bilərsiniz.",
    ): (
        "These hours are not assigned to anyone. If you confirm, they will stay “Vacant” — you can assign a "
        "teacher later.",
        "Эти часы никому не распределены. Если утвердите, они останутся «Вакансия» — преподавателя можно "
        "назначить позже.",
        "Bu saatler kimseye dağıtılmamış. Onaylarsanız «Boş» olarak kalacak — öğretim elemanını sonra "
        "atayabilirsiniz.",
        "Diese Stunden sind niemandem zugeteilt. Wenn Sie bestätigen, bleiben sie „Unbesetzt“ — Sie können "
        "später eine Lehrkraft zuweisen.",
    ),
    ("django", _AW, "Fənnin adına klikləsəniz, siyahı həmin fənnə görə süzülür."): (
        "Click a course name to filter the list by that course.",
        "Нажмите на название дисциплины, чтобы отфильтровать список по ней.",
        "Ders adına tıklarsanız liste o derse göre süzülür.",
        "Klicken Sie auf einen Fachnamen, um die Liste nach diesem Fach zu filtern.",
    ),
    ("django", _AW, "Aydındır: bölünməmiş saatlar «Vakant» qalsın"): (
        "Understood: keep the unassigned hours “Vacant”",
        "Понятно: нераспределённые часы остаются «Вакансия»",
        "Anlaşıldı: dağıtılmamış saatler «Boş» kalsın",
        "Verstanden: nicht zugeteilte Stunden bleiben „Unbesetzt“",
    ),
    (
        "django",
        _AW,
        "Bu sətirlərdə bölünmüş saat sətrin cəmindən çoxdur. Əvvəlcə artıq bölgünü azaldın və ya cəmi "
        "artırın — «Vakant» bunu düzəltmir.",
    ): (
        "These rows have more hours assigned than the row total. First reduce the extra assignment or raise the "
        "total — “Vacant” does not fix this.",
        "В этих строках распределено больше часов, чем итог строки. Сначала уменьшите лишнее распределение или "
        "увеличьте итог — «Вакансия» это не исправляет.",
        "Bu satırlarda dağıtılan saat satır toplamından fazla. Önce fazla dağıtımı azaltın veya toplamı artırın — "
        "«Boş» bunu düzeltmez.",
        "In diesen Zeilen sind mehr Stunden verteilt als die Zeilensumme. Kürzen Sie zuerst die überzählige "
        "Zuteilung oder erhöhen Sie die Summe — „Unbesetzt“ behebt das nicht.",
    ),
    ("django", _AW, "Aydındır, Vakant saxla və təsdiqlə"): (
        "Understood, keep Vacant and confirm",
        "Понятно, оставить вакансию и утвердить",
        "Anlaşıldı, Boş bırak ve onayla",
        "Verstanden, unbesetzt lassen und bestätigen",
    ),
    ("djangojs", None, "%(label)s %(hours)s s"): (
        "%(label)s %(hours)s h",
        "%(label)s %(hours)s ч",
        "%(label)s %(hours)s sa",
        "%(label)s %(hours)s Std.",
    ),
    ("djangojs", None, "müəllim yoxdur"): ("no teacher", "нет преподавателя", "öğretim elemanı yok", "keine Lehrkraft"),
    ("djangojs", None, "qismən bölünüb"): (
        "partly assigned",
        "распределено частично",
        "kısmen dağıtıldı",
        "teilweise zugeteilt",
    ),
    ("djangojs", None, "artıq: %(hours)s"): (
        "extra: %(hours)s",
        "лишнее: %(hours)s",
        "fazla: %(hours)s",
        "zu viel: %(hours)s",
    ),
    ("djangojs", None, "%(count)s sətirdə %(hours)s saat müəllimə bölünməyib:"): (
        "In %(count)s row(s) %(hours)s hours are not assigned to a teacher:",
        "В %(count)s строк(ах) %(hours)s ч не распределены преподавателям:",
        "%(count)s satırda %(hours)s saat öğretim elemanına dağıtılmamış:",
        "In %(count)s Zeile(n) sind %(hours)s Std. keiner Lehrkraft zugeteilt:",
    ),
    ("djangojs", None, "«Vakant» saxlanıldı: %(hours)s saat (%(rows)s sətir)."): (
        "Kept “Vacant”: %(hours)s hours (%(rows)s rows).",
        "Оставлено «Вакансия»: %(hours)s ч (%(rows)s строк).",
        "«Boş» bırakıldı: %(hours)s saat (%(rows)s satır).",
        "„Unbesetzt“ belassen: %(hours)s Std. (%(rows)s Zeilen).",
    ),
}


def main():
    for domain in ("django", "djangojs"):
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
