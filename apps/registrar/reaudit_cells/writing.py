"""Reviewed insertions and proven source restorations with exact receipt-bound undo."""

import uuid

from django.apps import apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.rls import journal_unlock

from ..absence_evidence import absence_counter_preview
from ..gradebook_marks import recompute_absence_hours_many
from .history import record
from .manifest import RESOURCE, digest, require
from .snapshot import model, read

LESSON_FIELDS = (
    "offering_id",
    "date",
    "kind",
    "hours",
    "start_time",
    "end_time",
    "instructor_id",
    "lab_group",
    "seminar_group",
)


def _rows(name, organization, ids):
    return read(model(name).objects.filter(organization=organization, pk__in=ids), True)


def counter_guard(organization, ids):
    ids = sorted(set(ids))
    for offset in range(0, len(ids), 1000):
        preview = absence_counter_preview(
            organization_id=organization.pk, added_hours_by_enrollment={eid: 0 for eid in ids[offset : offset + 1000]}
        )
        require(
            all(row["cached_before"] == row["derived_before"] for row in preview),
            "counter_drift_requires_separate_review",
        )


def apply_changes(*, organization, actor, planned, plan_hash, before_hash):
    created = {"lessons": [], "marks": [], "components": []}
    provenance = {"marks": [], "components": []}
    affected_absences = {row["enrollment_id"] for row in planned["marks"] if row["status"] == "absent"}
    affected_absences.update(
        row["before"]["enrollment_id"] for row in planned["restorations"] if row["before"]["status"] == "absent"
    )
    counter_guard(organization, affected_absences)
    for row in planned["lessons"]:
        instance = model("Lesson").objects.create(
            id=row["id"],
            organization=organization,
            created_by=actor,
            is_legacy_synthesised=True,
            **{key: row[key] for key in LESSON_FIELDS},
        )
        created["lessons"].append(str(instance.pk))
    absent_enrollments = set()
    restored_before = []
    for row in planned["restorations"]:
        old = row["before"]
        with journal_unlock():
            changed = (
                model("LessonMark")
                .objects.filter(
                    organization=organization, pk=old["id"], score__isnull=True, entered_by_id=old["entered_by_id"]
                )
                .update(status=row["status"], score=row["score"], updated_at=timezone.now())
            )
        require(changed == 1, "restoration_mark_changed")
        restored_before.append(old)
        if old["status"] == "absent":
            absent_enrollments.add(old["enrollment_id"])
        provenance["marks"].append(
            {
                "id": old["id"],
                "policy": "source_value_restore_imported_attendance",
                "source_ids": row["source_ids"],
                "import_proof": row["import_proof"],
            }
        )
    pending_marks = []
    for row in planned["marks"]:
        mark = model("LessonMark")(
            organization=organization,
            lesson_id=row["lesson_id"],
            enrollment_id=row["enrollment_id"],
            status=row["status"],
            score=row["score"],
            entered_by=actor if row["policy"] == "owner_assigned_present" else None,
        )
        pending_marks.append(mark)
        created["marks"].append(str(mark.pk))
        provenance["marks"].append({"id": str(mark.pk), "policy": row["policy"], "source_ids": row["source_ids"]})
        if row["status"] == "absent":
            absent_enrollments.add(row["enrollment_id"])
    model("LessonMark").objects.bulk_create(pending_marks, batch_size=500)
    pending_components = []
    for row in planned["components"]:
        score = model("ComponentScore")(
            organization=organization,
            component_id=row["component_id"],
            enrollment_id=row["enrollment_id"],
            score=row["score"],
            entered_by=None,
            exam_source=None,
        )
        pending_components.append(score)
        created["components"].append(str(score.pk))
        provenance["components"].append(
            {"id": str(score.pk), "policy": "source_component_preserve", "source_ids": row["source_ids"]}
        )
    model("ComponentScore").objects.bulk_create(pending_components, batch_size=500)
    if absent_enrollments:
        recompute_absence_hours_many(
            list(model("Enrollment").objects.filter(organization=organization, pk__in=absent_enrollments))
        )
    after_rows = {
        key: _rows(name, organization, created[key])
        for key, name in (("lessons", "Lesson"), ("marks", "LessonMark"), ("components", "ComponentScore"))
    }
    require(all(len(after_rows[key]) == len(created[key]) for key in created), "write_count_mismatch")
    restored_after = _rows("LessonMark", organization, [row["id"] for row in restored_before])
    record(
        organization=organization,
        actor=actor,
        created=after_rows,
        restored_before=restored_before,
        restored_after=restored_after,
    )
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=receipt,
        reason="Owner 2026-11-09: source grades through 21 October; confirmed attendance; owner present in applicable blanks or proven unchanged imported absence conflicts.",
        old_values={"baseline": before_hash},
        new_values={
            "operation": "apply",
            "plan_sha256": plan_hash,
            "created_rows_sha256": digest(after_rows),
            "restored_rows_sha256": digest(restored_after),
            "counts": planned["counts"],
        },
        changes={
            "created": after_rows,
            "restored_before": restored_before,
            "restored_after": restored_after,
            "provenance": provenance,
        },
    )
    return receipt


