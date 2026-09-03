"""Müraciətlər JSON API-si — siyahı, detal, kataloq, yaratma, əməl, KPI."""

from __future__ import annotations

from django.core.paginator import Paginator
from django.views.decorators.http import require_GET, require_POST

from ..constants import PAGE_SIZE, PERM_CREATE, PERM_MANAGE
from ..models import ApplicationKind, ApplicationUnit
from ..payloads import STATUS_CATALOG, detail_payload, kind_payload, row_payload, rules_payload, unit_payload
from ..services import access, queries, routing, submit, workflow
from ..state_machine import Action, TransitionDenied
from ._base import error, json_endpoint, load_application, ok


@require_GET
@json_endpoint
def application_list(request, *, organization):
    user = request.user
    tab = request.GET.get("tab", "mine")
    queryset = queries.list_applications(
        organization=organization,
        user=user,
        tab=tab,
        stat=request.GET.get("stat", "open"),
        kind_code=(request.GET.get("kind") or "").strip(),
        search=request.GET.get("q", ""),
    )
    paginator = Paginator(queryset, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page") or 1)
    handled = access.handled_unit_ids(user, organization)
    return ok(
        {
            "results": [
                row_payload(application, viewer_is_handler=application.current_unit_id in handled)
                for application in page.object_list
            ],
            "page": page.number,
            "pages": paginator.num_pages,
            "total": paginator.count,
            "tab": tab,
            "counts": queries.tab_counts(organization=organization, user=user),
        }
    )


@require_GET
@json_endpoint
def application_detail(request, application_id, *, organization):
    application = load_application(request, organization, application_id)
    if application is None:
        return error("Müraciət tapılmadı.", status=404)
    # Emalçı ilk dəfə açanda «Yeni → Baxılır» (dizayn §3.4).
    try:
        workflow.mark_seen(application=application, user=request.user, request=request)
    except TransitionDenied:
        pass
    return ok({"application": detail_payload(application, user=request.user)})


@require_GET
@json_endpoint
def application_catalog(request, *, organization):
    """Yaratma dialoqu + yönləndirmə dialoqu üçün kataloq."""
    user = request.user
    family = routing.sender_family_for(user, organization)
    can_create = bool(family) and access.has_app_permission(user, organization, PERM_CREATE)

    kinds = []
    if can_create:
        # Göndərənin öz bölməsi bir dəfə həll olunur — əks halda hər növ üçün
        # ayrı SAR/üzvlük sorğusu gedərdi (15 növ = 15 sorğu).
        sender_unit = routing.sender_scope_unit_for(user, organization, family)
        for kind in routing.allowed_kinds_for(organization, family):
            destination, _scope, _family, _unit = routing.route_for(
                kind, user, organization=organization, family=family, sender_unit=sender_unit
            )
            kinds.append(kind_payload(kind, destination=destination))

    units = ApplicationUnit.objects.filter(organization=organization, is_active=True).order_by("order", "name")
    return ok(
        {
            "family": family,
            "can_create": can_create,
            "is_handler": access.is_handler_anywhere(user, organization),
            "can_manage": access.has_app_permission(user, organization, PERM_MANAGE),
            "kinds": kinds,
            "units": [unit_payload(unit) for unit in units],
            "statuses": list(STATUS_CATALOG),
            "rules": rules_payload(),
        }
    )


@require_POST
@json_endpoint
def application_create(request, *, organization):
    code = (request.POST.get("kind") or "").strip()
    kind = ApplicationKind.objects.filter(organization=organization, code=code, is_active=True).first()
    if kind is None:
        return error({"kind": ["Müraciət növü seçilməyib."]})
    application = submit.submit_application(
        organization=organization,
        user=request.user,
        kind=kind,
        subject=request.POST.get("subject", ""),
        body=request.POST.get("body", ""),
        files=request.FILES.getlist("files"),
        request=request,
    )
    return ok({"application": detail_payload(application, user=request.user)})


def _action_kwargs(request, organization, action):
    """POST sahələrini SERVER tərəfdə əməlin imzasına çevirir."""
    text = request.POST.get("text") or request.POST.get("reason") or ""
    files = request.FILES.getlist("files")
    if action == Action.FORWARD:
        target = ApplicationUnit.objects.filter(
            organization=organization, code=(request.POST.get("target_unit") or "").strip(), is_active=True
        ).first()
        return {
            "target_unit": target,
            "note": text,
            "keep_watching": (request.POST.get("keep_watching") or "true").lower() not in {"false", "0", "off"},
        }
    if action == Action.ASSIGN:
        from django.contrib.auth import get_user_model

        assignee = get_user_model().objects.filter(pk=(request.POST.get("assignee") or "").strip()).first()
        return {"assignee": assignee, "note": text}
    if action == Action.ADD_COMMENT:
        return {
            "text": text,
            "is_internal": (request.POST.get("is_internal") or "").lower() in {"1", "true", "on"},
            "files": files,
        }
    if action == Action.RESUBMIT:
        return {
            "subject": request.POST.get("subject", ""),
            "body": request.POST.get("body", ""),
            "files": files,
        }
    if action in {Action.RETURN_FOR_CORRECTION, Action.REJECT, Action.CANCEL}:
        return {"reason": text}
    if action in {Action.RESOLVE, Action.REQUEST_INFO, Action.PROVIDE_INFO}:
        return {"text": text, "files": files}
    if action == Action.CLOSE:
        return {"text": text}
    return {}


@require_POST
@json_endpoint
def application_action(request, application_id, *, organization):
    application = load_application(request, organization, application_id)
    if application is None:
        return error("Müraciət tapılmadı.", status=404)
    action = (request.POST.get("action") or "").strip()
    handler = workflow.ACTION_DISPATCH.get(action)
    if handler is None:
        return error({"action": ["Naməlum əməl."]})
    handler(
        application=application, user=request.user, request=request, **_action_kwargs(request, organization, action)
    )
    application.refresh_from_db()
    return ok({"application": detail_payload(application, user=request.user)})


@require_GET
@json_endpoint
def application_kpis(request, *, organization):
    user = request.user
    payload = {
        "sender": queries.sender_kpis(organization=organization, user=user),
        "is_handler": access.is_handler_anywhere(user, organization),
        "counts": queries.tab_counts(organization=organization, user=user),
    }
    if payload["is_handler"]:
        payload["handler"] = queries.handler_kpis(organization=organization, user=user)
    return ok(payload)


__all__ = [
    "application_action",
    "application_catalog",
    "application_create",
    "application_detail",
    "application_kpis",
    "application_list",
]
