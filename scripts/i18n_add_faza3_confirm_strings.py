#!/usr/bin/env python3
"""Faza 3 — silmə təsdiqi sətirlərinin 4 dildə əlavəsi.

İki dəyişikliyi müşayiət edir:

1. ``exams/teacher/confirm_delete.html`` — JS-siz geri düşmə səhifəsi
   (əvvəllər view mövcud olmayan şablonu render edirdi → 500).
2. Zibil qutusunda birdəfəlik silmə — düymə artıq yalnız cəhdi OLMAYAN imtahan
   üçün görünür, ona görə köhnə təsdiq mətni («bütün nəticələri silinəcək»)
   yanlışdır: silinən imtahanın nəticəsi yoxdur. Mətn faktiki davranışa
   uyğunlaşdırılır.

İstifadə::

    python scripts/i18n_add_faza3_confirm_strings.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

#: ``(msgctxt, msgid) -> {lang: mətn}``
ENTRIES: dict[tuple[str, str], dict[str, str]] = {
    ("exams.view.exams.confirm", "delete_exam_title"): {
        "az": "İmtahanı silmək istəyirsiniz?",
        "en": "Delete this exam?",
        "ru": "Удалить этот экзамен?",
        "tr": "Bu sınav silinsin mi?",
    },
    ("exams.view.exams.confirm", "delete_exam_message"): {
        "az": "İmtahan Zibil qutusuna keçəcək. Nəticələr silinmir — imtahanı sonra bərpa edə bilərsiniz.",
        "en": "The exam will be moved to the Trash. Results are kept — you can restore the exam later.",
        "ru": "Экзамен будет перемещён в Корзину. Результаты сохраняются — экзамен можно восстановить позже.",
        "tr": "Sınav Çöp Kutusu'na taşınacak. Sonuçlar korunur — sınavı daha sonra geri yükleyebilirsiniz.",
    },
    ("exams.view.questions.confirm", "delete_question_title"): {
        "az": "Sualı silmək istəyirsiniz?",
        "en": "Delete this question?",
        "ru": "Удалить этот вопрос?",
        "tr": "Bu soru silinsin mi?",
    },
    ("exams.view.questions.confirm", "delete_question_message"): {
        "az": "Sual imtahandan silinəcək və qalan sualların nömrələri yenidən sıralanacaq.",
        "en": "The question will be removed from the exam and the remaining questions will be renumbered.",
        "ru": "Вопрос будет удалён из экзамена, а остальные вопросы будут перенумерованы.",
        "tr": "Soru sınavdan kaldırılacak ve kalan soruların numaraları yeniden sıralanacak.",
    },
    ("exams.template.confirm_delete", "action_cancel"): {
        "az": "Ləğv et",
        "en": "Cancel",
        "ru": "Отмена",
        "tr": "İptal",
    },
    ("exams.template.confirm_delete", "action_delete"): {
        "az": "Sil",
        "en": "Delete",
        "ru": "Удалить",
        "tr": "Sil",
    },
    ("exams.template.deleted_exams", "action_cancel"): {
        "az": "Ləğv et",
        "en": "Cancel",
        "ru": "Отмена",
        "tr": "İptal",
    },
    ("exams.template.deleted_exams", "permanent_delete_blocked_hint"): {
        "az": "Bu imtahanın cəhdləri var — akademik tarixçə qorunduğu üçün birdəfəlik silinə bilməz.",
        "en": "This exam has attempts — it cannot be deleted permanently because academic history is protected.",
        "ru": "У этого экзамена есть попытки — его нельзя удалить навсегда, так как учебная история защищена.",
        "tr": "Bu sınavın denemeleri var — akademik geçmiş korunduğu için kalıcı olarak silinemez.",
    },
}

#: Mövcud mətni faktiki davranışla uyğunlaşdırılan girişlər (üzərinə yazılır).
REPLACEMENTS: dict[tuple[str, str], dict[str, str]] = {
    ("exams.template.deleted_exams", "confirm_permanent_delete"): {
        "az": (
            "Bu imtahan bazadan birdəfəlik silinəcək. Cəhdi olmadığı üçün heç bir "
            "akademik nəticə itmir. Əməliyyat geri qaytarıla bilməz."
        ),
        "en": (
            "This exam will be permanently deleted from the database. It has no attempts, "
            "so no academic result is lost. This action cannot be undone."
        ),
        "ru": (
            "Этот экзамен будет навсегда удалён из базы данных. У него нет попыток, "
            "поэтому учебные результаты не теряются. Действие необратимо."
        ),
        "tr": (
            "Bu sınav veritabanından kalıcı olarak silinecek. Denemesi olmadığı için "
            "hiçbir akademik sonuç kaybolmaz. Bu işlem geri alınamaz."
        ),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Faza 3 təsdiq sətirlərini əlavə et")
    parser.add_argument("--dry-run", action="store_true", help="dəyişiklik yazma")
    args = parser.parse_args()

    try:
        import polib
    except ImportError:
        print("❌ polib lazımdır: pip install polib")
        return 1

    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        catalog = polib.pofile(path)
        index = {(e.msgctxt or "", e.msgid): e for e in catalog if not e.obsolete}

        added = updated = 0
        for (ctx, msgid), texts in ENTRIES.items():
            entry = index.get((ctx, msgid))
            if entry is None:
                catalog.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=texts[lang]))
                added += 1
            elif entry.msgstr != texts[lang]:
                entry.msgstr = texts[lang]
                updated += 1

        for (ctx, msgid), texts in REPLACEMENTS.items():
            entry = index.get((ctx, msgid))
            if entry is not None and entry.msgstr != texts[lang]:
                entry.msgstr = texts[lang]
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                updated += 1

        if (added or updated) and not args.dry_run:
            catalog.save(path)
        print(f"  {lang}: {added} yeni, {updated} yeniləndi")

    print("\n✅ Bitdi. İndi: python manage.py compilemessages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
