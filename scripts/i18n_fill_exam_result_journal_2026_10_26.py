#!/usr/bin/env python3
"""EMSArena i18n — imtahan nəticəsi jurnala düşəcəkmi: xəbərdarlıqlar + fənn seçicisinin işarəsi (sahib 2026-10-26).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

COVERAGE = "exams.journal_coverage"
PICKER = "exams.subject_picker"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    COVERAGE: {
        "Seçilmiş qruplar üçün bu fənnin cari semestr jurnalı tapılmadı — nəticə jurnala düşməyə bilər. "
        "Fənni və qrupları yoxlayın.": t(
            "No current-semester journal of this subject was found for the selected groups — the result may not "
            "reach the journal. Check the subject and the groups.",
            "Для выбранных групп не найден журнал этого предмета в текущем семестре — результат может не попасть "
            "в журнал. Проверьте предмет и группы.",
            "Seçilen gruplar için bu dersin bu dönemki defteri bulunamadı — sonuç deftere düşmeyebilir. Dersi ve "
            "grupları kontrol edin.",
            "Für die gewählten Gruppen wurde kein Journal dieses Fachs im laufenden Semester gefunden — das "
            "Ergebnis gelangt womöglich nicht ins Journal. Prüfen Sie Fach und Gruppen.",
        ),
        "%(count)s tələbənin bu fənn üzrə cari semestr jurnalı yoxdur — nəticə jurnala düşməyəcək.": t(
            "%(count)s student(s) have no current-semester journal for this subject — the result will not reach "
            "the journal.",
            "Студентов без журнала этого предмета в текущем семестре: %(count)s — результат не попадёт в журнал.",
            "%(count)s öğrencinin bu ders için bu dönemki defteri yok — sonuç deftere düşmeyecek.",
            "%(count)s Studierende haben kein Journal dieses Fachs im laufenden Semester — das Ergebnis gelangt "
            "nicht ins Journal.",
        ),
        "%(count)s tələbə bu fəndən birdən çox jurnaldadır — nəticə imtahanın qrupunun jurnalına "
        "(yoxdursa tələbənin öz qrupunun jurnalına) yazılacaq.": t(
            "%(count)s student(s) are in more than one journal of this subject — the result will be written to "
            "the journal of the exam's group (otherwise to the student's own group's journal).",
            "Студентов в нескольких журналах этого предмета: %(count)s — результат будет записан в журнал "
            "группы экзамена (иначе — в журнал собственной группы студента).",
            "%(count)s öğrenci bu dersin birden fazla defterinde — sonuç sınavın grubunun defterine (yoksa "
            "öğrencinin kendi grubunun defterine) yazılacak.",
            "%(count)s Studierende stehen in mehr als einem Journal dieses Fachs — das Ergebnis wird in das "
            "Journal der Prüfungsgruppe (sonst in das Journal der eigenen Gruppe) geschrieben.",
        ),
    },
    PICKER: {
        "%(count)s jurnal": t(
            "%(count)s journal(s)", "журналов: %(count)s", "%(count)s defter", "%(count)s Journal(e)"
        ),
        "jurnal yoxdur": t("no journal", "нет журнала", "defter yok", "kein Journal"),
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
