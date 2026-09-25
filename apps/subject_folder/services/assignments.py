"""Qovluğun qruplara təyinatı və tapşırıq son tarixləri.

Müəllim qovluğu YALNIZ özünün tədris etdiyi açılışlara təyin edə bilər
(``lookups.teaches_offering`` — canlı müəllim / dərs müəllimi / inzibatçı).
Təyin anında açılışın təsdiqlənmiş sillabus versiyası və sərbəst iş strukturu
SNAPSHOT kimi yazılır. Açılışın sərbəst işini yalnız BİR təyinat qiymətləndirir
(``grades_selfwork``): başqa qovluq artıq qiymətləndirirsə və ya açılışın
sillabus strukturu qovluğunkundan fərqlidirsə, təyinat yenə aktivdir (material
və ev tapşırığı axır), amma sərbəst iş bu qrupda qovluqdan qəbul edilmir —
nəticədə ``warnings`` qaytarılır.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from ..constants import FolderStatus, LatePolicy
from ..errors import FolderError
from ..models import FolderAssignment, TaskDeadline
from . import access, lookups, notify, syllabus_bridge
from .events import audit_change
from .locks import advisory_lock

#: Pəncərə vəziyyətləri (UI çipləri üçün kodlar).
WINDOW_OPEN = "open"
WINDOW_NOT_OPEN = "not_open"
WINDOW_LATE = "late"
WINDOW_CLOSED = "closed"


def _check_offering(folder, offering) -> None:
    if offering.organization_id != folder.organization_id:
        raise FolderError.of("folder.organization_mismatch")
    if offering.subject_id != folder.subject_id:
        raise FolderError.of("folder.subject_mismatch")
    if folder.period_id and offering.period_id != folder.period_id:
        raise FolderError.of("folder.period_mismatch")


def assignable_offerings(folder, user) -> list[dict]:
    """Aktorun bu qovluğu təyin edə biləcəyi açılışlar + cari təyinat vəziyyəti.

    ``[{"offering", "assignment" (və ya None), "is_active", "grades_selfwork",
    "selfwork_elsewhere"}]`` — sorğu sayı sabitdir (açılış sayından asılı deyil).
    """
    offerings = lookups.offering_model().objects.filter(
        organization_id=folder.organization_id, subject_id=folder.subject_id, is_active=True
    )
    if folder.period_id:
        offerings = offerings.filter(period_id=folder.period_id)
    if not lookups.is_org_admin(user, folder.organization):
        if not lookups.has_instructor_authority(user, folder.organization):
            return []
        offerings = offerings.filter(lookups.taught_offerings_q(user))
    rows = list(offerings.select_related("group", "period", "instructor").order_by("group__name", "pk").distinct())
    ids = [row.pk for row in rows]
    own = {row.offering_id: row for row in FolderAssignment.objects.filter(folder=folder, offering_id__in=ids)}
    graders = set(
        FolderAssignment.objects.filter(offering_id__in=ids, is_active=True, grades_selfwork=True)
        .exclude(folder=folder)
        .values_list("offering_id", flat=True)
    )
    return [
        {
            "offering": row,
            "assignment": own.get(row.pk),
            "is_active": bool(own.get(row.pk) and own[row.pk].is_active),
            "grades_selfwork": bool(own.get(row.pk) and own[row.pk].grades_selfwork),
            "selfwork_elsewhere": row.pk in graders,
        }
        for row in rows
    ]


def _grader_decision(folder, offering, assignment, option) -> tuple[bool, list]:
    warnings = []
    others = FolderAssignment.objects.filter(offering=offering, is_active=True, grades_selfwork=True)
    if assignment is not None:
        others = others.exclude(pk=assignment.pk)
    if others.exists():
        warnings.append(FolderError.of("assignment.selfwork_elsewhere").as_dict())
        return False, warnings
    if folder.selfwork_option and option and option != folder.selfwork_option:
        warnings.append(
            FolderError.of(
                "assignment.selfwork_option_mismatch", offering_option=option, folder_option=folder.selfwork_option
            ).as_dict()
        )
        return False, warnings
    return True, warnings


@transaction.atomic
def assign_folder(folder, offerings, *, by_user, request=None) -> list[dict]:
    """Qovluğu açılışlara təyin edir (təkrar çağırış idempotentdir, passiv təyinat yenidən aktivləşir).

    Nəticə: ``[{"assignment", "created": bool, "reactivated": bool, "warnings": [xəta dict]}]``.
    Qaralama qovluq ilk təyinatda AKTİV olur (tələbələr görməyə başlayır).
    """
    access.ensure_can_manage(by_user, folder)
    results = []
    for offering in offerings:
        _check_offering(folder, offering)
        if not lookups.teaches_offering(by_user, offering):
            raise FolderError.of("permission.not_teaching")
        # Paralel təyinatlar arasında «sərbəst işi kim qiymətləndirir» qərarı serializasiya olunsun
        # (DB-də açılış üzrə aktiv qiymətləndirici UNİKALDIR — bu, ikinci qatdır).
        advisory_lock("sf", "offering", offering.pk)
        version = syllabus_bridge.approved_version_for_offering(offering)
        structure = syllabus_bridge.selfwork_structure(version)
        option = structure["option"] if structure else ""
        assignment = FolderAssignment.objects.select_for_update().filter(folder=folder, offering=offering).first()
        created = reactivated = False
        grades, warnings = _grader_decision(folder, offering, assignment, option)
        now = timezone.now()
        if assignment is None:
            assignment = FolderAssignment.objects.create(
                organization_id=folder.organization_id,
                folder=folder,
                offering=offering,
                assigned_by=by_user,
                assigned_at=now,
                syllabus_version_ref=getattr(version, "pk", None),
                selfwork_option=option,
                grades_selfwork=grades,
            )
            created = True
        elif not assignment.is_active:
            assignment.is_active = True
            assignment.assigned_by = by_user
            assignment.assigned_at = now
            assignment.unassigned_at = None
            assignment.unassigned_by = None
            assignment.syllabus_version_ref = getattr(version, "pk", None)
            assignment.selfwork_option = option
            assignment.grades_selfwork = grades
            assignment.save()
            reactivated = True
        if created or reactivated:
            audit_change(
                assignment,
                actor=by_user,
                changes={"assigned": str(offering.pk), "grades_selfwork": grades, "option": option},
                request=request,
            )
            notify.folder_assigned(assignment)
        results.append({"assignment": assignment, "created": created, "reactivated": reactivated, "warnings": warnings})
    if results and folder.status == FolderStatus.DRAFT:
        folder.status = FolderStatus.ACTIVE
        folder.save(update_fields=["status", "updated_at"])
    return results


def unassign(assignment, *, by_user, request=None) -> FolderAssignment:
    """Təyinatı dayandırır (data saxlanılır, tələbə öz göndərişlərini görməyə davam edir)."""
    access.ensure_can_manage(by_user, assignment.folder)
    if assignment.is_active:
        assignment.is_active = False
        assignment.unassigned_at = timezone.now()
        assignment.unassigned_by = by_user
        assignment.save(update_fields=["is_active", "unassigned_at", "unassigned_by", "updated_at"])
        audit_change(assignment, actor=by_user, changes={"unassigned": str(assignment.offering_id)}, request=request)
    return assignment


# ── Son tarixlər ────────────────────────────────────────────────────────────


def _ensure_deadline_editor(user, assignment) -> None:
    if access.can_manage_folder(user, assignment.folder) or access.can_review_assignment(user, assignment):
        return
    raise FolderError.of("permission.denied")


def set_deadline(
    assignment, task, *, by_user, opens_at=None, due_at=None, late_policy: str = LatePolicy.NONE, request=None
) -> TaskDeadline:
    """Bir qrupda bir tapşırığın pəncərəsi (sahib və ya həmin qrupun müəllimi təyin edir)."""
    _ensure_deadline_editor(by_user, assignment)
    if task.folder_id != assignment.folder_id:
        raise FolderError.of("task.not_in_folder")
    if late_policy not in LatePolicy.values:
        late_policy = LatePolicy.NONE
    if opens_at and due_at and opens_at >= due_at:
        raise FolderError.of("deadline.invalid_range")
    deadline, _created = TaskDeadline.objects.update_or_create(
        assignment=assignment,
        task=task,
        defaults={
            "organization_id": assignment.organization_id,
            "opens_at": opens_at,
            "due_at": due_at,
            "late_policy": late_policy,
            "set_by": by_user,
        },
    )
    audit_change(
        deadline,
        actor=by_user,
        changes={"opens_at": opens_at, "due_at": due_at, "late_policy": late_policy},
        request=request,
    )
    return deadline


def set_deadline_for_all(task, *, by_user, opens_at=None, due_at=None, late_policy=LatePolicy.NONE, request=None):
    """Tapşırığın pəncərəsini qovluğun BÜTÜN aktiv təyinatlarına eyni qoyur → ``[TaskDeadline]``."""
    access.ensure_can_manage(by_user, task.folder)
    return [
        set_deadline(
            assignment,
            task,
            by_user=by_user,
            opens_at=opens_at,
            due_at=due_at,
            late_policy=late_policy,
            request=request,
        )
        for assignment in task.folder.assignments.filter(is_active=True).select_related("folder", "offering")
    ]


def clear_deadline(assignment, task, *, by_user, request=None) -> None:
    _ensure_deadline_editor(by_user, assignment)
    deleted, _ = TaskDeadline.objects.filter(assignment=assignment, task=task).delete()
    if deleted:
        audit_change(assignment, actor=by_user, changes={"deadline_cleared": str(task.pk)}, request=request)


def deadline_for(assignment, task):
    return TaskDeadline.objects.filter(assignment=assignment, task=task).first()


def window_state(deadline, *, now=None) -> dict:
    """Pəncərə vəziyyəti: ``open`` / ``not_open`` / ``late`` (gecikmə ilə açıq) / ``closed``."""
    now = now or timezone.now()
    if deadline is None:
        return {"state": WINDOW_OPEN, "opens_at": None, "due_at": None, "late_policy": LatePolicy.NONE.value}
    info = {"opens_at": deadline.opens_at, "due_at": deadline.due_at, "late_policy": deadline.late_policy}
    if deadline.opens_at and now < deadline.opens_at:
        return {"state": WINDOW_NOT_OPEN, **info}
    if deadline.due_at and now > deadline.due_at:
        state = WINDOW_LATE if deadline.late_policy == LatePolicy.ALLOW else WINDOW_CLOSED
        return {"state": state, **info}
    return {"state": WINDOW_OPEN, **info}


__all__ = [
    "WINDOW_CLOSED",
    "WINDOW_LATE",
    "WINDOW_NOT_OPEN",
    "WINDOW_OPEN",
    "assign_folder",
    "assignable_offerings",
    "clear_deadline",
    "deadline_for",
    "set_deadline",
    "set_deadline_for_all",
    "unassign",
    "window_state",
]
