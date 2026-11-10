"""Qovluğun qruplara AVTOMATİK təyinatı (sahib 2026-11-10).

«Müəllim fənn seçəndə o semestrdə hansı qrupa dərs deyirsə, o qrup müəllimin materiallarını avtomatik görsün —
bir də qrup seçməyə ehtiyac olmasın; indiki qovluqlara da aiddir.»

Qayda: qovluğun (``period`` dolu, arxivlənməmiş) sahibi həmin fənn + semestrdə AKTİV açılışın canlı müəllimidirsə
(``lookups.taught_offerings_q``: açılışın müəllimi, dərs müəllimi, bölünmüş jurnalın payı — patok/alt qrup/səviyyə
qrupu jurnalları da açılışdır) həmin açılışa ``FolderAssignment`` yaradılır. Passiv açılış (məs. gizlədilmiş Kollec
jurnalları — ``hide_college_journals_20261110``) daxil DEYİL.

Niyə oxu anında hesablanmır: təyinat sətri son tarixlərin, göndərişlərin, sərbəst iş qiymətləndiricisinin və jurnal
sinxronunun dayağıdır — auditoriya sətirsiz olsa bunların hamısı ikinci yol tələb edərdi. Ona görə sətir
materiallaşdırılır: qovluq yaradılanda dərhal (:func:`folders.create_folder`), sonra dövri beat tapşırığı
(``subject_folder.auto_assign_groups``) yeni yaranan açılışları tutur, mövcud qovluqlar üçün də eyni əmr
(``subject_folder_auto_assign``) işləyir.

Müəllimin əl ilə seçimi qalır: əlavə qrupu əl ilə təyin etmək olar; əl ilə LƏĞV edilmiş (passiv) təyinat avtomatik
geri qaytarılmır — sətri olan açılışa toxunulmur. Qaralama qovluq yalnız əvvəllər HEÇ təyinatı olmayıbsa aktivləşir.
"""

from __future__ import annotations

import logging
import secrets
from collections import Counter, defaultdict

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..constants import FolderStatus
from ..models import FolderAssignment, SubjectFolder
from . import lookups
from .assignments import assign_offering
from .events import audit_change

logger = logging.getLogger(__name__)

BATCH_PREFIX = "sfauto"


def new_batch_id(prefix: str = BATCH_PREFIX) -> str:
    return f"{prefix}-{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def candidate_folders(*, organization=None, include_ended: bool = False):
    """Avtomatik təyinata namizəd qovluqlar: semestri olan, arxivlənməmiş (defolt: semestri bitməmiş)."""
    rows = SubjectFolder.objects.filter(period__isnull=False).exclude(status=FolderStatus.ARCHIVED)
    if organization is not None:
        rows = rows.filter(organization=organization)
    if not include_ended:
        rows = rows.filter(Q(period__end_date__isnull=True) | Q(period__end_date__gte=timezone.localdate()))
    return rows


def plan(folders) -> list[tuple]:
    """``[(folder, [açılış…])]`` — hər qovluğun HƏLƏ sətri olmayan, sahibinin tədris etdiyi açılışları.

    Sorğu sayı sahib sayına mütənasibdir (sahib başına: səlahiyyət + açılışlar), qovluq sayına yox.
    """
    folders = [
        row
        for row in folders
        if row.period_id and row.status != FolderStatus.ARCHIVED and getattr(row, "owner", None) is not None
    ]
    if not folders:
        return []
    existing = set(
        FolderAssignment.objects.filter(folder_id__in=[row.pk for row in folders]).values_list(
            "folder_id", "offering_id"
        )
    )
    by_owner = defaultdict(list)
    for folder in folders:
        by_owner[(folder.organization_id, folder.owner_id)].append(folder)
    result = []
    for rows in by_owner.values():
        owner, organization = rows[0].owner, rows[0].organization
        if not getattr(owner, "is_active", False) or not lookups.has_instructor_authority(owner, organization):
            continue
        offerings = (
            lookups.offering_model()
            .objects.filter(
                organization_id=organization.pk,
                is_active=True,
                subject_id__in={row.subject_id for row in rows},
                period_id__in={row.period_id for row in rows},
            )
            .filter(lookups.taught_offerings_q(owner))
            .select_related("organization", "group")
            .order_by("group__name", "pk")
            .distinct()
        )
        index = defaultdict(list)
        for offering in offerings:
            index[(offering.subject_id, offering.period_id)].append(offering)
        for folder in rows:
            missing = [
                offering
                for offering in index.get((folder.subject_id, folder.period_id), [])
                if (folder.pk, offering.pk) not in existing
            ]
            if missing:
                result.append((folder, missing))
    return result


