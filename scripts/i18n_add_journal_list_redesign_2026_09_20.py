#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-20: jurnal siyahısı redizaynı + dərs modalında korpus
defoltu. Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent;
sonra `compilemessages`.

İstifadə:  python scripts/i18n_add_journal_list_redesign_2026_09_20.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

# (ctx, msgid): (en, ru, tr)
STRINGS = {
    ("registrar.journal", "<b>%(count)s</b> jurnal"): (
        "<b>%(count)s</b> journals",
        "<b>%(count)s</b> журналов",
        "<b>%(count)s</b> günlük",
    ),
    ("registrar.journal", "Vakant"): ("Vacant", "Вакантно", "Boş"),
    ("registrar.journal", "Dəyişikliklər yadda saxlanmayıb"): (
        "Unsaved changes",
        "Изменения не сохранены",
        "Değişiklikler kaydedilmedi",
    ),
    ("registrar.journal", "Formada tətbiq olunmamış dəyişikliklər var. Bağlasanız, onlar itəcək."): (
        "The form has changes that were not applied. If you close it, they will be lost.",
        "В форме есть неприменённые изменения. Если закрыть, они будут потеряны.",
        "Formda uygulanmamış değişiklikler var. Kapatırsanız kaybolacak.",
    ),
    ("registrar.journal", "Bağla, itsin"): ("Close and discard", "Закрыть и отменить", "Kapat, vazgeç"),
    (
        "registrar.journal",
        "Korpus qrupun ixtisasına görə «%(building)s» seçilib — dəyişə bilərsiniz; otaqlar korpusa görə süzülür. Otaq məcburi deyil.",
    ): (
        "Building “%(building)s” is preselected from the group's programme — you can change it; rooms are filtered by building. Room is optional.",
        "Корпус «%(building)s» выбран по специальности группы — его можно изменить; аудитории фильтруются по корпусу. Аудитория необязательна.",
        "Bina, grubun programına göre «%(building)s» olarak seçildi — değiştirebilirsiniz; odalar binaya göre süzülür. Oda zorunlu değildir.",
    ),
}  # fmt: skip


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            target = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            entry = existing.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=target))
                added += 1
            elif not entry.msgstr:
                entry.msgstr = target
                added += 1
        po.save(path)
        print(f"{lang}: {added} əlavə/doldurma")


if __name__ == "__main__":
    main()
