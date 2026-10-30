"""Version-two exceptions are exact reviewed identities, never blanket bypasses."""

import re

from .reviewed_batch_manifest import ACTIVITIES, integer, uid
from .sbio235_state import RepairError


def parse(entry, item, *, version):
    policy = entry.get("reviewed_policy", {})
    if not policy:
        return {}
    if version != "reviewed-workload-source/2" or set(policy) - {
        "handover",
        "legacy_history",
        "subject_create",
        "join_chair",
        "elective_choices",
        "empty_group_journals",
    }:
        raise RepairError("reviewed_v2_policy_required")
    result = {}
    if "elective_choices" in policy:
        from .reviewed_batch_electives import parse as parse_electives

        result["elective_choices"] = parse_electives(entry, item, policy["elective_choices"])
    if "empty_group_journals" in policy:
        from .reviewed_batch_electives import parse as parse_electives

        result["empty_group_journals"] = parse_electives(entry, item, policy["empty_group_journals"], empty=True)
        if {v["group_id"] for v in result["empty_group_journals"]} & {
            v["group_id"] for v in result.get("elective_choices", [])
        }:
            raise RepairError("reviewed_elective_and_empty_group_overlap")
    if "subject_create" in policy:
        value = policy["subject_create"]
        expected = {"id", "name", "code", "chair_unit_id", "ects", "kind"}
        if (
            set(value) != expected
            or uid(value["id"]) != item["subject_id"]
            or item["existing_journals"]
            or item["existing_rows"]
        ):
            raise RepairError("new_subject_policy_identity_invalid")
        if value["name"].strip() != str(entry["source_reference"]["values"]["subject"]).strip():
            raise RepairError("new_subject_must_use_exact_source_title")
        if not 1 <= integer(value["ects"], positive=True) <= 60 or value["kind"] not in {
            "core",
            "general",
            "elective",
            "practice",
        }:
            raise RepairError("new_subject_metadata_invalid")
        if (
            value["code"] != item["subject"]["code"]
            or value["name"] != item["subject"]["name"]
            or not 1 <= len(value["code"]) <= 32
        ):
            raise RepairError("new_subject_code_title_invalid")
        source_credits = entry["source_reference"]["values"].get("credits")
        if (
            isinstance(source_credits, bool)
            or not str(source_credits).strip().isdigit()
            or int(str(source_credits).strip()) != value["ects"]
        ):
            raise RepairError("new_subject_credits_must_match_literal_source")
        result["subject_create"] = {**value, "id": uid(value["id"]), "chair_unit_id": uid(value["chair_unit_id"])}
    journals = {value["id"]: value for value in item["existing_journals"]}
    if "handover" in policy:
        value = policy["handover"]
        if not journals or set(value) != {"from_instructor_id", "to_instructor_id", "offering_ids"}:
            raise RepairError("handover_exact_journal_identity_required")
        source, target = integer(value["from_instructor_id"], positive=True), integer(
            value["to_instructor_id"], positive=True
        )
        if source == target or {a["teacher_id"] for a in item["assignments"]} != {target}:
            raise RepairError("handover_teacher_policy_invalid")
        if {uid(pk) for pk in value["offering_ids"]} != set(journals) or len(value["offering_ids"]) != len(journals):
            raise RepairError("handover_exact_journal_identity_required")
        result["handover"] = {**value, "from_instructor_id": source, "to_instructor_id": target}
    history = policy.get("legacy_history", [])
    seen = set()
    for value in history:
        pk = uid(value["offering_id"])
        if (
            pk in seen
            or pk not in journals
            or set(value)
            != {
                "offering_id",
                "lesson_hours",
                "lessons",
                "marks",
                "enrollments",
                "recorded",
                "retain_capacity",
                "fingerprints",
                "syllabi",
            }
        ):
            raise RepairError("legacy_history_exact_journal_required")
        seen.add(pk)
        if set(value["fingerprints"]) != {"lesson_state_md5", "enrollment_state_md5", "mark_state_md5"} or any(
            not re.fullmatch(r"[a-f0-9]{32}", v) for v in value["fingerprints"].values()
        ):
            raise RepairError("legacy_snapshot_fingerprints_required")
        for syllabus in value["syllabi"]:
            if set(syllabus) != {"id", "author_id", "current_version_id", "approved_version_id"}:
                raise RepairError("legacy_syllabus_identity_invalid")
            uid(syllabus["id"])
            integer(syllabus["author_id"], positive=True)
            for field in ("current_version_id", "approved_version_id"):
                if syllabus[field] is not None:
                    uid(syllabus[field])
        if integer(value["lesson_hours"]) != journals[pk]["lesson_hours"] or type(value["retain_capacity"]) is not bool:
            raise RepairError("legacy_history_capacity_invalid")
        for name in ("lessons", "marks", "enrollments"):
            integer(value[name])
        keys = []
        for taught in value["recorded"]:
            if set(taught) != {"kind", "instructor_id", "hours", "count"} or taught["kind"] not in ACTIVITIES:
                raise RepairError("legacy_history_author_kind_invalid")
            if taught["instructor_id"] is not None:
                integer(taught["instructor_id"], positive=True)
            integer(taught["hours"], positive=True)
            integer(taught["count"], positive=True)
            keys.append((taught["kind"], taught["instructor_id"]))
        if len(keys) != len(set(keys)) or sum(t["count"] for t in value["recorded"]) != value["lessons"]:
            raise RepairError("legacy_history_aggregate_invalid")
        if value["retain_capacity"] and sum(t["hours"] for t in value["recorded"]) > value["lesson_hours"]:
            raise RepairError("retained_capacity_below_legacy_hours")
    if history:
        result["legacy_history"] = history
    if "join_chair" in policy:
        value = policy["join_chair"]
        if set(value) != {"teacher_id", "chair_id"} or integer(value["teacher_id"], positive=True) not in {
            a["teacher_id"] for a in item["assignments"]
        }:
            raise RepairError("reviewed_secondary_membership_invalid")
        result["join_chair"] = {"teacher_id": value["teacher_id"], "chair_id": uid(value["chair_id"])}
    return result