def _has_published_content(folder) -> bool:
    return (
        folder.materials.filter(is_published=True, is_archived=False).exists()
        or folder.tasks.filter(is_published=True, is_archived=False).exists()
    )


def auto_assign(folders, *, actor=None, batch: str = "", request=None, notify_students: bool = True) -> dict:
    """Plana görə təyinatları yaradır (idempotent) → ``{"batch", "counts": {...}}``.

    Hər qovluq öz savepoint-ində: bir qovluğun xətası digərlərini dayandırmır (``counts["errors"]``).
    Tələbələrə «Yeni fənn qovluğu» bildirişi yalnız qovluqda dərc edilmiş məzmun varsa gedir (boş qovluq səs-küy
    yaratmasın; sonrakı dərc öz bildirişini göndərir).
    """
    batch = batch or new_batch_id()
    counts = Counter()
    for folder, offerings in plan(folders):
        try:
            with transaction.atomic():
                created, activated = _apply_folder(
                    folder, offerings, actor=actor, batch=batch, request=request, notify=notify_students
                )
        except Exception:  # noqa: BLE001 — bir qovluq digərlərini saxlamasın; say jurnala düşür
            logger.exception("subject_folder auto-assign failed (folder %s)", folder.pk)
            counts["errors"] += 1
            continue
        counts["folders"] += 1
        counts["assignments"] += created
        counts["folders_activated"] += 1 if activated else 0
    return {"batch": batch, "counts": dict(counts)}


def _apply_folder(folder, offerings, *, actor, batch, request, notify) -> tuple[int, bool]:
    had_rows = FolderAssignment.objects.filter(folder=folder).exists()
    by_user = actor if actor is not None else folder.owner
    notify_now = notify and _has_published_content(folder)
    created = 0
    for offering in offerings:
        result = assign_offering(
            folder, offering, by_user=by_user, request=request, auto_batch=batch, notify_students=notify_now
        )
        created += 1 if result["created"] else 0
    if created and not had_rows and folder.status == FolderStatus.DRAFT:
        folder.status = FolderStatus.ACTIVE
        folder.save(update_fields=["status", "updated_at"])
        audit_change(
            folder, actor=by_user, changes={"status": ["draft", "active"], "auto_batch": batch}, request=request
        )
        return created, True
    return created, False


def undo(batch: str, *, actor=None, organization=None) -> dict:
    """Partiyanın təyinatlarını PASSİV edir (sətir qalır → avtomatik qayda onu yenidən açmır; müəllim əl ilə aça bilər).

    Partiyanın aktivləşdirdiyi qovluq (başqa təyinatı yoxdursa) qaralamaya qaytarılır. Göndərişlər saxlanılır.
    """
    counts = Counter()
    rows = FolderAssignment.objects.filter(auto_batch=batch).select_related("folder")
    if organization is not None:
        rows = rows.filter(organization=organization)
    now = timezone.now()
    folders = {}
    for assignment in rows:
        folders[assignment.folder_id] = assignment.folder
        if not assignment.is_active:
            counts["already_inactive"] += 1
            continue
        assignment.is_active = False
        assignment.unassigned_at = now
        assignment.unassigned_by = actor if getattr(actor, "pk", None) else None
        assignment.save(update_fields=["is_active", "unassigned_at", "unassigned_by", "updated_at"])
        audit_change(assignment, actor=actor, changes={"auto_undo": batch})
        counts["assignments_deactivated"] += 1
    for folder in folders.values():
        others = folder.assignments.exclude(auto_batch=batch).exists()
        if folder.status == FolderStatus.ACTIVE and not others:
            folder.status = FolderStatus.DRAFT
            folder.save(update_fields=["status", "updated_at"])
            audit_change(folder, actor=actor, changes={"status": ["active", "draft"], "auto_undo": batch})
            counts["folders_back_to_draft"] += 1
    return {"batch": batch, "counts": dict(counts)}


__all__ = ["BATCH_PREFIX", "auto_assign", "candidate_folders", "new_batch_id", "plan", "undo"]
