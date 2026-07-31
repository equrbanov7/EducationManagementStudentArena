#!/usr/bin/env python3
"""Faza 6 — view-as LIMITED rejiminin mətnləri (4 dil).

`MODE_LIMITED` rejimi əlavə olundu: İmtahan Mərkəzi və İKT Mərkəzi başqa rolun
səhifəsində yalnız ÖZ sahələrinə aid marşrutlarda yaza bilər; qalan yazma
cəhdləri bloklanır və audit-ə düşür.

İstifadə::

    python scripts/i18n_add_view_as_limited_strings.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

ENTRIES: dict[tuple[str, str], dict[str, str]] = {
    ("accounts.view_as", "action_blocked_out_of_scope"): {
        "az": "Bu əməliyyat sizin səlahiyyət sahənizdən kənardır. Başqa istifadəçinin adından yalnız "
        "öz sahənizə aid dəyişiklikləri edə bilərsiniz.",
        "en": "This action is outside your area of authority. While acting as another user you may only "
        "make changes that belong to your own area.",
        "ru": "Это действие вне вашей области полномочий. Действуя от имени другого пользователя, вы можете "
        "вносить только изменения, относящиеся к вашей области.",
        "tr": "Bu işlem yetki alanınızın dışındadır. Başka bir kullanıcı adına yalnızca kendi alanınıza ait "
        "değişiklikleri yapabilirsiniz.",
    },
    ("accounts.view_as", "mode_limited"): {
        "az": "Məhdud dəyişiklik",
        "en": "Limited changes",
        "ru": "Ограниченные изменения",
        "tr": "Sınırlı değişiklik",
    },
    ("accounts.view_as", "mode_limited_hint"): {
        "az": "Yalnız öz sahənizə aid əməliyyatları edə bilərsiniz; qalan hər şey yalnız-oxudur.",
        "en": "You can only perform operations that belong to your own area; everything else is read-only.",
        "ru": "Вы можете выполнять только операции, относящиеся к вашей области; всё остальное — только чтение.",
        "tr": "Yalnızca kendi alanınıza ait işlemleri yapabilirsiniz; geri kalan her şey salt okunurdur.",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="view-as LIMITED mətnlərini əlavə et")
    parser.add_argument("--dry-run", action="store_true")
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
        for key, texts in ENTRIES.items():
            entry = index.get(key)
            if entry is None:
                catalog.append(polib.POEntry(msgctxt=key[0], msgid=key[1], msgstr=texts[lang]))
                added += 1
            elif entry.msgstr != texts[lang]:
                entry.msgstr = texts[lang]
                updated += 1

        if (added or updated) and not args.dry_run:
            catalog.save(path)
        print(f"  {lang}: {added} yeni, {updated} yeniləndi")

    print("\n✅ Bitdi. İndi: python manage.py compilemessages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
