"""Exact Vefa234KE legacy fallback; no syllabus approval, copy, import or credit edit."""

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _load(name, expected):
    raw = (BASE / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("two_catalog_fixed_source_packet_changed")
    return json.loads(raw)


PINS = _load("reviewed_vefa_catalog_pins.json", "e49caa7b7c7dbbf4ec14ad8c1dae6e0b4fd5b134e4a82657aa00871875e1500b")
SCHEMA = _load(
    "reviewed_two_catalog_schema_pins.json", "b856305a51ce529af6d06842d3eaadf275c899181bb2a1cc3bce808d9fe6dc0f"
)
ORG = PINS["organization_id"]
PERIOD = PINS["period_id"]
YEAR = PINS["academic_year"]
CASES = PINS["cases"]
RESOURCE = "workload.reviewed_vefa_catalog_load_v1"
