#!/usr/bin/env python3
"""EMSArena i18n — yazılı / kodlaşdırma midtermi də jurnala avtomatik (sahib 2026-10-24).

Sehrbazın «nəticə jurnala avtomatik yazılacaq» qeydi, yoxlama ekranının qeydi və jurnalın «İmtahandan
avtomatik» izahı. msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra .mo polib ilə yığılır (msgfmt olmayan mühit üçün; ``compilemessages -i .claude -i venv`` də olar).
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

MODAL = "exams.template.create_exam_modal_form"
GRADING = "exams.teacher.grading"
JOURNAL = "registrar.journal"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


AZ_OVERRIDES = {}

ENTRIES = {
    MODAL: {
        "Bu midterm imtahanının nəticəsi tələbə imtahanı bitirən kimi seçilmiş fənnin qrup jurnallarına "
        "(Midterm /30) avtomatik yazılacaq.": t(
            "The result of this midterm will be written automatically to the group journals of the selected "
            "subject (Midterm /30) as soon as the student finishes the exam.",
            "Результат этого промежуточного экзамена будет автоматически записан в журналы групп выбранного "
            "предмета (Midterm /30) сразу после того, как студент завершит экзамен.",
            "Bu ara sınavın sonucu, öğrenci sınavı bitirir bitirmez seçilen dersin grup defterlerine "
            "(Midterm /30) otomatik olarak yazılacaktır.",
            "Das Ergebnis dieser Zwischenprüfung wird automatisch in die Gruppenjournale des ausgewählten "
            "Fachs (Midterm /30) eingetragen, sobald der Studierende die Prüfung beendet.",
        ),
        "Bu midterm imtahanının nəticəsi yoxlanıldıqdan sonra seçilmiş fənnin qrup jurnallarına "
        "(Midterm /30) avtomatik yazılacaq.": t(
            "The result of this midterm will be written automatically to the group journals of the selected "
            "subject (Midterm /30) once it has been graded.",
            "Результат этого промежуточного экзамена будет автоматически записан в журналы групп выбранного "
            "предмета (Midterm /30) после проверки.",
            "Bu ara sınavın sonucu, değerlendirildikten sonra seçilen dersin grup defterlerine (Midterm /30) "
            "otomatik olarak yazılacaktır.",
            "Das Ergebnis dieser Zwischenprüfung wird nach der Bewertung automatisch in die Gruppenjournale "
            "des ausgewählten Fachs (Midterm /30) eingetragen.",
        ),
    },
    GRADING: {
        "Bal jurnala avtomatik yazılır": t(
            "The score is written to the journal automatically",
            "Балл автоматически записывается в журнал",
            "Puan deftere otomatik olarak yazılır",
            "Die Punktzahl wird automatisch ins Journal eingetragen",
        ),
        "Bu midterm imtahanıdır. Bütün suallar qiymətləndirilib yadda saxlananda bal fənnin jurnalına "
        "(Midterm) avtomatik yazılır — jurnalda əl ilə yazmaq lazım deyil.": t(
            "This is a midterm exam. When all questions are graded and saved, the score is written "
            "automatically to the subject journal (Midterm) — there is no need to enter it in the journal "
            "manually.",
            "Это промежуточный экзамен. Когда все вопросы оценены и сохранены, балл автоматически "
            "записывается в журнал предмета (Midterm) — вводить его в журнал вручную не нужно.",
            "Bu bir ara sınavdır. Tüm sorular puanlanıp kaydedildiğinde puan dersin defterine (Midterm) "
            "otomatik olarak yazılır — deftere elle girmeye gerek yoktur.",
            "Dies ist eine Zwischenprüfung. Sobald alle Fragen bewertet und gespeichert sind, wird die "
            "Punktzahl automatisch ins Fachjournal (Midterm) eingetragen — eine manuelle Eingabe im Journal "
            "ist nicht nötig.",
        ),
        "Bu midterm imtahanıdır. Nəticə hazırda tələbədən gizlədilib — saxladığınız bal fənnin jurnalına "
        "(Midterm) nəticə tələbəyə açılanda avtomatik yazılacaq.": t(
            "This is a midterm exam. The result is currently hidden from the student — the score you save "
            "will be written automatically to the subject journal (Midterm) when the result is released to "
            "the student.",
            "Это промежуточный экзамен. Сейчас результат скрыт от студента — сохранённый вами балл будет "
            "автоматически записан в журнал предмета (Midterm), когда результат откроют студенту.",
            "Bu bir ara sınavdır. Sonuç şu anda öğrenciden gizlenmiştir — kaydettiğiniz puan, sonuç öğrenciye "
            "açıldığında dersin defterine (Midterm) otomatik olarak yazılacaktır.",
            "Dies ist eine Zwischenprüfung. Das Ergebnis ist derzeit für den Studierenden verborgen — die "
            "gespeicherte Punktzahl wird automatisch ins Fachjournal (Midterm) eingetragen, sobald das "
            "Ergebnis freigegeben wird.",
        ),
    },
    JOURNAL: {
        "İmtahan Mərkəzində keçirilən midterm balı imtahandan avtomatik yazılır (test — tələbə bitirən kimi, "
        "yazılı / praktiki — yoxlanıldıqdan sonra) və burada əl ilə dəyişdirilmir. Düzəliş yalnız apellyasiya "
        "və ya sənədli düzəliş ilə mümkündür.": t(
            "The midterm score of an exam held in the Exam Center is written automatically from the exam "
            "(test — as soon as the student finishes, written / practical — after grading) and cannot be "
            "changed manually here. It can be corrected only through an appeal or a documented correction.",
            "Балл промежуточного экзамена, проведённого в Экзаменационном центре, записывается автоматически "
            "(тест — сразу после завершения студентом, письменный / практический — после проверки) и здесь "
            "вручную не изменяется. Исправление возможно только через апелляцию или документальную поправку.",
            "Sınav Merkezinde yapılan ara sınav puanı sınavdan otomatik olarak yazılır (test — öğrenci bitirir "
            "bitirmez, yazılı / uygulamalı — değerlendirildikten sonra) ve burada elle değiştirilemez. "
            "Düzeltme yalnızca itiraz veya belgeli düzeltme ile mümkündür.",
            "Die Zwischenprüfungspunktzahl einer im Prüfungszentrum durchgeführten Prüfung wird automatisch "
            "übernommen (Test — sobald der Studierende fertig ist, schriftlich / praktisch — nach der "
            "Bewertung) und kann hier nicht manuell geändert werden. Eine Korrektur ist nur über einen "
            "Widerspruch oder eine dokumentierte Korrektur möglich.",
        ),
        "imtahandan avtomatik": t(
            "automatically from the exam",
            "автоматически из экзамена",
            "sınavdan otomatik",
            "automatisch aus der Prüfung",
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
    return added


def compile_mo(lang):
    path = po_path(lang)
    polib.pofile(path).save_as_mofile(path[:-3] + ".mo")


if __name__ == "__main__":
    for locale in LOCALES:
        if fill(locale):
            compile_mo(locale)
