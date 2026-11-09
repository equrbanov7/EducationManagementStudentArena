"""Plan the complete live grid; source numeric grades precede owner-assigned attendance."""

import collections
import uuid
from types import SimpleNamespace

from ..gradebook import assessment_scheme_is_locked
from ..lab_groups import applies, per_student_hours
from .class_history import fingerprint as class_history_fingerprint
from .class_history import from_snapshot as class_history_from_snapshot
from .manifest import CUTOFF, SHA, RepairError, clock, day, digest, number
from .proofs import Proofs
from .restoration import imported_attendance_proof

COMPONENTS = {
    "k1": ("kollokvium", "Kollokvium 1", 1),
    "k2": ("kollokvium", "Kollokvium 2", 2),
    "k3": ("kollokvium", "Kollokvium 3", 3),
    "si": ("self_work", "Sərbəst iş", 4),
}


def slot_key(row):
    return (
        row["offering_id"],
        row["date"],
        str(row["start_time"] or "")[:5],
        row["kind"],
        row["lab_group"],
        row["seminar_group"],
    )


def applicable(lesson, enrollment):
    return applies(SimpleNamespace(**lesson), SimpleNamespace(**enrollment))


class Planner:
    def __init__(self, plan, snapshot):
        self.plan, self.snapshot = plan, snapshot
        self.proofs = Proofs(plan, snapshot)
        self.counts = collections.Counter()
        self.holds, self.new_lessons, self.new_marks, self.new_components = [], {}, {}, {}
        self.restored_marks = {}
        self.grade_blocked_offerings, self.global_grade_hold = set(), False
        self.unknown_grade_sources = set()
        self.grade_cells = set()
        self.conflicted_cells, self.conflicted_components = set(), set()
        self.slots = collections.defaultdict(list)
        for lesson in snapshot["lessons"]:
            self.slots[slot_key(lesson)].append(lesson)
        self.marks = {(row["lesson_id"], row["enrollment_id"]): row for row in snapshot["marks"]}
        self.components = {row["id"]: row for row in snapshot["components"]}
        self.component_scores = {
            (row["component_id"], row["enrollment_id"]): row for row in snapshot["component_scores"]
        }
        self.protected_cells = {(row["lesson_ref"], row["enrollment_ref"]) for row in snapshot["journal_corrections"]}
        self.protected_components = {
            (row["component_id"], row["enrollment_id"]) for row in snapshot["component_corrections"]
        }
        self.closed = {
            row["offering_id"] for row in snapshot["schemes"] if assessment_scheme_is_locked(SimpleNamespace(**row))
        }

    def hold(self, source, reason, offering=None, cell_known=False):
        self.holds.append({"source_id": source["id"], "reason": reason, "offering_id": offering})
        self.counts["hold_" + reason] += 1
        if source["kind"] == "grade":
            if offering and not cell_known:
                self.grade_blocked_offerings.add(offering)
            elif not offering and reason != "no_current_enrollment":
                self.global_grade_hold = True
                self.unknown_grade_sources.add(source["id"])
                self.grade_blocked_offerings.update(source.get("candidate_offering_ids", []))

    def lesson(self, source, course):
        spec = source.get("slot", {})
        required = {"date", "start_time", "end_time", "kind", "hours", "lab_group", "seminar_group", "instructor_id"}
        if not isinstance(spec, dict) or not required.issubset(spec):
            return None, "exact_source_class_fields_required"
        date, start = day(spec["date"]), clock(spec["start_time"])
        end = clock(spec["end_time"]) if spec["end_time"] is not None else None
        period = self.snapshot["period"][0]
        if not period["start_date"] <= date.isoformat() <= min(period["end_date"], CUTOFF.isoformat()):
            return None, "source_date_outside_current_period_cutoff"
        if spec["kind"] not in {"lecture", "seminar", "lab"} or end is not None and start >= end:
            return None, "invalid_source_class"
        if type(spec["hours"]) is not int or not 1 <= spec["hours"] <= 12:
            return None, "exact_source_hours_required"
        if spec["instructor_id"] != course["instructor_id"]:
            return None, "source_lesson_teacher_unresolved"
        for field, kind in (("lab_group", "lab"), ("seminar_group", "seminar")):
            value = spec[field]
            if value is not None and (type(value) is not int or not 1 <= value <= 9 or spec["kind"] != kind):
                return None, "invalid_source_group_mask"
        desired = {
            **spec,
            "offering_id": course["id"],
            "date": date.isoformat(),
            "start_time": start.isoformat(),
            "end_time": end.isoformat() if end else None,
        }
        key = slot_key(desired)
        matches = self.slots.get(key, [])
        if len(matches) > 1:
            return None, "ambiguous_current_lesson_slot"
        if matches:
            match = matches[0]
            if (
                any(match[field] != desired[field] for field in ("hours", "end_time"))
                or (match["instructor_id"] or course["instructor_id"]) != desired["instructor_id"]
            ):
                return None, "current_lesson_identity_changed"
            return match, None
        if not self.plan.get("allow_new_lessons") or not SHA.fullmatch(str(source.get("class_authority_sha256", ""))):
            return None, "missing_lesson_requires_exact_source_authority"
        expected_history = source.get("class_history_sha256")
        if not SHA.fullmatch(str(expected_history or "")):
            return None, "missing_lesson_class_history_required"
        current_history = class_history_fingerprint(
            class_history_from_snapshot(self.snapshot), course=course, slot=desired
        )
        if expected_history != current_history:
            return None, "missing_lesson_class_history_changed"
        if source.get("group_mask_proven") is not True:
            return None, "new_lesson_group_mask_authority_required"
        if (
            spec["kind"] == "lab"
            and spec["lab_group"] is None
            and any(row["offering_id"] == course["id"] for row in self.snapshot["lab_groups"])
        ):
            return None, "new_lesson_lab_group_required"
        current = [r for r in self.snapshot["lessons"] if r["offering_id"] == course["id"]]
        current += [r for r in self.new_lessons.values() if r["offering_id"] == course["id"]]
        if (
            not course["lesson_hours"]
            or per_student_hours([SimpleNamespace(**r) for r in current + [desired]]) > course["lesson_hours"]
        ):
            return None, "new_lesson_hours_exceed_authoritative_load"
        desired["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "reaudit-lesson:" + digest(key)))
        desired["source_ids"] = [source["id"]]
        self.new_lessons[key] = desired
        self.slots[key] = [desired]
        return desired, None

    def mark(self, source, course, enrollment):
        try:
            lesson, reason = self.lesson(source, course)
        except RepairError as exc:
            self.hold(source, str(exc), course["id"])
            return
        if reason:
            self.hold(source, reason, course["id"])
            return
        if not applicable(lesson, enrollment):
            self.counts["source_other_group_mask"] += 1
            if source["kind"] == "grade":
                self.hold(source, "source_grade_group_mask_disagreement", course["id"], cell_known=True)
            return
        cell = (lesson["id"], enrollment["id"])
        if enrollment["superseded_by_id"] is not None:
            self.hold(source, "current_enrollment_has_history_successor", course["id"])
            return
        if cell in self.conflicted_cells:
            self.hold(source, "conflicting_source_values", course["id"])
            return
        score = number(source["score"]) if source["kind"] == "grade" else None
        if score is not None:
            self.grade_cells.add(cell)
            if lesson["kind"] not in {"seminar", "lab"}:
                self.hold(source, "source_grade_on_non_scoring_class", course["id"])
                return
            policy, status = "source_score_preserve", "present"
        elif source.get("certain") and source["status"] != "unknown":
            policy, status = "confirmed_attendance", source["status"]
        else:
            policy, status = "owner_assigned_present", "present"
            if self.plan["owner_present_policy"] == "disabled" or course["id"] in self.grade_blocked_offerings:
                self.hold(source, "owner_present_policy_disabled_or_grade_hold", course["id"])
                return
        old = self.marks.get(cell)
        if old is not None:
            if cell in self.restored_marks and self.restored_marks[cell]["score"] is not None and score is None:
                return
            if (
                score is not None
                and old["score"] is not None
                and number(old["score"]) == score
                and old["status"] == "present"
            ):
                self.counts["source_grade_already_preserved"] += 1
            elif (
                score is not None or old["status"] == "absent" and status in {"present", "excused"}
            ) and cell not in self.protected_cells:
                refusal = imported_attendance_proof(source=source, mark=old, course=course, snapshot=self.snapshot)
                if refusal:
                    self.hold(source, refusal, course["id"], cell_known=True)
                elif cell in self.restored_marks and (
                    self.restored_marks[cell]["score"],
                    self.restored_marks[cell]["status"],
                ) != (str(score) if score is not None else None, status):
                    self.restored_marks.pop(cell)
                    self.conflicted_cells.add(cell)
                    self.hold(source, "conflicting_source_values", course["id"])
                else:
                    self.restored_marks[cell] = {
                        "before": old,
                        "score": str(score) if score is not None else None,
                        "status": status,
                        "source_ids": [source["id"]],
                        "import_proof": source["import_proof"],
                    }
            else:
                self.counts["existing_cell_preserved"] += 1
                if score is not None:
                    self.hold(
                        source, "existing_value_requires_official_correction_review", course["id"], cell_known=True
                    )
            return
        if cell in self.protected_cells:
            self.hold(source, "formal_correction_history_preserved", course["id"], cell_known=True)
            return
        desired = {
            "lesson_id": cell[0],
            "enrollment_id": cell[1],
            "status": status,
            "score": str(score) if score is not None else None,
            "policy": policy,
            "source_ids": [source["id"]],
        }
        existing = self.new_marks.get(cell)
        if existing and existing["policy"] == "source_score_preserve" and score is None:
            return
        if existing and (existing["status"], existing["score"]) != (desired["status"], desired["score"]):
            self.new_marks.pop(cell, None)
            self.conflicted_cells.add(cell)
            self.grade_cells.add(cell)
            self.hold(source, "conflicting_source_values", course["id"])
            return
        if existing:
            existing["source_ids"].append(source["id"])
        else:
            self.new_marks[cell] = desired

    def component(self, source, course, enrollment):
        code = source.get("component_code")
        component = self.components.get(source.get("component_id"))
        expected = COMPONENTS.get(code)
        if expected is None or component is None:
            self.hold(source, "component_semantics_or_existing_component_unknown", course["id"])
            return
        if (
            (component["kind"], component["name"], component["order"]) != expected
            or component["offering_id"] != course["id"]
            or component["max_score"] != 10
            or component["rubric_id"]
        ):
            self.hold(source, "component_current_scheme_incompatible", course["id"])
            return
        if day(source.get("added_date")) > CUTOFF:
            self.hold(source, "component_after_cutoff", course["id"])
            return
        key = (component["id"], enrollment["id"])
        if key in self.conflicted_components:
            self.hold(source, "conflicting_component_sources", course["id"])
            return
        if key in self.component_scores or key in self.protected_components:
            self.counts["existing_component_or_correction_preserved"] += 1
            existing = self.component_scores.get(key)
            if existing is None or number(existing["score"], maximum=100) != number(source["score"], maximum=100):
                self.hold(source, "existing_component_value_requires_official_review", course["id"])
            return
        if number(source["score"], maximum=float("inf")) > 10:
            self.hold(source, "component_source_scale_requires_review", course["id"])
            return
        desired = {
            "component_id": key[0],
            "enrollment_id": key[1],
            "score": str(number(source["score"])),
            "source_ids": [source["id"]],
        }
        previous = self.new_components.get(key)
        if previous and previous["score"] != desired["score"]:
            self.new_components.pop(key)
            self.conflicted_components.add(key)
            self.hold(source, "conflicting_component_sources", course["id"])
        elif previous:
            previous["source_ids"].append(source["id"])
        else:
            self.new_components[key] = desired

    def build(self):
        ordered = sorted(self.plan["sources"], key=lambda row: (row["kind"] != "grade", row["id"]))
        for source in ordered:
            if source.get("hold_reason"):
                self.hold(source, "reviewed_source_hold")
                continue
            targets, reasons = self.proofs.resolve(source)
            for reason in reasons:
                self.hold(source, reason)
            for course, enrollment in targets:
                if course["id"] in self.closed:
                    self.hold(source, "closed_journal_official_path_required", course["id"])
                elif source["kind"] == "component":
                    self.component(source, course, enrollment)
                else:
                    self.mark(source, course, enrollment)
        self.owner_present()
        used = {row["lesson_id"] for row in self.new_marks.values()}
        lessons = [row for row in self.new_lessons.values() if row["id"] in used]
        result = {
            "lessons": lessons,
            "marks": list(self.new_marks.values()),
            "components": list(self.new_components.values()),
            "restorations": list(self.restored_marks.values()),
            "holds": self.holds,
        }
        result["counts"] = dict(
            self.counts,
            lessons_create=len(lessons),
            marks_create=len(self.new_marks),
            components_create=len(self.new_components),
            marks_restore=len(self.restored_marks),
            source_rows=len(self.plan["sources"]),
            hold_rows=len(self.holds),
        )
        return result

    def owner_present(self):
        self.counts["unknown_source_grade_route_reported"] += len(self.unknown_grade_sources)
        if self.plan["owner_present_policy"] == "disabled":
            return
        for course in self.snapshot["offerings"]:
            if course["id"] in self.closed or course["id"] in self.grade_blocked_offerings:
                continue
            enrolled = [
                row
                for row in self.snapshot["enrollments"]
                if row["offering_id"] == course["id"]
                and row["status"] == "enrolled"
                and row["superseded_by_id"] is None
            ]
            for lesson in self.snapshot["lessons"] + list(self.new_lessons.values()):
                if lesson["offering_id"] != course["id"] or not self.snapshot["period"][0]["start_date"] <= lesson[
                    "date"
                ] <= min(CUTOFF.isoformat(), self.snapshot["period"][0]["end_date"]):
                    continue
                for enrollment in enrolled:
                    cell = lesson["id"], enrollment["id"]
                    if (
                        cell in self.marks
                        or cell in self.new_marks
                        or cell in self.grade_cells
                        or cell in self.protected_cells
                        or not applicable(lesson, enrollment)
                    ):
                        continue
                    self.new_marks[cell] = {
                        "lesson_id": cell[0],
                        "enrollment_id": cell[1],
                        "status": "present",
                        "score": None,
                        "policy": "owner_assigned_present",
                        "source_ids": [],
                    }
