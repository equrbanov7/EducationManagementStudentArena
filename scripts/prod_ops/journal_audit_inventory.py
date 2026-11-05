"""Current server metadata inventory; evidence and proposed actions, never DB writes."""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from journal_audit_checks import normalize

CONTACT = {"lecture", "seminar", "lab"}
RELEASED = {"distributed", "amended"}


def build(payload, *, as_of="2026-11-04"):
    data = payload["data"]
    tables = {
        key: {row["id"]: row for row in data[key]}
        for key in ("offerings", "subjects", "groups", "teachers", "periods", "tasks", "rows", "syllabi")
    }
    offerings, subjects, groups, teachers, periods, tasks, rows, syllabi = (tables[key] for key in tables)
    counts = {row["offering_id"]: row for row in data["offering_counts"]}
    enrollment_counts = defaultdict(Counter)
    for row in data["enrollment_status_counts"]:
        enrollment_counts[row["offering_id"]][row["status"]] = row["count"]
    diagnostics = {}
    for row in data["journal_access_diagnostics"]:
        key = row["offering_id"]
        old = diagnostics.get(key)
        if old:
            assert (old["syllabus_id"], old["approved_syllabus_version_id"]) == (
                row["syllabus_id"],
                row["approved_syllabus_version_id"],
            )
        diagnostics[key] = row
    current = {
        key: row
        for key, row in offerings.items()
        if row["is_active"]
        and periods[row["period_id"]]["start_date"] <= as_of <= periods[row["period_id"]]["end_date"]
    }
    links, assigned = defaultdict(set), defaultdict(list)
    for row in data["row_groups"]:
        if row["groups__id"]:
            links[row["id"]].add(row["groups__id"])
    for row in data["assignments"]:
        assigned[row["row_id"]].append(row)
    by_owner_subject = defaultdict(list)
    for row in rows.values():
        for teacher in {a["teacher_id"] for a in assigned[row["id"]] if a["teacher_id"]}:
            by_owner_subject[teacher, row["subject_id"], row["period_id"]].append(row)

    def person(uid):
        row = teachers.get(uid, {})
        return " ".join(str(row.get(k, "")) for k in ("last_name", "first_name")).strip() or (
            f"Müəllim ID {uid}" if uid else "Müəllim təyin edilməyib"
        )

    def context(offering):
        oid = offering["id"]
        subject = subjects.get(offering["subject_id"], {})
        return {
            "offering_id": oid,
            "url": f"https://ems.wcu.edu.az/jurnal/{oid}/",
            "subject": subject.get("name", ""),
            "subject_code": subject.get("code", ""),
            "subject_id": offering["subject_id"],
            "group_id": offering["group_id"],
            "group": groups.get(offering["group_id"], {}).get("name", ""),
            "teacher": person(offering["instructor_id"]),
            "teacher_id": offering["instructor_id"],
            "period": periods[offering["period_id"]]["name"],
            "period_id": offering["period_id"],
            "is_active": offering["is_active"],
            "lesson_hours": offering["lesson_hours"],
            "lessons": counts[oid]["lessons"],
            "marks": counts[oid]["marks"],
            "enrolled": enrollment_counts[oid]["enrolled"],
        }

    def released(row):
        return tasks[row["task_id"]]["status"] in RELEASED or row["row_kind"] == "intensive"

    inventory = []
    issues = defaultdict(list)
    for oid, offering in sorted(current.items()):
        result = context(offering)
        diag = diagnostics.get(oid)
        if diag:
            sid, vid = diag["syllabus_id"], diag["approved_syllabus_version_id"]
            result.update(syllabus_id=sid, approved_version_id=vid, syllabus_evidence="live_canonical_resolver")
            state = "missing" if not sid else "unapproved" if not vid else "approved"
        else:
            state = "unverified_no_teacher_diagnostic"
            result.update(syllabus_id=None, approved_version_id=None, syllabus_evidence=state)
        result["syllabus_state"] = state
        if state != "approved":
            issues["syllabus_" + state].append(result)
        candidates = (
            by_owner_subject[offering["instructor_id"], offering["subject_id"], offering["period_id"]]
            if offering["instructor_id"]
            else []
        )
        visible = [row for row in candidates if released(row)]
        exact = [row for row in visible if offering["group_id"] in links[row["id"]]]
        result["visible_load_rows"] = [row["id"] for row in visible]
        result["exact_load_rows"] = [row["id"] for row in exact]
        if not offering["instructor_id"]:
            result["load_state"] = "owner_missing"
        elif not visible:
            result["load_state"] = "unreleased" if candidates else "subject_absent_for_owner"
        elif not exact:
            result["load_state"] = "subject_present_other_group"
            parent_id = (groups.get(offering["group_id"], {}).get("settings") or {}).get("parent_group")
            result["explicit_parent_load_rows"] = [
                row["id"] for row in visible if parent_id and parent_id in links[row["id"]]
            ]
        else:
            result["load_state"] = "exact"
        if result["load_state"] != "exact":
            issues["load_" + result["load_state"]].append(result)
        result["populated"] = bool(result["lessons"] or result["marks"] or result["enrolled"])
        if state in {"missing", "unapproved"}:
            potential = []
            for syllabus in syllabi.values():
                owner = offerings.get(syllabus["offering_id"], {}).get("instructor_id")
                if (
                    syllabus["id"] != result["syllabus_id"]
                    and syllabus["is_active"]
                    and syllabus["approved_version_id"]
                    and syllabus["subject_id"] == offering["subject_id"]
                    and syllabus["period_id"] == offering["period_id"]
                    and offering["instructor_id"]
                    and offering["instructor_id"] in {syllabus["author_id"], owner}
                ):
                    potential.append(syllabus["id"])
            result["same_teacher_subject_period_sources"] = sorted(potential)
            if potential:
                result["proposed_action"] = (
                    "Eyni müəllim/fənn/semestr üzrə təsdiqli mənbə var: saat və məzmunu yoxlayıb mövcud paylaşım/bağlama axını ilə qoşmaq. Qaralama varsa onun üstələməsini ayrıca həll etmək."
                )
            elif state == "unapproved":
                result["proposed_action"] = (
                    "Mövcud qaralamanın məzmununu tamamlayıb təsdiq axınından keçirmək; müəllimin yerinə məzmun uydurmamaq."
                )
            else:
                result["proposed_action"] = (
                    "Müəllimin həmin fənn üçün orijinal sillabusunu və köhnə mənbə bağını tapmaq; uyğun mənbə yoxdursa müəllimdən məzmun tələb etmək."
                )
        inventory.append(result)
    load_inventory = []
    for row in rows.values():
        period = periods.get(row["period_id"], {})
        if not period or not period["start_date"] <= as_of <= period["end_date"]:
            continue
        if not released(row):
            continue
        contact = [a for a in assigned[row["id"]] if a["activity"] in CONTACT and a["hours"] > 0 and a["teacher_id"]]
        if not contact:
            continue
        for teacher_id in sorted({a["teacher_id"] for a in contact}):
            target = [
                o
                for o in inventory
                if o["subject_id"] == row["subject_id"]
                and o["group_id"] in links[row["id"]]
                and o["teacher_id"] == teacher_id
            ]
            missing_groups = links[row["id"]] - {o["group_id"] for o in target}
            out = {
                "row_id": row["id"],
                "subject": subjects.get(row["subject_id"], {}).get("name", row["subject_text"]),
                "groups": row["groups_text"],
                "teacher": person(teacher_id),
                "teacher_id": teacher_id,
                "hours": sum(a["hours"] for a in contact if a["teacher_id"] == teacher_id),
                "exact_owned_journals": [o["offering_id"] for o in target],
                "unmatched_group_ids": sorted(g for g in missing_groups if g),
                "approved_syllabus_journals": [o["offering_id"] for o in target if o["syllabus_state"] == "approved"],
                "status": (
                    "needs_shared_or_subgroup_check"
                    if not target or missing_groups
                    else "all_approved" if all(o["syllabus_state"] == "approved" for o in target) else "syllabus_gap"
                ),
            }
            load_inventory.append(out)
            if out["status"] != "all_approved":
                issues["load_syllabus_" + out["status"]].append(out)
    title_differences = []
    fold = str.maketrans("əıöüçşğ", "eioucsg")
    for row in rows.values():
        actual = subjects.get(row["subject_id"], {}).get("name", "")
        source = row["subject_text"]
        if (
            not actual
            or not source
            or not released(row)
            or row["season"] != "fall"
            or normalize(actual) == normalize(source)
        ):
            continue
        if "blok" in source.casefold() or re.search(r"\b[123]\s*[.)]", source):
            continue  # The selected elective is intentionally one item in a source list.
        normalized_a, normalized_s = normalize(actual).translate(fold), normalize(source).translate(fold)
        level = "spelling" if normalized_a == normalized_s else "label_difference_requires_review"
        title_differences.append(
            {
                "row_id": row["id"],
                "groups": row["groups_text"],
                "source_label": source,
                "shown_label": actual,
                "classification": level,
            }
        )
    issues["load_title_differences"] = title_differences
    return {
        "captured_at": payload["captured_at"],
        "source_run": 41897824109,
        "read_only": True,
        "counts": {
            "current_active": len(inventory),
            "future_active": sum(
                o["is_active"] and periods[o["period_id"]]["start_date"] > as_of for o in offerings.values()
            ),
            "marks": sum(o["marks"] for o in inventory),
            "load_teacher_rows": len(load_inventory),
        },
        "issue_counts": {key: len(value) for key, value in sorted(issues.items())},
        "syllabus_states": dict(Counter(o["syllabus_state"] for o in inventory)),
        "load_states": dict(Counter(o["load_state"] for o in inventory)),
        "issues": dict(issues),
        "inventory": inventory,
        "load_inventory": load_inventory,
        "student_inventory": [
            context(o)
            for o in offerings.values()
            if periods[o["period_id"]]["start_date"] <= as_of <= periods[o["period_id"]]["end_date"]
        ],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = build(json.loads(args.source.read_bytes()))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    args.output.chmod(0o600)
    print(
        json.dumps(
            {k: result[k] for k in ("counts", "issue_counts", "syllabus_states", "load_states")}, ensure_ascii=False
        )
    )
