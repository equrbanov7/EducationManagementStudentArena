"""Dəqiqləşdirmə növbəsinin OXU endpoint-ləri (JSON).

Üç fərqli yenilənmə tezliyi, üç endpoint (``handover`` naxışı):

* ``legacy_review_queue``   — cədvəl sətirləri + irəliləyiş + kateqoriya sayları;
* ``legacy_review_options`` — nadir dəyişən süzgəc açılışları (dövr, status, şiddət);
* ``legacy_review_lookup``  — axtarışlı/səhifələnən seçicilər (struktur, fənn, müəllim).

Hamısı fail-closed: icazəsiz aktor ``has_access: false`` və BOŞ data alır — nə
sətir, nə sayğac, nə də ad sızır.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.registrar import legacy_grade_review as review_read
from apps.registrar import legacy_grade_review_counts as counts_read
from apps.registrar import legacy_grade_review_rows as rows_read

from .policy import resolve_actor

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
LOOKUP_LIMIT = 20
MAX_LOOKUP_LIMIT = 50

#: Süzgəc açarları — allow-list; naməlum GET parametri SƏSSİZCƏ nəzərə alınmır.
FILTER_KEYS = (
    "faculty",
    "kafedra",
    "specialty",
    "group",
    "subject",
    "teacher",
    "period",
    "year",
    "severity",
    "status",
    "q",
)

_EMPTY_QUEUE = {
    "has_access": False,
    "results": [],
    "page": 1,
    "num_pages": 1,
    "total": 0,
    "has_next": False,
    "has_previous": False,
    "progress": {"total": 0, "reviewed": 0, "pending": 0, "percent": 0},
    "categories": [],
    "can_review": False,
}


def _int(value, default, *, minimum=1, maximum=None):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if number < minimum:
        return default
    if maximum is not None and number > maximum:
        return maximum
    return number


def _filters(request) -> dict:
    filters = {key: (request.GET.get(key) or "").strip() for key in FILTER_KEYS}
    filters["categories"] = [code for code in request.GET.getlist("category") if code]
    return filters


@never_cache
@login_required
@require_GET
def legacy_review_queue(request):
    """Baxış tələb edən köhnə imtahan nəticələri — səhifələnmiş cədvəl."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse(_EMPTY_QUEUE)

    filters = _filters(request)
    queryset = review_read.review_queue(
        organization=actor.organization,
        user=actor.user,
        categories=filters["categories"],
        filters=filters,
    )
    prepared = rows_read.order_by_severity(
        rows_read.prepared_page_queryset(queryset, actor.organization),
        actor.organization,
    )
    # İrəliləyiş və bütün kateqoriya çipləri BİR aqreqat sorğudan gəlir.
    counts = counts_read.queue_counts(
        organization=actor.organization,
        user=actor.user,
        filters=filters,
    )
    size = _int(request.GET.get("page_size"), DEFAULT_PAGE_SIZE, maximum=MAX_PAGE_SIZE)
    paginator = _paginator(prepared, size, filters, counts)
    page = paginator.get_page(_int(request.GET.get("page"), 1))
    return JsonResponse(
        {
            "has_access": True,
            "can_review": actor.can_review,
            "results": rows_read.serialize_page(page.object_list, actor.organization, can_correct=actor.can_review),
            "page": page.number,
            "num_pages": paginator.num_pages,
            "total": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
            "progress": counts["progress"],
            "categories": counts["categories"],
        }
    )


def _paginator(prepared, size, filters, counts):
    """Səhifələyici — məlum olduqda öz ``COUNT``-unu təkrar ETMİR.

    ``Paginator.count`` növbənin bütün süzgəclərlə ölçüsüdür; irəliləyiş
    məxrəci isə eyni ölçüdür, sadəcə status süzgəci OLMADAN. Deməli status
    seçilməyibsə iki rəqəm TƏRİFƏ GÖRƏ eynidir və ikinci dəfə saymağa ehtiyac
    yoxdur (169 min sətirlik cədvəldə bu, bir tam skan deməkdir).

    Status seçiləndə isə bazalar ayrılır — orada ``Paginator`` öz sayını özü
    edir, yəni doğruluq «bilirik deyə» qısaldılmır.
    """
    paginator = Paginator(prepared, size)
    if not filters.get("status"):
        paginator.count = counts["progress"]["total"]
    return paginator


