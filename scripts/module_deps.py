#!/usr/bin/env python3
"""Modul-sərhəd ratchet gate-i (M1, audit yol xəritəsi 2026-07-02).

Nə edir (statik analiz, kod icra olunmur):
  * apps/<modul> daxilindəki (tests/migrations xaric) `from apps.X ...`
    importlarından modul-asılılıq qrafını qurur;
  * core/ daxilindən apps-a gedən importları ayrıca sayır (shared-kernel
    təmizliyi ratchet-i).

Rejimlər (scripts/check_module_size.py ilə eyni fəlsəfə):
  report   (default)  — matrisi və dövri cütləri çap edir
  --check             — baseline ilə müqayisə: YENİ dövri cüt və ya core→apps
                        YENİ hədəf modul → exit 1 (CI gate)
  --update            — baseline-i cari vəziyyətə yazır (yalnız şüurlu halda,
                        review-da əsaslandırın)

Baseline: scripts/module_deps_baseline.json
Məqsəd: mövcud 18 dövri cüt DONDURULUB — sayı yalnız AZALA bilər.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "module_deps_baseline.json"
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+apps\.(\w+)", re.MULTILINE)


def _iter_py(base: Path):
    for p in base.rglob("*.py"):
        s = str(p)
        if "/migrations/" in s or "/tests/" in s or s.endswith("/tests.py") or "__pycache__" in s:
            continue
        yield p


def build_graph():
    deps: dict[str, set[str]] = defaultdict(set)
    apps_dir = REPO_ROOT / "apps"
    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith("__"):
            continue
        src = app_dir.name
        for p in _iter_py(app_dir):
            for tgt in IMPORT_RE.findall(p.read_text(encoding="utf-8")):
                if tgt != src:
                    deps[src].add(tgt)

    core_to_apps: set[str] = set()
    for p in _iter_py(REPO_ROOT / "core"):
        core_to_apps.update(IMPORT_RE.findall(p.read_text(encoding="utf-8")))
    return deps, core_to_apps


def cycles_of(deps) -> set[str]:
    return {f"{a}<->{b}" for a in deps for b in deps[a] if a < b and a in deps.get(b, set())}


def snapshot():
    deps, core_to_apps = build_graph()
    return {
        "cycles": sorted(cycles_of(deps)),
        "core_to_apps": sorted(core_to_apps),
        "edges": {k: sorted(v) for k, v in sorted(deps.items())},
    }


def cmd_report(snap):
    print("Modul → asılı olduğu modullar:")
    for a, targets in snap["edges"].items():
        print(f"  {a:20s} → {', '.join(targets) or '—'}")
    print(f"\nDövri cütlər ({len(snap['cycles'])}):")
    for c in snap["cycles"]:
        print(f"  {c}")
    print(f"\ncore → apps hədəfləri ({len(snap['core_to_apps'])}): {', '.join(snap['core_to_apps'])}")


def cmd_check(snap) -> int:
    if not BASELINE_PATH.exists():
        print("❌ Baseline yoxdur. Əvvəl: python scripts/module_deps.py --update")
        return 1
    base = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    new_cycles = sorted(set(snap["cycles"]) - set(base["cycles"]))
    new_core = sorted(set(snap["core_to_apps"]) - set(base["core_to_apps"]))
    ok = True
    if new_cycles:
        ok = False
        print("❌ YENİ dövri modul cüt(lər)i (baseline-da yoxdur):")
        for c in new_cycles:
            print(f"   {c}")
    if new_core:
        ok = False
        print("❌ core/ YENİ app modullarına import edir (shared-kernel pozuntusu):")
        for m in new_core:
            print(f"   core → apps.{m}")
    if ok:
        healed = sorted(set(base["cycles"]) - set(snap["cycles"]))
        extra = f" (baseline-dan {len(healed)} dövr sağalıb — --update ilə kilidləyin)" if healed else ""
        print(f"✅ Modul-sərhəd gate-i: yeni dövr yoxdur ({len(snap['cycles'])} dondurulmuş){extra}")
    else:
        print("\nHəll: importu modulun public fasadı/servisi ilə əvəz edin; qəti zərurət")
        print("varsa --update ilə baseline-i böyüdüb PR-da əsaslandırın.")
    return 0 if ok else 1


def main() -> int:
    snap = snapshot()
    if "--update" in sys.argv:
        BASELINE_PATH.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(
            f"Baseline yazıldı: {BASELINE_PATH.name} ({len(snap['cycles'])} dövr, core→apps: {len(snap['core_to_apps'])})"
        )
        return 0
    if "--check" in sys.argv:
        return cmd_check(snap)
    cmd_report(snap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
