#!/usr/bin/env python3
"""Module-size budget guard — \"god-file\"-ların yenidən böyüməsinin qarşısını alır.

Niyə?
-----
Böyük tək-fayllı modullar (2000+ sətir view/servis faylları) oxunması, test
edilməsi və təhlükəsiz dəyişdirilməsi çətin olur. Bu yoxlama:

* YENİ fayllar üçün sərt limit qoyur (``SOFT_CAP`` = 600 sətir).
* Mövcud böyük faylları cari ölçüsündə "dondurur" (ratchet): onlar BÖYÜYƏ
  bilməz — yalnız kiçilə bilər. Baseline ``module_size_budget.json``-da saxlanılır.

Beləliklə AI agentləri və ya developerlər sonradan task həll edərkən bu fayllara
yeni sətir əlavə edib onları daha da şişirdə bilmir; məntiqi yeni/kiçik modullara
çıxarmağa məcbur olurlar.

İstifadə
--------
    python scripts/check_module_size.py --check     # CI / pre-commit (default)
    python scripts/check_module_size.py --update     # bölgüdən sonra baseline-i yenilə

Bir faylı şüurlu olaraq böyütmək lazımdırsa: əvvəlcə onu bölün; mümkün deyilsə,
``--update`` ilə baseline-i yeniləyin və dəyişikliyi review-da əsaslandırın.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Layihə kökü (bu fayl scripts/ altındadır).
ROOT = Path(__file__).resolve().parent.parent
BUDGET_FILE = Path(__file__).resolve().parent / "module_size_budget.json"

# Skan olunan kök qovluqlar.
SOURCE_DIRS = ["apps", "core", "config"]

# Yeni (baseline-də olmayan) fayllar üçün sərt yuxarı hədd.
SOFT_CAP = 600

# Bu yol fraqmentlərini ehtiva edən fayllar yoxlanmır.
EXCLUDE_PARTS = ("/migrations/", "/__pycache__/", "/tests/")
EXCLUDE_NAME_PREFIX = ("test_",)
EXCLUDE_NAME_EXACT = ("tests.py",)


def _is_excluded(rel: str, name: str) -> bool:
    posix = "/" + rel.replace("\\", "/")
    if any(part in posix for part in EXCLUDE_PARTS):
        return True
    if name in EXCLUDE_NAME_EXACT:
        return True
    if any(name.startswith(p) for p in EXCLUDE_NAME_PREFIX):
        return True
    return False


def _count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def _iter_py_files():
    for d in SOURCE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel = str(path.relative_to(ROOT))
            if _is_excluded(rel, path.name):
                continue
            yield rel, path


def _load_budget() -> dict:
    if BUDGET_FILE.exists():
        return json.loads(BUDGET_FILE.read_text(encoding="utf-8")).get("budgets", {})
    return {}


def update_baseline() -> int:
    """Hazırkı vəziyyəti baseline kimi yaz: SOFT_CAP-dən böyük hər fayl dondurulur."""
    budgets = {}
    for rel, path in _iter_py_files():
        n = _count_lines(path)
        if n > SOFT_CAP:
            budgets[rel] = n
    payload = {
        "_comment": (
            "Avtomatik yaradılır: python scripts/check_module_size.py --update. "
            f"SOFT_CAP={SOFT_CAP}. Buradakı fayllar grandfathered-dir (cari ölçüdə "
            "dondurulub) və yalnız kiçilə bilər. Yeni böyük fayl əlavə etmək üçün "
            "əvvəlcə onu bölün."
        ),
        "soft_cap": SOFT_CAP,
        "budgets": dict(sorted(budgets.items())),
    }
    BUDGET_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ Baseline yeniləndi: {len(budgets)} fayl, {BUDGET_FILE.relative_to(ROOT)}")
    return 0


def check() -> int:
    budgets = _load_budget()
    over_cap = []  # baseline-də olmayan + SOFT_CAP-i keçən (yeni şişmiş fayl)
    over_budget = []  # baseline faylı öz budcəsini keçib (böyüyüb)
    shrunk = []  # baseline faylı kiçilib → budcəni sıxmaq olar (informativ)

    for rel, path in _iter_py_files():
        n = _count_lines(path)
        if rel in budgets:
            budget = budgets[rel]
            if n > budget:
                over_budget.append((rel, n, budget))
            elif n < budget - 40:
                shrunk.append((rel, n, budget))
        elif n > SOFT_CAP:
            over_cap.append((rel, n))

    ok = not over_cap and not over_budget

    if over_cap:
        print(f"\n❌ YENİ fayllar SOFT_CAP={SOFT_CAP} sətir limitini keçir:")
        for rel, n in sorted(over_cap, key=lambda x: -x[1]):
            print(f"   {n:>5}  {rel}")
        print("   → Məntiqi alt-modullara bölün (servis/helper/view) və ya paketə çevirin.")

    if over_budget:
        print("\n❌ Mövcud fayllar dondurulmuş budcəni keçib (BÖYÜYÜB):")
        for rel, n, b in sorted(over_budget, key=lambda x: -(x[1] - x[2])):
            print(f"   {n:>5} > {b:<5} (+{n - b})  {rel}")
        print("   → Yeni kodu ayrı modula çıxarın. Şüurlu böyütmə lazımdırsa:")
        print("     python scripts/check_module_size.py --update  (və review-da əsaslandırın)")

    if shrunk:
        print("\nℹ️  Bu fayllar kiçilib — baseline-i sıxmaq tövsiyə olunur (--update):")
        for rel, n, b in sorted(shrunk, key=lambda x: x[1] - x[2]):
            print(f"   {n:>5} (budcə {b})  {rel}")

    if ok:
        print(f"✅ Modul ölçü budcəsi: bütün fayllar limit daxilindədir (SOFT_CAP={SOFT_CAP}).")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Module-size budget guard.")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="Budcəni yoxla (default).")
    g.add_argument("--update", action="store_true", help="Baseline budcəni yenidən yaz.")
    args = parser.parse_args()
    if args.update:
        return update_baseline()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
