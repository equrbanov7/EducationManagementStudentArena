#!/usr/bin/env python3
"""EMSArena i18n — W8 2026-09-14 «sual idxalı: pano ilə şəkil yapışdırma» (w8paste).

w3import yarımçıq 7 / NIGHT_WAVES §5 maddə 11: toplu sual iş masasında şəkil
Ctrl+V / sürükləmə ilə yapışdırılır, `[[img:N]]` markeri caret-ə düşür.

Əlavə olunan mətnlər:
  * `exams.template.test_question_bank` — zolaq ipucu, çip etiketləri, JS mesajları
    (msgid AZ cümlədir → az msgstr = msgid);
  * `exams.view.bank.paste` — view JSON xətaları (AZ cümlə);
  * `exams.service.import.paste.error` — açar-üslublu msgid-lər (az msgstr ayrıca).

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Orkestrator serial işlədir; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_w8paste_2026_09_14.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

TQB = "exams.template.test_question_bank"
VIEW = "exams.view.bank.paste"
SVC = "exams.service.import.paste.error"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    TQB: {
        "Şəkil yüklənir…": {"en": "Uploading image…", "ru": "Загрузка изображения…", "tr": "Görsel yükleniyor…"},
        "Şəkil yüklənmədi.": {
            "en": "The image could not be uploaded.",
            "ru": "Не удалось загрузить изображение.",
            "tr": "Görsel yüklenemedi.",
        },
        "Şəkil silindi — [[img:N]] işarəsi mətndən çıxarıldı.": {
            "en": "Image removed — the [[img:N]] marker was taken out of the text.",
            "ru": "Изображение удалено — маркер [[img:N]] убран из текста.",
            "tr": "Görsel silindi — [[img:N]] işareti metinden çıkarıldı.",
        },
        "Yalnız şəkil faylı (PNG/JPG/GIF/WebP) yapışdırıla bilər.": {
            "en": "Only image files (PNG/JPG/GIF/WebP) can be pasted here.",
            "ru": "Сюда можно вставить только изображение (PNG/JPG/GIF/WebP).",
            "tr": "Buraya yalnızca görsel dosyası (PNG/JPG/GIF/WebP) yapıştırılabilir.",
        },
        "Şəkli sil": {"en": "Remove image", "ru": "Удалить изображение", "tr": "Görseli sil"},
        (
            "Şəkli panodan yapışdırın (Ctrl+V) və ya bura sürüşdürün — [[img:N]] işarəsi kursorun yerinə "
            "düşür; sual sətrində sual, variant sətrində həmin varianta bağlanır."
        ): {
            "en": (
                "Paste an image from the clipboard (Ctrl+V) or drop it here — the [[img:N]] marker lands at "
                "the cursor; on a question line it attaches to the question, on an option line to that option."
            ),
            "ru": (
                "Вставьте изображение из буфера (Ctrl+V) или перетащите сюда — маркер [[img:N]] встанет в "
                "позицию курсора; в строке вопроса он привязывается к вопросу, в строке варианта — к варианту."
            ),
            "tr": (
                "Görseli panodan yapıştırın (Ctrl+V) veya buraya sürükleyin — [[img:N]] işareti imlecin yerine "
                "düşer; soru satırında soruya, seçenek satırında o seçeneğe bağlanır."
            ),
        },
    },
    VIEW: {
        "Şəkil göndərilməyib.": {
            "en": "No image was sent.",
            "ru": "Изображение не отправлено.",
            "tr": "Görsel gönderilmedi.",
        },
        "Şəkil nömrəsi yanlışdır.": {
            "en": "The image number is invalid.",
            "ru": "Неверный номер изображения.",
            "tr": "Görsel numarası geçersiz.",
        },
        "Şəkil müvəqqəti yığına yazılmadı.": {
            "en": "The image could not be written to the temporary stash.",
            "ru": "Не удалось записать изображение во временное хранилище.",
            "tr": "Görsel geçici depoya yazılamadı.",
        },
    },
    SVC: {
        "paste_token_invalid": {
            "az": "İdxal token-i yanlışdır — səhifəni yeniləyib yenidən cəhd edin.",
            "en": "The import token is invalid — reload the page and try again.",
            "ru": "Неверный токен импорта — обновите страницу и повторите попытку.",
            "tr": "İçe aktarma belirteci geçersiz — sayfayı yenileyip yeniden deneyin.",
        },
        "paste_into_visual_bundle": {
            "az": "Bu idxal mənbəsi vizual PDF-dir — ona şəkil yapışdırmaq olmur; «Təmizlə» ilə yenidən başlayın.",
            "en": "This import source is a visual PDF — images cannot be pasted into it; start over with “Clear”.",
            "ru": "Источник импорта — визуальный PDF; в него нельзя вставлять изображения. Начните заново через «Очистить».",
            "tr": "Bu içe aktarma kaynağı görsel bir PDF — içine görsel yapıştırılamaz; «Temizle» ile yeniden başlayın.",
        },
        "paste_image_unsupported": {
            "az": "Şəkil tanınmadı və ya limitdən böyükdür (PNG/JPG/GIF/BMP/TIFF/WebP, ≤12 MB, ≤50 MP).",
            "en": "The image was not recognised or exceeds the limit (PNG/JPG/GIF/BMP/TIFF/WebP, ≤12 MB, ≤50 MP).",
            "ru": "Изображение не распознано или превышает лимит (PNG/JPG/GIF/BMP/TIFF/WebP, ≤12 МБ, ≤50 МП).",
            "tr": "Görsel tanınmadı veya sınırı aşıyor (PNG/JPG/GIF/BMP/TIFF/WebP, ≤12 MB, ≤50 MP).",
        },
        "paste_image_limit": {
            "az": "Bir idxalda ən çox {limit} şəkil ola bilər.",
            "en": "An import can hold at most {limit} images.",
            "ru": "В одном импорте может быть не более {limit} изображений.",
            "tr": "Bir içe aktarmada en fazla {limit} görsel olabilir.",
        },
        "paste_image_not_found": {
            "az": "Bu nömrəli yapışdırılmış şəkil tapılmadı.",
            "en": "No pasted image with this number was found.",
            "ru": "Вставленное изображение с таким номером не найдено.",
            "tr": "Bu numaralı yapıştırılmış görsel bulunamadı.",
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
