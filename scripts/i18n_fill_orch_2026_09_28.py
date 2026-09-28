#!/usr/bin/env python3
"""EMSArena i18n — Audit 2026-09-28 FQ-I18N-4: gettext-ə alınmış sərt Az mətnlər.

Kontekstlər: ``registrar.transfer`` (qrup köçürməsi xətaları), ``exams.form.question``,
``accounts.people.action``. ``makemessages`` İŞLƏDİLMİR; idempotentdir, sonra ``.mo`` qurulur.
İstifadə:  python scripts/i18n_fill_orch_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

ENTRIES = {
    "registrar.transfer": {
        "Yeni qrup tələbənin təşkilatına aid deyil.": {
            "az": "Yeni qrup tələbənin təşkilatına aid deyil.",
            "en": "The new group does not belong to the student's organization.",
            "ru": "Новая группа не принадлежит организации студента.",
            "tr": "Yeni grup öğrencinin kurumuna ait değil.",
        },
        "Yeni struktur vahidi akademik qrup olmalıdır.": {
            "az": "Yeni struktur vahidi akademik qrup olmalıdır.",
            "en": "The new unit must be an academic group.",
            "ru": "Новое подразделение должно быть академической группой.",
            "tr": "Yeni birim bir akademik grup olmalıdır.",
        },
        "Akademik dövr tələbənin təşkilatına aid deyil.": {
            "az": "Akademik dövr tələbənin təşkilatına aid deyil.",
            "en": "The academic period does not belong to the student's organization.",
            "ru": "Учебный период не принадлежит организации студента.",
            "tr": "Akademik dönem öğrencinin kurumuna ait değil.",
        },
        "Aktiv cari akademik dövr qrup köçürməsində göstərilməlidir.": {
            "az": "Aktiv cari akademik dövr qrup köçürməsində göstərilməlidir.",
            "en": "The active current academic period must be specified for a group transfer.",
            "ru": "Для перевода в группу необходимо указать активный текущий учебный период.",
            "tr": "Grup nakli için etkin güncel akademik dönem belirtilmelidir.",
        },
        "Qrup köçürməsi yalnız aktiv cari akademik dövr üçün aparıla bilər.": {
            "az": "Qrup köçürməsi yalnız aktiv cari akademik dövr üçün aparıla bilər.",
            "en": "A group transfer can only be made for the active current academic period.",
            "ru": "Перевод в группу возможен только для активного текущего учебного периода.",
            "tr": "Grup nakli yalnızca etkin güncel akademik dönem için yapılabilir.",
        },
    },
    "exams.form.question": {
        "Sual üçün mövzu bloku seçilməlidir.": {
            "az": "Sual üçün mövzu bloku seçilməlidir.",
            "en": "A topic block must be selected for the question.",
            "ru": "Для вопроса необходимо выбрать тематический блок.",
            "tr": "Soru için bir konu bloğu seçilmelidir.",
        },
    },
    "accounts.people.action": {
        "Naməlum əməliyyat.": {
            "az": "Naməlum əməliyyat.",
            "en": "Unknown action.",
            "ru": "Неизвестное действие.",
            "tr": "Bilinmeyen işlem.",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if stale and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
