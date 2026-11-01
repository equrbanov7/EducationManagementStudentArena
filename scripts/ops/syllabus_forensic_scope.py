"""Only fixed027/029 body fingerprints with explicit cycle-held lineage."""

import importlib.util
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024


def validate(payload):
    definition = importlib.util.spec_from_file_location(
        "shared_body_shape", Path(__file__).with_name("syllabus_content_scope.py")
    )
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    module._validate(payload, _forensic=True)
