"""Reuse the immutable ninety-batch registry; no second incomplete root inventory."""

from ..chair_cells_export.spec import PERIOD, REGISTRY_SHA, batch_spec
from ..scoped_snapshot.data import ORG, YEAR

FORMAT = "wcu-syllabus-content/1"
MAX_COURSES = 25
MAX_SYLLABI = 1500
MAX_BODY_SYLLABI = 300
MAX_VERSIONS = 500
MAX_SECTIONS = 5000
MAX_TOPICS = 100000
MAX_ROWS = 110000
MAX_BODY_BYTES = 32 * 1024 * 1024
MAX_SECTION_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_CLOSURE_DEPTH = 16
MAX_LEDGER = 5000

__all__ = ["PERIOD", "REGISTRY_SHA", "batch_spec", "ORG", "YEAR"]
