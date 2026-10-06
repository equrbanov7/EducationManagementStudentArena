"""İdarə səthi (``announcement.manage``): siyahı + statistika, yarat/redaktə, önizləmə, əməllər.

Səhifələr profil örtüyündədir (``accounts/profile_embed_base.html`` — sol sidebar qalır).
Hər yazı əvvəl əhatəni yoxlayır (``services.access``); əhatədən kənar elan 404 verir.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from apps.applications.models import ApplicationKind, ApplicationUnit

from ..constants import (
    ATTACHMENT_ACCEPT,
    MANAGE_PAGE_SIZE,
    MANAGE_STATES,
    PROFILE_SECTION,
    ApplyMode,
    Audience,
    Category,
    Priority,
)
from ..forms import AnnouncementForm
from ..models import Announcement
from ..services import access, manage, snapshot
from ..services.queries import decorate
from ._base import error, ok

_CTX = "announcements.manage"
_ACTIONS = ("publish", "unpublish", "archive", "restore", "delete")


def _gate(request):
    organization = getattr(request, "organization", None)
    scope = access.manage_scope(request.user, organization, request=request)
    if organization is None or not scope.has_structure_access:
        raise PermissionDenied
    return organization, scope


def _load(request, organization, scope, announcement_id):
    announcement = (
        Announcement.objects.filter(organization=organization, pk=announcement_id)
        .select_related("apply_kind", "apply_unit", "created_by")
        .prefetch_related("attachments")
        .first()
    )
    if announcement is None or not access.can_edit(scope, request.user, announcement, organization):
        raise Http404
    return announcement


def _page_context(request, **extra):
    return {
        "embed_active_section": PROFILE_SECTION,
        "embed_section_title": pgettext(_CTX, "Elanların idarəsi"),
        "cabinet_url": f"{reverse('accounts:profile')}?section={PROFILE_SECTION}",
        **extra,
    }


def _list_params(request):
    try:
        page = max(1, int(request.GET.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    state = request.GET.get("state") or "all"
    category = request.GET.get("category") or ""
    return {
        "q": (request.GET.get("q") or "").strip()[:100],
        "state": state if state in MANAGE_STATES else "all",
        "category": category if category in Category.values else "",
        "page": page,
    }


@login_required
@require_GET
def manage_list(request):
    organization, scope = _gate(request)
    if snapshot.snapshot_is_stale(organization):  # self-healing (bax services/snapshot)
        snapshot.sync_snapshot(organization)
    params = _list_params(request)
    listing = manage.manage_list(organization, scope, request.user, page_size=MANAGE_PAGE_SIZE, **params)
    context = _page_context(
        request,
        listing=listing,
        params=params,
        states=MANAGE_STATES,
        categories=Category.choices,
        is_org_wide=scope.is_org_wide,
    )
    return render(request, "announcements/manage/list.html", context)


@login_required
@require_GET
def manage_rows(request):
    """Siyahının fraqmenti (debounce-lu axtarış / filtr) — JSON + HTML."""
    try:
        organization, scope = _gate(request)
    except PermissionDenied:
        return error(pgettext(_CTX, "Səlahiyyət yoxdur."), status=403)
    params = _list_params(request)
    listing = manage.manage_list(organization, scope, request.user, page_size=MANAGE_PAGE_SIZE, **params)
    html = render_to_string("announcements/manage/_rows.html", {"listing": listing, "params": params}, request)
    return ok(html=html, total=listing["total"], page=listing["page"], pages=listing["pages"])


def _form_options(organization, scope, announcement=None):
    kinds = ApplicationKind.objects.filter(organization=organization, is_active=True).select_related("target_unit")
    units = ApplicationUnit.objects.filter(organization=organization, is_active=True)
    selected = {str(unit) for unit in (announcement.audience_units if announcement else [])}
    unit_choices = access.scope_unit_choices(scope, organization)
    for choice in unit_choices:
        choice["checked"] = choice["id"] in selected
    return {
        "categories": Category.choices,
        "priorities": Priority.choices,
        "families": Audience.choices,
        "apply_modes": ApplyMode.choices,
        "kinds": [
            {"id": str(kind.pk), "label": kind.label, "unit": kind.target_unit.name, "families": kind.families}
            for kind in kinds.order_by("order", "label")
        ],
        "app_units": [{"id": str(unit.pk), "label": unit.name} for unit in units.order_by("order", "name")],
        "unit_choices": unit_choices,
        "is_org_wide": scope.is_org_wide,
        "attachment_accept": ATTACHMENT_ACCEPT,
    }


def _bound_data(request):
    data = request.POST.copy()
    data["audience_units"] = ",".join(request.POST.getlist("audience_units"))
    return data


def _initial(announcement):
    def _local(value):
        return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M") if value else ""

    return {
        "title": announcement.title,
        "summary": announcement.summary,
        "body": announcement.body,
        "category": announcement.category,
        "priority": announcement.priority,
        "is_pinned": announcement.is_pinned,
        "show_as_popup": announcement.show_as_popup,
        "publish_at": _local(announcement.publish_at),
        "expires_at": _local(announcement.expires_at),
        "deadline_at": _local(announcement.deadline_at),
        "audience_families": list(announcement.audience_families or []),
        "apply_mode": announcement.apply_mode,
        "apply_kind": str(announcement.apply_kind_id or ""),
        "apply_unit": str(announcement.apply_unit_id or ""),
        "apply_url": announcement.apply_url,
        "apply_label": announcement.apply_label,
    }


def _edit(request, organization, scope, announcement=None):
    form_errors = []
    if request.method == "POST":
        form = AnnouncementForm(_bound_data(request), organization=organization)
        if form.is_valid():
            try:
                with transaction.atomic():
                    saved = manage.save_announcement(
                        request, organization, scope, form.cleaned_data, announcement=announcement
                    )
                    manage.add_attachments(request, organization, saved, request.FILES.getlist("files"))
            except ValidationError as exc:
                form_errors = exc.messages
            else:
                if request.POST.get("then") == "publish":
                    try:
                        manage.transition(request, organization, scope, saved, "publish")
                        messages.success(request, pgettext(_CTX, "Elan dərc olundu."))
                    except ValidationError as exc:
                        messages.error(request, "; ".join(exc.messages))
                else:
                    messages.success(request, pgettext(_CTX, "Elan yadda saxlanıldı."))
                return redirect("announcements:manage_edit", announcement_id=saved.pk)
        values = request.POST
        families = request.POST.getlist("audience_families")
    else:
        form = AnnouncementForm(organization=organization)
        values = _initial(announcement) if announcement else {"category": "general", "priority": 0, "apply_mode": "none"}
        families = values.get("audience_families", []) if announcement else ["students"]
    options = _form_options(organization, scope, announcement)
    if request.method == "POST":
        posted_units = set(request.POST.getlist("audience_units"))
        for choice in options["unit_choices"]:
            choice["checked"] = choice["id"] in posted_units
    stats = None
    if announcement is not None:
        stats = manage.receipt_stats([announcement.pk]).get(announcement.pk, {"seen": 0, "read": 0, "applied": 0})
        stats["targeted"] = manage.targeted_count(announcement)
        decorate(announcement, timezone.now())
    context = _page_context(
        request,
        form=form,
        form_errors=form_errors,
        values=values,
        selected_families=families,
        announcement=announcement,
        stats=stats,
        **options,
    )
    return render(request, "announcements/manage/form.html", context)


@login_required
def manage_create(request):
    organization, scope = _gate(request)
    return _edit(request, organization, scope)


@login_required
def manage_edit(request, announcement_id):
    organization, scope = _gate(request)
    return _edit(request, organization, scope, _load(request, organization, scope, announcement_id))


@login_required
@require_POST
def manage_action(request, announcement_id):
    organization, scope = _gate(request)
    announcement = _load(request, organization, scope, announcement_id)
    action = request.POST.get("action") or ""
    if action == "remove_attachment":
        manage.remove_attachment(organization, announcement, request.POST.get("attachment") or None)
        messages.success(request, pgettext(_CTX, "Sənəd silindi."))
        return redirect("announcements:manage_edit", announcement_id=announcement.pk)
    if action not in _ACTIONS:
        raise Http404
    try:
        manage.transition(request, organization, scope, announcement, action)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("announcements:manage_edit", announcement_id=announcement.pk)
    labels = {
        "publish": pgettext(_CTX, "Elan dərc olundu."),
        "unpublish": pgettext(_CTX, "Elan qaralamaya qaytarıldı."),
        "archive": pgettext(_CTX, "Elan arxivləndi."),
        "restore": pgettext(_CTX, "Elan arxivdən qaytarıldı (qaralama)."),
        "delete": pgettext(_CTX, "Qaralama silindi."),
    }
    messages.success(request, labels[action])
    if action == "delete":
        return redirect("announcements:manage_list")
    return redirect("announcements:manage_edit", announcement_id=announcement.pk)


@login_required
@require_GET
def manage_preview(request, announcement_id):
    """İstifadəçinin görəcəyi detal kartı (qaralama da) — yazı yoxdur."""
    organization, scope = _gate(request)
    announcement = _load(request, organization, scope, announcement_id)
    decorate(announcement, timezone.now())
    context = _page_context(request, item=announcement, preview=True)
    return render(request, "announcements/manage/preview.html", context)


__all__ = ["manage_action", "manage_create", "manage_edit", "manage_list", "manage_preview", "manage_rows"]
