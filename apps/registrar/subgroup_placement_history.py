"""«Alt qrupa yerləşdirmə» TARİXÇƏSİ — alətin «Son yerləşdirmələr» siyahısı və tələbə izi (2026-10-18).

Sahib (2026-09-07): «alt qrupa yazılıbsa onun da tarixçəsi qalsın, biz də bilək» — koordinator / dekanlıq
tələbənin izində hər yerləşdirməni (kim, nə vaxt, hansı sənədlə, hansı səbəblə, kredit əvvəl/sonra) və geri
götürmələri görür. Oxu-only; sorğu sayı sətir sayından asılı deyil (``select_related`` + bir «geri götürülüb»
xəritəsi).
"""

from __future__ import annotations

from django.utils import timezone

from core.media_urls import protected_media_url
from core.search_text import tolerant_q

from . import subgroup_access as access
from .models import SubgroupPlacementEvent, SubgroupPlacementKind

PAGE_SIZE = 20
MAX_PAGE_SIZE = 50

_RELATED = (
    "offering__subject",
    "offering__period",
    "offering__group",
    "student",
    "source_group",
    "target_group",
    "document",
)


def _name(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def _when(value) -> str:
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M") if value else ""


def _undo_map(place_ids) -> dict:
    ids = [value for value in place_ids if value]
    if not ids:
        return {}
    rows = SubgroupPlacementEvent.objects.filter(kind=SubgroupPlacementKind.UNDO, undoes_id__in=ids).order_by(
        "created_at"
    )
    return {row.undoes_id: row for row in rows}


def serialize(event, *, undo=None) -> dict:
    offering = event.offering
    document = event.document
    return {
        "id": str(event.pk),
        "kind": event.kind,
        "kind_label": str(event.get_kind_display()),
        "student_id": event.student_id,
        "student": _name(event.student),
        "subject_code": offering.subject.code,
        "subject_name": offering.subject.name,
        "period": f"{offering.period.year_display} · {offering.period.name}",
        "source_group": getattr(event.source_group, "name", "") or "",
        "target_group": getattr(event.target_group, "name", "") or "",
        "order_number": event.order_number,
        "order_date": event.order_date.strftime("%d.%m.%Y") if event.order_date else "",
        "document_url": protected_media_url(document.document) if document is not None else "",
        "reason": event.reason,
        "credits_before": event.credits_before,
        "credits_after": event.credits_after,
        "credit_limit": event.credit_limit,
        "clash_count": len((event.details or {}).get("clashes") or []),
        "retake": bool((event.details or {}).get("retake")),
        "actor": event.actor_name,
        "created_at": _when(event.created_at),
        "undone": undo is not None,
        "undo": (
            {"actor": undo.actor_name, "created_at": _when(undo.created_at), "reason": undo.reason}
            if undo is not None
            else None
        ),
    }


def recent_placements(*, actor, organization, q: str = "", offset: int = 0, limit: int = PAGE_SIZE) -> dict:
    """Aktorun əhatəsindəki son yerləşdirmələr (ən yenisi birinci) + geri götürmə izi."""
    limit = max(1, min(int(limit or PAGE_SIZE), MAX_PAGE_SIZE))
    offset = max(0, int(offset or 0))
    queryset = SubgroupPlacementEvent.objects.filter(organization=organization, kind=SubgroupPlacementKind.PLACE)
    if not access.is_org_wide(actor, organization):
        queryset = queryset.filter(source_group__in=access.scoped_groups(actor, organization))
    search = tolerant_q(
        q,
        ("student__first_name", "student__last_name", "student__username", "offering__subject__name", "order_number"),
    )
    if search is not None:
        queryset = queryset.filter(search)
    window = list(queryset.select_related(*_RELATED).order_by("-created_at")[offset : offset + limit + 1])
    rows = window[:limit]
    undo = _undo_map([row.pk for row in rows])
    return {"results": [serialize(row, undo=undo.get(row.pk)) for row in rows], "has_more": len(window) > limit}


def student_placements(*, student, organization) -> list:
    """Bir tələbənin BÜTÜN yerləşdirmələri (tələbə izi — reyestr çekməcəsi)."""
    rows = list(
        SubgroupPlacementEvent.objects.filter(
            organization=organization, student=student, kind=SubgroupPlacementKind.PLACE
        )
        .select_related(*_RELATED)
        .order_by("-created_at")
    )
    undo = _undo_map([row.pk for row in rows])
    return [serialize(row, undo=undo.get(row.pk)) for row in rows]


__all__ = ["PAGE_SIZE", "recent_placements", "serialize", "student_placements"]
