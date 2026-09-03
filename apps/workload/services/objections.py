"""Müəllimin yükü təsdiqləməsi və etirazı — ekran 16 §4 «Təsdiq / etiraz».

Dizayn 4 SƏBƏB verir (hərfi copy, ``constants.ObjectionReason``):
«Saat sayı düz deyil» · «Qrup/tələbə sayı səhvdir» · «Fənn ixtisasım deyil» ·
«Norma həddindən artıqdır».

QAYDALAR
--------
* Müəllim YALNIZ ÖZ bölgü sətirlərinə etiraz edir (``teacher=request.user``);
  başqasının sətri → 403 ``workload.objection_denied``.
* Etiraz reyestri **append-only** (DB trigger, miqrasiya ``0005``): mətn heç
  vaxt redaktə olunmur; kafedra müdiri yalnız qərar sahələrini bağlayır.
* Etiraz kafedra müdirinə VƏ dekanlığa görünür — bildiriş hər ikisinə gedir
  (dizayn: «Etiraz kafedra müdirinə və dekanlığa göndərilir.»).
* Etiraz **bölgünü dayandırmır** — o, düzəliş (amendment) üçün siqnaldır.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

from ..constants import (
    DEFAULT_ANNUAL_NORM_HOURS,
    PERM_OBJECT,
    ObjectionReason,
    ObjectionStatus,
    TaskStatus,
)
from ..models import LoadObjection, TeacherAssignment, TeacherWorkloadProfile
from .scoping import WorkloadDenied
from .workflow import ensure_reason

logger = logging.getLogger(__name__)

_REASON_KEYS = {str(value) for value, _ in ObjectionReason.choices}
#: Müəllim yalnız TƏSDİQLƏNMİŞ (bölünmüş) tapşırığın sətirlərini görür.
_VISIBLE_TASK_STATUSES = (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED)


def ensure_can_object(actor) -> None:
    if not actor.has(PERM_OBJECT):
        raise WorkloadDenied("workload.objection_denied", "Etiraz bildirmək səlahiyyətiniz yoxdur.")


def _own_assignment(actor, assignment_id):
    if not assignment_id:
        raise WorkloadDenied("workload.assignment_not_found", "Bölgü sətri tapılmadı.")
    assignment = (
        TeacherAssignment.objects.filter(
            organization=actor.organization,
            pk=assignment_id,
            row__task__status__in=_VISIBLE_TASK_STATUSES,
        )
        .select_related("row", "row__task", "teacher")
        .first()
    )
    if assignment is None:
        raise WorkloadDenied("workload.assignment_not_found", "Bölgü sətri tapılmadı.")
    if assignment.teacher_id != actor.user_id:
        raise WorkloadDenied("workload.objection_denied", "Bu sətir sizin yükünüz deyil.")
    return assignment


@transaction.atomic
def create_objection(*, actor, assignment_id, reason_key: str, text: str, request=None) -> LoadObjection:
    """Müəllim öz bölgü sətrinə 4 səbəbdən biri ilə etiraz göndərir."""
    ensure_can_object(actor)
    if reason_key not in _REASON_KEYS:
        raise WorkloadDenied("workload.invalid_reason", "Etiraz səbəbi seçilməyib.")
    body = ensure_reason(text)
    assignment = _own_assignment(actor, assignment_id)

    objection = LoadObjection.objects.create(
        organization=assignment.organization,
        row=assignment.row,
        assignment=assignment,
        teacher=actor.user,
        reason_key=reason_key,
        text=body,
        status=ObjectionStatus.OPEN,
    )
    _notify_chain(assignment.row.task, objection)
    log_action(
        AuditAction.CREATE,
        user=actor.user,
        organization=assignment.organization,
        obj=objection,
        new_values={"reason": reason_key, "text": body, "assignment": str(assignment.pk)},
        reason=f"workload.objection_raised — {body}",
        request=request,
        resource_type="workload.LoadObjection",
        resource_id=str(objection.pk),
        resource_repr=assignment.row.subject_label,
    )
    return objection


@transaction.atomic
def confirm_own_load(*, actor, academic_year: str, request=None) -> dict:
    """Müəllim illik yükünü TƏSDİQLƏYİR (profil bayrağı + audit)."""
    ensure_can_object(actor)
    if not academic_year:
        raise WorkloadDenied("workload.year_required", "Tədris ili göstərilməlidir.")
    has_rows = TeacherAssignment.objects.filter(
        organization=actor.organization,
        teacher=actor.user,
        row__task__academic_year=academic_year,
        row__task__status__in=_VISIBLE_TASK_STATUSES,
    ).exists()
    if not has_rows:
        raise WorkloadDenied("workload.nothing_to_confirm", "Bu tədris ilində təsdiqlənəsi yük yoxdur.")

    profile, _created = TeacherWorkloadProfile.objects.get_or_create(
        organization=actor.organization,
        teacher=actor.user,
        academic_year=academic_year,
        defaults={"annual_norm_hours": DEFAULT_ANNUAL_NORM_HOURS},
    )
    profile.load_confirmed_at = timezone.now()
    profile.save(update_fields=["load_confirmed_at", "updated_at"])

    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=actor.organization,
        obj=profile,
        new_values={"load_confirmed_at": profile.load_confirmed_at.isoformat(), "academic_year": academic_year},
        reason="workload.load_confirmed",
        request=request,
        resource_type="workload.TeacherWorkloadProfile",
        resource_id=str(profile.pk),
        resource_repr=academic_year,
    )
    return {"confirmed_at": profile.load_confirmed_at}


def is_load_confirmed(*, organization, teacher, academic_year: str) -> bool:
    return TeacherWorkloadProfile.objects.filter(
        organization=organization, teacher=teacher, academic_year=academic_year, load_confirmed_at__isnull=False
    ).exists()


def my_objections(*, organization, teacher, academic_year: str = ""):
    queryset = LoadObjection.objects.filter(organization=organization, teacher=teacher).select_related(
        "row", "row__subject", "row__task"
    )
    if academic_year:
        queryset = queryset.filter(row__task__academic_year=academic_year)
    return queryset


def chair_objections(*, task):
    """Kafedra müdirinin gördüyü etirazlar (ekran 14 sağ panel siqnalı)."""
    return (
        LoadObjection.objects.filter(row__task=task)
        .select_related("row", "row__subject", "teacher", "assignment")
        .order_by("status", "-created_at")
    )


@transaction.atomic
def resolve_objection(*, objection: LoadObjection, actor, status: str, note: str = "", request=None) -> LoadObjection:
    """Kafedra müdiri etirazı bağlayır (qəbul / rədd) — MƏTN toxunulmur."""
    from .scoping import ensure_can_distribute

    ensure_can_distribute(actor, objection.row.task.chair_id)
    if status not in {ObjectionStatus.ACCEPTED, ObjectionStatus.REJECTED}:
        raise WorkloadDenied("workload.invalid_status", "Qərar dəyəri yanlışdır.")
    if objection.status != ObjectionStatus.OPEN:
        raise WorkloadDenied("workload.objection_closed", "Etiraz artıq bağlanıb.")

    objection.status = status
    objection.resolved_by = actor.user
    objection.resolved_at = timezone.now()
    objection.resolution_note = (note or "").strip()
    objection.save(update_fields=["status", "resolved_by", "resolved_at", "resolution_note", "updated_at"])

    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=objection.organization,
        obj=objection,
        new_values={"status": status, "note": objection.resolution_note},
        reason="workload.objection_resolved",
        request=request,
        resource_type="workload.LoadObjection",
        resource_id=str(objection.pk),
        resource_repr=objection.row.subject_label,
    )
    return objection


def _notify_chain(task, objection) -> int:
    """Kafedra müdiri + fakültə dekanı etirazdan xəbər tutur."""
    from django.apps import apps as django_apps

    from .workflow import send_notification

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    chair = OrgUnit.objects.filter(pk=task.chair_id).select_related("head").first()
    faculty = (
        OrgUnit.objects.filter(pk=objection.row.faculty_id, unit_type=OrgUnitType.FACULTY)
        .select_related("head")
        .first()
        if objection.row.faculty_id
        else None
    )
    recipients = {}
    for unit in (chair, faculty):
        head = getattr(unit, "head", None)
        if head is not None:
            recipients[head.pk] = head
    teacher = objection.teacher
    label = teacher.get_full_name() or teacher.username if teacher else ""
    return send_notification(
        task.organization,
        list(recipients.values()),
        title=f"Yük üzrə etiraz: {objection.row.subject_label}",
        body=f"{label}: {objection.get_reason_key_display()} — {objection.text}",
        link="/accounts/profile/?section=workload-distribution",
        event="workload_objection_raised",
        metadata={"task_id": str(task.pk), "objection_id": str(objection.pk)},
    )


__all__ = [
    "chair_objections",
    "confirm_own_load",
    "create_objection",
    "ensure_can_object",
    "is_load_confirmed",
    "my_objections",
    "resolve_objection",
]
