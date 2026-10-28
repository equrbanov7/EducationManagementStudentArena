"""Müraciətlər JSON API-si — siyahı, detal, kataloq, yaratma, əməl, KPI."""

from __future__ import annotations

from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_POST

from ..constants import PAGE_SIZE, PERM_CREATE, PERM_MANAGE, ApplicationStatus
from ..models import ApplicationKind, ApplicationUnit
from ..payloads import STATUS_CATALOG, detail_payload, kind_payload, row_payload, rules_payload, unit_payload
from ..services import access, queries, routing, submit, workflow
from ..services.recipients import destination_payload, selectable_units
from ..state_machine import Action
from ._base import error, json_endpoint, load_application, ok
from .documents import detail_with_tools


def _date_param(request, name):
    """``?from=`` / ``?to=`` → ``date`` | ``None``. FAIL-SOFT.

    ``parse_date`` formatı tutan, amma mövcud olmayan tarixdə (``2026-13-45``)
    ``ValueError`` atır — tutulmasa süzgəc sətrinə yazılan zibil 500 verərdi.
    """
    try:
        return parse_date((request.GET.get(name) or "").strip())
    except ValueError:
        return None


@require_GET
@json_endpoint
def application_list(request, *, organization):
    user = request.user
    tab = request.GET.get("tab", "mine")
    if tab == "all" and not access.can_oversee(user, organization):
        # «Bütün müraciətlər» yalnız nəzarətçiyə (RİM) — URL-i əl ilə yazan 403 alır.
        return error("Bu siyahıya baxmaq üçün icazəniz yoxdur.", status=403)
    queryset = queries.list_applications(
        organization=organization,
        user=user,
        tab=tab,
        stat=request.GET.get("stat", "open"),
        kind_code=(request.GET.get("kind") or "").strip(),
        search=request.GET.get("q", ""),
        # Tarix aralığı fail-soft-dur: yararsız dəyər `None` olur və süzgəc
        # sadəcə tətbiq olunmur — 400 vermək filtrləri «qırıq» göstərərdi.
        date_from=_date_param(request, "from"),
        date_to=_date_param(request, "to"),
        # Şöbə / göndərən bölməsi (RİM nəzarəti): görünən dəsti yalnız DARALDIR.
        unit_code=(request.GET.get("unit") or "").strip(),
        sender_unit=(request.GET.get("sender_unit") or "").strip(),
    )
    paginator = Paginator(queryset, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page") or 1)
    return ok(
        {
            "results": [
                row_payload(application, viewer_is_handler=access.is_current_handler(user, application))
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
    # Emalçı ilk dəfə açanda «Yeni → Baxılır» (dizayn §3.4) — bilərəkdən qalan
    # GET-daxili keçid (QA 2026-09-05 P3-19: "yan-təsirli GET"). Read-only
    # baxıcı (göndərən, izləyən şöbə) heç bir yazı TƏTİKLƏMİR: `can_act` yalnız
    # QƏRAR hüququ olan cari şöbənin emalçısını keçirir (bax `access.can_act`).
    # Status yoxlaması ilə eyni şərt təkrar (idempotent) açılışlarda `mark_seen`-i
    # heç çağırmır — `workflow.mark_seen`-in öz daxili yoxlaması ilə üst-üstə
    # düşür, amma burada AÇIQ və şərtsiz istisna-tutma OLMADAN yoxlanır.
    # 2026-10-26: RİM (hər müraciəti cavablandıran) başqa şöbənin müraciətini AÇANDA keçid olmur —
    # şöbənin «Yeni» nişanı itməsin; RİM-in ilk QƏRARI «Baxılır»ı özü yazır (`workflow._take_into_review`).
    if (
        application.deleted_at is None
        and application.status == ApplicationStatus.SUBMITTED.value
        and access.is_current_handler(request.user, application)
    ):
        workflow.mark_seen(application=application, user=request.user, request=request)
    # 2026-10-19: «Arayış sorğusu» emalçısına «Arayışı hazırla» bloku (views.documents).
    return ok({"application": detail_with_tools(application, request=request)})


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
            if family == "student" and not destination.accepts_students:
                continue
            item = kind_payload(kind, destination=destination)
            item["recipients"] = destination_payload(destination)
            kinds.append(item)

    # ``access.active_units`` təşkilat üzrə keşlənib (bax P2-26/P2-6) — yuxarıdakı
    # dövr də daxil olmaqla eyni kataloqu artıq təkrar sorğulamır.
    units = access.active_units(organization)
    can_oversee = access.can_oversee(user, organization)
    payload = {
        "family": family,
        "can_create": can_create,
        "is_handler": access.is_handler_anywhere(user, organization),
        "can_manage": access.has_app_permission(user, organization, PERM_MANAGE),
        "can_oversee": can_oversee,
        "kinds": kinds,
        "units": [
            {**unit_payload(unit), "recipients": destination_payload(unit)} for unit in selectable_units(units, family)
        ],
        "statuses": list(STATUS_CATALOG),
        "rules": rules_payload(),
    }
    if can_oversee:
        # «Bütün müraciətlər» növ süzgəci göndərənin ailəsindən asılı deyil — BÜTÜN aktiv növlər.
        active_kinds = ApplicationKind.objects.filter(organization=organization, is_active=True)
        payload["filter_kinds"] = [kind_payload(kind) for kind in active_kinds.order_by("order", "label")]
    return ok(payload)


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
        recipient_id=request.POST.get("recipient"),
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
            "recipient_id": request.POST.get("recipient"),
            "scope_id": request.POST.get("scope"),
            "note": text,
            "keep_watching": (request.POST.get("keep_watching") or "true").lower() not in {"false", "0", "off"},
        }
    if action == Action.ASSIGN:
        from django.contrib.auth import get_user_model

        raw_assignee = (request.POST.get("assignee") or "").strip()
        try:
            assignee_pk = int(raw_assignee)
        except ValueError:
            # 'abc' / boş → `filter(pk=...)` ValueError ilə 500 verirdi (QA 2026-09-05 APPLICATIONS-06).
            assignee_pk = None
        assignee = get_user_model().objects.filter(pk=assignee_pk).first() if assignee_pk is not None else None
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
    if action in {Action.RESOLVE, Action.REQUEST_INFO, Action.PROVIDE_INFO, Action.REOPEN}:
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
    from ..services.content import edit_application, edit_reply, set_application_deleted
    from ..services.reply_visibility import set_reply_visibility

    if action == "edit_reply":
        edit_reply(
            application=application,
            user=request.user,
            event_id=request.POST.get("event"),
            text=request.POST.get("text", ""),
            expected_revision=request.POST.get("revision"),
            request=request,
        )
        return ok({"application": detail_with_tools(application, request=request)})
    if action == "edit_application":
        edit_application(
            application=application,
            user=request.user,
            subject=request.POST.get("subject", ""),
            body=request.POST.get("body", ""),
            expected_updated_at=request.POST.get("updated_at"),
            request=request,
        )
        return ok({"application": detail_with_tools(application, request=request)})
    if action in {"delete_application", "restore_application"}:
        set_application_deleted(
            application=application,
            user=request.user,
            deleted=action == "delete_application",
            expected_updated_at=request.POST.get("updated_at"),
            request=request,
        )
        return ok({"application": detail_with_tools(application, request=request)})

    if action in {"hide_reply", "restore_reply"}:
        set_reply_visibility(
            application=application,
            user=request.user,
            event_id=request.POST.get("event"),
            hidden=action == "hide_reply",
            request=request,
        )
        return ok({"application": detail_with_tools(application, request=request)})
    handler = workflow.ACTION_DISPATCH.get(action)
    if handler is None:
        return error({"action": ["Naməlum əməl."]})
    handler(
        application=application, user=request.user, request=request, **_action_kwargs(request, organization, action)
    )
    application.refresh_from_db()
    return ok({"application": detail_with_tools(application, request=request)})


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
