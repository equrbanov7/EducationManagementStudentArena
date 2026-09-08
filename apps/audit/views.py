"""Audit jurnalı — kabinet bölməsi, müstəqil səhifə, JSON detal və CSV ixrac.

2026-09-08 yenidən qurulub («dünya təcrübəsi» — Auth0 / Stripe / CloudTrail
tipli jurnal): KPI sırası, AVTO filtr paneli (`al_` prefiksi), server tərəfli
səhifələmə + səhifə ölçüsü, sətir çekmecəsi (oxunaqlı əvvəl → sonra fərqi) və
cari filtrin CSV ixracı.

ƏHATƏ (fail-closed, hər üç giriş nöqtəsində EYNİ `can_view_audit`):
  * superadmin — BÜTÜN tenantlar (`bypass_rls()` daxilində materiallaşdırılır,
    `audit_auditlog` RLS altındadır); «Təşkilat» filtri yalnız ona açılır;
  * təşkilat sahibi və `audit.view` daşıyıcısı — yalnız aktiv təşkilat.

SORĞU BÜDCƏSİ səhifə ölçüsündən asılı deyil: sətirlər `select_related`
(user · organization · content_type) ilə gəlir, resurs göstərişi GenericFK-ya
TOXUNMUR (hər sətirdə əlavə sorğu olmasın), KPI-lar bir aqreqat + bir
qruplaşdırma sorğusudur, seçici siyahıları tavanlıdır (`OPTION_CAP`).

TARİX ARALIĞI yerli günlərlə (Asia/Baku) hesablanır: preset (bu gün / 7 gün /
30 gün / bütün vaxtlar) və ya «seçilmiş aralıq» (`al_from` / `al_to`). Tarix
sahəsi dəyişəndə filtr paneli select-i avtomatik `custom`-a keçirir.
"""

from __future__ import annotations

import csv
import json
import uuid
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from core.constants import AuditAction
from core.permissions import is_superadmin_user, request_has_permission
from core.tenancy import get_request_organization
from core.ui import status_catalog

from .models import AuditLog

_CTX = "audit.section"

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


def scoped_queryset(*, is_superadmin: bool, organization):
    """Aktorun görə biləcəyi qeydlər — superadmin hamısı, digərləri öz təşkilatı."""
    queryset = AuditLog.objects.select_related("user", "organization", "content_type")
    if is_superadmin:
        return queryset
    if organization is None:
        return queryset.none()
    return queryset.filter(organization=organization)


def _run_scoped(is_superadmin: bool, func):
    """Superadmin üçün `bypass_rls()` daxilində, digərləri üçün adi çağırış.

    Şablon render-i kontekstdən kənarda baş verdiyi üçün nəticələr `func`
    içində MATERİALLAŞDIRILMALIDIR (lazy queryset kifayət etmir).
    """
    if not is_superadmin:
        return func()
    from core.rls import bypass_rls

    with bypass_rls():
        return func()


# ─── Parametrlər ────────────────────────────────────────────────────────────


def _param(request, name: str, default: str = "") -> str:
    return (request.GET.get(PREFIX + name) or default).strip()[:SEARCH_MAX]


def _parse_date(raw: str):
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
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
    if key == RANGE_TODAY:
        return key, today, today
    if key == RANGE_7D:
        return key, today - timedelta(days=6), today
    if key == RANGE_30D:
        return key, today - timedelta(days=29), today
    return RANGE_ALL, None, None


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


# ─── Sətir / detal serializasiyası ──────────────────────────────────────────


def _initials(name: str) -> str:
    parts = [part for part in (name or "").split() if part]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _display_name(user) -> str:
    return (user.get_full_name() or "").strip() or user.username


def _humanize_type(value: str) -> str:
    return value.replace("_", " ").replace(".", " › ").strip().capitalize() if value else ""


def action_label(key: str) -> str:
    return str(status_catalog.label(STATUS_FAMILY, key))