@never_cache
@login_required
@require_GET
def legacy_review_options(request):
    """Dövr, status və şiddət açılışları — nadir dəyişir, ayrıca keşlənə bilər."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse({"has_access": False, "periods": [], "years": [], "statuses": [], "severities": []})

    from django.apps import apps as django_apps

    academic_period = django_apps.get_model("organizations", "AcademicPeriod")
    periods, years, seen = [], [], set()
    for period in academic_period.objects.filter(organization=actor.organization).order_by("-start_date")[:60]:
        periods.append({"id": str(period.pk), "label": period.name})
        label = getattr(period, "year_display", "") or ""
        if label and label not in seen:
            seen.add(label)
            years.append(label)
    return JsonResponse(
        {
            "has_access": True,
            "periods": periods,
            "years": years,
            "statuses": [{"id": code, "label": str(label)} for code, label in review_read.STATUS_LABELS.items()],
            "severities": [
                {"id": code, "label": str(review_read.SEVERITY_LABELS[code])} for code in review_read.SEVERITY_ORDER
            ],
        }
    )


# ── Axtarışlı seçicilər ──────────────────────────────────────────────────────
#
# `EMSSearchableSelect` müqaviləsi: `?q=&limit=&offset=&<dependParam>=` →
# `{results: [{id, text}], has_more: bool}`. Debounce, lazy səhifələmə və
# kaskad ön tərəfdədir; server yalnız daralda bilən sorğu verir.


def _lookup_window(request):
    limit = _int(request.GET.get("limit"), LOOKUP_LIMIT, maximum=MAX_LOOKUP_LIMIT)
    offset = _int(request.GET.get("offset"), 0, minimum=0)
    return limit, offset


def _lookup_payload(queryset, request, to_row):
    """Bir səhifə + ``has_more`` (limit+1 oxuma ilə, ayrıca COUNT olmadan)."""
    limit, offset = _lookup_window(request)
    window = list(queryset[offset : offset + limit + 1])
    return JsonResponse(
        {
            "results": [to_row(item) for item in window[:limit]],
            "has_more": len(window) > limit,
        }
    )


_EMPTY_LOOKUP = {"results": [], "has_more": False}

#: Kaskadın pillələri: hansı vahid tipi, valideyni hansı GET parametridir.
_UNIT_STEPS = {
    "faculty": ("FACULTY", ""),
    "kafedra": ("CHAIR", "faculty"),
    "specialty": ("SPECIALTY", "kafedra"),
}


@never_cache
@login_required
@require_GET
def legacy_review_units(request, kind):
    """Fakültə → kafedra → ixtisas kaskadı (valideyn seçimi ilə daralır)."""
    actor = resolve_actor(request)
    if not actor.has_access or kind not in _UNIT_STEPS:
        return JsonResponse(_EMPTY_LOOKUP)

    from django.apps import apps as django_apps

    from core.constants import OrgUnitType

    org_unit = django_apps.get_model("organizations", "OrgUnit")
    unit_type_name, depend_param = _UNIT_STEPS[kind]
    unit_types = [getattr(OrgUnitType, unit_type_name)]
    if kind == "kafedra":
        # Bəzi universitetlərdə kafedra `department` kimi qeyd olunub — hər ikisi.
        unit_types.append(OrgUnitType.DEPARTMENT)

    queryset = org_unit.objects.filter(organization=actor.organization, is_active=True, unit_type__in=unit_types)
    queryset = _scope_units(queryset, actor)
    parent_id = (request.GET.get(depend_param) or "").strip() if depend_param else ""
    if parent_id:
        queryset = queryset.filter(pk__in=review_read.unit_subtree_ids(actor.organization, parent_id))
    term = (request.GET.get("q") or "").strip()
    if term:
        queryset = queryset.filter(name__icontains=term)
    return _lookup_payload(
        queryset.order_by("name"),
        request,
        lambda unit: {"id": str(unit.pk), "text": unit.name},
    )


@never_cache
@login_required
@require_GET
def legacy_review_groups(request):
    """Qrup seçicisi — ixtisas (və ya kafedra/fakültə) alt-ağacı ilə daralır."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse(_EMPTY_LOOKUP)

    from django.apps import apps as django_apps

    from core.constants import OrgUnitType

    org_unit = django_apps.get_model("organizations", "OrgUnit")
    queryset = org_unit.objects.filter(
        organization=actor.organization,
        is_active=True,
        # Universitetdən universitetə qrup vahidinin tipi dəyişir (sahibin
        # «tenant-konfiqurasiyalı struktur» qaydası) — dördü də qəbul olunur.
        unit_type__in=(OrgUnitType.GROUP, OrgUnitType.CLASS, OrgUnitType.SECTION, OrgUnitType.PARALLEL),
    )
    queryset = _scope_units(queryset, actor)
    for param in ("specialty", "kafedra", "faculty"):
        parent_id = (request.GET.get(param) or "").strip()
        if parent_id:
            queryset = queryset.filter(pk__in=review_read.unit_subtree_ids(actor.organization, parent_id))
            break
    term = (request.GET.get("q") or "").strip()
    if term:
        queryset = queryset.filter(name__icontains=term)
    return _lookup_payload(
        queryset.order_by("name"),
        request,
        lambda unit: {"id": str(unit.pk), "text": unit.name},
    )


