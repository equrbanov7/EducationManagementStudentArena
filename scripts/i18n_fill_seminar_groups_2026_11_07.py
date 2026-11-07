#!/usr/bin/env python3
"""Seminar alt qrupları + jurnal bölmələri (sahib 2026-11-07): yalnız yeni msgid-ləri əlavə edir; mövcudlara toxunmur."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return dict(zip(LANGS[1:], (en, ru, tr, de)))


def quote(text):
    return json.dumps(text, ensure_ascii=False)


ENTRIES = {
    "django": {
        "registrar.seminar_groups": {
            "Seminar-%(n)s": t("Seminar group %(n)s", "Семинар-%(n)s", "Seminer-%(n)s", "Seminargruppe %(n)s"),
            "Seminar alt qrupu düzgün seçilməyib.": t(
                "The seminar subgroup is not valid.",
                "Подгруппа семинара выбрана неверно.",
                "Seminer alt grubu geçerli değil.",
                "Die Seminar-Untergruppe ist ungültig.",
            ),
            "Seminar alt qrupu yalnız seminar dərsinə aiddir.": t(
                "A seminar subgroup applies only to a seminar lesson.",
                "Подгруппа семинара относится только к семинарскому занятию.",
                "Seminer alt grubu yalnızca seminer dersine uygulanır.",
                "Eine Seminar-Untergruppe gilt nur für eine Seminarstunde.",
            ),
            "Bu jurnalda belə seminar alt qrupu yoxdur.": t(
                "This journal has no such seminar subgroup.",
                "В этом журнале нет такой подгруппы семинара.",
                "Bu yoklamada böyle bir seminer alt grubu yok.",
                "Dieses Journal hat keine solche Seminar-Untergruppe.",
            ),
            "Bu dərsdə başqa alt qrupun tələbələrinə qeyd yazılıb — alt qrupu dəyişmək olmaz.": t(
                "This lesson has entries for another subgroup's students — the subgroup cannot be changed.",
                "В этом занятии есть записи студентов другой подгруппы — подгруппу изменить нельзя.",
                "Bu derste başka alt grubun öğrencilerine kayıt girilmiş — alt grup değiştirilemez.",
                "Diese Stunde hat Einträge für Studierende einer anderen Untergruppe — die Untergruppe kann nicht geändert werden.",
            ),
            "Bu seminar dərsi yalnız bu alt qrupun tələbələrinindir": t(
                "This seminar lesson belongs only to this subgroup's students",
                "Это семинарское занятие только для студентов этой подгруппы",
                "Bu seminer dersi yalnızca bu alt grubun öğrencilerine aittir",
                "Diese Seminarstunde gehört nur den Studierenden dieser Untergruppe",
            ),
            "Seminar alt qrupu": t(
                "Seminar subgroup", "Подгруппа семинара", "Seminer alt grubu", "Seminar-Untergruppe"
            ),
            "Başqa seminar alt qrupunun dərsi": t(
                "Another seminar subgroup's lesson",
                "Занятие другой подгруппы семинара",
                "Başka bir seminer alt grubunun dersi",
                "Stunde einer anderen Seminar-Untergruppe",
            ),
            "SEMİNAR ALT QRUPU": t(
                "SEMINAR SUBGROUP", "ПОДГРУППА СЕМИНАРА", "SEMİNER ALT GRUBU", "SEMINAR-UNTERGRUPPE"
            ),
            "Bütün qrup": t("Whole group", "Вся группа", "Tüm grup", "Ganze Gruppe"),
            "Alt qrup seçilsə dərs yalnız onun tələbələrinə yazılır; mühazirə bütün qrupladır.": t(
                "If a subgroup is chosen, the lesson is recorded only for its students; lectures are for the whole group.",
                "Если выбрана подгруппа, занятие записывается только её студентам; лекция — для всей группы.",
                "Alt grup seçilirse ders yalnızca onun öğrencilerine yazılır; ders anlatımı tüm grupladır.",
                "Wird eine Untergruppe gewählt, gilt die Stunde nur für ihre Studierenden; Vorlesungen gelten für die ganze Gruppe.",
            ),
        },
        "registrar.model.seminar_group.meta": {
            "seminar alt qrupu": t(
                "seminar subgroup", "подгруппа семинара", "seminer alt grubu", "Seminar-Untergruppe"
            ),
            "seminar alt qrupları": t(
                "seminar subgroups", "подгруппы семинара", "seminer alt grupları", "Seminar-Untergruppen"
            ),
        },
        "registrar.journal_sections": {
            "Hamısı": t("All", "Все", "Tümü", "Alle"),
            "Mühazirə": t("Lecture", "Лекция", "Ders anlatımı", "Vorlesung"),
            "Seminar": t("Seminars", "Семинар", "Seminer", "Seminarteil"),
            "Jurnal bölmələri": t("Journal sections", "Разделы журнала", "Yoklama bölümleri", "Journal-Bereiche"),
        },
    },
}


def fill():
    counts = {}
    for domain, contexts in ENTRIES.items():
        for lang in LANGS:
            path = BASE / "locale" / lang / "LC_MESSAGES" / f"{domain}.po"
            existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
            blocks = []
            for context, messages in contexts.items():
                for msgid, translations in messages.items():
                    if (context, msgid) in existing:
                        continue
                    value = msgid if lang == "az" else translations[lang]
                    lines = ["#, python-format"] if "%" in msgid else []
                    if context:
                        lines.append("msgctxt " + quote(context))
                    lines += ["msgid " + quote(msgid), "msgstr " + quote(value)]
                    blocks.append("\n".join(lines) + "\n")
            if blocks:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(blocks))
            counts[f"{domain}/{lang}"] = len(blocks)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    fill()
