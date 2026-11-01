"""Load the same pinned, Django-free contract as the source capture."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "apps/workload/services/timetable_evidence"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_spec = load("timetable_evidence_spec", PACKAGE / "spec.py")
_contract = load("timetable_evidence_contract", PACKAGE / "contract.py")
MAX_BYTES = _spec.MAX_BYTES
MANIFEST_SHA = _spec.MANIFEST_SHA
BATCHES = _spec.BATCHES
selection = _spec.selection
validate = _contract.validate