def _action_tone(key: str) -> str:
    status = status_catalog.get(STATUS_FAMILY, key)
    return status.tone if status is not None else "neutral"


def _resource_bits(log) -> tuple[str, str, str]:
    """``(tip etiketi, identifikator, göstəriş)`` — GenericFK-ya TOXUNMADAN."""
    type_key = log.resource_type or (log.content_type.model if log.content_type_id else "")
    identifier = log.resource_id or log.object_id or ""
    repr_text = log.resource_repr or ""
    if not repr_text and type_key and identifier:
        repr_text = f"{_humanize_type(type_key)} #{identifier}"
    return _humanize_type(type_key), identifier, repr_text


def _row(log, *, profile_url_name="accounts:public_profile") -> dict:
    user = log.user if log.user_id else None
    name = _display_name(user) if user is not None else ""
    type_label, identifier, repr_text = _resource_bits(log)
    return {
        "id": str(log.id),
        "created_at": log.created_at,
        "actor_name": name,
        "actor_username": user.username if user is not None else "",
        "actor_initials": _initials(name) if name else "",
        "actor_url": reverse(profile_url_name, kwargs={"username": user.username}) if user is not None else "",
        "action": log.action,
        "action_label": action_label(log.action),
        "resource_type": type_label,
        "resource_type_key": log.resource_type or "",
        "resource_id": identifier,
        # `resource_label` YALNIZ həqiqi `resource_repr`-dir; sintez olunmuş
        # «Tip #id» forması `resource_display`-dədir (CSV/detal) — xana
        # tip+id-ni ayrıca göstərdiyi üçün təkrar olmasın.
        "resource_label": log.resource_repr or "",
        "resource_display": repr_text,
        "reason": log.reason or "",
        "reason_missing": log.action in REASONED_ACTIONS and not (log.reason or "").strip(),
        "ip": log.ip_address or "",
        "org_name": log.organization.name if log.organization_id else "",
        "has_changes": bool(log.changes or log.old_values or log.new_values),
        "detail_url": reverse("audit:detail", kwargs={"pk": log.id}),
    }


def _diff_state(before, after, *, in_old: bool, in_new: bool) -> str:
    if not in_old and in_new:
        return "added"
    if in_old and not in_new:
        return "removed"
    if before is None and after is not None:
        return "added"
    if before is not None and after is None:
        return "removed"
    return "same" if before == after else "changed"


def build_diff(old_values, new_values, changes) -> list[dict]:
    """Oxunaqlı əvvəl → sonra siyahısı.

    Prioritet `changes`-dədir (`{sahə: {"old": …, "new": …}}` konvensiyası;
    `[old, new]` cütü və düz dəyər də qəbul olunur). O yoxdursa, `old_values` və
    `new_values` açar-açar tutuşdurulur; dəyişməyən sahələr `same` kimi qalır
    (UI onları yığılmış göstərir).
    """
    old = old_values if isinstance(old_values, dict) else {}
    new = new_values if isinstance(new_values, dict) else {}
    rows: list[dict] = []
    if isinstance(changes, dict) and changes:
        for key, value in changes.items():
            key = str(key)
            if isinstance(value, dict) and value and set(value) <= {"old", "new"}:
                before, after = value.get("old"), value.get("new")
                in_old, in_new = "old" in value, "new" in value
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                before, after = value[0], value[1]
                in_old, in_new = True, True
            else:
                before, after = old.get(key), value
                in_old, in_new = key in old, True
            rows.append(
                {
                    "key": key,
                    "old": before,
                    "new": after,
                    "state": _diff_state(before, after, in_old=in_old, in_new=in_new),
                }
            )
        return rows
    for key in sorted(set(old) | set(new), key=str):
        before, after = old.get(key), new.get(key)
        rows.append(
            {
                "key": str(key),
                "old": before,
                "new": after,
                "state": _diff_state(before, after, in_old=key in old, in_new=key in new),
            }
        )
    return rows


