#!/usr/bin/env python3
"""EMSArena i18n — W3 2026-09-14 «sual idxalı: şəkil + düstur» (w3import).

Sahib: «Sual import yerlərinə də bax… şəkil və düstur olanda problem yaranmasın
deyə dünyada bununla bağlı best practice nədirsə onu düşünərək et.»

Əlavə olunan mətnlər:
  * `exams.template.test_question_bank` — workbench nişanları/çipləri/ipucu
    (msgid AZ cümlədir → az msgstr = msgid);
  * `exams.service.parsing.docx.warning`, `exams.service.parsing.error`,
    `exams.service.parsing.warning` — açar-üslublu msgid-lər (az msgstr ayrıca verilir).

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Orkestrator serial işlədir; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_w3import_2026_09_14.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

TQB = "exams.template.test_question_bank"
DOCX_WARN = "exams.service.parsing.docx.warning"
PARSE_ERR = "exams.service.parsing.error"
PARSE_WARN = "exams.service.parsing.warning"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    TQB: {
        "Düstur": {"en": "Formula", "ru": "Формула", "tr": "Formül"},
        "Şəkil": {"en": "Image", "ru": "Изображение", "tr": "Görsel"},
        "Sual": {"en": "Question", "ru": "Вопрос", "tr": "Soru"},
        "şəkil bağlı": {"en": "image attached", "ru": "изображение прикреплено", "tr": "görsel bağlı"},
        "LaTeX düstur tanındı": {
            "en": "LaTeX formula recognised",
            "ru": "Формула LaTeX распознана",
            "tr": "LaTeX formülü tanındı",
        },
        "Düstur tam çevrilmədi — mətni yoxlayın": {
            "en": "The formula was not fully converted — check the text",
            "ru": "Формула преобразована не полностью — проверьте текст",
            "tr": "Formül tam dönüştürülemedi — metni kontrol edin",
        },
        "Sənəddən şəkil bağlanacaq": {
            "en": "An image from the document will be attached",
            "ru": "Изображение из документа будет прикреплено",
            "tr": "Belgedeki görsel eklenecek",
        },
        "Şəkil istinadı var, mənbə tapılmadı": {
            "en": "Image reference present, source not found",
            "ru": "Есть ссылка на изображение, источник не найден",
            "tr": "Görsel referansı var, kaynak bulunamadı",
        },
        "Sənəddən çıxarılan şəkil — yadda saxlayanda bağlanır:": {
            "en": "Image extracted from the document — attached on save:",
            "ru": "Изображение из документа — прикрепляется при сохранении:",
            "tr": "Belgeden çıkarılan görsel — kaydedince eklenir:",
        },
        "Word (.docx) faylındakı şəkillər və düsturlar (LaTeX) avtomatik tanınır; .doc/.docm qəbul edilmir.": {
            "en": "Images and formulas (LaTeX) in Word (.docx) files are recognised automatically; .doc/.docm are not accepted.",
            "ru": "Изображения и формулы (LaTeX) из файлов Word (.docx) распознаются автоматически; .doc/.docm не принимаются.",
            "tr": "Word (.docx) dosyasındaki görseller ve formüller (LaTeX) otomatik tanınır; .doc/.docm kabul edilmez.",
        },
    },
    DOCX_WARN: {
        "formula_partial": {
            "az": "Düstur tam çevrilmədi ({nodes}) — mətn kimi saxlanıldı: «{preview}»",
            "en": "Formula was only partially converted ({nodes}) — kept as text: “{preview}”",
            "ru": "Формула преобразована частично ({nodes}) — сохранена как текст: «{preview}»",
            "tr": "Formül kısmen dönüştürüldü ({nodes}) — metin olarak tutuldu: «{preview}»",
        },
        "formula_fallback": {
            "az": "Bu sualdakı düstur Word-dən tam çevrilmədi — render nəticəsini yoxlayın.",
            "en": "The formula in this question was not fully converted from Word — check how it renders.",
            "ru": "Формула в этом вопросе преобразована из Word не полностью — проверьте отображение.",
            "tr": "Bu sorudaki formül Word'den tam dönüştürülemedi — görünümü kontrol edin.",
        },
        "image_ref_unknown": {
            "az": "Şəkil istinadı tapılmadı: [[img:{refs}]] — sənəddəki şəkil nömrələri ilə uyğun deyil.",
            "en": "Image reference not found: [[img:{refs}]] — it does not match the image numbers in the document.",
            "ru": "Ссылка на изображение не найдена: [[img:{refs}]] — не совпадает с номерами изображений в документе.",
            "tr": "Görsel referansı bulunamadı: [[img:{refs}]] — belgedeki görsel numaralarıyla eşleşmiyor.",
        },
        "images_external_skipped": {
            "az": "{count} şəkil xarici linkdir — təhlükəsizlik səbəbi ilə yüklənmədi.",
            "en": "{count} image(s) are external links — not downloaded for security reasons.",
            "ru": "{count} изображений — внешние ссылки; из соображений безопасности не загружены.",
            "tr": "{count} görsel dış bağlantı — güvenlik nedeniyle indirilmedi.",
        },
        "images_unsupported_skipped": {
            "az": "{count} şəkil dəstəklənmir və ya limitdən böyükdür — atıldı (EMF/WMF/SVG dəstəklənmir).",
            "en": "{count} image(s) are unsupported or too large — skipped (EMF/WMF/SVG are not supported).",
            "ru": "{count} изображений не поддерживаются или слишком велики — пропущены (EMF/WMF/SVG не поддерживаются).",
            "tr": "{count} görsel desteklenmiyor veya çok büyük — atlandı (EMF/WMF/SVG desteklenmez).",
        },
    },
    PARSE_ERR: {
        "file_docx_corrupt": {
            "az": "Word (.docx) faylı oxunmadı — zip strukturu pozuqdur və ya sənəd deyil.",
            "en": "The Word (.docx) file could not be read — the zip structure is broken or it is not a document.",
            "ru": "Файл Word (.docx) не удалось прочитать — структура zip повреждена или это не документ.",
            "tr": "Word (.docx) dosyası okunamadı — zip yapısı bozuk ya da bir belge değil.",
        },
    },
    PARSE_WARN: {
        "formula_denied": {
            "az": "Düsturda icazə verilməyən əmr var ({command}) — düstur mətn kimi saxlanıldı: «{preview}»",
            "en": "The formula contains a disallowed command ({command}) — kept as plain text: “{preview}”",
            "ru": "В формуле недопустимая команда ({command}) — сохранена как обычный текст: «{preview}»",
            "tr": "Formülde izin verilmeyen komut var ({command}) — düz metin olarak tutuldu: «{preview}»",
        },
        "formula_too_long": {
            "az": "Düstur çox uzundur (limit 2000 simvol) — mətn kimi saxlanıldı: «{preview}»",
            "en": "The formula is too long (limit 2000 characters) — kept as plain text: “{preview}”",
            "ru": "Формула слишком длинная (лимит 2000 символов) — сохранена как обычный текст: «{preview}»",
            "tr": "Formül çok uzun (sınır 2000 karakter) — düz metin olarak tutuldu: «{preview}»",
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
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
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
