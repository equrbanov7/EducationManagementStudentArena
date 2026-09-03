"""Koordinator vizası — ekran 13 «Yük vizası» (spec §5.4, handoff §5/13).

ƏSAS QAYDA
----------
**İrad yazılan sətrin ``reviewed`` bayrağı silinir.** Sətir eyni anda həm
vizalanmış, həm iradlı ola bilməz — ona görə viza yazısı `(row, coordinator)`
üzrə UNİKALDIR və `TeachingTaskRow.review_status` güzgüsü eyni tranzaksiyada
yenilənir.

ƏHATƏ
-----
Koordinator YALNIZ öz ixtisasının (``Membership.scope_unit`` = specialty
OrgUnit) sətirlərini görür və işarələyir. Başqa ixtisasın sətri → 403
(``workload.review_denied``), boş əhatə → BOŞ siyahı (§8/4: «no scope ≠ bütün
universitet»).

ARXİV
-----
Keçmiş tədris ili yalnız oxunuşdur (``is_archive_year``) — servis qatı yazmanı
bloklayır, UI isə lentdə «arxiv — yalnız oxunuş» göstərir.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, Q

from core.audit import log_action
from core.constants import AuditAction

from .. import state_machine as sm
from ..constants import PERM_REVIEW, RowReviewStatus, TaskStatus
from ..models import TaskRowReview, TeachingTaskRow
from .scoping import WorkloadDenied
from .workflow import ensure_reason

#: Vizanın icazəli iki dəyəri (`RETURNED` dekanın işarəsidir, koordinatorun yox).
REVIEW_STATES = (RowReviewStatus.REVIEWED, RowReviewStatus.FLAGGED)


def coordinator_specialty_ids(actor) -> list:
    """Koordinatorun əhatəsindəki ixtisas ``OrgUnit`` id-ləri (fail-closed)."""
    from django.apps import apps as django_apps

    from core.constants import OrgUnitType

    if not actor.has(PERM_REVIEW):
        return []
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    base = OrgUnit.objects.filter(organization=actor.organization, is_active=True, unit_type=OrgUnitType.SPECIALTY)
    scope = actor.scope_for(PERM_REVIEW)
    if scope.is_org_wide:
        return list(base.values_list("pk", flat=True))
    if not scope.has_structure_access:
        return []
    return list(base.filter(scope.unit_subtree_q()).values_list("pk", flat=True))


def review_queue(*, actor, academic_year: str = "", season: str = "", state: str = "", search: str = ""):
    """Koordinatorun növbəsi — YALNIZ göndərilmiş sənədlərin öz sətirləri."""
    specialty_ids = coordinator_specialty_ids(actor)
    if not specialty_ids:
        return TeachingTaskRow.objects.none()
    queryset = (
        TeachingTaskRow.objects.filter(
            organization=actor.organization,
            specialty_id__in=specialty_ids,
            task__status__in=(TaskStatus.SUBMITTED, TaskStatus.PENDING_FINAL_APPROVAL),
        )
        .select_related("subject", "specialty", "faculty", "task", "task__chair", "period")
        .prefetch_related("groups", "reviews")
        .order_by("task__chair__name", "season", "order")
    )
    if academic_year:
        queryset = queryset.filter(task__academic_year=academic_year)
    if season:
        queryset = queryset.filter(season=season)
    if state:
        queryset = queryset.filter(review_status=state)
    if search:
        queryset = queryset.filter(
            Q(subject__name__icontains=search) | Q(subject_text__icontains=search) | Q(groups_text__icontains=search)
        )
    return queryset


def review_counts(*, actor, academic_year: str = "") -> dict:
    """«{done} sətirdən {n}-i baxılıb» göstəricisi + irad sayğacı."""
    queryset = review_queue(actor=actor, academic_year=academic_year)
    counts = queryset.aggregate(
        total=Count("id"),
        reviewed=Count("id", filter=Q(review_status=RowReviewStatus.REVIEWED)),
        flagged=Count("id", filter=Q(review_status=RowReviewStatus.FLAGGED)),
        pending=Count("id", filter=Q(review_status=RowReviewStatus.PENDING)),
    )
    result = {key: int(value or 0) for key, value in counts.items()}
    total = result["total"] or 0
    result["percent"] = int(round((result["reviewed"] + result["flagged"]) * 100 / total)) if total else 0
    return result


def ensure_can_review_row(actor, row) -> None:
    if not actor.has(PERM_REVIEW):
        raise WorkloadDenied("workload.review_denied", "Viza vermək səlahiyyətiniz yoxdur.")
    if row.specialty_id is None or not actor.covers_unit(row.specialty_id, PERM_REVIEW):
        raise WorkloadDenied("workload.review_denied", "Bu sətir sizin ixtisasınıza aid deyil.")
    if row.task.status not in sm.REVIEWABLE:
        raise WorkloadDenied(
            "workload.review_closed",
            "Sənəd viza mərhələsində deyil — sətir işarələnə bilməz.",
        )


@transaction.atomic
def set_row_review(*, row: TeachingTaskRow, actor, status: str, comment: str = "", request=None) -> TaskRowReview:
    """Sətrə viza verir və ya irad yazır (irad `reviewed` bayrağını SİLİR)."""
    ensure_can_review_row(actor, row)
    if status not in {str(value) for value in REVIEW_STATES}:
        raise WorkloadDenied("workload.invalid_review_state", "Viza dəyəri yanlışdır.")

    text = (comment or "").strip()
    if status == RowReviewStatus.FLAGGED:
        # İrad şərhsiz göndərilmir: «Şərh yazılmadan irad göndərilə bilməz.»
        text = ensure_reason(text)

    review, _created = TaskRowReview.objects.update_or_create(
        row=row,
        coordinator=getattr(actor, "user", None),
        defaults={"organization": row.organization, "status": status, "comment": text},
    )
    # Güzgü: sətrin cari vizası. İRAD `reviewed`-i əvəz edir (eyni anda hər
    # ikisi mümkün deyil — handoff §5/13).
    TeachingTaskRow.objects.filter(pk=row.pk).update(review_status=status)
    row.review_status = status

    log_action(
        AuditAction.UPDATE,
        user=getattr(actor, "user", None),
        organization=row.organization,
        obj=review,
        new_values={"status": status, "comment": text},
        reason=(f"workload.row_flagged — {text}" if status == RowReviewStatus.FLAGGED else "workload.row_reviewed"),
        request=request,
        resource_type="workload.TaskRowReview",
        resource_id=str(review.pk),
        resource_repr=row.subject_label,
    )
    return review


@transaction.atomic
def review_all(*, actor, academic_year: str = "", request=None) -> int:
    """«Hamısına viza ver» — İRADI OLMAYAN bütün gözləyən sətirlər."""
    rows = list(review_queue(actor=actor, academic_year=academic_year).filter(review_status=RowReviewStatus.PENDING))
    marked = 0
    for row in rows:
        set_row_review(row=row, actor=actor, status=RowReviewStatus.REVIEWED, request=request)
        marked += 1
    return marked


def row_remarks(rows) -> dict:
    """row_id → iradların siyahısı (dekan ekranı üçün, ekran 15 «Koordinator vizası»)."""
    reviews = (
        TaskRowReview.objects.filter(row_id__in=[row.pk for row in rows])
        .select_related("coordinator")
        .order_by("-created_at")
    )
    result: dict = {}
    for review in reviews:
        bucket = result.setdefault(str(review.row_id), [])
        coordinator = review.coordinator
        bucket.append(
            {
                "status": review.status,
                "comment": review.comment,
                "who": (coordinator.get_full_name() or coordinator.username) if coordinator else "",
                "when": review.created_at,
            }
        )
    return result


__all__ = [
    "REVIEW_STATES",
    "coordinator_specialty_ids",
    "ensure_can_review_row",
    "review_all",
    "review_counts",
    "review_queue",
    "row_remarks",
    "set_row_review",
]
