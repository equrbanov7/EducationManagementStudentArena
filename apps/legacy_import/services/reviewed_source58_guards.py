"""Closed current authority/history/credit gates; no missing export is interpreted as zero."""

import datetime
import hashlib
import json

from django.core.exceptions import EmptyResultSet
from django.db import connection

from apps.registrar.public import handover
from apps.workload.public import fixed_source58_recovery_evidence

from .reviewed_content_contract import ContentError
from .reviewed_content_state import digest, model
from .reviewed_source58_source import require


def rows(evidence, label):
    for key in ("source58_reference_graph", "source58_authority_context"):
        for entry in evidence.get(key, []):
            if entry["model"] == label:
                return entry["rows"]
    return []


def collect(*, actor, organization, lock=False):
    try:
        return fixed_source58_recovery_evidence(actor=actor, organization=organization, lock=lock)
    except ValueError as exc:
        raise ContentError("reviewed_source58_current_evidence_unavailable") from exc


def _ledger(scope, data, evidence):
    expected = {}
    for pin in scope["offerings"].values():
        expected[("worker", str(pin["source_teacher"]))] = ("auth.user", str(pin["instructor_id"]))
        expected[("lesson_subject", str(pin["source_subject"]))] = ("registrar.subject", pin["subject_id"])
    students = {row["id"]: row for row in data["students"]}
    for case in scope["cases"].values():
        expected[("student", str(case["source_student_id"]))] = ("auth.user", str(case["student_id"]))
        expected[("group_unit", str(students[case["source_student_id"]]["group_id"]))] = (
            "organizations.orgunit",
            scope["offerings"][case["offering_id"]]["group_id"],
        )
    seen = {}
    for row in evidence["source58_typed_ledger"]:
        key = row["entity_type"], row["legacy_pk"]
        require(row["state"] == "migrated", "source_ledger_state_requires_review")
        if key in expected:
            require(
                key not in seen and (row["target_model_label"], row["target_pk"]) == expected[key],
                "typed_identity_conflict",
            )
            seen[key] = True
        elif key[0] == "worker_materialisation":
            require(
                (row["target_model_label"], row["target_pk"]) == expected.get(("worker", key[1])),
                "worker_materialisation_identity_conflict",
            )
        elif key[0] in {"course_offering", "journal_enrollment"}:
            wanted = {}
            for c in scope["cases"].values():
                pin = scope["offerings"][c["offering_id"]]
                if key[0] == "course_offering":
                    wanted.update(
                        {
                            f'{pin["source_uniqid"]}:{g}': ("registrar.courseoffering", c["offering_id"])
                            for g in pin["source_groups"]
                        }
                    )
                else:
                    wanted[f'{pin["source_uniqid"]}:{c["source_student_id"]}'] = (
                        "registrar.enrollment",
                        c["enrollment_id"],
                    )
            require(
                (row["target_model_label"], row["target_pk"]) == wanted.get(key[1]),
                "existing_source_claim_requires_review",
            )
    require(set(seen) == set(expected), "all_current_typed_identity_maps_required")


