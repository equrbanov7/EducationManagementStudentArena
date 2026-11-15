#!/usr/bin/env python3
"""«Passiv» dərs (sahib 2026-11-14): yalnız yeni msgid-ləri əlavə edir; mövcudlara toxunmur."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return dict(zip(LANGS[1:], (en, ru, tr, de)))


def quote(text):
    return json.dumps(text, ensure_ascii=False)


PASSIVE = t("Passive", "Пассивный", "Pasif", "Passivstunde")  # de: «Passiv» = az msgid (identity borcu olmasın)

ENTRIES = {
    "django": {
        "registrar.passive_lessons": {
            "Passiv": PASSIVE,
            "Passiv: %(hours)s saat": t(
                "Passive: %(hours)s h", "Пассивные: %(hours)s ч", "Pasif: %(hours)s saat", "Passiv: %(hours)s Std."
            ),
            "keçirilmiş saata daxil deyil": t(
                "not counted as held hours",
                "не входит в проведённые часы",
                "yapılan saate dahil değil",
                "zählt nicht als gehaltene Stunden",
            ),
            "«Passiv» — saat yazılır, amma keçirilmiş saata, həddə və dərs yükünə daxil deyil; xana yazılmır.": t(
                "«Passive» — the hours are recorded but not counted as held hours, in the hour cap or in the "
                "teaching load; no marks are entered.",
                "«Пассивный» — часы записываются, но не входят в проведённые часы, лимит и учебную нагрузку; "
                "отметки не ставятся.",
                "«Pasif» — saat kaydedilir ama yapılan saate, sınıra ve ders yüküne dahil değildir; not girilmez.",
                "«Passiv» — die Stunden werden erfasst, zählen aber nicht als gehaltene Stunden, nicht zum "
                "Stundenlimit und nicht zur Lehrbelastung; es werden keine Einträge gemacht.",
            ),
            "Passiv dərs — müəllimin keçirilmiş saatına, həddə və dərs yükünə daxil deyil; xana yazılmır": t(
                "Passive lesson — not counted in the teacher's held hours, the hour cap or the teaching load; "
                "no marks are entered",
                "Пассивное занятие — не входит в проведённые часы преподавателя, лимит и учебную нагрузку; "
                "отметки не ставятся",
                "Pasif ders — öğretmenin yaptığı saate, sınıra ve ders yüküne dahil değil; not girilmez",
                "Passive Lehrveranstaltung — zählt nicht zu den gehaltenen Stunden, zum Stundenlimit oder zur "
                "Lehrbelastung; keine Einträge",
            ),
            "Passiv dərs — davamiyyət və bal yazılmır": t(
                "Passive lesson — no attendance or score is entered",
                "Пассивное занятие — посещаемость и баллы не ставятся",
                "Pasif ders — devam ve puan girilmez",
                "Passive Lehrveranstaltung — keine Anwesenheit und keine Punkte",
            ),
            "Passiv dərslərin saatı — keçirilmiş saata, dərs saatı həddinə və dərs yükünə daxil deyil": t(
                "Hours of passive lessons — not counted in held hours, the hour cap or the teaching load",
                "Часы пассивных занятий — не входят в проведённые часы, лимит часов и учебную нагрузку",
                "Pasif derslerin saati — yapılan saate, saat sınırına ve ders yüküne dahil değil",
                "Stunden passiver Lehrveranstaltungen — zählen nicht zu gehaltenen Stunden, Stundenlimit oder "
                "Lehrbelastung",
            ),
            "Bu dərsdə qeyd (i/e, q/b, bal) var — passiv edilə bilməz. Əvvəl qeydləri təmizləyin.": t(
                "This lesson already has marks (present, absent, score) — it cannot be made passive. Clear the "
                "marks first.",
                "В этом занятии есть отметки (присутствие, пропуск, балл) — его нельзя сделать пассивным. "
                "Сначала удалите отметки.",
                "Bu derste not var (var, yok, puan) — pasif yapılamaz. Önce notları temizleyin.",
                "Diese Lehrveranstaltung hat bereits Einträge (anwesend, abwesend, Punkte) — sie kann nicht passiv "
                "werden. Entfernen Sie zuerst die Einträge.",
            ),
            "Bu jurnalda passiv dərs açmaq olmaz (dil səviyyə qrupunun saatı sabitdir).": t(
                "Passive lessons cannot be added to this journal (the language level group has fixed hours).",
                "В этом журнале нельзя создать пассивное занятие (часы языковой группы фиксированы).",
                "Bu yoklamada pasif ders açılamaz (dil seviyesi grubunun saati sabittir).",
                "In diesem Journal sind keine passiven Lehrveranstaltungen möglich (die Sprachniveaugruppe hat "
                "feste Stunden).",
            ),
            "Dərsin «Passiv» seçimi yalnız redaktə pəncərəsində dəyişir — sənədli düzəlişdə dəyişmir.": t(
                "The lesson's «Passive» choice can only be changed within the edit window — not through a "
                "documented correction.",
                "Отметку «Пассивный» можно изменить только в окне редактирования — не через документированное "
                "исправление.",
                "Dersin «Pasif» seçimi yalnızca düzenleme süresinde değişir — belgeli düzeltmede değişmez.",
                "Die Auswahl «Passiv» kann nur im Bearbeitungsfenster geändert werden — nicht über eine "
                "dokumentierte Korrektur.",
            ),
        },
        "registrar.lessons_log": {
            "Passiv": PASSIVE,
            "Passiv dərs": t("Passive lesson", "Пассивное занятие", "Pasif ders", "Passive Lehrveranstaltung"),
            "Bəli": t("Yes", "Да", "Evet", "Ja"),
            "Passiv saat (cəmə daxil deyil)": t(
                "Passive hours (not in the total)",
                "Пассивные часы (не входят в итог)",
                "Pasif saat (toplama dahil değil)",
                "Passive Stunden (nicht in der Summe)",
            ),
        },
        "accounts.lessons_log": {
            "Passiv": PASSIVE,
            "Passiv: %(n)s saat": t(
                "Passive: %(n)s h", "Пассивные: %(n)s ч", "Pasif: %(n)s saat", "Passiv: %(n)s Std."
            ),
            "Passiv dərs — cəmə daxil deyil": t(
                "Passive lesson — not in the total",
                "Пассивное занятие — не входит в итог",
                "Pasif ders — toplama dahil değil",
                "Passive Lehrveranstaltung — nicht in der Summe",
            ),
            "Passiv dərs — müəllimin keçirilmiş saatına daxil deyil": t(
                "Passive lesson — not counted in the teacher's held hours",
                "Пассивное занятие — не входит в проведённые часы преподавателя",
                "Pasif ders — öğretmenin yaptığı saate dahil değil",
                "Passive Lehrveranstaltung — zählt nicht zu den gehaltenen Stunden",
            ),
            "Passiv dərslər cəmə daxil deyil": t(
                "Passive lessons are not in the total",
                "Пассивные занятия не входят в итог",
                "Pasif dersler toplama dahil değil",
                "Passive Lehrveranstaltungen sind nicht in der Summe",
            ),
            "akademik saat cəmi · passiv %(hours)s saat ayrıca": t(
                "total academic hours · passive %(hours)s h separately",
                "сумма академических часов · пассивные %(hours)s ч отдельно",
                "akademik saat toplamı · pasif %(hours)s saat ayrıca",
                "Summe der akademischen Stunden · passiv %(hours)s Std. gesondert",
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
