#!/usr/bin/env python3
"""Ratchet cross-app private imports; preserve existing debt without expanding it.

Public facades and ORM models are permitted. Hook registrations still appear
as debt until their owning module exposes a public registration API. Dynamic
imports and runtime dependency semantics need a separate architecture review.
"""

from __future__ import annotations

import ast
import json
import sys
from importlib.util import resolve_name
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = Path(__file__).with_name("public_api_baseline.json")


def private_imports(source, owner, package=None):
    found = set()
    for node in ast.walk(ast.parse(source)):
        targets = []
        if isinstance(node, ast.Import):
            targets = [(alias.name, "") for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level and package is None:
                continue
            module = resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module
            if module == "apps":
                targets = [("apps." + alias.name, "") for alias in node.names]
            else:
                targets = [(module or "", alias.name) for alias in node.names]
        for module, member in targets:
            parts = module.split(".")
            if len(parts) < 2 or parts[0] != "apps" or parts[1] == owner:
                continue
            surface = parts[2] if len(parts) > 2 else member
            if surface in {"public", "models"}:
                continue
            found.add(module + (":" + member if member else ""))
    return found


def inventory(root=ROOT):
    found = set()
    for path in (root / "apps").rglob("*.py"):
        relative = path.relative_to(root)
        if "tests" in relative.parts or "migrations" in relative.parts or path.name == "tests.py":
            continue
        owner = relative.parts[1]
        found.update(
            f"{relative.as_posix()} -> {target}"
            for target in private_imports(path.read_text(), owner, ".".join(relative.parent.parts))
        )
    return found


def check(current, baseline):
    added = current - baseline
    for entry in sorted(added):
        print(f"❌ Yeni private cross-app import: {entry}")
    if not added:
        print(f"✅ Public API gate: yeni pozuntu yoxdur; {len(current)} mövcud import müqaviləsi açıqdır.")
    return int(bool(added))


def main():
    current = inventory()
    if not BASELINE.exists():
        print("Baseline yoxdur; mövcud inventar ayrıca review ilə yaradılmalıdır.")
        return 1
    baseline = set(json.loads(BASELINE.read_text()))
    result = check(current, baseline)
    if "--update" in sys.argv and not result:
        BASELINE.write_text(json.dumps(sorted(current), indent=2, ensure_ascii=False) + "\n")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
