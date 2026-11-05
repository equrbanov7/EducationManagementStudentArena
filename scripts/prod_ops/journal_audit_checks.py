"""Offline, read-only checks for journal_integrity_snapshot academic snapshots."""

import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


def normalize(value):
    value = unicodedata.normalize("NFKC", str(value or "")).replace("İ", "i").casefold()
    return " ".join(re.sub(r"[^\w\s+#]", " ", value).split())


def index(rows):
    return {row["id"]: row for row in rows}


def audit(data, *, as_of="2026-11-04"):
    offerings = index(data["registrar.CourseOffering"])
    subjects = index(data["registrar.Subject"])
    groups = index(data["organizations.OrgUnit"])
    periods = index(data["organizations.AcademicPeriod"])
    people = index(data["people"])
    enrollments = index(data["registrar.Enrollment"])
    lessons = index(data["registrar.Lesson"])
    syllabi = index(data["syllabus.Syllabus"])
    versions = index(data["syllabus.SyllabusVersion"])
    sections = defaultdict(dict)
    for row in data["syllabus.SyllabusSection"]:
        sections[row["version_id"]][row["section_id"]] = row["data"]
    current = {
        key
        for key, value in offerings.items()
        if value["is_active"]
        and periods[value["period_id"]]["academic_year"] == "2026/2027"
        and periods[value["period_id"]]["start_date"] <= as_of
    }
    counts = defaultdict(Counter)
    for row in enrollments.values():
        counts[row["offering_id"]]["enrollments"] += 1
        counts[row["offering_id"]][row["status"]] += 1
    for row in lessons.values():
        counts[row["offering_id"]]["lessons"] += 1
        counts[row["offering_id"]]["hours"] += row["hours"]
    issues = defaultdict(list)

    def person(pk):
        row = people.get(pk, {})
        return " ".join(str(row.get(k, "")) for k in ("last_name", "first_name")).strip() or str(pk)

    def context(oid):
        row = offerings[oid]
        subject = subjects.get(row["subject_id"], {})
        return {
            "offering_id": oid,
            "subject": subject.get("name", ""),
            "subject_code": subject.get("code", ""),
            "group": groups.get(row["group_id"], {}).get("name", ""),
            "teacher": person(row["instructor_id"]),
            "period": periods[row["period_id"]]["name"],
            "lesson_hours": row["lesson_hours"],
            **counts[oid],
        }

    tasks = index(data["workload.TeachingTask"])
    rows = index(data["workload.TeachingTaskRow"])
    row_groups = defaultdict(set)
    for row in data["workload_groups"]:
        if row["groups__id"]:
            row_groups[row["id"]].add(row["groups__id"])
    assignments = defaultdict(list)
    for row in data["workload.TeacherAssignment"]:
        assignments[row["row_id"]].append(row)
    slot_rows = defaultdict(list)
    for row in rows.values():
        for group in row_groups[row["id"]] or {None}:
            slot_rows[row["subject_id"], row["period_id"], group].append(row)
    for oid in sorted(current):
        offering = offerings[oid]
        candidates = slot_rows[offering["subject_id"], offering["period_id"], offering["group_id"]]
        owner_rows = [
            row
            for row in candidates
            if any(a["teacher_id"] == offering["instructor_id"] for a in assignments[row["id"]])
        ]
        visible = [
            row
            for row in owner_rows
            if tasks[row["task_id"]]["status"] in {"distributed", "amended"} or row["row_kind"] == "intensive"
        ]
        if not visible:
            category = (
                "load_unreleased"
                if owner_rows
                else "load_other_teacher" if candidates else "load_no_exact_group_subject"
            )
            issues[category].append(
                {
                    **context(oid),
                    "row_ids": [r["id"] for r in candidates],
                    "task_statuses": sorted({tasks[r["task_id"]]["status"] for r in candidates}),
                    "other_teachers": sorted(
                        {person(a["teacher_id"]) for r in candidates for a in assignments[r["id"]] if a["teacher_id"]}
                    ),
                    "parent_group": (groups.get(offering["group_id"], {}).get("settings") or {}).get("parent_group"),
                }
            )
    resolutions = {row["offering_id"]: row for row in data["resolved_syllabi"]}
    for oid in sorted(current):
        resolution = resolutions.get(oid, {})
        own = resolution.get("teacher_syllabus_id")
        approved = resolution.get("teacher_approved_version_id")
        student = resolution.get("student_syllabus_id")
        if not own:
            issues["syllabus_missing"].append(context(oid))
        elif not approved:
            issues["syllabus_unapproved"].append({**context(oid), "syllabus_id": own})
        if not student:
            issues["student_syllabus_missing"].append(context(oid))
        if own and student and own != student:
            issues["syllabus_views_differ"].append({**context(oid), **resolution})
        for surface, sid in (("teacher", own), ("student", student)):
            if sid and sid in syllabi and syllabi[sid]["subject_id"] != offerings[oid]["subject_id"]:
                source = subjects.get(syllabi[sid]["subject_id"], {})
                issues["syllabus_wrong_subject_link"].append(
                    {
                        **context(oid),
                        "surface": surface,
                        "syllabus_id": sid,
                        "syllabus_subject": source.get("name", ""),
                        "syllabus_subject_code": source.get("code", ""),
                    }
                )
        if approved:
            week = sections.get(approved, {}).get("week") or {}
            topics = [
                row.get("topic", "").strip()
                for row in week.get("rows", [])
                if isinstance(row, dict) and str(row.get("topic") or "").strip()
            ]
            if not topics:
                issues["syllabus_approved_no_topics"].append(
                    {**context(oid), "syllabus_id": own, "version_id": approved}
                )
            total = sum(
                (versions.get(approved, {}).get("plan_hours") or {}).get(k, 0) or 0
                for k in ("lecture", "seminar", "lab")
            )
            if total and offerings[oid]["lesson_hours"] and total != offerings[oid]["lesson_hours"]:
                issues["syllabus_offering_hours_differ"].append(
                    {**context(oid), "syllabus_id": own, "syllabus_hours": total}
                )
    raw_hours, mark_count = Counter(), Counter()
    slot_marks = defaultdict(list)
    for mark in data["registrar.LessonMark"]:
        lesson = lessons.get(mark["lesson_id"])
        enrollment = enrollments.get(mark["enrollment_id"])
        if not lesson or not enrollment:
            issues["mark_reference_missing"].append(mark["id"])
            continue
        oid = enrollment["offering_id"]
        if lesson["offering_id"] != oid:
            issues["mark_cross_offering"].append(
                {"mark_id": mark["id"], "lesson_offering_id": lesson["offering_id"], **context(oid)}
            )
        if mark["status"] == "absent":
            raw_hours[enrollment["id"]] += lesson["hours"]
            mark_count[enrollment["id"]] += 1
            if lesson["date"] > as_of and oid in current:
                issues["future_absence"].append(
                    {
                        **context(oid),
                        "student": person(enrollment["student_id"]),
                        "mark_id": mark["id"],
                        "date": lesson["date"],
                    }
                )
        if oid in current and enrollment["status"] == "enrolled" and lesson.get("start_time"):
            subject = subjects.get(offerings[oid]["subject_id"], {})
            key = (
                enrollment["student_id"],
                offerings[oid]["period_id"],
                normalize(subject.get("name")),
                lesson["date"],
                lesson["start_time"],
                lesson["kind"],
            )
            slot_marks[key].append(
                {
                    "mark_id": mark["id"],
                    "lesson_id": lesson["id"],
                    "enrollment_id": enrollment["id"],
                    "offering_id": oid,
                    "status": mark["status"],
                    "hours": lesson["hours"],
                }
            )
    credits, reversed_ids = Counter(), set()
    for row in data["registrar.AbsenceCredit"]:
        if row["reverses_id"]:
            reversed_ids.add(row["reverses_id"])
    for row in data["registrar.AbsenceCredit"]:
        if not row["reverses_id"] and row["id"] not in reversed_ids:
            credits[row["enrollment_id"]] += row["hours"]
    carry = Counter()
    for row in enrollments.values():
        target = enrollments.get(row["superseded_by_id"])
        if row["status"] == "dropped" and target and row["student_id"] == target["student_id"]:
            a, b = offerings[row["offering_id"]], offerings[target["offering_id"]]
            if a["subject_id"] == b["subject_id"] and a["period_id"] == b["period_id"]:
                carry[target["id"]] += max(0, raw_hours[row["id"]] - credits[row["id"]])
    active_subjects = defaultdict(list)
    for row in enrollments.values():
        oid = row["offering_id"]
        if oid not in current or row["status"] != "enrolled":
            continue
        expected = max(0, raw_hours[row["id"]] + carry[row["id"]] - credits[row["id"]])
        if expected != row["absence_hours"]:
            issues["absence_cache_mismatch"].append(
                {
                    **context(oid),
                    "enrollment_id": row["id"],
                    "student_id": row["student_id"],
                    "student": person(row["student_id"]),
                    "cached": row["absence_hours"],
                    "derived": expected,
                    "own_raw": raw_hours[row["id"]],
                    "carried": carry[row["id"]],
                    "credit": credits[row["id"]],
                }
            )
        subject = subjects[offerings[oid]["subject_id"]]
        active_subjects[row["student_id"], offerings[oid]["period_id"], normalize(subject["name"])].append(row)
    for key, rows in active_subjects.items():
        if len(rows) > 1:
            issues["duplicate_student_subject"].append(
                {
                    "student_id": key[0],
                    "student": person(key[0]),
                    "subject": key[2],
                    "enrollment_ids": [r["id"] for r in rows],
                    "offering_ids": [r["offering_id"] for r in rows],
                    "cached_absences": [r["absence_hours"] for r in rows],
                    "raw_absences": [raw_hours[r["id"]] for r in rows],
                }
            )
    for key, marks in slot_marks.items():
        if len(marks) > 1 and any(m["status"] == "absent" for m in marks):
            issues["duplicate_absence_slot"].append(
                {
                    "student_id": key[0],
                    "student": person(key[0]),
                    "subject": key[2],
                    "date": key[3],
                    "time": key[4],
                    "kind": key[5],
                    "statuses": sorted({m["status"] for m in marks}),
                    "marks": marks,
                }
            )
    return {
        "as_of": date.fromisoformat(as_of).isoformat(),
        "source": data["metadata"],
        "counts": {"active_started_current_year_offerings": len(current), "scope_offerings": len(offerings)},
        "issue_counts": {key: len(value) for key, value in sorted(issues.items())},
        "issues": dict(issues),
        "inventory": [context(oid) for oid in sorted(current)],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(json.loads(args.source.read_bytes()))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    args.output.chmod(0o600)
    print(json.dumps({"counts": result["counts"], "issue_counts": result["issue_counts"]}, ensure_ascii=False))
