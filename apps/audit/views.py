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

MODUL BÖLGÜSÜ (2026-09-21, modul-ölçü qapısı): sabitlər / əhatə / filtrlər
``views_filters.py``-da, sətir-detal serializasiyası ``views_serializers.py``-da,
CSV ixracı ``views_export.py``-dadır. Hamısı buradan yenidən ixrac olunur —
``urls.py`` və ``from apps.audit.views import …`` yolları dəyişmir.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from core.permissions import is_superadmin_user
from core.tenancy import get_request_organization

from .views_export import audit_log_export  # noqa: F401 — yenidən ixrac (urls.py)
from .views_filters import (  # noqa: F401 — yenidən ixrac
    ACTION_KEYS,
    ACTOR_NONE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_RANGE,
    EXPORT_CAP,
    FAILED_ACTIONS,
    FLAG_ANON,
    FLAG_FAILED,
    FLAG_KEYS,
    FLAG_NOREASON,
    OPTION_CAP,
    PAGE_SIZES,
    PREFIX,
    RANGE_7D,
    RANGE_30D,
    RANGE_ALL,
    RANGE_CUSTOM,
    RANGE_KEYS,
    RANGE_TODAY,
    REASONED_ACTIONS,
    SEARCH_MAX,
    SEARCHABLE_FROM,
    SORT_NEWEST,
    SORT_OLDEST,
    STATUS_FAMILY,
    _query_params,
    _run_scoped,
    _sort_url,
    apply_filters,
    can_export_audit,
    can_view_audit,
    parse_filters,
    resolve_range,
    scoped_queryset,
)
from .views_serializers import (  # noqa: F401 — yenidən ixrac
    _action_tone,
    _display_name,
    _humanize_type,
    _initials,
    _resource_bits,
    _row,
    action_label,
    build_diff,
    serialize_entry,
)

_CTX = "audit.section"


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
    columns.append({"key": "actions", "label": pgettext("accounts.people", "Əməllər"), "sr_only": True})  # P2-8 a11y

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
        "export_url": (
            ("%s?%s" % (reverse("audit:export"), urlencode(params)) if params else reverse("audit:export"))
            if can_export_audit(request)
            else ""
        ),
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


# ─── Görünüşlər ─────────────────────────────────────────────────────────────


@login_required
def audit_log_list(request):
    """Müstəqil (qabıqsız) audit jurnalı səhifəsi — eyni kontekst qurucusu (JSON/CSV nöqtələri 403 qaytarır)."""
    if not can_view_audit(request):
        raise PermissionDenied(
            pgettext("audit.view.permission", "required_permission_missing").format(permission="audit.view")
        )
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
