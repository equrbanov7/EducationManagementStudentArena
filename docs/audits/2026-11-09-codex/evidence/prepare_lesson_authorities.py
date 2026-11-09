"""Bounded offline authority for the 24 audited source events; never executes SQL."""

import argparse
import collections
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from apps.registrar.reaudit_cells.class_history import fingerprint, from_tables  # noqa: E402
from apps.registrar.reaudit_cells.ledger import effective_maps  # noqa: E402

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
POLICY = "owner-present-for-reviewed-missing-slot-source-qb-20261109"


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def require(condition, code):
    if not condition:
        raise ValueError(code)


def array(value):
    raw = json.loads(value) if isinstance(value, str) else value
    require(
        isinstance(raw, list) and all(type(v) in (str, int) and str(v).isdigit() for v in raw), "source_roster_shape"
    )
    return {str(v) for v in raw}


def time_text(value):
    parts = str(value).split(":")
    return ":".join(part.zfill(2) for part in parts[:2])


def mapped_index(tables):
    result = collections.defaultdict(set)
    for row in effective_maps(tables["legacy_import.LegacyEntityMap"], tables["legacy_import.LegacyEntityMapVersion"]):
        require(row["organization_id"] == ORG, "foreign_canonical_mapping")
        if row["source_system"] == "myedu_mariadb":
            result[(row["entity_type"], row["target_model_label"], str(row["legacy_pk"]))].add(str(row["target_pk"]))
    return result


