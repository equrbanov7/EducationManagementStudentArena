"""MR-000250/251 şifrəli paketinin yoxlanması: hər mənbə, birbaşa jurnal göstəricisi və çevrilmə sabitlənib."""

import hashlib
import json
from pathlib import Path

from . import exact_syllabus_recovery as core
from . import govher_syllabi_spec as spec
from .delta.syllabi import document_for
from .rehearsal_syllabus_targets import TEXT_TRUNCATED, build_section_data

RestoreError = core.RestoreError
KINDS = ("lecture", "seminar", "practical", "lab")
MAX_PACKET = 1_000_000


def week_hours(sections):
    """Həftəlik cədvəlin növ üzrə cəmi — yalnız sıfırdan böyük növlər (plan forması ilə eyni)."""
    totals = {kind: sum(int(row.get(kind) or 0) for row in sections["week"]["rows"]) for kind in KINDS}
    return {kind: value for kind, value in totals.items() if value}


def _convert(case, entry):
    if set(entry) != {"source", "source_journal"}:
        raise RestoreError("source_entry_shape")
    source, journal = entry["source"], entry["source_journal"]
    if core.digest(source) != case["source_digest"] or core.digest(journal) != case["journal_digest"]:
        raise RestoreError("pinned_source_changed")
    pins, jpins = case["source"], case["journal"]
    if (
        source["id"],
        source["teacher_id"],
        source["lesson_id"],
        source["uniqid"],
        source["ders_saati"],
        source["language"],
        source["active"],
    ) != (pins["id"], spec.SOURCE_AUTHOR, pins["lesson_id"], pins["uniqid"], pins["ders_saati"], pins["language"], 1):
        raise RestoreError("own_source_scope_changed")
    if (
        journal["id"],
        journal["teacher_id"],
        journal["lesson_id"],
        journal["sillabus_id"],
        journal["groups_id"],
        journal["fenn_saati"],
        journal["semestr"],
        journal["active"],
        journal["fake"],
        journal["sonra_sil"],
    ) != (
        jpins["id"],
        spec.SOURCE_AUTHOR,
        jpins["lesson_id"],
        pins["id"],
        jpins["groups_id"],
        jpins["fenn_saati"],
        jpins["semestr"],
        1,
        0,
        0,
    ):
        raise RestoreError("direct_journal_pointer_changed")
    week = source["week"]
    if (
        tuple(sorted(source["sections"])) != spec.COMMON_TABLES
        or len(week) != case["topics"]
        or len({row["id"] for row in week}) != len(week)
        or any(row["uniqid"] != pins["uniqid"] for row in week)
        or len(source["sections"]["sillabus_serbest_is"]) != case["selfwork_rows"]
    ):
        raise RestoreError("source_topic_scope_changed")
    sections, codes = build_section_data(document_for(source))
    if (
        TEXT_TRUNCATED in codes
        or core.digest(sections) != case["converted_digest"]
        or len(sections["week"]["rows"]) != case["topics"]
        or len(sections["self"]["topics"]) != case["selfwork_topics"]
        or week_hours(sections) != case["plan"]
    ):
        raise RestoreError("source_conversion_or_hours_changed")
    return sections, tuple(codes)


def load(path, expected):
    """``[(case, sections, codes)]`` — paket sha256-sı, formatı və hədəf dəsti sabitdir."""
    raw = Path(path).read_bytes()
    if len(raw) > MAX_PACKET or expected != spec.PACKET_SHA256 or hashlib.sha256(raw).hexdigest() != expected:
        raise RestoreError("pinned_source_packet_changed")
    try:
        package = json.loads(raw)
        if (
            set(package) != {"format", "organization_id", "entries"}
            or package["format"] != spec.FORMAT
            or package["organization_id"] != spec.ORG
            or set(package["entries"]) != {case["offering_id"] for case in spec.CASES}
        ):
            raise RestoreError("fixed_source_packet_scope")
        return [(case, *_convert(case, package["entries"][case["offering_id"]])) for case in spec.CASES]
    except RestoreError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RestoreError("source_packet_shape") from None
