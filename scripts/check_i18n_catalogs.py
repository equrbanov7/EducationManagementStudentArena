#!/usr/bin/env python3
"""EMSArena i18n kataloq qapısı (CI gate).

Tərcümə regressiyalarını dayandırır. Qapı ratchet prinsipi ilə işləyir:
mövcud borc `scripts/i18n_baseline.json`-da dondurulub; yeni borc ƏLAVƏ etmək
olmaz, borcu azaltmaq isə həmişə olar (baseline `--update` ilə sıxılır).

Yoxlanan meyarlar
-----------------
1. **msgid dəsti eyniliyi** — 4 dilin kataloqunda eyni (msgctxt, msgid) cütləri
   olmalıdır; birində olub digərində olmayan giriş = drift.
2. **Tərcüməsiz (boş msgstr)** — dil üzrə budcə.
3. **Tərcümə olunmamış identity** (`msgstr == msgid`) — YALNIZ qeyri-AZ dillər
   üçün borc sayılır (az kataloqunda msgid AZ mətndir, identity normaldır).
4. **Placeholder uyğunluğu** — msgstr-dəki `%(x)s` / `{x}` dəsti mənbə ilə eyni
   olmalıdır. Uyğunsuzluq runtime `KeyError` deməkdir (bax 2026-07-31 auditi).
5. **Xam açar sızması** — `msgstr` snake_case açarın özüdürsə (məs.
   `visible_test_cases`) istifadəçi UI-da açarı görür.

İstifadə::

    python scripts/check_i18n_catalogs.py            # yoxla (CI)
    python scripts/check_i18n_catalogs.py --update   # baseline-i sıx
    python scripts/check_i18n_catalogs.py --report   # detallı hesabat
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")
SOURCE_LANG = "az"
CATALOGS = ("django", "djangojs")
BASELINE_PATH = os.path.join(BASE, "scripts", "i18n_baseline.json")

PLACEHOLDER_RE = re.compile(r"%\([^)]+\)[sd]|\{[a-zA-Z_][a-zA-Z0-9_]*\}|%[sd]")
RAW_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,}$")


def _load_catalog(lang: str, domain: str):
    import polib

    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
    if not os.path.exists(path):
        return {}
    return {(e.msgctxt or "", e.msgid): e for e in polib.pofile(path) if not e.obsolete}


def _measure(domain: str) -> dict:
    """Domen üzrə cari borc ölçüləri."""
    catalogs = {lang: _load_catalog(lang, domain) for lang in LOCALES}
    source_keys = set(catalogs[SOURCE_LANG])

    metrics: dict[str, dict] = {}
    details: dict[str, dict] = {}
    for lang in LOCALES:
        entries = catalogs[lang]
        missing = sorted(f"{c}|{m}"[:120] for c, m in (source_keys - set(entries)))
        extra = sorted(f"{c}|{m}"[:120] for c, m in (set(entries) - source_keys))

        untranslated, identity, bad_placeholder, raw_keys = [], [], [], []
        for key, entry in entries.items():
            if entry.msgid_plural:
                continue
            msgstr = entry.msgstr or ""
            if not msgstr:
                untranslated.append(key)
                continue
            if lang != SOURCE_LANG and msgstr == entry.msgid:
                identity.append(key)
            # Placeholder etalonu: msgid-də placeholder varsa msgid, yoxsa AZ mətni.
            source_entry = catalogs[SOURCE_LANG].get(key)
            reference = entry.msgid
            if not PLACEHOLDER_RE.search(reference) and source_entry is not None and source_entry.msgstr:
                reference = source_entry.msgstr
            if sorted(PLACEHOLDER_RE.findall(reference)) != sorted(PLACEHOLDER_RE.findall(msgstr)):
                bad_placeholder.append(key)
            if RAW_KEY_RE.fullmatch(msgstr) and RAW_KEY_RE.fullmatch(entry.msgid):
                raw_keys.append(key)

        metrics[lang] = {
            "total": len(entries),
            "missing_vs_source": len(missing),
            "extra_vs_source": len(extra),
            "untranslated": len(untranslated),
            "identity": len(identity),
            "bad_placeholder": len(bad_placeholder),
            "raw_key_leak": len(raw_keys),
        }
        details[lang] = {
            "missing_vs_source": missing[:20],
            "extra_vs_source": extra[:20],
            "bad_placeholder": [f"{c}|{m}"[:120] for c, m in bad_placeholder[:20]],
            "raw_key_leak": [f"{c}|{m}"[:120] for c, m in raw_keys[:20]],
        }
    return {"metrics": metrics, "details": details}


#: Bu ölçülər ARTA BİLMƏZ (ratchet). Azalma həmişə qəbul olunur.
RATCHET_KEYS = ("missing_vs_source", "untranslated", "identity", "bad_placeholder", "raw_key_leak")
#: Bu ölçülər HƏMİŞƏ sıfır olmalıdır (baseline-dan asılı deyil).
HARD_ZERO_KEYS = ("bad_placeholder",)


def _check_mo_freshness() -> list[str]:
    """Commit olunmuş ``.mo`` faylı ``.po`` ilə uyğundurmu.

    Bilinən tələ: msgstr `.po`-da olsa belə, ``compilemessages`` işlədilməsə
    runtime msgid-i hərfi göstərir (məs. sehrbazda `review_title` mətn kimi
    çıxmışdı). `.mo` git-də izləndiyi üçün bu, səssiz regressiya mənbəyidir.
    """
    import polib

    problems: list[str] = []
    for lang in LOCALES:
        for domain in CATALOGS:
            po_path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            mo_path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.mo")
            if not os.path.exists(po_path):
                continue
            if not os.path.exists(mo_path):
                problems.append(f"{domain}/{lang}: .mo faylı YOXDUR — `compilemessages` işlədin")
                continue

            # DİQQƏT: fuzzy girişlər `msgfmt` tərəfindən QƏSDƏN .mo-ya salınmır
            # (etibarsız sayılır) — onları müqayisədən çıxarmasaq hər fuzzy
            # giriş yanlış "köhnəlmiş" siqnalı verər.
            po_map = {
                (e.msgctxt or "", e.msgid): e.msgstr
                for e in polib.pofile(po_path)
                if not e.obsolete and not e.msgid_plural and e.msgstr and "fuzzy" not in e.flags
            }
            mo_map = {
                (e.msgctxt or "", e.msgid): e.msgstr for e in polib.mofile(mo_path) if not e.msgid_plural and e.msgstr
            }
            stale = [key for key, value in po_map.items() if mo_map.get(key) != value]
            if stale:
                sample = ", ".join(f"{c}|{m}"[:60] for c, m in stale[:3])
                problems.append(
                    f"{domain}/{lang}: .mo KÖHNƏDİR — {len(stale)} giriş uyğun gəlmir "
                    f"(məs. {sample}). Düzəliş: python manage.py compilemessages"
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="EMSArena i18n kataloq qapısı")
    parser.add_argument("--update", action="store_true", help="baseline-i cari vəziyyətlə yenilə")
    parser.add_argument("--report", action="store_true", help="detallı hesabat göstər")
    args = parser.parse_args()

    try:
        import polib  # noqa: F401
    except ImportError:
        print("⚠️  polib quraşdırılmayıb — i18n qapısı ötürüldü.")
        return 0

    current = {domain: _measure(domain) for domain in CATALOGS}

    if args.update:
        payload = {domain: current[domain]["metrics"] for domain in CATALOGS}
        with open(BASELINE_PATH, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
            handle.write("\n")
        print(f"✅ Baseline yeniləndi: {BASELINE_PATH}")
        for domain in CATALOGS:
            for lang in LOCALES:
                print(f"   {domain}/{lang}: {current[domain]['metrics'][lang]}")
        return 0

    if not os.path.exists(BASELINE_PATH):
        print(f"❌ Baseline yoxdur: {BASELINE_PATH}\n   Yaratmaq üçün: python {sys.argv[0]} --update")
        return 1

    with open(BASELINE_PATH, encoding="utf-8") as handle:
        baseline = json.load(handle)

    failures: list[str] = _check_mo_freshness()
    improvements: list[str] = []

    for domain in CATALOGS:
        metrics = current[domain]["metrics"]
        base_domain = baseline.get(domain, {})
        for lang in LOCALES:
            actual = metrics[lang]
            expected = base_domain.get(lang, {})
            for key in RATCHET_KEYS:
                now = actual.get(key, 0)
                before = expected.get(key, 0)
                if key in HARD_ZERO_KEYS and now > 0:
                    failures.append(
                        f"{domain}/{lang}: {key} = {now} — SIFIR olmalıdır "
                        f"(placeholder uyğunsuzluğu runtime KeyError deməkdir)"
                    )
                elif now > before:
                    failures.append(f"{domain}/{lang}: {key} {before} → {now} (ARTIB — yeni tərcümə borcu)")
                elif now < before:
                    improvements.append(f"{domain}/{lang}: {key} {before} → {now} ✓")

    if args.report or failures:
        print("── i18n kataloq vəziyyəti ──")
        for domain in CATALOGS:
            for lang in LOCALES:
                print(f"  {domain}/{lang}: {current[domain]['metrics'][lang]}")
        for domain in CATALOGS:
            for lang in LOCALES:
                detail = current[domain]["details"][lang]
                for key, items in detail.items():
                    if items:
                        print(f"  ⚠️  {domain}/{lang}/{key}: {items[:5]}")

    if improvements:
        print("\n✅ Yaxşılaşma (baseline-i sıxmaq üçün --update):")
        for line in improvements[:20]:
            print(f"   {line}")

    if failures:
        print("\n❌ i18n qapısı KEÇMƏDİ:")
        for line in failures:
            print(f"   {line}")
        print("\n   Düzəliş: tərcüməni tamamla və ya (əsaslandırılıbsa) baseline-i --update ilə yenilə.")
        return 1

    print("✅ i18n kataloq qapısı: yeni borc yoxdur.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
