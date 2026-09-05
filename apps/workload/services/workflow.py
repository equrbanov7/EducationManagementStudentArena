"""Təsdiq zənciri: göndərmə → fakültə dilimləri → dekan qərarı (spec §4.1–§4.2).

    Tədris şöbəsi (12) göndərir → hər toxunulan FAKÜLTƏ üçün bir dilim yaranır
      → koordinator (13) sətirlərə viza/irad verir
      → dekan (15) dilimi təsdiqləyir və ya sətir seçib qaytarır
      → BÜTÜN dilimlər təsdiqlənəndə sənəd `approved` olur
      → kafedra müdiri (14) bölgüyə başlayır.

Keçid qaydası ``apps/workload/state_machine.py``-dədir (saf modul) — burada
YALNIZ icra var: kilid (``select_for_update``), audit, bildiriş, dilim
hesabı. Hər səbəb tələb edən əməl ≥20 simvol yoxlanışından keçir (§8/6).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

from .. import state_machine as sm
from ..constants import (
    DEAN_SECOND_APPROVAL_ENABLED,
    PERM_APPROVE,
    PERM_SUBMIT,
    REASON_MIN_LENGTH,
    RowReviewStatus,
    SliceStatus,
    TaskStatus,
)
from ..models import TaskFacultySlice, TeachingTask, TeachingTaskRow
from .scoping import WorkloadDenied

logger = logging.getLogger(__name__)

_SECTION_LINKS = {
    "center": "/accounts/profile/?section=workload-center",
    "approval": "/accounts/profile/?section=workload-approval",
    "distribution": "/accounts/profile/?section=workload-distribution",
}


# ── Qapılar ─────────────────────────────────────────────────────────────────


def ensure_reason(reason: str) -> str:
    text = (reason or "").strip()
    if len(text) < REASON_MIN_LENGTH:
        raise WorkloadDenied(
            "workload.reason_too_short",
            f"Səbəb ən azı {REASON_MIN_LENGTH} simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.",
        )
    return text


def ensure_can_submit(actor, chair_id) -> None:
    """Tapşırığı dekanlıqlara göndərmək — tədris şöbəsi (və operator rolları)."""
    if not actor.has(PERM_SUBMIT) or not actor.covers_unit(chair_id, PERM_SUBMIT):
        raise WorkloadDenied("workload.submit_denied", "Tapşırığı göndərmək səlahiyyətiniz yoxdur.")


def ensure_can_approve(actor, faculty_id) -> None:
    """Fakültə dilimini təsdiqləmək/qaytarmaq — dekan (öz fakültəsi)."""
    if not actor.has(PERM_APPROVE) or not actor.covers_unit(faculty_id, PERM_APPROVE):
        raise WorkloadDenied("workload.approve_denied", "Bu fakültənin dilimini təsdiqləmək səlahiyyətiniz yoxdur.")


def ensure_distribution_stage(task) -> None:
    """Kafedra bölgüsü YALNIZ zəncir keçiləndən sonra (plan §2/14).

    ``draft`` istisna yalnız F1-dən ƏVVƏLKİ sənədlər üçündür: kafedra özü
    yaratmışsa (``submitted_at`` boşdur) bölgü açıqdır. Sənəd bir dəfə
    göndərilibsə, ``approved``-dan əvvəl bölgü BAĞLIDIR.
    """
    if task.status == TaskStatus.DRAFT and task.submitted_at is not None:
        raise WorkloadDenied(
            "workload.not_approved_yet",
            "Tapşırıq dekanlıq təsdiqindən keçməyib — bölgü açılmır.",
        )
    if task.status in (TaskStatus.SUBMITTED, TaskStatus.RETURNED, TaskStatus.PENDING_FINAL_APPROVAL):
        raise WorkloadDenied(
            "workload.not_approved_yet",
            "Tapşırıq təsdiq mərhələsindədir — bölgü yalnız təsdiqdən sonra açılır.",
        )


# ── Fakültə dilimləri ───────────────────────────────────────────────────────


def task_faculty_ids(task) -> list:
    """Tapşırığın toxunduğu fakültələr — sətirlərin ``faculty`` sahəsindən.

    Sətrin fakültəsi boşdursa (ixtisas göstərilməyib) dilim yaranmır; belə
    sətirlər göndərmə xülasəsində «marşrutsuz» kimi sadalanır.
    """
    return list(
        TeachingTaskRow.objects.filter(task=task, faculty__isnull=False).values_list("faculty_id", flat=True).distinct()
    )


def unrouted_rows(task):
    """Fakültəsi olmayan sətirlər — dekanlıq marşrutuna düşmür."""
    return TeachingTaskRow.objects.filter(task=task, faculty__isnull=True)


def submit_summary(task) -> dict:
    """Göndərmədən əvvəlki yoxlama (ekran 12 «Göndərmədən əvvəl yoxlama»)."""
    from django.apps import apps as django_apps

    from .tasks import row_warnings

    rows = list(task.rows.all().select_related("subject", "specialty", "faculty").prefetch_related("groups"))
    warnings: list[dict] = []
    for row in rows:
        for warning in row_warnings(row):
            warnings.append({"row": row.subject_label, **warning})
    faculty_ids = task_faculty_ids(task)
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    faculties = list(OrgUnit.objects.filter(pk__in=faculty_ids).order_by("name"))
    unrouted = [row.subject_label for row in rows if row.faculty_id is None]
    return {
        "row_count": len(rows),
        "total_hours": sum(int(row.total_hours or 0) for row in rows),
        "total_credits": sum(int(row.credits_value or 0) for row in rows),
        "warnings": warnings,
        "faculties": [{"id": str(unit.pk), "name": unit.name} for unit in faculties],
        "unrouted": unrouted,
        "can_submit": bool(rows) and bool(faculty_ids),
    }


@transaction.atomic
def submit_task(*, task: TeachingTask, actor, request=None) -> dict:
    """Sənədi dekanlıqlara göndərir və fakültə dilimlərini yaradır (spec §4.2)."""
    ensure_can_submit(actor, task.chair_id)
    locked = TeachingTask.objects.select_for_update(of=("self",)).get(pk=task.pk)
    sm.ensure_transition(locked.status, sm.SUBMITTED)

    faculty_ids = task_faculty_ids(locked)
    if not faculty_ids:
        raise WorkloadDenied(
            "workload.no_faculty_slice",
            "Sətirlərin heç birində ixtisas/fakültə göstərilməyib — dilim yaradıla bilmir.",
        )
    if not locked.rows.exists():
        raise WorkloadDenied("workload.no_rows", "Boş sənəd göndərilmir.")

    was_returned = locked.status == TaskStatus.RETURNED
    if was_returned:
        locked.revision = int(locked.revision or 0) + 1
    now = timezone.now()
    locked.status = TaskStatus.SUBMITTED
    locked.submitted_by = getattr(actor, "user", None)
    locked.submitted_at = now
    locked.save(update_fields=["status", "revision", "submitted_by", "submitted_at", "updated_at"])

    created = 0
    for faculty_id in faculty_ids:
        _, is_new = TaskFacultySlice.objects.get_or_create(
            task=locked,
            faculty_id=faculty_id,
            revision=locked.revision,
            defaults={
                "organization": locked.organization,
                "status": SliceStatus.PENDING,
                "submitted_at": now,
            },
        )
        created += int(is_new)

    # Qaytarılmış sətirlərin işarəsi göndərişdə təmizlənir — yeni dövrə.
    TeachingTaskRow.objects.filter(task=locked, review_status=RowReviewStatus.RETURNED).update(
        review_status=RowReviewStatus.PENDING
    )

    _notify_faculty_actors(locked, faculty_ids)
    log_action(
        AuditAction.UPDATE,
        user=getattr(actor, "user", None),
        organization=locked.organization,
        obj=locked,
        new_values={"status": locked.status, "revision": locked.revision, "slices": created},
        reason="workload.task_submitted",
        request=request,
        resource_type="workload.TeachingTask",
        resource_id=str(locked.pk),
        resource_repr=f"{locked.chair_id} · {locked.academic_year}",
    )
    return {"status": locked.status, "revision": locked.revision, "slices": created}


def _ensure_current_revision(locked: TaskFacultySlice, task) -> None:
    """Köhnəlmiş revision-un dilimi üzərində qərar verilməsini bloklayır.

    QA dalğa 2 (2026-09-03) tapıntısı: dilim qaytarılıb tapşırıq YENİDƏN
    göndəriləndə (`submit_task`) cari revision üçün YENİ dilim yaranır, köhnəsi
    isə bazada qalır.  `approve_slice` / `return_slice` revision yoxlamadığı
    üçün dekan köhnə (superseded) dilimi təsdiqləyə bilirdi: cavab `ok: true`
    gəlirdi, audit «təsdiqləndi» yazırdı, LAKİN `slice_progress` yalnız
    `revision=task.revision` sayır → sənəd irəliləmirdi.  Yəni sükutla itən
    qərar.  Layihənin «final entry session versioning» qaydası ilə eyni
    məntiq: köhnə versiya 409 ilə rədd edilir.
    """
    if locked.revision != task.revision:
        raise WorkloadDenied(
            "workload.stale_revision",
            "Bu dilim köhnəlmiş revision-a aiddir — səhifəni yeniləyin.",
        )


@transaction.atomic
def approve_slice(*, slice_obj: TaskFacultySlice, actor, comment: str = "", request=None) -> dict:
    """Dekan fakültə dilimini bütöv təsdiqləyir."""
    ensure_can_approve(actor, slice_obj.faculty_id)
    locked = TaskFacultySlice.objects.select_for_update(of=("self",)).get(pk=slice_obj.pk)
    task = TeachingTask.objects.get(pk=locked.task_id)
    if task.status not in sm.REVIEWABLE:
        raise WorkloadDenied("workload.slice_not_open", "Tapşırıq təsdiq mərhələsində deyil.")
    _ensure_current_revision(locked, task)
    if locked.status == SliceStatus.APPROVED:
        raise WorkloadDenied("workload.slice_already_approved", "Dilim artıq təsdiqlənib.")

    locked.status = SliceStatus.APPROVED
    locked.decided_by = getattr(actor, "user", None)
    locked.decided_at = timezone.now()
    locked.comment = (comment or "").strip()
    locked.save(update_fields=["status", "decided_by", "decided_at", "comment", "updated_at"])

    log_action(
        AuditAction.UPDATE,
        user=getattr(actor, "user", None),
        organization=locked.organization,
        obj=locked,
        new_values={"status": locked.status, "faculty": str(locked.faculty_id)},
        reason="workload.slice_approved",
        request=request,
        resource_type="workload.TaskFacultySlice",
        resource_id=str(locked.pk),
        resource_repr=f"{locked.task_id} · {locked.faculty_id}",
    )
    result = recompute_task_status(task, actor=actor, request=request)
    return {"slice_status": locked.status, **result}


@transaction.atomic
def return_slice(*, slice_obj: TaskFacultySlice, actor, reason: str, row_ids=None, request=None) -> dict:
    """Dekan dilimi (və ya seçilmiş sətirləri) səbəblə geri qaytarır."""
    ensure_can_approve(actor, slice_obj.faculty_id)
    text = ensure_reason(reason)
    locked = TaskFacultySlice.objects.select_for_update(of=("self",)).get(pk=slice_obj.pk)
    task = TeachingTask.objects.select_for_update(of=("self",)).get(pk=locked.task_id)
    if task.status not in sm.REVIEWABLE:
        raise WorkloadDenied("workload.slice_not_open", "Tapşırıq təsdiq mərhələsində deyil.")
    _ensure_current_revision(locked, task)

    locked.status = SliceStatus.RETURNED
    locked.decided_by = getattr(actor, "user", None)
    locked.decided_at = timezone.now()
    locked.comment = text
    locked.save(update_fields=["status", "decided_by", "decided_at", "comment", "updated_at"])

    marked = TeachingTaskRow.objects.filter(task=task, faculty_id=locked.faculty_id)
    if row_ids:
        marked = marked.filter(pk__in=list(row_ids))
    marked_count = marked.update(review_status=RowReviewStatus.RETURNED)

    sm.ensure_transition(task.status, sm.RETURNED)
    task.status = TaskStatus.RETURNED
    task.save(update_fields=["status", "updated_at"])

    _notify_office(task, title="Dərs yükü tapşırığı qaytarıldı", body=text)
    log_action(
        AuditAction.UPDATE,
        user=getattr(actor, "user", None),
        organization=locked.organization,
        obj=locked,
        new_values={"status": locked.status, "returned_rows": marked_count, "reason": text},
        reason=f"workload.slice_returned — {text}",
        request=request,
        resource_type="workload.TaskFacultySlice",
        resource_id=str(locked.pk),
        resource_repr=f"{locked.task_id} · {locked.faculty_id}",
    )
    return {"slice_status": locked.status, "task_status": task.status, "returned_rows": marked_count}


def slice_progress(task) -> dict:
    """Cari revision üzrə dilim sayğacları (ekran 12 «İzləmə» paneli)."""
    counts = TaskFacultySlice.objects.filter(task=task, revision=task.revision).aggregate(
        total=Count("id"),
        approved=Count("id", filter=Q(status=SliceStatus.APPROVED)),
        returned=Count("id", filter=Q(status=SliceStatus.RETURNED)),
        pending=Count("id", filter=Q(status=SliceStatus.PENDING)),
    )
    return {key: int(value or 0) for key, value in counts.items()}


def recompute_task_status(task, *, actor=None, request=None) -> dict:
    """Bütün dilimlər təsdiqlənibsə sənədi ``approved`` edir (spec §4.2/5).

    ⚠️ ``approved`` HEÇ VAXT əl ilə qoyulmur — aşağıdan yuxarı törəyir.
    """
    progress = slice_progress(task)
    if not progress["total"] or progress["approved"] != progress["total"]:
        return {"task_status": task.status, **progress}

    target = sm.APPROVED
    if task.status == TaskStatus.PENDING_FINAL_APPROVAL:
        pass
    elif not DEAN_SECOND_APPROVAL_ENABLED:  # pragma: no cover — policy söndürüldükdə
        target = sm.APPROVED
    sm.ensure_transition(task.status, target)
    task.status = TaskStatus.APPROVED
    task.save(update_fields=["status", "updated_at"])
    _notify_chair(task)
    log_action(
        AuditAction.UPDATE,
        user=getattr(actor, "user", None),
        organization=task.organization,
        obj=task,
        new_values={"status": task.status, "slices": progress["total"]},
        reason="workload.task_approved",
        request=request,
        resource_type="workload.TeachingTask",
        resource_id=str(task.pk),
        resource_repr=f"{task.chair_id} · {task.academic_year}",
    )
    return {"task_status": task.status, **progress}


# ── Bildirişlər (uğursuzluq axını DAYANDIRMIR) ──────────────────────────────


def _recipients(queryset):
    return [user for user in queryset if user is not None]


def _unit_role_users(organization, units, role_names):
    """Vahid(lər)i əhatə edən, verilmiş rolları daşıyan AKTİV üzvlərin istifadəçiləri.

    Əvvəl alıcı yalnız ``OrgUnit.head`` idi — klonda fakültə/kafedraların çoxu
    rəhbərsizdir, ona görə dekan/kafedra müdiri bildiriş almırdı (QA 2026-09-05
    WORKLOAD-SCHEDULE-09). İndi rol üzvlüyü də alıcıdır (rəhbər + rol daşıyıcıları).
    """
    from apps.organizations.unit_heads import members_covering_unit

    users: dict = {}
    for unit in units:
        if unit is None:
            continue
        for membership in members_covering_unit(organization, unit, role_names=role_names):
            users.setdefault(membership.user_id, membership.user)
    return list(users.values())


FACULTY_ACTOR_ROLES = ("dean", "vice_dean", "program_coordinator")
CHAIR_ACTOR_ROLES = ("chair_head", "department_head", "section_head")


def send_notification(organization, recipients, *, title, body, link, event, metadata=None) -> int:
    recipients = _recipients(recipients)
    if not recipients:
        return 0
    try:
        from apps.notifications.models import NotificationType
        from apps.notifications.public import create_notification_for_users

        created = create_notification_for_users(
            recipients=recipients,
            title=title[:255],
            message=body,
            link=link,
            notification_type=NotificationType.SYSTEM,
            metadata={"event": event, **(metadata or {})},
            organization=organization,
        )
        return len(created)
    except Exception:  # noqa: BLE001 — bildiriş zənciri iş axınını dayandırmır
        logger.warning("workload: notification failed (%s)", event, exc_info=True)
        return 0


def _notify_faculty_actors(task, faculty_ids) -> int:
    """Dekan + fakültənin koordinatorları «yeni dilim gəldi» bildirişi alır."""
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    faculties = list(OrgUnit.objects.filter(pk__in=list(faculty_ids)).select_related("head"))
    unique = {u.pk: u for u in [unit.head for unit in faculties] if u is not None}
    for user in _unit_role_users(task.organization, faculties, FACULTY_ACTOR_ROLES):
        unique.setdefault(user.pk, user)
    return send_notification(
        task.organization,
        list(unique.values()),
        title=f"Dərs yükü dilimi: {task.academic_year}",
        body="Kafedranın tədris tapşırığı fakültənizə göndərildi — təsdiq gözlənilir.",
        link=_SECTION_LINKS["approval"],
        event="workload_slice_submitted",
        metadata={"task_id": str(task.pk)},
    )


def _notify_office(task, *, title, body) -> int:
    """Sənədi göndərən + kafedra rəhbəri qaytarma barədə xəbərdar edilir."""
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    chair = OrgUnit.objects.filter(pk=task.chair_id).select_related("head").first()
    recipients = [task.submitted_by, task.created_by, getattr(chair, "head", None)]
    recipients += _unit_role_users(task.organization, [chair], CHAIR_ACTOR_ROLES)
    unique: dict = {}
    for user in recipients:
        if user is not None:
            unique[user.pk] = user
    return send_notification(
        task.organization,
        list(unique.values()),
        title=title,
        body=body,
        link=_SECTION_LINKS["center"],
        event="workload_task_returned",
        metadata={"task_id": str(task.pk)},
    )


def _notify_chair(task) -> int:
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    chair = OrgUnit.objects.filter(pk=task.chair_id, unit_type__in=(OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)).first()
    unique = {u.pk: u for u in [getattr(chair, "head", None)] if u is not None}
    for user in _unit_role_users(task.organization, [chair], CHAIR_ACTOR_ROLES):
        unique.setdefault(user.pk, user)
    return send_notification(
        task.organization,
        list(unique.values()),
        title=f"Tədris tapşırığı təsdiqləndi: {task.academic_year}",
        body="Bütün fakültə dilimləri təsdiqləndi — yükü müəllimlərə bölə bilərsiniz.",
        link=_SECTION_LINKS["distribution"],
        event="workload_task_approved",
        metadata={"task_id": str(task.pk)},
    )


__all__ = [
    "approve_slice",
    "ensure_can_approve",
    "ensure_can_submit",
    "ensure_distribution_stage",
    "ensure_reason",
    "recompute_task_status",
    "return_slice",
    "send_notification",
    "slice_progress",
    "submit_summary",
    "submit_task",
    "task_faculty_ids",
    "unrouted_rows",
]
