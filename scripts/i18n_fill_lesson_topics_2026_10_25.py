#!/usr/bin/env python3
"""EMSArena i18n — jurnal dərsinin mövzusu ↔ sillabusun həftəlik plan sətri (sahib 2026-10-25).

Dərs modalında planda olmayan mövzu üçün sərbəst mətn və «Sillabusa bax» panelində hər plan sətrinin
«Keçilib / Keçilməyib» statusu.

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

JT = "registrar.journal_topics"
SP = "registrar.syllabus_progress"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    JT: {
        "…və ya planda olmayan mövzunu özünüz yazın": t(
            "…or type a topic that is not in the plan",
            "…или впишите тему, которой нет в плане",
            "…veya planda olmayan konuyu kendiniz yazın",
            "…oder geben Sie ein Thema ein, das nicht im Plan steht",
        ),
        "növbəti mövzu": t("next topic", "следующая тема", "sıradaki konu", "nächstes Thema"),
        "Mövzu adı ilə axtar…": t(
            "Search by topic name…", "Поиск по названию темы…", "Konu adına göre ara…", "Nach Themenname suchen…"
        ),
        "Uyğun mövzu tapılmadı": t(
            "No matching topic found",
            "Подходящая тема не найдена",
            "Eşleşen konu bulunamadı",
            "Kein passendes Thema gefunden",
        ),
        "Planda olmayan mövzu": t(
            "Topic not in the plan", "Тема вне плана", "Planda olmayan konu", "Thema außerhalb des Plans"
        ),
        "Plandan seçilən mövzu sillabusun həftəlik planında «keçilib» kimi işarələnir.": t(
            "A topic chosen from the plan is marked as «covered» in the syllabus weekly plan.",
            "Тема, выбранная из плана, отмечается в недельном плане силлабуса как «пройдена».",
            "Plandan seçilen konu, izlencenin haftalık planında «işlendi» olarak işaretlenir.",
            "Ein aus dem Plan gewähltes Thema wird im Wochenplan des Syllabus als «behandelt» markiert.",
        ),
    },
    SP: {
        "Keçilib": t("Covered", "Пройдена", "İşlendi", "Behandelt"),
        "Keçilməyib": t("Not covered", "Не пройдена", "İşlenmedi", "Nicht behandelt"),
        "Planlaşdırılıb": t("Scheduled", "Запланирована", "Planlandı", "Geplant"),
        "{covered} / {total} mövzu keçilib": t(
            "{covered} / {total} topics covered",
            "Пройдено тем: {covered} / {total}",
            "{covered} / {total} konu işlendi",
            "{covered} / {total} Themen behandelt",
        ),
        "Mövzuların keçilməsi (jurnal üzrə)": t(
            "Topic coverage (from the journal)",
            "Прохождение тем (по журналу)",
            "Konuların işlenmesi (deftere göre)",
            "Behandlung der Themen (laut Journal)",
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
