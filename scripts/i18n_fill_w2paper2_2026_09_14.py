#!/usr/bin/env python3
"""EMSArena i18n — W2 `w2paper`, 2-ci dövrə (sahibin rəyi, 2026-09-14): təsdiq dialoqu + hərf sütunu.

«İmtahan balının daxil edilməsi» bölməsində yeni mətnlər (`registrar.exam_score_entry`):
hərf qiyməti sütunu, təsdiq dialoqunun düyməsi və kəsilən tələbə sayğacı.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir və
idempotentdir. TR qarşılıqları QƏSDƏN AZ mənbədən fərqlidir.

İstifadə:  python scripts/i18n_fill_w2paper2_2026_09_14.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ESE = "registrar.exam_score_entry"

ENTRIES = {
    ESE: {
        "Hərf": {"en": "Letter", "ru": "Буква", "tr": "Harf"},
        "Təsdiq et — sistemə yaz": {
            "en": "Confirm — record in the system",
            "ru": "Подтвердить — записать в систему",
            "tr": "Onayla — sisteme kaydet",
        },
        "tələbə kəsilir (F)": {
            "en": "student(s) failing (F)",
            "ru": "студент(ов) не сдают (F)",
            "tr": "öğrenci kalıyor (F)",
        },
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
