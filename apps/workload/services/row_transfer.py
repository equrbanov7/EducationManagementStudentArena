"""Yük sətrini UUID/bölgü/jurnal tarixçəsini saxlayaraq başqa kafedraya köçür."""

from django.apps import apps as django_apps
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentTarget, SliceStatus, TaskStatus
from ..models import TeachingTask, TeachingTaskRow
from .amendments import open_amendment
from .chair_merge import row_key
from .intensive import ensure_not_intensive
from .people import ensure_assignable_teacher, resolve_chair
from .repair_fingerprints import academic_fingerprint
from .row_edit import _require_amend, distribution_edit_url
from .sbio235_state import records
from .scoping import WorkloadDenied, ensure_can_distribute, ensure_can_manage, manageable_chairs

_STAGES = (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED)


def _denied(code, message):
    raise WorkloadDenied("workload.transfer_" + code, message)


def _permissions(actor, chair_id):
    ensure_can_manage(actor, chair_id)
    ensure_can_distribute(actor, chair_id)


def _stage(task, row):
    if task.status not in _STAGES:
        _denied("stage", "Köçürmə üçün hər iki kafedranın bölgüsü əvvəlcə təsdiqlənməlidir.")
    slices = task.slices.filter(revision=task.revision)
    if slices.exists() and (
        not row.faculty_id
        or not slices.filter(faculty_id=row.faculty_id, status=SliceStatus.APPROVED).exists()
        or slices.exclude(status=SliceStatus.APPROVED).exists()
    ):
        _denied("approval", "Hədəf fakültənin təsdiqi tamamlanmayıb. Mövcud təsdiqlər dəyişdirilmədi.")


def source_row(*, actor, row_id, task_id, lock=False):
    rows = TeachingTaskRow.objects.filter(organization=actor.organization, pk=row_id, task_id=task_id)
    if lock:
        rows = rows.select_for_update(of=("self",))
    row = rows.select_related("task__chair", "period").first()
    if row is None:
        _denied("source_changed", "Sətir tapılmadı və ya artıq başqa kafedraya köçürülüb. Siyahını yeniləyin.")
    _permissions(actor, row.task.chair_id)
    resolve_chair(actor.organization, row.task.chair_id)
    ensure_not_intensive(row)
    return row


def destinations(*, actor, row):
    """Yalnız hər iki yazı icazəsi olan, eyni ilin mövcud kafedra tapşırıqları."""
    _permissions(actor, row.task.chair_id)
    chairs = (
        manageable_chairs(actor)
        .filter(pk__in=manageable_chairs(actor, permission="workload.distribute").values("pk"))
        .exclude(pk=row.task.chair_id)
    )
    tasks = (
        TeachingTask.objects.filter(
            organization=actor.organization, chair__in=chairs, academic_year=row.task.academic_year, status__in=_STAGES
        )
        .select_related("chair")
        .order_by("chair__name")
    )
    result = []
    for task in tasks:
        try:
            _stage(task, row)
        except WorkloadDenied:
            continue
        result.append({"id": str(task.chair_id), "name": task.chair.name, "task_id": str(task.pk)})
    return result


def _protected_row(row, *, lock=False):
    values = records(TeachingTaskRow.objects.filter(organization=row.organization, pk=row.pk), lock=lock)[0]
    return {
        "row": {k: v for k, v in values.items() if k not in {"task_id", "updated_at"}},
        "groups": sorted(str(pk) for pk in row.groups.values_list("pk", flat=True)),
        "assignments": records(row.assignments.all(), lock=lock),
        "reviews": records(row.reviews.all(), lock=lock),
        "objections": records(row.objections.all(), lock=lock),
    }


def _journals(row):
    return (
        list(
            django_apps.get_model("registrar.CourseOffering")
            .objects.filter(
                organization=row.organization,
                subject_id=row.subject_id,
                period_id=row.period_id,
                group_id__in=row.groups.values("pk"),
            )
            .select_for_update()
        )
        if row.subject_id and row.period_id
        else []
    )


def _ensure_no_duplicate(row, target):
    wanted = row_key(row, row.groups.values_list("pk", flat=True))
    for other in target.rows.all().prefetch_related("groups"):
        if row_key(other, (g.pk for g in other.groups.all())) == wanted:
            _denied("duplicate", "Hədəf kafedrada eyni fənn, semestr və qruplu sətir var. Təkrar yük yaradılmadı.")


def _memberships(organization, teacher_ids):
    return django_apps.get_model("organizations.Membership").objects.filter(
        organization=organization,
        user_id__in=teacher_ids,
    )


