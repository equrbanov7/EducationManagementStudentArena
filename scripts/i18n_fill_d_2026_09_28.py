#!/usr/bin/env python3
"""EMSArena i18n — Audit 2026-09-28 remediasiyası, iş paketi D (təhlükəsizlik/auth).

Əlavə olunan mətnlər:
  * `assignments.views.message` — `max_attempts` / `max_score` yararsızdırsa 400 (SA-10);
  * `exams.final_center.message` — «bərpa et» neytral xəta mətni (SA-10);
  * `live_exam.template.create_session_confirm` — canlı sessiya yaratma təsdiq
    səhifəsi (EX28-10: yaratma yalnız POST).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_d_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

AV = "assignments.views.message"
FC = "exams.final_center.message"
LC = "live_exam.template.create_session_confirm"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    AV: {
        "invalid_attempts_or_score": {
            "az": "Cəhd sayı və maksimal bal müsbət rəqəm olmalıdır.",
            "en": "Attempts and maximum score must be positive numbers.",
            "ru": "Число попыток и максимальный балл должны быть положительными числами.",
            "tr": "Deneme sayısı ve maksimum puan pozitif sayı olmalıdır.",
        },
    },
    FC: {
        "Cəhdi bərpa etmək mümkün olmadı.": {
            "az": "Cəhdi bərpa etmək mümkün olmadı.",
            "en": "The attempt could not be resumed.",
            "ru": "Не удалось возобновить попытку.",
            "tr": "Deneme devam ettirilemedi.",
        },
    },
    LC: {
        "create_confirm_title": {
            "az": "Canlı sessiyanı başlat",
            "en": "Start live session",
            "ru": "Начать живую сессию",
            "tr": "Canlı oturumu başlat",
        },
        "create_confirm_force_new_hint": {
            "az": "Bu imtahan üçün aktiv canlı sessiya bitiriləcək və yenisi yaradılacaq.",
            "en": "The active live session for this exam will be finished and a new one will be created.",
            "ru": "Активная живая сессия этого экзамена будет завершена, и будет создана новая.",
            "tr": "Bu sınavın aktif canlı oturumu sonlandırılacak ve yenisi oluşturulacak.",
        },
        "create_confirm_cancel": {
            "az": "Ləğv et",
            "en": "Cancel",
            "ru": "Отмена",
            "tr": "İptal",
        },
        "create_confirm_submit": {
            "az": "Başlat",
            "en": "Start",
            "ru": "Начать",
            "tr": "Başlat",
        },
    },
}

# Mövcud, lakin səhv tərcümə üstələnəcək cütlər (bu paketdə yoxdur).
FORCE: set = set()


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
