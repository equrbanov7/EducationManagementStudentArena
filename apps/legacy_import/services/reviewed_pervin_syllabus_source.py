"""Exact source14133→8573, fixed219/2125 spelling alias; no general alias authority."""

import hashlib
import json
from pathlib import Path

from apps.syllabus.public import content_fingerprints

from . import exact_syllabus_recovery as core
from . import reviewed_pervin_syllabus_spec as spec
from .delta.syllabi import document_for
from .rehearsal_syllabus_targets import build_section_data


def load(path, expected):
    raw = Path(path).read_bytes()
    if expected != spec.SOURCE_SHA or len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected:
        raise core.RestoreError("pervin_exact_source_packet_required")
    try:
        value = json.loads(raw)
        if (
            value["format"] != "reviewed-pervin-own60-syllabus/1"
            or value["organization_id"] != spec.ORG
            or set(value["selected_targets"]) != set(spec.COURSES)
            or len(value["selected_targets"]) != 2
            or value["legacy_source_approval_asserted"] is not False
            or value["current_approval_authority"] != "explicit_user_reviewed_own_source_recovery"
            or value["official_current_hours"] != {"lecture": 15, "seminar": 30, "total": 45}
            or value["preserved_source_hours"] != {"lecture": 30, "seminar": 30, "total": 60}
            or core.digest(value["source"]) != spec.SOURCE_DIGEST
            or core.digest(value["source_journal"]) != spec.JOURNAL_DIGEST
            or value["source_subject_alias"]
            != {
                "journal_subject": 219,
                "syllabus_subject": 2125,
                "scope": "fixed direct pointer14133→8573 only; no global alias authority",
            }
        ):
            raise core.RestoreError("pervin_own_source_identity_changed")
        sections, codes = build_section_data(document_for(value["source"]))
        if (
            set(codes)
            != {
                "legacy_syllabus_week_rows_exceed_plan",
                "legacy_syllabus_assessment_note_unsurfaced",
                "legacy_syllabus_blank_row_dropped",
            }
            or content_fingerprints(sections)["canonical_body_sha256"] != spec.BODY_SHA
            or len(sections["week"]["rows"]) != 30
            or len(sections["self"]["topics"]) != 10
            or tuple(
                sum(r.get(k, 0) for r in sections["week"]["rows"]) for k in ("lecture", "seminar", "practical", "lab")
            )
            != (30, 30, 0, 0)
            or sections["info"]["lesson_hours"] != 60
        ):
            raise core.RestoreError("pervin_exact_lossless_conversion_required")
        return sections, codes
    except core.RestoreError:
        raise
    except (KeyError, ValueError, TypeError, AttributeError):
        raise core.RestoreError("pervin_source_shape") from None
