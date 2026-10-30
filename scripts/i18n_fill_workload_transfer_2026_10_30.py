#!/usr/bin/env python3
"""Kafedra köçürməsi və ana qrup etiketi: yalnız yeni msgid-ləri əlavə edir.

Baseline və əvvəlki üç source_missing borcu dəyişmir. Mövcud tərcümələrə toxunmur.
"""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return dict(zip(LANGS[1:], (en, ru, tr, de)))


def quote(text):
    return json.dumps(text, ensure_ascii=False)


CHAIR = t("Select a department", "Выберите кафедру", "Bölüm seçin", "Fachbereich auswählen")
ENTRIES = {
    "django": {
        "accounts.groups": {
            "ana qrup: %s": t("parent group: %s", "основная группа: %s", "ana grup: %s", "übergeordnete Gruppe: %s"),
        },
        "accounts.workload": {
            "Başqa kafedraya köçür": t(
                "Transfer to another department",
                "Перенести на другую кафедру",
                "Başka bir bölüme aktar",
                "An einen anderen Fachbereich übertragen",
            ),
            "Hədəf kafedra": t("Destination department", "Целевая кафедра", "Hedef bölüm", "Zielabteilung"),
            "Kafedra seçin": CHAIR,
            "Kafedraya köçür": t(
                "Transfer to department", "Перенести на кафедру", "Bölüme aktar", "An den Fachbereich übertragen"
            ),
            "Köçürmə səbəbi": t(
                "Reason for transfer", "Причина переноса", "Aktarma gerekçesi", "Grund der Übertragung"
            ),
            "Sətir müəllim bölgüsü və saatları ilə köçürülür. Jurnal və qiymətlər saxlanılır. Digər redaktələri əvvəlcə yadda saxlayın.": t(
                "The row is transferred with its teaching assignments and hours. The journal and grades are preserved. Save other changes first.",
                "Строка переносится вместе с распределением преподавателей и часами. Журнал и оценки сохраняются. Сначала сохраните остальные изменения.",
                "Satır, öğretim elemanı dağılımı ve ders saatleriyle birlikte aktarılır. Defter ve notlar korunur. Önce diğer değişiklikleri kaydedin.",
                "Die Zeile wird mit der Lehrkräftezuordnung und den Stunden übertragen. Das Journal und die Noten bleiben erhalten. Speichern Sie zuerst andere Änderungen.",
            ),
        },
    },
    "djangojs": {
        "": {
            "Hədəf kafedranı və köçürmə səbəbini yazın.": t(
                "Select the destination department and enter the reason for transfer.",
                "Выберите целевую кафедру и укажите причину переноса.",
                "Hedef bölümü seçin ve aktarma gerekçesini yazın.",
                "Wählen Sie die Zielabteilung und geben Sie den Grund der Übertragung an.",
            ),
            "Kafedra seçin": CHAIR,
            "Kafedralar yüklənir…": t(
                "Loading departments…", "Загрузка кафедр…", "Bölümler yükleniyor…", "Fachbereiche werden geladen…"
            ),
            "Köçürülür…": t("Transferring…", "Перенос…", "Aktarılıyor…", "Wird übertragen…"),
            "Səlahiyyətiniz daxilində uyğun təsdiqlənmiş kafedra tapşırığı yoxdur.": t(
                "There is no suitable confirmed department task within your access scope.",
                "В пределах ваших полномочий нет подходящего утверждённого задания кафедры.",
                "Yetki alanınızda uygun, onaylanmış bir bölüm görevlendirmesi yok.",
                "In Ihrem Berechtigungsbereich gibt es keinen geeigneten bestätigten Fachbereichsauftrag.",
            ),
            "Yük sətri köçürüldü.": t(
                "The teaching load row was transferred.",
                "Строка учебной нагрузки перенесена.",
                "Ders yükü satırı aktarıldı.",
                "Die Lehrlastzeile wurde übertragen.",
            ),
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
                    lines = ["#, python-format"] if "%s" in msgid else []
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
