#!/usr/bin/env python3
"""EMSArena i18n — W6 `w6paper` (2026-09-14): kağız bal idxalı — şablon şəbəkəsi + imtahan növü sütunu.

Yeni mətnlər: idxal planında «İmtahan növü» xanasının vərəqin növü ilə uyğunsuzluğu
(`registrar.exam_score_import`) və «Fayldan yüklə» panelindəki şablon izahı
(`registrar.exam_score_entry`). «İmtahan növü» başlığı və növ xətası MÖVCUD
msgid-lərdən (`registrar.exam_score_entry`) təkrar istifadə olunur.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir və
idempotentdir. TR qarşılıqları QƏSDƏN AZ mənbədən fərqlidir.

İstifadə:  python scripts/i18n_fill_w6paper_2026_09_14.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

IMPORT = "registrar.exam_score_import"
ESE = "registrar.exam_score_entry"

ENTRIES = {
    IMPORT: {
        "Sətirdəki imtahan növü («%(cell)s») vərəqin növü (%(kind)s) ilə uyğun gəlmir.": {
            "en": "The exam kind in this row (“%(cell)s”) does not match the sheet's kind (%(kind)s).",
            "ru": "Вид экзамена в строке («%(cell)s») не совпадает с видом ведомости (%(kind)s).",
            "tr": "Satırdaki sınav türü («%(cell)s») çizelgenin türüyle (%(kind)s) uyuşmuyor.",
        },
    },
    ESE: {
        "Şablon kartdakı sual sayı, bir sualın maksimumu və imtahan növü ilə endirilir; yoxlama da eyni şəbəkə ilə gedir.": {
            "en": (
                "The template is downloaded with the question count, per-question maximum and exam kind "
                "from the sheet card; the dry run uses the same grid."
            ),
            "ru": (
                "Шаблон скачивается с числом вопросов, максимумом за вопрос и видом экзамена из карточки "
                "ведомости; проверка использует ту же сетку."
            ),
            "tr": (
                "Şablon, çizelge kartındaki soru sayısı, soru başına en yüksek puan ve sınav türüyle indirilir; "
                "kontrol de aynı ızgarayla yapılır."
            ),
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
