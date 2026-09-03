"""Ekran 15 «Dekanlıq — Yük təsdiqi» — OXU qatı.

Üç görünüş (dizayn `state.view`): `queue` · `summary` (fakültə yekunu) ·
`history` (zəncir hadisələri timeline kimi).

Dekan YALNIZ öz fakültəsinin dilimlərini görür (``workload.approve`` əhatəsi).
Toplu «Qaytar» ≥1 sətir seçildikdə aktivdir; hər iki əməl səbəb dialoqundan
keçir (≥20 simvol, auditli).

⚠️ Fakültə/universitet yekunları SAXLANILMIR — hər sorğuda kafedra
sətirlərindən hesablanır (§8/13).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Count, Q, Sum

from core.constants import OrgUnitType

from .center_registry import current_academic_year, is_archive_year, known_years, safe_uuid
from .constants import PERM_APPROVE, RowReviewStatus, Season, SliceStatus
from .models import TaskFacultySlice, TeachingTaskRow
from .services import resolve_actor, row_remarks

VIEWS = ("queue", "summary", "history")
PAGE_SIZE = 25


def visible_faculties(actor):
    """Dekanın əhatəsindəki fakültələr (fail-closed)."""
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    if not actor.has(PERM_APPROVE):
        return OrgUnit.objects.none()
    base = OrgUnit.objects.filter(organization=actor.organization, unit_type=OrgUnitType.FACULTY, is_active=True)
    scope = actor.scope_for(PERM_APPROVE)
    if scope.is_org_wide:
        return base.order_by("name")
    if not scope.has_structure_access:
        return OrgUnit.objects.none()
    return base.filter(scope.unit_subtree_q()).order_by("name")


def build_approval(request, organization) -> dict:
    """«Yük təsdiqi» konteksti."""
    actor = resolve_actor(request.user, organization, request=request)
    if not actor.has(PERM_APPROVE):
        return {"has_access": False}

    params = request.GET
    view = params.get("wa_view") or "queue"
    if view not in VIEWS:
        view = "queue"
    years = known_years(organization)
    year = params.get("wa_year") or current_academic_year(organization)
    faculties = list(visible_faculties(actor))
    faculty_id = safe_uuid(params.get("wa_faculty")) or (str(faculties[0].pk) if faculties else "")

    slices = list(
        TaskFacultySlice.objects.filter(
            organization=organization,
            faculty_id=faculty_id,
            task__academic_year=year,
        )
        .select_related("task", "task__chair", "faculty", "decided_by")
        .order_by("task__chair__name", "-revision")
        if faculty_id
        else []
    )
    current = [item for item in slices if item.revision == item.task.revision]
    pending = [item for item in current if item.status == SliceStatus.PENDING]

    slice_id = safe_uuid(params.get("wa_slice")) or (
        str(pending[0].pk) if pending else (str(current[0].pk) if current else "")
    )
    active = next((item for item in current if str(item.pk) == slice_id), None)

    archive = is_archive_year(organization, year)
    payload = {
        "has_access": True,
        "view": view,
        "year": year,
        "years": years,
        "is_archive": archive,
        "can_write": not archive,
        "faculty_id": faculty_id,
        "faculty_options": [{"value": str(unit.pk), "label": unit.name} for unit in faculties],
        "slice_cards": [
            {
                "id": str(item.pk),
                "chair": item.task.chair.name if item.task.chair_id else "",
                "status": item.status,
                "status_key": "sent" if item.status == SliceStatus.PENDING else item.status,
                "revision": item.revision,
                "comment": item.comment,
                "decided_at": item.decided_at,
            }
            for item in current
        ],
        "pending_count": len(pending),
        "slice": None,
        "rows": [],
        "row_total": 0,
        "page": 1,
        "page_count": 1,
        "kpi": {"hours": 0, "credits": 0, "specialties": 0, "flagged": 0},
        "summary": _summary(organization, faculty_id, year) if view == "summary" else [],
        "history": _history(organization, faculty_id, year) if view == "history" else [],
        "filters": {
            "season": params.get("wa_sem") or "",
            "visa": params.get("wa_visa") or "",
            "specialty": safe_uuid(params.get("wa_spec")),
        },
    }
    if active is None:
        return payload

    payload["slice"] = {
        "id": str(active.pk),
        "chair": active.task.chair.name if active.task.chair_id else "",
        "faculty": active.faculty.name,
        "status": active.status,
        # `workload_line` ailəsi üç pill saxlayır: `pending` → «sent».
        "status_key": "sent" if active.status == SliceStatus.PENDING else active.status,
        "revision": active.revision,
        "comment": active.comment,
        "task_id": str(active.task_id),
        "is_open": active.status == SliceStatus.PENDING,
    }

    queryset = (
        TeachingTaskRow.objects.filter(task=active.task, faculty_id=active.faculty_id)
        .select_related("subject", "specialty")
        .prefetch_related("groups")
        .order_by("season", "order")
    )
    if payload["filters"]["season"]:
        queryset = queryset.filter(season=payload["filters"]["season"])
    if payload["filters"]["visa"]:
        queryset = queryset.filter(review_status=payload["filters"]["visa"])
    if payload["filters"]["specialty"]:
        queryset = queryset.filter(specialty_id=payload["filters"]["specialty"])

    aggregate = TeachingTaskRow.objects.filter(task=active.task, faculty_id=active.faculty_id).aggregate(
        hours=Sum("total_hours"),
        credits=Sum("credits_value"),
        specialties=Count("specialty_id", distinct=True),
        flagged=Count("id", filter=Q(review_status=RowReviewStatus.FLAGGED)),
    )
    payload["kpi"] = {
        "hours": int(aggregate["hours"] or 0),
        "credits": int(aggregate["credits"] or 0),
        "specialties": int(aggregate["specialties"] or 0),
        "flagged": int(aggregate["flagged"] or 0),
    }

    total = queryset.count()
    try:
        page = max(int(params.get("wa_page") or 1), 1)
    except (TypeError, ValueError):
        page = 1
    page_count = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = min(page, page_count)
    offset = (page - 1) * PAGE_SIZE
    rows = list(queryset[offset : offset + PAGE_SIZE])
    remarks = row_remarks(rows)

    payload["rows"] = [
        {
            "id": str(row.pk),
            "subject": row.subject_label,
            "specialty": row.specialty.name if row.specialty_id else row.specialty_text,
            "groups": row.groups_text or ", ".join(unit.name for unit in row.groups.all()),
            "season": row.season,
            "season_label": str(Season(row.season).label) if row.season in Season.values else row.season,
            "total_hours": row.total_hours,
            "credits": row.credits or (str(row.credits_value) if row.credits_value else ""),
            "review_status": row.review_status,
            "remarks": remarks.get(str(row.pk), []),
        }
        for row in rows
    ]
    payload["row_total"] = total
    payload["page"] = page
    payload["page_count"] = page_count
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    specialty_ids = (
        TeachingTaskRow.objects.filter(task=active.task, faculty_id=active.faculty_id, specialty__isnull=False)
        .values_list("specialty_id", flat=True)
        .distinct()
    )
    payload["specialty_options"] = [
        {"value": str(unit.pk), "label": unit.name}
        for unit in OrgUnit.objects.filter(pk__in=list(specialty_ids)).order_by("name")
    ]
    return payload


def _summary(organization, faculty_id, year: str) -> list[dict]:
    """Kafedralar üzrə yekun — AŞAĞIDAN YUXARI hesablanır, saxlanılmır."""
    if not faculty_id:
        return []
    rows = (
        TeachingTaskRow.objects.filter(organization=organization, faculty_id=faculty_id, task__academic_year=year)
        .values("task__chair__name", "task__status")
        .annotate(
            rows=Count("id"),
            hours=Sum("total_hours"),
            credits=Sum("credits_value"),
            specialties=Count("specialty_id", distinct=True),
        )
        .order_by("task__chair__name")
    )
    return [
        {
            "chair": item["task__chair__name"] or "—",
            "status": item["task__status"],
            "rows": int(item["rows"] or 0),
            "hours": int(item["hours"] or 0),
            "credits": int(item["credits"] or 0),
            "specialties": int(item["specialties"] or 0),
        }
        for item in rows
    ]


def _history(organization, faculty_id, year: str) -> list[dict]:
    """Zəncir hadisələri — dilim qərarları (timeline)."""
    if not faculty_id:
        return []
    queryset = (
        TaskFacultySlice.objects.filter(organization=organization, faculty_id=faculty_id, task__academic_year=year)
        .exclude(status=SliceStatus.PENDING)
        .select_related("task", "task__chair", "decided_by")
        .order_by("-decided_at")
    )
    return [
        {
            "who": (item.decided_by.get_full_name() or item.decided_by.username) if item.decided_by_id else "—",
            "when": item.decided_at,
            "what": item.task.chair.name if item.task.chair_id else "",
            "status": item.status,
            "reason": item.comment,
        }
        for item in queryset[:100]
    ]


__all__ = ["PAGE_SIZE", "VIEWS", "build_approval", "visible_faculties"]