def serialize_entry(log, *, list_url: str) -> dict:
    """Çekmecə üçün tam qeyd (JSON)."""
    row = _row(log)
    created_local = timezone.localtime(log.created_at)
    type_label, identifier, repr_text = _resource_bits(log)
    diff = build_diff(log.old_values, log.new_values, log.changes)
    filter_links = {}
    if log.user_id:
        filter_links["actor"] = (
            f"{list_url}?{urlencode({'section': 'audit-log', PREFIX + 'actor': log.user_id, PREFIX + 'range': RANGE_ALL})}"
        )
    if log.request_id:
        filter_links["request"] = (
            f"{list_url}?{urlencode({'section': 'audit-log', PREFIX + 'q': str(log.request_id), PREFIX + 'range': RANGE_ALL})}"
        )
    return {
        "id": row["id"],
        "created_at": created_local.isoformat(),
        "created_display": created_local.strftime("%d.%m.%Y %H:%M:%S"),
        "actor": (
            {
                "name": row["actor_name"],
                "username": row["actor_username"],
                "initials": row["actor_initials"],
                "url": row["actor_url"],
            }
            if log.user_id
            else None
        ),
        "organization": row["org_name"],
        "action": log.action,
        "action_label": row["action_label"],
        "action_tone": _action_tone(log.action),
        "resource": {
            "type": type_label,
            "type_key": log.resource_type or "",
            "id": identifier,
            "repr": repr_text,
            "content_type": (f"{log.content_type.app_label}.{log.content_type.model}" if log.content_type_id else ""),
            "object_id": log.object_id or "",
        },
        "reason": log.reason or "",
        "reason_required": log.action in REASONED_ACTIONS,
        "ip_address": log.ip_address or "",
        "user_agent": log.user_agent or "",
        "request_id": str(log.request_id) if log.request_id else "",
        "diff": diff,
        "changed_count": sum(1 for item in diff if item["state"] != "same"),
        "raw": {"old_values": log.old_values, "new_values": log.new_values, "changes": log.changes},
        "filter_links": filter_links,
    }


# ─── Seçici siyahıları ──────────────────────────────────────────────────────


def _range_labels() -> dict:
    return {
        RANGE_TODAY: pgettext(_CTX, "Bu gün"),
        RANGE_7D: pgettext(_CTX, "Son 7 gün"),
        RANGE_30D: pgettext(_CTX, "Son 30 gün"),
        RANGE_ALL: pgettext(_CTX, "Bütün vaxtlar"),
        RANGE_CUSTOM: pgettext(_CTX, "Seçilmiş aralıq"),
    }


def _flag_labels() -> dict:
    return {
        FLAG_NOREASON: pgettext(_CTX, "Səbəbsiz dəyişikliklər"),
        FLAG_FAILED: pgettext(_CTX, "Rədd və yoxlama sorğuları"),
        FLAG_ANON: pgettext(_CTX, "Anonim / sistem hadisələri"),
    }


def _action_options() -> list[dict]:
    return [{"value": "", "label": pgettext(_CTX, "Bütün əməliyyatlar")}] + [
        {"value": key, "label": action_label(key)} for key in ACTION_KEYS
    ]


def _resource_options(scope) -> tuple[list[dict], dict]:
    """Əhatədəki fərqli resurs tipləri — `rt:<ad>` və (boş `resource_type`
    olan sətirlər üçün) `ct:<content_type_id>` dəyərləri."""
    labels: dict = {}
    for value in (
        scope.exclude(resource_type="").order_by().values_list("resource_type", flat=True).distinct()[:OPTION_CAP]
    ):
        labels[f"rt:{value}"] = _humanize_type(value)
    content_type_ids = list(
        scope.filter(resource_type="", content_type__isnull=False)
        .order_by()
        .values_list("content_type_id", flat=True)
        .distinct()[:OPTION_CAP]
    )
    if content_type_ids:
        for content_type in ContentType.objects.filter(id__in=content_type_ids):
            labels[f"ct:{content_type.id}"] = f"{_humanize_type(content_type.model)} · {content_type.app_label}"
    options = [{"value": key, "label": label} for key, label in sorted(labels.items(), key=lambda kv: kv[1].casefold())]
    return [{"value": "", "label": pgettext(_CTX, "Bütün resurslar")}] + options, labels


