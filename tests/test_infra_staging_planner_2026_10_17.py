"""PERF-1 F-17 (2026-10-17): staging / QA klon Postgres-inin planlaşdırıcı parametrləri prod ilə eynidir.

Klonda defolt `random_page_cost=4` ilə jurnalın legacy-excuse sorğusu 305 k sətirlik paralel seq scan seçirdi
(prod parametrləri ilə indeks) — klon EXPLAIN-ləri və QA vaxtları yanıldırdı. DB-siz test: iki compose faylı
müqayisə olunur.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_RE = re.compile(r"^\$\{[A-Z0-9_]+:-(?P<default>[^}]*)\}$")
PLANNER_KEYS = ("random_page_cost", "effective_io_concurrency", "effective_cache_size", "work_mem", "jit")


def _flags(path: str) -> dict[str, str]:
    compose = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    command = compose["services"]["postgres"].get("command") or []
    flags = {}
    for item in command:
        if isinstance(item, str) and "=" in item and not item.startswith("-"):
            key, value = item.split("=", 1)
            match = _DEFAULT_RE.match(value)
            flags[key] = match.group("default") if match else value
    return flags


def test_staging_planner_flags_match_prod_defaults():
    prod = _flags("docker-compose.prod.yml")
    staging = _flags("docker-compose.staging.yml")
    for key in PLANNER_KEYS:
        assert key in staging, f"staging-də `{key}` yoxdur"
        assert staging[key] == prod[key], f"{key}: staging {staging[key]!r} ≠ prod {prod[key]!r}"


def test_staging_does_not_allocate_prod_memory():
    # Lokal konteyner: RAM ayıran parametrlər (shared_buffers, max_connections) prod-dan KÖÇÜRÜLMÜR.
    staging = _flags("docker-compose.staging.yml")
    assert "shared_buffers" not in staging
    assert "max_connections" not in staging
