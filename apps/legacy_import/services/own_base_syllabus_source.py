"""Lossless fixed BASE source conversion, with visible welcome/assessment projections."""

import copy
import hashlib
import json
from pathlib import Path

from . import exact_syllabus_recovery as core
from . import own_base_syllabus_spec as spec
from .delta.syllabi import document_for
from .rehearsal_syllabus_targets import TEXT_TRUNCATED, build_section_data
from .syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS


def require(condition, code):
    if not condition:
        raise core.RestoreError("ownbase_" + code)


def visible_sections(source, row):
    require(core.digest(source) == row["source_digest"], "source_digest_changed")
    require(
        (source["id"], source["teacher_id"], source["lesson_id"], source["uniqid"], source["active"])
        == (row["source_id"], row["source_author"], row["source_subject"], row["uniqid"], 1),
        "source_identity_changed",
    )
    require(source["ders_saati"] == row["hours"] and source["language"] == row["language"], "source_plan_changed")
    require(set(source["sections"]) == set(SYLLABUS_SECTION_CONTRACTS), "twelve_table_source_required")
    require(
        len(source["week"]) == row["raw_topics"]
        and len({r["id"] for r in source["week"]}) == row["raw_topics"]
        and all(r["uniqid"] == row["uniqid"] for r in source["week"]),
        "source_week_scope",
    )
    original, codes = build_section_data(document_for(source))
    require(TEXT_TRUNCATED not in codes and len(original["week"]["rows"]) == row["topics"], "source_text_loss")
    require(
        [sum(r.get(k, 0) for r in original["week"]["rows"]) for k in ("lecture", "seminar", "practical", "lab")]
        == row["source_contact_hours"],
        "source_kind_hours_changed",
    )
    data = copy.deepcopy(original)
    # Keep original extension values verbatim; expose the same text in normal document fields too.
    welcome = data["info"].get("welcome", "")
    if welcome:
        data["desc"]["description"] = "\n\n".join(x for x in (welcome, data["desc"]["description"]) if x)
    questions = data["assess"].get("exam_questions", [])
    if questions:
        data["assess"]["note"] = "\n\n".join(x for x in (data["assess"].get("note", ""), *questions) if x)
    return data, list(codes), core.digest(original)


def load(path, expected):
    raw = Path(path).read_bytes()
    require(
        expected == spec.SOURCE_SHA and len(raw) <= 2_000_000 and hashlib.sha256(raw).hexdigest() == expected,
        "packet_digest",
    )
    try:
        packet = json.loads(raw)
        require(
            packet["format"] == spec.FORMAT
            and packet["organization_id"] == spec.ORG
            and packet["targets"] == [r["offering_id"] for r in spec.ROWS]
            and packet["legacy_source_approval_asserted"] is False
            and packet["current_approval_authority"] == "explicit_user_reviewed_own_active_base_recovery"
            and packet["raw_legacy_status"] == {str(r["source_id"]): 0 for r in spec.ROWS}
            and set(packet["unique_sources"]) == {str(r["source_id"]) for r in spec.ROWS},
            "fixed_source_set",
        )
        return {r["offering_id"]: visible_sections(packet["unique_sources"][str(r["source_id"])], r) for r in spec.ROWS}
    except core.RestoreError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError):
        raise core.RestoreError("ownbase_packet_shape") from None
