#!/usr/bin/env python3
"""EMSArena i18n — kabinet bölmə başlıqları (Codex audit P2-06 yan tapıntısı, 2026-09-13).

`apps/accounts/views/profile/_sections/labels.py`-də 12 başlıq tərcüməsiz hərfi
AZ sətir idi (EN/RU/TR-də də azərbaycanca görünürdü). Başlıqlar
`pgettext_lazy("profile.sidebar", …)`-yə keçirildi; bu skript həmin msgid-ləri
dörd kataloqa əlavə edir. «Kafedralar» `profile.sidebar` kontekstində artıq
mövcuddur (sidebar şablonu) — skript onu ötür.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız əlavə edir və idempotentdir.
İstifadə:  python scripts/i18n_fill_section_titles_2026_09_13.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]
CTX = "profile.sidebar"

ENTRIES = {
    CTX: {
        "Postların idarəetməsi": {"en": "Post moderation", "ru": "Модерация постов", "tr": "Gönderi yönetimi"},
        "Dəyərləndirilmiş nəticələr": {
            "en": "Reviewed results",
            "ru": "Проверенные результаты",
            "tr": "Değerlendirilmiş sonuçlar",
        },
        "Təşkilat özəllikləri": {"en": "Organization features", "ru": "Функции организации", "tr": "Kurum özellikleri"},
        "Sual Bankı": {"en": "Question bank", "ru": "Банк вопросов", "tr": "Soru bankası"},
        "Bölmə imtahanları": {"en": "Unit exams", "ru": "Экзамены подразделения", "tr": "Birim sınavları"},
        "Fakültə və kafedralar": {
            "en": "Faculties and departments",
            "ru": "Факультеты и кафедры",
            "tr": "Fakülteler ve bölümler",
        },
        "Fakültələr": {"en": "Faculties", "ru": "Факультеты", "tr": "Fakülteler"},
        "Kafedralar": {"en": "Departments", "ru": "Кафедры", "tr": "Bölümler"},
        "Struktur üzvləri": {"en": "Structure members", "ru": "Члены структуры", "tr": "Yapı üyeleri"},
        "Təşkilat rolları": {"en": "Organization roles", "ru": "Роли организации", "tr": "Kurum rolleri"},
        "Audit jurnalı": {"en": "Audit log", "ru": "Журнал аудита", "tr": "Denetim günlüğü"},
        "Təşkilat məlumatları": {
            "en": "Organization details",
            "ru": "Сведения об организации",
            "tr": "Kurum bilgileri",
        },
    }
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
