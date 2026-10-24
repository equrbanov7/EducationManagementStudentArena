#!/usr/bin/env python3
"""EMSArena i18n — imtahan ↔ jurnal bağlantısı, müəllim → fənn seçimi (sahib 2026-10-24).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

MODEL = "exams.model.exam.field"
LABEL = "exams.form.exam.label"
HELP = "exams.form.exam.help"
ERROR = "exams.form.exam.error"
MODAL = "exams.template.create_exam_modal_form"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


AZ_OVERRIDES = {}

TEACHER = t("Teacher (journal)", "Преподаватель (журнал)", "Öğretmen (yoklama defteri)", "Lehrkraft (Journal)")

ENTRIES = {
    MODEL: {
        "Müəllim (jurnal)": TEACHER,
        "Bağlı jurnallar": t("Linked journals", "Связанные журналы", "Bağlı defterler", "Verknüpfte Journale"),
    },
    LABEL: {"Müəllim (jurnal)": TEACHER},
    HELP: {
        "Müəllimi seçsəniz, fənn siyahısı onun cari dövrdə tədris etdiyi fənlərlə məhdudlaşır və "
        "midterm nəticəsi həmin fənnin qrup jurnallarına yazılır. Boş qalarsa bütün fənlər göstərilir.": t(
            "If you select a teacher, the subject list is limited to the subjects they teach in the current "
            "period and the midterm result is written to that subject's group journals. If left empty, all "
            "subjects are shown.",
            "Если выбрать преподавателя, список предметов ограничится предметами, которые он ведёт в текущем "
            "периоде, а результат промежуточного экзамена будет записан в журналы групп по этому предмету. "
            "Если оставить пустым, показываются все предметы.",
            "Öğretmen seçerseniz ders listesi onun mevcut dönemde verdiği derslerle sınırlanır ve ara sınav "
            "sonucu o dersin grup defterlerine yazılır. Boş bırakılırsa tüm dersler gösterilir.",
            "Wenn Sie eine Lehrkraft auswählen, wird die Fächerliste auf die Fächer beschränkt, die sie im "
            "aktuellen Zeitraum unterrichtet, und das Ergebnis der Zwischenprüfung wird in die Gruppenjournale "
            "dieses Fachs geschrieben. Bleibt das Feld leer, werden alle Fächer angezeigt.",
        ),
    },
    ERROR: {
        "Seçilmiş müəllim bu fənni cari dövrdə tədris etmir.": t(
            "The selected teacher does not teach this subject in the current period.",
            "Выбранный преподаватель не ведёт этот предмет в текущем периоде.",
            "Seçilen öğretmen bu dersi mevcut dönemde vermiyor.",
            "Die ausgewählte Lehrkraft unterrichtet dieses Fach im aktuellen Zeitraum nicht.",
        ),
    },
    MODAL: {
        "Müəllim tapılmadı": t(
            "No teacher found", "Преподаватель не найден", "Öğretmen bulunamadı", "Keine Lehrkraft gefunden"
        ),
        "Müəllim axtar…": t("Search teacher…", "Поиск преподавателя…", "Öğretmen ara…", "Lehrkraft suchen…"),
        "Seçilmiş müəllim": t(
            "Selected teacher", "Выбранный преподаватель", "Seçilen öğretmen", "Ausgewählte Lehrkraft"
        ),
        "Təmizlə (bütün fənlər)": t(
            "Clear (all subjects)", "Очистить (все предметы)", "Temizle (tüm dersler)", "Leeren (alle Fächer)"
        ),
        "Bu müəllimin cari dövrdə tədris etdiyi fənn tapılmadı": t(
            "No subject taught by this teacher in the current period was found",
            "Не найдено предметов, которые этот преподаватель ведёт в текущем периоде",
            "Bu öğretmenin mevcut dönemde verdiği ders bulunamadı",
            "Kein Fach gefunden, das diese Lehrkraft im aktuellen Zeitraum unterrichtet",
        ),
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
            if lang == "az":
                msgstr = AZ_OVERRIDES.get((ctx, msgid), msgid)
            else:
                msgstr = translations.get(lang) or msgid
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
