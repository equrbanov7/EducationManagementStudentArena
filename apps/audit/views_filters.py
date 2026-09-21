"""Audit jurnalı — əhatə qapıları, filtr parametrləri və sorğu süzgəci.

``apps/audit/views.py``-dan ayrılıb (modul-ölçü qapısı, 2026-09-21): sabitlər,
``can_view_audit`` / ``can_export_audit``, ``parse_filters`` / ``apply_filters``
və URL parametr qurucuları buradadır. ``views.py`` eyni adları yenidən ixrac
edir — ``from apps.audit.views import RANGE_30D`` işləməyə davam edir.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from core.constants import AuditAction
from core.permissions import is_superadmin_user, request_has_permission
from core.tenancy import get_request_organization

from .models import AuditLog

#: Filtr parametrlərinin ad fəzası (`ems_ui/_filter_bar.html` müqaviləsi).
PREFIX = "al_"
PAGE_SIZES = (25, 50, 100)
DEFAULT_PAGE_SIZE = 25
#: CSV ixracının tavanı — brauzerə və yaddaşa qarşı sığorta.
EXPORT_CAP = 10_000
#: Seçici siyahılarının tavanı (icraçı / resurs tipi / təşkilat).
OPTION_CAP = 300
SEARCH_MAX = 120
#: Menyuda daxili axtarış sətri bu qədər seçimdən sonra görünür.
SEARCHABLE_FROM = 8

RANGE_TODAY = "today"
RANGE_7D = "7d"
RANGE_30D = "30d"
RANGE_ALL = "all"
RANGE_CUSTOM = "custom"
DEFAULT_RANGE = RANGE_30D
RANGE_KEYS = (RANGE_TODAY, RANGE_7D, RANGE_30D, RANGE_ALL, RANGE_CUSTOM)

FLAG_NOREASON = "noreason"
FLAG_FAILED = "failed"
FLAG_ANON = "anon"
FLAG_KEYS = (FLAG_NOREASON, FLAG_FAILED, FLAG_ANON)

SORT_NEWEST = "newest"
SORT_OLDEST = "oldest"

ACTOR_NONE = "none"
STATUS_FAMILY = "audit_action"

#: Səbəb tələb edən əməliyyatlar — «səbəbsiz dəyişiklik» KPI-sı bunlara baxır.
REASONED_ACTIONS = (AuditAction.UPDATE, AuditAction.DELETE)
#: «Uğursuz» hadisələr — rədd və yoxlama sorğusu.
FAILED_ACTIONS = (AuditAction.DENY, AuditAction.CHALLENGE)
ACTION_KEYS = tuple(key for key, _label in AuditAction.CHOICES)


# ─── Əhatə ──────────────────────────────────────────────────────────────────


def can_view_audit(request) -> bool:
    """Fail-closed qapı: superadmin · təşkilat sahibi · `audit.view` daşıyıcısı.

    Superadmin ƏVVƏL yoxlanır ki, `request_has_permission`-ın üzvlüksüz
    superadmin üçün yazdığı «cross-org» audit qeydi hər panel açılışında
    təkrarlanmasın.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if is_superadmin_user(user):
        return True
    organization = get_request_organization(request)
    if organization is None:
        return False
    if getattr(organization, "owner_id", None) == user.id:
        return True
    return request_has_permission(request, "audit.view")


def can_export_audit(request) -> bool:
    """CSV ixracı: baxış qapısı + `audit.export` (audit 2026-09-13 F-06, 2026-09-14; superadmin/sahib azad)."""
    if not can_view_audit(request):
        return False
    user = request.user
    if is_superadmin_user(user) or getattr(get_request_organization(request), "owner_id", None) == user.id:
        return True
    return request_has_permission(request, "audit.export")


def scoped_queryset(*, is_superadmin: bool, organization):
    """Aktorun görə biləcəyi qeydlər — superadmin hamısı, digərləri öz təşkilatı."""
    queryset = AuditLog.objects.select_related("user", "organization", "content_type")
    if is_superadmin:
        return queryset
    return queryset.none() if organization is None else queryset.filter(organization=organization)


def _run_scoped(is_superadmin: bool, func):
    """Superadmin üçün `bypass_rls()` daxilində, digərləri üçün adi çağırış. Şablon render-i
    kontekstdən kənarda baş verdiyi üçün nəticələr `func` içində MATERİALLAŞDIRILMALIDIR."""
    if not is_superadmin:
        return func()
    from core.rls import bypass_rls

    with bypass_rls():
        return func()


# ─── Parametrlər ────────────────────────────────────────────────────────────


def _param(request, name: str, default: str = "") -> str:
    return (request.GET.get(PREFIX + name) or default).strip()[:SEARCH_MAX]


def _parse_date(raw: str):
    try:
        return date.fromisoformat(raw[:10]) if raw else None
    except ValueError:
        return None


def _pk_or_none(model, raw: str):
    """Sətri modelin PK tipinə çevirir; yararsız dəyər filtr kimi ATILIR."""
    if not raw:
        return None
    try:
        return model._meta.pk.to_python(raw)
    except (TypeError, ValueError, ValidationError):
        return None


def resolve_range(range_key: str, start_raw: str, end_raw: str, *, today=None):
    """``(key, start_date | None, end_date | None)`` — yerli günlər, hər iki uc daxil.

    Preset seçiləndə tarix sahələri NƏZƏRƏ ALINMIR (URL-də köhnə dəyər qala
    bilər); `custom` isə ən azı bir tarix tələb edir, əks halda defolta düşür.
    """
    today = today or timezone.localdate()
    key = range_key if range_key in RANGE_KEYS else DEFAULT_RANGE
    if key == RANGE_CUSTOM:
        start, end = _parse_date(start_raw), _parse_date(end_raw)
        if start is None and end is None:
            key = DEFAULT_RANGE
        else:
            if start and end and start > end:
                start, end = end, start
            return key, start, end
    days = {RANGE_TODAY: 0, RANGE_7D: 6, RANGE_30D: 29}.get(key)
    if days is None:
        return RANGE_ALL, None, None
    return key, today - timedelta(days=days), today


