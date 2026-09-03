"""Ekran 13 «Koordinator — Yük vizası» — OXU qatı.

İki görünüş (dizayn `state.view`): `queue` (default) · `history`.
Koordinator YALNIZ öz ixtisasının sətirlərini görür (§8/4 — əhatəsiz aktor
BOŞ siyahı alır, bütün universitet AÇILMIR).

Göstərici: «{done} sətirdən {n}-i baxılıb» + faiz (dizayn copy-si).
Arxiv rejimi: keçmiş il seçildikdə ekran read-only.
"""

from __future__ import annotations

from .center_registry import current_academic_year, is_archive_year, known_years
from .constants import PERM_REVIEW, RowReviewStatus, Season
from .models import TaskRowReview
from .services import coordinator_specialty_ids, resolve_actor, review_counts, review_queue

VIEWS = ("queue", "history")
PAGE_SIZE = 25


def build_visa(request, organization) -> dict:
    """«Yük vizası» konteksti."""
    actor = resolve_actor(request.user, organization, request=request)
    if not actor.has(PERM_REVIEW):
        return {"has_access": False}

    params = request.GET
    view = params.get("wv_view") or "queue"
    if view not in VIEWS:
        view = "queue"
    years = known_years(organization)
    year = params.get("wv_year") or current_academic_year(organization)
    season = params.get("wv_sem") or ""
    state = params.get("wv_state") or ""
    search = (params.get("wv_q") or "").strip()

    specialty_ids = coordinator_specialty_ids(actor)
    counts = review_counts(actor=actor, academic_year=year)
    queryset = review_queue(actor=actor, academic_year=year, season=season, state=state, search=search)

    total = queryset.count()
    try:
        page = max(int(params.get("wv_page") or 1), 1)
    except (TypeError, ValueError):
        page = 1
    page_count = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = min(page, page_count)
    offset = (page - 1) * PAGE_SIZE
    rows = list(queryset[offset : offset + PAGE_SIZE])

    my_reviews = {
        str(review.row_id): review
        for review in TaskRowReview.objects.filter(row_id__in=[row.pk for row in rows], coordinator=request.user)
    }

    archive = is_archive_year(organization, year)
    return {
        "has_access": True,
        "view": view,
        "year": year,
        "years": years,
        "is_archive": archive,
        "can_write": not archive,
        "has_scope": bool(specialty_ids),
        "counts": counts,
        "rows": [_serialize(row, my_reviews.get(str(row.pk))) for row in rows],
        "row_total": total,
        "page": page,
        "page_count": page_count,
        "filters": {"season": season, "state": state, "search": search},
        "history": _history(request.user, organization, year) if view == "history" else [],
    }


def _serialize(row, review) -> dict:
    return {
        "id": str(row.pk),
        "subject": row.subject_label,
        "groups": row.groups_text or ", ".join(unit.name for unit in row.groups.all()),
        "season": row.season,
        "season_label": str(Season(row.season).label) if row.season in Season.values else row.season,
        "degree_level": row.degree_level,
        "education_form": row.education_form,
        "students": row.student_count,
        "total_hours": row.total_hours,
        "credits": row.credits or (str(row.credits_value) if row.credits_value else ""),
        "chair": row.task.chair.name if row.task.chair_id else "",
        "review_status": row.review_status,
        "is_reviewed": row.review_status == RowReviewStatus.REVIEWED,
        "is_flagged": row.review_status == RowReviewStatus.FLAGGED,
        "my_comment": review.comment if review is not None else "",
        "activities": {
            "lecture": {"plan": row.lecture_plan, "total": row.lecture_total},
            "seminar": {"plan": row.seminar_plan, "total": row.seminar_total},
            "lab": {"plan": row.lab_plan, "total": row.lab_total},
        },
    }


def _history(user, organization, year: str) -> list[dict]:
    """«Mənim hərəkətlərim» — koordinatorun öz viza/irad yazıları."""
    queryset = (
        TaskRowReview.objects.filter(organization=organization, coordinator=user)
        .select_related("row", "row__subject", "row__task")
        .order_by("-created_at")
    )
    if year:
        queryset = queryset.filter(row__task__academic_year=year)
    return [
        {
            "id": str(review.pk),
            "subject": review.row.subject_label,
            "status": review.status,
            "comment": review.comment,
            "when": review.created_at,
        }
        for review in queryset[:100]
    ]


__all__ = ["PAGE_SIZE", "VIEWS", "build_visa"]