def validate(scope, data, evidence, *, owned_marks=(), owned_receipts=()):
    summary = evidence.get("source58_scope", [])
    require(
        len(summary) == 1 and summary[0].get("bounded_reference_closure_collected") is True,
        "complete_current_closure_required",
    )
    summary = summary[0]
    require(
        summary.get("credit_excuse_coverage") == "EXPORTED_CURRENT_BOUNDED_CLOSURE"
        and summary.get("credit_reversal_closure_complete") is True,
        "complete_credit_excuse_coverage_required",
    )
    require(
        summary.get("source_sha256") == scope["source_sha256"]
        and summary.get("fixed_source_cells") == len(scope["cases"]),
        "current_scope_changed",
    )
    require(
        not evidence["source58_identity_issues"] and not evidence["source58_supersession_issues"],
        "identity_or_supersession_requires_review",
    )
    require(not summary["missing_target_enrollment_ids"], "missing_target_enrollment")
    require(
        set(summary["eligible_current_instructor_ids"])
        >= {pin["instructor_id"] for pin in scope["offerings"].values()},
        "current_teacher_permission_required",
    )
    coverage = evidence.get("source58_history_coverage", [])
    require(len(coverage) == 1 and coverage[0].get("available_scope_collected") is True, "current_history_required")
    require(
        not coverage[0]["unlocatable_delete_audits"] and not evidence["source58_unlocatable_grade_history"],
        "unlocatable_history_requires_review",
    )
    for audit in evidence["source58_history_audits"]:
        require(
            not audit["contrary_clear_evidence"]
            and not audit["contrary_delete_evidence"]
            and not audit["malformed_intent"],
            "contrary_history_requires_review",
        )
        if audit["id"] in owned_receipts:
            continue
        if audit["action"] != "view":
            require(
                audit["resource_kind"] != "other" or audit.get("projection") == "verified_workload_receipt",
                "unclassified_write_or_counter_override_requires_review",
            )
            require(
                not any(
                    audit[k]
                    for k in (
                        "unresolved_scope_row",
                        "malformed_intent",
                        "source_undo_marker",
                        "contrary_clear_evidence",
                        "contrary_delete_evidence",
                    )
                ),
                "contrary_or_unresolved_history_requires_review",
            )
    require(
        not any(c["clear_evidence"] or c["lesson_delete_evidence"] for c in evidence["source58_history_changes"]),
        "clear_or_delete_claim_requires_review",
    )
    require(len(evidence["source58_claims"]) == len(scope["cases"]), "all_source_claims_required")
    for claim in evidence["source58_claims"]:
        require(
            all(row["mark_id"] in owned_marks for row in claim["existing_claims"]),
            "existing_canonical_claim_requires_review",
        )
    _formal_claims(scope, evidence)
    for row in rows(evidence, "registrar.LegacyExcuseDocument"):
        if row["student_id"] is None:
            source_ref = row.get("source_student_ref", "")
            require(
                str(source_ref).isdigit()
                and int(source_ref) not in {c["source_student_id"] for c in scope["cases"].values()},
                "unlocated_formal_excuse_requires_review",
            )
            continue
        relevant = [c for c in scope["cases"].values() if c["student_id"] == row["student_id"]]
        require(row["starts_on"] is not None and row["ends_on"] is not None, "formal_excuse_dates_unknown")
        require(
            not any(row["starts_on"] <= c["date"] <= row["ends_on"] for c in relevant),
            "formal_excuse_covers_source_date",
        )
    _ledger(scope, data, evidence)
    _identity_and_authority(scope, evidence)
    _credits(evidence)
    previews = {row["enrollment_id"]: row for row in evidence["source58_counter_preview"]}
    require(set(previews) == {c["enrollment_id"] for c in scope["cases"].values()}, "all_counter_previews_required")
    return json.loads(json.dumps(previews, default=str))


def _formal_claims(scope, evidence):
    lessons = {r["id"]: r for r in rows(evidence, "registrar.Lesson")}
    enrollments = {r["id"]: r for r in rows(evidence, "registrar.Enrollment")}
    cases = list(scope["cases"].values())
    for label in (
        "registrar.JournalCorrection",
        "registrar.JournalHygieneDecision",
        "registrar.LegacyGradeFact",
        "registrar.LegacyGradeArtifact",
    ):
        for row in rows(evidence, label):
            source = row.get("source_pk")
            require(source is None or int(source) not in scope["cases"], "formal_sourcepoint_claim_requires_review")
            enrollment = enrollments.get(str(row.get("enrollment_ref") or row.get("enrollment_id")))
            relevant = [c for c in cases if enrollment is None or c["student_id"] == enrollment["student_id"]]
            if not relevant:
                continue
            lesson = lessons.get(str(row.get("lesson_ref") or row.get("lesson_id")))
            require(
                lesson is not None and not any(c["date"] == lesson["date"] for c in relevant),
                "formal_claim_requires_review",
            )
    # Reversals never permit replacing a corrected cell. Their parent correction
    # is checked above; all reversal bytes remain protected by the full graph.
    corrections = {r["id"] for r in rows(evidence, "registrar.JournalCorrection")}
    lesson_corrections = {r["id"] for r in rows(evidence, "registrar.LessonCorrection")}
    for row in rows(evidence, "registrar.CorrectionReversal"):
        require(
            str(row.get("journal_correction_id")) in corrections
            or str(row.get("lesson_correction_id")) in lesson_corrections,
            "unlocated_correction_reversal",
        )
    dates = {c["date"] for c in cases}
    for row in rows(evidence, "registrar.LessonCorrection"):
        lesson = lessons.get(str(row.get("lesson_id")))
        known = {row.get("old_date"), row.get("new_date")} - {None}
        if lesson:
            known.add(lesson["date"])
        require(bool(known) and not known & dates, "lesson_correction_requires_review")


