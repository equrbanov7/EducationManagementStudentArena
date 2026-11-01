"""One real dated PRESENT lesson; no relaxation of generic QB-only protection."""

import uuid

from django.db import connection

from apps.workload.public import fixed_source28_recovery_history

from . import reviewed_content_28_spec as fixed
from .reviewed_content_contract import ContentError
from .reviewed_content_spec import ORG
from .reviewed_content_state import digest, model


def require(ok, code):
    if not ok:
        raise ContentError("reviewed_source28_" + code)


def selected(data):
    return fixed.TARGET in data["selected_target_ids"]


def mark_ids():
    return {
        point: str(uuid.uuid5(uuid.UUID(ORG), f'reviewed-source-mark:{fixed.LESSON}:{c["enrollment_id"]}'))
        for point, c in fixed.CASES.items()
    }


def source_guard(data, sha):
    if not selected(data):
        return
    raw = {k: v for k, v in data.items() if k not in {"selected_target_ids", "until_date"}}
    require(
        data["selected_target_ids"] == [fixed.TARGET]
        and sha == fixed.SOURCE_SHA
        and digest(raw) == fixed.PAYLOAD_DIGEST,
        "exact_private_source_and_single_target_required",
    )
    require({p["id"] for p in data["points"]} == set(fixed.CASES), "only_28_present_source_points")
    require({r["id"] for r in data["dates"]} == set(fixed.CALENDAR_IDS), "exact_calendar_rows_required")
    require(
        all(p["point"] == "ie" and str(p["sem_muh"]) == "0" and not int(p["lab"]) for p in data["points"]),
        "only_normal_seminar_present",
    )


def _ledger(rows):
    expected = {
        ("worker", str(fixed.SPEC["legacy_teacher_id"])): ("auth.user", str(fixed.SPEC["teacher_id"])),
        ("lesson_subject", str(fixed.SPEC["legacy_subject_id"])): ("registrar.subject", fixed.SPEC["subject_id"]),
        ("group_unit", str(fixed.SPEC["legacy_group_id"])): ("organizations.orgunit", fixed.SPEC["group_id"]),
    }
    expected.update(
        {("student", str(c["source_student_id"])): ("auth.user", str(c["student_id"])) for c in fixed.CASES.values()}
    )
    found = {}
    for row in rows:
        key = row["entity_type"], row["legacy_pk"]
        actual = row["target_model_label"], row["target_pk"]
        require(row["state"] == "migrated", "source_ledger_state_changed")
        if key in expected:
            require(key not in found and actual == expected[key], "typed_source_ledger_conflict")
            found[key] = actual
        elif key == ("course_offering", f'{fixed.SPEC["journal_uniqid"]}:{fixed.SPEC["legacy_group_id"]}'):
            require(actual == ("registrar.courseoffering", fixed.TARGET), "course_ledger_conflict")
        elif key[0] == "journal_enrollment":
            wanted = {
                f'{fixed.SPEC["journal_uniqid"]}:{c["source_student_id"]}': c["enrollment_id"]
                for c in fixed.CASES.values()
            }
            require(actual == ("registrar.enrollment", wanted.get(key[1])), "enrollment_ledger_conflict")
        else:
            require(False, "additional_source_claim_requires_review")
    require(set(found) == set(expected), "all_typed_identity_ledgers_required")


def _canonical(*, lock, allow_created):
    family = model("registrar.CourseOffering").objects.filter(
        organization_id=ORG, subject_id=fixed.SPEC["subject_id"], period_id=fixed.SPEC["period_id"]
    )
    if lock:
        family = family.select_for_update()
    ids = list(family.values_list("pk", flat=True)[:1001])
    require(len(ids) <= 1000, "canonical_course_budget")
    students = {c["student_id"] for c in fixed.CASES.values()}
    lessons = model("registrar.Lesson").objects.filter(
        organization_id=ORG, offering_id=fixed.TARGET, date=fixed.DATE, start_time=fixed.START
    )
    marks = model("registrar.LessonMark").objects.filter(
        organization_id=ORG,
        enrollment__organization_id=ORG,
        enrollment__offering_id__in=ids,
        enrollment__student_id__in=students,
        lesson__organization_id=ORG,
        lesson__offering_id__in=ids,
        lesson__date=fixed.DATE,
    )
    if lock:
        lessons, marks = lessons.select_for_update(), marks.select_for_update()
    ls = list(lessons.order_by("pk")[:2])
    ms = list(marks.order_by("pk")[:29])
    require(len(ls) <= 1 and len(ms) <= 28, "existing_canonical_slot_requires_review")
    if ls or ms:
        require(allow_created, "existing_content_without_original_recovery_receipt")
    for lesson in ls:
        require(
            str(lesson.pk) == fixed.LESSON
            and lesson.kind == "seminar"
            and lesson.hours == 2
            and lesson.topic == fixed.TOPIC
            and lesson.end_time is None
            and lesson.created_by_id is None
            and lesson.instructor_id is None
            and not lesson.is_legacy_synthesised,
            "existing_lesson_changed",
        )
    expected = {c["enrollment_id"]: mark_ids()[point] for point, c in fixed.CASES.items()}
    for mark in ms:
        require(
            str(mark.lesson_id) == fixed.LESSON
            and str(mark.pk) == expected.get(str(mark.enrollment_id))
            and mark.status == "present"
            and mark.score is None
            and mark.entered_by_id is None,
            "canonical_copy_or_current_value_requires_review",
        )
    return [{"id": str(m.pk), "enrollment": str(m.enrollment_id)} for m in ms]


