"""Pinned complete own-source bodies for append-only approved-version recovery."""

import hashlib
import json
from pathlib import Path

from apps.syllabus.public import content_fingerprints

from . import blank_draft_syllabus_spec as spec
from . import exact_syllabus_recovery as core
from .delta.syllabi import document_for
from .rehearsal_syllabus_targets import TEXT_TRUNCATED, build_section_data
from .syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS

RestoreError = core.RestoreError


def load(path, expected):
    raw = Path(path).read_bytes()
    pins = {r["packet_sha256"] for r in spec.ROWS}
    if len(raw) > 2000000 or pins != {expected} or hashlib.sha256(raw).hexdigest() != expected:
        raise RestoreError("pinned_source_packet_changed")
    try:
        package = json.loads(raw)
        if set(package) != {
            "format",
            "organization_id",
            "legacy_source_approval_asserted",
            "current_approval_authority",
            "unique_sources",
            "selected_targets",
        } or (
            package["format"] != "blank-draft-own-syllabi/1"
            or package["organization_id"] != spec.ORG
            or package["legacy_source_approval_asserted"] is not False
            or package["current_approval_authority"] != "explicit_user_reviewed_own_source_recovery"
            or package["selected_targets"] != [r["offering_id"] for r in spec.ROWS]
            or set(package["unique_sources"]) != {str(r["source_syllabus"]) for r in spec.ROWS}
        ):
            raise RestoreError("fixed_source_packet_scope")
        loaded = []
        for row in spec.ROWS:
            source = package["unique_sources"][str(row["source_syllabus"])]
            if core.digest(source) != row["source_digest"] or (
                source["id"],
                source["teacher_id"],
                source["lesson_id"],
                source["uniqid"],
                source["ders_saati"],
                source["language"],
                source["active"],
            ) != (
                row["source_syllabus"],
                row["source_author"],
                row["source_subject"],
                row["uniqid"],
                row["hours"],
                row["sector"],
                1,
            ):
                raise RestoreError("pinned_own_source_changed")
            if set(source["sections"]) != set(SYLLABUS_SECTION_CONTRACTS):
                raise RestoreError("complete_source_tables_required")
            if (
                len(source["week"]) != row["topics"]
                or len({r["id"] for r in source["week"]}) != row["topics"]
                or any(r["uniqid"] != row["uniqid"] for r in source["week"])
                or len(source["sections"]["sillabus_serbest_is"]) != row["selfwork_rows"]
            ):
                raise RestoreError("source_topic_or_selfwork_scope")
            sections, codes = build_section_data(document_for(source))
            fingerprint = content_fingerprints(sections)
            if (
                TEXT_TRUNCATED in codes
                or fingerprint["canonical_body_sha256"] != row["source_canonical_body"]
                or len(sections["week"]["rows"]) != row["topics"]
                or len(sections["self"]["topics"]) != row["selfwork_topics"]
                or tuple(
                    sum(x.get(k, 0) for x in sections["week"]["rows"])
                    for k in ("lecture", "seminar", "practical", "lab")
                )
                != tuple(row["contact_hours"])
            ):
                raise RestoreError("source_conversion_or_plan_changed")
            loaded.append((row, sections, codes))
        return loaded
    except RestoreError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RestoreError("source_packet_shape") from None
