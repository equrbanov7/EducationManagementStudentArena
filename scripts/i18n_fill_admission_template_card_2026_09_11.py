#!/usr/bin/env python3
"""EMSArena i18n — ekran 08 «Tələbə qəbulu», 1-ci addım kartı (4 dil).

2026-09-11 sahib tələbi: «ATİS şablonu olan yer dizaynı yaxşı deyil, rənglər
və s. — nəsə deyəsən gəlməyib, onu da düzəlt.» 1-ci addım kartı 2/3-cü kartların
`six-card` dilinə keçirildi; sütun kataloqu iki qruplu `ems-table` oldu.

Yeni mətnlər (`accounts.student_admission`):
* kart başlığı cümlə halında («1 · ATİS ŞABLONUNU ENDİRİN» → nömrə nişanı
  ayrıca, başlıq «ATİS şablonunu endirin»);
* açılışın etiketi, qrup başlığı, cədvəl başlığı və məcburi-sütun izahı.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir və idempotentdir. TR qarşılıqları QƏSDƏN AZ mənbədən fərqlidir —
i18n qapısı `msgstr == msgid` sətrini «tərcümə olunmamış» sayır.

İstifadə:  python scripts/i18n_fill_admission_template_card_2026_09_11.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "accounts.student_admission": {
        "ATİS şablonunu endirin": {
            "en": "Download the ATİS template",
            "ru": "Скачайте шаблон ATİS",
            "tr": "ATİS şablonunu indirin",
        },
        "Şablonun sütunları": {
            "en": "Template columns",
            "ru": "Столбцы шаблона",
            "tr": "Şablon sütunları",
        },
        "Əsas sütunlar": {
            "en": "Core columns",
            "ru": "Основные столбцы",
            "tr": "Temel sütunlar",
        },
        "Başlıq": {
            "en": "Header",
            "ru": "Заголовок",
            "tr": "Başlık",
        },
        "Məcburi sütun": {
            "en": "Required column",
            "ru": "Обязательный столбец",
            "tr": "Zorunlu sütun",
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
