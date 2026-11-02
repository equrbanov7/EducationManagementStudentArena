"""Fixed official source and already-corrected keeper prerequisite identities."""

import hashlib
import json
from pathlib import Path

from .reviewed_two_catalog_spec import SCHEMA as SCHEMA

_SOURCE = Path(__file__).with_name("reviewed_elshen_duplicates_pins.json")
_RAW = _SOURCE.read_bytes()
if hashlib.sha256(_RAW).hexdigest() != "fcfa9c3bbc5807d8208735996c63675316c069466d05e2f2f71214f5d0cea13c":
    raise ValueError("elshen_compiled_source_changed")

PINS = json.loads(_RAW)
RESOURCE = "workload.elshen_duplicate_zero_reviewed"
ZERO = {key: 0 for key in ("lecture_plan", "lecture_total", "seminar_plan", "seminar_total", "total_hours")}

__all__ = ["PINS", "RESOURCE", "SCHEMA", "ZERO"]