def _actor_options(scope) -> tuple[list[dict], dict]:
    labels: dict = {}
    rows = (
        scope.filter(user__isnull=False)
        .order_by()
        .values_list("user_id", "user__username", "user__first_name", "user__last_name")
        .distinct()[:OPTION_CAP]
    )
    for user_id, username, first, last in rows:
        key = str(user_id)
        if key in labels:
            continue
        full = f"{first or ''} {last or ''}".strip()
        labels[key] = f"{full} (@{username})" if full else f"@{username}"
    options = [{"value": key, "label": label} for key, label in sorted(labels.items(), key=lambda kv: kv[1].casefold())]
    anonymous = pgettext(_CTX, "Anonim / sistem")
    labels[ACTOR_NONE] = anonymous
    return (
        [{"value": "", "label": pgettext(_CTX, "Bütün icraçılar")}, {"value": ACTOR_NONE, "label": anonymous}]
        + options,
        labels,
    )


def _organization_options() -> tuple[list[dict], dict]:
    organization_model = django_apps.get_model("organizations", "Organization")
    labels = {
        str(pk): name
        for pk, name in organization_model.objects.filter(is_active=True)
        .order_by("name")
        .values_list("id", "name")[:OPTION_CAP]
    }
    return (
        [{"value": "", "label": pgettext(_CTX, "Bütün təşkilatlar")}]
        + [{"value": k, "label": v} for k, v in labels.items()],
        labels,
    )


# ─── Bölmə konteksti ────────────────────────────────────────────────────────


def _denied(request) -> dict:
    return {
        "has_access": False,
        "access_denied_message": pgettext(
            _CTX, "Audit jurnalına baxış üçün `audit.view` icazəsi və aktiv təşkilat konteksti lazımdır."
        ),
        "audit_logs": [],
        "current_organization": get_request_organization(request),
        "is_superadmin": is_superadmin_user(getattr(request, "user", None)),
    }


