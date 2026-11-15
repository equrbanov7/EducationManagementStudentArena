#!/usr/bin/env python3
"""«Sillabusu redaktə et» (sahib 2026-11-15): yalnız yeni msgid-ləri əlavə edir; mövcudlara toxunmur."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return dict(zip(LANGS[1:], (en, ru, tr, de)))


def quote(text):
    return json.dumps(text, ensure_ascii=False)


ENTRIES = {
    "django": {
        "registrar.syllabus": {
            "Sillabusu redaktə et": t(
                "Edit the syllabus", "Редактировать силлабус", "Müfredatı düzenle", "Syllabus bearbeiten"
            ),
            "Redaktəyə keçmək alınmadı. Səhifəni yeniləyib yenidən cəhd edin.": t(
                "Could not open the editor. Refresh the page and try again.",
                "Не удалось перейти к редактированию. Обновите страницу и попробуйте ещё раз.",
                "Düzenleyici açılamadı. Sayfayı yenileyip tekrar deneyin.",
                "Der Editor konnte nicht geöffnet werden. Laden Sie die Seite neu und versuchen Sie es erneut.",
            ),
        },
        "accounts.syllabus": {
            "Versiya kafedra müdirinin baxışındadır. Dəyişiklik etmək üçün «Sillabuslar» siyahısında təqdimatı "
            "geri çağırın — sonra redaktə yenidən açılır.": t(
                "This version is being reviewed by the head of department. To make changes, withdraw the "
                "submission in the «Syllabi» list — editing then opens again.",
                "Версия на рассмотрении у заведующего кафедрой. Чтобы внести изменения, отзовите отправку в "
                "списке «Силлабусы» — после этого редактирование снова откроется.",
                "Sürüm bölüm başkanının incelemesinde. Değişiklik yapmak için «Müfredatlar» listesinde gönderimi "
                "geri çekin — ardından düzenleme yeniden açılır.",
                "Diese Version wird von der Lehrstuhlleitung geprüft. Um Änderungen vorzunehmen, ziehen Sie die "
                "Einreichung in der Liste «Syllabi» zurück — danach ist die Bearbeitung wieder möglich.",
            ),
            "Yeni versiya yarat": t(
                "Create a new version", "Создать новую версию", "Yeni sürüm oluştur", "Neue Version erstellen"
            ),
            "Yeni versiya yaradıla bilmədi. Səhifəni yeniləyib yenidən cəhd edin.": t(
                "Could not create a new version. Refresh the page and try again.",
                "Не удалось создать новую версию. Обновите страницу и попробуйте ещё раз.",
                "Yeni sürüm oluşturulamadı. Sayfayı yenileyip tekrar deneyin.",
                "Die neue Version konnte nicht erstellt werden. Laden Sie die Seite neu und versuchen Sie es erneut.",
            ),
        },
    },
}


def fill():
    counts = {}
    for domain, contexts in ENTRIES.items():
        for lang in LANGS:
            path = BASE / "locale" / lang / "LC_MESSAGES" / f"{domain}.po"
            existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
            blocks = []
            for context, messages in contexts.items():
                for msgid, translations in messages.items():
                    if (context, msgid) in existing:
                        continue
                    value = msgid if lang == "az" else translations[lang]
                    lines = ["#, python-format"] if "%" in msgid else []
                    if context:
                        lines.append("msgctxt " + quote(context))
                    lines += ["msgid " + quote(msgid), "msgstr " + quote(value)]
                    blocks.append("\n".join(lines) + "\n")
            if blocks:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(blocks))
            counts[f"{domain}/{lang}"] = len(blocks)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    fill()
