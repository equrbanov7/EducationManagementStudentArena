#!/usr/bin/env python3
"""EMSArena i18n — qrup imtahanın fənnini keçmir: xəbərdarlıq modalı + məcburi əlavə (sahib 2026-10-27).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CTX = "exams.unit_coverage"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    CTX: {
        "Bu qrupun bu fənni yoxdur": t(
            "This group does not take this subject",
            "У этой группы нет этого предмета",
            "Bu grubun bu dersi yok",
            "Diese Gruppe hat dieses Fach nicht",
        ),
        "Bu qrupda {n} tələbə bu fənnin jurnalında yoxdur": t(
            "{n} student(s) of this group are not in this subject's journal",
            "В этой группе студентов, которых нет в журнале этого предмета: {n}",
            "Bu grupta {n} öğrenci bu dersin defterinde yok",
            "{n} Studierende dieser Gruppe stehen nicht im Journal dieses Fachs",
        ),
        "Seçilmiş qrupların tələbələri bu fənnin jurnalında yoxdur": t(
            "Students of the selected groups are not in this subject's journal",
            "Студентов выбранных групп нет в журнале этого предмета",
            "Seçilen grupların öğrencileri bu dersin defterinde yok",
            "Studierende der ausgewählten Gruppen stehen nicht im Journal dieses Fachs",
        ),
        "Fənn: {subject}. Bu tələbələrin imtahan nəticəsi fənnin jurnalına düşməyəcək.": t(
            "Subject: {subject}. These students' exam results will not reach the subject journal.",
            "Предмет: {subject}. Результаты экзамена этих студентов не попадут в журнал предмета.",
            "Ders: {subject}. Bu öğrencilerin sınav sonucu dersin defterine düşmeyecek.",
            "Fach: {subject}. Die Prüfungsergebnisse dieser Studierenden gelangen nicht ins Fachjournal.",
        ),
        "{n} / {total} tələbə fənnin cari semestr jurnalında yoxdur": t(
            "{n} / {total} students are not in the subject's current-semester journal",
            "{n} / {total} студентов нет в журнале предмета текущего семестра",
            "{n} / {total} öğrenci dersin bu dönem defterinde yok",
            "{n} / {total} Studierende stehen nicht im Journal des laufenden Semesters",
        ),
        "Bu qrupun bu fəndən cari semestr jurnalı yoxdur.": t(
            "This group has no current-semester journal for this subject.",
            "У этой группы нет журнала по этому предмету в текущем семестре.",
            "Bu grubun bu dersten bu dönem defteri yok.",
            "Diese Gruppe hat für dieses Fach kein Journal im laufenden Semester.",
        ),
        "və daha {n} nəfər": t("and {n} more", "и ещё {n}", "ve {n} kişi daha", "und {n} weitere"),
        "Qrupu çıxar": t("Remove the group", "Убрать группу", "Grubu çıkar", "Gruppe entfernen"),
        "Yenə də əlavə et": t("Add anyway", "Всё равно добавить", "Yine de ekle", "Trotzdem hinzufügen"),
        "Məcburi əlavənin səbəbi": t(
            "Reason for adding anyway",
            "Причина принудительного добавления",
            "Zorunlu ekleme nedeni",
            "Grund für das Hinzufügen trotz Warnung",
        ),
        "Məsələn: tələbələr bu fəndən akademik borcu verir": t(
            "E.g. the students are retaking this subject as an academic debt",
            "Например: студенты сдают академическую задолженность по этому предмету",
            "Örneğin: öğrenciler bu dersten akademik borcunu veriyor",
            "Z. B.: Die Studierenden holen dieses Fach als offene Leistung nach",
        ),
        "Ən azı {n} simvol. Səbəb imtahan tarixçəsinə yazılır.": t(
            "At least {n} characters. The reason is saved to the exam history.",
            "Не менее {n} символов. Причина записывается в историю экзамена.",
            "En az {n} karakter. Neden sınav geçmişine yazılır.",
            "Mindestens {n} Zeichen. Der Grund wird im Prüfungsverlauf gespeichert.",
        ),
        "Məcburi əlavə": t("Added anyway", "Добавлено принудительно", "Zorunlu ekleme", "Trotz Warnung hinzugefügt"),
        "Səbəb ən azı %(min)d simvol olmalıdır.": t(
            "The reason must be at least %(min)d characters.",
            "Причина должна содержать не менее %(min)d символов.",
            "Neden en az %(min)d karakter olmalıdır.",
            "Der Grund muss mindestens %(min)d Zeichen lang sein.",
        ),
        "Seçilmiş qrupların bəzi tələbələri bu fənnin cari semestr jurnalında yoxdur. "
        "Qrupu çıxarın və ya səbəb yazaraq məcburi əlavə edin.": t(
            "Some students of the selected groups are not in this subject's current-semester journal. "
            "Remove the group or add it anyway with a reason.",
            "Некоторых студентов выбранных групп нет в журнале этого предмета текущего семестра. "
            "Уберите группу или добавьте её принудительно, указав причину.",
            "Seçilen grupların bazı öğrencileri bu dersin bu dönem defterinde yok. "
            "Grubu çıkarın veya bir neden yazarak zorunlu ekleyin.",
            "Einige Studierende der ausgewählten Gruppen stehen nicht im Journal dieses Fachs für das laufende "
            "Semester. Entfernen Sie die Gruppe oder fügen Sie sie mit Begründung trotzdem hinzu.",
        ),
        "Məcburi əlavə olunmuş qruplar": t(
            "Groups added anyway",
            "Принудительно добавленные группы",
            "Zorunlu eklenen gruplar",
            "Trotz Warnung hinzugefügte Gruppen",
        ),
        "Səbəb": t("Reason", "Причина", "Neden", "Grund"),
        "Fənnin jurnalında olmayan tələbə: %(uncovered)s / %(students)s": t(
            "Students not in the subject journal: %(uncovered)s / %(students)s",
            "Студентов нет в журнале предмета: %(uncovered)s / %(students)s",
            "Dersin defterinde olmayan öğrenci: %(uncovered)s / %(students)s",
            "Studierende nicht im Fachjournal: %(uncovered)s / %(students)s",
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
