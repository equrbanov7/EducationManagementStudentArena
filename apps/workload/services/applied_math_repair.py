"""Fixed AppliedMath domain operation; source/receipt orchestration belongs to legacy import."""

from uuid import uuid4

from django.db import connection, transaction
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save

from apps.registrar.public import subject_merge_apply

from ..constants import AmendmentReason, TaskStatus
from . import applied_math_schedule as schedule
from . import applied_math_state as state
from .qosqar_duplicate_repair import _restore_records
from .row_edit import delete_row_amended
from .scoping import resolve_actor

Error = state.DuplicateError
CELL_SHA = "5303b46370b002e496a6a4f027969526b83c531aca20c1dc3efb38ce3893add6"


def capture():
    return state.capture()


def baseline():
    return state.digest(capture())


def lock(*, organization, user):
    if (
        str(organization.pk) != state.ORG
        or not organization.is_active
        or organization.status != "active"
        or not user.is_active
        or not user.is_superuser
    ):
        raise Error("fixed_active_tenant_superadmin_required")
    schedule.schedule_lock.lock_schedule(organization.pk, state.PERIOD)
    task = (
        state.model("workload.TeachingTask").objects.select_for_update().get(pk=state.TASK, organization=organization)
    )
    if task.status not in (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED):
        raise Error("released_task_required")
    list(
        state.model("registrar.CourseOffering")
        .objects.select_for_update()
        .filter(pk__in=(state.EMPTY, state.FILLED), organization=organization)
    )
    list(
        state.model("workload.TeachingTaskRow")
        .objects.select_for_update()
        .filter(pk__in=(state.KEEP_ROW, state.REMOVE_ROW), organization=organization)
    )
    return task


def _write_subject(offering_id, old, new):
    subject_merge_apply.allow_offering_subject_change([old], new)
    try:
        if (
            state.model("registrar.CourseOffering")
            .objects.filter(pk=offering_id, organization_id=state.ORG, subject_id=old)
            .update(subject_id=new)
            != 1
        ):
            raise Error("offering_subject_write_conflict")
    finally:
        if not connection.needs_rollback:
            subject_merge_apply.clear_offering_subject_change()


def _swap(*, undo=False):
    """No group/period mutation, trigger bypass, persistent placeholder, or existing ID deletion."""
    Subject = state.model("registrar.Subject")
    if any(signal.has_listeners(Subject) for signal in (pre_save, post_save, pre_delete, post_delete)):
        raise Error("transient_subject_signal_side_effect_requires_review")
    temporary = Subject(
        organization_id=state.ORG,
        code="repair-" + uuid4().hex[:24],
        name="Temporary atomic identity swap",
        is_active=False,
    )
    Subject.objects.bulk_create([temporary])
    a, b = (state.OLD, state.NEW) if undo else (state.NEW, state.OLD)
    _write_subject(state.EMPTY, a, temporary.pk)
    _write_subject(state.FILLED, b, a)
    _write_subject(state.EMPTY, temporary.pk, b)
    for rel in Subject._meta.get_fields(include_hidden=True):
        if rel.auto_created and not rel.concrete and rel.related_model:
            lookup = rel.field.name if rel.many_to_many else rel.field.attname
            if rel.related_model._base_manager.filter(**{lookup: temporary.pk}).exists():
                raise Error("transient_subject_has_reference")
    Subject.objects.filter(pk=temporary.pk).delete()
    state.model("registrar.CourseOffering").objects.filter(pk=state.EMPTY, organization_id=state.ORG).update(
        is_active=undo
    )


def prepare(*, organization, user, cell_sha):
    lock(organization=organization, user=user)
    state.validate()
    if cell_sha != CELL_SHA or state.digest(state.cells()) != CELL_SHA:
        raise Error("source_exact_81_cells_changed")
    schedule.validate_empty(state.EMPTY, state.FILLED)
    if (
        state.model("syllabus.Syllabus").objects.filter(offering_id__in=(state.EMPTY, state.FILLED)).exists()
        or state.model("syllabus.SyllabusShare").objects.filter(offering_id__in=(state.EMPTY, state.FILLED)).exists()
    ):
        raise Error("existing_syllabus_no_overwrite")
    return capture(), schedule.plan(state.EMPTY, state.FILLED)