def inspect_undo(*, organization, plan_hash, receipt):
    logs = apps.get_model("audit", "AuditLog").objects.filter(organization=organization, resource_type=RESOURCE)
    original = logs.filter(resource_id=receipt, new_values__operation="apply").first()
    require(
        original is not None and original.new_values.get("plan_sha256") == plan_hash, "exact_apply_receipt_required"
    )
    expected = (original.changes or {}).get("created")
    require(
        isinstance(expected, dict) and digest(expected) == original.new_values.get("created_rows_sha256"),
        "receipt_content_invalid",
    )
    undone = logs.filter(new_values__operation="undo", new_values__undo_of=receipt).exists()
    restored_before = original.changes.get("restored_before", [])
    restored_after = original.changes.get("restored_after", [])
    require(digest(restored_after) == original.new_values.get("restored_rows_sha256"), "restoration_receipt_invalid")
    restored_current = read(
        model("LessonMark").objects.filter(organization=organization, pk__in=[row["id"] for row in restored_after]),
        False,
    )
    # Read mode must stay SELECT-only; the caller already locks scope during apply.
    current = {}
    for key, name in (("lessons", "Lesson"), ("marks", "LessonMark"), ("components", "ComponentScore")):
        ids = [row["id"] for row in expected[key]]
        require(len(ids) == len(set(ids)), "receipt_duplicate_object")
        current[key] = read(model(name).objects.filter(organization=organization, pk__in=ids), False)
    if undone:
        require(not any(current.values()), "undone_receipt_objects_reappeared")
        require(restored_current == sorted(restored_before, key=lambda row: row["id"]), "undone_restored_mark_changed")
        return original, expected, True
    require(current == expected, "receipt_objects_changed_preserve_human_edits")
    require(restored_current == restored_after, "restored_grade_changed_preserve_human_edits")
    lesson_ids = [row["id"] for row in expected["lessons"]]
    mark_ids = {row["id"] for row in expected["marks"]}
    require(
        set(
            map(
                str,
                model("LessonMark")
                .objects.filter(organization=organization, lesson_id__in=lesson_ids)
                .values_list("id", flat=True),
            )
        )
        <= mark_ids,
        "created_lesson_has_later_marks",
    )
    protected = {(row["lesson_id"], row["enrollment_id"]) for row in expected["marks"] + restored_after}
    correction_pairs = (
        model("JournalCorrection")
        .objects.filter(organization=organization, enrollment_ref__in={enrollment for _lesson, enrollment in protected})
        .values_list("lesson_ref", "enrollment_ref")
    )
    require(
        not any((str(lesson), str(enrollment)) in protected for lesson, enrollment in correction_pairs),
        "receipt_mark_has_correction_history",
    )
    require(
        not model("LessonCorrection").objects.filter(organization=organization, lesson_id__in=lesson_ids).exists(),
        "receipt_lesson_has_correction_history",
    )
    for row in expected["components"]:
        require(
            not model("ComponentScoreCorrection")
            .objects.filter(
                organization=organization, component_id=row["component_id"], enrollment_id=row["enrollment_id"]
            )
            .exists(),
            "receipt_component_has_correction_history",
        )
    return original, expected, False


def undo_changes(*, organization, actor, original, expected, plan_hash, baseline):
    absent_ids = {row["enrollment_id"] for row in expected["marks"] if row["status"] == "absent"}
    restored_before = original.changes.get("restored_before", [])
    absent_ids.update(row["enrollment_id"] for row in restored_before if row["status"] == "absent")
    counter_guard(organization, absent_ids)
    record(
        organization=organization,
        actor=actor,
        created=expected,
        restored_before=restored_before,
        restored_after=original.changes.get("restored_after", []),
        undo=True,
    )
    with journal_unlock():
        for row in restored_before:
            changed = (
                model("LessonMark")
                .objects.filter(organization=organization, pk=row["id"])
                .update(**{key: row[key] for key in ("status", "score", "entered_by_id", "updated_at")})
            )
            require(changed == 1, "undo_restoration_mark_missing")
        for key, name in (("components", "ComponentScore"), ("marks", "LessonMark"), ("lessons", "Lesson")):
            rows = expected[key]
            count = model(name).objects.filter(organization=organization, pk__in=[row["id"] for row in rows]).count()
            require(count == len(rows), "undo_count_changed")
            model(name).objects.filter(organization=organization, pk__in=[row["id"] for row in rows]).delete()
    if absent_ids:
        recompute_absence_hours_many(
            list(model("Enrollment").objects.filter(organization=organization, pk__in=absent_ids))
        )
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=receipt,
        reason="Exact receipt-bound undo of unchanged November 9 remediation objects.",
        old_values={"baseline": baseline},
        new_values={"operation": "undo", "undo_of": original.resource_id, "plan_sha256": plan_hash},
        changes={
            "deleted_ids": {key: [row["id"] for row in values] for key, values in expected.items()},
            "restored_mark_ids": [row["id"] for row in restored_before],
        },
    )
    return receipt