def build_audit_log_context(request) -> dict:
    """`audit_log_section` sözlüyü — kabinet bölməsi VƏ müstəqil səhifə üçün."""
    if not can_view_audit(request):
        return _denied(request)
    is_superadmin = is_superadmin_user(request.user)
    organization = get_request_organization(request)
    filters = parse_filters(request, is_superadmin=is_superadmin)

    def _collect():
        scope = scoped_queryset(is_superadmin=is_superadmin, organization=organization)
        queryset = apply_filters(scope, filters)
        page_obj = Paginator(queryset, filters["size"]).get_page(request.GET.get(PREFIX + "page"))
        page_obj.object_list = list(page_obj.object_list)
        totals = queryset.aggregate(
            total=Count("id"),
            actors=Count("user_id", distinct=True),
            no_reason=Count("id", filter=Q(action__in=REASONED_ACTIONS, reason="")),
            failed=Count("id", filter=Q(action__in=FAILED_ACTIONS)),
        )
        mix = list(queryset.order_by().values("action").annotate(n=Count("id")).order_by("-n", "action"))
        return {
            "page_obj": page_obj,
            "totals": totals,
            "mix": mix,
            "resource": _resource_options(scope),
            "actor": _actor_options(scope),
            "org": _organization_options() if is_superadmin else ([], {}),
        }

    data = _run_scoped(is_superadmin, _collect)
    page_obj, totals, mix = data["page_obj"], data["totals"], data["mix"]
    resource_options, resource_labels = data["resource"]
    actor_options, actor_labels = data["actor"]
    org_options, org_labels = data["org"]

    rows = [_row(log) for log in page_obj.object_list]
    range_labels = _range_labels()
    flag_labels = _flag_labels()
    action_labels = {key: action_label(key) for key in ACTION_KEYS}
    total = totals["total"] or 0

    action_mix = [
        {
            "key": item["action"],
            "label": action_labels.get(item["action"], item["action"]),
            "tone": _action_tone(item["action"]),
            "count": item["n"],
            "pct": round(item["n"] * 100 / total, 1) if total else 0,
        }
        for item in mix
    ]
    top = action_mix[0] if action_mix else None

    range_note = range_labels[filters["range"]]
    if filters["range"] == RANGE_CUSTOM:
        range_note = "%s — %s" % (
            filters["start"].isoformat() if filters["start"] else "…",
            filters["end"].isoformat() if filters["end"] else "…",
        )
    kpi_tiles = [
        {"label": pgettext(_CTX, "Hadisə"), "value": total, "tone": "primary", "note": range_note},
        {
            "label": pgettext(_CTX, "İcraçı"),
            "value": totals["actors"] or 0,
            "note": pgettext(_CTX, "fərqli istifadəçi"),
        },
        {
            "label": pgettext(_CTX, "Ən çox əməliyyat"),
            "value": top["label"] if top else "—",
            "note": (
                pgettext(_CTX, "%(n)d hadisə · %(pct)s") % {"n": top["count"], "pct": "%s%%" % top["pct"]}
                if top
                else pgettext(_CTX, "hadisə yoxdur")
            ),
        },
        {
            "label": pgettext(_CTX, "Səbəbsiz dəyişiklik"),
            "value": totals["no_reason"] or 0,
            "tone": "accent-warning" if totals["no_reason"] else "accent-success",
            "note": (
                pgettext(_CTX, "dəyişiklik / silinmə səbəbsiz")
                if totals["no_reason"]
                else pgettext(_CTX, "hamısında səbəb var")
            ),
            "filter": FLAG_NOREASON,
            "pressed": filters["flag"] == FLAG_NOREASON,
        },
        {
            "label": pgettext(_CTX, "Rədd / yoxlama"),
            "value": totals["failed"] or 0,
            "tone": "accent-danger" if totals["failed"] else "",
            "note": (
                pgettext(_CTX, "rədd və yoxlama sorğusu")
                if totals["failed"]
                else pgettext(_CTX, "uğursuz hadisə yoxdur")
            ),
            "filter": FLAG_FAILED,
            "pressed": filters["flag"] == FLAG_FAILED,
        },
    ]

    columns = [
        {
            "key": "time",
            "label": pgettext(_CTX, "Vaxt"),
            "sortable": True,
            "sort_url": _sort_url(filters, is_superadmin),
            "sort_dir": "descending" if filters["sort"] == SORT_NEWEST else "ascending",
        },
        {"key": "actor", "label": pgettext(_CTX, "İcraçı")},
        {"key": "action", "label": pgettext(_CTX, "Əməliyyat")},
        {"key": "resource", "label": pgettext(_CTX, "Resurs")},
        {"key": "reason", "label": pgettext(_CTX, "Səbəb")},
        {"key": "ip", "label": pgettext(_CTX, "IP")},
    ]
    if is_superadmin:
        columns.append({"key": "org", "label": pgettext(_CTX, "Təşkilat")})
    columns.append({"key": "actions", "label": ""})

    cell_dir = "audit/partials/"
    table_rows = []
    for row in rows:
        cells = [
            {"include": f"{cell_dir}_cell_actor.html"},
            {"badge_family": STATUS_FAMILY, "badge_key": row["action"]},
            {"include": f"{cell_dir}_cell_resource.html"},
            {"include": f"{cell_dir}_cell_reason.html"},
            {"text": row["ip"] or "—", "mono": bool(row["ip"]), "muted": not row["ip"], "nowrap": True},
        ]
        if is_superadmin:
            cells.append({"text": row["org_name"] or "—", "muted": not row["org_name"], "nowrap": True})
        table_rows.append(
            {
                "row_head": row["created_at"],
                "head_include": f"{cell_dir}_cell_time.html",
                "cells": cells,
                "actions_include": f"{cell_dir}_row_actions.html",
                "data": row,
            }
        )

    filter_fields = [
        {
            "name": PREFIX + "q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": filters["q"],
            "wide": True,
            "placeholder": pgettext(_CTX, "İcraçı, resurs, səbəb və ya sorğu ID"),
        },
        {
            "name": PREFIX + "range",
            "label": pgettext(_CTX, "Dövr"),
            "kind": "select",
            "value": filters["range"],
            "default": DEFAULT_RANGE,
            "options": [{"value": key, "label": range_labels[key]} for key in RANGE_KEYS],
        },
        {
            "name": PREFIX + "from",
            "label": pgettext(_CTX, "Başlanğıc"),
            "kind": "date",
            "value": filters["start"].isoformat() if filters["start"] else "",
            "range_select": PREFIX + "range",
            "range_custom": RANGE_CUSTOM,
        },
        {
            "name": PREFIX + "to",
            "label": pgettext(_CTX, "Son"),
            "kind": "date",
            "value": filters["end"].isoformat() if filters["end"] else "",
            "range_select": PREFIX + "range",
            "range_custom": RANGE_CUSTOM,
        },
        {
            "name": PREFIX + "action",
            "label": pgettext(_CTX, "Əməliyyat"),
            "kind": "select",
            "value": filters["action"],
            "default": "",
            "options": _action_options(),
        },
        {
            "name": PREFIX + "resource",
            "label": pgettext(_CTX, "Resurs tipi"),
            "kind": "select",
            "value": filters["resource"] if filters["resource"] in resource_labels else "",
            "default": "",
            "searchable": len(resource_options) > SEARCHABLE_FROM,
            "options": resource_options,
        },
        {
            "name": PREFIX + "actor",
            "label": pgettext(_CTX, "İcraçı"),
            "kind": "select",
            "value": filters["actor"] if filters["actor"] in actor_labels else "",
            "default": "",
            "searchable": len(actor_options) > SEARCHABLE_FROM,
            "options": actor_options,
        },
        {
            "name": PREFIX + "flag",
            "label": pgettext(_CTX, "Yalnız"),
            "kind": "select",
            "value": filters["flag"],
            "default": "",
            "options": [{"value": "", "label": pgettext(_CTX, "Hamısı")}]
            + [{"value": key, "label": flag_labels[key]} for key in FLAG_KEYS],
        },
    ]
    if is_superadmin:
        filter_fields.append(
            {
                "name": PREFIX + "org",
                "label": pgettext(_CTX, "Təşkilat"),
                "kind": "select",
                "value": filters["org"] if filters["org"] in org_labels else "",
                "default": "",
                "searchable": len(org_options) > SEARCHABLE_FROM,
                "options": org_options,
            }
        )
    filter_fields.append(
        {
            "name": PREFIX + "size",
            "label": pgettext(_CTX, "Səhifədə"),
            "kind": "select",
            "value": str(filters["size"]),
            "default": str(DEFAULT_PAGE_SIZE),
            "options": [{"value": str(size), "label": str(size)} for size in PAGE_SIZES],
        }
    )

    applied = []
    if filters["range"] != DEFAULT_RANGE:
        applied.append({"name": PREFIX + "range", "label": pgettext(_CTX, "Dövr"), "value_label": range_note})
    for key, label, value_label in (
        ("action", pgettext(_CTX, "Əməliyyat"), action_labels.get(filters["action"], "")),
        ("resource", pgettext(_CTX, "Resurs tipi"), resource_labels.get(filters["resource"], "")),
        ("actor", pgettext(_CTX, "İcraçı"), actor_labels.get(filters["actor"], "")),
        ("flag", pgettext(_CTX, "Yalnız"), flag_labels.get(filters["flag"], "")),
        ("org", pgettext(_CTX, "Təşkilat"), org_labels.get(filters["org"], "")),
        ("q", pgettext(_CTX, "Axtarış"), filters["q"]),
    ):
        if filters[key] and value_label:
            applied.append({"name": PREFIX + key, "label": label, "value_label": value_label})

    params = _query_params(filters, is_superadmin)
    is_filtered = bool(applied)
    list_url = reverse("audit:list")
    return {
        "has_access": True,
        "is_superadmin": is_superadmin,
        "current_organization": organization,
        "prefix": PREFIX,
        "filters": filters,
        "rows": rows,
        "table_rows": table_rows,
        "columns": columns,
        "table_state": "ready" if rows else "empty",
        "page_obj": page_obj,
        "audit_logs": page_obj.object_list,
        "audit_logs_page_obj": page_obj,
        "pagination_query": urlencode({"section": "audit-log", **params}),
        "filtered_count": total,
        "kpi_tiles": kpi_tiles,
        "action_mix": action_mix,
        "filter_fields": filter_fields,
        "filter_applied": applied,
        "filter_count_label": pgettext(_CTX, "Nəticə: %(n)d hadisə") % {"n": total},
        "export_url": "%s?%s" % (reverse("audit:export"), urlencode(params)) if params else reverse("audit:export"),
        "list_url": list_url,
        "range_note": range_note,
        "state_title": (
            pgettext(_CTX, "Filtrə uyğun hadisə yoxdur")
            if is_filtered
            else pgettext(_CTX, "Seçilmiş dövrdə hadisə yoxdur")
        ),
        "state_body": (
            pgettext(_CTX, "Axtarışı dəyişin və ya «Sıfırla» ilə son 30 günə qayıdın.")
            if is_filtered
            else pgettext(_CTX, "Dövrü genişləndirin («Bütün vaxtlar») və ya başqa aralıq seçin.")
        ),
        "subtitle": (
            pgettext(
                _CTX,
                "Bütün təşkilatların əməliyyat izi: kim, nə vaxt, nəyi dəyişib. Sətrə klik tam qeydi "
                "və əvvəl → sonra fərqini açır; cari filtr CSV kimi yüklənir.",
            )
            if is_superadmin
            else pgettext(
                _CTX,
                "Təşkilatınızın əməliyyat izi: kim, nə vaxt, nəyi dəyişib. Sətrə klik tam qeydi və "
                "əvvəl → sonra fərqini açır; cari filtr CSV kimi yüklənir.",
            )
        ),
    }


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


