#!/usr/bin/env python3
"""Zədəli ``msgctxt`` girişlərinin təmiri (2026-07-30 audit, Faza 2).

Problem
-------
Əvvəlki toplu doldurma skriptlərinin regex-i ``pgettext(...)`` çağırışının
bağlanğıc dırnağını düzgün tutmayıb və kontekst sahəsinə Python mənbə fraqmenti
düşüb, məsələn::

    msgctxt "exams.view.access.message\", message_key))\n            return redirect("

Belə giriş runtime-da HEÇ VAXT tapılmır (real çağırışın msgctxt-i başqadır), yəni
tərcümə ölüdür və istifadəçi ingilis/az mənbə mətnini görür.

Həll
----
Doğru kontekst **kataloqdan deyil, MƏNBƏ KODUNDAN** çıxarılır — zədəli msgctxt-in
əvvəli çox vaxt *əvvəlki* çağırışın kontekstidir, ona görə onu kəsib istifadə
etmək yanlış nəticə verir (yoxlanıb: `blog.notification` yox, `blog.post.message`).

Hər zədəli giriş üçün:

* mənbədə həmin msgid üçün yeganə kontekst tapılırsa —
  * təmiz cüt kataloqda YOXDURSA → girişin msgctxt-i düzəldilir (tərcümə qalır);
  * VARSA → tərcümə boş olan tərəfə köçürülür, zədəli giriş silinir;
* mənbədə tapılmırsa (ölü giriş) → silinir.

İstifadə::

    python scripts/i18n_repair_corrupt_msgctxt.py --dry-run
    python scripts/i18n_repair_corrupt_msgctxt.py
"""

from __future__ import annotations

import argparse
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")
DOMAINS = ("django", "djangojs")
SOURCE_ROOTS = ("apps", "core", "config")

#: ``pgettext("ctx", "msgid"`` — kontekst dırnaqsız, msgid escape-lərlə.
PGETTEXT_RE = re.compile(
    r"""pgettext(?:_lazy)?\(\s*(['"])(?P<ctx>[^'"]+)\1\s*,\s*(['"])(?P<msgid>(?:\\.|(?!\3).)*?)\3""",
    re.S,
)


def _is_corrupt(msgctxt: str | None) -> bool:
    """Kontekst Python fraqmenti daşıyırmı.

    Sağlam kontekst nöqtə ilə ayrılmış qısa açardır (``exams.view.access``).
    Sətir sonu, dırnaq, mötərizə və ya həddindən uzunluq = zədə.
    """
    if not msgctxt:
        return False
    return "\n" in msgctxt or '"' in msgctxt or "'" in msgctxt or "(" in msgctxt or len(msgctxt) > 80


def _source_contexts() -> dict[str, set[str]]:
    """Mənbə kodundakı ``msgid -> {msgctxt}`` xəritəsi."""
    pairs: dict[str, set[str]] = {}
    for root in SOURCE_ROOTS:
        root_path = os.path.join(BASE, root)
        if not os.path.isdir(root_path):
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "migrations", "node_modules")]
            for filename in filenames:
                if not filename.endswith((".py", ".html", ".js")):
                    continue
                path = os.path.join(dirpath, filename)
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    text = handle.read()
                for match in PGETTEXT_RE.finditer(text):
                    pairs.setdefault(match.group("msgid"), set()).add(match.group("ctx"))
    return pairs


def _repair_catalog(path: str, source_map: dict[str, set[str]], dry_run: bool) -> tuple[int, int, list[str]]:
    import polib

    catalog = polib.pofile(path)
    active = {(e.msgctxt or "", e.msgid): e for e in catalog if not e.obsolete}

    renamed = 0
    dropped = 0
    notes: list[str] = []

    for entry in list(catalog):
        if entry.obsolete or not _is_corrupt(entry.msgctxt):
            continue

        contexts = source_map.get(entry.msgid, set())
        if len(contexts) != 1:
            # Mənbədə yoxdur, ya da bir neçə kontekstdə işlənir → hansına aid
            # olduğu bilinmir; hər halda bu giriş runtime-da ölüdür.
            catalog.remove(entry)
            dropped += 1
            reason = "mənbədə yoxdur" if not contexts else f"{len(contexts)} namizəd kontekst"
            notes.append(f"sil ({reason}): {entry.msgid[:50]!r}")
            continue

        clean_ctx = next(iter(contexts))
        existing = active.get((clean_ctx, entry.msgid))
        if existing is None:
            entry.msgctxt = clean_ctx
            active[(clean_ctx, entry.msgid)] = entry
            renamed += 1
            notes.append(f"bərpa → {clean_ctx}: {entry.msgid[:50]!r}")
        else:
            if not existing.msgstr and entry.msgstr:
                existing.msgstr = entry.msgstr
                notes.append(f"tərcümə köçürüldü → {clean_ctx}: {entry.msgid[:50]!r}")
            catalog.remove(entry)
            dropped += 1

    if (renamed or dropped) and not dry_run:
        catalog.save(path)
    return renamed, dropped, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Zədəli msgctxt girişlərini təmir et")
    parser.add_argument("--dry-run", action="store_true", help="dəyişiklik yazma, yalnız göstər")
    args = parser.parse_args()

    try:
        import polib  # noqa: F401
    except ImportError:
        print("❌ polib lazımdır: pip install polib")
        return 1

    source_map = _source_contexts()
    print(f"Mənbədən {len(source_map)} unikal msgid üçün kontekst çıxarıldı.\n")

    total_renamed = total_dropped = 0
    for lang in LOCALES:
        for domain in DOMAINS:
            path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            if not os.path.exists(path):
                continue
            renamed, dropped, notes = _repair_catalog(path, source_map, args.dry_run)
            total_renamed += renamed
            total_dropped += dropped
            if renamed or dropped:
                print(f"── {domain}/{lang}: {renamed} bərpa, {dropped} silindi")
                for note in notes:
                    print(f"     {note}")

    verb = "olacaq" if args.dry_run else "oldu"
    print(f"\n✅ Cəmi: {total_renamed} kontekst bərpa {verb}, {total_dropped} ölü giriş silindi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
