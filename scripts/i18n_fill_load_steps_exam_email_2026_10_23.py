#!/usr/bin/env python3
"""EMSArena i18n — «Dərs yükü faylı» addımları + final/midterm girişində e-poçt (2026-10-23, ikinci dalğa).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

WL = "accounts.workload_load"
FE = "exams.template.final_entry"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "accounts.syllabus": {"Sətri sil": t("Delete row", "Удалить строку", "Satırı sil", "Zeile löschen")},
    "accounts.workload": {
        "fənn, qrup və ya müəllim": t(
            "subject, group or teacher",
            "дисциплина, группа или преподаватель",
            "ders, grup veya öğretim elemanı",
            "Fach, Gruppe oder Lehrkraft",
        )
    },
    WL: {
        "Bir sətir — bir müəllimin bir fənni: müəllim, qrup(lar), fənn, kredit, I və II semestrin saatları. Kafedranın Word «Forma 1» faylı da olar — onda bu addımı keçin.": t(
            "One row — one subject of one teacher: teacher, group(s), subject, credits, hours of semesters I and II. The chair's Word “Form 1” file also works — then skip this step.",
            "Одна строка — одна дисциплина одного преподавателя: преподаватель, группа(ы), дисциплина, кредиты, часы I и II семестров. Подойдёт и Word-файл кафедры «Форма 1» — тогда пропустите этот шаг.",
            "Bir satır — bir öğretim elemanının bir dersi: öğretim elemanı, grup(lar), ders, kredi, I ve II dönem saatleri. Bölümün Word “Form 1” dosyası da olur — o zaman bu adımı atlayın.",
            "Eine Zeile — ein Fach einer Lehrkraft: Lehrkraft, Gruppe(n), Fach, Credits, Stunden des I. und II. Semesters. Auch die Word-Datei „Formular 1“ des Lehrstuhls geht — dann diesen Schritt überspringen.",
        ),
        "Doldurulmuş faylı seçin": t(
            "Choose the filled-in file",
            "Выберите заполненный файл",
            "Doldurulmuş dosyayı seçin",
            "Ausgefüllte Datei auswählen",
        ),
        "Excel şablonunu yükləyin və doldurun": t(
            "Download and fill in the Excel template",
            "Скачайте и заполните шаблон Excel",
            "Excel şablonunu indirip doldurun",
            "Excel-Vorlage herunterladen und ausfüllen",
        ),
        "Kafedra və ya fakültə adı ilə axtar…": t(
            "Search by chair or faculty name…",
            "Поиск по кафедре или факультету…",
            "Bölüm veya fakülte adıyla ara…",
            "Nach Lehrstuhl oder Fakultät suchen…",
        ),
        "Kafedranı seçin": t("Choose the chair", "Выберите кафедру", "Bölümü seçin", "Lehrstuhl auswählen"),
        "Siyahıda kafedra adı və fakültəsi göstərilir — yazmağa başlayın, axtarış süzür.": t(
            "The list shows the chair and its faculty — start typing to filter.",
            "В списке указаны кафедра и факультет — начните вводить, поиск отфильтрует.",
            "Listede bölüm ve fakültesi gösterilir — yazmaya başlayın, arama süzer.",
            "Die Liste zeigt Lehrstuhl und Fakultät — tippen Sie, um zu filtern.",
        ),
        "Yoxlanılır… (bir neçə dəqiqə çəkə bilər)": t(
            "Checking… (may take a few minutes)",
            "Проверка… (может занять несколько минут)",
            "Kontrol ediliyor… (birkaç dakika sürebilir)",
            "Wird geprüft… (kann einige Minuten dauern)",
        ),
        "Yoxlayın — hələ heç nə yazılmır": t(
            "Check — nothing is written yet",
            "Проверьте — пока ничего не записывается",
            "Kontrol edin — henüz hiçbir şey yazılmaz",
            "Prüfen — noch wird nichts geschrieben",
        ),
    },
    FE: {
        "İstifadəçi adı və ya e-poçt": t(
            "Username or e-mail",
            "Имя пользователя или e-mail",
            "Kullanıcı adı veya e-posta",
            "Benutzername oder E-Mail",
        ),
        "İstifadəçi adınızı (və ya e-poçtunuzu) və şəxsi imtahan PIN-inizi daxil edin": t(
            "Enter your username (or e-mail) and personal exam PIN",
            "Введите имя пользователя (или e-mail) и личный PIN экзамена",
            "Kullanıcı adınızı (veya e-postanızı) ve kişisel sınav PIN'inizi girin",
            "Geben Sie Ihren Benutzernamen (oder Ihre E-Mail) und Ihre persönliche Prüfungs-PIN ein",
        ),
        "istifadəçi adı və ya e-poçt ünvanı": t(
            "username or e-mail address",
            "имя пользователя или адрес e-mail",
            "kullanıcı adı veya e-posta adresi",
            "Benutzername oder E-Mail-Adresse",
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
