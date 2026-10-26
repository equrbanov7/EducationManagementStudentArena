#!/usr/bin/env python3
"""EMSArena i18n — «Transkript sorğusu» → «Transkripti hazırla və əlavə et» (sahib 2026-10-26).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

AT = "applications.transcript"
RD = "registrar.documents"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    AT: {
        "Akademik transkript": t(
            "Academic transcript", "Академическая выписка", "Akademik not dökümü", "Leistungsnachweis"
        ),
        "Transkript QR və yoxlama kodu ilə möhürlənir və müraciətə açıq qeyd kimi əlavə olunur — sahib onu "
        "müraciətdən endirir.": t(
            "The transcript is sealed with a QR and verification code and attached to the application as a "
            "public note — the applicant downloads it from the application.",
            "Выписка заверяется QR-кодом и кодом проверки и прикрепляется к обращению открытой заметкой — "
            "заявитель скачивает её из обращения.",
            "Transkript QR ve doğrulama koduyla mühürlenir ve başvuruya açık not olarak eklenir — başvuru sahibi "
            "onu başvurudan indirir.",
            "Der Leistungsnachweis wird mit QR- und Prüfcode versiegelt und dem Antrag als öffentliche Notiz "
            "angehängt — die antragstellende Person lädt ihn aus dem Antrag herunter.",
        ),
        "Transkripti hazırla və əlavə et": t(
            "Prepare and attach the transcript",
            "Подготовить и прикрепить выписку",
            "Transkripti hazırla ve ekle",
            "Leistungsnachweis erstellen und anhängen",
        ),
        "Transkript əlavə olunub": t(
            "Transcript attached", "Выписка прикреплена", "Transkript eklendi", "Leistungsnachweis angehängt"
        ),
        "Transkripti aç": t("Open transcript", "Открыть выписку", "Transkripti görüntüle", "Leistungsnachweis öffnen"),
        "Transkripti yenidən hazırla": t(
            "Prepare the transcript again",
            "Подготовить выписку заново",
            "Transkripti yeniden hazırla",
            "Leistungsnachweis erneut erstellen",
        ),
        "Nəticələr dəyişməyibsə, bu gün artıq əlavə olunmuş transkript qaytarılır — ikinci fayl yaranmır.": t(
            "If the results have not changed, the transcript already attached today is returned — no second "
            "file is created.",
            "Если результаты не изменились, возвращается уже прикреплённая сегодня выписка — второй файл не "
            "создаётся.",
            "Sonuçlar değişmediyse bugün zaten eklenmiş transkript döndürülür — ikinci dosya oluşmaz.",
            "Haben sich die Ergebnisse nicht geändert, wird der heute bereits angehängte Leistungsnachweis "
            "zurückgegeben — es entsteht keine zweite Datei.",
        ),
        "Bu müraciətə transkript hazırlamaq mümkün deyil.": t(
            "A transcript cannot be prepared for this application.",
            "Для этого обращения нельзя подготовить выписку.",
            "Bu başvuru için transkript hazırlanamaz.",
            "Für diesen Antrag kann kein Leistungsnachweis erstellt werden.",
        ),
        "Akademik transkript hazırlandı və əlavə olundu. Yoxlama kodu: %(code)s.": t(
            "The academic transcript has been prepared and attached. Verification code: %(code)s.",
            "Академическая выписка подготовлена и прикреплена. Код проверки: %(code)s.",
            "Akademik transkript hazırlandı ve eklendi. Doğrulama kodu: %(code)s.",
            "Der Leistungsnachweis wurde erstellt und angehängt. Prüfcode: %(code)s.",
        ),
        "hazırlanıb: %(date)s": t(
            "prepared: %(date)s", "подготовлено: %(date)s", "hazırlandı: %(date)s", "erstellt: %(date)s"
        ),
    },
    RD: {
        "Tələbənin transkriptə düşəcək akademik qeydi hələ yoxdur.": t(
            "The student has no academic results for a transcript yet.",
            "У студента пока нет академических результатов для выписки.",
            "Öğrencinin transkripte girecek akademik kaydı henüz yok.",
            "Für die/den Studierende(n) liegen noch keine Ergebnisse für einen Leistungsnachweis vor.",
        ),
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
