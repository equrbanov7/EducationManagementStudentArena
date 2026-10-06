"""Siyahı, filtr, axtarış və KPI sorğuları — hamısı SERVER tərəfdə."""

from __future__ import annotations

from django.db.models import Count, Q
from django.utils import timezone

from core.search_text import tolerant_q

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
    """Dözümlü axtarış (``core.search_text``): mövzu/ad az/ing hərfinə, nömrə ayırıcıya dözümlü; boş → ``Q()``."""
    query = tolerant_q(
        text,
        ("subject", "created_by__first_name", "created_by__last_name", "created_by__username"),
        compact_fields=("number",),
    )
    return Q() if query is None else query


def date_q(date_from=None, date_to=None) -> Q:
    """GÖNDƏRİLMƏ tarixi üzrə aralıq (hər iki uc DAXİLDİR).

    Meyar ``submitted_at``-dır, ``last_activity_at`` deyil: istifadəçi «filan
    tarixlərdə göndərdiyim müraciətlər» axtarır — sonrakı yazışma sətri onu
    aralıqdan çıxarmamalıdır.

    Uclar səhv sıra ilə gəlsə (başlanğıc > son) YER DƏYİŞİR: boş nəticə əvəzinə
    istifadəçinin nəzərdə tutduğu aralıq qaytarılır.
    """
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    query = Q()
    if date_from:
        query &= Q(submitted_at__date__gte=date_from)
    if date_to:
        query &= Q(submitted_at__date__lte=date_to)
    return query


def list_applications(
    *, organization, user, tab="mine", stat="open", kind_code="", search="", date_from=None, date_to=None
):
    """Filtrlənmiş siyahı. Görünüş qapısı HƏMİŞƏ tətbiq olunur."""
    tab = tab if tab in TABS else "mine"
    stat = stat if stat in STATS else "open"
    queryset = base_queryset(organization).filter(_tab_q(user, organization, tab))
    if tab != "archive":
        queryset = queryset.filter(_stat_q(stat))
    if kind_code:
        queryset = queryset.filter(kind__code=kind_code)
    queryset = queryset.filter(search_q(search)).filter(date_q(date_from, date_to))
    return queryset.distinct()


_RESOLVED_STATUSES = (ApplicationStatus.RESOLVED, ApplicationStatus.CLOSED)


def _count(queryset) -> int:
    """Çox-qiymətli JOIN-li (``watches``) filtr üçün say — DISTINCT YALNIZ pk üzrə.

    Tutum 2026-10-07: əvvəl ``queryset.distinct().count()`` bütün ~20 sütun üzrə
    ``SELECT DISTINCT`` alt-sorğusu verirdi; pk unikal olduğu üçün say eynidir.
    """
    return queryset.values("pk").distinct().count()


def _aggregate_counts(queryset, **filters) -> dict:
    """Bir neçə şərtli sayı TƏK sorğuda — yalnız sətir TƏKRARLAMAYAN filtrlər üçün."""
    totals = queryset.aggregate(**{key: Count("pk", filter=condition) for key, condition in filters.items()})
    return {key: int(totals.get(key) or 0) for key in filters}


def sender_counts(*, organization, user) -> dict:
    """Göndərənin sayğacları — TƏK aqreqat sorğu (əvvəl 3 ayrı ``COUNT(DISTINCT …)``).

    ``created_by`` sətir təkrarlamır (çox-qiymətli JOIN yoxdur) → ``DISTINCT``-siz
    say əvvəlki ilə eynidir.
    """
    return _aggregate_counts(
        Application.objects.filter(organization=organization, created_by=user),
        open=Q(status__in=OPEN_STATUSES),
        waiting_info=Q(status=ApplicationStatus.WAITING_INFO),
        resolved=Q(status__in=_RESOLVED_STATUSES),
    )


def sender_kpis(*, organization, user) -> dict:
    resolved = base_queryset(organization).filter(created_by=user, status__in=_RESOLVED_STATUSES)
    durations = [
        working_days_between(app.submitted_at.date(), app.resolved_at.date())
        for app in resolved.exclude(resolved_at__isnull=True)
    ]
    average = round(sum(durations) / len(durations), 1) if durations else 0.0
    counts = sender_counts(organization=organization, user=user)
    return {
        "open": counts["open"],
        "waiting_info": counts["waiting_info"],
        "resolved": counts["resolved"],
        "avg_response_days": average,
    }


def handler_inbox_counts(*, organization, user) -> dict:
    """Emalçının «Gələnlər» sayğacları — TƏK aqreqat sorğu.

    ``inbox_q`` yalnız tək-qiymətli FK-lardan (``current_unit``,
    ``current_scope_unit``) ibarətdir — sətir təkrarlanmır, ``DISTINCT`` lazım deyil.
    """
    open_q = Q(status__in=OPEN_STATUSES)
    return _aggregate_counts(
        Application.objects.filter(organization=organization).filter(access.inbox_q(user, organization)),
        inbox_open=open_q,
        new_unseen=Q(status=ApplicationStatus.SUBMITTED),
        overdue=open_q & Q(sla_due_on__lt=timezone.localdate()),
    )


def handler_kpis(*, organization, user) -> dict:
    watching = base_queryset(organization).filter(access.watching_q(user, organization))
    return {
        **handler_inbox_counts(organization=organization, user=user),
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
    "date_q",
    "handler_inbox_counts",
    "handler_kpis",
    "list_applications",
    "search_q",
    "sender_counts",
    "sender_kpis",
    "tab_counts",
]