def history_authority(tables, course, evidence):
    """Explicit owner policy supersedes only native empty/absent-only cleanup."""
    lessons = {row["id"]: row for row in tables["registrar.Lesson"]}
    reversed_ids = {row.get("lesson_correction_id") for row in tables["registrar.CorrectionReversal"]}
    for row in tables["registrar.LessonCorrection"]:
        if (
            row["id"] in reversed_ids
            or str(row.get("old_date")) != evidence["date"]
            or row.get("old_kind") != evidence["kind"]
        ):
            continue
        old_time = str(row.get("old_time") or "")
        if old_time and old_time[:5] != evidence["start_time"]:
            continue
        linked = lessons.get(row.get("lesson_id"))
        if linked is not None and linked["offering_id"] != course["id"]:
            continue
        if row.get("old_instructor_id") is not None and row["old_instructor_id"] != course["instructor_id"]:
            continue
        require(False, "formal_lesson_correction_or_deletion_requires_review")

    def objects(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from objects(child)
        elif isinstance(value, list):
            for child in value:
                yield from objects(child)

    overridden = []
    for row in tables["audit.AuditLog"]:
        if row.get("organization_id") != ORG:
            continue
        scope = str(row.get("resource_id")) == course["id"]
        relevant = []
        for old in objects(row.get("old_values") or {}):
            if not (scope or str(old.get("offering_id")) == course["id"]):
                continue
            if (
                str(old.get("date")) != evidence["date"]
                or time_text(old.get("start_time")) != evidence["start_time"]
                or old.get("kind") != evidence["kind"]
            ):
                continue
            relevant.append(old)
        if not relevant:
            continue
        if row.get("resource_type") == "legacy_import.empty_lesson" and row.get("action") == "delete":
            require(
                all(
                    all(
                        mark.get("status") in ("absent", "unknown", "") and mark.get("score") is None
                        for mark in old.get("marks", [])
                    )
                    for old in relevant
                ),
                "cleanup_removed_real_content_requires_review",
            )
            overridden.append({"audit_id": row["id"], "audit_sha256": sha(row), "authority": POLICY})
        elif row.get("action") in ("delete", "update"):
            require(False, "source_slot_has_other_change_history")
    return overridden


def generate(snapshot, facts, probe, *, capture_sha256):
    require(len(probe["slots"]) <= 24 and probe["candidate_point_count"] == 247, "fixed_24slot_probe_required")
    tables = snapshot["tables"]
    labels = (
        "registrar.CourseOffering",
        "registrar.Enrollment",
        "registrar.Lesson",
        "registrar.LabGroup",
        "registrar.SeminarGroup",
        "organizations.AcademicPeriod",
        "legacy_import.LegacyEntityMap",
        "legacy_import.LegacyEntityMapVersion",
        "registrar.LessonCorrection",
        "registrar.CorrectionReversal",
        "audit.AuditLog",
    )
    require(all(label in tables for label in labels), "fresh_roster_mask_closure_required")
    periods = [r for r in tables["organizations.AcademicPeriod"] if r["id"] == PERIOD]
    require(
        len(periods) == 1 and periods[0]["is_current"] and periods[0]["is_active"] and not periods[0]["locked_at"],
        "active_current_period_required",
    )
    offerings = {r["id"]: r for r in tables["registrar.CourseOffering"]}
    current = [r for r in offerings.values() if r["is_active"] and r["period_id"] == PERIOD]
    class_counts = collections.Counter(
        (r["subject_id"], r["group_id"], r["instructor_id"], r["period_id"]) for r in current
    )
    mapping = mapped_index(tables)
    journals = {r["id"]: r for r in facts["journals"]}
    metadata = {r["id"]: r for r in facts["metadata"]}
    all_points = {r["id"]: r for r in facts["all_slot_points"]}
    authorities, holds, uncertain = [], [], set()
    for evidence in sorted(
        probe["slots"],
        key=lambda r: (not r["has_real_source_attendance_or_score"], r["offering_id"], r["date"], r["start_time"]),
    ):
        oid, jid = evidence["offering_id"], evidence["legacy_journal_id"]
        try:
            course = offerings.get(oid)
            require(
                course and course["organization_id"] == ORG and course["period_id"] == PERIOD and course["is_active"],
                "current_offering_required",
            )
            key = tuple(course[k] for k in ("subject_id", "group_id", "instructor_id", "period_id"))
            require(class_counts[key] == 1, "current_typed_class_ambiguous")
            journal = journals[jid]
            require(
                journal["semestr"] == 14 and not journal["fake"] and not journal["sonra_sil"],
                "source_journal_flags_changed",
            )
            require(
                mapping[("worker", "auth.user", str(journal["teacher_id"]))] == {str(course["instructor_id"])},
                "teacher_route_unproven",
            )
            require(
                mapping[("lesson_subject", "registrar.subject", str(journal["lesson_id"]))]
                == {str(course["subject_id"])},
                "subject_route_unproven",
            )
            require(
                any(
                    mapping[("group_unit", "organizations.orgunit", g)] == {str(course["group_id"])}
                    for g in array(journal["groups_id"])
                ),
                "group_route_unproven",
            )
            source_users = set()
            for sid in array(journal["students_id"]):
                users = mapping[("student", "auth.user", sid)]
                require(len(users) == 1, "source_roster_student_route_unproven")
                source_users.update(users)
            enrollments = [
                r for r in tables["registrar.Enrollment"] if r["offering_id"] == oid and r["status"] == "enrolled"
            ]
            require(
                enrollments and len({r["student_id"] for r in enrollments}) == len(enrollments),
                "current_roster_empty_or_ambiguous",
            )
            enrolled_users = {str(r["student_id"]) for r in enrollments}
            mapped_roster = source_users & enrolled_users
            require(mapped_roster, "source_roster_not_in_current_class")
            kind = evidence["kind"]
            masks = {"lab_group": None, "seminar_group": None}
            if kind == "lecture":
                require(mapped_roster == enrolled_users, "lecture_roster_scope_changed")
            else:
                field = "lab_group" if kind == "lab" else "seminar_group"
                label = "registrar.LabGroup" if kind == "lab" else "registrar.SeminarGroup"
                defined = {r["number"] for r in tables[label] if r["offering_id"] == oid}
                defined |= {r[field] for r in enrollments if r.get(field) is not None}
                if defined:
                    # A source journal's entire roster must be exactly one formally
                    # declared current subgroup; a few point rows are not a mask.
                    exact = [
                        number
                        for number in defined
                        if {str(r["student_id"]) for r in enrollments if r.get(field) == number} == mapped_roster
                    ]
                    require(len(exact) == 1, "source_roster_subgroup_not_unique")
                    masks[field] = exact[0]
                else:
                    require(mapped_roster == enrolled_users, "whole_class_roster_scope_changed")
            for pid in evidence["legacy_point_ids"]:
                point = all_points[pid]
                require(
                    mapping[("student", "auth.user", str(point["student_id"]))] <= mapped_roster
                    and bool(mapping[("student", "auth.user", str(point["student_id"]))]),
                    "candidate_student_outside_proven_roster",
                )
            same_day = [
                r
                for r in tables["registrar.Lesson"]
                if r["offering_id"] == oid and r["date"] == evidence["date"] and r["kind"] == kind
            ]
            exact = [r for r in same_day if time_text(r["start_time"]) == evidence["start_time"]]
            require(not exact, "lesson_already_exists_use_existing_path")
            require(not same_day, "same_day_retime_or_native_merge_review")
            require(
                evidence["exact_point_slot_and_student_match"]
                and evidence["metadata_kind_matches_points"]
                and len(evidence["metadata_ids"]) == 1,
                "exact_source_event_required",
            )
            meta = metadata[evidence["metadata_ids"][0]]
            require(
                meta["journal_id"] == jid
                and not meta["fake"]
                and str(meta["date"]) == evidence["date"]
                and time_text(meta["times"]) == evidence["start_time"]
                and float(meta["saatliq_ders"]) * 2 == evidence["explicit_pair_hours"],
                "source_hour_authority_changed",
            )
            cleanup_proof = history_authority(tables, course, evidence)
            authority = {
                "offering_id": oid,
                "journal_uniqid": journal["uniqid"],
                "group_mask_proven": True,
                "slot": {
                    "date": evidence["date"],
                    "start_time": evidence["start_time"] + ":00",
                    "end_time": None,
                    "kind": kind,
                    "hours": evidence["explicit_pair_hours"],
                    "instructor_id": course["instructor_id"],
                    **masks,
                },
                "source_journal_id": jid,
                "source_metadata_id": meta["id"],
                "source_point_ids": evidence["legacy_point_ids"],
                "source_fact_sha256": evidence["source_fact_sha256"],
                "current_capture_sha256": capture_sha256,
                "current_roster_sha256": sha(enrollments),
                "source_roster_sha256": sha(sorted(source_users)),
                "hours_authority": "journals_dates_rooms.saatliq_ders * 2; date >= 2024-02-01",
                "end_time_authority": "not_recorded_in_legacy; nullable Lesson field preserved",
                "subgroup_authority": "exact canonical source journal roster equals current whole roster or one declared subgroup",
                "reviewed_empty_cleanup_overrides": cleanup_proof,
                "fresh_history_capture_sha256": capture_sha256,
                "cleanup_history_must_remain_unchanged": True,
                "owner_present_policy": POLICY,
            }
            authority["class_history_sha256"] = fingerprint(from_tables(tables), course=course, slot=authority["slot"])
            authorities.append(authority)
            uncertain.update(
                pid for pid in evidence["legacy_point_ids"] if str(all_points[pid]["point"]).strip().lower() == "qb"
            )
        except (ValueError, KeyError) as error:
            holds.append(
                {
                    "offering_id": oid,
                    "legacy_journal_id": jid,
                    "date": evidence["date"],
                    "start_time": evidence["start_time"],
                    "kind": evidence["kind"],
                    "code": str(error) if isinstance(error, ValueError) else "source_field_missing",
                }
            )
    return {
        "class_authorities": authorities,
        "reviewed_owner_present_source_ids": sorted(map(str, uncertain)),
        "reviewed_owner_present_reason": POLICY,
        "held_classes": holds,
        "source_slots": 24,
        "snapshot_sha256": capture_sha256,
        "production_writes": False,
        "live_repair_preflight_required": True,
    }


def read(path, expected):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "private_input_sha256_mismatch")
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "facts", "probe"):
        parser.add_argument("--" + name, required=True, type=Path)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(
        REPO not in args.output.resolve().parents and args.output.parent.stat().st_mode & 0o077 == 0,
        "private_output_required",
    )
    snapshot = read(args.snapshot, args.snapshot_sha256)
    require(
        snapshot["manifest"]["complete"]
        and snapshot["manifest"]["organization_id"] == ORG
        and snapshot["manifest"]["period_id"] == PERIOD,
        "complete_current_capture_required",
    )
    probe = read(args.probe, args.probe_sha256)
    require(probe["private_raw_sha256"] == args.facts_sha256, "probe_source_facts_identity_changed")
    result = generate(
        snapshot,
        read(args.facts, args.facts_sha256),
        probe,
        capture_sha256=args.snapshot_sha256,
    )
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(result, stream, sort_keys=True)
    print(
        json.dumps(
            {
                "class_authorities": len(result["class_authorities"]),
                "owner_present_points": len(result["reviewed_owner_present_source_ids"]),
                "holds": dict(collections.Counter(r["code"] for r in result["held_classes"])),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError):
        raise SystemExit("class_authority_precondition_failed; private values were not printed") from None
