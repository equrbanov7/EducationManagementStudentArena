#!/usr/bin/env python3
"""EMSArena i18n — «Kafedra materialları» (tyutor / laborant, yalnız-oxu) + açar etiketi, 2026-10-27.

msgid AZ cümlədir → az msgstr = msgid. Yalnız ``django`` domeni (kontekstlə). Mövcud açarlar atlanır
(idempotent); sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

UI = "subject_folder.ui"
SIDEBAR = "profile.sidebar"
PERM = "organizations.permission.label"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


UNIT_MATERIALS = t("Department materials", "Материалы кафедры", "Bölüm materyalleri", "Lehrstuhlmaterialien")

ENTRIES = {
    UI: {
        "Kafedra materialları": UNIT_MATERIALS,
        "Struktur əhatəniz təyin edilməyib": t(
            "Your structural scope is not set",
            "Ваша структурная область не задана",
            "Yapısal kapsamınız tanımlanmamış",
            "Ihr struktureller Bereich ist nicht festgelegt",
        ),
        "Kafedra materialları üzvlüyünüzün bölməsinə (kafedra / fakültə) görə göstərilir — administratora müraciət edin.": t(
            "Department materials are shown for the unit of your membership (department / faculty) — "
            "contact the administrator.",
            "Материалы кафедры показываются по подразделению вашего членства (кафедра / факультет) — "
            "обратитесь к администратору.",
            "Bölüm materyalleri üyeliğinizin birimine (bölüm / fakülte) göre gösterilir — yöneticiye başvurun.",
            "Lehrstuhlmaterialien werden nach der Einheit Ihrer Mitgliedschaft (Lehrstuhl / Fakultät) angezeigt — "
            "wenden Sie sich an den Administrator.",
        ),
        "Qovluq əhatənizdə deyil və ya hələ qaralamadır.": t(
            "The folder is outside your scope or is still a draft.",
            "Папка вне вашей области или ещё является черновиком.",
            "Klasör kapsamınızın dışında veya hâlâ taslak.",
            "Der Ordner liegt außerhalb Ihres Bereichs oder ist noch ein Entwurf.",
        ),
        "Kafedranızın müəllimlərinin fənn qovluqlarında dərc etdiyi tədris materialları — yalnız baxış və endirmə.": t(
            "Teaching materials published by your department's teachers in their subject folders — view and "
            "download only.",
            "Учебные материалы, опубликованные преподавателями вашей кафедры в папках дисциплин, — только "
            "просмотр и скачивание.",
            "Bölümünüzün öğretmenlerinin ders klasörlerinde yayımladığı öğretim materyalleri — yalnızca "
            "görüntüleme ve indirme.",
            "Von den Lehrkräften Ihres Lehrstuhls in den Fachordnern veröffentlichte Lehrmaterialien — nur "
            "Ansicht und Download.",
        ),
        "İlk %(n)s qovluq göstərilir — süzgəc və ya axtarışla daraldın.": t(
            "The first %(n)s folders are shown — narrow down with filters or search.",
            "Показаны первые %(n)s папок — сузьте фильтром или поиском.",
            "İlk %(n)s klasör gösteriliyor — filtre veya aramayla daraltın.",
            "Die ersten %(n)s Ordner werden angezeigt — mit Filtern oder Suche eingrenzen.",
        ),
        "Hələ dərc edilmiş fənn qovluğu yoxdur": t(
            "No published subject folders yet",
            "Опубликованных папок дисциплин пока нет",
            "Henüz yayımlanmış ders klasörü yok",
            "Noch keine veröffentlichten Fachordner",
        ),
        "Kafedranın müəllimləri fənn qovluğunu qruplara təyin edəndə materiallar burada görünəcək.": t(
            "Materials will appear here once the department's teachers assign subject folders to groups.",
            "Материалы появятся здесь, когда преподаватели кафедры назначат папки дисциплин группам.",
            "Bölüm öğretmenleri ders klasörlerini gruplara atadığında materyaller burada görünecek.",
            "Die Materialien erscheinen hier, sobald die Lehrkräfte des Lehrstuhls Fachordner Gruppen zuweisen.",
        ),
        "Yalnız baxış": t("View only", "Только просмотр", "Yalnızca görüntüleme", "Nur Ansicht"),
        "Qovluqda hələ dərc edilmiş material yoxdur": t(
            "No published materials in the folder yet",
            "В папке пока нет опубликованных материалов",
            "Klasörde henüz yayımlanmış materyal yok",
            "Im Ordner gibt es noch keine veröffentlichten Materialien",
        ),
        "Fənn, qovluq və ya müəllim…": t(
            "Subject, folder or teacher…",
            "Дисциплина, папка или преподаватель…",
            "Ders, klasör veya öğretmen…",
            "Fach, Ordner oder Lehrkraft…",
        ),
        "MATERİAL": t("MATERIALS", "МАТЕРИАЛЫ", "MATERYAL", "MATERIALIEN"),
        "dərc edilmiş": t("published", "опубликовано", "yayımlanmış", "veröffentlicht"),
    },
    SIDEBAR: {
        "Kafedra materialları": UNIT_MATERIALS,
    },
    PERM: {
        "Kafedranın fənn qovluqlarına (dərs materiallarına) baxmaq": t(
            "View the department's subject folders (teaching materials)",
            "Просмотр папок дисциплин кафедры (учебных материалов)",
            "Bölümün ders klasörlerini (öğretim materyallerini) görüntüleme",
            "Fachordner des Lehrstuhls (Lehrmaterialien) ansehen",
        ),
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    blocks = []
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
    if blocks:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.rstrip("\n") + "\n\n" + "\n".join(blocks))
    print(f"{lang}: +{len(blocks)} django")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
