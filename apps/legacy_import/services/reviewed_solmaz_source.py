"""Verify every byte of the teacher's own ancient-literature source 8355."""

import hashlib
import json
from pathlib import Path

from apps.syllabus.public import content_fingerprints
from apps.workload.public import reviewed_catalog_graph as evidence

from . import reviewed_solmaz_spec as spec
from .delta.syllabi import document_for
from .rehearsal_syllabus_targets import TEXT_TRUNCATED, build_section_data
from .syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS


def load(path, expected):
    candidate = Path(path)
    evidence.require(
        candidate.is_file() and not candidate.is_symlink() and 0 < candidate.stat().st_size <= 2000000,
        "solmaz_regular_bounded_source_required",
    )
    raw = candidate.read_bytes()
    evidence.require(
        len(raw) <= 2000000
        and expected == spec.PINS["source_packet_sha256"]
        and hashlib.sha256(raw).hexdigest() == expected,
        "solmaz_source_packet_changed",
    )
    try:
        package = json.loads(raw)
        evidence.require(
            set(package)
            == {
                "format",
                "organization_id",
                "source",
                "source_approval_asserted",
                "current_authority",
                "source_subject_alias",
                "official_source_sha256",
            },
            "solmaz_source_shape",
        )
        evidence.require(
            package["format"] == "reviewed-solmaz-own-source/1"
            and package["organization_id"] == spec.ORG
            and package["source_approval_asserted"] is False
            and package["current_authority"] == "explicit_reviewed_own_source_restoration"
            and package["source_subject_alias"] == [187, 2078]
            and package["official_source_sha256"] == spec.PINS["source_official_sha256"],
            "solmaz_source_authority_changed",
        )
        source = package["source"]
        digest = hashlib.sha256(
            json.dumps(source, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
        evidence.require(
            digest == spec.PINS["source_digest"]
            and (
                source["id"],
                source["teacher_id"],
                source["lesson_id"],
                source["ders_saati"],
                source["language"],
                source["active"],
            )
            == (8355, 22, 187, 60, "az", 1),
            "solmaz_own_source_identity_changed",
        )
        evidence.require(
            set(source["sections"]) == set(SYLLABUS_SECTION_CONTRACTS)
            and len(source["week"]) == len({r["id"] for r in source["week"]}) == 15
            and all(r["uniqid"] == source["uniqid"] for r in source["week"]),
            "solmaz_complete_source_required",
        )
        sections, codes = build_section_data(document_for(source))
        evidence.require(
            TEXT_TRUNCATED not in codes
            and content_fingerprints(sections)["canonical_body_sha256"] == spec.PINS["source_canonical_body"]
            and tuple(
                sum(r.get(k, 0) for r in sections["week"]["rows"]) for k in ("lecture", "seminar", "practical", "lab")
            )
            == (30, 30, 0, 0),
            "solmaz_source_conversion_changed",
        )
        return sections, list(codes)
    except (KeyError, TypeError, json.JSONDecodeError):
        evidence.require(False, "solmaz_source_shape")
