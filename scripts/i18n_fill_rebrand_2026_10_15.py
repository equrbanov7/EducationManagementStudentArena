#!/usr/bin/env python3
"""EMSArena i18n — köhnə məhsul adı istifadəçiyə görünən mətnlərdən çıxarılır (2026-10-15).

Sahib: «EMS Arena köhnədir, onu sil. Olmasın heç yerdə, dəyiş o hissəni.»

Skript üç iş görür (hamısı idempotentdir — ikinci işə salınma heç nə dəyişmir):

1. **ADD** — yeni mətn: e-poçt çərçivəsinin məhsul sözü
   (`email.layout` / «Elektron Universitet», `apps/notifications/templatetags/email_layout.py`).
2. **SET** — işlənən girişlərin köhnə adlı/səhv tərcüməsi düzəldilir:
   * `exams.template.student_exam_list` / `live_kicker` — «EMSARENA LIVE» → «CANLI İMTAHAN»;
   * `exams.template.teacher_exam_detail` / `live_resume_modal_eyebrow` — ru/tr-də səhvən
     «EMSArena qeydiyyat siyasəti» yazılmışdı (az/en/de: «Davam edən canlı sessiya»).
3. **DROP** — kodda artıq ÇAĞIRILMAYAN, köhnə adı daşıyan ölü girişlər bütün 5 kataloqdan
   (django + djangojs) silinir. Onların yerini çoxdan `{{ brand }}` / `%(brand)s` /
   `{{ site_brand_name }}` ilə yazılmış girişlər tutub. Təhlükəsizlik: silinəcək giriş
   mənbə skanerində (`scripts/i18n_source_scan.py`) tapılsa skript DAYANIR.

E-poçt ÜNVANLARI (`info@emsarena.com`, `support@emsarena.com`) məhsul adı deyil, real
poçt qutularıdır — onlara toxunulmur (sahib qərarı gözlənilir).

⚠️ `makemessages` İŞLƏDİLMİR — fayl mətn səviyyəsində dəyişdirilir (polib `save()` bütün
faylı yenidən sarıyıb nəhəng diff yaradardı). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_rebrand_2026_10_15.py
"""

from __future__ import annotations

import os
import re
import sys

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]
DOMAINS = ["django", "djangojs"]

#: Köhnə məhsul adı (EMS Arena / EMSArena / EMS-Arena / Ems Arena …), registrsiz.
OLD_NAME_RE = re.compile(r"ems[ _-]?arena", re.IGNORECASE)
#: Poçt ünvanları məhsul adı sayılmır (real qutulardır).
ADDRESS_RE = re.compile(r"[\w.+-]*@emsarena\.com", re.IGNORECASE)

ADD = {
    ("email.layout", "Elektron Universitet"): {
        "az": "Elektron Universitet",
        "en": "e-University",
        "ru": "Электронный университет",
        "tr": "Elektronik Üniversite",
        "de": "Elektronische Universität",
    },
}

SET = {
    ("exams.template.student_exam_list", "live_kicker"): {
        "az": "CANLI İMTAHAN",
        "en": "LIVE EXAM",
        "ru": "ЖИВОЙ ЭКЗАМЕН",
        "tr": "CANLI SINAV",
        "de": "LIVE-PRÜFUNG",
    },
    ("exams.template.teacher_exam_detail", "live_resume_modal_eyebrow"): {
        "ru": "Идёт живая сессия",
        "tr": "Devam eden canlı oturum",
    },
}

#: Mətni (msgid) köhnə adı daşımayan, amma tərcüməsi daşıyan ölü girişlər.
DEAD_KEYS = {
    ("accounts.register", "privacy_card_description"),
    ("accounts.register", "privacy_modal_eyebrow"),
    ("accounts.register", "privacy_modal_intro"),
    ("exams.wizard", "rail_kicker"),
}


def has_old_name(text: str) -> bool:
    return bool(OLD_NAME_RE.search(ADDRESS_RE.sub("", text or "")))


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# ---------------------------------------------------------------------------
# Mətn səviyyəsində PO blok analizi
# ---------------------------------------------------------------------------
_KEYWORD_RE = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+"(.*)"\s*$')
_CONT_RE = re.compile(r'^"(.*)"\s*$')