def _scope_units(queryset, actor):
    """Unit-scoped aktoru öz alt-ağacına kilidlə (seçicidə də, cədvəldə də)."""
    if actor.is_superadmin:
        return queryset
    scope = review_read.actor_scope(actor.user, actor.organization)
    if not scope.has_structure_access:
        return queryset.none()
    if scope.is_org_wide:
        return queryset
    return queryset.filter(scope.unit_subtree_q())


@never_cache
@login_required
@require_GET
def legacy_review_subjects(request):
    """Fənn seçicisi — YALNIZ köhnə faktı olan fənlər (boş nəticə verməsin)."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse(_EMPTY_LOOKUP)

    from apps.registrar.models import Subject

    subject_ids = (
        review_read.review_queue(organization=actor.organization, user=actor.user)
        .exclude(enrollment__isnull=True)
        .values("enrollment__offering__subject_id")
    )
    queryset = Subject.objects.filter(organization=actor.organization, pk__in=subject_ids)
    term = (request.GET.get("q") or "").strip()
    if term:
        queryset = queryset.filter(Q(name__icontains=term) | Q(code__icontains=term))
    return _lookup_payload(
        queryset.order_by("code", "name"),
        request,
        lambda subject: {"id": str(subject.pk), "text": f"{subject.code} — {subject.name}".strip(" —")},
    )


@never_cache
@login_required
@require_GET
def legacy_review_teachers(request):
    """Müəllim seçicisi — növbədəki açılışların müəllimləri."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse(_EMPTY_LOOKUP)

    from django.contrib.auth import get_user_model

    teacher_ids = (
        review_read.review_queue(organization=actor.organization, user=actor.user)
        .exclude(enrollment__offering__instructor__isnull=True)
        .values("enrollment__offering__instructor_id")
    )
    queryset = get_user_model().objects.filter(pk__in=teacher_ids)
    term = (request.GET.get("q") or "").strip()
    if term:
        queryset = queryset.filter(
            Q(first_name__icontains=term) | Q(last_name__icontains=term) | Q(username__icontains=term)
        )
    return _lookup_payload(
        queryset.order_by("last_name", "first_name", "username"),
        request,
        lambda user: {"id": str(user.pk), "text": user.get_full_name() or user.get_username()},
    )


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "legacy_review_groups",
    "legacy_review_options",
    "legacy_review_queue",
    "legacy_review_subjects",
    "legacy_review_teachers",
    "legacy_review_units",
]