@transaction.atomic
def apply(*, organization, user, expected_baseline, cell_sha):
    before, _ = prepare(organization=organization, user=user, cell_sha=cell_sha)
    if not expected_baseline or state.digest(before) != expected_baseline:
        raise Error("fresh_live_baseline_changed")
    task = state.model("workload.TeachingTask").objects.get(pk=state.TASK, organization=organization)
    row = state.model("workload.TeachingTaskRow").objects.get(pk=state.REMOVE_ROW, organization=organization)
    delete_row_amended(
        task=task,
        row=row,
        actor=resolve_actor(user, organization),
        amend={
            "reason": AmendmentReason.CORRECTION,
            "note": "Mənbə14316 öz6690 sillabusu ilə tətbiqi riyaziyyatdır; qiymətli jurnalın ID-ləri saxlanaraq yanlış əlavə yük çıxarılır.",
        },
    )
    _swap()
    # Canonical slot creation occurs only after the retained target has its correct subject.
    pairs = schedule.apply(source_id=state.EMPTY, target_id=state.FILLED, organization=organization, user=user)
    state.validate(corrected=True)
    after = capture()
    schedule.preserved(
        before=before["academic"].get("registrar.ScheduleSlot", []),
        after=after["academic"].get("registrar.ScheduleSlot", []),
        pairs=pairs,
    )
    if state.digest(state.protected(before)) != state.digest(state.protected(after)):
        raise Error("protected_journal_or_canonical_workload_changed")
    return {"before": before, "schedule_pairs": pairs, "domain_after_hash": state.digest(after)}


@transaction.atomic
def undo(*, organization, user, original, pairs, expected_baseline):
    lock(organization=organization, user=user)
    before = capture()
    if not expected_baseline or state.digest(before) != expected_baseline:
        raise Error("undo_live_state_changed")
    state.validate(corrected=True)
    if state.digest(state.cells()) != CELL_SHA:
        raise Error("undo_source_cells_changed")
    schedule.check_undo(
        source_id=state.EMPTY,
        target_id=state.FILLED,
        before=original["academic"].get("registrar.ScheduleSlot", []),
        pairs=pairs,
    )
    _swap(undo=True)
    for label, key in (("workload.TeachingTaskRow", "rows"), ("workload.TeacherAssignment", "assignments")):
        rows = [
            r for r in original[key] if str(r["id"]) == state.REMOVE_ROW or str(r.get("row_id")) == state.REMOVE_ROW
        ]
        _restore_records(label, rows)
    through = state.model("workload.TeachingTaskRow").groups.through
    _restore_records(
        through._meta.label, [r for r in original["group_links"] if str(r["teachingtaskrow_id"]) == state.REMOVE_ROW]
    )
    schedule.undo(
        source_id=state.EMPTY,
        target_id=state.FILLED,
        before=original["academic"].get("registrar.ScheduleSlot", []),
        pairs=pairs,
        organization=organization,
        user=user,
    )
    after = capture()
    if state.digest(state.protected(original)) != state.digest(state.protected(after)):
        raise Error("undo_protected_content_changed")
    for key in ("rows", "assignments", "groups", "group_links", "subjects"):
        if state.digest(after[key]) != state.digest(original[key]):
            raise Error("undo_original_metadata_not_exact")
    # Immutable amendment/audit records and archived repair artifacts remain.
    return {"rows_restored": 1, "assignments_restored": 2}


def fixed_identity():
    """Public immutable scope values, resolved at call time for isolated PG fixtures."""
    return {name: getattr(state, name) for name in ("EMPTY", "FILLED", "NEW", "TEACHER")}


def protected(value):
    return state.protected(value)
