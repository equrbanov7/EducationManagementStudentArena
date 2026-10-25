#!/usr/bin/env python3
"""EMSArena i18n — müəllim nəticələri: qrup sütunu + əlavə süzgəclər (2026-10-25).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CTX = "exams.template.teacher_exam_results"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    CTX: {
        "Süzgəcə uyğun": t("Matching filters", "По фильтрам", "Filtreye uyan", "Gefiltert"),
        "Bütün qruplar": t("All groups", "Все группы", "Tüm gruplar", "Alle Gruppen"),
        "{count} qrup seçilib": t(
            "{count} groups selected", "Выбрано групп: {count}", "{count} grup seçildi", "{count} Gruppen ausgewählt"
        ),
        "Alt qruplar": t("Subgroups", "Подгруппы", "Alt gruplar", "Untergruppen"),
        "Ad, istifadəçi adı, e-poçt və ya FİN": t(
            "Name, username, email or PIN",
            "Имя, логин, эл. почта или ФИН",
            "Ad, kullanıcı adı, e-posta veya FİN",
            "Name, Benutzername, E-Mail oder FIN",
        ),
        "Qrupsuz": t("No group", "Без группы", "Grupsuz", "Ohne Gruppe"),
        "Apellyasiya": t("Appeal", "Апелляция", "İtiraz", "Einspruch"),
        "Apellyasiya verib": t("Appeal filed", "Подана апелляция", "İtiraz edildi", "Einspruch eingelegt"),
        "Apellyasiya: baxılır": t(
            "Appeal: under review", "Апелляция: на рассмотрении", "İtiraz: inceleniyor", "Einspruch: in Prüfung"
        ),
        "Apellyasiya: qərar verilib": t(
            "Appeal: decided", "Апелляция: решение принято", "İtiraz: karara bağlandı", "Einspruch: entschieden"
        ),
        "Apellyasiyasız": t("No appeal", "Без апелляции", "İtirazsız", "Ohne Einspruch"),
        "Gün": t("Day", "День", "Tarih", "Tag"),
        "Bütün günlər": t("All days", "Все дни", "Tüm günler", "Alle Tage"),
        "Zal": t("Room", "Зал", "Salon", "Raum"),
        "Bütün zallar": t("All rooms", "Все залы", "Tüm salonlar", "Alle Räume"),
        "Zalsız (onlayn)": t("No room (online)", "Без зала (онлайн)", "Salonsuz (çevrim içi)", "Ohne Raum (online)"),
        "Bal: -dan": t("Score: from", "Балл: от", "Puan: en az", "Punkte: ab"),
        "Bal: -dək": t("Score: to", "Балл: до", "Puan: en çok", "Punkte: bis"),
        "Bal aralığı": t("Score range", "Диапазон баллов", "Puan aralığı", "Punktebereich"),
        "Sətir": t("Rows", "Строк", "Satır", "Zeilen"),
        "Ana qrup": t("Parent group", "Основная группа", "Ana grup", "Hauptgruppe"),
        "ana qrup": t("parent group", "основная группа", "ana grup", "Hauptgruppe"),
        "qeyd aktiv deyil": t("record inactive", "запись неактивна", "kayıt aktif değil", "Eintrag inaktiv"),
        "Tələbənin akademik qeydində qrup yoxdur": t(
            "The student's academic record has no group",
            "В академической записи студента нет группы",
            "Öğrencinin akademik kaydında grup yok",
            "Im Studiendatensatz ist keine Gruppe hinterlegt",
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
