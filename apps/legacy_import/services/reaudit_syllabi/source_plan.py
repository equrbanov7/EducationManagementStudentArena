"""Offline typed source plan. Fresh SQL dry-run still qualifies official hours and locks."""

from collections import Counter, defaultdict

from apps.registrar.public import syllabus_group_language
from apps.syllabus.public import content_fingerprints

from ..delta.syllabi import document_for
from ..rehearsal_syllabus_targets import build_section_data
from .contracts import SCOPE, RestoreError, digest
from .readonly_mapping import effective_maps
from .sources import document_sections


def _language(group):
    from types import SimpleNamespace

    return syllabus_group_language(SimpleNamespace(name=group.get("name", ""), settings=group.get("settings")))


def _ids(row):
    value = row.get("group_ids")
    if not isinstance(value, list) or any(type(x) is not int for x in value):
        return ()
    return value


def prepare_sources(snapshot, headers, journals, load_source, *, offering_ids=None):
    """Only exact canonical typed identities; ambiguous bodies never pick newest ID.

    ``load_source`` reads a header and every section under its uniqid from one
    repeatable-read source transaction. Output body values are private artifacts.
    """
    tables = snapshot["tables"]
    needed = {
        "registrar.CourseOffering",
        "organizations.OrgUnit",
        "legacy_import.LegacyEntityMap",
        "legacy_import.LegacyEntityMapVersion",
    }
    if not needed <= set(tables):
        raise RestoreError("fresh_snapshot_mapping_tables_missing")
    mappings = effective_maps(tables["legacy_import.LegacyEntityMap"], tables["legacy_import.LegacyEntityMapVersion"])
    reverse = defaultdict(set)
    for row in mappings:
        if str(row["organization_id"]) != SCOPE["organization_id"]:
            raise RestoreError("fresh_snapshot_foreign_mapping")
        if row["source_system"] == "myedu_mariadb":
            reverse[(row["entity_type"], row["target_model_label"], str(row["target_pk"]))].add(str(row["legacy_pk"]))
    groups = {str(row["id"]): row for row in tables["organizations.OrgUnit"]}
    offerings = {str(row["id"]): row for row in tables["registrar.CourseOffering"]}
    ids = sorted(set(offering_ids or SCOPE["offering_ids"]))
    if not set(ids) <= set(SCOPE.get("allowed_offering_ids", SCOPE["offering_ids"])):
        raise RestoreError("fixed_audit_offering_scope_required")
    uniqids = Counter(row["uniqid"] for row in headers)
    by_pair = defaultdict(list)
    for row in headers:
        by_pair[(str(row["teacher_id"]), str(row["lesson_id"]))].append(row)
    loaded, bindings, selected, queue = {}, {}, {}, []

    def source_for(header, offering):
        source_id = str(header["id"])
        if source_id not in loaded:
            loaded[source_id] = load_source(header)
        source = loaded[source_id]
        if any(
            source.get(key) != header.get(key)
            for key in ("id", "uniqid", "teacher_id", "lesson_id", "active", "language", "ders_saati")
        ):
            raise RestoreError("source_header_changed_within_snapshot")
        sections, _codes = build_section_data(document_for(source))
        official_candidate = content_fingerprints(sections)["topic_summary"]["hours_by_kind"]
        _doc, sections, _codes = document_sections(source, official_candidate)
        if sum(official_candidate.values()) != offering["lesson_hours"]:
            raise RestoreError("source_and_offering_total_hours_disagree")
        return source, digest(sections)

    for oid in ids:
        row = offerings.get(oid)
        if (
            not row
            or str(row["organization_id"]) != SCOPE["organization_id"]
            or str(row["period_id"]) != SCOPE["period_id"]
        ):
            queue.append({"offering_id": oid, "code": "current_target_not_in_snapshot"})
            continue
        if not row["is_active"] or row.get("instructor_id") is None or not row.get("group_id"):
            queue.append({"offering_id": oid, "code": "inactive_or_unassigned_target"})
            continue
        teachers = reverse[("worker", "auth.user", str(row["instructor_id"]))]
        subjects = reverse[("lesson_subject", "registrar.subject", str(row["subject_id"]))]
        group_ids = reverse[("group_unit", "organizations.orgunit", str(row["group_id"]))]
        group = groups.get(str(row["group_id"]))
        if not group or str(group["organization_id"]) != SCOPE["organization_id"]:
            raise RestoreError("fresh_snapshot_group_closure_missing")
        language = _language(group)
        candidates = []
        for teacher in teachers:
            for subject in subjects:
                for header in by_pair[(teacher, subject)]:
                    normalized = {"en": "ing", "eng": "ing", "ru": "rus", "aze": "az"}.get(
                        header["language"], header["language"]
                    )
                    if header["active"] == 1 and header["ders_saati"] == row["lesson_hours"] and normalized == language:
                        candidates.append(header)
        linked = [
            j
            for j in journals
            if str(j["teacher_id"]) in teachers
            and str(j["lesson_id"]) in subjects
            and j["semestr"] == 14
            and not j["fake"]
            and not j["sonra_sil"]
            and any(str(g) in group_ids for g in _ids(j))
            and j.get("sillabus_id")
        ]
        linked_ids = {j["sillabus_id"] for j in linked}
        direct = [h for h in candidates if h["id"] in linked_ids]
        chosen = direct or candidates
        if not chosen:
            queue.append(
                {
                    "offering_id": oid,
                    "code": "no_exact_legacy_body_candidate",
                    "typed_worker_count": len(teachers),
                    "typed_subject_count": len(subjects),
                    "linked_source_ids": sorted(linked_ids),
                    "native_donor_check_pending": True,
                }
            )
            continue
        try:
            if any(uniqids[h["uniqid"]] != 1 for h in chosen):
                raise RestoreError("legacy_source_uniqid_ambiguous")
            converted = [(h, *source_for(h, row)) for h in chosen]
            if len({body for _h, _source, body in converted}) != 1:
                raise RestoreError("multiple_distinct_legacy_bodies_require_review")
            converted.sort(key=lambda entry: entry[0]["id"])  # tie only AFTER exact body equality
            header, source, body = converted[0]
            binding = {"source_id": header["id"], "journal": None}
            if direct:
                matching = [j for j in linked if j["sillabus_id"] == header["id"]]
                binding["journal"] = min(matching, key=lambda item: item["id"])
            else:
                binding["candidate_ids"] = sorted(h["id"] for h in chosen)
            bindings[oid] = binding
            for h, payload, _body in converted:
                selected[str(h["id"])] = {"data": payload, "sha256": digest(payload)}
            queue.append(
                {
                    "offering_id": oid,
                    "code": "source_packet_candidate",
                    "source_id": header["id"],
                    "candidate_ids": sorted(h["id"] for h in chosen),
                    "body_sha256": body,
                    "route": "exact_journal" if direct else "own_base_identical_candidates",
                    "live_official_hours_check_pending": True,
                }
            )
        except RestoreError as error:
            queue.append({"offering_id": oid, "code": str(error), "candidate_ids": sorted(h["id"] for h in chosen)})
    packet = {
        "format": "reaudit-syllabi-source/1",
        "organization_id": SCOPE["organization_id"],
        "period_id": SCOPE["period_id"],
        "sources": selected,
        "bindings": bindings,
    }
    return packet, {
        "format": "reaudit-syllabi-plan/1",
        "scope_count": len(ids),
        "source_count": len(selected),
        "binding_count": len(bindings),
        "counts": dict(Counter(row["code"] for row in queue)),
        "rows": queue,
        "selection_policy": "canonical-applied-mapping; exact subject+author+language+contact-hours; identical-body tie only",
        "production_writes": False,
        "live_dry_run_required": True,
    }
