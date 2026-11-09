"""Offline all-period source/final comparison; no ORM, identity guesses or writes to EMS."""

import argparse
import datetime as dt
import hashlib
import json
import os
import stat
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from apps.registrar.reaudit_cells.ledger import effective_maps  # noqa: E402

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
CURRENT_PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
SYSTEM = "myedu_mariadb"
MAX_BYTES = 512 * 1024 * 1024
REQUIRED = (
    "organizations.AcademicPeriod",
    "registrar.CourseOffering",
    "registrar.Enrollment",
    "registrar.FinalGrade",
    "registrar.ResitRecord",
    "registrar.ExamScoreEntry",
    "registrar.ExamScoreSheet",
    "registrar.LegacyGradeFact",
    "registrar.LegacyGradeReview",
    "legacy_import.LegacyEntityMap",
    "legacy_import.LegacyEntityMapVersion",
)


def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def number(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def source_key(row):
    parts = str(row.get("time") or "").split(":")
    try:
        hour, minute = int(parts[0]), int(parts[1])
        clock = f"{hour:02d}:{minute:02d}" if 0 <= hour < 24 and 0 <= minute < 60 else ""
    except (ValueError, IndexError):
        clock = ""
    return row["journal_uniqid"], row["month_id"], str(row["day_number"]), str(row["student_id"]), clock


def native_winners(source):
    journals = {r["uniqid"]: r for r in source["journals"]}
    require(len(journals) == len(source["journals"]), "source_journal_key_not_unique")
    winners = {}
    for row in source["points"]["journals_dates_points"]:
        journal = journals.get(row["journal_uniqid"])
        if not journal or int(journal.get("fake") or 0) or int(journal.get("sonra_sil") or 0):
            continue
        require(row["month_id"] in ("im", "im2"), "non_final_point_in_source")
        rank = (int(row.get("update_counter") or 0), str(row.get("updated_at") or ""), int(row["id"]))
        key = source_key(row)
        if key not in winners or rank > winners[key][0]:
            winners[key] = (rank, row)
    return journals, [value[1] for value in winners.values()]


def indexed(rows, key):
    result = defaultdict(list)
    for row in rows:
        result[str(row[key])].append(row)
    return result


def latest(rows):
    if not rows:
        return [], False
    parsed = [(timestamp(row.get("created_at")), row) for row in rows]
    if any(t is None for t, _ in parsed):
        return rows, True
    last = max(t for t, _ in parsed)
    return [row for t, row in parsed if t == last], False


class Comparison:
    def __init__(self, current, source, selected):
        self.tables = current["tables"]
        require(set(REQUIRED) <= set(self.tables), "historical_snapshot_tables_missing")
        for label in REQUIRED:
            rows = self.tables[label]
            require(all(str(r["organization_id"]) == ORG for r in rows), "foreign_tenant_snapshot")
            require(len(rows) == len({str(r["id"]) for r in rows}), "snapshot_duplicate_id")
        self.periods = {str(r["id"]): r for r in self.tables[REQUIRED[0]]}
        self.offerings = {str(r["id"]): r for r in self.tables[REQUIRED[1]]}
        self.enrollments = {str(r["id"]): r for r in self.tables[REQUIRED[2]]}
        self.journals, self.sources = native_winners(source)
        expected = {str(row["source_id"]) for row in selected["rows"]}
        require(len(expected) == len(selected["rows"]), "duplicate_selected_source")
        require(expected == {str(row["id"]) for row in self.sources}, "native_selection_changed")
        lookup = {str(row["id"]): row for row in self.sources}
        for row in selected["rows"]:
            original = lookup[str(row["source_id"])]
            require(
                row["table"] == "journals_dates_points"
                and str(row["source_student_id"]) == str(original["student_id"])
                and row["journal_uniqid"] == original["journal_uniqid"]
                and row["kind"] == original["month_id"],
                "selected_source_identity_changed",
            )
        effective = effective_maps(
            self.tables["legacy_import.LegacyEntityMap"], self.tables["legacy_import.LegacyEntityMapVersion"]
        )
        self.maps = defaultdict(set)
        for row in effective:
            if row["source_system"] == SYSTEM:
                self.maps[(row["entity_type"], str(row["legacy_pk"]), row["target_model_label"])].add(
                    str(row["target_pk"])
                )
        self.grades = indexed(self.tables["registrar.FinalGrade"], "enrollment_id")
        self.resits = indexed(self.tables["registrar.ResitRecord"], "enrollment_id")
        self.entries = indexed(
            [r for r in self.tables["registrar.ExamScoreEntry"] if r["assessment"] == "final"], "enrollment_id"
        )
        self.facts = defaultdict(list)
        for row in self.tables["registrar.LegacyGradeFact"]:
            if row["source_system"] == SYSTEM:
                self.facts[(row["source_table"], str(row["source_pk"]))].append(row)
        self.reviews = indexed(self.tables["registrar.LegacyGradeReview"], "fact_id")

    def mapped(self, entity, pk, label):
        return self.maps[(entity, str(pk), label)]

    def route(self, row):
        journal = self.journals[row["journal_uniqid"]]
        keys = self.mapped("journal_enrollment", f'{row["journal_uniqid"]}:{row["student_id"]}', "registrar.enrollment")
        if len(keys) != 1:
            return None, "enrollment_route_missing" if not keys else "enrollment_route_ambiguous"
        enrollment = self.enrollments.get(next(iter(keys)))
        if not enrollment:
            return None, "mapped_enrollment_closure_missing"
        course = self.offerings.get(str(enrollment["offering_id"]))
        if not course or str(course["period_id"]) not in self.periods:
            return None, "course_period_closure_missing"
        checks = (
            ("student", row["student_id"], "auth.user", enrollment["student_id"], "student"),
            ("lesson_subject", journal["lesson_id"], "registrar.subject", course["subject_id"], "subject"),
            ("academic_period", journal["semestr"], "organizations.academicperiod", course["period_id"], "period"),
        )
        for entity, source_id, label, target, name in checks:
            mapped = self.mapped(entity, source_id, label)
            if mapped != {str(target)}:
                return None, name + ("_mapping_missing" if not mapped else "_mapping_conflict")
        return enrollment, "exact_canonical_enrollment_student_subject_period"

    def review_state(self, rows, enrollment_id):
        records, bad_time = [], False
        for row in rows:
            for fact in self.facts[("journals_dates_points", str(row["id"]))]:
                if str(fact.get("enrollment_id")) == enrollment_id:
                    reviews, uncertain = latest(self.reviews[str(fact["id"])])
                    records.extend(reviews)
                    bad_time |= uncertain
        return records, bad_time

    def compare_target(self, enrollment_id, kind, rows):
        enrollment = self.enrollments[enrollment_id]
        offering = self.offerings[str(enrollment["offering_id"])]
        stored = (self.grades if kind == "im" else self.resits).get(enrollment_id, [])
        # J6 accepts digit-only legacy cells; decimal-looking tokens are evidence,
        # not silently reinterpreted as canonical numeric scores.
        values = {number(row["point"]) if str(row["point"]).isdigit() else None for row in rows}
        entries, entry_time_unknown = latest(self.entries.get(enrollment_id, []) if kind == "im" else [])
        reviews, review_time_unknown = self.review_state(rows, enrollment_id)
        current = number(stored[0].get("exam_score" if kind == "im" else "resit_score")) if len(stored) == 1 else None
        source = next(iter(values)) if len(values) == 1 else None
        status = "source_current_difference_needs_authority"
        if len(stored) > 1:
            status = "multiple_current_target_rows_hold"
        elif len(values) != 1:
            status = "conflicting_canonical_source_values_hold"
        elif source is None or not 0 <= source <= 100:
            status = "source_non_numeric_or_invalid_hold"
        elif any(r["decision"] != "verified" for r in reviews) or review_time_unknown:
            status = "source_review_disputed_or_uncertain_hold"
        elif kind == "im2" and stored and stored[0]["status"] != "completed" and current is not None:
            status = "resit_status_score_conflict_hold"
        elif entries:
            entry_values = {number(r.get("new_score")) for r in entries}
            if entry_time_unknown or len(entry_values) != 1:
                status = "official_entry_order_ambiguous_hold"
            elif current in entry_values:
                status = "source_current_equal" if current == source else "protected_current_official_entry"
            else:
                status = "current_differs_latest_official_entry_hold"
        elif any(r["reason_code"] == "exam_center_corrected" for r in reviews):
            status = "reviewed_correction_preserve_current_hold"
        elif current == source:
            status = "source_current_equal"
        elif current is None:
            status = "source_present_current_blank_needs_authority"
        elif stored and stored[0].get("entered_by_id") is not None:
            status = "authored_current_final_provenance_required"
        return {
            "enrollment_id": enrollment_id,
            "offering_id": str(offering["id"]),
            "period_id": str(offering["period_id"]),
            "historical": str(offering["period_id"]) != CURRENT_PERIOD,
            "kind": kind,
            "source_ids": sorted(str(r["id"]) for r in rows),
            "current_row_ids": [str(r["id"]) for r in stored],
            "official_entry_ids": [str(r["id"]) for r in entries],
            "official_entry_kinds": sorted({r["kind"] for r in entries}),
            "review_ids": [str(r["id"]) for r in reviews],
            "source_numeric_present": source is not None,
            "source_zero": source == 0,
            "current_numeric_present": current is not None,
            "status": status,
            "eligible_for_apply": False,
        }

    def result(self, source, history):
        source_rows, targets = [], defaultdict(list)
        for row in self.sources:
            enrollment, outcome = self.route(row)
            semester = str(self.journals[row["journal_uniqid"]]["semestr"])
            record = {
                "source_table": "journals_dates_points",
                "source_id": str(row["id"]),
                "source_student_id": str(row["student_id"]),
                "source_journal_id": str(self.journals[row["journal_uniqid"]]["id"]),
                "semester": semester,
                "kind": row["month_id"],
                "route_status": outcome,
                "enrollment_id": str(enrollment["id"]) if enrollment else None,
                "eligible_for_apply": False,
            }
            source_rows.append(record)
            if enrollment:
                targets[(str(enrollment["id"]), row["month_id"])].append(row)
        target_rows = [self.compare_target(eid, kind, rows) for (eid, kind), rows in sorted(targets.items())]
        current_only = []
        for kind, index in (("im", self.grades), ("im2", self.resits)):
            keys = set(index) | (set(self.entries) if kind == "im" else set())
            for eid in sorted(keys):
                rows = index.get(eid, [])
                if (eid, kind) in targets:
                    continue
                enrollment = self.enrollments.get(eid)
                course = self.offerings.get(str(enrollment["offering_id"])) if enrollment else None
                official, uncertain = latest(self.entries.get(eid, []) if kind == "im" else [])
                actual = number(rows[0].get("exam_score")) if kind == "im" and len(rows) == 1 else None
                values = {number(r.get("new_score")) for r in official}
                official_status = "no_final_entry_in_capture"
                if official:
                    official_status = (
                        "official_entry_order_ambiguous_hold"
                        if uncertain or len(values) != 1
                        else (
                            "current_matches_latest_official_entry"
                            if actual in values
                            else "current_differs_latest_official_entry_hold"
                        )
                    )
                current_only.append(
                    {
                        "enrollment_id": eid,
                        "kind": kind,
                        "current_row_ids": [str(r["id"]) for r in rows],
                        "period_id": str(course["period_id"]) if course else None,
                        "status": "no_exact_native_source_route" if course else "target_reference_closure_missing",
                        "official_entry_status": official_status,
                        "official_entry_ids": [str(r["id"]) for r in official],
                        "eligible_for_apply": False,
                    }
                )
        enrollment_coverage = []
        for eid, enrollment in sorted(self.enrollments.items()):
            course = self.offerings.get(str(enrollment["offering_id"]))
            if course and str(course["period_id"]) == CURRENT_PERIOD:
                continue
            enrollment_coverage.append(
                {
                    "enrollment_id": eid,
                    "offering_id": str(enrollment["offering_id"]),
                    "period_id": str(course["period_id"]) if course else None,
                    "source_im_routed": (eid, "im") in targets,
                    "source_im2_routed": (eid, "im2") in targets,
                    "current_final_row_present": bool(self.grades.get(eid)),
                    "current_resit_row_present": bool(self.resits.get(eid)),
                    "official_final_entry_present": bool(self.entries.get(eid)),
                    "status": "coverage_only_not_a_lost_grade_claim" if course else "course_closure_missing_hold",
                    "eligible_for_apply": False,
                }
            )
        raw_sem14 = sum(
            int(self.journals.get(r["journal_uniqid"], {}).get("semestr") or 0) == 14
            for rows in source["points"].values()
            for r in rows
        )
        return {
            "format": "offline-historical-final-comparison/1",
            "all_academic_results_verified": False,
            "eligible_for_apply": False,
            "summary": {
                "native_source_cells": len(source_rows),
                "raw_main_source_rows": len(source["points"]["journals_dates_points"]),
                "raw_main_rows_outside_native_selection": len(source["points"]["journals_dates_points"])
                - len(source_rows),
                "source_route_counts": dict(Counter(r["route_status"] for r in source_rows)),
                "target_pairs": len(target_rows),
                "target_status_counts": dict(Counter(r["status"] for r in target_rows)),
                "current_pairs_without_exact_source": len(current_only),
                "current_without_source_official_counts": dict(
                    Counter(r["official_entry_status"] for r in current_only)
                ),
                "historical_enrollments_or_missing_course": len(enrollment_coverage),
                "source_sem14_im_im2_rows": raw_sem14,
                "archive_rows_history_only": len(source["points"].get("journals_dates_points_archive", [])),
                "yekun_rows_not_resolved_by_im_im2_helper": len(source.get("yekun", [])),
                "entry_exit_rows_without_journal_key": len(source.get("exam_entry_exit", [])),
                "non_authoritative_update_log_sample": len(history.get("updates", [])),
            },
            "limitations": [
                "Missing source route does not establish a lost grade.",
                "All rows are comparison or hold; no maximum-score selection or write authority.",
                "Current official entries/reviews are protected; timestamp ties and unknown order are held.",
                "Legacy naive source times are not compared to timezone-aware official timestamps.",
                "Print logs and update_log cannot establish an accepted appeal decision.",
                "Yekun, entry/exit and arbitrary historical online attempts need separate exact source authority.",
                "Historical computed total is not reconstructed from partial component evidence.",
            ],
            "source_rows": source_rows,
            "target_rows": target_rows,
            "current_without_source": current_only,
            "historical_enrollment_coverage": enrollment_coverage,
        }


def load_private(path, expected):
    info = Path(path).lstat()
    require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077, "private_regular_input_required")
    require(info.st_size <= MAX_BYTES, "input_budget")
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "input_hash_mismatch")
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("current", "source", "selection", "history"):
        parser.add_argument("--" + key, required=True)
        parser.add_argument("--" + key + "-sha256", required=True)
    parser.add_argument("--out", required=True)
    args = vars(parser.parse_args())
    data = {
        key: load_private(args[key], args[key + "_sha256"]) for key in ("current", "source", "selection", "history")
    }
    report = Comparison(data["current"], data["source"], data["selection"]).result(data["source"], data["history"])
    report["input_sha256"] = {key: args[key + "_sha256"] for key in data}
    report["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    output = Path(args["out"])
    require(output.parent.is_dir() and not output.parent.stat().st_mode & 0o077, "private_output_directory_required")
    raw = json.dumps(report, ensure_ascii=False, sort_keys=True).encode()
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
        handle.write(raw)
    print(json.dumps({"summary": report["summary"], "output_sha256": hashlib.sha256(raw).hexdigest()}))


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(str(error)) from None
