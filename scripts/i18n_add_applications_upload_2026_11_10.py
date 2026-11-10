#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-10: müraciət sənədləri 50 MB + PowerPoint, «MIME» sözü istifadəçi mətnindən çıxdı
(``core/upload_security.py``), prorektor seçimi, mövzu ehtiyat mənbəyi və səviyyə qrupları (yalnız baxış). Beş kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_applications_upload_2026_11_10.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")

_U = "upload.security.error"
_A = "applications"

STRINGS = {
    (_U, "Faylın tipi müəyyən edilə bilmədi."): (
        "The file type could not be determined.",
        "Не удалось определить тип файла.",
        "Dosya türü belirlenemedi.",
        "Der Dateityp konnte nicht ermittelt werden.",
    ),
    (_U, "Bu fayl tipi dəstəklənmir."): (
        "This file type is not supported.",
        "Этот тип файла не поддерживается.",
        "Bu dosya türü desteklenmiyor.",
        "Dieser Dateityp wird nicht unterstützt.",
    ),
    (_A, "Fayl seç — PDF, şəkil, Word, Excel, PowerPoint və ya ZIP · maks. %(mb)s MB · ən çox %(n)s fayl"): (
        "Choose a file — PDF, image, Word, Excel, PowerPoint or ZIP · max. %(mb)s MB · up to %(n)s files",
        "Выберите файл — PDF, изображение, Word, Excel, PowerPoint или ZIP · макс. %(mb)s МБ · до %(n)s файлов",
        "Dosya seç — PDF, görsel, Word, Excel, PowerPoint veya ZIP · en fazla %(mb)s MB · en çok %(n)s dosya",
        "Datei wählen — PDF, Bild, Word, Excel, PowerPoint oder ZIP · max. %(mb)s MB · bis zu %(n)s Dateien",
    ),
    (
        "registrar.journal_topics",
        "Təsdiqlənmiş sillabus hələ yoxdur — mövzular sillabus qaralamasından və ya eyni fənnin təsdiqlənmiş "
        "sillabusundan götürülüb.",
    ): (
        "There is no approved syllabus yet — topics are taken from the syllabus draft or from an approved "
        "syllabus of the same subject.",
        "Утверждённого силлабуса ещё нет — темы взяты из черновика силлабуса или из утверждённого силлабуса "
        "того же предмета.",
        "Henüz onaylanmış bir müfredat yok — konular müfredat taslağından veya aynı dersin onaylanmış "
        "müfredatından alındı.",
        "Es gibt noch keinen genehmigten Lehrplan — die Themen stammen aus dem Lehrplanentwurf oder aus einem "
        "genehmigten Lehrplan desselben Fachs.",
    ),
    ("registrar.language_cohort", "Siyahıya bax"): ("View list", "Посмотреть список", "Listeye bak", "Liste ansehen"),
    ("registrar.language_cohort", "Səviyyə qrupları"): (
        "Level groups",
        "Уровневые группы",
        "Seviye grupları",
        "Niveaugruppen",
    ),
    (
        "registrar.language_cohort",
        "Səviyyə qrupunun tələbə tərkibini koordinator / dekanlıq idarə edir. Qrupları və jurnalları yalnız görə "
        "bilərsiniz.",
    ): (
        "The coordinator / dean's office manages the students of a level group. You can only view groups and journals.",
        "Состав студентов уровневой группы ведёт координатор / деканат. Вы можете только просматривать группы и журналы.",
        "Seviye grubunun öğrenci listesini koordinatör / dekanlık yönetir. Grupları ve yoklama defterlerini yalnızca "
        "görüntüleyebilirsiniz.",
        "Die Studierenden einer Niveaugruppe verwaltet die Koordination / das Dekanat. Sie können Gruppen und "
        "Journale nur ansehen.",
    ),
    (
        "registrar.language_cohort",
        "Səviyyə qrupunun tələbə tərkibini koordinator / dekanlıq idarə edir. Siz siyahıya yalnız baxa bilərsiniz.",
    ): (
        "The coordinator / dean's office manages the students of a level group. You can only view the list.",
        "Состав студентов уровневой группы ведёт координатор / деканат. Вы можете только просматривать список.",
        "Seviye grubunun öğrenci listesini koordinatör / dekanlık yönetir. Listeyi yalnızca görüntüleyebilirsiniz.",
        "Die Studierenden einer Niveaugruppe verwaltet die Koordination / das Dekanat. Sie können die Liste nur ansehen.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            entry = polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr)
            if "%(" in msgid:
                entry.flags.append("python-format")
            po.append(entry)
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