def _receipt_ids():
    receipts = model("audit.AuditLog").objects.filter(
        organization_id=ORG,
        resource_type="legacy_import.reviewed_content",
        action="create",
        new_values__source_sha256=fixed.SOURCE_SHA,
        new_values__target_ids=[fixed.TARGET],
        new_values__created_lesson_ids=[fixed.LESSON],
    )
    rows = list(receipts.values("id", "new_values")[:2])
    require(len(rows) <= 1, "ambiguous_original_recovery_receipt")
    for row in rows:
        value = row["new_values"]
        require(
            set(value.get("created_mark_ids", [])) == set(mark_ids().values())
            and {p.get("source_point_id") for p in value.get("source_provenance", [])} == set(fixed.CASES),
            "original_recovery_receipt_bindings_changed",
        )
    return {str(row["id"]) for row in rows}


def fresh_guard(state, *, actor, organization, lock=False, allow_created=False):
    if not selected(state.data):
        return None
    require(connection.in_atomic_block, "atomic_required")
    try:
        history = fixed_source28_recovery_history(actor=actor, organization=organization, lock=lock)
    except ValueError as exc:
        raise ContentError("reviewed_source28_fresh_history_or_allocation_unavailable") from exc
    receipt_ids = _receipt_ids()
    _ledger(history["source28_history_ledger"])
    require(not history["source28_history_evidence"], "correction_hygiene_or_sourceclaim_requires_review")
    require(
        not any(
            r["contrary_clear_evidence"]
            or r["contrary_delete_evidence"]
            or r["malformed_intent"]
            or r["source_undo_marker"]
            for r in history["source28_history_audits"]
            if r["action"] != "view"
        ),
        "contrary_history_requires_review",
    )
    require(
        all(
            not r["tenant_unlocatable_mark_delete_audits"] and not r["tenant_deleted_lesson_corrections_unlocatable"]
            for r in history["source28_history_scope"]
        ),
        "unlocatable_deletion_requires_review",
    )
    require(
        not any(
            r["unresolved_scope_row"] and r["action"] != "view" and r["id"] not in receipt_ids
            for r in history["source28_history_audits"]
        ),
        "unresolved_course_audit_requires_review",
    )
    require(
        all(not r["tenant_unlocatable_lesson_delete_audits"] for r in history["source28_history_scope"]),
        "unlocatable_lesson_deletion_requires_review",
    )
    require(not state.closed and not state.selected_offerings[fixed.TARGET].period.locked_at, "closed_or_locked_target")
    uids = {c["student_id"] for c in fixed.CASES.values()} | {fixed.SPEC["teacher_id"]}
    profiles = model("accounts.UserProfile").objects.filter(
        organization_id=ORG,
        user_id__in=uids,
        access_state="active",
        user__is_active=True,
        is_deleted=False,
        deleted_at__isnull=True,
        blocked_at__isnull=True,
    )
    require(set(profiles.values_list("user_id", flat=True)) == uids, "active_tenant_profiles_required")
    enrs = {str(e.pk): e for e in state.enrollments}
    for c in fixed.CASES.values():
        e = enrs.get(c["enrollment_id"])
        require(
            e is not None
            and e.student_id == c["student_id"]
            and str(e.offering_id) == fixed.TARGET
            and e.status == "enrolled"
            and e.superseded_by_id is None,
            "exact_active_enrollment_changed",
        )
        require(state.active_groups[c["student_id"]] == {fixed.SPEC["group_id"]}, "current_home_group_requires_review")
    canonical = _canonical(lock=lock, allow_created=allow_created or bool(receipt_ids))
    return {
        "available_history": history,
        "canonical_cells": canonical,
        "absence_hours": {c["enrollment_id"]: enrs[c["enrollment_id"]].absence_hours for c in fixed.CASES.values()},
    }


def decision_guard(data, decision):
    if not selected(data):
        return
    require(not decision.counts["existing_conflicting_cells_kept"], "current_value_conflict")
    require(len(decision.marks) + decision.counts["existing_identical_cells"] == 28, "all_28_cells_must_resolve")
    require(len(decision.lessons) in (0, 1), "single_lesson_only")
    expected = mark_ids()
    for mark in decision.marks:
        point = next((p for p, c in fixed.CASES.items() if c["enrollment_id"] == str(mark.enrollment_id)), None)
        require(
            point
            and str(mark.pk) == expected[point]
            and str(mark.lesson_id) == fixed.LESSON
            and mark.status == "present"
            and mark.score is None,
            "exact_present_mark_required",
        )
    for lesson in decision.lessons.values():
        require(
            str(lesson.pk) == fixed.LESSON
            and lesson.date.isoformat() == fixed.DATE
            and lesson.start_time.isoformat() == fixed.START
            and lesson.kind == "seminar"
            and lesson.hours == 2
            and not lesson.is_legacy_synthesised,
            "actual_calendar_seminar_required",
        )
        lesson.topic = fixed.TOPIC
    decision.counts["source28_remaining_qb_cells_deferred"] = 58


def receipt(before, decision):
    if before is None:
        return {}
    return {
        "fixed_source28_recovery": {
            "source_review_sha256": fixed.SOURCE_REVIEW_SHA,
            "available_history_sha256": digest(before["available_history"]),
            "before_absence_hours": before["absence_hours"],
            "source_metadata_id": fixed.METADATA_ID,
            "hours_semantics": "documented_pair1_to_academic2_after2024_02_01",
            "end_and_authors": "unknown_DEFAULT_NULL",
            "core_course_enrollment_ledger_claimed": False,
            "remaining_qb_cells_deferred": 58,
        }
    }


def after_guard(before, after):
    require(before["available_history"] == after["available_history"], "history_changed_during_write")
    require(before["absence_hours"] == after["absence_hours"], "present_only_must_not_change_existing_qb_counter")
