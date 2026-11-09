"""Read-only, ID-only comparison. Candidate linkage is not exact UI authorization."""

import collections
import hashlib
import json
import re
from pathlib import Path

OUT = Path(__file__).parent
SOURCE = Path("/Users/elvin/Desktop/RIM/Secret/reaudit-20261109/metadata.json")
SHA = "d38583d40048d3b1da47bb8cf77337f00d576e0647089e901b5752bddd3b880a"
raw = SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == SHA
snapshot = json.loads(raw)
d = snapshot["data"]
groups = {r["id"]: r for r in d["groups"]}
rows = {r["id"]: r for r in d["rows"]}
tasks = {r["id"]: r for r in d["tasks"]}
current = next(r["id"] for r in d["repair_current_periods"] if r["is_active"] and r["is_current"])
rg = collections.defaultdict(set)
for r in d["row_groups"]:
    rg[r["id"]].add(r["groups__id"])
children = collections.defaultdict(set)
for child in groups.values():
    parent = groups.get(str(child["settings"].get("parent_group") or ""))
    if not parent or not child["is_active"] or child["unit_type"] != "group":
        continue
    if child["id"] == parent["id"] or child["parent_id"] != parent["parent_id"]:
        continue
    if any(
        child["settings"].get(k) and parent["settings"].get(k) and child["settings"][k] != parent["settings"][k]
        for k in ("sector", "language", "degree_level", "education_form")
    ):
        continue
    children[parent["id"]].add(child["id"])

aliases = {}
source_id = "761579e3-8add-442b-8576-416bc634100c"
target_id = "26270fcd-4d69-482b-9be4-e0fa0d904aca"
source, target = groups.get(source_id), groups.get(target_id)


def name_key(value):
    return re.sub(r"\s+", "", value or "").casefold().removesuffix("az")


if source and target and snapshot["organization_id"] == "526cfa63-4f80-4bba-a7a7-61c8fbb3d918":
    valid = (
        source["settings"].get("canonical_group") == target_id
        and not source["is_active"]
        and target["is_active"]
        and source["unit_type"] == target["unit_type"] == "group"
        and source["parent_id"] == target["parent_id"]
        and not source["settings"].get("parent_group")
        and not target["settings"].get("parent_group")
        and name_key(source["name"]) == name_key(target["name"])
        and source["settings"].get("sector") == "az"
        and all(
            source["settings"].get(k) == target["settings"].get(k) for k in ("degree_level", "education_form", "sector")
        )
    )
    if valid:
        aliases[source_id] = target_id

KINDS = {"lecture", "seminar", "lab"}
RELEASED = {"approved", "distributed", "amended"}
eligible = []
other = []
for a in d["assignments"]:
    row = rows[a["row_id"]]
    task = tasks[row["task_id"]]
    if a["teacher_id"] and a["hours"] > 0 and a["activity"] in KINDS:
        (eligible if task["status"] in RELEASED else other).append(a)
by_teacher_subject_period = collections.defaultdict(list)
by_teacher_subject = collections.defaultdict(list)
by_row = collections.defaultdict(list)
for a in eligible:
    row = rows[a["row_id"]]
    by_teacher_subject_period[a["teacher_id"], row["subject_id"], row["period_id"]].append(a)
    by_teacher_subject[a["teacher_id"], row["subject_id"]].append(a)
    by_row[a["row_id"]].append(a)

counts = {r["offering_id"]: r for r in d["offering_counts"]}
enrollment_states = collections.defaultdict(dict)
for r in d["enrollment_status_counts"]:
    enrollment_states[r["offering_id"]][r["status"]] = r["count"]
own_lesson_counts = collections.Counter()
for r in d["lesson_teacher_hours"]:
    own_lesson_counts[r["offering_id"], r["instructor_id"]] += r["count"]
diagnostics = collections.defaultdict(list)
for r in d["journal_access_diagnostics"]:
    diagnostics[r["offering_id"]].append(r)


