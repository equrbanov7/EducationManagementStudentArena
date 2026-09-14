#!/usr/bin/env python3
"""EMSArena i18n — backend auditi 2026-09-13, F-05 (ÜOMG etiketləri).

Tələbə «Statistika» bölməsindəki kart 4.0 şkalalı, kredit-çəkili GPA göstərir
(`statistics_metrics/student.py`), transkript isə 100 ballıq «Kumulyativ ÜOMG»
(`exam_eligibility.uomg_from`). Hər ikisi «ÜOMG (GPA)» adı ilə görünürdü —
eyni tələbə iki ekranda iki fərqli «ÜOMG» görürdü. Düsturlar DƏYİŞMİR; yalnız
statistika kartının etiketi və izah qeydi fərqləndirilir
(`statistics_metrics/presenter.py`).

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir və
idempotentdir. TR qarşılıqları QƏSDƏN AZ mənbədən fərqlidir — i18n qapısı
`msgstr == msgid` sətrini «tərcümə olunmamış» sayır.

İstifadə:  python scripts/i18n_fill_fixbackend_2026_09_13.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CTX = "profile.statistics"

# msgid = AZ mətn; msgstr: az = msgid, digərləri lüğətdən.
ENTRIES = {
    CTX: {
        "Orta GPA (4.0)": {"en": "Average GPA (4.0)", "ru": "Средний GPA (4.0)", "tr": "Ortalama GPA (4.0)"},
        "4.0 şkalası": {"en": "4.0 scale", "ru": "шкала 4.0", "tr": "4.0 ölçeği"},
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
