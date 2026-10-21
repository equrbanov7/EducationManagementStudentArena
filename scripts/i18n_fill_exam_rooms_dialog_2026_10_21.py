#!/usr/bin/env python3
"""EMSArena i18n — «İmtahan zalları» dialoqlarında sahə xətaları (AJAX) və təkrar IP qaydası (2026-10-21).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

SR = "accounts.superadmin_exam_rooms"
RA = "exams.final_center.room_admin"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    SR: {
        "Bu sahə məcburidir.": t(
            "This field is required.", "Это поле обязательно.", "Bu alan zorunludur.", "Dieses Feld ist erforderlich."
        ),
        "Bu sahənin dəyəri düzgün deyil.": t(
            "This field's value is not valid.",
            "Значение этого поля недопустимо.",
            "Bu alanın değeri geçerli değil.",
            "Der Wert dieses Feldes ist ungültig.",
        ),
        "Formada xəta var — qeyd olunmuş sahələri düzəldin.": t(
            "The form has errors — correct the marked fields.",
            "В форме есть ошибки — исправьте отмеченные поля.",
            "Formda hata var — işaretli alanları düzeltin.",
            "Das Formular enthält Fehler – korrigieren Sie die markierten Felder.",
        ),
        "Yadda saxlamaq alınmadı. Bağlantını yoxlayıb yenidən cəhd edin.": t(
            "Could not save. Check your connection and try again.",
            "Не удалось сохранить. Проверьте подключение и повторите попытку.",
            "Kaydedilemedi. Bağlantınızı kontrol edip tekrar deneyin.",
            "Speichern fehlgeschlagen. Prüfen Sie die Verbindung und versuchen Sie es erneut.",
        ),
        "Heç bir kompüter əlavə edilmədi — %(n)s sətirdə xəta var.": t(
            "No computers were added — %(n)s line(s) have errors.",
            "Ни один компьютер не добавлен — ошибки в строках: %(n)s.",
            "Hiçbir bilgisayar eklenmedi — %(n)s satırda hata var.",
            "Es wurden keine Computer hinzugefügt – %(n)s Zeile(n) fehlerhaft.",
        ),
        "%(n)s sətir əlavə edilmədi — düzəldib yenidən göndərin.": t(
            "%(n)s line(s) were not added — fix them and submit again.",
            "Не добавлено строк: %(n)s — исправьте и отправьте снова.",
            "%(n)s satır eklenmedi — düzeltip yeniden gönderin.",
            "%(n)s Zeile(n) nicht hinzugefügt – korrigieren und erneut senden.",
        ),
    },
    "exams.template.take_exam": {
        "Bu imtahan artıq başqa tabda açıqdır — bu tabdan cavablar yazılmır. "
        "İmtahanı həmin tabda davam etdirin və ya onu bağlayıb bu səhifəni yeniləyin.": t(
            "This exam is already open in another tab — answers are not saved from this tab. "
            "Continue the exam in that tab, or close it and reload this page.",
            "Этот экзамен уже открыт в другой вкладке — ответы из этой вкладки не сохраняются. "
            "Продолжайте экзамен в той вкладке или закройте её и обновите эту страницу.",
            "Bu sınav zaten başka bir sekmede açık — bu sekmeden cevaplar kaydedilmiyor. "
            "Sınava o sekmede devam edin veya onu kapatıp bu sayfayı yenileyin.",
            "Diese Prüfung ist bereits in einem anderen Tab geöffnet – Antworten aus diesem Tab werden nicht gespeichert. "
            "Setzen Sie die Prüfung in jenem Tab fort oder schließen Sie ihn und laden Sie diese Seite neu.",
        ),
    },
    RA: {
        "Bu IP artıq «%(room)s» zalında «%(label)s» kompüterinə verilib: %(ip)s": t(
            "This IP is already assigned to computer «%(label)s» in room «%(room)s»: %(ip)s",
            "Этот IP уже назначен компьютеру «%(label)s» в зале «%(room)s»: %(ip)s",
            "Bu IP zaten «%(room)s» salonundaki «%(label)s» bilgisayarına atanmış: %(ip)s",
            "Diese IP ist bereits dem Computer «%(label)s» im Raum «%(room)s» zugewiesen: %(ip)s",
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