def group_relation(row, gid):
    """Return candidate relationship; missing groups_note prevents exact application."""
    if gid in rg[row["id"]]:
        return "direct"
    if any(aliases.get(parent) == aliases.get(gid, gid) for parent in rg[row["id"]]):
        return "managed_alias"
    if any(gid in children[parent] for parent in rg[row["id"]]):
        return "registered_parent"
    return None


def family_only(row, gid):
    for other_gid in rg[row["id"]]:
        if other_gid in children[gid]:
            return True
        if any(gid in ids and other_gid in ids for ids in children.values()):
            return True
    return False


def key(row):
    return tuple(row[k] for k in ("task_id", "subject_id", "season", "period_id"))


partners = [
    r
    for r in rows.values()
    if r["row_kind"] == "teaching"
    and r["lecture_plan"] > 0
    and r["lecture_total"] == 0
    and tasks[r["task_id"]]["status"] in RELEASED
]
result = []
for o in d["offerings"]:
    if not o["is_active"] or o["period_id"] != current:
        continue
    owner, gid = o["instructor_id"], o["group_id"]
    candidates = by_teacher_subject_period[owner, o["subject_id"], current] if owner else []
    ordinary = [a for a in candidates if rows[a["row_id"]]["row_kind"] != "intensive"]
    relations = collections.defaultdict(set)
    for a in ordinary:
        relation = group_relation(rows[a["row_id"]], gid)
        if relation:
            relations[relation].add(a["row_id"])
    potential_partner_ids = set()
    for p in partners:
        if p["subject_id"] != o["subject_id"] or p["period_id"] != current or not group_relation(p, gid):
            continue
        if any(
            a["activity"] == "lecture" and rows[a["row_id"]]["lecture_total"] > 0 and key(rows[a["row_id"]]) == key(p)
            for a in ordinary
        ):
            potential_partner_ids.add(p["id"])
    related = {a["row_id"] for a in ordinary if family_only(rows[a["row_id"]], gid)}
    if not owner:
        category = "NO_OWNER"
    elif relations["direct"]:
        category = "DIRECT_ROW_CANDIDATE"
    elif relations["managed_alias"]:
        category = "MANAGED_ALIAS_ROW_CANDIDATE"
    elif relations["registered_parent"]:
        category = "REGISTERED_PARENT_ROW_CANDIDATE"
    elif potential_partner_ids:
        category = "POTENTIAL_PATOK_LINK_UNEXPORTED"
    elif any(rows[a["row_id"]]["row_kind"] == "intensive" for a in candidates):
        category = "INTENSIVE_TARGET_UNEXPORTED"
    elif related:
        category = "CHILD_OR_SIBLING_LOAD_ONLY"
    elif candidates:
        category = "SAME_SUBJECT_OTHER_GROUP_ONLY"
    else:
        category = "SUBJECT_ABSENT_FROM_RELEASED_OWNER_PERIOD_LOAD"
    share = [
        r
        for r in diagnostics[o["id"]]
        if any(r.get(k) for k in ("share_full", "share_row_restricted", "share_kind_restricted"))
    ]
    other_exact_load = {
        a["teacher_id"]
        for a in eligible
        if a["teacher_id"] != owner
        and rows[a["row_id"]]["subject_id"] == o["subject_id"]
        and rows[a["row_id"]]["period_id"] == current
        and rows[a["row_id"]]["row_kind"] != "intensive"
        and group_relation(rows[a["row_id"]], gid)
    }
    c = counts[o["id"]]
    result.append(
        {
            "offering_id": o["id"],
            "subject_id": o["subject_id"],
            "group_id": gid,
            "instructor_id": owner,
            "category": category,
            "positive_released_subject_period_row_ids": sorted({a["row_id"] for a in candidates}),
            "direct_row_ids": sorted(relations["direct"]),
            "managed_alias_row_ids": sorted(relations["managed_alias"]),
            "registered_parent_row_ids": sorted(relations["registered_parent"]),
            "potential_patok_partner_row_ids": sorted(potential_partner_ids),
            "child_or_sibling_only_row_ids": sorted(related),
            "same_subject_other_period_load": bool(
                owner and by_teacher_subject[owner, o["subject_id"]] and not candidates
            ),
            "owner_lesson_count": own_lesson_counts[o["id"], owner],
            "all_content_counts": {k: c[k] for k in ("enrollments", "lessons", "marks")},
            "enrollment_status_counts": enrollment_states[o["id"]],
            "exported_share_diagnostic_count": len(share),
            "other_teacher_share_diagnostic_count": sum(r["teacher_id"] != owner for r in share),
            "other_teacher_direct_or_registered_load_candidate_count": len(other_exact_load),
        }
    )

