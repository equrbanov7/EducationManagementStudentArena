"""Oxu tərəfi: istifadəçinin elan siyahısı (axtarış, filtr, sıralama, səhifələmə), detal, sayğac.

Sorğu büdcəsi (bir səhifə): say + sətirlər + qəbzlər + (tələbə üçün) akademik qeyd = 3–4 sorğu,
elan sayından asılı deyil. Klientdən gələn hər parametr ağ siyahı ilə süzülür.
"""

from __future__ import annotations

import datetime
import math
import uuid
from dataclasses import dataclass

from django.db.models import Case, Exists, F, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone

from core.search_text import tolerant_q

from ..constants import PAGE_SIZE, SORTS, UNREAD_WINDOW_DAYS, USER_STATES, Category, Status
from ..models import Announcement, AnnouncementReceipt
from .audience import Viewer, visible_q


@dataclass(frozen=True)
class ListParams:
    q: str = ""
    category: str = ""
    state: str = "active"
    sort: str = "new"
    unread: bool = False
    has_deadline: bool = False
    page: int = 1

    @classmethod
    def from_query(cls, data) -> ListParams:
        def _pick(key, allowed, default):
            value = str(data.get(key) or "").strip()
            return value if value in allowed else default

        try:
            page = max(1, min(int(data.get("page") or 1), 1000))
        except (TypeError, ValueError):
            page = 1
        return cls(
            q=str(data.get("q") or "").strip()[:100],
            category=_pick("category", set(Category.values), ""),
            state=_pick("state", set(USER_STATES), "active"),
            sort=_pick("sort", set(SORTS), "new"),
            unread=str(data.get("unread") or "") in ("1", "true", "on"),
            has_deadline=str(data.get("deadline") or "") in ("1", "true", "on"),
            page=page,
        )

    def as_query(self) -> dict:
        return {
            "q": self.q,
            "category": self.category,
            "state": self.state,
            "sort": self.sort,
            "unread": "1" if self.unread else "",
            "deadline": "1" if self.has_deadline else "",
        }


def published_for(organization, viewer: Viewer, now=None):
    """Dərc olunmuş, başlamış, istifadəçiyə ünvanlanmış elanlar (müddəti bitmişlər də daxil)."""
    now = now or timezone.now()
    return Announcement.objects.filter(organization=organization, status=Status.PUBLISHED, publish_at__lte=now).filter(
        visible_q(viewer)
    )


def _active_q(now) -> Q:
    return Q(expires_at__isnull=True) | Q(expires_at__gt=now)


def _read_exists(user):
    return Exists(AnnouncementReceipt.objects.filter(announcement=OuterRef("pk"), user=user, read_at__isnull=False))


def _applied_exists(user):
    return Exists(
        AnnouncementReceipt.objects.filter(announcement=OuterRef("pk"), user=user, applied_at__isnull=False)
    )


def search_q(text: str) -> Q:
    query = tolerant_q(text, ("title", "summary", "body"))
    return Q() if query is None else query


def user_list(organization, user, viewer: Viewer, params: ListParams, now=None) -> dict:
    now = now or timezone.now()
    queryset = published_for(organization, viewer, now)
    if params.state == "active":
        queryset = queryset.filter(_active_q(now))
    elif params.state == "expired":
        queryset = queryset.filter(expires_at__lte=now)
    if params.category:
        queryset = queryset.filter(category=params.category)
    if params.has_deadline:
        queryset = queryset.filter(deadline_at__isnull=False)
    if params.q:
        queryset = queryset.filter(search_q(params.q))
    queryset = queryset.annotate(is_read=_read_exists(user), is_applied=_applied_exists(user))
    if params.unread:
        queryset = queryset.filter(is_read=False)

    pinned = Case(
        When(Q(is_pinned=True) & _active_q(now), then=Value(1)), default=Value(0), output_field=IntegerField()
    )
    queryset = queryset.annotate(pin_rank=pinned)
    if params.sort == "deadline":
        # Yaxın son tarix birinci; keçmiş son tarixlər və son tarixsizlər sonda.
        upcoming = Case(When(deadline_at__gt=now, then=Value(0)), default=Value(1), output_field=IntegerField())
        queryset = queryset.annotate(deadline_rank=upcoming).order_by(
            "-pin_rank", "deadline_rank", F("deadline_at").asc(nulls_last=True), "-publish_at"
        )
    elif params.sort == "priority":
        queryset = queryset.order_by("-pin_rank", "-priority", "-publish_at")
    else:
        queryset = queryset.order_by("-pin_rank", "-publish_at", "-created_at")

    total = queryset.count()
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(params.page, pages)
    start = (page - 1) * PAGE_SIZE
    rows = list(queryset.prefetch_related("attachments")[start : start + PAGE_SIZE]) if total else []
    for row in rows:
        decorate(row, now)
    return {"items": rows, "total": total, "page": page, "pages": pages, "params": params}


def receipt_for(announcement, user):
    return AnnouncementReceipt.objects.filter(announcement=announcement, user=user).first()


def get_visible(organization, viewer: Viewer, announcement_id, now=None):
    """Detal: ünvanlanmış dərc olunmuş elan (müddəti bitmiş də oxunur); tapılmasa/görünməsə ``None``."""
    try:
        pk = uuid.UUID(str(announcement_id))
    except (TypeError, ValueError, AttributeError):
        return None
    row = (
        published_for(organization, viewer, now)
        .filter(pk=pk)
        .select_related("apply_kind", "apply_unit")
        .prefetch_related("attachments")
        .first()
    )
    if row is not None:
        decorate(row, now or timezone.now())
    return row


def unread_count(organization, user, viewer: Viewer, now=None) -> int:
    """Aktiv, son ``UNREAD_WINDOW_DAYS`` gündə dərc olunmuş, oxunmamış elan sayı."""
    now = now or timezone.now()
    since = now - datetime.timedelta(days=UNREAD_WINDOW_DAYS)
    return (
        published_for(organization, viewer, now)
        .filter(_active_q(now), publish_at__gte=since)
        .exclude(
            Exists(AnnouncementReceipt.objects.filter(announcement=OuterRef("pk"), user=user, read_at__isnull=False))
        )
        .count()
    )


def deadline_info(deadline_at, now) -> dict | None:
    """Son tarix çipi: ``overdue`` / ``today`` / ``soon`` (≤ 3 gün) / ``later`` + qalan gün."""
    if not deadline_at:
        return None
    local_deadline = timezone.localtime(deadline_at)
    days = (local_deadline.date() - timezone.localtime(now).date()).days
    if deadline_at <= now:
        state = "overdue"
    elif days == 0:
        state = "today"
    elif days <= 3:
        state = "soon"
    else:
        state = "later"
    return {"at": local_deadline, "days": max(days, 0), "state": state, "iso": local_deadline.isoformat()}


def decorate(row, now) -> None:
    """Şablon üçün hesablanmış sahələr (DB-yə getmir)."""
    row.state = row.effective_state(now)
    row.deadline = deadline_info(row.deadline_at, now)
    fresh = row.publish_at and row.publish_at >= now - datetime.timedelta(days=UNREAD_WINDOW_DAYS)
    row.is_new = bool(fresh and not getattr(row, "is_read", True) and row.state == "active")


__all__ = [
    "ListParams",
    "deadline_info",
    "decorate",
    "get_visible",
    "published_for",
    "receipt_for",
    "search_q",
    "unread_count",
    "user_list",
]
