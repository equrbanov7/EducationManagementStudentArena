#!/usr/bin/env python3
"""EMSArena i18n — mövcud olmayan poçt qutuları çıxarıldı 2026-10-16.

Sahib: `info@` / `support@` / `no-reply@emsarena.com` (və `info@`/`support@qku.edu.az`)
qutuları YOXDUR; cavablar sistemin real M365 qutusundan gedir. Skript iki iş görür:

1. **ADD** — yeni mətnlər (kontekstsiz, AZ msgid):
   * «Cavab sistemin rəsmi poçt qutusundan gedəcək.» — işçi bildiriş məktubları
     (əlaqə + sınaq), admin cavab səhifələri, profil «Əlaqə mesajları» bölməsi;
   * `reply_from` seçimlərinin neytral adları — «Əsas poçt qutusu», «Köhnə dəstək ünvanı».
2. **DROP** — `@emsarena.com` ünvanını daşıyan və kodda artıq ÇAĞIRILMAYAN ölü girişlər
   (köhnə seçim adları, «Cavab müştəriyə info@ və ya support@emsarena.com-dan gedəcək …»)
   bütün 5 kataloqdan (django + djangojs) silinir. Təhlükəsizlik: giriş mənbə skanerində
   (`scripts/i18n_source_scan.py`) tapılarsa silinmir.

İdempotentdir. ⚠️ `makemessages` İŞLƏDİLMİR — fayl mətn səviyyəsində dəyişdirilir.
Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_mailboxes_2026_10_16.py
"""

from __future__ import annotations

import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from scripts.i18n_fill_rebrand_2026_10_15 import _source_keys, esc, parse_block, split_blocks  # noqa: E402

LOCALES = ["az", "en", "ru", "tr", "de"]
DOMAINS = ["django", "djangojs"]
DEAD_ADDRESS_RE = re.compile(r"@emsarena\.com", re.IGNORECASE)

# (ctx, msgid) → {lang: msgstr}; "az" verilməyibsə az msgstr = msgid.
ADD = {
    ("", "Cavab sistemin rəsmi poçt qutusundan gedəcək."): {
        "en": "The reply will be sent from the system's official mailbox.",
        "ru": "Ответ будет отправлен с официального почтового ящика системы.",
        "tr": "Yanıt sistemin resmî e-posta kutusundan gönderilecek.",
        "de": "Die Antwort wird vom offiziellen Postfach des Systems gesendet.",
    },
    ("", "Əsas poçt qutusu"): {
        "en": "Main mailbox",
        "ru": "Основной почтовый ящик",
        "tr": "Ana e-posta kutusu",
        "de": "Hauptpostfach",
    },
    ("", "Köhnə dəstək ünvanı"): {
        "en": "Former support address",
        "ru": "Прежний адрес поддержки",
        "tr": "Eski destek adresi",
        "de": "Frühere Support-Adresse",
    },
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def process(lang, domain, used_keys):
    path = po_path(lang, domain)
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    parts = split_blocks(text)
    out, seen, dropped, kept_used = [], set(), 0, 0
    for index in range(0, len(parts), 2):
        block = parts[index]
        sep = parts[index + 1] if index + 1 < len(parts) else ""
        parsed = parse_block(block)
        if parsed:
            fields, _spans, lines = parsed
            key = (fields.get("msgctxt", ""), fields["msgid"])
            is_obsolete = all(line.startswith("#") or not line.strip() for line in lines)
            if not is_obsolete and key[1]:
                seen.add(key)
                if DEAD_ADDRESS_RE.search(key[1]) or DEAD_ADDRESS_RE.search(fields.get("msgstr", "")):
                    if key in used_keys:
                        kept_used += 1
                    else:
                        dropped += 1
                        continue
        out.append(block)
        out.append(sep)

    new_blocks = []
    if domain == "django":
        for (ctx, msgid), translations in ADD.items():
            if (ctx, msgid) in seen:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            ctx_line = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            new_blocks.append(f'{ctx_line}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')

    result = "".join(out)
    if new_blocks:
        result = result.rstrip("\n") + "\n\n" + "\n".join(new_blocks)
    if result != text:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(result)
    note = f", {kept_used} still used (kept)" if kept_used else ""
    print(f"{lang}/{domain}: +{len(new_blocks)} add, -{dropped} drop{note}")


def main():
    source = _source_keys()
    for domain in DOMAINS:
        for lang in LOCALES:
            process(lang, domain, source.get(domain, set()))


if __name__ == "__main__":
    main()