unmatched = [
    r
    for r in result
    if r["instructor_id"]
    and r["category"] not in {"DIRECT_ROW_CANDIDATE", "REGISTERED_PARENT_ROW_CANDIDATE", "MANAGED_ALIAS_ROW_CANDIDATE"}
]
absent = [r for r in result if r["category"] == "SUBJECT_ABSENT_FROM_RELEASED_OWNER_PERIOD_LOAD"]
summary = {
    "active_current_period_offerings": len(result),
    "classification_counts": dict(collections.Counter(r["category"] for r in result)),
    "unmatched_owner_candidate_count": len(unmatched),
    "unmatched_with_recorded_owner_lessons": sum(r["owner_lesson_count"] > 0 for r in unmatched),
    "unmatched_with_other_teacher_share_diagnostic": sum(
        r["other_teacher_share_diagnostic_count"] > 0 for r in unmatched
    ),
    "unmatched_with_enrolled_students": sum(r["enrollment_status_counts"].get("enrolled", 0) > 0 for r in unmatched),
    "subject_absent_count": len(absent),
    "subject_absent_with_owner_lessons": sum(r["owner_lesson_count"] > 0 for r in absent),
    "subject_absent_with_other_teacher_share": sum(r["other_teacher_share_diagnostic_count"] > 0 for r in absent),
    "subject_absent_with_enrolled_students": sum(r["enrollment_status_counts"].get("enrolled", 0) > 0 for r in absent),
    "subject_absent_with_other_period_subject": sum(r["same_subject_other_period_load"] for r in absent),
    "subject_absent_with_other_teacher_group_load_candidate": sum(
        r["other_teacher_direct_or_registered_load_candidate_count"] > 0 for r in absent
    ),
    "subject_absent_history_share_overlap": sum(
        r["owner_lesson_count"] > 0 and r["other_teacher_share_diagnostic_count"] > 0 for r in absent
    ),
    "task_status_counts": dict(collections.Counter(r["status"] for r in tasks.values())),
    "released_positive_teaching_assignments": len(eligible),
    "not_released_positive_teaching_assignments": len(other),
    "valid_registered_parent_edges": sum(map(len, children.values())),
    "verified_managed_aliases": aliases,
}
payload = {
    "source": {
        "sha256": SHA,
        "captured_at": snapshot["captured_at"],
        "run_id": 42539120177,
        "application_head": "45892d9011e6e31d9ad39f9999fa3cb7f6717f84",
        "current_period_id": current,
    },
    "grain": "one active current-period offering and its owner; not all visible teacher-journal pairs",
    "summary": summary,
    "limitations": [
        "groups_note is not exported: positive row membership is a candidate, not confirmed assignment applicability",
        "patok_lead_id is not exported: compatible lead/partner candidates do not prove actual links",
        "intensive_offering is not exported: exact intensive target cannot be verified",
        "Child/sibling-only row is not inherited by teacher_journal_assignments; name matching is not used",
        "Owner without current positive load may remain a legitimate history-only journal; ownership is not a UI visibility claim",
        "Global JournalShare/handovers/assessment history and full teacher-list projections are not exported",
        "Diagnostic share flags show some current sharing evidence; absent flags are not complete absence proof",
        "Source is a bounded organization/year capture; absent subject is relative to captured positive released assignments",
    ],
    "offerings": result,
}
(OUT / "groups_workload_matches.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
