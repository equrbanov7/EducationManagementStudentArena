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
    "reviewed_two_catalog_schema_pins.json", "eae004e4bef34dd93a61f76dced7fdc1c2f523df222fe6572b18a790400c256c"
)
ORG = PINS["organization_id"]
PERIOD = PINS["period_id"]
YEAR = PINS["academic_year"]
CASES = PINS["cases"]
RESOURCE = "workload.reviewed_vefa_catalog_load_v1"
