"""Read-only source qualification: typed identities and exact contact hours."""

from apps.registrar.public import syllabus_group_language
from apps.syllabus.public import content_fingerprints

from ..delta.syllabi import document_for
from ..rehearsal_syllabus_source import HOUR_CELL_INVALID, legacy_language
from ..rehearsal_syllabus_targets import TEXT_TRUNCATED, build_section_data
from ..syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS
from .contracts import RestoreError, digest, model
from .readonly_mapping import effective_maps


def _mapped(org, entity, source, label, target):
    bases = list(
        model("legacy_import.LegacyEntityMap")
        .objects.filter(organization=org, source_system="myedu_mariadb", entity_type=entity, legacy_pk=str(source))
        .values()
    )
    versions = list(
        model("legacy_import.LegacyEntityMapVersion")
        .objects.filter(entity_map_id__in=[row["id"] for row in bases])
        .values()
    )
    current = effective_maps(bases, versions)
    return len(current) == 1 and current[0]["target_model_label"] == label and current[0]["target_pk"] == str(target)


def checked_content(sections, official):
    result = content_fingerprints(sections)
    topics = result["topic_summary"]
    if (
        not topics["nonempty_topic_count"]
        or not topics["totals_complete"]
        or topics["invalid_shape_or_hours_count"]
        or topics["hours_without_topic_count"]
        or topics["hours_by_kind"] != official
    ):
        raise RestoreError("source_topics_or_contact_hours_mismatch")
    return result


def document_sections(source, official):
    """Pure source conversion, shared by offline preparation and live validation."""
    if (
        source["active"] != 1
        or not source["uniqid"]
        or legacy_language(source["language"])[1]
        or source["ders_saati"] != sum(official.values())
        or set(source["sections"]) != set(SYLLABUS_SECTION_CONTRACTS)
    ):
        raise RestoreError("legacy_source_header_invalid")
    document = document_for(source)
    if any(row["uniqid"] != source["uniqid"] for row in source["week"]):
        raise RestoreError("legacy_source_week_owner_mismatch")
    sections, codes = build_section_data(document)
    if HOUR_CELL_INVALID in codes or TEXT_TRUNCATED in codes or any(row.issues for row in document.week):
        raise RestoreError("legacy_source_conversion_requires_review")
    checked_content(sections, official)
    return document, sections, codes


def _source(packet, source_id):
    envelope = packet["sources"][str(source_id)]
    if set(envelope) != {"data", "sha256"} or digest(envelope["data"]) != envelope["sha256"]:
        raise RestoreError("legacy_source_digest_changed")
    if envelope["data"]["id"] != int(source_id):
        raise RestoreError("legacy_source_id_changed")
    return envelope


def legacy_for(offering, packet, official):
    binding = packet["bindings"].get(str(offering.pk))
    if binding is None:
        return None
    try:
        base_route = binding.get("journal") is None and "candidate_ids" in binding
        expected_keys = {"source_id", "journal", "candidate_ids"} if base_route else {"source_id", "journal"}
        if set(binding) != expected_keys:
            raise RestoreError("source_binding_shape")
        envelope = _source(packet, binding["source_id"])
        source, journal = envelope["data"], binding["journal"]
        if not base_route and (
            (journal["sillabus_id"], journal["teacher_id"], journal["lesson_id"])
            != (source["id"], source["teacher_id"], source["lesson_id"])
            or journal["semestr"] != 14
            or journal["fake"] != 0
            or journal["sonra_sil"] != 0
        ):
            raise RestoreError("legacy_source_journal_identity_mismatch")
        org = offering.organization
        if not all(
            (
                _mapped(org, "worker", source["teacher_id"], "auth.user", offering.instructor_id),
                _mapped(org, "lesson_subject", source["lesson_id"], "registrar.subject", offering.subject_id),
                base_route
                or any(
                    _mapped(org, "group_unit", group, "organizations.orgunit", offering.group_id)
                    for group in journal["group_ids"]
                ),
            )
        ):
            raise RestoreError("exact_legacy_target_route_unproven")
        document, sections, codes = document_sections(source, official)
        language = {"en": "ing", "eng": "ing", "ru": "rus", "aze": "az"}.get(
            document.header.language, document.header.language
        )
        if language != syllabus_group_language(offering.group):
            raise RestoreError("legacy_source_language_mismatch")
        if base_route:
            candidates = binding["candidate_ids"]
            if not isinstance(candidates, list) or not candidates or source["id"] not in candidates:
                raise RestoreError("legacy_own_base_candidates_required")
            for candidate_id in candidates:
                row = _source(packet, candidate_id)["data"]
                if any(
                    row[key] != source[key] for key in ("teacher_id", "lesson_id", "language", "active", "ders_saati")
                ):
                    raise RestoreError("legacy_own_base_identity_mismatch")
                _doc, other_sections, _codes = document_sections(row, official)
                if digest(other_sections) != digest(sections):
                    raise RestoreError("legacy_own_base_ambiguous_bodies")
        return {
            "kind": "legacy",
            "sections": sections,
            "fingerprint": checked_content(sections, official),
            "source_id": source["id"],
            "journal_id": journal["id"] if journal else None,
            "route": "own_base_identical_candidates" if base_route else "exact_journal",
            "source_digest": envelope["sha256"],
            "conversion_codes": list(codes),
        }
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        if isinstance(error, RestoreError):
            raise
        raise RestoreError("legacy_source_packet_shape") from None
