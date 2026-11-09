"""Build a private executable plan from a full authenticated capture and original source rows."""

import collections
import json

from .class_history import fingerprint as class_history_fingerprint
from .class_history import from_tables as class_history_from_tables
from .creation_proof import created_ids, seal
from .ledger import effective_maps
from .manifest import CUTOFF, FORMAT, digest, normalize, require, validate
from .planning import COMPONENTS
from .source_rows import rows


def group_ids(journal):
    value = journal.get("group_ids", journal.get("groups_id", []))
    try:
        value = json.loads(value) if isinstance(value, str) else value
        return [str(int(item)) for item in value] if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


class Builder:
    def __init__(
        self,
        *,
        source,
        current,
        organization_id,
        period_id,
        source_system,
        source_sha256,
        current_sha256,
        owner_present_policy="applicable_blank_without_grade_hold",
    ):
        self.source, self.tables = source, normalize(current["tables"])
        self.org, self.period, self.system = organization_id, period_id, source_system
        self.current_hash = current_sha256
        self.offerings = [
            r for r in self.table("registrar.CourseOffering") if r["period_id"] == period_id and r["is_active"]
        ]
        require(bool(self.offerings), "full_capture_active_offerings_required")
        base = [r for r in self.table("legacy_import.LegacyEntityMap") if r["source_system"] == source_system]
        base_ids = {row["id"] for row in base}
        self.ledger = effective_maps(
            base, [r for r in self.table("legacy_import.LegacyEntityMapVersion") if r["entity_map_id"] in base_ids]
        )
        self.maps = collections.defaultdict(set)
        for row in self.ledger:
            self.maps[(row["entity_type"], row["target_model_label"], row["legacy_pk"])].add(str(row["target_pk"]))
        self.lessons = self.table("registrar.Lesson")
        self.enrollments = self.table("registrar.Enrollment")
        self.marks = {(r["lesson_id"], r["enrollment_id"]): r for r in self.table("registrar.LessonMark")}
        self.components = self.table("registrar.AssessmentComponent")
        self.creation_audits = collections.defaultdict(list)
        for audit in self.table("audit.AuditLog"):
            for mark_id in created_ids(audit):
                self.creation_audits[mark_id].append(audit)
        self.enrollment_index = collections.defaultdict(list)
        for enrollment in self.enrollments:
            if enrollment["status"] == "enrolled" and enrollment["superseded_by_id"] is None:
                self.enrollment_index[(enrollment["offering_id"], str(enrollment["student_id"]))].append(enrollment)
        self.lesson_index = collections.defaultdict(list)
        for lesson in self.lessons:
            self.lesson_index[
                (lesson["offering_id"], lesson["date"], str(lesson["start_time"] or "")[:5], lesson["kind"])
            ].append(lesson)
        self.courses = {course["id"]: course for course in self.offerings}
        self.plan = {
            "format": FORMAT,
            "organization_id": organization_id,
            "period_id": period_id,
            "source_system": source_system,
            "source_sha256": source_sha256,
            "current_capture_sha256": current_sha256,
            "cutoff": CUTOFF.isoformat(),
            "scope": "entire_active_period",
            "offering_ids": sorted(r["id"] for r in self.offerings),
            "owner_present_policy": owner_present_policy,
            "allow_new_lessons": bool(source.get("class_authorities")),
            "routes": [],
            "sources": [],
        }
        self.journals = collections.defaultdict(list)
        for journal in source["journals"]:
            self.journals[journal["uniqid"]].append(journal)

    def table(self, label):
        require(label in self.tables, "full_capture_table_missing")
        data = self.tables[label]
        require(all(str(row["organization_id"]) == self.org for row in data), "cross_tenant_capture_row")
        return data

    def mapped(self, entity, label, legacy):
        return self.maps[(entity, label, str(legacy))]

    def route(self, journal):
        routes, candidates = [], set()
        subject = self.mapped("lesson_subject", "registrar.subject", journal["lesson_id"])
        teacher = self.mapped("worker", "auth.user", journal["teacher_id"])
        for gid in group_ids(journal):
            group = self.mapped("group_unit", "organizations.orgunit", gid)
            direct = self.mapped("course_offering", "registrar.courseoffering", journal["uniqid"] + ":" + gid)
            for course in self.offerings:
                typed = (
                    subject == {course["subject_id"]}
                    and teacher == {str(course["instructor_id"])}
                    and group == {course["group_id"]}
                )
                if course["id"] in direct or (
                    group == {course["group_id"]} and teacher == {str(course["instructor_id"])}
                ):
                    candidates.add(course["id"])
                if not typed:
                    continue
                spec = {
                    "key": f"{journal['id']}:{gid}:{course['id']}",
                    "offering_id": course["id"],
                    "mode": "offering_ledger" if direct == {course["id"]} else "unique_typed_class",
                    "legacy_offering_key": journal["uniqid"] + ":" + gid,
                    "legacy_subject_id": str(journal["lesson_id"]),
                    "legacy_group_id": gid,
                    "legacy_teacher_id": str(journal["teacher_id"]),
                }
                routes.append(spec)
        return routes, candidates

    def attach(self, row, routes):
        student = self.mapped("student", "auth.user", row["legacy_student_id"])
        possible = [
            (route, enrollment)
            for route in routes
            for user in student
            for enrollment in self.enrollment_index[(route["offering_id"], user)]
        ]
        unique = {(route["offering_id"], enrollment["id"]): (route, enrollment) for route, enrollment in possible}
        if len(student) != 1 or len(unique) != 1:
            return
        route, enrollment = next(iter(unique.values()))
        row["route_keys"] = [route["key"]]
        course = self.courses[route["offering_id"]]
        if row["kind"] == "component":
            expected = COMPONENTS.get(row["component_code"])
            candidates = [
                c
                for c in self.components
                if c["offering_id"] == course["id"] and (c["kind"], c["name"], c["order"]) == expected
            ]
            if len(candidates) == 1:
                row["component_id"] = candidates[0]["id"]
            return
        matches = self.lesson_index[(course["id"], row["source_date"], row["source_time"], row["source_kind"])]
        # Source has no subgroup label: multiple slots never become guessed matches.
        if len(matches) == 1:
            lesson = matches[0]
            row["slot"] = {
                key: lesson[key]
                for key in ("date", "start_time", "end_time", "kind", "hours", "lab_group", "seminar_group")
            }
            row["slot"]["instructor_id"] = lesson["instructor_id"] or course["instructor_id"]
            mark = self.marks.get((lesson["id"], enrollment["id"]))
            mappings = [
                m
                for m in self.ledger
                if m["entity_type"] == "journal_marks"
                and m["legacy_pk"] == row["legacy_journal_uniqid"]
                and m["target_pk"] == course["id"]
                and m["target_model_label"] == "registrar.courseoffering"
            ]
            if mark and len(mappings) == 1:
                row["import_proof"] = {
                    "map_id": mappings[0]["id"],
                    "mark_sha256": digest(mark),
                    "capture_sha256": self.current_hash,
                }
                row["_captured_absent"] = mark["status"] == "absent"
            if mark and len(self.creation_audits[mark["id"]]) == 1:
                audit = self.creation_audits[mark["id"]][0]
                row["import_proof"] = {
                    "audit_id": audit["id"],
                    "audit_sha256": seal(audit),
                    "mark_sha256": digest(mark),
                    "capture_sha256": self.current_hash,
                }
                row["_captured_absent"] = mark["status"] == "absent"
        elif not matches:
            authorities = [
                a
                for a in self.source.get("class_authorities", [])
                if a["offering_id"] == course["id"]
                and a["journal_uniqid"] == row["legacy_journal_uniqid"]
                and a["slot"]["date"] == row["source_date"]
                and str(a["slot"]["start_time"])[:5] == row["source_time"]
                and a["slot"]["kind"] == row["source_kind"]
            ]
            if len(authorities) == 1:
                authority = authorities[0]
                expected_history = authority.get("class_history_sha256")
                current_history = class_history_fingerprint(
                    class_history_from_tables(self.tables), course=course, slot=authority["slot"]
                )
                if expected_history != current_history:
                    row["hold_reason"] = "reviewed_class_history_changed_or_missing"
                    return
                row.update(
                    class_history_sha256=expected_history,
                    slot=authority["slot"],
                    class_authority_sha256=digest(authority),
                    group_mask_proven=authority.get("group_mask_proven") is True,
                )

    def build(self):
        routes_by_journal = {}
        for uniqid, journals in self.journals.items():
            if len(journals) == 1:
                routes, candidates = self.route(journals[0])
                routes_by_journal[uniqid] = routes, candidates
                self.plan["routes"].extend(routes)
        for row in rows(self.source):
            journals = self.journals.get(row["legacy_journal_uniqid"], [])
            routes, candidates = routes_by_journal.get(row["legacy_journal_uniqid"], ([], set()))
            row["route_keys"] = [route["key"] for route in routes]
            row["candidate_offering_ids"] = sorted(candidates)
            if len(journals) != 1 or journals[0].get("fake") or journals[0].get("sonra_sil"):
                row["hold_reason"] = "source_journal_identity_or_flag_review"
            self.attach(row, routes)
            captured_absent = row.pop("_captured_absent", False)
            if row.get("source_blank") and not captured_absent:
                continue
            self.plan["sources"].append(row)
        self.plan["source_ids_sha256"] = digest(sorted(row["id"] for row in self.plan["sources"]))
        self.plan["inventory_counts"] = dict(collections.Counter(row["kind"] for row in self.plan["sources"]))
        return validate(self.plan)
