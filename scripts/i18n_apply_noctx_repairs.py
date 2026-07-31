#!/usr/bin/env python3
"""Faza 4 — msgctxt-siz blokun bərpa edilmiş tərcümələrinin tətbiqi.

Kontekst
--------
`{% trans %}` çağırışlarının bir hissəsi AZ mətnini birbaşa msgid kimi verir və
msgctxt vermir. Toplu tərcümə addımında bu blokdakı msgstr-lər **əlifba sırası
ilə sürüşüb** — bir çox giriş qonşusunun tərcüməsini mənimsəyib. Nümunələr:

    "Fakültə seçin"        → EN "Choose file"
    "Fakültə yarat"        → EN "Generate with AI"
    "Kafedranı redaktə et" → EN "Edit bank"
    "Bütün fakültələr"     → EN "All languages"

Heç biri fuzzy deyildi, yəni runtime-da canlı göstərilirdi: EN/RU/TR istifadəçi
kafedra silmə düyməsində «Delete bank» görürdü.

Düzəlişlər 1712 girişin hamısını yoxlayan çoxagentli axında hazırlanıb və ikinci
agent tərəfindən nəzarətdən keçirilib (`docs/audits/`). Bu skript onları tətbiq
edir və **placeholder bütövlüyünü proqramla yoxlayır** — model səhv etsə belə
runtime `KeyError` verə biləcək düzəliş keçmir.

İstifadə::

    python scripts/i18n_apply_noctx_repairs.py <fixes.json> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("en", "ru", "tr")  # az mənbə dildir — msgid-in özüdür, dəyişmir

#: Django format placeholder-ləri + HTML teqləri + HTML entity-ləri.
PLACEHOLDER_RE = re.compile(
    r"%\([^)]+\)[sd]|%[sd]|\{[a-zA-Z_][a-zA-Z0-9_]*\}|\{\}|</?[a-zA-Z][a-zA-Z0-9]*[^>]*>|&#?\w+;"
)


def _signature(text: str) -> list[str]:
    """Mətnin placeholder «imzası» — sıralanmış dəst."""
    return sorted(PLACEHOLDER_RE.findall(text or ""))


def main() -> int:
    parser = argparse.ArgumentParser(description="msgctxt-siz blok düzəlişlərini tətbiq et")
    parser.add_argument("fixes", help="düzəlişlərin JSON faylı")
    parser.add_argument("--dry-run", action="store_true", help="dəyişiklik yazma")
    args = parser.parse_args()

    try:
        import polib
    except ImportError:
        print("❌ polib lazımdır: pip install polib")
        return 1

    with open(args.fixes, encoding="utf-8") as handle:
        fixes = json.load(handle)
    print(f"{len(fixes)} düzəliş yükləndi.\n")

    rejected: list[str] = []
    missing: list[str] = []
    applied_total = 0

    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        catalog = polib.pofile(path)
        index = {e.msgid: e for e in catalog if not e.obsolete and not e.msgctxt}

        applied = skipped = 0
        for fix in fixes:
            text = fix.get(lang)
            if not text:
                continue
            entry = index.get(fix["az"])
            if entry is None:
                missing.append(f"{lang}: {fix['az'][:60]!r}")
                continue

            # SƏRT QAPI: placeholder dəsti mənbə ilə eyni olmalıdır. Model
            # nəyi təklif etsə də, uyğunsuzluq runtime KeyError deməkdir.
            if _signature(entry.msgid) != _signature(text):
                rejected.append(
                    f"{lang}: {fix['az'][:44]!r}\n"
                    f"        mənbə   {_signature(entry.msgid)}\n"
                    f"        təklif  {_signature(text)}"
                )
                continue

            if entry.msgstr == text:
                skipped += 1
                continue

            entry.msgstr = text
            if "fuzzy" in entry.flags:
                entry.flags.remove("fuzzy")
            applied += 1

        if applied and not args.dry_run:
            catalog.save(path)
        applied_total += applied
        print(f"── {lang}: {applied} tətbiq, {skipped} onsuz da eyni")

    if rejected:
        print(f"\n⛔ PLACEHOLDER QAPISI {len(rejected)} düzəlişi rədd etdi:")
        for item in rejected[:15]:
            print(f"   {item}")
    if missing:
        print(f"\n⚠️  kataloqda tapılmayan msgid: {len(missing)}")
        for item in missing[:8]:
            print(f"   {item}")

    verb = "tətbiq ediləcək" if args.dry_run else "tətbiq edildi"
    print(f"\n✅ Cəmi {applied_total} msgstr {verb}. Sonra: python manage.py compilemessages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