# ─── Görünüşlər ─────────────────────────────────────────────────────────────


def _raise_permission_denied():
    """Müstəqil səhifə üçün `PermissionDenied` (JSON/CSV giriş nöqtələri 403 qaytarır)."""
    raise PermissionDenied(
        pgettext("audit.view.permission", "required_permission_missing").format(permission="audit.view")
    )


@login_required
def audit_log_list(request):
    """Müstəqil (qabıqsız) audit jurnalı səhifəsi — eyni kontekst qurucusu."""
    if not can_view_audit(request):
        _raise_permission_denied()
    context = build_audit_log_context(request)
    return render(
        request,
        "audit/list.html",
        {"audit_log_section": context, "standalone": True, "page_title": pgettext(_CTX, "Audit jurnalı")},
    )


@login_required
@require_GET
def audit_log_detail(request, pk):
    """Bir qeydin tam məzmunu (JSON) — sətir çekmecəsi üçün. Əhatə siyahı ilə eynidir."""
    if not can_view_audit(request):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    is_superadmin = is_superadmin_user(request.user)
    organization = get_request_organization(request)

    def _load():
        entry = scoped_queryset(is_superadmin=is_superadmin, organization=organization).filter(pk=pk).first()
        return serialize_entry(entry, list_url=reverse("accounts:profile")) if entry is not None else None

    payload = _run_scoped(is_superadmin, _load)
    if payload is None:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)
    return JsonResponse({"ok": True, "entry": payload})


