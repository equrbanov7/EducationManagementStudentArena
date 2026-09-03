"""Siyahı, filtr, axtarış və KPI sorğuları — hamısı SERVER tərəfdə."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from ..constants import CLOSED_STATUSES, OPEN_STATUSES, ApplicationStatus
from ..models import Application
from ..sla import working_days_between
from . import access

TABS = ("mine", "inbox", "watching", "archive")
STATS = ("open", "overdue", "closed", "all")


def base_queryset(organization):
    return Application.objects.filter(organization=organization).select_related(
        "kind", "current_unit", "current_scope_unit", "created_by", "assigned_to"
    )


def _tab_q(user, organization, tab: str) -> Q:
    if tab == "mine":
        return Q(created_by=user)
    if tab == "inbox":
        return access.inbox_q(user, organization)
    if tab == "watching":
        return access.watching_q(user, organization)
    # archive = görünən hər şey, yalnız bağlı statuslar
    return access.visible_q(user, organization) & Q(status__in=CLOSED_STATUSES)


def _stat_q(stat: str) -> Q:
    if stat == "open":
        return Q(status__in=OPEN_STATUSES)
    if stat == "closed":
        return Q(status__in=CLOSED_STATUSES)
    if stat == "overdue":
        return Q(status__in=OPEN_STATUSES) & Q(sla_due_on__lt=timezone.localdate())
    return Q()


def search_q(text: str) -> Q:
    cleaned = (text or "").strip()
    if not cleaned:
        return Q()
    return (
        Q(subject__icontains=cleaned)
        | Q(number__icontains=cleaned)
        | Q(created_by__first_name__icontains=cleaned)
        | Q(created_by__last_name__icontains=cleaned)
        | Q(created_by__username__icontains=cleaned)
    )


def list_applications(*, organization, user, tab="mine", stat="open", kind_code="", search=""):
    """Filtrlənmiş siyahı. Görünüş qapısı HƏMİŞƏ tətbiq olunur."""
    tab = tab if tab in TABS else "mine"
    stat = stat if stat in STATS else "open"
    queryset = base_queryset(organization).filter(_tab_q(user, organization, tab))
    if tab != "archive":
        queryset = queryset.filter(_stat_q(stat))
    if kind_code:
        queryset = queryset.filter(kind__code=kind_code)
    queryset = queryset.filter(search_q(search))
    return queryset.distinct()


def _count(queryset) -> int:
    return queryset.distinct().count()


def sender_kpis(*, organization, user) -> dict:
    mine = base_queryset(organization).filter(created_by=user)
    resolved = mine.filter(status__in=[ApplicationStatus.RESOLVED, ApplicationStatus.CLOSED])
    durations = [
        working_days_between(app.submitted_at.date(), app.resolved_at.date())
        for app in resolved.exclude(resolved_at__isnull=True)
    ]
    average = round(sum(durations) / len(durations), 1) if durations else 0.0
    return {
        "open": _count(mine.filter(status__in=OPEN_STATUSES)),
        "waiting_info": _count(mine.filter(status=ApplicationStatus.WAITING_INFO)),
        "resolved": _count(resolved),
        "avg_response_days": average,
    }


def handler_kpis(*, organization, user) -> dict:
    inbox = base_queryset(organization).filter(access.inbox_q(user, organization))
    watching = base_queryset(organization).filter(access.watching_q(user, organization))
    return {
        "inbox_open": _count(inbox.filter(status__in=OPEN_STATUSES)),
        "new_unseen": _count(inbox.filter(status=ApplicationStatus.SUBMITTED)),
        "overdue": _count(inbox.filter(status__in=OPEN_STATUSES, sla_due_on__lt=timezone.localdate())),
        "watching": _count(watching.filter(status__in=OPEN_STATUSES)),
    }


def tab_counts(*, organization, user) -> dict:
    """Tab başlıqlarındakı sayğaclar (açıq müraciətlər)."""
    counts = {}
    for tab in ("mine", "inbox", "watching"):
        queryset = base_queryset(organization).filter(_tab_q(user, organization, tab))
        counts[tab] = _count(queryset.filter(status__in=OPEN_STATUSES))
    counts["archive"] = _count(base_queryset(organization).filter(_tab_q(user, organization, "archive")))
    return counts


__all__ = [
    "STATS",
    "TABS",
    "base_queryset",
    "handler_kpis",
    "list_applications",
    "search_q",
    "sender_kpis",
    "tab_counts",
]