def _identity_and_authority(scope, evidence):
    users = {row["id"]: row for row in rows(evidence, "auth.User")}
    profiles = {row["user_id"]: row for row in rows(evidence, "accounts.UserProfile")}
    required = {c["student_id"] for c in scope["cases"].values()} | {
        p["instructor_id"] for p in scope["offerings"].values()
    }
    for uid in required:
        row = profiles.get(uid, {})
        require(
            set(row) >= {"user_id", "organization_id", "access_state", "is_deleted", "deleted_at", "blocked_at"}
            and users.get(uid, {}).get("is_active")
            and row.get("access_state") == "active"
            and not row.get("is_deleted")
            and row.get("deleted_at") is None
            and row.get("blocked_at") is None,
            "active_tenant_identity_required",
        )
    for oid, pin in scope["offerings"].items():
        require(
            model("organizations.OrgUnit")
            .objects.filter(
                pk=pin["group_id"], organization_id=scope["organization_id"], is_active=True, unit_type="group"
            )
            .exists(),
            "active_exact_group_required",
        )
        require(
            model("registrar.Subject")
            .objects.filter(pk=pin["subject_id"], organization_id=scope["organization_id"], is_active=True)
            .exists(),
            "active_exact_subject_required",
        )
        period = model("organizations.AcademicPeriod").objects.get(
            pk=pin["period_id"], organization_id=scope["organization_id"]
        )
        require(period.locked_at is None, "locked_period")
        offering = model("registrar.CourseOffering").objects.get(pk=oid, organization_id=scope["organization_id"])
        require(offering.is_active and offering.pk not in handover.closed_offering_ids([offering.pk]), "closed_target")
        for slot in (s for s in scope["slots"] if s["offering_id"] == oid):
            require(
                period.start_date <= datetime.date.fromisoformat(slot["date"]) <= period.end_date,
                "source_outside_period",
            )
            candidates = model("workload.TeacherAssignment").objects.filter(
                organization_id=scope["organization_id"],
                teacher_id=pin["instructor_id"],
                activity=slot["kind"],
                hours__gt=0,
                row__subject_id=pin["subject_id"],
                row__period_id=pin["period_id"],
                row__groups__id=pin["group_id"],
                row__row_kind="teaching",
                row__task__academic_year="2026/2027",
                row_id__in=evidence["source58_runtime_released_rows"],
            )
            require(candidates.exists(), "exact_kind_workload_authority_required")
    for case in scope["cases"].values():
        groups = {
            row["group_id"]
            for row in rows(evidence, "registrar.StudentAcademicRecord")
            if row["student_id"] == case["student_id"] and row["is_active"] and row["status"] == "enrolled"
        }
        require(groups == {scope["offerings"][case["offering_id"]]["group_id"]}, "current_exact_home_group_required")


def _credits(evidence):
    credits = {row["id"]: row for row in rows(evidence, "registrar.AbsenceCredit")}
    for row in credits.values():
        require(type(row["hours"]) is int and row["hours"] > 0, "invalid_credit_hours")
        if row["reverses_id"] is None:
            continue
        root = credits.get(row["reverses_id"])
        require(
            root is not None
            and root["reverses_id"] is None
            and root["enrollment_id"] == row["enrollment_id"]
            and root["hours"] == row["hours"],
            "invalid_credit_reversal",
        )


def fingerprint(query, *, excluded_fields=()):
    try:
        sql, params = query.order_by().query.sql_with_params()
    except EmptyResultSet:
        # The ORM has proved an empty explicit PK set; missing evidence is
        # rejected separately and is never converted to an empty result here.
        return {"count": 0, "sha256": hashlib.sha256(b"").hexdigest()}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*), encode(sha256(convert_to(COALESCE(string_agg(encode(sha256(convert_to((to_jsonb(s)-%s::text[])::text,'UTF8')),'hex'),'' ORDER BY s.id::text),''),'UTF8')),'hex') FROM ("
            + sql
            + ") s",
            [list(excluded_fields), *params],
        )
        count, sha = cursor.fetchone()
    return {"count": count, "sha256": sha}


def protected(scope, evidence, *, created_lessons=(), created_marks=()):
    targets = {c["enrollment_id"] for c in scope["cases"].values()}
    graph = {entry["model"]: entry["rows"] for entry in evidence["source58_reference_graph"]}
    labels = set(graph) | {
        "registrar.Lesson",
        "registrar.LessonMark",
        "registrar.Enrollment",
        "registrar.AbsenceCredit",
    }
    result = {}
    for label in sorted(labels):
        cls = model(label)
        if label == "auth.User":
            continue
        query = cls._base_manager.all()
        if any(f.name == "organization" for f in cls._meta.concrete_fields):
            query = query.filter(organization_id=scope["organization_id"])
        else:
            query = query.filter(pk__in=[row[cls._meta.pk.attname] for row in graph.get(label, [])])
        if label == "registrar.Lesson":
            query = query.exclude(pk__in=created_lessons)
        elif label == "registrar.LessonMark":
            query = query.exclude(pk__in=created_marks)
        elif label == "registrar.Enrollment":
            result["target_enrollment_identity"] = fingerprint(
                query.filter(pk__in=targets), excluded_fields=["absence_hours"]
            )
            query = query.exclude(pk__in=targets)
        result[label] = fingerprint(query)
    return result


def stable_evidence(evidence, *, owned_receipts=()):
    excluded = {
        "source58_reference_graph",
        "source58_counter_preview",
        "source58_claims",
        "source58_source_slot_coverage",
        "source58_scope",
        "source58_history_coverage",
    }
    result = {key: value for key, value in evidence.items() if key not in excluded}
    result["source58_history_audits"] = [
        row for row in result["source58_history_audits"] if row["id"] not in owned_receipts
    ]
    result["source58_history_changes"] = [
        row for row in result["source58_history_changes"] if row["audit_id"] not in owned_receipts
    ]
    return digest(result)
