#!/usr/bin/env python3
"""EMSArena i18n — «Sınaq keç» deaktiv / tarixi çatmamış imtahanda da (2026-10-20).

Detal səhifəsindəki «Sınaq keç» düyməsinin ipucu yeniləndi (köhnə ``trial_run_hint`` açarı artıq
istifadə olunmur; ``exam_inactive_trial_blocked`` mesajı da koddan çıxıb — makemessages onları
obsolete edəcək). msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid
toxunulmur); sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

TD = "exams.template.teacher_exam_detail"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    TD: {
        "İmtahanı tələbə kimi yoxlayın — deaktiv olsa və ya tarixi çatmasa da işləyir. "
        "Bu cəhd nəticələrə sayılmır.": t(
            "Take the exam as a student — works even if the exam is inactive or its date has not come yet. "
            "This attempt is not counted in results.",
            "Пройдите экзамен как студент — работает, даже если экзамен неактивен или его дата ещё не наступила. "
            "Эта попытка не учитывается в результатах.",
            "Sınavı öğrenci gibi deneyin — sınav pasif olsa veya tarihi gelmemiş olsa da çalışır. "
            "Bu deneme sonuçlara sayılmaz.",
            "Prüfung als Studierende(r) testen — funktioniert auch, wenn die Prüfung inaktiv ist oder ihr Termin "
            "noch nicht erreicht ist. Dieser Versuch zählt nicht zu den Ergebnissen.",
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
