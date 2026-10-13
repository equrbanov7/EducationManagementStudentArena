#!/usr/bin/env python3
"""EMSArena i18n — jurnal UX 2026-10-14 (avtomatik yadda saxlama).

Əlavə olunan mətnlər (`registrar.journal_autosave`):
  * «Yadda saxla» düyməsinin yanındakı kiçik vəziyyət mətni (`_jd_autosave_status.html`) —
    gözləmə / yazılır / yazıldı / qismən yazıldı (`{n}` — yazılmayan xana sayı) / təkrar cəhd / xəta;
  * «Yenidən cəhd et» düyməsi.

Server tərəfi yeni mətn əlavə etmir — JSON cavablar mövcud msgid-ləri («Jurnal bağlıdır — …»,
«… bal-yazma pəncərəsi açıq deyil — …») təkrar işlədir.

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_journalux_2026_10_14.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

AUTOSAVE = "registrar.journal_autosave"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    AUTOSAVE: {
        "Dəyişikliklər avtomatik yadda saxlanılır.": {
            "en": "Changes are saved automatically.",
            "ru": "Изменения сохраняются автоматически.",
            "tr": "Değişiklikler otomatik olarak kaydedilir.",
            "de": "Änderungen werden automatisch gespeichert.",
        },
        "Yadda saxlanılır…": {
            "en": "Saving…",
            "ru": "Сохранение…",
            "tr": "Kaydediliyor…",
            "de": "Wird gespeichert…",
        },
        "Yadda saxlanıldı": {
            "en": "Saved",
            "ru": "Сохранено",
            "tr": "Kaydedildi",
            "de": "Gespeichert",
        },
        "Yadda saxlanıldı — {n} xana yazılmadı (kilid, dərs günü və ya bal qaydası).": {
            "en": "Saved — {n} cell(s) were not written (lock, lesson-day or score rule).",
            "ru": "Сохранено — {n} ячеек не записано (блокировка, правило дня занятия или балла).",
            "tr": "Kaydedildi — {n} hücre yazılmadı (kilit, ders günü veya puan kuralı).",
            "de": "Gespeichert — {n} Zelle(n) nicht übernommen (Sperre, Unterrichtstag- oder Punkteregel).",
        },
        "Xəta — yenidən cəhd edilir…": {
            "en": "Error — retrying…",
            "ru": "Ошибка — повторная попытка…",
            "tr": "Hata — yeniden deneniyor…",
            "de": "Fehler — neuer Versuch läuft…",
        },
        "Yadda saxlanılmadı — səhifəni yeniləyin. Dəyişikliklər brauzerdə qaralama kimi qalır.": {
            "en": "Not saved — please reload the page. Your changes are kept in the browser as a draft.",
            "ru": "Не сохранено — обновите страницу. Изменения остаются в браузере как черновик.",
            "tr": "Kaydedilmedi — sayfayı yenileyin. Değişiklikler tarayıcıda taslak olarak kalır.",
            "de": "Nicht gespeichert — bitte die Seite neu laden. Die Änderungen bleiben als Entwurf im Browser.",
        },
        "Yenidən cəhd et": {
            "en": "Try again",
            "ru": "Повторить",
            "tr": "Tekrar dene",
            "de": "Erneut versuchen",
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
    print(f"{lang}: +{added}")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
