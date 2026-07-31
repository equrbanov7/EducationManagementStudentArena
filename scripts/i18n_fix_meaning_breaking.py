#!/usr/bin/env python3
"""Faza 4 — məna pozan tərcümələrin düzəlişi (2026-07-31 audit).

Üç ailə düzəlir:

1. **«Qiymət» (grade) → «qiymət» (price).** Azərbaycan dilində «qiymət» həm
   *grade*, həm *price* deməkdir; kontekstsiz tərcümədə yanlış məna seçilib və
   assignment app-ın bütün qiymətləndirmə səthlərinə yayılıb: RU «Цена»,
   TR «Fiyat». Bildirişdə isə tələbə «Цена была указана» görürdü.

2. **«Bal»/«Hesab» (score).** RU «Мед» (arı balı), TR «Bal» (yenə bal) və labs
   app-da TR «Gol» (futbol qolu), RU «Счет» (faktura).

3. **Status seçimləri düymə mətnləri ilə əvəzlənib.** `in_progress` (tələbə
   HAZIRDA imtahan yazır) 4 dildə də «Yoxlanılır / Pending processing» kimi
   göstərilirdi — müəllim canlı cəhdi bitmiş sanırdı. Nəzarət statusları isə
   daha pisdir: `removed` → «Sil» (düymə), `locked` → «Bloklanmış tələbə
   yoxdur.» (boş siyahı mesajı), `resumed` → «Bərpa et» (düymə).

İstifadə::

    python scripts/i18n_fix_meaning_breaking.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

#: ``(msgctxt, msgid) -> {lang: düzgün mətn}``
FIXES: dict[tuple[str, str], dict[str, str]] = {
    # ── 1. «Qiymət» = grade, PRICE deyil ────────────────────────────────────
    ("assignment.form.label", "grade"): {"ru": "Оценка", "tr": "Not"},
    ("assignment.submission.field", "grade"): {"ru": "Оценка", "tr": "Not"},
    ("assignment.detail", "table_grade"): {"ru": "Оценка", "tr": "Not"},
    ("assignment.my_submissions", "table_grade"): {"ru": "Оценка", "tr": "Not"},
    ("assignment.my_submissions", "grade"): {"ru": "Оценка", "tr": "Not"},
    ("assignment.review_submissions", "table_grade"): {"ru": "Оценка", "tr": "Not"},
    ("assignment.review_submissions", "grade"): {"ru": "Оценка", "tr": "Not"},
    ("assignment.review_submissions", "grade_submit"): {"ru": "Выставить оценку", "tr": "Not ver"},
    # EN tərəfi də «Grade» (isim) idi, AZ isə «Qiymət verildi» (hadisə) —
    # bildiriş növü olduğu üçün hamısı hadisə formasına gətirilir.
    ("assignment.notification.choice.type", "grade"): {
        "en": "Grade posted",
        "ru": "Оценка выставлена",
        "tr": "Not verildi",
    },
    ("assignment.form.placeholder", "grade_range"): {"ru": "Оценка от 0 до 100", "tr": "0-100 arası not"},
    # ── 2. «Bal» / «Hesab» = score ──────────────────────────────────────────
    ("profile.results", "score_label"): {"ru": "Балл", "tr": "Puan"},
    ("assignment.legacy.modals", "label_max_score"): {"ru": "Макс. балл", "tr": "Maks. puan"},
    ("labs.template.grade_submission", "label_score"): {"ru": "Балл", "tr": "Puan"},
    ("labs.template.lab_submissions", "table_score"): {"ru": "Балл", "tr": "Puan"},
    ("labs.template.my_lab_answers", "label_score"): {"ru": "Балл", "tr": "Puan"},
    # ── 3. Cəhd statusları ──────────────────────────────────────────────────
    # `in_progress` = tələbə imtahanı HAZIRDA yazır. Eyni anlayış canlı monitor
    # şablonlarında artıq «Davam edir / In progress / В процессе / Devam ediyor»
    # kimidir — status seçimi ona uyğunlaşdırılır.
    ("exams.model.attempt.choice.status", "in_progress"): {
        "az": "Davam edir",
        "en": "In progress",
        "ru": "В процессе",
        "tr": "Devam ediyor",
    },
    ("exams.model.attempt.choice.status", "expired"): {
        "az": "Müddəti bitib",
        "en": "Expired",
        "ru": "Истекла",
        "tr": "Süresi doldu",
    },
    ("exams.model.attempt.choice.status", "submitted"): {
        "az": "Təqdim edilib",
        "en": "Submitted",
        "ru": "Отправлена",
        "tr": "Gönderildi",
    },
    # ── 4. Nəzarət statusları — düymə mətnləri ilə əvəzlənmişdi ─────────────
    ("exams.model.attempt.choice.supervision_status", "locked"): {
        "az": "Bloklanıb",
        "en": "Locked",
        "ru": "Заблокирован",
        "tr": "Kilitlendi",
    },
    ("exams.model.attempt.choice.supervision_status", "removed"): {
        "az": "Uzaqlaşdırılıb",
        "en": "Removed",
        "ru": "Удалён с экзамена",
        "tr": "Sınavdan çıkarıldı",
    },
    ("exams.model.attempt.choice.supervision_status", "resumed"): {
        "az": "Davam etdirilib",
        "en": "Resumed",
        "ru": "Возобновлён",
        "tr": "Devam ettirildi",
    },
    ("exams.model.attempt.choice.supervision_status", "warned"): {
        "az": "Xəbərdarlıq edilib",
        "en": "Warned",
        "ru": "Предупреждён",
        "tr": "Uyarıldı",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Məna pozan tərcümələri düzəlt")
    parser.add_argument("--dry-run", action="store_true", help="dəyişiklik yazma")
    args = parser.parse_args()

    try:
        import polib
    except ImportError:
        print("❌ polib lazımdır: pip install polib")
        return 1

    missing: list[str] = []
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        catalog = polib.pofile(path)
        index = {(e.msgctxt or "", e.msgid): e for e in catalog if not e.obsolete}

        changed = 0
        for key, texts in FIXES.items():
            text = texts.get(lang)
            if text is None:
                continue
            entry = index.get(key)
            if entry is None:
                missing.append(f"{lang}: {key}")
                continue
            if entry.msgstr == text:
                continue
            print(f"  {lang} [{key[0]}|{key[1]}]: {entry.msgstr[:34]!r} → {text!r}")
            entry.msgstr = text
            if "fuzzy" in entry.flags:
                entry.flags.remove("fuzzy")
            changed += 1

        if changed and not args.dry_run:
            catalog.save(path)
        print(f"── {lang}: {changed} düzəliş\n")

    for item in missing:
        print(f"⚠️  kataloqda tapılmadı — {item}")

    print("✅ Bitdi. İndi: python manage.py compilemessages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
