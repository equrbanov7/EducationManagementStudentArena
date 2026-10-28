#!/usr/bin/env python3
"""Sillabusun avtomatik təsdiq/redaktə mətnlərini idempotent əlavə edir."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
CONTEXT = "accounts.syllabus"
LANGUAGES = ("az", "en", "ru", "tr", "de")


def translations(en, ru, tr, de):
    return dict(zip(("en", "ru", "tr", "de"), (en, ru, tr, de)))


MESSAGES = {
    "Redaktə et": translations("Edit", "Редактировать", "Düzenle", "Bearbeiten"),
    "Düzəlişlər avtomatik təsdiqlənir": translations(
        "Changes are approved automatically",
        "Изменения утверждаются автоматически",
        "Değişiklikler otomatik onaylanır",
        "Änderungen werden automatisch genehmigt",
    ),
    "Dəyişiklikləri saxla": translations(
        "Save changes", "Сохранить изменения", "Değişiklikleri kaydet", "Änderungen speichern"
    ),
    "Məsləhət saatı (istəyə bağlı)": translations(
        "Consultation hours (optional)",
        "Часы консультаций (необязательно)",
        "Danışmanlık saatleri (isteğe bağlı)",
        "Sprechstunden (optional)",
    ),
    "Düzəlişlər avtomatik saxlanılır və təsdiqlənmiş qalır. Təkrar təsdiqə göndərmək lazım deyil.": translations(
        "Changes are saved automatically and remain approved. No further approval submission is needed.",
        "Изменения сохраняются автоматически и остаются утверждёнными. Повторное согласование не требуется.",
        "Değişiklikler otomatik kaydedilir ve onaylı kalır. Yeniden onaya göndermek gerekmez.",
        "Änderungen werden automatisch gespeichert und bleiben genehmigt. Eine erneute Freigabe ist nicht nötig.",
    ),
    "Düzəlişlər saxlandıqda sillabus təsdiqlənmiş qalır. Təkrar göndərmə tələb olunmur.": translations(
        "The syllabus remains approved when changes are saved. No resubmission is required.",
        "После сохранения изменений силлабус остаётся утверждённым. Повторная отправка не требуется.",
        "Değişiklikler kaydedildiğinde izlence onaylı kalır. Yeniden göndermek gerekmez.",
        "Der Lehrplan bleibt nach dem Speichern genehmigt. Eine erneute Einreichung ist nicht erforderlich.",
    ),
    "Sillabus avtomatik təsdiqlənəcək. Sonrakı düzəlişlər də təsdiqlənmiş qalacaq.": translations(
        "The syllabus will be approved automatically. Later changes will also remain approved.",
        "Силлабус будет утверждён автоматически. Последующие изменения также останутся утверждёнными.",
        "İzlence otomatik onaylanacaktır. Sonraki değişiklikler de onaylı kalacaktır.",
        "Der Lehrplan wird automatisch genehmigt. Spätere Änderungen bleiben ebenfalls genehmigt.",
    ),
    "Sillabusu təsdiqlə": translations(
        "Approve syllabus", "Утвердить силлабус", "İzlenceyi onayla", "Lehrplan genehmigen"
    ),
    "Təsdiqlədikdə sillabus avtomatik təsdiqlənir və dərhal istifadə olunur.": translations(
        "Confirming automatically approves the syllabus and makes it available immediately.",
        "После подтверждения силлабус автоматически утверждается и сразу становится доступным.",
        "Onayladığınızda izlence otomatik onaylanır ve hemen kullanıma açılır.",
        "Nach der Bestätigung wird der Lehrplan automatisch genehmigt und ist sofort verfügbar.",
    ),
    "Təsdiqlədikdə sillabus dərhal avtomatik təsdiqlənir. Kafedra növbəsində gözləmir.": translations(
        "Confirming approves the syllabus immediately. It does not wait for department approval.",
        "После подтверждения силлабус сразу утверждается автоматически, без ожидания согласования кафедрой.",
        "Onayladığınızda izlence hemen otomatik onaylanır. Bölüm onayı beklemez.",
        "Nach der Bestätigung wird der Lehrplan sofort genehmigt, ohne auf die Freigabe der Abteilung zu warten.",
    ),
}


def fill(language):
    path = BASE / "locale" / language / "LC_MESSAGES" / "django.po"
    catalog = polib.pofile(path)
    blocks = []
    for message, values in MESSAGES.items():
        entry = catalog.find(message, msgctxt=CONTEXT)
        if entry is not None:
            if not entry.msgstr or "fuzzy" in entry.flags:
                raise ValueError(f"Untranslated existing entry: {language}: {message}")
            continue
        value = message if language == "az" else values[language]
        blocks.append(
            f"msgctxt {json.dumps(CONTEXT, ensure_ascii=False)}\n"
            f"msgid {json.dumps(message, ensure_ascii=False)}\n"
            f"msgstr {json.dumps(value, ensure_ascii=False)}\n"
        )
    if blocks:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + "\n".join(blocks))
    polib.pofile(path).save_as_mofile(path.with_suffix(".mo"))
    return len(blocks)


if __name__ == "__main__":
    for language in LANGUAGES:
        print(f"{language}: {fill(language)} added")
