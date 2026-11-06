#!/usr/bin/env python3
"""EMSArena i18n — laboratoriya qrupları bir jurnal daxilində (sahib 2026-11-06).

Kontekst: ``registrar.lab_groups`` (``apps/registrar/lab_groups.py``, ``gradebook_lessons``, jurnal qridi və dərs
modalı). ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir. Sonra `.mo`
faylları `msgfmt` ilə yığılır.

İstifadə:  python scripts/i18n_fill_lab_groups_2026_11_06.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ENTRIES = {
    "registrar.lab_groups": {
        "Lab-%(n)s": {
            "az": "Lab-%(n)s",
            "en": "Lab %(n)s",
            "ru": "Лаб-%(n)s",
            "tr": "Lab %(n)s",
            "de": "Labor-%(n)s",
        },
        "Laboratoriya qrupu düzgün seçilməyib.": {
            "az": "Laboratoriya qrupu düzgün seçilməyib.",
            "en": "The lab group is not selected correctly.",
            "ru": "Лабораторная группа выбрана неверно.",
            "tr": "Laboratuvar grubu doğru seçilmedi.",
            "de": "Die Laborgruppe ist nicht korrekt gewählt.",
        },
        "Laboratoriya qrupu yalnız laboratoriya dərsinə aiddir.": {
            "az": "Laboratoriya qrupu yalnız laboratoriya dərsinə aiddir.",
            "en": "A lab group applies only to a lab lesson.",
            "ru": "Лабораторная группа относится только к лабораторному занятию.",
            "tr": "Laboratuvar grubu yalnızca laboratuvar dersine aittir.",
            "de": "Eine Laborgruppe gilt nur für eine Laborstunde.",
        },
        "Bu jurnalda belə laboratoriya qrupu yoxdur.": {
            "az": "Bu jurnalda belə laboratoriya qrupu yoxdur.",
            "en": "This journal has no such lab group.",
            "ru": "В этом журнале нет такой лабораторной группы.",
            "tr": "Bu yoklamada böyle bir laboratuvar grubu yok.",
            "de": "Dieses Journal hat keine solche Laborgruppe.",
        },
        "Bu jurnal laboratoriya qruplarına bölünüb — dərsin qrupunu seçin.": {
            "az": "Bu jurnal laboratoriya qruplarına bölünüb — dərsin qrupunu seçin.",
            "en": "This journal is split into lab groups — choose the lesson's group.",
            "ru": "Этот журнал разделён на лабораторные группы — выберите группу занятия.",
            "tr": "Bu yoklama laboratuvar gruplarına bölünmüş — dersin grubunu seçin.",
            "de": "Dieses Journal ist in Laborgruppen geteilt — wählen Sie die Gruppe der Stunde.",
        },
        "Bu dərsdə başqa laboratoriya qrupunun tələbələrinə qeyd yazılıb — qrupu dəyişmək olmaz.": {
            "az": "Bu dərsdə başqa laboratoriya qrupunun tələbələrinə qeyd yazılıb — qrupu dəyişmək olmaz.",
            "en": "This lesson already has records for students of another lab group — the group cannot be changed.",
            "ru": "На этом занятии уже есть отметки студентов другой лабораторной группы — группу изменить нельзя.",
            "tr": "Bu derste başka bir laboratuvar grubunun öğrencilerine kayıt girilmiş — grup değiştirilemez.",
            "de": "Diese Stunde hat bereits Einträge für Studierende einer anderen Laborgruppe — die Gruppe kann nicht geändert werden.",
        },
        "Bu laboratoriya dərsi yalnız bu qrupun tələbələrinindir": {
            "az": "Bu laboratoriya dərsi yalnız bu qrupun tələbələrinindir",
            "en": "This lab lesson belongs only to this group's students",
            "ru": "Это лабораторное занятие только для студентов этой группы",
            "tr": "Bu laboratuvar dersi yalnızca bu grubun öğrencilerine aittir",
            "de": "Diese Laborstunde gehört nur den Studierenden dieser Gruppe",
        },
        "Laboratoriya qrupu": {
            "az": "Laboratoriya qrupu",
            "en": "Lab group",
            "ru": "Лабораторная группа",
            "tr": "Laboratuvar grubu",
            "de": "Laborgruppe",
        },
        "Tələbə heç bir laboratoriya qrupuna yerləşdirilməyib — qruplu lab dərsləri ona aid deyil. RİM-ə müraciət edin.": {
            "az": "Tələbə heç bir laboratoriya qrupuna yerləşdirilməyib — qruplu lab dərsləri ona aid deyil. RİM-ə müraciət edin.",
            "en": "The student is not placed in any lab group — group lab lessons do not apply to them. Contact the registrar's office.",
            "ru": "Студент не распределён ни в одну лабораторную группу — групповые лабораторные занятия к нему не относятся. Обратитесь в РИМ.",
            "tr": "Öğrenci hiçbir laboratuvar grubuna yerleştirilmemiş — gruplu laboratuvar dersleri ona ait değil. Öğrenci işlerine başvurun.",
            "de": "Der/die Studierende ist keiner Laborgruppe zugeordnet — gruppierte Laborstunden gelten nicht. Wenden Sie sich an das Studienbüro.",
        },
        "Lab qrupu yoxdur": {
            "az": "Lab qrupu yoxdur",
            "en": "No lab group",
            "ru": "Нет лаб. группы",
            "tr": "Lab grubu yok",
            "de": "Keine Laborgruppe",
        },
        "Başqa laboratoriya qrupunun dərsi": {
            "az": "Başqa laboratoriya qrupunun dərsi",
            "en": "Another lab group's lesson",
            "ru": "Занятие другой лабораторной группы",
            "tr": "Başka bir laboratuvar grubunun dersi",
            "de": "Stunde einer anderen Laborgruppe",
        },
        "LABORATORİYA QRUPU": {
            "az": "LABORATORİYA QRUPU",
            "en": "LAB GROUP",
            "ru": "ЛАБОРАТОРНАЯ ГРУППА",
            "tr": "LABORATUVAR GRUBU",
            "de": "LABORGRUPPE",
        },
        "Qrupu seçin…": {
            "az": "Qrupu seçin…",
            "en": "Choose the group…",
            "ru": "Выберите группу…",
            "tr": "Grubu seçin…",
            "de": "Gruppe wählen…",
        },
        "Dərs yalnız bu qrupun tələbələrinə yazılır; mühazirə və seminar bütün qrupladır.": {
            "az": "Dərs yalnız bu qrupun tələbələrinə yazılır; mühazirə və seminar bütün qrupladır.",
            "en": "The lesson is recorded only for this group's students; lectures and seminars are for the whole group.",
            "ru": "Занятие записывается только студентам этой группы; лекции и семинары — для всей группы.",
            "tr": "Ders yalnızca bu grubun öğrencilerine yazılır; ders anlatımı ve seminer tüm grupla yapılır.",
            "de": "Die Stunde wird nur für die Studierenden dieser Gruppe erfasst; Vorlesungen und Seminare sind für die ganze Gruppe.",
        },
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain="django"):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(translations[lang])}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for lang in LOCALES:
        fill(lang)
