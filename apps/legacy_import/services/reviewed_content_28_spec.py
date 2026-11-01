"""Exact one-case facade; compiled workload/history identity is the shared source."""

from apps.workload.public import source28_recovery_spec

_VALUE = source28_recovery_spec()
TARGET = _VALUE["target"]
SPEC = _VALUE["spec"]

CASES = {int(key): value for key, value in _VALUE["cases"].items()}
LESSON = _VALUE["lesson"]
DATE = _VALUE["date"]
START = _VALUE["start"]
TOPIC = _VALUE["topic"]
SOURCE_SHA = _VALUE["source_sha"]
PAYLOAD_DIGEST = _VALUE["payload_digest"]
SOURCE_REVIEW_SHA = _VALUE["source_review_sha"]
CALENDAR_IDS = _VALUE["calendar_ids"]
METADATA_ID = _VALUE["metadata_id"]
