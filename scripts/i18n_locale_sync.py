#!/usr/bin/env python3
"""Bir dilin kataloqunu AZ mənbə kataloqu ilə sinxronlaşdıran alət (2026-10-13 (gecə), «de» dili).

Niyə lazımdır
-------------
Gecə agentləri yeni mətnləri ``scripts/i18n_fill_<slug>_<tarix>.py`` skriptləri ilə
YALNIZ az/en/ru/tr kataloqlarına yazır. Alman dili (``de``) sonradan əlavə olunduğu üçün
həmin skriptlərin çoxu ``de``-ni tanımır — birləşmə (merge) vaxtı ``de`` kataloqunda həmin
mətnlər əskik qalır (`check_i18n_catalogs.py` → ``missing_vs_source`` artır və qapı qırmızı
olur). Bu alət o boşluğu iki addımda bağlayır:

1. ``export`` — AZ kataloqunda olub hədəf dildə OLMAYAN / boş girişləri (``--include-identity``
   ilə AZ surəti olanları da) unikal ``(EN mətn, AZ mətn)`` cütləri kimi JSON partiyalarına çıxarır
   (tərcüməçi — insan və ya agent — EN-i pivot, AZ-ı həqiqət mənbəyi kimi görür).
2. ``apply`` — tərcümə olunmuş partiyaları (``{"<id>": "mətn"}``) oxuyur, placeholder-ləri
   qapının ÖZ qaydası ilə yoxlayır və hədəf kataloqu AZ-ın sırası/strukturu ilə yenidən
   yazır (AZ-da olmayan köhnə girişlər atılır → ``extra_vs_source`` = 0). Mövcud boş olmayan
   tərcümələr yeni dəyər gəlmədikcə toxunulmaz qalır.

Placeholder (``%(x)s``, ``%s``, ``{x}``) və HTML teq dəsti uyğun gəlməyən tərcümə QƏBUL
OLUNMUR — hesabatda göstərilir və giriş boş qalır (runtime ``KeyError`` riskindən yaxşıdır).

İstifadə::

    python scripts/i18n_locale_sync.py export --lang de --out /tmp/de_batches --batch-size 500
    # … /tmp/de_batches/django_000.json → /tmp/de_out/django_000.json ({"id": "Deutsch"}) …
    python scripts/i18n_locale_sync.py apply --lang de --batches /tmp/de_batches --translations /tmp/de_out
    python manage.py compilemessages -l de -i .claude -i venv
    python scripts/check_i18n_catalogs.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_LANG = "az"
PIVOT_LANG = "en"
CATALOGS = ("django", "djangojs")
#: Qapı ilə EYNİ regex (scripts/check_i18n_catalogs.py) — fərqli olsa alət «keçər», qapı yıxılardı.
PLACEHOLDER_RE = re.compile(r"%\([^)]+\)[sd]|\{[a-zA-Z_][a-zA-Z0-9_]*\}|%[sd]")
TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)\b")

LANG_META = {
    # Plural-Forms: alman dilində 2 forma, «n != 1» (gettext standartı).
    "de": {"team": "German", "plural": "nplurals=2; plural=(n != 1);"},
}


def _po_path(lang: str, domain: str) -> str:
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def _load(lang: str, domain: str):
    import polib

    path = _po_path(lang, domain)
    if not os.path.exists(path):
        return None
    return polib.pofile(path)


def _index(po) -> dict:
    if po is None:
        return {}
    return {(e.msgctxt or "", e.msgid): e for e in po if not e.obsolete}


def _is_filled(entry, az_entry) -> bool:
    """Hədəf girişində (boş olmayan) tərcümə varmı."""
    if entry is None:
        return False
    if az_entry.msgid_plural:
        return all(entry.msgstr_plural.get(i) for i in (0, 1))
    return bool(entry.msgstr)


def _needs_work(entry, az_entry, include_identity: bool = False) -> bool:
    """Hədəf girişi tərcümə tələb edirmi (yox / boş; istəyə görə AZ msgid-in eyni surəti də).

    Identity (``msgstr == msgid``) defolt olaraq iş sayılmır: «Status», «Rektor», «PDF» kimi
    sözlər alman dilində də eynidir və hər ixracda təkrar tərcüməyə düşməməlidir.
    """
    if not _is_filled(entry, az_entry):
        return True
    if not include_identity or az_entry.msgid_plural:
        return False
    # Qapının `identity` meyarı: msgid AZ mətnidirsə (az msgstr == msgid) surət borcdur.
    return entry.msgstr == entry.msgid and (az_entry.msgstr == entry.msgid or not az_entry.msgstr)


def _pair_key(az_entry, en_entry) -> str:
    """Dedup açarı: eyni (EN, AZ) mətni bir dəfə tərcümə olunur."""
    if az_entry.msgid_plural:
        en_forms = [en_entry.msgstr_plural.get(i, "") for i in (0, 1)] if en_entry else ["", ""]
        az_forms = [az_entry.msgstr_plural.get(i, "") for i in (0, 1)]
        return json.dumps(["P", en_forms, az_forms, az_entry.msgid, az_entry.msgid_plural], ensure_ascii=False)
    en_text = en_entry.msgstr if en_entry is not None else ""
    return json.dumps(["S", en_text, az_entry.msgstr or az_entry.msgid], ensure_ascii=False)


def cmd_export(args) -> int:
    os.makedirs(args.out, exist_ok=True)
    total = 0
    for domain in CATALOGS:
        az = _index(_load(SOURCE_LANG, domain))
        en = _index(_load(PIVOT_LANG, domain))
        target = _index(_load(args.lang, domain))
        items: dict[str, dict] = {}
        for key, az_entry in az.items():
            if not _needs_work(target.get(key), az_entry, include_identity=args.include_identity):
                continue
            en_entry = en.get(key)
            pk = _pair_key(az_entry, en_entry)
            if pk in items:
                continue
            item = {"ctx": key[0], "msgid": key[1]}
            if az_entry.msgid_plural:
                item["plural"] = True
                item["en"] = [en_entry.msgstr_plural.get(i, "") for i in (0, 1)] if en_entry else []
                item["az"] = [az_entry.msgstr_plural.get(i, "") or az_entry.msgid for i in (0, 1)]
            else:
                item["en"] = en_entry.msgstr if en_entry is not None else ""
                item["az"] = az_entry.msgstr or az_entry.msgid
            items[pk] = item
        rows = list(items.items())
        for start in range(0, len(rows), args.batch_size):
            chunk = rows[start : start + args.batch_size]
            batch = {f"{domain}_{start + n}": dict(item, pair=pk) for n, (pk, item) in enumerate(chunk)}
            name = os.path.join(args.out, f"{domain}_{start // args.batch_size:03d}.json")
            with open(name, "w", encoding="utf-8") as handle:
                json.dump(batch, handle, ensure_ascii=False, indent=1)
        print(f"{domain}: {len(rows)} unikal mətn ixrac olundu")
        total += len(rows)
    print(f"Cəmi: {total}")
    return 0


def _placeholders(text: str) -> list[str]:
    return sorted(PLACEHOLDER_RE.findall(text or ""))


def _tags(text: str) -> list[str]:
    return sorted(t.lower() for t in TAG_RE.findall(text or ""))


def _validate(item: dict, value) -> str | None:
    """Uyğunsuzluq varsa səbəbi qaytarır."""
    if item.get("plural"):
        if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) and v for v in value)):
            return "plural: 2 elementli siyahı gözlənilirdi"
        # Django-da tək forma sayı (%(count)s) buraxa bilər — yalnız «other» formasını sərt yoxlayırıq.
        ref = item["en"][1] if item.get("en") else item["az"][1]
        if set(_placeholders(value[1])) != set(_placeholders(ref)):
            return f"plural placeholder: {_placeholders(ref)} ≠ {_placeholders(value[1])}"
        return None
    if not isinstance(value, str) or not value.strip():
        return "boş tərcümə"
    # Qapı etalonu: msgid-də placeholder varsa msgid, yoxsa AZ mətni.
    ref = item["msgid"] if PLACEHOLDER_RE.search(item["msgid"]) else item["az"]
    if _placeholders(ref) != _placeholders(value):
        return f"placeholder: {_placeholders(ref)} ≠ {_placeholders(value)}"
    source_tags = _tags(item["en"] or item["az"])
    if source_tags and _tags(value) != source_tags:
        return f"HTML teq: {source_tags} ≠ {_tags(value)}"
    return None


def _load_translations(batches_dir: str, translations_dir: str) -> tuple[dict, list[str]]:
    """``{pair_key: dəyər}`` + rədd olunanların siyahısı."""
    accepted: dict[str, object] = {}
    rejected: list[str] = []
    for name in sorted(os.listdir(batches_dir)):
        if not name.endswith(".json"):
            continue
        out_path = os.path.join(translations_dir, name)
        if not os.path.exists(out_path):
            continue
        with open(os.path.join(batches_dir, name), encoding="utf-8") as handle:
            batch = json.load(handle)
        with open(out_path, encoding="utf-8") as handle:
            done = json.load(handle)
        for item_id, item in batch.items():
            if item_id not in done:
                continue
            value = done[item_id]
            problem = _validate(item, value)
            if problem:
                rejected.append(f"{name}:{item_id}: {problem} :: {str(value)[:90]}")
                continue
            accepted[item["pair"]] = value
    return accepted, rejected


def _header(lang: str, template_po) -> dict:
    meta = dict(template_po.metadata) if template_po is not None else {}
    info = LANG_META.get(lang, {})
    meta.update(
        {
            "Project-Id-Version": meta.get("Project-Id-Version", "EMSArena"),
            "Language": lang,
            "Language-Team": info.get("team", lang),
            "MIME-Version": "1.0",
            "Content-Type": "text/plain; charset=UTF-8",
            "Content-Transfer-Encoding": "8bit",
        }
    )
    if info.get("plural"):
        meta["Plural-Forms"] = info["plural"]
    return meta


def cmd_apply(args) -> int:
    import polib

    accepted, rejected = _load_translations(args.batches, args.translations)
    stats = {}
    for domain in CATALOGS:
        az_po = _load(SOURCE_LANG, domain)
        en = _index(_load(PIVOT_LANG, domain))
        old_po = _load(args.lang, domain)
        old = _index(old_po)
        new_po = polib.POFile()
        new_po.header = old_po.header if old_po is not None else az_po.header
        new_po.metadata = _header(args.lang, old_po if old_po is not None else az_po)
        filled = empty = 0
        for az_entry in az_po:
            if az_entry.obsolete:
                continue
            key = (az_entry.msgctxt or "", az_entry.msgid)
            prev = old.get(key)
            entry = polib.POEntry(
                msgctxt=az_entry.msgctxt,
                msgid=az_entry.msgid,
                msgid_plural=az_entry.msgid_plural,
                occurrences=list(az_entry.occurrences),
                comment=az_entry.comment,
                tcomment=prev.tcomment if prev is not None else "",
                flags=[f for f in az_entry.flags if f != "fuzzy"],
            )
            value = accepted.get(_pair_key(az_entry, en.get(key)))
            if az_entry.msgid_plural:
                if value is None and _is_filled(prev, az_entry):
                    value = [prev.msgstr_plural.get(0, ""), prev.msgstr_plural.get(1, "")]
                entry.msgstr_plural = {0: value[0], 1: value[1]} if value else {0: "", 1: ""}
            else:
                if value is None and _is_filled(prev, az_entry):
                    value = prev.msgstr
                entry.msgstr = value or ""
            if value:
                filled += 1
            else:
                empty += 1
            new_po.append(entry)
        os.makedirs(os.path.dirname(_po_path(args.lang, domain)), exist_ok=True)
        new_po.save(_po_path(args.lang, domain))
        stats[domain] = (filled, empty)
    for domain, (filled, empty) in stats.items():
        print(f"{domain}/{args.lang}: dolu={filled} boş={empty}")
    if rejected:
        print(f"⚠️  Rədd olunan tərcümələr: {len(rejected)}")
        for line in rejected[: args.show]:
            print("   ", line)
        if args.rejected_out:
            with open(args.rejected_out, "w", encoding="utf-8") as handle:
                handle.write("\n".join(rejected) + "\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Dil kataloqunu AZ mənbəyi ilə sinxronlaşdır")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="tərcümə tələb edən girişləri JSON partiyalarına çıxar")
    exp.add_argument("--lang", required=True)
    exp.add_argument("--out", required=True)
    exp.add_argument("--batch-size", type=int, default=500)
    exp.add_argument(
        "--include-identity",
        action="store_true",
        help="msgstr == msgid (AZ surəti) olan girişləri də ixrac et (defolt: yalnız əskik/boş)",
    )
    app = sub.add_parser("apply", help="tərcümə olunmuş partiyaları kataloqa yaz")
    app.add_argument("--lang", required=True)
    app.add_argument("--batches", required=True)
    app.add_argument("--translations", required=True)
    app.add_argument("--show", type=int, default=30)
    app.add_argument("--rejected-out", default="")
    args = parser.parse_args()
    if args.lang == SOURCE_LANG:
        print("❌ Mənbə dili (az) bu alətlə yazılmır.")
        return 2
    return cmd_export(args) if args.command == "export" else cmd_apply(args)


if __name__ == "__main__":
    sys.exit(main())
