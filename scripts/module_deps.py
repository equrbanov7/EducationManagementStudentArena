#!/usr/bin/env python3
"""Modul-sərhəd ratchet gate-i (M1, audit yol xəritəsi 2026-07-02).

Nə edir (statik analiz, kod icra olunmur):
  * apps/<modul> daxilindəki (tests/migrations xaric) absolute Python
    importlarından AST ilə modul-asılılıq qrafını qurur;
  * core/ daxilindən apps-a gedən importları ayrıca sayır (shared-kernel
    təmizliyi ratchet-i).

Rejimlər (scripts/check_module_size.py ilə eyni fəlsəfə):
  report   (default)  — matrisi və dövri cütləri çap edir
  --check             — baseline ilə müqayisə: YENİ dövri kənar və ya core→apps
                        YENİ hədəf modul → exit 1 (CI gate)
  --update            — baseline-i cari vəziyyətə yazır (yalnız şüurlu halda,
                        review-da əsaslandırın)

Baseline: scripts/module_deps_baseline.json
Məqsəd: baseline-dakı dövri kənarlar yalnız AZALA bilər.
AST adi absolute importları yoxlayır; runtime hook-lar ayrıca dizayn review tələb edir.
"""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from importlib.util import resolve_name
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "module_deps_baseline.json"


def imported_apps(source: str, package=None) -> set[str]:
    """Parse real absolute imports, including aliases and multi-import statements."""
    targets = set()
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level and package is None:
                continue
            module = resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module
            if module == "apps":
                names = ["apps." + alias.name for alias in node.names]
            else:
                names = [module or ""]
        for name in names:
            parts = name.split(".")
            if len(parts) > 1 and parts[0] == "apps":
                targets.add(parts[1])
    return targets


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
            for tgt in imported_apps(p.read_text(encoding="utf-8"), ".".join(p.relative_to(REPO_ROOT).parent.parts)):
                if tgt != src:
                    deps[src].add(tgt)

    core_to_apps: set[str] = set()
    for p in _iter_py(REPO_ROOT / "core"):
        core_to_apps.update(
            imported_apps(p.read_text(encoding="utf-8"), ".".join(p.relative_to(REPO_ROOT).parent.parts))
        )
    return deps, core_to_apps


def cycles_of(deps) -> set[str]:
    return {f"{a}<->{b}" for a in deps for b in deps[a] if a < b and a in deps.get(b, set())}


def cyclic_edges(deps) -> set[tuple[str, str]]:
    """Return every edge with a return path, including cycles longer than two."""

    def reaches(start, target):
        pending, visited = [start], set()
        while pending:
            node = pending.pop()
            if node == target:
                return True
            if node not in visited:
                visited.add(node)
                pending.extend(deps.get(node, ()))
        return False

    return {(src, dst) for src, targets in deps.items() for dst in targets if reaches(dst, src)}


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
    print(f"\nBütün dövrlərə daxil olan kənarlar: {len(cyclic_edges(snap['edges']))}")
    print(f"\ncore → apps hədəfləri ({len(snap['core_to_apps'])}): {', '.join(snap['core_to_apps'])}")


def cmd_check(snap) -> int:
    if not BASELINE_PATH.exists():
        print("❌ Baseline yoxdur. Əvvəl: python scripts/module_deps.py --update")
        return 1
    base = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    new_cycles = sorted(set(snap["cycles"]) - set(base["cycles"]))
    new_core = sorted(set(snap["core_to_apps"]) - set(base["core_to_apps"]))
    # Existing edge inventory is the ratchet: do not silently bless longer cycles.
    new_cyclic_edges = sorted(cyclic_edges(snap["edges"]) - cyclic_edges(base["edges"]))
    ok = True
    if new_cyclic_edges:
        ok = False
        print("❌ Yeni dövri asılılıq kənarları (istənilən uzunluqda dövr):")
        for src, dst in new_cyclic_edges:
            print(f"   {src} → {dst}")
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