def parse_block(block: str):
    """Blokun sahələri: ``{"msgctxt": …, "msgid": …, "msgstr": …}`` və msgstr sətir aralığı.

    Şərh/obsolete (``#``, ``#~``) sətirləri buraxılır. Giriş deyilsə ``None``.
    """
    fields, spans, current = {}, {}, None
    lines = block.split("\n")
    for index, line in enumerate(lines):
        if line.startswith("#"):
            current = None
            continue
        match = _KEYWORD_RE.match(line)
        if match:
            current = match.group(1)
            fields[current] = polib.unescape(match.group(2))
            spans[current] = [index, index]
            continue
        match = _CONT_RE.match(line)
        if match and current:
            fields[current] += polib.unescape(match.group(1))
            spans[current][1] = index
    if "msgid" not in fields:
        return None
    return fields, spans, lines


def split_blocks(text: str):
    """``[blok, ayırıcı, blok, ayırıcı, …]`` — ayırıcılar olduğu kimi saxlanılır."""
    return re.split(r"(\n[ \t]*\n+)", text)


def collect_drop_keys(domain_entries):
    """Silinəcək ``(ctx, msgid)`` dəsti (az kataloqu üzrə, bütün dillərə tətbiq olunur)."""
    keys = set()
    for entry in domain_entries:
        if entry.obsolete:
            continue
        key = (entry.msgctxt or "", entry.msgid)
        if has_old_name(entry.msgid) or has_old_name(entry.msgid_plural or "") or key in DEAD_KEYS:
            keys.add(key)
    return keys


def _source_keys():
    """Kodda çağırılan ``(ctx, msgid)`` dəsti (domen üzrə) — `check_i18n_catalogs`-in skaneri."""
    if BASE not in sys.path:
        sys.path.insert(0, BASE)
    from scripts.check_i18n_catalogs import _source_msgids

    found = _source_msgids()
    if found is False:
        raise SystemExit("Mənbə skaneri işləmədi — silmə təhlükəsiz yoxlanıla bilmir, dayanıram.")
    return {domain: {(ctx or "", msgid) for ctx, msgid in pairs} for domain, pairs in found.items()}


def process(lang, domain, drop_keys):
    path = po_path(lang, domain)
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    parts = split_blocks(text)
    out, dropped, updated = [], 0, 0
    seen = set()
    index = 0
    while index < len(parts):
        block = parts[index]
        sep = parts[index + 1] if index + 1 < len(parts) else ""
        parsed = parse_block(block)
        if parsed:
            fields, spans, lines = parsed
            key = (fields.get("msgctxt", ""), fields["msgid"])
            is_obsolete = all(line.startswith("#") or not line.strip() for line in lines)
            if not is_obsolete and key[1]:
                seen.add(key)
                if key in drop_keys:
                    dropped += 1
                    index += 2
                    continue
                new_value = SET.get(key, {}).get(lang)
                if new_value is not None and fields.get("msgstr") != new_value and "msgstr" in spans:
                    start, end = spans["msgstr"]
                    lines[start : end + 1] = [f'msgstr "{esc(new_value)}"']
                    block = "\n".join(lines)
                    updated += 1
        out.append(block)
        out.append(sep)
        index += 2

    added = 0
    new_blocks = []
    if domain == "django":
        for (ctx, msgid), translations in ADD.items():
            if (ctx, msgid) in seen:
                continue
            msgstr = translations.get(lang) or translations["az"]
            new_blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    result = "".join(out)
    if new_blocks:
        result = result.rstrip("\n") + "\n\n" + "\n".join(new_blocks)
    if result != text:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(result)
    print(f"{lang}/{domain}: +{added} add, ~{updated} set, -{dropped} drop")


def main():
    source = _source_keys()
    for domain in DOMAINS:
        az_path = po_path("az", domain)
        drop_keys = collect_drop_keys(polib.pofile(az_path))
        used = sorted(drop_keys & source.get(domain, set()))
        if used:
            raise SystemExit(f"{domain}: silinəcək girişlər kodda İŞLƏNİR, dayanıram: {used[:5]}")
        for lang in LOCALES:
            process(lang, domain, drop_keys)


if __name__ == "__main__":
    main()
