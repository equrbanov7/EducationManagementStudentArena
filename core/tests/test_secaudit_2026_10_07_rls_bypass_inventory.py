"""Audit 2026-09-28 T-04 / 2026-10-07: hər yeni ``bypass_rls()`` faylı təsnif olunmalıdır.

``scripts/rls_bypass_inventory.py`` təsnif edilməmiş fayl görəndə 1 ilə çıxırdı, amma heç
bir CI addımı onu işlətmirdi — inventar 156 → 197 çağırışa sürüşdü, 16 fayl təsnifsiz qaldı.
Bu test həmin qapını pytest-ə bağlayır (DB tələb etmir).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_inventory_module():
    spec = importlib.util.spec_from_file_location("rls_bypass_inventory", ROOT / "scripts" / "rls_bypass_inventory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_bypass_rls_file_is_classified():
    module = _load_inventory_module()
    counts = module.inventory(ROOT)
    assert counts, "inventar boşdur — skriptin yol qaydası səhvdir"
    unclassified = sorted(rel for rel in counts if module._category(rel)[0] == "?")
    assert unclassified == [], f"bypass_rls() olan təsnif edilməmiş fayllar (RLS_BYPASS_AUDIT.md): {unclassified}"
