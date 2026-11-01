"""Exact read-only body fingerprints and typed shape metrics; no authored text leaves here."""

import copy
import hashlib
import json
from collections import Counter

KINDS = ("lecture", "seminar", "practical", "lab")
SECTIONS = ("info", "desc", "out", "week", "method", "assess", "self", "lit", "prev", "send")
CONTACT_FIELDS = {"teacher", "office_hours", "email", "phone"}
LEAF_KEYS = (
    "dict_nodes",
    "list_nodes",
    "empty_lists",
    "string_leaves",
    "blank_string_leaves",
    "null_leaves",
    "boolean_leaves",
    "number_leaves",
)
MAX_NODES = 1000000
MAX_DEPTH = 32
MAX_TOPICS = 100000
POLICY = "exact_syllabus_recovery.digest/1"


def digest(value):
    """Match the existing exact source converter; never normalize prose, math or list order."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()


def leaf_counts(value):
    counts = Counter({key: 0 for key in LEAF_KEYS})
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError("syllabus_body_shape_budget_exceeded")
        if isinstance(item, dict):
            counts["dict_nodes"] += 1
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            counts["list_nodes"] += 1
            counts["empty_lists"] += not item
            pending.extend((v, depth + 1) for v in item)
        elif isinstance(item, str):
            counts["string_leaves"] += 1
            counts["blank_string_leaves"] += not item.strip()
        elif item is None:
            counts["null_leaves"] += 1
        elif type(item) is bool:
            counts["boolean_leaves"] += 1
        elif isinstance(item, (int, float)):
            counts["number_leaves"] += 1
    return dict(counts)


def typed_hours(raw):
    result, strings = {}, 0
    valid = isinstance(raw, dict) and not set(raw) - set(KINDS)
    for kind in KINDS:
        value = raw.get(kind, 0) if isinstance(raw, dict) else None
        if type(value) is int and 0 <= value <= 1000000:
            result[kind] = value
        elif (
            isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 7 and int(value) <= 1000000
        ):
            result[kind] = int(value)
            strings += 1
        else:
            result[kind] = None
            valid = False
    return {"hours": result, "valid": valid, "numeric_string_count": strings, "raw_sha256": digest(raw)}


def course_data(section_id, data):
    if section_id == "info" and isinstance(data, dict):
        return {key: value for key, value in data.items() if key not in CONTACT_FIELDS}
    return data


def topic_metrics(data):
    raw = data.get("rows", []) if isinstance(data, dict) else None
    rows = raw if isinstance(raw, list) else []
    if len(rows) > MAX_TOPICS:
        raise ValueError("syllabus_topic_budget_exceeded")
    totals = Counter({kind: 0 for kind in KINDS})
    topics_by_kind = Counter({kind: 0 for kind in KINDS})
    summary = {
        "row_count": len(rows),
        "nonempty_topic_count": 0,
        "hours_without_topic_count": 0,
        "topic_without_hours_count": 0,
        "invalid_shape_or_hours_count": int(not isinstance(raw, list)),
        "numeric_string_count": 0,
    }
    result = []
    for index, row in enumerate(rows):
        shape = isinstance(row, dict)
        topic = row.get("topic") if shape else None
        outcome = row.get("outcome") if shape else None
        present = isinstance(topic, str) and bool(topic.strip())
        parsed = typed_hours({kind: row.get(kind, 0) for kind in KINDS} if shape else None)
        valid = (
            shape
            and parsed["valid"]
            and (topic is None or isinstance(topic, str))
            and (outcome is None or isinstance(outcome, str))
        )
        summary["invalid_shape_or_hours_count"] += not valid
        summary["nonempty_topic_count"] += present
        summary["numeric_string_count"] += parsed["numeric_string_count"]
        positive = any(value is not None and value > 0 for value in parsed["hours"].values())
        summary["hours_without_topic_count"] += positive and not present
        summary["topic_without_hours_count"] += present and not positive
        for kind, value in parsed["hours"].items():
            if value is not None:
                totals[kind] += value
                topics_by_kind[kind] += present and value > 0
        result.append(
            {
                "row_index": index,
                "valid_shape": shape,
                "topic_present": present,
                "outcome_present": isinstance(outcome, str) and bool(outcome.strip()),
                "hours": parsed["hours"],
                "hours_valid": parsed["valid"],
                "numeric_string_count": parsed["numeric_string_count"],
                "row_sha256": digest(row),
                "unknown_key_count": len(set(row) - {*KINDS, "topic", "outcome"}) if shape else 0,
            }
        )
    hashes = [row["row_sha256"] for row in result]
    summary.update(
        {
            "hours_by_kind": dict(totals),
            "nonempty_topics_by_kind": dict(topics_by_kind),
            "totals_complete": summary["invalid_shape_or_hours_count"] == 0,
            "ordered_row_sha256": digest(hashes),
            "row_multiset_sha256": digest(sorted(hashes)),
            "duplicate_row_count": len(hashes) - len(set(hashes)),
        }
    )
    return result, summary


def content_fingerprints(sections):
    """Input is an exact section-id→data map; unknown keys survive only inside hashes."""
    summaries = []
    for key, data in sorted(sections.items()):
        leaves = leaf_counts(data)
        summaries.append(
            {
                "section_id": key if key in SECTIONS else None,
                "section_key_sha256": digest(key),
                "raw_data_sha256": digest(data),
                "course_data_sha256": digest(course_data(key, data)),
                "leaf_counts": leaves,
                "is_object": isinstance(data, dict),
                "nonblank_string_present": leaves["string_leaves"] > leaves["blank_string_leaves"],
            }
        )
    course = copy.copy(sections)
    if "info" in course:
        course["info"] = course_data("info", course["info"])
    topics, summary = topic_metrics(sections.get("week", {}))
    return {
        "canonical_policy": POLICY,
        "canonical_body_sha256": digest(sections),
        "course_body_sha256": digest(course),
        "known_section_count": len(set(sections) & set(SECTIONS)),
        "unknown_section_count": len(set(sections) - set(SECTIONS)),
        "sections": summaries,
        "topics": topics,
        "topic_summary": summary,
    }
