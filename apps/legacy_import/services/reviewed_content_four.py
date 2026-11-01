"""Conditional four-cell reuse of the existing missing-only writer, never a new importer."""

from django.db import connection

from apps.workload.public import fixed_four_recovery_history

from . import reviewed_content_four_spec as fixed
from .reviewed_content_contract import ContentError
from .reviewed_content_spec import ORG
from .reviewed_content_state import digest, model


def selected(data):
    return bool(set(data["selected_target_ids"]) & set(fixed.TARGETS))


def require(ok, code):
    if not ok:
        raise ContentError("reviewed_four_" + code)


def source_guard(data, sha):
    if not selected(data):
        return
    raw = {k: v for k, v in data.items() if k not in {"selected_target_ids", "until_date"}}
    require(
        set(data["selected_target_ids"]) == set(fixed.TARGETS)
        and len(data["selected_target_ids"]) == 2
        and sha == fixed.SOURCE_SHA
        and digest(raw) == fixed.PAYLOAD_DIGEST,
        "exact_source_and_two_targets_required",
    )
    require({p["id"] for p in data["points"]} == set(fixed.CASES), "only_four_source_points")


def _expected_ledger():
    wanted = {}
    for spec in fixed.TARGETS.values():
        for kind, source, label, target in (
            ("worker", spec["legacy_teacher_id"], "auth.user", spec["teacher_id"]),
            ("lesson_subject", spec["legacy_subject_id"], "registrar.subject", spec["subject_id"]),
            ("group_unit", spec["legacy_group_id"], "organizations.orgunit", spec["group_id"]),
        ):
            wanted[kind, str(source)] = (label, str(target))
    for case in fixed.CASES.values():
        wanted["student", str(case[3])] = ("auth.user", str(case[4]))
    return wanted


def _ledger_guard(rows):
    expected = _expected_ledger()
    found = {}
    for row in rows:
        key = row["entity_type"], row["legacy_pk"]
        actual = row["target_model_label"], row["target_pk"]
        require(row["state"] == "migrated", "source_ledger_state_changed")
        if key in expected:
            require(key not in found and actual == expected[key], "typed_source_ledger_conflict")
            found[key] = actual
            continue
        if key[0] == "course_offering":
            target = next(
                (oid for oid, s in fixed.TARGETS.items() if key[1] == f'{s["journal_uniqid"]}:{s["legacy_group_id"]}'),
                None,
            )
            require(actual == ("registrar.courseoffering", target), "course_ledger_conflict")
        elif key[0] == "journal_enrollment":
            targets = {f'{fixed.TARGETS[c[0]]["journal_uniqid"]}:{c[3]}': c[2] for c in fixed.CASES.values()}
            require(actual == ("registrar.enrollment", targets.get(key[1])), "enrollment_ledger_conflict")
        else:
            require(False, "additional_source_claim_requires_review")
    require(set(found) == set(expected), "all_ten_typed_identity_ledgers_required")


def _canonical_cells(*, lock):
    """All active/dropped/inactive canonical courses; no registry/group-marker filter."""
    rows = []
    for point, c in fixed.CASES.items():
        oid, lid, eid, sid, uid, day, start = c
        spec = fixed.TARGETS[oid]
        family = model("registrar.CourseOffering").objects.filter(
            organization_id=ORG, subject_id=spec["subject_id"], period_id=spec["period_id"]
        )
        if lock:
            family = family.select_for_update()
        course_ids = list(family.values_list("pk", flat=True)[:1001])
        require(len(course_ids) <= 1000, "canonical_course_budget_exceeded")
        enrs = model("registrar.Enrollment").objects.filter(
            organization_id=ORG, offering_id__in=course_ids, student_id=uid
        )
        lessons = model("registrar.Lesson").objects.filter(
            organization_id=ORG, offering_id__in=course_ids, date=day, start_time=start, kind="seminar"
        )
        if lock:
            enrs, lessons = enrs.select_for_update(), lessons.select_for_update()
        enr_ids = list(enrs.values_list("pk", flat=True)[:1001])
        lesson_ids = list(lessons.values_list("pk", flat=True)[:1001])
        require(len(enr_ids) <= 1000 and len(lesson_ids) <= 1000, "canonical_ref_budget_exceeded")
        marks = model("registrar.LessonMark").objects.filter(
            organization_id=ORG, enrollment_id__in=enr_ids, lesson_id__in=lesson_ids
        )
        if lock:
            marks = marks.select_for_update()
        cells = list(
            marks.order_by("pk").values("id", "lesson_id", "enrollment_id", "status", "score", "entered_by_id")[:1001]
        )
        require(len(cells) <= 1000, "canonical_mark_budget_exceeded")
        for mark in cells:
            require(
                (str(mark["lesson_id"]), str(mark["enrollment_id"])) == (lid, eid), "canonical_copy_already_elsewhere"
            )
            rows.append({"source_point_id": point, **{k: str(v) if v is not None else None for k, v in mark.items()}})
    return rows