def _day_start(value: date):
    return timezone.make_aware(datetime.combine(value, time.min), timezone.get_current_timezone())


def parse_filters(request, *, is_superadmin: bool) -> dict:
    """URL parametrlərini normallaşdırılmış filtr sözlüyünə çevirir."""
    range_key, start, end = resolve_range(_param(request, "range"), _param(request, "from"), _param(request, "to"))
    action = _param(request, "action")
    flag = _param(request, "flag")
    sort = _param(request, "sort")
    try:
        size = int(_param(request, "size") or DEFAULT_PAGE_SIZE)
    except ValueError:
        size = DEFAULT_PAGE_SIZE
    organization_model = django_apps.get_model("organizations", "Organization")
    return {
        "q": _param(request, "q"),
        "range": range_key,
        "start": start,
        "end": end,
        "action": action if action in ACTION_KEYS else "",
        "resource": _param(request, "resource"),
        "actor": _param(request, "actor"),
        "flag": flag if flag in FLAG_KEYS else "",
        "org": _param(request, "org") if is_superadmin else "",
        "org_id": _pk_or_none(organization_model, _param(request, "org")) if is_superadmin else None,
        "sort": SORT_OLDEST if sort == SORT_OLDEST else SORT_NEWEST,
        "size": size if size in PAGE_SIZES else DEFAULT_PAGE_SIZE,
    }


def _search_q(term: str) -> Q:
    query = (
        Q(user__username__icontains=term)
        | Q(user__first_name__icontains=term)
        | Q(user__last_name__icontains=term)
        | Q(resource_repr__icontains=term)
        | Q(resource_type__icontains=term)
        | Q(resource_id__icontains=term)
        | Q(object_id__icontains=term)
        | Q(reason__icontains=term)
    )
    try:
        as_uuid = uuid.UUID(term)
    except (ValueError, AttributeError):
        as_uuid = None
    if as_uuid is not None:
        query |= Q(request_id=as_uuid) | Q(id=as_uuid)
    return query


def apply_filters(queryset, filters: dict):
    """Filtr sözlüyünü queryset-ə tətbiq edir — bölmə və CSV ixracı üçün TƏK mənbə."""
    if filters["start"] is not None:
        queryset = queryset.filter(created_at__gte=_day_start(filters["start"]))
    if filters["end"] is not None:
        queryset = queryset.filter(created_at__lt=_day_start(filters["end"] + timedelta(days=1)))
    if filters["action"]:
        queryset = queryset.filter(action=filters["action"])
    resource = filters["resource"]
    if resource:
        kind, _sep, value = resource.partition(":")
        if kind == "rt" and value:
            queryset = queryset.filter(resource_type=value)
        elif kind == "ct" and value.isdigit():
            queryset = queryset.filter(resource_type="", content_type_id=int(value))
    actor = filters["actor"]
    if actor == ACTOR_NONE:
        queryset = queryset.filter(user__isnull=True)
    elif actor:
        actor_pk = _pk_or_none(get_user_model(), actor)
        if actor_pk is not None:
            queryset = queryset.filter(user_id=actor_pk)
    if filters.get("org_id") is not None:
        queryset = queryset.filter(organization_id=filters["org_id"])
    flag = filters["flag"]
    if flag == FLAG_NOREASON:
        queryset = queryset.filter(action__in=REASONED_ACTIONS, reason="")
    elif flag == FLAG_FAILED:
        queryset = queryset.filter(action__in=FAILED_ACTIONS)
    elif flag == FLAG_ANON:
        queryset = queryset.filter(user__isnull=True)
    if filters["q"]:
        queryset = queryset.filter(_search_q(filters["q"]))
    order = ("created_at", "id") if filters["sort"] == SORT_OLDEST else ("-created_at", "-id")
    return queryset.order_by(*order)


def _query_params(filters: dict, is_superadmin: bool) -> dict:
    """Defolt olmayan filtr dəyərləri — səhifələmə linkləri və ixrac URL-i üçün."""
    params = {
        PREFIX + "q": filters["q"],
        PREFIX + "range": filters["range"] if filters["range"] != DEFAULT_RANGE else "",
        PREFIX + "from": filters["start"].isoformat() if filters["range"] == RANGE_CUSTOM and filters["start"] else "",
        PREFIX + "to": filters["end"].isoformat() if filters["range"] == RANGE_CUSTOM and filters["end"] else "",
        PREFIX + "action": filters["action"],
        PREFIX + "resource": filters["resource"],
        PREFIX + "actor": filters["actor"],
        PREFIX + "flag": filters["flag"],
        PREFIX + "org": filters["org"] if is_superadmin else "",
        PREFIX + "sort": filters["sort"] if filters["sort"] != SORT_NEWEST else "",
        PREFIX + "size": str(filters["size"]) if filters["size"] != DEFAULT_PAGE_SIZE else "",
    }
    return {key: value for key, value in params.items() if value}


def _sort_url(filters: dict, is_superadmin: bool) -> str:
    flipped = dict(filters, sort=SORT_OLDEST if filters["sort"] == SORT_NEWEST else SORT_NEWEST)
    return "?" + urlencode({"section": "audit-log", **_query_params(flipped, is_superadmin)})