@transaction.atomic
def transfer_row(*, actor, row_id, source_task_id, destination_chair_id, amend, request=None):
    """Mövcud iki təsdiqlənmiş tapşırıq arasında yalnız ``row.task`` dəyişir.

    Jurnal sinxronu çağırılmır: fiziki fənn/semestr/qruplar və müəllimlər dəyişmir.
    Əsas üzvlüklər toxunulmaz, lazım olan əlavə üzvlük canonical təyinat qapısından keçir.
    """
    reason, note = _require_amend(amend)
    target_chair = resolve_chair(actor.organization, destination_chair_id)
    _permissions(actor, target_chair.pk)
    # Always lock task headers in UUID order, then row: competing A→B / B→A transfers cannot deadlock.
    task_ids = (
        TeachingTask.objects.filter(
            organization=actor.organization,
        )
        .filter(pk=source_task_id)
        .values_list("academic_year", flat=True)
    )
    year = task_ids.first()
    tasks = list(
        TeachingTask.objects.filter(
            organization=actor.organization,
            academic_year=year,
        )
        .filter(chair_id=target_chair.pk)
        .values_list("pk", flat=True)
    )
    tasks.append(source_task_id)
    locked = {
        str(t.pk): t
        for t in TeachingTask.objects.filter(
            organization=actor.organization,
            pk__in=tasks,
        )
        .order_by("pk")
        .select_for_update()
    }
    row = source_row(actor=actor, row_id=row_id, task_id=source_task_id, lock=True)
    source = locked[str(row.task_id)]
    target = next((t for t in locked.values() if t.chair_id == target_chair.pk and t.pk != source.pk), None)
    if target is None:
        _denied("destination", "Bu kafedrada eyni tədris ili üçün uyğun tapşırıq tapılmadı.")
    if source.academic_year != target.academic_year:
        _denied("year", "Mənbə və hədəf tapşırığın tədris ili eyni olmalıdır.")
    for task in (source, target):
        _permissions(actor, task.chair_id)
        _stage(task, row)
    if row.period_id and row.period.academic_year != source.academic_year:
        _denied("period", "Sətrin semestri tapşırığın tədris ilinə uyğun deyil.")
    _ensure_no_duplicate(row, target)
    row.task = source
    before = _protected_row(row, lock=True)
    journals = _journals(row)
    academic = academic_fingerprint(organization_id=actor.organization.pk, offerings=journals, lock=True)
    teacher_ids = {a.teacher_id for a in row.assignments.all() if a.teacher_id}
    memberships_before = records(_memberships(actor.organization, teacher_ids), lock=True)
    for teacher in django_apps.get_model("auth.User").objects.filter(pk__in=teacher_ids).order_by("pk"):
        ensure_assignable_teacher(actor.organization, target_chair, teacher, actor_user=actor.user)
    details = {
        "action": "chair_transfer",
        "source_task": str(source.pk),
        "target_task": str(target.pk),
        "source_chair": str(source.chair_id),
        "target_chair": str(target.chair_id),
        "academic_year": source.academic_year,
    }
    for task in (source, target):
        if task == target:
            row.task = target
            row.save(update_fields=["task", "updated_at"])
        open_amendment(
            task=task,
            actor=actor,
            target_kind=AmendmentTarget.ROW,
            target_id=row.pk,
            reason=reason,
            note=note,
            new_values=details,
            request=request,
        )
    row.refresh_from_db()
    if (
        _protected_row(row) != before
        or academic_fingerprint(
            organization_id=actor.organization.pk,
            offerings=journals,
        )
        != academic
    ):
        _denied("content_changed", "Köçürmə zamanı yük və ya jurnal məzmunu dəyişdi. Əməl geri qaytarıldı.")
    memberships_after = records(_memberships(actor.organization, teacher_ids))
    after_by_id = {m["id"]: m for m in memberships_after}
    teacher_roles = {
        str(pk)
        for pk in django_apps.get_model("organizations.Role")
        .objects.filter(
            organization=actor.organization,
            name="teacher",
            is_active=True,
        )
        .values_list("pk", flat=True)
    }
    for membership in memberships_before:
        current = after_by_id.get(membership["id"], {})
        allowed = (
            {"is_active", "updated_at"}
            if (
                membership["scope_unit_id"] == str(target_chair.pk)
                and not membership["is_active"]
                and not membership["is_primary"]
                and membership["role_id"] in teacher_roles
            )
            else set()
        )
        if {k: v for k, v in membership.items() if k not in allowed} != {
            k: v for k, v in current.items() if k not in allowed
        }:
            _denied("membership_changed", "Mövcud müəllim üzvlüyü dəyişdi. Əməl geri qaytarıldı.")
    old_membership_ids = {m["id"] for m in memberships_before}
    for membership in memberships_after:
        if membership["id"] not in old_membership_ids and (
            membership["scope_unit_id"] != str(target_chair.pk)
            or membership["is_primary"]
            or not membership["is_active"]
            or membership["role_id"] not in teacher_roles
        ):
            _denied("membership_changed", "Gözlənilməz yeni müəllim səlahiyyəti yarandı. Əməl geri qaytarıldı.")
    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=actor.organization,
        resource_type="workload.TeachingTaskRow",
        resource_id=str(row.pk),
        reason="workload.row_chair_transferred",
        old_values={"task": str(source.pk), "chair": str(source.chair_id)},
        new_values={
            **details,
            "memberships_before": memberships_before,
            "memberships_after": memberships_after,
            "academic_protected": academic,
        },
        request=request,
    )
    return {
        "row_id": str(row.pk),
        "task_id": str(target.pk),
        "chair_id": str(target.chair_id),
        "chair_name": target_chair.name,
        "edit_url": distribution_edit_url(chair_id=target.chair_id, academic_year=target.academic_year, row_id=row.pk),
    }