def fresh_guard(state, *, actor, organization, lock=False):
    """Available best-effort audit is evidence, never a claim to prove a negative."""
    if not selected(state.data):
        return None
    require(connection.in_atomic_block, "atomic_required")
    try:
        history = fixed_four_recovery_history(actor=actor, organization=organization)
    except ValueError as exc:
        raise ContentError("reviewed_four_available_history_unavailable") from exc
    _ledger_guard(history["four_cell_history_ledger"])
    require(not history["four_cell_history_evidence"], "formal_correction_hygiene_or_gradefact_requires_review")
    require(
        not any(
            r["contrary_clear_evidence"]
            or r["contrary_delete_evidence"]
            or r["malformed_intent"]
            or r["source_undo_marker"]
            for r in history["four_cell_history_audits"]
        ),
        "contrary_clear_delete_or_malformed_intent",
    )
    require(not state.closed, "closed_history_target")
    uids = {c[4] for c in fixed.CASES.values()}
    profiles = model("accounts.UserProfile").objects.filter(
        organization_id=ORG, user_id__in=uids, access_state="active", user__is_active=True
    )
    require(set(profiles.values_list("user_id", flat=True)) == uids, "active_tenant_student_required")
    for oid in fixed.TARGETS:
        offering = state.selected_offerings[oid]
        require(not offering.period.locked_at, "period_locked")
        for c in fixed.CASES.values():
            if c[0] != oid:
                continue
            _, lid, eid, sid, uid, day, start = c
            enrs = [e for e in state.enrollments if str(e.pk) == eid]
            require(
                len(enrs) == 1
                and enrs[0].student_id == uid
                and str(enrs[0].offering_id) == oid
                and enrs[0].status == "enrolled"
                and enrs[0].superseded_by_id is None,
                "exact_active_enrollment_changed",
            )
            lessons = [lesson for values in state.lessons.values() for lesson in values if str(lesson.pk) == lid]
            require(
                len(lessons) == 1
                and str(lessons[0].offering_id) == oid
                and lessons[0].date.isoformat() == day
                and lessons[0].start_time.isoformat() == start
                and lessons[0].kind == "seminar"
                and lessons[0].hours == 2,
                "exact_existing_lesson_changed",
            )
    return {"available_history": history, "canonical_cells": _canonical_cells(lock=lock)}


def decision_guard(data, decision):
    if not selected(data):
        return
    require(not decision.lessons, "lesson_creation_forbidden")
    require(not decision.counts["existing_conflicting_cells_kept"], "current_nonempty_value_requires_review")
    require(len(decision.marks) + decision.counts["existing_identical_cells"] == 4, "exact_four_cases_must_be_resolved")
    allowed = {(c[1], c[2]): point for point, c in fixed.CASES.items()}
    seen = set()
    for mark in decision.marks:
        key = str(mark.lesson_id), str(mark.enrollment_id)
        require(
            key in allowed
            and key not in seen
            and mark.status == "absent"
            and mark.score is None
            and mark.entered_by_id is None,
            "only_exact_four_blank_absences_allowed",
        )
        seen.add(key)
    require(
        {p["source_point_id"] for p in decision.provenance} == {allowed[k] for k in seen},
        "source_point_binding_changed",
    )


def receipt(before, decision):
    if before is None:
        return {}
    return {
        "fixed_four_recovery": {
            "source_review_sha256": fixed.SOURCE_REVIEW_SHA,
            "source_row_hashes": {str(k): v for k, v in fixed.ROW_HASHES.items()},
            "available_history_sha256": digest(before["available_history"]),
            "all_canonical_cells_sha256": digest(before["canonical_cells"]),
            "best_effort_audit_limitation_acknowledged": True,
            "core_course_enrollment_ledger_claimed": False,
            "before_absence_hours": {pk: str(e.absence_hours) for pk, e in decision.touched.items()},
        }
    }