class _Echo:
    """`csv.writer` üçün yazılanı olduğu kimi qaytaran bufer (Django sənəd naxışı)."""

    def write(self, value):
        return value


def _csv_header() -> list[str]:
    return [
        pgettext(_CTX, "Vaxt"),
        pgettext(_CTX, "İcraçı (istifadəçi adı)"),
        pgettext(_CTX, "İcraçı (ad)"),
        pgettext(_CTX, "Əməliyyat"),
        pgettext(_CTX, "Resurs tipi"),
        pgettext(_CTX, "Resurs ID"),
        pgettext(_CTX, "Resurs"),
        pgettext(_CTX, "Təşkilat"),
        pgettext(_CTX, "Səbəb"),
        pgettext(_CTX, "IP ünvanı"),
        pgettext(_CTX, "Sorğu ID"),
        pgettext(_CTX, "Dəyişikliklər (JSON)"),
    ]


def _csv_row(log) -> list:
    user = log.user if log.user_id else None
    type_label, identifier, repr_text = _resource_bits(log)
    changes = (
        log.changes
        if log.changes
        else ({"old": log.old_values, "new": log.new_values} if (log.old_values or log.new_values) else None)
    )
    return [
        timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S"),
        user.username if user is not None else "",
        _display_name(user) if user is not None else "",
        action_label(log.action),
        log.resource_type or (log.content_type.model if log.content_type_id else ""),
        identifier,
        repr_text,
        log.organization.name if log.organization_id else "",
        log.reason or "",
        log.ip_address or "",
        str(log.request_id) if log.request_id else "",
        json.dumps(changes, ensure_ascii=False, default=str) if changes is not None else "",
    ]


