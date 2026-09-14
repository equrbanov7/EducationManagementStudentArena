#!/usr/bin/env python3
"""EMSArena i18n — W4 `w4superv` (2026-09-14): final mərkəzi oturum tarixçəsi.

w3sweep R7: fərdi ExamStudentPin axınında oturum tarixçəsi KPI-ları «Girişlər 0 /
PIN əməliyyatı 0» göstərirdi. İndi `claim_student_pin_entry` giriş audit
hadisəsi yazır, `session_history` isə fərdi PIN-in yaradılmasını sintez edir.
Hər iki hadisənin DETAL mətni yenidir (`apps/exams/services/final_center/history.py`);
başlıqlar mövcud msgid-lərdir («Tələbə PIN ilə daxil oldu», «PIN yaradıldı və
tələbəyə təyin edildi»). Tarixçə modulunun mövcud sətirləri kimi KONTEKSTSİZ.

PDF şəkilləri (w3import yarımçıq 6): `exams.service.parsing.docx.warning`
kontekstində `pdf_images_unanchored_skipped` açarı (4 dil).

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir və
idempotentdir. TR qarşılığı QƏSDƏN AZ mənbədən fərqlidir (i18n qapısı
`msgstr == msgid` sətrini «tərcümə olunmamış» sayır).

İstifadə:  python scripts/i18n_fill_w4superv_2026_09_14.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# W4 PDF şəkilləri (w3import yarımçıq 6): `parsing/pdf_images.py` — ilk sualdan
# əvvəlki və ya mətndə sual sətri tapılmayan şəkillər üçün bundle xəbərdarlığı.
# Msgid AÇAR formasındadır (mövcud `images_unsupported_skipped` kimi), AZ msgstr
# tam mətndir — ona görə az üçün də lüğətdən götürülür.
PDF_WARN_CTX = "exams.service.parsing.docx.warning"

# ctx None → msgctxt sətri yazılmır (history.py çılpaq gettext işlədir).
ENTRIES = {
    PDF_WARN_CTX: {
        "pdf_images_unanchored_skipped": {
            "az": "{count} şəkil heç bir suala bağlanmadı (ilk sualdan əvvəl və ya mətndə sual sətri tapılmadı) — atıldı.",
            "en": "{count} image(s) could not be tied to a question (before the first question or no matching question line in the text) — skipped.",
            "ru": "{count} изображений не удалось привязать к вопросу (до первого вопроса или строка вопроса не найдена в тексте) — пропущены.",
            "tr": "{count} görsel hiçbir soruya bağlanamadı (ilk sorudan önce veya metinde soru satırı bulunamadı) — atlandı.",
        },
    },
    None: {
        "fərdi imtahan PIN-i ilə": {
            "en": "with the personal exam PIN",
            "ru": "по персональному PIN-коду экзамена",
            "tr": "kişisel sınav PIN'i ile",
        },
        "fərdi imtahan PIN-i (tələbə kabinetində göstərilir)": {
            "en": "personal exam PIN (shown in the student cabinet)",
            "ru": "персональный PIN-код экзамена (показывается в кабинете студента)",
            "tr": "kişisel sınav PIN'i (öğrenci panelinde gösterilir)",
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
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            key = f'{head}msgid "{esc(msgid)}"\n'
            if ctx is None:
                # Kontekstsiz blok: eyni msgid-in kontekstli variantı ilə qarışmasın.
                needle = f'msgid "{esc(msgid)}"\n'
                exists = any(needle in part and "msgctxt" not in part for part in text.split("\n\n"))
            else:
                exists = key in text
            if exists:
                continue
            msgstr = translations.get(lang, msgid) if (lang != "az" or "az" in translations) else msgid
            blocks.append(f'{key}msgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
