"""Bounded reviewed targets; a cache discrepancy alone is never attendance authority."""

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from uuid import UUID

from core.reviewed_graph import require

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
RESOURCE = "registrar.reaudit_journal_structure_v1"
SCOPE_SHA = "abcaa3792034c47263275183f35eadea63cce6650595b23e836068316716c190"
HALF_AUTHORITY_SHA = "127a1dbe67fcc2f1e5aa9756988032cd6d3b0c36ef8d3be934ee5d79cc4ec96a"
MAX_BYTES = 1024 * 1024


def scope():
    raw = Path(__file__).with_name("reaudit_journal_structure_scope.json").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SCOPE_SHA, "structure_scope_changed")
    return json.loads(raw)


def private_bytes(path, expected_sha):
    require(bool(re.fullmatch(r"[0-9a-f]{64}", expected_sha)), "structure_file_sha_required")
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        info = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077 and 0 < info.st_size <= MAX_BYTES,
            "structure_private_file_required",
        )
        raw = stream.read(MAX_BYTES + 1)
    require(hashlib.sha256(raw).hexdigest() == expected_sha, "structure_file_changed")
    return raw


def validate(value):
    require(
        isinstance(value, dict)
        and set(value)
        == {
            "format",
            "organization_id",
            "period_id",
            "operation",
            "target_ids",
            "authority_sha256",
        },
        "structure_manifest_schema",
    )
    require(
        value["format"] == "reaudit-journal-structure/1"
        and value["organization_id"] == ORG
        and value["period_id"] == PERIOD,
        "structure_manifest_tenant_period",
    )
    require(
        value["operation"] in {"half_pair", "inactive_cache", "timetable", "park_inactive_slots"}, "structure_operation"
    )
    ids = value["target_ids"]
    require(isinstance(ids, list) and 0 < len(ids) <= 25 and len(set(ids)) == len(ids), "structure_target_budget")
    require(all(isinstance(pk, str) and str(UUID(pk)) == pk for pk in ids), "structure_target_ids")
    require(
        isinstance(value["authority_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", value["authority_sha256"]),
        "structure_authority_required",
    )
    registry = scope()
    if value["operation"] == "half_pair":
        require(
            set(ids) == {case["lesson_id"] for case in registry["half_pair_cases"]}
            and value["authority_sha256"] == HALF_AUTHORITY_SHA,
            "structure_half_pair_fixed_source",
        )
    elif value["operation"] == "inactive_cache":
        require(set(ids) <= set(registry["inactive_cache_enrollment_ids"]), "structure_unreviewed_cache_target")
    elif value["operation"] == "park_inactive_slots":
        require(
            set(ids) <= {row["slot_id"] for row in registry["inactive_slot_cases"]}, "structure_unreviewed_slot_target"
        )
    return value