@login_required
@require_GET
def audit_log_export(request):
    """Cari filtrin CSV ixracı (UTF-8 BOM, axınla; tavan `EXPORT_CAP`).

    Sətirlər GÖRÜNÜŞ İÇİNDƏ materiallaşdırılır: axın middleware zəncirindən
    SONRA oxunur və tenant/RLS konteksti o vaxt artıq sıfırlanmış ola bilər.
    İxracın özü də auditə düşür («auditçini audit et»).
    """
    if not can_view_audit(request):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    is_superadmin = is_superadmin_user(request.user)
    organization = get_request_organization(request)
    filters = parse_filters(request, is_superadmin=is_superadmin)

    def _materialize():
        queryset = apply_filters(scoped_queryset(is_superadmin=is_superadmin, organization=organization), filters)
        rows = [_csv_row(log) for log in queryset[: EXPORT_CAP + 1].iterator(chunk_size=500)]
        truncated = len(rows) > EXPORT_CAP
        rows = rows[:EXPORT_CAP]
        from core.audit import log_action

        log_action(
            AuditAction.EXPORT,
            user=request.user,
            organization=organization,
            request=request,
            resource_type="audit_log",
            resource_repr="CSV",
            reason=pgettext(_CTX, "Audit jurnalı CSV ixracı: %(n)d sətir") % {"n": len(rows)},
            new_values={"filters": _query_params(filters, is_superadmin), "rows": len(rows), "truncated": truncated},
        )
        return rows, truncated

    rows, truncated = _run_scoped(is_superadmin, _materialize)
    writer = csv.writer(_Echo())

    def _stream():
        yield "\ufeff"  # BOM — Excel UTF-8 Azərbaycan hərflərini düzgün oxusun
        yield writer.writerow(_csv_header())
        for row in rows:
            yield writer.writerow(row)

    filename = "audit-jurnali-%s.csv" % timezone.localdate().isoformat()
    response = StreamingHttpResponse(_stream(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    response["X-Audit-Export-Rows"] = str(len(rows))
    response["X-Audit-Export-Truncated"] = "1" if truncated else "0"
    return response
