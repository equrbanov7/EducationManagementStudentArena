"""Load only the pinned pure contract without importing Django or changing old decoders."""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "apps/workload/services/english_level_evidence"
NAME = "_pinned_english_level_evidence"


def contract():
    package = types.ModuleType(NAME)
    package.__path__ = [str(PACKAGE)]
    sys.modules[NAME] = package
    for key in ("spec", "contract"):
        source = importlib.util.spec_from_file_location(NAME + "." + key, PACKAGE / (key + ".py"))
        module = importlib.util.module_from_spec(source)
        sys.modules[source.name] = module
        source.loader.exec_module(module)
    return module


def validate(payload):
    return contract().validate(payload)


MAX_BYTES = 16 * 1024 * 1024
